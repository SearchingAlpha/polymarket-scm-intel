"""
Polymarket API client wrapping both the Gamma (metadata) and CLOB (pricing) APIs.
Handles rate limiting, caching, retries, and pagination automatically.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import yaml

logger = logging.getLogger(__name__)

_settings: Optional[Dict] = None


def _load_settings() -> Dict:
    global _settings
    if _settings is None:
        settings_path = Path(__file__).parents[2] / "config" / "settings.yaml"
        with open(settings_path) as f:
            _settings = yaml.safe_load(f)
    return _settings


class RateLimiter:
    """Token bucket rate limiter to stay within API limits."""

    def __init__(self, requests_per_minute: int) -> None:
        self.rate = requests_per_minute / 60.0  # requests per second
        self.tokens = float(requests_per_minute)
        self.max_tokens = float(requests_per_minute)
        self.last_update = time.monotonic()

    def acquire(self) -> None:
        """Block until a request token is available."""
        while True:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.max_tokens, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            sleep_time = (1.0 - self.tokens) / self.rate
            time.sleep(sleep_time)


class PolymarketClient:
    """
    Client for both the Polymarket Gamma API and CLOB API.

    All responses are cached to data/raw/ as JSON. Re-fetch is skipped if a
    cached file exists and is newer than settings.data.cache_ttl_hours.
    """

    def __init__(self, settings: Optional[Dict] = None) -> None:
        cfg = settings or _load_settings()
        gamma_cfg = cfg["api"]["gamma"]
        clob_cfg = cfg["api"]["clob"]

        self.gamma_base = gamma_cfg["base_url"].rstrip("/")
        self.clob_base = clob_cfg["base_url"].rstrip("/")
        self.timeout = gamma_cfg.get("timeout", 30)
        self.max_retries = gamma_cfg.get("max_retries", 3)
        self.retry_backoff_base = gamma_cfg.get("retry_backoff_base", 2.0)
        self.cache_ttl_hours = cfg["data"].get("cache_ttl_hours", 24)

        rate_limit = gamma_cfg.get("rate_limit_per_minute", 100)
        self._rate_limiter = RateLimiter(rate_limit)

        raw_dir = Path(cfg["data"]["raw_dir"])
        raw_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir = raw_dir

        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_path(self, key: str) -> Path:
        """Return path for a cache file, sanitising the key."""
        safe = key.replace("/", "_").replace("?", "_").replace("&", "_").replace("=", "-")
        return self.raw_dir / f"{safe}.json"

    def _is_cache_valid(self, path: Path) -> bool:
        if not path.exists():
            return False
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        return datetime.now() - mtime < timedelta(hours=self.cache_ttl_hours)

    def _load_cache(self, path: Path) -> Any:
        with open(path) as f:
            return json.load(f)

    def _save_cache(self, path: Path, data: Any) -> None:
        with open(path, "w") as f:
            json.dump(data, f)

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, params: Optional[Dict] = None) -> Any:
        """Make a GET request with rate limiting, retries, and caching."""
        # Build a cache key from URL + sorted params
        param_str = ""
        if params:
            param_str = "_" + "_".join(f"{k}-{v}" for k, v in sorted(params.items()))
        cache_key = url.replace("https://", "").replace("http://", "") + param_str
        cache_path = self._cache_path(cache_key)

        if self._is_cache_valid(cache_path):
            logger.debug("Cache hit: %s", cache_path.name)
            return self._load_cache(cache_path)

        self._rate_limiter.acquire()

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug("GET %s params=%s (attempt %d)", url, params, attempt)
                resp = self._session.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                self._save_cache(cache_path, data)
                return data
            except requests.exceptions.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 429:
                    wait = self.retry_backoff_base ** attempt
                    logger.warning("Rate limited. Waiting %.1fs before retry.", wait)
                    time.sleep(wait)
                elif attempt == self.max_retries:
                    raise
                else:
                    wait = self.retry_backoff_base ** attempt
                    logger.warning("HTTP error %s. Retrying in %.1fs.", exc, wait)
                    time.sleep(wait)
            except requests.exceptions.RequestException as exc:
                if attempt == self.max_retries:
                    raise
                wait = self.retry_backoff_base ** attempt
                logger.warning("Request error %s. Retrying in %.1fs.", exc, wait)
                time.sleep(wait)

    # ------------------------------------------------------------------
    # Gamma API — market metadata
    # ------------------------------------------------------------------

    def get_tags(self) -> List[Dict]:
        """Return all available tags/categories from the Gamma API."""
        url = f"{self.gamma_base}/tags"
        result = self._get(url)
        return result if isinstance(result, list) else result.get("data", [])

    def get_events(
        self,
        limit: int = 100,
        active: Optional[bool] = None,
        closed: Optional[bool] = None,
        tag_id: Optional[int] = None,
    ) -> List[Dict]:
        """
        Fetch all events with automatic pagination.

        Args:
            limit: Page size (max 100).
            active: Filter to active markets only if True.
            closed: Filter to closed markets only if True.
            tag_id: Filter by numeric tag ID.

        Returns:
            Flat list of all matching event dicts.
        """
        url = f"{self.gamma_base}/events"
        params: Dict[str, Any] = {"limit": limit}
        if active is not None:
            params["active"] = str(active).lower()
        if closed is not None:
            params["closed"] = str(closed).lower()
        if tag_id is not None:
            params["tag_id"] = tag_id

        all_events: List[Dict] = []
        offset = 0
        while True:
            params["offset"] = offset
            page = self._get(url, params=dict(params))  # copy to vary cache key
            items = page if isinstance(page, list) else page.get("data", page)
            if not items:
                break
            all_events.extend(items)
            if len(items) < limit:
                break
            offset += limit
            logger.debug("Fetched %d events so far (offset %d)", len(all_events), offset)

        return all_events

    def get_markets(
        self,
        limit: int = 100,
        tag_id: Optional[int] = None,
        active: Optional[bool] = None,
        closed: Optional[bool] = None,
    ) -> List[Dict]:
        """
        Fetch all markets with automatic pagination.

        Args:
            limit: Page size.
            tag_id: Filter by tag.
            active: Filter active markets.
            closed: Filter closed markets.

        Returns:
            Flat list of all matching market dicts.
        """
        url = f"{self.gamma_base}/markets"
        params: Dict[str, Any] = {"limit": limit}
        if tag_id is not None:
            params["tag_id"] = tag_id
        if active is not None:
            params["active"] = str(active).lower()
        if closed is not None:
            params["closed"] = str(closed).lower()

        all_markets: List[Dict] = []
        offset = 0
        while True:
            params["offset"] = offset
            page = self._get(url, params=dict(params))
            items = page if isinstance(page, list) else page.get("data", page)
            if not items:
                break
            all_markets.extend(items)
            if len(items) < limit:
                break
            offset += limit

        return all_markets

    # ------------------------------------------------------------------
    # CLOB API — pricing and timeseries
    # ------------------------------------------------------------------

    def get_price(self, token_id: str) -> Optional[float]:
        """
        Return the current midpoint price (implied probability) for a single token.

        Args:
            token_id: CLOB token ID (from clobTokenIds).

        Returns:
            Float probability in [0, 1], or None if unavailable.
        """
        url = f"{self.clob_base}/price"
        try:
            data = self._get(url, params={"token_id": token_id})
            price = data.get("price")
            return float(price) if price is not None else None
        except Exception as exc:
            logger.warning("Failed to get price for token %s: %s", token_id, exc)
            return None

    def get_prices_history(
        self,
        token_id: str,
        interval: str = "max",
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        fidelity: Optional[int] = None,
    ) -> List[Dict]:
        """
        Fetch historical price data for a CLOB token.

        Args:
            token_id: CLOB token ID.
            interval: One of 'max', '1w', '1d', '6h', '1h'.
            start_ts: Optional Unix timestamp for start of range.
            end_ts: Optional Unix timestamp for end of range.
            fidelity: Optional data point density hint.

        Returns:
            List of dicts with keys 't' (timestamp) and 'p' (price string).
        """
        url = f"{self.clob_base}/prices-history"
        params: Dict[str, Any] = {"market": token_id, "interval": interval}
        if start_ts is not None:
            params["startTs"] = start_ts
        if end_ts is not None:
            params["endTs"] = end_ts
        if fidelity is not None:
            params["fidelity"] = fidelity

        try:
            data = self._get(url, params=params)
            return data.get("history", [])
        except Exception as exc:
            logger.warning(
                "Failed to fetch price history for token %s: %s", token_id, exc
            )
            return []

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def parse_outcome_prices(outcome_prices_str: str) -> List[float]:
        """
        Parse outcomePrices from the Gamma API string format.

        Example input: '["0.65", "0.35"]'
        Returns: [0.65, 0.35]
        """
        try:
            parsed = json.loads(outcome_prices_str)
            return [float(p) for p in parsed]
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning("Could not parse outcomePrices: %r", outcome_prices_str)
            return []

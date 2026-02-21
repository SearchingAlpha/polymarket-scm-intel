"""
Fetch and normalise Polymarket price histories into daily-frequency DataFrames.

For binary Yes/No markets only the "Yes" token is retained
(No probability = 1 - Yes probability).
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yaml

from .client import PolymarketClient
from .market_discovery import load_discovered_markets

logger = logging.getLogger(__name__)


def _load_settings() -> Dict:
    path = Path(__file__).parents[2] / "config" / "settings.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _history_to_series(history: List[Dict], market_id: str, title: str) -> pd.DataFrame:
    """
    Convert raw CLOB price history to a DataFrame.

    Args:
        history: List of {t: unix_ts, p: price_str} dicts.
        market_id: Market identifier for labelling.
        title: Human-readable market title.

    Returns:
        DataFrame with columns [timestamp, probability, market_id, market_title].
    """
    if not history:
        return pd.DataFrame(columns=["timestamp", "probability", "market_id", "market_title"])

    rows = []
    for point in history:
        ts = point.get("t")
        price = point.get("p")
        if ts is None or price is None:
            continue
        try:
            rows.append({"timestamp": pd.to_datetime(ts, unit="s", utc=True), "probability": float(price)})
        except (TypeError, ValueError):
            continue

    if not rows:
        return pd.DataFrame(columns=["timestamp", "probability", "market_id", "market_title"])

    df = pd.DataFrame(rows)
    df["market_id"] = market_id
    df["market_title"] = title
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def _resample_daily(df: pd.DataFrame) -> pd.DataFrame:
    """
    Resample to daily frequency (last observation per UTC day).

    Args:
        df: DataFrame with a 'timestamp' (tz-aware) column and 'probability'.

    Returns:
        DataFrame indexed by date with 'probability' column.
    """
    df = df.set_index("timestamp")
    df.index = df.index.normalize()  # floor to midnight UTC
    df = df[~df.index.duplicated(keep="last")]
    daily = df["probability"].resample("D").last().ffill()
    result = daily.reset_index()
    result.columns = ["date", "probability"]
    result["date"] = result["date"].dt.date
    return result


class TimeseriesFetcher:
    """
    Fetches and caches daily Polymarket probability timeseries for all
    discovered supply-chain-relevant markets.

    Usage::

        client = PolymarketClient()
        fetcher = TimeseriesFetcher(client)
        ts_dict = fetcher.fetch_all()
        # Returns {market_id: DataFrame(date, probability)}
    """

    def __init__(self, client: Optional[PolymarketClient] = None) -> None:
        self.client = client or PolymarketClient()
        self.settings = _load_settings()
        self.processed_dir = Path(self.settings["data"]["processed_dir"])
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def fetch_for_market(
        self,
        market_id: str,
        title: str,
        clob_token_ids: List[str],
        interval: str = "max",
        start_ts: Optional[int] = None,
    ) -> Optional[pd.DataFrame]:
        """
        Fetch and return daily probability series for a single market.

        For binary markets the first token (Yes) is used.

        Args:
            market_id: Unique market identifier.
            title: Human-readable title (for labelling).
            clob_token_ids: List of CLOB token IDs for this market.
            interval: CLOB API interval parameter.
            start_ts: Optional Unix timestamp; only fetch data on or after this time.

        Returns:
            DataFrame with columns [date, probability, market_id, market_title],
            or None if no data is available.
        """
        if not clob_token_ids:
            logger.warning("No CLOB token IDs for market %s – skipping.", market_id)
            return None

        # Use the first (Yes) token
        token_id = clob_token_ids[0]
        logger.info("Fetching history for market %s (token %s) …", market_id, token_id)

        history = self.client.get_prices_history(token_id, interval=interval, start_ts=start_ts)
        if not history:
            logger.warning("No price history returned for market %s.", market_id)
            return None

        raw_df = _history_to_series(history, market_id, title)
        if raw_df.empty:
            return None

        daily = _resample_daily(raw_df)
        daily["market_id"] = market_id
        daily["market_title"] = title

        # Apply date range filter from settings
        start = self.settings["analysis"]["study_period"]["start"]
        end = self.settings["analysis"]["study_period"]["end"]
        daily = daily[(daily["date"].astype(str) >= start) & (daily["date"].astype(str) <= end)]

        return daily if not daily.empty else None

    def fetch_all(
        self,
        markets_df: Optional[pd.DataFrame] = None,
        interval: str = "max",
        force_refresh: bool = False,
        start_ts: Optional[int] = None,
        max_workers: int = 8,
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch daily probability timeseries for all discovered markets.

        Fetches are issued in parallel (``max_workers`` threads) while the
        shared ``RateLimiter`` inside the client serialises the actual HTTP
        calls, hiding network latency and cutting wall-clock time significantly.

        Args:
            markets_df: Pre-loaded DataFrame of discovered markets. If None,
                        loads from the saved CSV.
            interval: CLOB API interval.
            force_refresh: If True, re-fetch even if cached CSV exists.
            start_ts: Optional Unix timestamp; only request data on or after
                      this point (passed directly to the CLOB ``startTs`` param).
            max_workers: Thread pool size. 8 is a safe default that saturates
                         the 100 req/min rate limit without overloading the API.

        Returns:
            Dict mapping market_id → daily probability DataFrame.
        """
        if markets_df is None:
            markets_df = load_discovered_markets()

        logger.info("Fetching timeseries for %d markets …", len(markets_df))

        # Separate cached from markets that need a network call
        timeseries: Dict[str, pd.DataFrame] = {}
        to_fetch: List[Dict] = []

        for _, row in markets_df.iterrows():
            market_id = str(row["market_id"])
            cache_path = self.processed_dir / f"ts_{market_id}.csv"
            if cache_path.exists() and not force_refresh:
                logger.debug("Loading cached timeseries for %s", market_id)
                df = pd.read_csv(cache_path, parse_dates=["date"])
                df["date"] = df["date"].dt.date
                timeseries[market_id] = df
            else:
                to_fetch.append({
                    "market_id": market_id,
                    "title": str(row["title"]),
                    "clob_ids": row["clob_token_ids"],
                })

        logger.info(
            "%d markets loaded from cache; %d require API calls.",
            len(timeseries),
            len(to_fetch),
        )

        if not to_fetch:
            return timeseries

        def _fetch_one(item: Dict) -> tuple:
            mid = item["market_id"]
            df = self.fetch_for_market(
                mid,
                item["title"],
                item["clob_ids"],
                interval=interval,
                start_ts=start_ts,
            )
            return mid, df

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_fetch_one, item): item for item in to_fetch}
            for future in as_completed(futures):
                try:
                    market_id, df = future.result()
                    if df is not None and not df.empty:
                        cache_path = self.processed_dir / f"ts_{market_id}.csv"
                        df.to_csv(cache_path, index=False)
                        timeseries[market_id] = df
                except Exception as exc:
                    item = futures[future]
                    logger.error("Failed to fetch %s: %s", item["market_id"], exc)

        logger.info(
            "Timeseries fetched for %d / %d markets.", len(timeseries), len(markets_df)
        )
        return timeseries

    def build_panel(self, timeseries: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        Stack all individual timeseries into a single long-format DataFrame.

        Returns:
            DataFrame with columns [date, probability, market_id, market_title].
        """
        if not timeseries:
            return pd.DataFrame(columns=["date", "probability", "market_id", "market_title"])

        parts = list(timeseries.values())
        panel = pd.concat(parts, ignore_index=True)
        panel["date"] = pd.to_datetime(panel["date"])
        panel = panel.sort_values(["market_id", "date"]).reset_index(drop=True)

        out_path = self.processed_dir / "timeseries_panel.csv"
        panel.to_csv(out_path, index=False, date_format="%Y-%m-%d")
        logger.info("Saved timeseries panel (%d rows) to %s", len(panel), out_path)

        return panel

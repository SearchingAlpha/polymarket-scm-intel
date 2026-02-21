"""
Market discovery: find all supply-chain-relevant Polymarket contracts.

Strategy:
1. Tag-based discovery — identify relevant tag IDs then fetch by tag
2. Keyword filtering — scan titles/descriptions against keyword lists
3. Cover both active AND resolved/closed markets for backtesting
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml

from .client import PolymarketClient

logger = logging.getLogger(__name__)


def _load_mappings() -> Dict:
    path = Path(__file__).parents[2] / "config" / "market_mappings.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _load_settings() -> Dict:
    path = Path(__file__).parents[2] / "config" / "settings.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _title_matches_keywords(title: str, keywords: List[str]) -> bool:
    """Return True if any keyword appears in the title (case-insensitive)."""
    title_lower = title.lower()
    return any(kw.lower() in title_lower for kw in keywords)


def _categorise_market(title: str, mappings: Dict) -> Optional[str]:
    """
    Return the first matching category key for a market title, or None.
    """
    for cat_key, cat_cfg in mappings["categories"].items():
        if _title_matches_keywords(title, cat_cfg.get("keywords", [])):
            return cat_key
    return None


def _find_relevant_tag_ids(tags: List[Dict], mappings: Dict) -> List[int]:
    """
    Scan all available tags and return IDs whose labels match supply-chain
    keywords.
    """
    all_keywords: List[str] = []
    for kw_list in mappings["keywords"].values():
        all_keywords.extend(kw_list)

    relevant_ids: List[int] = []
    for tag in tags:
        label = tag.get("label", "") or tag.get("name", "") or tag.get("slug", "")
        if _title_matches_keywords(label, all_keywords):
            tag_id = tag.get("id")
            if tag_id is not None:
                relevant_ids.append(int(tag_id))
                logger.debug("Relevant tag: %s (id=%s)", label, tag_id)
    return relevant_ids


def _extract_clob_token_ids(market: Dict) -> List[str]:
    """
    Extract clobTokenIds from a market dict.
    They may be stored as a list or as a JSON string.
    """
    raw = market.get("clobTokenIds", [])
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = []
    return [str(t) for t in (raw or [])]


def _parse_volume(market: Dict) -> float:
    """Return market volume as a float, defaulting to 0."""
    for key in ("volume", "volumeNum", "volume24hr", "volume24hrClob"):
        val = market.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return 0.0


def _market_to_record(market: Dict, category: Optional[str], source_tag: Optional[str]) -> Dict:
    """Flatten a raw market dict into a record suitable for a DataFrame."""
    clob_ids = _extract_clob_token_ids(market)

    # Determine if closed/resolved
    is_closed = bool(market.get("closed") or market.get("resolved"))
    status = "closed" if is_closed else "active"

    return {
        "market_id": market.get("id") or market.get("conditionId", ""),
        "event_id": market.get("eventId", ""),
        "title": market.get("question") or market.get("title", ""),
        "category": category,
        "source_tag": source_tag,
        "status": status,
        "clob_token_ids": clob_ids,
        "outcomes": market.get("outcomes", []),
        "outcome_prices": market.get("outcomePrices", ""),
        "volume": _parse_volume(market),
        "created_at": market.get("createdAt", ""),
        "end_date": market.get("endDate", "") or market.get("endDateIso", ""),
        "resolution_source": market.get("resolutionSource", ""),
    }


class MarketDiscovery:
    """
    Discovers supply-chain-relevant Polymarket markets.

    Usage::

        client = PolymarketClient()
        discovery = MarketDiscovery(client)
        df = discovery.run()   # returns DataFrame of discovered markets
    """

    def __init__(self, client: Optional[PolymarketClient] = None) -> None:
        self.client = client or PolymarketClient()
        self.mappings = _load_mappings()
        self.settings = _load_settings()
        self._all_keywords: List[str] = [
            kw for kw_list in self.mappings["keywords"].values() for kw in kw_list
        ]

    def _is_relevant(self, title: str) -> bool:
        return _title_matches_keywords(title, self._all_keywords)

    def discover_via_tags(self) -> List[Dict]:
        """Fetch markets by relevant tag IDs."""
        logger.info("Fetching all tags …")
        tags = self.client.get_tags()
        logger.info("Found %d tags total.", len(tags))

        relevant_ids = _find_relevant_tag_ids(tags, self.mappings)
        logger.info("Found %d supply-chain-relevant tag IDs: %s", len(relevant_ids), relevant_ids)

        records: List[Dict] = []
        for tag_id in relevant_ids:
            for closed in (False, True):
                markets = self.client.get_markets(tag_id=tag_id, closed=closed)
                logger.info(
                    "Tag %d (%s): %d markets",
                    tag_id,
                    "closed" if closed else "active",
                    len(markets),
                )
                for m in markets:
                    title = m.get("question") or m.get("title", "")
                    cat = _categorise_market(title, self.mappings)
                    records.append(_market_to_record(m, cat, f"tag_{tag_id}"))

        return records

    def discover_via_events(self) -> List[Dict]:
        """Fetch all events and filter by keyword match in titles."""
        logger.info("Fetching all events (active) for keyword scan …")
        records: List[Dict] = []

        for closed in (False, True):
            events = self.client.get_events(closed=closed)
            label = "closed" if closed else "active"
            logger.info("Fetched %d %s events.", len(events), label)

            for event in events:
                event_title = event.get("title", "")
                event_relevant = self._is_relevant(event_title)

                nested_markets = event.get("markets", [])
                for m in nested_markets:
                    market_title = m.get("question") or m.get("title", event_title)
                    if event_relevant or self._is_relevant(market_title):
                        cat = _categorise_market(market_title, self.mappings) or _categorise_market(
                            event_title, self.mappings
                        )
                        m.setdefault("eventId", event.get("id", ""))
                        records.append(_market_to_record(m, cat, "event_scan"))

        return records

    def run(self) -> pd.DataFrame:
        """
        Run full discovery pipeline and return a deduplicated DataFrame.

        Columns: market_id, event_id, title, category, source_tag, status,
                 clob_token_ids, outcomes, volume, created_at, end_date
        """
        logger.info("=== Starting market discovery ===")

        records: List[Dict] = []
        records.extend(self.discover_via_tags())
        records.extend(self.discover_via_events())

        df = pd.DataFrame(records)

        if df.empty:
            logger.warning("No markets discovered.")
            return df

        # Deduplicate by market_id, keeping the record with highest volume
        df = df.sort_values("volume", ascending=False)
        df = df.drop_duplicates(subset=["market_id"], keep="first").reset_index(drop=True)

        # Drop markets with no CLOB token IDs (can't fetch price history)
        df = df[df["clob_token_ids"].apply(lambda x: len(x) > 0)].reset_index(drop=True)

        logger.info(
            "=== Discovery complete: %d unique markets (%d active, %d closed) ===",
            len(df),
            (df["status"] == "active").sum(),
            (df["status"] == "closed").sum(),
        )

        # Persist to processed/
        processed_dir = Path(self.settings["data"]["processed_dir"])
        processed_dir.mkdir(parents=True, exist_ok=True)
        out_path = processed_dir / "discovered_markets.csv"

        # clob_token_ids is a list — serialise for CSV
        df_save = df.copy()
        df_save["clob_token_ids"] = df_save["clob_token_ids"].apply(json.dumps)
        df_save["outcomes"] = df_save["outcomes"].apply(
            lambda x: json.dumps(x) if isinstance(x, list) else x
        )
        df_save.to_csv(out_path, index=False)
        logger.info("Saved discovered markets to %s", out_path)

        return df


def load_discovered_markets() -> pd.DataFrame:
    """
    Load previously discovered markets from processed CSV.
    Deserialises list columns back to Python lists.
    """
    settings = _load_settings()
    path = Path(settings["data"]["processed_dir"]) / "discovered_markets.csv"
    if not path.exists():
        raise FileNotFoundError(f"No discovered markets file at {path}. Run MarketDiscovery().run() first.")

    df = pd.read_csv(path)
    for col in ("clob_token_ids", "outcomes"):
        if col in df.columns:
            df[col] = df[col].apply(lambda x: json.loads(x) if pd.notna(x) else [])
    return df

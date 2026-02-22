"""
Freight index data collection.

Attempts programmatic download of BDI and FBX data from public sources.
Falls back gracefully to any CSVs already placed in data/freight/.

Supported indexes: BDI, FBX_GLOBAL, FBX01, FBX03, FBX11
"""

import logging
import time
from io import StringIO
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests
import yaml

logger = logging.getLogger(__name__)

_FREIGHT_DIR: Optional[Path] = None


def _load_settings() -> Dict:
    path = Path(__file__).parents[2] / "config" / "settings.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _load_mappings() -> Dict:
    path = Path(__file__).parents[2] / "config" / "market_mappings.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _freight_dir() -> Path:
    global _FREIGHT_DIR
    if _FREIGHT_DIR is None:
        settings = _load_settings()
        _FREIGHT_DIR = Path(settings["data"]["freight_dir"])
        _FREIGHT_DIR.mkdir(parents=True, exist_ok=True)
    return _FREIGHT_DIR


# ---------------------------------------------------------------------------
# Programmatic download helpers
# ---------------------------------------------------------------------------


def _fetch_with_retry(url: str, params: Optional[Dict] = None, max_retries: int = 3) -> Optional[str]:
    """GET a URL with exponential back-off. Returns response text or None."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml,application/json,*/*;q=0.9",
    }
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            logger.warning("Attempt %d/%d failed for %s: %s", attempt, max_retries, url, exc)
            if attempt < max_retries:
                time.sleep(2**attempt)
    return None


def _try_download_bdi() -> Optional[pd.DataFrame]:
    """
    Attempt to download BDI data from Stooq (free, CSV download endpoint).
    """
    url = "https://stooq.com/q/d/l/?s=bdi&i=d"
    logger.info("Attempting BDI download from Stooq …")
    text = _fetch_with_retry(url)
    if not text:
        return None

    try:
        df = pd.read_csv(StringIO(text))
        # Stooq format: Date, Open, High, Low, Close, Volume
        df.columns = [c.strip().lower() for c in df.columns]
        if "date" not in df.columns:
            return None
        df["date"] = pd.to_datetime(df["date"])
        # Use close price as the BDI value
        value_col = next((c for c in ["close", "last", "value"] if c in df.columns), None)
        if value_col is None:
            return None
        df = df[["date", value_col]].rename(columns={value_col: "value"})
        df = df.dropna().sort_values("date").reset_index(drop=True)
        logger.info("Downloaded %d BDI rows from Stooq.", len(df))
        return df
    except Exception as exc:
        logger.warning("Failed to parse Stooq BDI data: %s", exc)
        return None


def _try_download_bdi_from_trading_economics() -> Optional[pd.DataFrame]:
    """
    Try TradingEconomics API-style endpoint for BDI (may be blocked).
    """
    # TradingEconomics provides embeddable chart JSON for some series
    url = "https://api.tradingeconomics.com/historical/indicator/BDI"
    params = {"c": "guest:guest", "f": "json"}
    logger.info("Attempting BDI download from TradingEconomics …")
    text = _fetch_with_retry(url, params=params)
    if not text:
        return None
    try:
        import json
        data = json.loads(text)
        rows = []
        for item in data:
            date = item.get("DateTime") or item.get("date")
            value = item.get("Value") or item.get("value")
            if date and value is not None:
                rows.append({"date": pd.to_datetime(date), "value": float(value)})
        if not rows:
            return None
        df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
        logger.info("Downloaded %d BDI rows from TradingEconomics.", len(df))
        return df
    except Exception as exc:
        logger.warning("Failed to parse TradingEconomics BDI: %s", exc)
        return None


def _generate_synthetic_bdi() -> pd.DataFrame:
    """
    Generate synthetic BDI data for development when live data is unavailable.

    Simulates realistic BDI behaviour (mean ~1500, high volatility, trending).
    """
    import numpy as np

    logger.warning("Generating SYNTHETIC BDI data for development purposes.")
    np.random.seed(42)

    settings = _load_settings()
    start = pd.Timestamp(settings["analysis"]["study_period"]["start"])
    end = pd.Timestamp(settings["analysis"]["study_period"]["end"])
    dates = pd.bdate_range(start, end)

    # Random walk with mean reversion around 1500
    n = len(dates)
    returns = np.random.normal(0, 0.02, n)  # ~2% daily vol
    levels = [1500.0]
    for r in returns[1:]:
        prev = levels[-1]
        # Mean reversion
        drift = 0.01 * (1500 - prev) / 1500
        levels.append(max(200, prev * (1 + drift + r)))

    df = pd.DataFrame({"date": dates, "value": levels})
    logger.info("Generated %d synthetic BDI observations.", len(df))
    return df


def _generate_synthetic_fbx(index_name: str, base_value: float, volatility: float = 0.025) -> pd.DataFrame:
    """Generate synthetic weekly FBX data for development."""
    import numpy as np

    logger.warning("Generating SYNTHETIC %s data for development purposes.", index_name)
    np.random.seed(hash(index_name) % (2**32))

    settings = _load_settings()
    start = pd.Timestamp(settings["analysis"]["study_period"]["start"])
    end = pd.Timestamp(settings["analysis"]["study_period"]["end"])
    dates = pd.date_range(start, end, freq="W-FRI")

    n = len(dates)
    returns = np.random.normal(0, volatility, n)
    levels = [base_value]
    for r in returns[1:]:
        prev = levels[-1]
        drift = 0.005 * (base_value - prev) / base_value
        levels.append(max(100, prev * (1 + drift + r)))

    df = pd.DataFrame({"date": dates, "value": levels})
    logger.info("Generated %d synthetic %s observations.", len(df), index_name)
    return df


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def _is_wci_format(columns: List[str]) -> bool:
    """Detect Drewry WCI multi-lane format (multiple Shanghai route columns)."""
    return sum(1 for c in columns if "shanghai" in c or "rotterdam" in c or "wci" in c) >= 2


# Maps FBX index names to the substring that identifies the matching WCI column
_WCI_LANE_KEYWORDS: Dict[str, str] = {
    "FBX01": "los angeles",
    "FBX03": "new york",
    "FBX11": "rotterdam",
}


def _parse_wci_df(df: pd.DataFrame, date_col: str, index_name: str) -> pd.DataFrame:
    """
    Given a raw WCI DataFrame with multiple route columns, return a (date, value)
    DataFrame for the requested index.  FBX_GLOBAL gets a simple average of all
    numeric route columns; lane-specific indexes pick the matching column.
    """
    numeric_cols = [c for c in df.columns if c != date_col]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    keyword = _WCI_LANE_KEYWORDS.get(index_name)
    if keyword:
        target = next((c for c in numeric_cols if keyword in c), None)
        if target:
            df = df[[date_col, target]].rename(columns={date_col: "date", target: "value"})
        else:
            logger.warning("WCI column for %s (keyword '%s') not found; using composite.", index_name, keyword)
            df["value"] = df[numeric_cols].mean(axis=1)
            df = df[[date_col, "value"]].rename(columns={date_col: "date"})
    else:
        # FBX_GLOBAL or unknown: composite average
        df["value"] = df[numeric_cols].mean(axis=1)
        df = df[[date_col, "value"]].rename(columns={date_col: "date"})

    df["date"] = pd.to_datetime(df["date"], format="mixed", dayfirst=True)
    df = df.dropna().sort_values("date").reset_index(drop=True)
    return df


def load_from_csv(index_name: str) -> Optional[pd.DataFrame]:
    """
    Load a freight index from a manually placed CSV in data/freight/.

    Handles two formats automatically:
    - Standard 2-column (date, value) — any source
    - Drewry WCI multi-lane format (Date + 4 Shanghai route columns)
    - Investing.com format (BOM, comma-formatted numbers, newest-first)

    Args:
        index_name: Key matching freight_indexes in market_mappings.yaml (e.g. 'BDI').

    Returns:
        Cleaned DataFrame with [date, value] columns, or None if file not found.
    """
    mappings = _load_mappings()
    idx_cfg = mappings["freight_indexes"].get(index_name)
    if idx_cfg is None:
        logger.error("Unknown freight index: %s", index_name)
        return None

    filename = idx_cfg["filename"]
    path = _freight_dir() / filename

    if not path.exists():
        logger.warning("Freight CSV not found: %s", path)
        return None

    try:
        # utf-8-sig strips the BOM that investing.com adds to exported CSVs
        df = pd.read_csv(path, encoding="utf-8-sig")
        df.columns = [c.strip().lower() for c in df.columns]

        date_col = next((c for c in df.columns if "date" in c or "time" in c), None)

        # --- Drewry WCI multi-lane format ---
        if _is_wci_format(df.columns) and date_col:
            result = _parse_wci_df(df, date_col, index_name)
            logger.info("Loaded %d WCI rows for %s from %s", len(result), index_name, path)
            return result

        # --- Standard / investing.com single-value format ---
        value_col = next(
            (c for c in df.columns if c in ("value", "close", "price", "bdi", "fbx", "index")),
            None,
        )
        if date_col is None or value_col is None:
            # Last resort: assume first col is date, second is value
            cols = list(df.columns)
            if len(cols) >= 2:
                date_col, value_col = cols[0], cols[1]
            else:
                raise ValueError(f"Cannot identify date/value columns in {filename}: {list(df.columns)}")

        df = df[[date_col, value_col]].rename(columns={date_col: "date", value_col: "value"})
        df["date"] = pd.to_datetime(df["date"])
        # Strip thousands-separator commas (investing.com exports "2,043.00")
        df["value"] = pd.to_numeric(
            df["value"].astype(str).str.replace(",", "", regex=False),
            errors="coerce",
        )
        df = df.dropna().sort_values("date").reset_index(drop=True)
        logger.info("Loaded %d rows from %s", len(df), path)
        return df
    except Exception as exc:
        logger.error("Failed to load %s: %s", path, exc)
        return None


def fetch_bdi(use_synthetic_fallback: bool = True) -> Optional[pd.DataFrame]:
    """
    Fetch Baltic Dry Index data.

    Tries:
    1. Manual CSV in data/freight/bdi.csv
    2. Stooq programmatic download
    3. TradingEconomics API
    4. Synthetic fallback (if use_synthetic_fallback=True)

    Returns:
        DataFrame with [date, value] columns, or None.
    """
    # 1. Manual CSV
    df = load_from_csv("BDI")
    if df is not None:
        return df

    # 2. Stooq
    df = _try_download_bdi()
    if df is not None:
        out = _freight_dir() / "bdi.csv"
        df.to_csv(out, index=False)
        logger.info("Saved BDI data to %s", out)
        return df

    # 3. TradingEconomics
    df = _try_download_bdi_from_trading_economics()
    if df is not None:
        out = _freight_dir() / "bdi.csv"
        df.to_csv(out, index=False)
        return df

    # 4. Synthetic fallback
    if use_synthetic_fallback:
        df = _generate_synthetic_bdi()
        out = _freight_dir() / "bdi_synthetic.csv"
        df.to_csv(out, index=False)
        return df

    return None


def _try_extract_wci_lane(index_name: str) -> Optional[pd.DataFrame]:
    """
    Extract a lane-specific series from the WCI multi-column file (fbx_global.csv).

    Used as a fallback when fbx01.csv / fbx03.csv / fbx11.csv are not present but
    the user has provided the Drewry WCI multi-lane export as fbx_global.csv.
    """
    if index_name not in _WCI_LANE_KEYWORDS:
        return None

    path = _freight_dir() / "fbx_global.csv"
    if not path.exists():
        return None

    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
        df.columns = [c.strip().lower() for c in df.columns]
        date_col = next((c for c in df.columns if "date" in c or "time" in c), None)
        if date_col is None or not _is_wci_format(df.columns):
            return None

        result = _parse_wci_df(df, date_col, index_name)
        if result.empty:
            return None
        logger.info(
            "Extracted %s (%d rows) from WCI multi-lane file (fbx_global.csv).",
            index_name, len(result),
        )
        return result
    except Exception as exc:
        logger.warning("Failed to extract WCI lane %s: %s", index_name, exc)
        return None


def fetch_fbx(
    index_name: str = "FBX_GLOBAL",
    use_synthetic_fallback: bool = True,
) -> Optional[pd.DataFrame]:
    """
    Fetch a Freightos Baltic Index (FBX) / WCI series.

    Tries:
    1. Manual CSV in data/freight/<filename>
    2. WCI lane extraction from fbx_global.csv (for FBX01, FBX03, FBX11)
    3. Synthetic fallback

    Args:
        index_name: One of 'FBX_GLOBAL', 'FBX01', 'FBX03', 'FBX11'.
        use_synthetic_fallback: Generate synthetic data if real data unavailable.

    Returns:
        DataFrame with [date, value] columns, or None.
    """
    df = load_from_csv(index_name)
    if df is not None:
        return df

    # Extract lane data from WCI multi-column file if available
    df = _try_extract_wci_lane(index_name)
    if df is not None:
        return df

    if use_synthetic_fallback:
        base_values = {
            "FBX_GLOBAL": 2800.0,
            "FBX01": 3200.0,
            "FBX03": 4500.0,
            "FBX11": 2600.0,
        }
        base = base_values.get(index_name, 2500.0)
        df = _generate_synthetic_fbx(index_name, base)
        out = _freight_dir() / f"{index_name.lower()}_synthetic.csv"
        df.to_csv(out, index=False)
        return df

    return None


def fetch_all_freight_indexes(use_synthetic_fallback: bool = True) -> Dict[str, pd.DataFrame]:
    """
    Fetch all configured freight indexes.

    Returns:
        Dict mapping index_name → DataFrame(date, value).
    """
    mappings = _load_mappings()
    indexes = list(mappings["freight_indexes"].keys())
    result: Dict[str, pd.DataFrame] = {}

    for name in indexes:
        logger.info("Fetching freight index: %s", name)
        if name == "BDI":
            df = fetch_bdi(use_synthetic_fallback=use_synthetic_fallback)
        else:
            df = fetch_fbx(name, use_synthetic_fallback=use_synthetic_fallback)

        if df is not None:
            result[name] = df
            logger.info("  → %d observations for %s", len(df), name)
        else:
            logger.warning("  → No data available for %s", name)

    return result


def print_download_instructions() -> None:
    """Print manual download instructions for all freight indexes."""
    mappings = _load_mappings()
    freight_dir = _freight_dir()

    print("\n" + "=" * 70)
    print("FREIGHT DATA MANUAL DOWNLOAD INSTRUCTIONS")
    print("=" * 70)
    print(f"\nPlace CSV files in: {freight_dir.resolve()}\n")

    for name, cfg in mappings["freight_indexes"].items():
        print(f"\n{'─' * 50}")
        print(f"Index: {cfg['name']} ({name})")
        print(f"Filename: {cfg['filename']}")
        print(f"Source: {cfg['source']}")
        print(f"URL: {cfg.get('manual_download_url', 'N/A')}")
        print(f"Expected columns: {cfg.get('expected_columns', ['date', 'value'])}")
        print(f"Frequency: {cfg.get('frequency', 'unknown')}")

    print("\n" + "=" * 70 + "\n")

"""
Freight data normalisation and alignment.

Aligns freight indexes to daily frequency (forward-filling weekly FBX data),
normalises to z-scores and percentage changes, and aligns date indexes for
cross-correlation with Polymarket timeseries.
"""

import logging
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)


def _load_settings() -> Dict:
    path = Path(__file__).parents[2] / "config" / "settings.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def to_daily(df: pd.DataFrame, method: str = "ffill") -> pd.DataFrame:
    """
    Upsample a freight DataFrame to daily frequency.

    Args:
        df: DataFrame with [date, value] columns. date may be datetime or date objects.
        method: Fill method for missing days — 'ffill' (forward fill) or 'linear'.

    Returns:
        Daily DataFrame with [date, value], date as datetime64.
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()

    # Reindex to full daily range
    full_range = pd.date_range(df.index.min(), df.index.max(), freq="D")
    df = df.reindex(full_range)

    if method == "ffill":
        df["value"] = df["value"].ffill()
    elif method == "linear":
        df["value"] = df["value"].interpolate(method="linear")
    else:
        raise ValueError(f"Unknown fill method: {method!r}. Use 'ffill' or 'linear'.")

    df = df.reset_index().rename(columns={"index": "date"})
    return df


def compute_pct_change(df: pd.DataFrame, periods: int = 1) -> pd.DataFrame:
    """
    Add a 'pct_change' column: percentage change over `periods` days.

    Args:
        df: DataFrame with [date, value].
        periods: Number of periods for pct change calculation.

    Returns:
        DataFrame with additional 'pct_change' column.
    """
    df = df.copy()
    df["pct_change"] = df["value"].pct_change(periods=periods) * 100
    return df


def compute_zscore(df: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """
    Add a 'zscore' column: rolling z-score of the value series.

    Args:
        df: DataFrame with [date, value].
        window: Rolling window size in days.

    Returns:
        DataFrame with additional 'zscore' column.
    """
    df = df.copy()
    roll_mean = df["value"].rolling(window, min_periods=10).mean()
    roll_std = df["value"].rolling(window, min_periods=10).std()
    df["zscore"] = (df["value"] - roll_mean) / roll_std.replace(0, np.nan)
    return df


def normalise_to_baseline(df: pd.DataFrame, baseline_start: str, baseline_end: str) -> pd.DataFrame:
    """
    Normalise the 'value' column to percentage change from a baseline period mean.

    Args:
        df: DataFrame with [date, value].
        baseline_start: ISO date string for start of baseline period.
        baseline_end: ISO date string for end of baseline period.

    Returns:
        DataFrame with additional 'normalised' column (0 = baseline mean).
    """
    df = df.copy()
    mask = (df["date"] >= pd.Timestamp(baseline_start)) & (df["date"] <= pd.Timestamp(baseline_end))
    baseline_mean = df.loc[mask, "value"].mean()
    if pd.isna(baseline_mean) or baseline_mean == 0:
        logger.warning("Cannot normalise to baseline — mean is NaN or zero.")
        df["normalised"] = np.nan
    else:
        df["normalised"] = (df["value"] / baseline_mean - 1) * 100
    return df


def align_to_polymarket(
    freight_df: pd.DataFrame,
    polymarket_df: pd.DataFrame,
    freight_value_col: str = "value",
) -> pd.DataFrame:
    """
    Align a freight index DataFrame to the date range and index of a
    Polymarket timeseries DataFrame.

    Args:
        freight_df: Daily freight DataFrame with [date, value, …].
        polymarket_df: Polymarket DataFrame with [date, probability, …].
        freight_value_col: Column in freight_df to align.

    Returns:
        Merged DataFrame with [date, probability, freight_value] columns,
        covering only the intersection of the two date ranges.
    """
    freight = freight_df[["date", freight_value_col]].copy()
    freight["date"] = pd.to_datetime(freight["date"])

    poly = polymarket_df[["date", "probability"]].copy()
    poly["date"] = pd.to_datetime(poly["date"])

    merged = pd.merge(poly, freight, on="date", how="inner")
    merged = merged.rename(columns={freight_value_col: "freight_value"})
    merged = merged.sort_values("date").reset_index(drop=True)

    logger.debug(
        "Aligned %d overlapping data points (poly: %d, freight: %d).",
        len(merged),
        len(poly),
        len(freight),
    )
    return merged


def prepare_freight_panel(
    freight_dict: Dict[str, pd.DataFrame],
    settings: Optional[Dict] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Run full normalisation pipeline on all freight indexes.

    For each index:
    - Upsample to daily (forward fill)
    - Apply date range filter from settings
    - Compute pct_change and z-score
    - Add 'normalised' column relative to 2024 baseline

    Args:
        freight_dict: Raw dict of {index_name: DataFrame(date, value)}.
        settings: Settings dict (loads from YAML if None).

    Returns:
        Dict of {index_name: normalised daily DataFrame}.
    """
    if settings is None:
        settings = _load_settings()

    start = settings["analysis"]["study_period"]["start"]
    end = settings["analysis"]["study_period"]["end"]

    result: Dict[str, pd.DataFrame] = {}
    for name, df in freight_dict.items():
        logger.info("Normalising freight index: %s", name)

        # Upsample to daily
        daily = to_daily(df, method="ffill")

        # Date range filter
        daily["date"] = pd.to_datetime(daily["date"])
        daily = daily[(daily["date"] >= start) & (daily["date"] <= end)].reset_index(drop=True)

        if daily.empty:
            logger.warning("No data in study period for %s.", name)
            continue

        # Derived columns
        daily = compute_pct_change(daily)
        daily = compute_zscore(daily)
        daily = normalise_to_baseline(daily, start, str(pd.Timestamp(start) + pd.Timedelta(days=90)))

        result[name] = daily
        logger.info(
            "  %s: %d daily observations from %s to %s",
            name,
            len(daily),
            daily["date"].min().date(),
            daily["date"].max().date(),
        )

    # Persist processed freight data
    processed_dir = Path(settings["data"]["processed_dir"])
    processed_dir.mkdir(parents=True, exist_ok=True)
    for name, df in result.items():
        out = processed_dir / f"freight_{name.lower()}.csv"
        df.to_csv(out, index=False)
        logger.debug("Saved processed %s to %s", name, out)

    return result

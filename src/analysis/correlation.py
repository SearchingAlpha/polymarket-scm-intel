"""
Cross-correlation and Granger causality analysis between Polymarket probability
timeseries and freight index timeseries.

Core analytical module — tests whether prediction market signals lead freight
rate changes (the central thesis of this project).
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml
from scipy import stats

logger = logging.getLogger(__name__)


def _load_settings() -> Dict:
    path = Path(__file__).parents[2] / "config" / "settings.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CrossCorrelationResult:
    """Results from cross-correlation analysis at multiple lags."""

    market_id: str
    market_title: str
    freight_index: str
    lags: List[int]
    correlations: List[float]
    p_values: List[float]
    peak_lag: int              # Lag (days) at maximum absolute correlation
    peak_correlation: float
    peak_p_value: float
    n_observations: int
    interpretation: str = ""   # Natural language summary

    def is_significant(self, alpha: float = 0.05) -> bool:
        return self.peak_p_value < alpha

    def polymarket_leads(self) -> bool:
        """True if the peak correlation is at a positive lag (freight follows poly)."""
        return self.peak_lag > 0


@dataclass
class GrangerResult:
    """Results from Granger causality test."""

    market_id: str
    market_title: str
    freight_index: str
    direction: str           # 'poly_causes_freight' or 'freight_causes_poly'
    min_p_value: float       # Minimum p-value across tested lags
    best_lag: int
    test_statistic: float
    n_observations: int
    is_significant: bool
    details: Dict = field(default_factory=dict)


@dataclass
class EventStudyResult:
    """Average freight index behaviour around significant probability shift events."""

    market_id: str
    market_title: str
    freight_index: str
    n_events: int
    event_window: List[int]              # Days relative to event (e.g., -5 to +30)
    mean_freight_change: List[float]     # Mean pct change at each lag
    ci_lower: List[float]                # 95% confidence interval lower bound
    ci_upper: List[float]                # 95% confidence interval upper bound
    baseline_change: float               # Average freight change in non-event periods
    cumulative_abnormal_return: float    # CAR over the post-event window


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _align_series(
    poly_df: pd.DataFrame,
    freight_df: pd.DataFrame,
) -> Optional[pd.DataFrame]:
    """
    Merge Polymarket and freight DataFrames on date, returning aligned panel.

    Args:
        poly_df: DataFrame with [date, probability] columns.
        freight_df: DataFrame with [date, value] columns.

    Returns:
        Merged DataFrame with [date, probability, freight_value], or None if
        fewer than 30 overlapping observations.
    """
    poly = poly_df[["date", "probability"]].copy()
    poly["date"] = pd.to_datetime(poly["date"])

    freight = freight_df[["date", "value"]].copy()
    freight["date"] = pd.to_datetime(freight["date"])

    merged = pd.merge(poly, freight, on="date", how="inner")
    merged = merged.rename(columns={"value": "freight_value"})
    merged = merged.sort_values("date").reset_index(drop=True)
    merged = merged.dropna()

    if len(merged) < 30:
        logger.debug("Insufficient overlap (%d < 30 obs) — skipping pair.", len(merged))
        return None

    return merged


def _pearson_with_pvalue(x: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    """Compute Pearson r and two-tailed p-value, handling edge cases."""
    if len(x) < 5 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan"), float("nan")
    r, p = stats.pearsonr(x, y)
    return float(r), float(p)


# ---------------------------------------------------------------------------
# Cross-correlation
# ---------------------------------------------------------------------------


def compute_cross_correlation(
    market_id: str,
    market_title: str,
    poly_df: pd.DataFrame,
    freight_df: pd.DataFrame,
    freight_index_name: str,
    lag_range: int = 30,
    settings: Optional[Dict] = None,
) -> Optional[CrossCorrelationResult]:
    """
    Compute Pearson cross-correlation between daily Polymarket probability changes
    and freight index changes at multiple lags.

    A positive lag means freight changes after the prediction market moves —
    this is the "leading indicator" signature we are looking for.

    Args:
        market_id: Polymarket market identifier.
        market_title: Human-readable title.
        poly_df: Daily probability DataFrame [date, probability].
        freight_df: Daily freight DataFrame [date, value].
        freight_index_name: Name of freight index (e.g. 'FBX01').
        lag_range: Test lags from -lag_range to +lag_range.
        settings: Settings dict (loads from YAML if None).

    Returns:
        CrossCorrelationResult, or None if insufficient data.
    """
    if settings is None:
        settings = _load_settings()

    merged = _align_series(poly_df, freight_df)
    if merged is None:
        return None

    # Use changes rather than levels for stationarity
    merged["d_prob"] = merged["probability"].diff()
    merged["d_freight"] = merged["freight_value"].pct_change() * 100
    merged = merged.dropna()

    if len(merged) < settings["analysis"]["correlation"]["min_observations"]:
        logger.debug("Too few observations for %s × %s after differencing.", market_id, freight_index_name)
        return None

    poly_changes = merged["d_prob"].values
    freight_changes = merged["d_freight"].values

    lags = list(range(-lag_range, lag_range + 1))
    correlations: List[float] = []
    p_values: List[float] = []

    for lag in lags:
        if lag > 0:
            # freight changes lag behind poly changes
            x = poly_changes[: len(poly_changes) - lag]
            y = freight_changes[lag:]
        elif lag < 0:
            # poly changes lag behind freight changes
            x = poly_changes[-lag:]
            y = freight_changes[: len(freight_changes) + lag]
        else:
            x, y = poly_changes, freight_changes

        if len(x) < 10:
            correlations.append(float("nan"))
            p_values.append(float("nan"))
            continue

        r, p = _pearson_with_pvalue(x, y)
        correlations.append(r)
        p_values.append(p)

    # Find peak correlation (by absolute value)
    valid_idx = [i for i, c in enumerate(correlations) if not np.isnan(c)]
    if not valid_idx:
        return None

    peak_idx = max(valid_idx, key=lambda i: abs(correlations[i]))
    peak_lag = lags[peak_idx]
    peak_corr = correlations[peak_idx]
    peak_p = p_values[peak_idx]

    # Natural language interpretation
    direction = "higher" if peak_corr > 0 else "lower"
    lead_label = (
        f"Polymarket signals LEAD freight by {peak_lag} days"
        if peak_lag > 0
        else f"freight LEADS Polymarket by {abs(peak_lag)} days"
        if peak_lag < 0
        else "contemporaneous"
    )
    sig_label = f"(p={peak_p:.3f}, {'significant' if peak_p < 0.05 else 'not significant'})"
    interpretation = (
        f"Peak correlation r={peak_corr:.3f} at lag={peak_lag}: "
        f"{lead_label}. Higher prediction market probability → {direction} {freight_index_name} rates. "
        f"{sig_label}"
    )

    return CrossCorrelationResult(
        market_id=market_id,
        market_title=market_title,
        freight_index=freight_index_name,
        lags=lags,
        correlations=correlations,
        p_values=p_values,
        peak_lag=peak_lag,
        peak_correlation=peak_corr,
        peak_p_value=peak_p,
        n_observations=len(merged),
        interpretation=interpretation,
    )


# ---------------------------------------------------------------------------
# Granger causality
# ---------------------------------------------------------------------------


def run_granger_test(
    market_id: str,
    market_title: str,
    poly_df: pd.DataFrame,
    freight_df: pd.DataFrame,
    freight_index_name: str,
    max_lag: int = 14,
    settings: Optional[Dict] = None,
) -> Optional[GrangerResult]:
    """
    Test whether Polymarket probability changes Granger-cause freight index changes.

    Tests both directions: poly → freight and freight → poly.

    Args:
        market_id: Polymarket market identifier.
        market_title: Human-readable title.
        poly_df: Daily probability DataFrame [date, probability].
        freight_df: Daily freight DataFrame [date, value].
        freight_index_name: Name of freight index.
        max_lag: Maximum lag order to test.
        settings: Settings dict.

    Returns:
        GrangerResult for the poly → freight direction, or None on failure.
    """
    try:
        from statsmodels.tsa.stattools import grangercausalitytests
    except ImportError:
        logger.error("statsmodels not installed — cannot run Granger test.")
        return None

    if settings is None:
        settings = _load_settings()

    merged = _align_series(poly_df, freight_df)
    if merged is None:
        return None

    merged["d_prob"] = merged["probability"].diff()
    merged["d_freight"] = merged["freight_value"].pct_change() * 100
    merged = merged.dropna()

    min_obs = settings["analysis"]["correlation"]["min_observations"]
    if len(merged) < min_obs + max_lag:
        logger.debug("Insufficient data for Granger test: %d obs.", len(merged))
        return None

    # Test poly → freight (does poly probability improve freight forecast?)
    data = merged[["d_freight", "d_prob"]].dropna().values

    try:
        results = grangercausalitytests(data, maxlag=max_lag, verbose=False)
    except Exception as exc:
        logger.warning("Granger test failed for %s × %s: %s", market_id, freight_index_name, exc)
        return None

    # Extract minimum p-value and its lag
    p_values_by_lag: Dict[int, float] = {}
    f_stats_by_lag: Dict[int, float] = {}
    for lag, lag_results in results.items():
        # lag_results[0] is dict of test results; we use F-test
        f_test = lag_results[0].get("ssr_ftest")
        if f_test is not None:
            p_values_by_lag[lag] = float(f_test[1])
            f_stats_by_lag[lag] = float(f_test[0])

    if not p_values_by_lag:
        return None

    best_lag = min(p_values_by_lag, key=p_values_by_lag.get)
    min_p = p_values_by_lag[best_lag]
    best_f = f_stats_by_lag[best_lag]

    return GrangerResult(
        market_id=market_id,
        market_title=market_title,
        freight_index=freight_index_name,
        direction="poly_causes_freight",
        min_p_value=min_p,
        best_lag=best_lag,
        test_statistic=best_f,
        n_observations=len(merged),
        is_significant=min_p < 0.05,
        details={lag: {"p": p, "f": f_stats_by_lag[lag]} for lag, p in p_values_by_lag.items()},
    )


# ---------------------------------------------------------------------------
# Event study
# ---------------------------------------------------------------------------


def event_study(
    market_id: str,
    market_title: str,
    event_timestamps: List[pd.Timestamp],
    freight_df: pd.DataFrame,
    freight_index_name: str,
    pre_window: int = 5,
    post_window: int = 30,
) -> Optional[EventStudyResult]:
    """
    Compute average freight index behaviour around probability shift events.

    For each event at time t:
    - Extract freight pct_change in window [t - pre_window, t + post_window]
    - Average across all events
    - Compare to baseline (non-event) average

    Args:
        market_id: Polymarket market identifier.
        market_title: Human-readable title.
        event_timestamps: List of event timestamps.
        freight_df: Daily freight DataFrame [date, value].
        freight_index_name: Name of freight index.
        pre_window: Days before event to include.
        post_window: Days after event to include.

    Returns:
        EventStudyResult, or None if fewer than 2 events.
    """
    if len(event_timestamps) < 2:
        logger.debug("Need ≥2 events for event study — only %d available.", len(event_timestamps))
        return None

    freight = freight_df[["date", "value"]].copy()
    freight["date"] = pd.to_datetime(freight["date"])
    freight = freight.sort_values("date").set_index("date")

    # Compute pct_change relative to start of each event window
    window_range = list(range(-pre_window, post_window + 1))
    event_traces: List[List[float]] = []

    for ts in event_timestamps:
        ts = pd.Timestamp(ts)
        window_dates = [ts + pd.Timedelta(days=d) for d in window_range]
        trace = []
        anchor_price: Optional[float] = None

        for d, wd in zip(window_range, window_dates):
            # Find nearest available freight date within ±2 days
            nearest = freight.index[np.abs((freight.index - wd).days)]
            if len(nearest) == 0:
                trace.append(float("nan"))
                continue
            closest = min(freight.index, key=lambda x: abs((x - wd).days))
            if abs((closest - wd).days) > 3:
                trace.append(float("nan"))
                continue

            val = float(freight.loc[closest, "value"])

            if d == 0:
                anchor_price = val

            if anchor_price is None or anchor_price == 0:
                trace.append(float("nan"))
            else:
                trace.append((val / anchor_price - 1) * 100)

        if len([v for v in trace if not np.isnan(v)]) >= post_window // 2:
            event_traces.append(trace)

    if len(event_traces) < 2:
        return None

    # Compute statistics across event traces
    arr = np.array(event_traces, dtype=float)
    mean_change = np.nanmean(arr, axis=0).tolist()
    se = np.nanstd(arr, axis=0) / np.sqrt(np.sum(~np.isnan(arr), axis=0))
    ci_lower = (np.nanmean(arr, axis=0) - 1.96 * se).tolist()
    ci_upper = (np.nanmean(arr, axis=0) + 1.96 * se).tolist()

    # Cumulative abnormal return (post-event mean change)
    post_idx = window_range.index(0)
    car = float(np.nanmean(arr[:, post_idx:], axis=None))

    # Baseline: average freight pct_change in non-event periods
    freight_pct = freight["value"].pct_change().dropna() * 100
    baseline_change = float(freight_pct.mean()) if not freight_pct.empty else 0.0

    return EventStudyResult(
        market_id=market_id,
        market_title=market_title,
        freight_index=freight_index_name,
        n_events=len(event_traces),
        event_window=window_range,
        mean_freight_change=mean_change,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        baseline_change=baseline_change,
        cumulative_abnormal_return=car,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


class CorrelationAnalyser:
    """
    Runs cross-correlation, Granger causality, and event study analyses for
    all configured Polymarket–freight pairings.

    Usage::

        analyser = CorrelationAnalyser()
        xcorr_results = analyser.run_cross_correlations(timeseries, freight_data, markets_df)
        granger_results = analyser.run_granger_tests(timeseries, freight_data, markets_df)
    """

    def __init__(self, settings: Optional[Dict] = None) -> None:
        self.settings = settings or _load_settings()
        self.lag_range = self.settings["analysis"]["correlation"]["lag_range_days"]
        self.max_granger_lag = self.settings["analysis"]["correlation"]["granger_max_lag"]

    def _get_pairings(
        self,
        markets_df: pd.DataFrame,
        freight_data: Dict[str, pd.DataFrame],
    ) -> List[Tuple[str, str, str, List[str]]]:
        """
        Build (market_id, market_title, freight_index, clob_ids) tuples based on
        category mappings in market_mappings.yaml.
        """
        import yaml as _yaml

        mappings_path = Path(__file__).parents[2] / "config" / "market_mappings.yaml"
        with open(mappings_path) as f:
            mappings = _yaml.safe_load(f)

        pairings = []
        for _, row in markets_df.iterrows():
            cat = row.get("category")
            if not cat or cat not in mappings.get("categories", {}):
                continue

            cat_cfg = mappings["categories"][cat]
            for fi in cat_cfg.get("freight_indicators", []):
                fi_name = fi["name"]
                if fi_name in freight_data:
                    pairings.append((
                        str(row["market_id"]),
                        str(row["title"]),
                        fi_name,
                        row.get("clob_token_ids", []),
                    ))

        return pairings

    def run_cross_correlations(
        self,
        timeseries: Dict[str, pd.DataFrame],
        freight_data: Dict[str, pd.DataFrame],
        markets_df: pd.DataFrame,
    ) -> List[CrossCorrelationResult]:
        """Run cross-correlation for all market–freight pairings."""
        pairings = self._get_pairings(markets_df, freight_data)
        logger.info("Running cross-correlation for %d pairings …", len(pairings))

        results = []
        for market_id, title, fi_name, _ in pairings:
            poly_df = timeseries.get(market_id)
            freight_df = freight_data.get(fi_name)
            if poly_df is None or freight_df is None:
                continue

            result = compute_cross_correlation(
                market_id, title, poly_df, freight_df, fi_name,
                lag_range=self.lag_range, settings=self.settings,
            )
            if result is not None:
                results.append(result)
                logger.info(
                    "  %s × %s: peak r=%.3f at lag=%d %s",
                    market_id[:12], fi_name, result.peak_correlation,
                    result.peak_lag,
                    "(significant)" if result.is_significant() else "",
                )

        return results

    def run_granger_tests(
        self,
        timeseries: Dict[str, pd.DataFrame],
        freight_data: Dict[str, pd.DataFrame],
        markets_df: pd.DataFrame,
    ) -> List[GrangerResult]:
        """Run Granger causality tests for all pairings."""
        pairings = self._get_pairings(markets_df, freight_data)
        logger.info("Running Granger tests for %d pairings …", len(pairings))

        results = []
        for market_id, title, fi_name, _ in pairings:
            poly_df = timeseries.get(market_id)
            freight_df = freight_data.get(fi_name)
            if poly_df is None or freight_df is None:
                continue

            result = run_granger_test(
                market_id, title, poly_df, freight_df, fi_name,
                max_lag=self.max_granger_lag, settings=self.settings,
            )
            if result is not None:
                results.append(result)
                logger.info(
                    "  %s → %s: p=%.4f (lag=%d) %s",
                    market_id[:12], fi_name,
                    result.min_p_value, result.best_lag,
                    "*** SIGNIFICANT ***" if result.is_significant else "",
                )

        return results

    def xcorr_to_dataframe(self, results: List[CrossCorrelationResult]) -> pd.DataFrame:
        """Summarise cross-correlation results as a DataFrame."""
        rows = [
            {
                "market_id": r.market_id,
                "market_title": r.market_title,
                "freight_index": r.freight_index,
                "peak_lag_days": r.peak_lag,
                "peak_correlation": r.peak_correlation,
                "peak_p_value": r.peak_p_value,
                "is_significant": r.is_significant(),
                "polymarket_leads": r.polymarket_leads(),
                "n_observations": r.n_observations,
                "interpretation": r.interpretation,
            }
            for r in results
        ]
        return pd.DataFrame(rows)

    def granger_to_dataframe(self, results: List[GrangerResult]) -> pd.DataFrame:
        """Summarise Granger results as a DataFrame."""
        rows = [
            {
                "market_id": r.market_id,
                "market_title": r.market_title,
                "freight_index": r.freight_index,
                "direction": r.direction,
                "best_lag": r.best_lag,
                "min_p_value": r.min_p_value,
                "f_statistic": r.test_statistic,
                "is_significant": r.is_significant,
                "n_observations": r.n_observations,
            }
            for r in results
        ]
        return pd.DataFrame(rows)

"""
Signal validation: evaluate whether Polymarket probability shifts reliably
predict freight rate changes.

Three metrics are computed for each market-freight pairing:

1. Directional Accuracy / Precision
   Of all signals that fired, what % were followed by freight moving in the
   expected direction within the outcome window?

2. Coverage / Recall
   Of all significant freight rate moves, what % were preceded by a
   Polymarket signal within the lookback window?

3. Lead Time Distribution
   For true-positive signals, how many days elapsed between the signal and
   the subsequent freight move?

A confusion matrix per pairing:
  TP — signal fired → freight moved in expected direction within outcome_window
  FP — signal fired → no matching freight move within outcome_window
  FN — freight moved → no preceding signal within lookback_window
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from .events import ProbabilityEvent
from .correlation import CrossCorrelationResult

matplotlib.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})

BLUE = "#1f6aa5"
ORANGE = "#e07b39"
GREEN = "#2ca02c"
RED = "#d62728"
GRAY = "#888888"

logger = logging.getLogger(__name__)


def _load_settings() -> Dict:
    path = Path(__file__).parents[2] / "config" / "settings.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _save_figure(fig: plt.Figure, filename_stem: str, settings: Optional[Dict] = None) -> List[Path]:
    """Save a figure as PNG and SVG in the configured output directory."""
    if settings is None:
        settings = _load_settings()
    figures_dir = Path(settings["output"]["figures_dir"])
    figures_dir.mkdir(parents=True, exist_ok=True)
    dpi = settings["output"].get("figure_dpi", 300)
    formats = settings["output"].get("figure_formats", ["png", "svg"])
    paths = []
    for fmt in formats:
        p = figures_dir / f"{filename_stem}.{fmt}"
        fig.savefig(p, dpi=dpi if fmt == "png" else None, bbox_inches="tight")
        paths.append(p)
        logger.info("Saved: %s", p)
    return paths


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class FreightEvent:
    """A detected significant freight rate move."""

    freight_index: str
    timestamp: pd.Timestamp
    value_before: float
    value_after: float
    pct_change: float    # signed % change (e.g. +12.5 means +12.5%)
    direction: str       # 'up' or 'down'
    magnitude: float     # absolute pct_change


@dataclass
class SignalOutcome:
    """Classification of a single Polymarket signal against freight outcomes."""

    market_id: str
    market_title: str
    freight_index: str
    signal_timestamp: pd.Timestamp
    signal_delta: float                   # probability change (signed)
    signal_direction: str                 # 'up' or 'down'
    expected_freight_direction: str       # 'up', 'down', or 'unknown'
    outcome: str                          # 'TP', 'FP', 'FN'
    lead_time_days: Optional[int]         # days from signal to freight event (TP only)
    freight_pct_change: Optional[float]   # actual freight % change in outcome window
    direction_correct: Optional[bool]
    matched_freight_event: Optional[FreightEvent] = None


@dataclass
class PairingValidation:
    """All validation results for one market-freight pairing."""

    market_id: str
    market_title: str
    freight_index: str
    peak_correlation: float
    peak_lag_days: int
    n_signals: int
    n_freight_events: int
    n_tp: int
    n_fp: int
    n_fn: int
    precision: float        # TP / (TP + FP)
    recall: float           # TP / (TP + FN)
    f1: float
    lead_times: List[int]   # days for all TPs
    outcomes: List[SignalOutcome] = field(default_factory=list)

    @property
    def median_lead_time(self) -> Optional[float]:
        return float(np.median(self.lead_times)) if self.lead_times else None

    @property
    def mean_lead_time(self) -> Optional[float]:
        return float(np.mean(self.lead_times)) if self.lead_times else None


# ---------------------------------------------------------------------------
# Freight event detection
# ---------------------------------------------------------------------------


def detect_freight_events(
    freight_df: pd.DataFrame,
    freight_index_name: str,
    threshold_pct: float = 0.08,
    window: int = 14,
) -> List[FreightEvent]:
    """
    Detect significant freight rate moves using a rolling window threshold.

    A freight event is triggered when the index changes by more than
    `threshold_pct` (e.g. 0.08 = 8%) over `window` days.  Events are
    deduplicated so that only the largest move per window is kept.

    Args:
        freight_df: DataFrame with [date, value] columns.
        freight_index_name: Label for the freight index (e.g. 'BDI').
        threshold_pct: Minimum absolute fractional change to flag.
        window: Rolling window in days.

    Returns:
        List of FreightEvent objects, sorted by timestamp.
    """
    df = freight_df[["date", "value"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True).dropna(subset=["value"])

    events: List[FreightEvent] = []
    values = df["value"].values
    dates = df["date"].values

    for i in range(window, len(df)):
        val_start = values[i - window]
        val_end = values[i]
        if val_start == 0 or np.isnan(val_start) or np.isnan(val_end):
            continue
        pct = (val_end - val_start) / abs(val_start)
        if abs(pct) >= threshold_pct:
            direction = "up" if pct > 0 else "down"
            events.append(FreightEvent(
                freight_index=freight_index_name,
                timestamp=pd.Timestamp(dates[i]),
                value_before=float(val_start),
                value_after=float(val_end),
                pct_change=float(pct * 100),
                direction=direction,
                magnitude=abs(pct * 100),
            ))

    return _deduplicate_freight_events(events, cooldown_days=window)


def _deduplicate_freight_events(
    events: List[FreightEvent],
    cooldown_days: int,
) -> List[FreightEvent]:
    """Keep the largest freight event per cooldown_days cluster."""
    if not events:
        return events
    events = sorted(events, key=lambda e: e.timestamp)
    kept: List[FreightEvent] = []
    last_ts: Optional[pd.Timestamp] = None
    for ev in events:
        if last_ts is None or (ev.timestamp - last_ts).days >= cooldown_days:
            kept.append(ev)
            last_ts = ev.timestamp
        elif ev.magnitude > kept[-1].magnitude:
            kept[-1] = ev
            last_ts = ev.timestamp
    return kept


# ---------------------------------------------------------------------------
# Signal validator
# ---------------------------------------------------------------------------


class SignalValidator:
    """
    Evaluates Polymarket probability signals against observed freight rate moves.

    For each market-freight pairing supplied via xcorr_results, the validator:
    - Detects significant freight events in the freight timeseries
    - Classifies each Polymarket signal event as TP, FP, or FN
    - Computes precision, recall, F1, and lead time distribution

    Usage::

        validator = SignalValidator()
        validations = validator.validate_all(
            all_events, xcorr_results, timeseries, freight_data, markets_df
        )
        summary = validator.to_summary_dataframe(validations)
    """

    def __init__(
        self,
        outcome_window: int = 30,
        lookback_window: int = 30,
        freight_threshold_pct: float = 0.08,
        freight_event_window: int = 14,
        min_correlation_magnitude: float = 0.10,
    ) -> None:
        """
        Args:
            outcome_window: Days after a signal to look for a matching freight move.
            lookback_window: Days before a freight event to look for a preceding signal.
            freight_threshold_pct: Min fractional change to qualify as a freight event.
            freight_event_window: Rolling window (days) for freight event detection.
            min_correlation_magnitude: Pairs with |peak_correlation| below this are
                skipped (weak signal, direction assignment is unreliable).
        """
        self.outcome_window = outcome_window
        self.lookback_window = lookback_window
        self.freight_threshold_pct = freight_threshold_pct
        self.freight_event_window = freight_event_window
        self.min_correlation_magnitude = min_correlation_magnitude

    def _expected_direction(self, signal_delta: float, peak_correlation: float) -> str:
        """
        Determine the expected freight direction given a probability shift.

        The sign of peak_correlation encodes the relationship:
          positive → higher probability ⟹ higher freight
          negative → higher probability ⟹ lower freight

        Combined with the direction of the probability shift (delta sign), the
        expected freight direction is sign(peak_correlation × delta).

        Returns 'up', 'down', or 'unknown' when the correlation is too weak.
        """
        if abs(peak_correlation) < self.min_correlation_magnitude:
            return "unknown"
        product = peak_correlation * signal_delta
        return "up" if product > 0 else "down"

    def _get_freight_change_in_window(
        self,
        freight_df: pd.DataFrame,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> Optional[float]:
        """
        Compute the net % change in freight over [start_date, end_date].

        Returns None if there are fewer than 2 observations in the window.
        """
        df = freight_df.copy()
        df["date"] = pd.to_datetime(df["date"])
        window = df[(df["date"] >= start_date) & (df["date"] <= end_date)].dropna(subset=["value"])
        if len(window) < 2:
            return None
        anchor = window.iloc[0]["value"]
        final = window.iloc[-1]["value"]
        if anchor == 0 or np.isnan(anchor):
            return None
        return float((final - anchor) / abs(anchor) * 100)

    def classify_pairing(
        self,
        signal_events: List[ProbabilityEvent],
        freight_events: List[FreightEvent],
        freight_df: pd.DataFrame,
        market_id: str,
        market_title: str,
        freight_index_name: str,
        peak_correlation: float,
        peak_lag_days: int,
    ) -> PairingValidation:
        """
        Classify all signal events for a single market-freight pairing.

        For each signal:
        - Search for a matching freight event in [signal_date, signal_date + outcome_window]
          where the freight direction aligns with the expected direction.
        - TP if found; FP if not.

        For each freight event:
        - Search for any preceding signal in [freight_date - lookback_window, freight_date]
          that would have predicted that direction.
        - FN if no such signal exists.

        Args:
            signal_events: ProbabilityEvents for this market_id.
            freight_events: FreightEvents for this freight_index.
            freight_df: Raw freight DataFrame [date, value] for window computations.
            market_id: Polymarket market identifier.
            market_title: Human-readable title.
            freight_index_name: Freight index label.
            peak_correlation: From the cross-correlation result.
            peak_lag_days: From the cross-correlation result (positive = poly leads).

        Returns:
            PairingValidation with TP/FP/FN breakdown and metrics.
        """
        outcomes: List[SignalOutcome] = []

        # --- Classify each signal as TP or FP ---
        for sig in signal_events:
            expected_dir = self._expected_direction(sig.delta, peak_correlation)
            window_end = sig.timestamp + pd.Timedelta(days=self.outcome_window)

            # Find the first matching freight event in the forward window
            matching = [
                fe for fe in freight_events
                if sig.timestamp < fe.timestamp <= window_end
                and (expected_dir == "unknown" or fe.direction == expected_dir)
            ]

            if matching:
                matched = min(matching, key=lambda fe: (fe.timestamp - sig.timestamp).days)
                lead_time = (matched.timestamp - sig.timestamp).days
                outcome = SignalOutcome(
                    market_id=market_id,
                    market_title=market_title,
                    freight_index=freight_index_name,
                    signal_timestamp=sig.timestamp,
                    signal_delta=sig.delta,
                    signal_direction=sig.direction,
                    expected_freight_direction=expected_dir,
                    outcome="TP",
                    lead_time_days=lead_time,
                    freight_pct_change=matched.pct_change,
                    direction_correct=True,
                    matched_freight_event=matched,
                )
            else:
                raw_change = self._get_freight_change_in_window(
                    freight_df, sig.timestamp, window_end
                )
                outcome = SignalOutcome(
                    market_id=market_id,
                    market_title=market_title,
                    freight_index=freight_index_name,
                    signal_timestamp=sig.timestamp,
                    signal_delta=sig.delta,
                    signal_direction=sig.direction,
                    expected_freight_direction=expected_dir,
                    outcome="FP",
                    lead_time_days=None,
                    freight_pct_change=raw_change,
                    direction_correct=None,
                )
            outcomes.append(outcome)

        # --- Identify FNs: freight events with no preceding predictive signal ---
        for fe in freight_events:
            lookback_start = fe.timestamp - pd.Timedelta(days=self.lookback_window)
            preceding = [
                sig for sig in signal_events
                if lookback_start <= sig.timestamp < fe.timestamp
                and (
                    self._expected_direction(sig.delta, peak_correlation) == fe.direction
                    or abs(peak_correlation) < self.min_correlation_magnitude
                )
            ]
            if not preceding:
                outcomes.append(SignalOutcome(
                    market_id=market_id,
                    market_title=market_title,
                    freight_index=freight_index_name,
                    signal_timestamp=fe.timestamp,  # use freight event date as reference
                    signal_delta=0.0,
                    signal_direction="none",
                    expected_freight_direction=fe.direction,
                    outcome="FN",
                    lead_time_days=None,
                    freight_pct_change=fe.pct_change,
                    direction_correct=None,
                ))

        n_tp = sum(1 for o in outcomes if o.outcome == "TP")
        n_fp = sum(1 for o in outcomes if o.outcome == "FP")
        n_fn = sum(1 for o in outcomes if o.outcome == "FN")

        precision = n_tp / (n_tp + n_fp) if (n_tp + n_fp) > 0 else 0.0
        recall = n_tp / (n_tp + n_fn) if (n_tp + n_fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0 else 0.0
        )
        lead_times = [
            o.lead_time_days for o in outcomes
            if o.outcome == "TP" and o.lead_time_days is not None
        ]

        return PairingValidation(
            market_id=market_id,
            market_title=market_title,
            freight_index=freight_index_name,
            peak_correlation=peak_correlation,
            peak_lag_days=peak_lag_days,
            n_signals=len(signal_events),
            n_freight_events=len(freight_events),
            n_tp=n_tp,
            n_fp=n_fp,
            n_fn=n_fn,
            precision=precision,
            recall=recall,
            f1=f1,
            lead_times=lead_times,
            outcomes=outcomes,
        )

    def validate_all(
        self,
        all_events: List[ProbabilityEvent],
        xcorr_results: List[CrossCorrelationResult],
        timeseries: Dict[str, pd.DataFrame],
        freight_data: Dict[str, pd.DataFrame],
        markets_df: pd.DataFrame,
        sc_only: bool = True,
    ) -> List[PairingValidation]:
        """
        Run validation for all market-freight pairings in xcorr_results.

        Args:
            all_events: All detected ProbabilityEvents (from EventDetector).
            xcorr_results: Cross-correlation results (from CorrelationAnalyser).
            timeseries: Dict of {market_id: DataFrame[date, probability]}.
            freight_data: Dict of {freight_index: DataFrame[date, value]}.
            markets_df: Market metadata DataFrame (must have 'market_id', 'category').
            sc_only: If True, skip pairings where the market has no SC category.

        Returns:
            List of PairingValidation, one per (market_id × freight_index) pair.
        """
        # Build SC-category lookup
        sc_market_ids: set = set()
        if sc_only and "category" in markets_df.columns:
            sc_market_ids = {
                str(row["market_id"])
                for _, row in markets_df.iterrows()
                if pd.notna(row.get("category")) and row.get("category") != ""
            }

        # Pre-cache freight events per index to avoid redundant computation
        freight_events_cache: Dict[str, List[FreightEvent]] = {}
        for fi_name, freight_df in freight_data.items():
            freight_events_cache[fi_name] = detect_freight_events(
                freight_df, fi_name,
                threshold_pct=self.freight_threshold_pct,
                window=self.freight_event_window,
            )
            logger.info(
                "Freight events detected — %s: %d events",
                fi_name, len(freight_events_cache[fi_name]),
            )

        # Build signal lookup: {market_id: [ProbabilityEvent]}
        signal_lookup: Dict[str, List[ProbabilityEvent]] = {}
        for ev in all_events:
            signal_lookup.setdefault(str(ev.market_id), []).append(ev)

        validations: List[PairingValidation] = []
        seen_pairs: set = set()

        for xcorr in xcorr_results:
            mid = str(xcorr.market_id)
            fi_name = xcorr.freight_index

            pair_key = (mid, fi_name)
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            if sc_only and sc_market_ids and mid not in sc_market_ids:
                logger.debug("Skipping non-SC market %s", mid)
                continue

            if abs(xcorr.peak_correlation) < self.min_correlation_magnitude:
                logger.debug(
                    "Skipping weak correlation pair %s × %s (r=%.3f)",
                    mid, fi_name, xcorr.peak_correlation,
                )
                continue

            signal_events = signal_lookup.get(mid, [])
            freight_events = freight_events_cache.get(fi_name, [])
            freight_df = freight_data.get(fi_name)

            if not signal_events:
                logger.debug("No signal events for market %s — skipping.", mid)
                continue
            if freight_df is None:
                logger.debug("No freight data for %s — skipping.", fi_name)
                continue

            pv = self.classify_pairing(
                signal_events=signal_events,
                freight_events=freight_events,
                freight_df=freight_df,
                market_id=mid,
                market_title=xcorr.market_title,
                freight_index_name=fi_name,
                peak_correlation=xcorr.peak_correlation,
                peak_lag_days=xcorr.peak_lag,
            )
            validations.append(pv)
            logger.info(
                "Validated %s × %s: precision=%.2f recall=%.2f F1=%.2f "
                "(TP=%d FP=%d FN=%d, median lead=%s days)",
                mid[:12], fi_name,
                pv.precision, pv.recall, pv.f1,
                pv.n_tp, pv.n_fp, pv.n_fn,
                f"{pv.median_lead_time:.0f}" if pv.median_lead_time is not None else "N/A",
            )

        logger.info(
            "Validation complete: %d pairings validated.", len(validations)
        )
        return validations

    # -------------------------------------------------------------------------
    # Output helpers
    # -------------------------------------------------------------------------

    def to_summary_dataframe(self, validations: List[PairingValidation]) -> pd.DataFrame:
        """
        Summarise validation results as a tidy DataFrame, one row per pairing.

        Columns include precision, recall, F1, lead time stats, and TP/FP/FN counts.
        """
        rows = []
        for v in validations:
            rows.append({
                "market_id": v.market_id,
                "market_title": v.market_title,
                "freight_index": v.freight_index,
                "peak_correlation": round(v.peak_correlation, 3),
                "peak_lag_days": v.peak_lag_days,
                "poly_leads": v.peak_lag_days > 0,
                "n_signals": v.n_signals,
                "n_freight_events": v.n_freight_events,
                "n_tp": v.n_tp,
                "n_fp": v.n_fp,
                "n_fn": v.n_fn,
                "precision": round(v.precision, 3),
                "recall": round(v.recall, 3),
                "f1": round(v.f1, 3),
                "median_lead_time_days": v.median_lead_time,
                "mean_lead_time_days": (
                    round(v.mean_lead_time, 1) if v.mean_lead_time is not None else None
                ),
            })
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values("f1", ascending=False).reset_index(drop=True)
        return df

    def all_outcomes_dataframe(self, validations: List[PairingValidation]) -> pd.DataFrame:
        """
        Return a flat DataFrame of all individual signal outcomes across all pairings.

        Useful for detailed per-event inspection and filtering by outcome type.
        """
        rows = []
        for v in validations:
            for o in v.outcomes:
                rows.append({
                    "market_id": o.market_id,
                    "market_title": o.market_title,
                    "freight_index": o.freight_index,
                    "signal_timestamp": o.signal_timestamp,
                    "signal_delta": round(o.signal_delta, 4),
                    "signal_direction": o.signal_direction,
                    "expected_freight_direction": o.expected_freight_direction,
                    "outcome": o.outcome,
                    "lead_time_days": o.lead_time_days,
                    "freight_pct_change": (
                        round(o.freight_pct_change, 2) if o.freight_pct_change is not None else None
                    ),
                    "direction_correct": o.direction_correct,
                })
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values(["signal_timestamp", "market_id"]).reset_index(drop=True)
        return df


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------


def plot_precision_recall(
    validations: List[PairingValidation],
    top_n: int = 15,
    filename_stem: Optional[str] = "val_precision_recall",
    settings: Optional[Dict] = None,
) -> plt.Figure:
    """
    Horizontal bar chart showing precision and recall for each pairing.

    Pairings are sorted by F1 score.  The top `top_n` pairings are shown.

    Args:
        validations: List of PairingValidation objects.
        top_n: Maximum number of pairings to display.
        filename_stem: Output file stem (None to skip saving).
        settings: Settings dict.

    Returns:
        matplotlib Figure.
    """
    if not validations:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "No validation results", ha="center", va="center")
        return fig

    validations_sorted = sorted(validations, key=lambda v: v.f1, reverse=True)[:top_n]

    labels = [
        f"{v.market_title[:35]}… × {v.freight_index}"
        if len(v.market_title) > 35
        else f"{v.market_title} × {v.freight_index}"
        for v in validations_sorted
    ]
    precisions = [v.precision for v in validations_sorted]
    recalls = [v.recall for v in validations_sorted]

    y = np.arange(len(labels))
    bar_h = 0.35

    fig, ax = plt.subplots(figsize=(11, max(4, len(labels) * 0.55)))
    ax.barh(y + bar_h / 2, precisions, bar_h, color=BLUE, alpha=0.85, label="Precision")
    ax.barh(y - bar_h / 2, recalls, bar_h, color=ORANGE, alpha=0.85, label="Recall")

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Score (0–1)", fontsize=11)
    ax.set_xlim(0, 1.05)
    ax.axvline(0.5, color=GRAY, linestyle="--", linewidth=0.8, alpha=0.7)
    ax.set_title(
        "Signal Validation: Precision & Recall per Market-Freight Pairing\n"
        "(sorted by F1 score, top pairings shown)",
        fontsize=12, fontweight="bold", pad=10,
    )
    ax.legend(loc="lower right", fontsize=10)

    # Annotate F1
    for i, v in enumerate(validations_sorted):
        ax.text(
            1.02, i, f"F1={v.f1:.2f}",
            va="center", fontsize=8, color=DARK_GRAY if "DARK_GRAY" in dir() else "#333333",
        )

    fig.tight_layout()
    if filename_stem:
        _save_figure(fig, filename_stem, settings)
    return fig


def plot_lead_time_histogram(
    validations: List[PairingValidation],
    bins: int = 15,
    filename_stem: Optional[str] = "val_lead_time",
    settings: Optional[Dict] = None,
) -> plt.Figure:
    """
    Histogram of lead times (days) for all true-positive signals across all pairings.

    A longer and positive lead time confirms that Polymarket signals fire before
    the freight rate move, giving supply chain teams actionable advance notice.

    Args:
        validations: List of PairingValidation objects.
        bins: Number of histogram bins.
        filename_stem: Output file stem (None to skip saving).
        settings: Settings dict.

    Returns:
        matplotlib Figure.
    """
    all_lead_times = [lt for v in validations for lt in v.lead_times]

    fig, ax = plt.subplots(figsize=(9, 5))

    if not all_lead_times:
        ax.text(0.5, 0.5, "No true-positive signals detected", ha="center", va="center",
                fontsize=12, color=GRAY, transform=ax.transAxes)
        ax.set_title("Lead Time Distribution (no data)", fontsize=12, fontweight="bold")
        if filename_stem:
            _save_figure(fig, filename_stem, settings)
        return fig

    ax.hist(all_lead_times, bins=bins, color=BLUE, alpha=0.8, edgecolor="white", linewidth=0.5)

    median_lt = np.median(all_lead_times)
    mean_lt = np.mean(all_lead_times)

    ax.axvline(median_lt, color=ORANGE, linewidth=2, linestyle="--",
               label=f"Median: {median_lt:.0f} days")
    ax.axvline(mean_lt, color=RED, linewidth=1.5, linestyle=":",
               label=f"Mean: {mean_lt:.1f} days")

    ax.set_xlabel("Lead Time (days from signal to freight event)", fontsize=11)
    ax.set_ylabel("Count", fontsize=11)
    ax.set_title(
        "Lead Time Distribution: Days Between Polymarket Signal and Freight Rate Move\n"
        f"(n={len(all_lead_times)} true-positive signals across all pairings)",
        fontsize=12, fontweight="bold", pad=10,
    )
    ax.legend(fontsize=10)

    # Shade "actionable" zone (>= 5 days)
    x_max = ax.get_xlim()[1]
    if x_max > 5:
        ax.axvspan(5, x_max, alpha=0.06, color=GREEN,
                   label="Actionable zone (≥5 days)")
        ax.legend(fontsize=10)

    fig.tight_layout()
    if filename_stem:
        _save_figure(fig, filename_stem, settings)
    return fig


def plot_outcome_breakdown(
    validations: List[PairingValidation],
    top_n: int = 12,
    filename_stem: Optional[str] = "val_outcome_breakdown",
    settings: Optional[Dict] = None,
) -> plt.Figure:
    """
    Stacked bar chart showing TP / FP / FN counts per pairing.

    Gives an at-a-glance view of how many signals fired in each category,
    complementing the precision/recall summary.

    Args:
        validations: List of PairingValidation objects.
        top_n: Maximum pairings to display (sorted by F1).
        filename_stem: Output file stem (None to skip saving).
        settings: Settings dict.

    Returns:
        matplotlib Figure.
    """
    if not validations:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "No validation results", ha="center", va="center")
        return fig

    validations_sorted = sorted(validations, key=lambda v: v.f1, reverse=True)[:top_n]

    labels = [
        f"{v.market_title[:30]}… × {v.freight_index}"
        if len(v.market_title) > 30 else f"{v.market_title} × {v.freight_index}"
        for v in validations_sorted
    ]
    tps = [v.n_tp for v in validations_sorted]
    fps = [v.n_fp for v in validations_sorted]
    fns = [v.n_fn for v in validations_sorted]

    x = np.arange(len(labels))
    bar_w = 0.55

    fig, ax = plt.subplots(figsize=(12, max(4, len(labels) * 0.55)))
    ax.barh(x, tps, bar_w, color=GREEN, alpha=0.85, label="True Positive (TP)")
    ax.barh(x, fps, bar_w, left=tps, color=ORANGE, alpha=0.85, label="False Positive (FP)")
    ax.barh(x, fns, bar_w, left=[tp + fp for tp, fp in zip(tps, fps)],
            color=RED, alpha=0.75, label="False Negative (FN)")

    ax.set_yticks(x)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Count", fontsize=11)
    ax.set_title(
        "Signal Outcome Breakdown per Pairing\n"
        "(sorted by F1 score, top pairings shown)",
        fontsize=12, fontweight="bold", pad=10,
    )
    ax.legend(loc="lower right", fontsize=10)
    fig.tight_layout()
    if filename_stem:
        _save_figure(fig, filename_stem, settings)
    return fig

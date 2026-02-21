"""
Event detection: identify significant probability shifts in Polymarket timeseries.

Three complementary detection methods:
1. Threshold-based — delta > N percentage points within a rolling window
2. Rate-of-change — daily change exceeds K standard deviations
3. Combined scoring — ranks events by magnitude for prioritisation
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)


def _load_settings() -> Dict:
    path = Path(__file__).parents[2] / "config" / "settings.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


@dataclass
class ProbabilityEvent:
    """A detected significant probability shift."""

    market_id: str
    market_title: str
    timestamp: pd.Timestamp
    probability_before: float
    probability_after: float
    delta: float                   # signed change in probability
    direction: str                 # 'up' or 'down'
    magnitude: float               # absolute delta
    detection_method: str
    zscore: Optional[float] = None
    volume: Optional[float] = None
    metadata: Dict = field(default_factory=dict)

    @property
    def is_bullish(self) -> bool:
        return self.direction == "up"


def _rolling_threshold_events(
    df: pd.DataFrame,
    market_id: str,
    market_title: str,
    threshold: float = 0.10,
    window: int = 7,
) -> List[ProbabilityEvent]:
    """
    Detect events where probability changes by more than `threshold` within `window` days.

    Args:
        df: DataFrame with [date, probability] sorted by date.
        market_id: Market identifier.
        market_title: Human-readable title.
        threshold: Minimum probability delta to flag (default 0.10 = 10pp).
        window: Rolling window in days.

    Returns:
        List of ProbabilityEvent objects.
    """
    events: List[ProbabilityEvent] = []
    if len(df) < window + 1:
        return events

    prob = df["probability"].values
    dates = pd.to_datetime(df["date"]).values

    for i in range(window, len(df)):
        window_start_prob = prob[i - window]
        current_prob = prob[i]
        delta = current_prob - window_start_prob

        if abs(delta) >= threshold:
            direction = "up" if delta > 0 else "down"
            events.append(
                ProbabilityEvent(
                    market_id=market_id,
                    market_title=market_title,
                    timestamp=pd.Timestamp(dates[i]),
                    probability_before=float(window_start_prob),
                    probability_after=float(current_prob),
                    delta=float(delta),
                    direction=direction,
                    magnitude=abs(delta),
                    detection_method="threshold",
                )
            )

    # Merge overlapping events: keep the largest event per 7-day cluster
    if events:
        events = _deduplicate_events(events, cooldown_days=window)

    return events


def _zscore_events(
    df: pd.DataFrame,
    market_id: str,
    market_title: str,
    zscore_threshold: float = 2.0,
) -> List[ProbabilityEvent]:
    """
    Detect events where the daily probability change exceeds `zscore_threshold` SDs.

    Args:
        df: DataFrame with [date, probability].
        market_id: Market identifier.
        market_title: Human-readable title.
        zscore_threshold: Number of SDs above/below mean to flag.

    Returns:
        List of ProbabilityEvent objects.
    """
    events: List[ProbabilityEvent] = []
    if len(df) < 10:
        return events

    df = df.copy()
    df["daily_change"] = df["probability"].diff()
    df = df.dropna(subset=["daily_change"])

    mean_change = df["daily_change"].mean()
    std_change = df["daily_change"].std()

    if std_change == 0 or pd.isna(std_change):
        return events

    df["zscore"] = (df["daily_change"] - mean_change) / std_change
    flagged = df[df["zscore"].abs() >= zscore_threshold]

    for _, row in flagged.iterrows():
        delta = row["daily_change"]
        prob_before = row["probability"] - delta
        events.append(
            ProbabilityEvent(
                market_id=market_id,
                market_title=market_title,
                timestamp=pd.Timestamp(row["date"]),
                probability_before=float(prob_before),
                probability_after=float(row["probability"]),
                delta=float(delta),
                direction="up" if delta > 0 else "down",
                magnitude=abs(delta),
                detection_method="zscore",
                zscore=float(row["zscore"]),
            )
        )

    return events


def _deduplicate_events(
    events: List[ProbabilityEvent],
    cooldown_days: int = 7,
) -> List[ProbabilityEvent]:
    """
    Remove duplicate events within `cooldown_days` of a larger event.
    Within a cluster, keep the event with the greatest magnitude.
    """
    if not events:
        return events

    events = sorted(events, key=lambda e: e.timestamp)
    kept: List[ProbabilityEvent] = []
    last_kept_ts: Optional[pd.Timestamp] = None

    for ev in events:
        if last_kept_ts is None:
            kept.append(ev)
            last_kept_ts = ev.timestamp
        else:
            gap = (ev.timestamp - last_kept_ts).days
            if gap >= cooldown_days:
                kept.append(ev)
                last_kept_ts = ev.timestamp
            elif ev.magnitude > kept[-1].magnitude:
                # Replace with larger event in the same cluster
                kept[-1] = ev
                last_kept_ts = ev.timestamp

    return kept


class EventDetector:
    """
    Detects significant probability shift events across all Polymarket timeseries.

    Usage::

        detector = EventDetector()
        events = detector.detect_all(timeseries_dict)
        df = detector.to_dataframe(events)
    """

    def __init__(self, settings: Optional[Dict] = None) -> None:
        cfg = settings or _load_settings()
        evtcfg = cfg["analysis"]["event_detection"]
        self.threshold = float(evtcfg.get("probability_shift_threshold", 0.10))
        self.zscore_threshold = float(evtcfg.get("zscore_threshold", 2.0))
        self.window = int(evtcfg.get("rolling_window_days", 7))

    def detect_for_market(
        self,
        market_id: str,
        market_title: str,
        df: pd.DataFrame,
    ) -> List[ProbabilityEvent]:
        """
        Run all detection methods on a single market's timeseries.

        Args:
            market_id: Unique market identifier.
            market_title: Human-readable title.
            df: DataFrame with [date, probability] columns.

        Returns:
            Deduplicated list of ProbabilityEvent objects.
        """
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        threshold_events = _rolling_threshold_events(
            df, market_id, market_title, self.threshold, self.window
        )
        zscore_events = _zscore_events(
            df, market_id, market_title, self.zscore_threshold
        )

        all_events = threshold_events + zscore_events

        # Final deduplication across methods
        all_events = _deduplicate_events(all_events, cooldown_days=self.window)

        logger.debug(
            "Market %s: %d threshold events, %d z-score events → %d after dedup",
            market_id,
            len(threshold_events),
            len(zscore_events),
            len(all_events),
        )
        return all_events

    def detect_all(
        self,
        timeseries: Dict[str, pd.DataFrame],
        markets_df: Optional[pd.DataFrame] = None,
    ) -> List[ProbabilityEvent]:
        """
        Detect events across all markets in `timeseries`.

        Args:
            timeseries: Dict of {market_id: DataFrame(date, probability)}.
            markets_df: Optional DataFrame with market metadata (for title lookup).

        Returns:
            All detected events sorted by timestamp.
        """
        # Build title lookup
        title_map: Dict[str, str] = {}
        if markets_df is not None:
            for _, row in markets_df.iterrows():
                title_map[str(row["market_id"])] = str(row.get("title", row["market_id"]))

        all_events: List[ProbabilityEvent] = []
        for market_id, df in timeseries.items():
            title = title_map.get(market_id, market_id)
            events = self.detect_for_market(market_id, title, df)
            all_events.extend(events)

        all_events.sort(key=lambda e: e.timestamp)
        logger.info(
            "Event detection complete: %d events across %d markets.",
            len(all_events),
            len(timeseries),
        )
        return all_events

    @staticmethod
    def to_dataframe(events: List[ProbabilityEvent]) -> pd.DataFrame:
        """Convert a list of ProbabilityEvent objects to a DataFrame."""
        if not events:
            return pd.DataFrame()

        rows = [
            {
                "market_id": e.market_id,
                "market_title": e.market_title,
                "timestamp": e.timestamp,
                "probability_before": e.probability_before,
                "probability_after": e.probability_after,
                "delta": e.delta,
                "direction": e.direction,
                "magnitude": e.magnitude,
                "detection_method": e.detection_method,
                "zscore": e.zscore,
            }
            for e in events
        ]
        df = pd.DataFrame(rows)
        df = df.sort_values(["timestamp", "magnitude"], ascending=[True, False])
        return df.reset_index(drop=True)

    def get_top_events(
        self,
        events: List[ProbabilityEvent],
        n: int = 20,
    ) -> List[ProbabilityEvent]:
        """Return the N most significant events ranked by magnitude."""
        return sorted(events, key=lambda e: e.magnitude, reverse=True)[:n]

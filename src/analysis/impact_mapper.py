"""
Impact Mapper: translate analytical results into actionable supply chain
intelligence assessments.

This module is the "product demo" layer — it shows what a real-time
intelligence platform would output for procurement and logistics teams.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yaml

from .events import ProbabilityEvent
from .correlation import CrossCorrelationResult

logger = logging.getLogger(__name__)


def _load_mappings() -> Dict:
    path = Path(__file__).parents[2] / "config" / "market_mappings.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _load_settings() -> Dict:
    path = Path(__file__).parents[2] / "config" / "settings.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Impact assessment data structure
# ---------------------------------------------------------------------------


@dataclass
class ImpactAssessment:
    """
    A structured supply chain intelligence alert derived from a Polymarket
    probability shift event.
    """

    signal: str
    timestamp: str
    market_id: str
    market_title: str
    probability_before: float
    probability_after: float
    probability_delta: float
    direction: str
    affected_routes: List[str]
    predicted_impact: str
    predicted_impact_range: str
    recommended_actions: List[str]
    confidence: str
    impact_score: float
    historical_precedent: str
    category: Optional[str] = None
    correlation_strength: Optional[float] = None
    optimal_lag_days: Optional[int] = None

    def to_dict(self) -> Dict:
        return {
            "signal": self.signal,
            "timestamp": self.timestamp,
            "market_id": self.market_id,
            "market_title": self.market_title,
            "probability_before": self.probability_before,
            "probability_after": self.probability_after,
            "probability_delta": self.probability_delta,
            "direction": self.direction,
            "affected_routes": self.affected_routes,
            "predicted_impact": self.predicted_impact,
            "predicted_impact_range": self.predicted_impact_range,
            "recommended_actions": self.recommended_actions,
            "confidence": self.confidence,
            "impact_score": self.impact_score,
            "historical_precedent": self.historical_precedent,
            "category": self.category,
            "correlation_strength": self.correlation_strength,
            "optimal_lag_days": self.optimal_lag_days,
        }


# ---------------------------------------------------------------------------
# Category-specific impact templates
# ---------------------------------------------------------------------------

_IMPACT_TEMPLATES: Dict[str, Dict] = {
    "tariffs_us_china": {
        "affected_routes": [
            "FBX01: China/East Asia → US West Coast",
            "FBX03: China/East Asia → US East Coast",
        ],
        "up_actions": [
            "Pre-ship high-value inventory before tariff effective date",
            "Accelerate ocean freight bookings to secure current rates",
            "Explore alternative sourcing from Vietnam, India, Mexico",
            "Lock in forward freight contracts to hedge rate risk",
            "Increase safety stock for China-sourced components (60–90 day buffer)",
            "Audit supplier base for tariff exposure by HTS code",
        ],
        "down_actions": [
            "Defer non-urgent ocean bookings — rates likely to soften",
            "Review inventory positions to avoid excess stock at higher tariff costs",
            "Renegotiate freight rates at current market levels",
        ],
        "up_impact": "Container rates on Asia-US lanes likely to increase as importers front-load shipments ahead of tariff implementation",
        "down_impact": "Container rates on Asia-US lanes may soften as trade war risk diminishes",
        "up_range": "15–30% rate increase on FBX01/FBX03 within 2–4 weeks",
        "down_range": "5–15% rate decrease on FBX01/FBX03 within 2–4 weeks",
        "precedent_up": "Similar tariff escalation in Jan 2025 preceded 22% FBX01 increase over 3 weeks",
        "precedent_down": "US-China trade truce in late 2024 coincided with 12% rate decrease on trans-Pacific",
    },
    "iran_hormuz": {
        "affected_routes": [
            "BDI: Baltic Dry Index (bulk commodities)",
            "Tanker rates (VLCC, Suezmax)",
        ],
        "up_actions": [
            "Assess energy commodity exposure to Strait of Hormuz routing",
            "Evaluate war risk insurance premium increases",
            "Identify alternative oil/LNG supply sources outside Gulf region",
            "Review just-in-time energy procurement policies",
            "Build strategic inventory of energy-dependent inputs",
        ],
        "down_actions": [
            "Review elevated war risk insurance premiums for potential renegotiation",
            "Resume normal JIT procurement rhythms",
        ],
        "up_impact": "Strait of Hormuz conflict risk increases rerouting probability around Cape of Good Hope, adding 10–14 days transit time for energy shipments",
        "down_impact": "Reduced conflict probability eases tanker routing disruptions",
        "up_range": "10–25% BDI increase within 1–2 weeks of escalation; tanker rates may spike 30–50%",
        "down_range": "Gradual 5–10% BDI moderation over 2–4 weeks",
        "precedent_up": "2024 Houthi attack escalation drove 35% BDI spike and rerouting of major tanker fleets",
        "precedent_down": "Ceasefire announcements historically precede 2–3 week lag before rate normalisation",
    },
    "red_sea_houthi": {
        "affected_routes": [
            "FBX11: China/East Asia → North Europe",
            "FBX_GLOBAL: Global Container Index",
        ],
        "up_actions": [
            "Rebook Asia-Europe shipments via Cape of Good Hope routing (add 10–14 days)",
            "Increase Europe-bound inventory lead times by 2–3 weeks",
            "Secure space on alternative Cape-routed vessels immediately",
            "Assess war risk surcharge exposure on current bookings",
            "Communicate supply chain delays to European customers",
        ],
        "down_actions": [
            "Monitor Suez Canal reopening signals; rebook via Suez to cut transit time",
            "Assess pent-up capacity as ships return to Suez routing",
        ],
        "up_impact": "Elevated Houthi attack probability forces Suez Canal avoidance; Cape routing adds cost and time to Asia-Europe lanes",
        "down_impact": "Reduced attack risk enables Suez Canal resumption, relieving Asia-Europe rate pressure",
        "up_range": "20–40% FBX11 increase within 1–3 weeks as Suez rerouting accelerates",
        "down_range": "10–20% FBX11 decrease over 3–6 weeks as capacity normalises",
        "precedent_up": "Jan 2024 Houthi escalation drove FBX11 from $2,200 to over $7,000 within 6 weeks",
        "precedent_down": "Ceasefire signals in mid-2024 preceded 15% FBX11 decline over 4 weeks",
    },
    "eu_tariffs": {
        "affected_routes": [
            "FBX11: China/East Asia → North Europe",
        ],
        "up_actions": [
            "Review EU import tariff exposure by product category",
            "Accelerate pre-tariff shipments from Asia",
            "Assess bonded warehouse / duty suspension options",
            "Evaluate European near-shoring opportunities",
        ],
        "down_actions": [
            "Defer non-urgent EU-bound bookings pending trade agreement outcome",
        ],
        "up_impact": "EU tariff escalation risk drives pre-tariff front-loading on Asia-Europe lanes",
        "down_impact": "Reduced EU tariff risk eases Asia-Europe rate pressure",
        "up_range": "10–20% FBX11 increase as front-loading demand builds",
        "down_range": "5–10% FBX11 moderation over 2–4 weeks",
        "precedent_up": "EUDR postponement in late 2024 briefly disrupted Asia-Europe booking patterns",
        "precedent_down": "EU trade deal signals historically moderate freight rates within 3–4 weeks",
    },
    "labor_disruption": {
        "affected_routes": [
            "FBX03: China/East Asia → US East Coast",
            "FBX_GLOBAL: Global Container Index",
        ],
        "up_actions": [
            "Accelerate East Coast bookings before strike deadline",
            "Reroute to US West Coast ports as contingency",
            "Expedite air freight for time-sensitive components",
            "Build 30–60 day buffer stock for East Coast-dependent supply chains",
            "Activate port omission routing via West Coast or Gulf ports",
        ],
        "down_actions": [
            "Resume normal East Coast routing once labour agreement confirmed",
            "Assess backlog clearance timeline for capacity planning",
        ],
        "up_impact": "Port strike risk drives front-loading and rerouting, spiking East Coast rates and air freight demand",
        "down_impact": "Labour resolution removes rerouting surcharges and normalises East Coast capacity",
        "up_range": "25–50% FBX03 rate increase in the weeks before a strike; air freight rates may double",
        "down_range": "Gradual normalisation over 3–6 weeks as port backlogs clear",
        "precedent_up": "ILA strike threat in Sep 2024 drove significant pre-strike booking surge on East Coast lanes",
        "precedent_down": "ILA resolution in Jan 2025 preceded 10% FBX03 decrease as backlog cleared",
    },
    "us_trade_policy": {
        "affected_routes": [
            "FBX_GLOBAL: Global Container Index",
            "FBX01: China/East Asia → US West Coast",
        ],
        "up_actions": [
            "Build strategic inventory buffer for policy-sensitive SKUs",
            "Accelerate procurement of goods subject to policy uncertainty",
            "Lock in freight contracts at current rates",
            "Diversify supplier base to reduce single-country dependency",
        ],
        "down_actions": [
            "Reduce safety stock once policy uncertainty clears",
            "Resume normal procurement cycles",
        ],
        "up_impact": "Trade policy uncertainty drives hedging behaviour — importers front-load, boosting spot rates",
        "down_impact": "Policy clarity reduces hedging demand, moderating freight rates",
        "up_range": "10–20% spot rate increase on major US import lanes",
        "down_range": "5–10% rate moderation once policy uncertainty resolves",
        "precedent_up": "Supreme Court tariff ruling uncertainty in early 2025 correlated with heightened trans-Pacific volatility",
        "precedent_down": "USMCA certainty renewal in 2023 preceded 8% rate normalisation",
    },
}

_DEFAULT_TEMPLATE: Dict = {
    "affected_routes": ["Global shipping lanes"],
    "up_actions": [
        "Monitor freight rate developments across major lanes",
        "Assess supply chain exposure to affected trade corridors",
        "Consider building strategic inventory buffer",
    ],
    "down_actions": [
        "Defer discretionary freight bookings to take advantage of potential rate softening",
    ],
    "up_impact": "Increased geopolitical or trade risk may drive freight rate volatility",
    "down_impact": "Reduced risk signals may ease freight rate pressure",
    "up_range": "5–20% rate variation possible on affected lanes",
    "down_range": "5–10% rate moderation possible",
    "precedent_up": "Historical pattern: elevated supply chain risk precedes rate volatility",
    "precedent_down": "Historical pattern: risk resolution typically precedes rate normalisation",
}


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------


def _compute_confidence(
    magnitude: float,
    correlation_strength: Optional[float],
) -> str:
    """Determine confidence level based on event magnitude and historical correlation."""
    score = magnitude

    if correlation_strength is not None:
        score = score * 0.6 + abs(correlation_strength) * 0.4

    if score >= 0.35:
        return "high"
    elif score >= 0.18:
        return "medium"
    else:
        return "low"


def _compute_impact_score(
    magnitude: float,
    correlation_strength: float,
    volume: Optional[float] = None,
) -> float:
    """
    Numeric impact score: magnitude × correlation × volume_weight.
    Returns a score in roughly [0, 1].
    """
    import math

    base = magnitude * abs(correlation_strength)
    if volume is not None and volume > 0:
        volume_weight = min(1.0, math.log10(max(1, volume)) / 6)
        return base * (0.7 + 0.3 * volume_weight)
    return base


# ---------------------------------------------------------------------------
# Impact Mapper
# ---------------------------------------------------------------------------


class ImpactMapper:
    """
    Converts probability shift events + correlation results into structured
    supply chain intelligence assessments.

    Usage::

        mapper = ImpactMapper()
        assessments = mapper.generate_assessments(events, xcorr_results, markets_df)
        df = mapper.to_dataframe(assessments)
    """

    def __init__(self) -> None:
        self.mappings = _load_mappings()
        self.settings = _load_settings()

    def _get_category(self, market_id: str, markets_df: pd.DataFrame) -> Optional[str]:
        row = markets_df[markets_df["market_id"].astype(str) == str(market_id)]
        if row.empty:
            return None
        return row.iloc[0].get("category")

    def _get_correlation(
        self,
        market_id: str,
        xcorr_results: List[CrossCorrelationResult],
    ) -> Tuple[Optional[float], Optional[int]]:
        """Return (peak_correlation, optimal_lag) for the strongest pairing."""
        market_results = [r for r in xcorr_results if r.market_id == market_id]
        if not market_results:
            return None, None
        best = max(market_results, key=lambda r: abs(r.peak_correlation))
        return best.peak_correlation, best.peak_lag

    def generate_assessment(
        self,
        event: ProbabilityEvent,
        markets_df: pd.DataFrame,
        xcorr_results: Optional[List[CrossCorrelationResult]] = None,
    ) -> ImpactAssessment:
        """
        Generate a single ImpactAssessment from a ProbabilityEvent.

        Args:
            event: Detected probability shift event.
            markets_df: DataFrame of all discovered markets.
            xcorr_results: Optional cross-correlation results for confidence scoring.

        Returns:
            ImpactAssessment object.
        """
        category = self._get_category(event.market_id, markets_df)
        template = _IMPACT_TEMPLATES.get(category, _DEFAULT_TEMPLATE)

        is_up = event.direction == "up"
        impact_key = "up_impact" if is_up else "down_impact"
        range_key = "up_range" if is_up else "down_range"
        action_key = "up_actions" if is_up else "down_actions"
        precedent_key = "precedent_up" if is_up else "precedent_down"

        corr, lag = None, None
        if xcorr_results:
            corr, lag = self._get_correlation(event.market_id, xcorr_results)

        confidence = _compute_confidence(event.magnitude, corr)
        impact_score = _compute_impact_score(
            event.magnitude,
            corr if corr is not None else 0.2,
            event.volume,
        )

        prob_pct_before = int(event.probability_before * 100)
        prob_pct_after = int(event.probability_after * 100)
        delta_pct = int(abs(event.delta) * 100)
        direction_word = "rose" if is_up else "fell"

        signal = (
            f"{event.market_title}: probability {direction_word} from "
            f"{prob_pct_before}% to {prob_pct_after}% ({delta_pct:+d}pp shift)"
        )

        return ImpactAssessment(
            signal=signal,
            timestamp=event.timestamp.date().isoformat(),
            market_id=event.market_id,
            market_title=event.market_title,
            probability_before=event.probability_before,
            probability_after=event.probability_after,
            probability_delta=event.delta,
            direction=event.direction,
            affected_routes=template.get("affected_routes", []),
            predicted_impact=template.get(impact_key, ""),
            predicted_impact_range=template.get(range_key, ""),
            recommended_actions=template.get(action_key, []),
            confidence=confidence,
            impact_score=round(impact_score, 4),
            historical_precedent=template.get(precedent_key, ""),
            category=category,
            correlation_strength=corr,
            optimal_lag_days=lag,
        )

    def generate_assessments(
        self,
        events: List[ProbabilityEvent],
        markets_df: pd.DataFrame,
        xcorr_results: Optional[List[CrossCorrelationResult]] = None,
        min_magnitude: float = 0.05,
    ) -> List[ImpactAssessment]:
        """
        Generate assessments for all significant events.

        Args:
            events: Detected probability shift events.
            markets_df: Markets metadata DataFrame.
            xcorr_results: Optional cross-correlation results.
            min_magnitude: Minimum event magnitude to include.

        Returns:
            List of ImpactAssessment objects sorted by impact_score descending.
        """
        assessments = []
        for event in events:
            if event.magnitude < min_magnitude:
                continue
            try:
                assessment = self.generate_assessment(event, markets_df, xcorr_results)
                assessments.append(assessment)
            except Exception as exc:
                logger.warning("Failed to generate assessment for %s: %s", event.market_id, exc)

        assessments.sort(key=lambda a: a.impact_score, reverse=True)
        logger.info("Generated %d impact assessments.", len(assessments))
        return assessments

    @staticmethod
    def to_dataframe(assessments: List[ImpactAssessment]) -> pd.DataFrame:
        """Convert assessments list to a DataFrame."""
        if not assessments:
            return pd.DataFrame()
        return pd.DataFrame([a.to_dict() for a in assessments])

    def generate_report_section(
        self,
        assessments: List[ImpactAssessment],
        top_n: int = 5,
    ) -> str:
        """
        Generate a markdown-formatted report section for the top N assessments.

        Args:
            assessments: List of ImpactAssessment objects.
            top_n: Number of top assessments to include.

        Returns:
            Markdown string.
        """
        lines = [
            "## Supply Chain Intelligence Alerts\n",
            f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}*\n",
            f"Top {min(top_n, len(assessments))} highest-impact signals:\n",
        ]

        for i, a in enumerate(assessments[:top_n], 1):
            lines += [
                f"### Alert #{i} — Confidence: {a.confidence.upper()}",
                f"**Signal:** {a.signal}",
                f"**Date:** {a.timestamp}",
                f"**Category:** {a.category or 'General'}",
                f"**Impact Score:** {a.impact_score:.4f}\n",
                "**Affected Routes:**",
            ]
            for route in a.affected_routes:
                lines.append(f"- {route}")

            lines += [
                f"\n**Predicted Impact:** {a.predicted_impact}",
                f"**Expected Range:** {a.predicted_impact_range}",
                "\n**Recommended Actions:**",
            ]
            for action in a.recommended_actions:
                lines.append(f"- {action}")

            if a.historical_precedent:
                lines.append(f"\n**Historical Precedent:** {a.historical_precedent}")

            if a.correlation_strength is not None:
                lines.append(
                    f"**Correlation Strength:** r={a.correlation_strength:.3f}, "
                    f"optimal lag={a.optimal_lag_days} days"
                )

            lines.append("\n---\n")

        return "\n".join(lines)

"""
Publication-quality chart generation for the Polymarket SCM Intelligence whitepaper.

All charts are exported as both PNG (300 DPI) and SVG.
Style: clean, minimal, professional — suitable for VC investor presentations.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import yaml

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

logger = logging.getLogger(__name__)

# Color palette
BLUE = "#1f6aa5"
ORANGE = "#e07b39"
LIGHT_BLUE = "#a8c8e8"
LIGHT_ORANGE = "#f0c8a8"
GRAY = "#888888"
DARK_GRAY = "#333333"


def _load_settings() -> Dict:
    path = Path(__file__).parents[2] / "config" / "settings.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _get_figures_dir(settings: Optional[Dict] = None) -> Path:
    if settings is None:
        settings = _load_settings()
    figures_dir = Path(settings["output"]["figures_dir"])
    figures_dir.mkdir(parents=True, exist_ok=True)
    return figures_dir


def _save_figure(fig: plt.Figure, filename_stem: str, settings: Optional[Dict] = None) -> List[Path]:
    """Save a figure in all configured formats (PNG + SVG)."""
    if settings is None:
        settings = _load_settings()

    figures_dir = _get_figures_dir(settings)
    dpi = settings["output"].get("figure_dpi", 300)
    formats = settings["output"].get("figure_formats", ["png", "svg"])

    saved_paths = []
    for fmt in formats:
        path = figures_dir / f"{filename_stem}.{fmt}"
        fig.savefig(path, dpi=dpi if fmt == "png" else None, bbox_inches="tight")
        saved_paths.append(path)
        logger.info("Saved chart: %s", path)

    return saved_paths


# ---------------------------------------------------------------------------
# Chart 1: Dual-axis overlay (hero chart)
# ---------------------------------------------------------------------------


def plot_dual_axis_overlay(
    poly_df: pd.DataFrame,
    freight_df: pd.DataFrame,
    market_title: str,
    freight_index_name: str,
    event_timestamps: Optional[List[pd.Timestamp]] = None,
    filename_stem: Optional[str] = None,
    settings: Optional[Dict] = None,
) -> plt.Figure:
    """
    Plot Polymarket probability (left y-axis) and freight index (right y-axis)
    on a shared time axis. Shaded regions highlight significant probability shifts.

    Args:
        poly_df: DataFrame with [date, probability] columns.
        freight_df: DataFrame with [date, value] columns.
        market_title: Title for the Polymarket series.
        freight_index_name: Label for the freight index.
        event_timestamps: Optional list of event dates to shade.
        filename_stem: Output file stem (auto-generated if None).
        settings: Settings dict.

    Returns:
        matplotlib Figure.
    """
    fig, ax1 = plt.subplots(figsize=(12, 5))

    poly = poly_df.copy()
    poly["date"] = pd.to_datetime(poly["date"])
    poly = poly.sort_values("date")

    freight = freight_df.copy()
    freight["date"] = pd.to_datetime(freight["date"])
    freight = freight.sort_values("date")

    # Left axis: probability
    ax1.plot(poly["date"], poly["probability"] * 100, color=BLUE, linewidth=2.0,
             label=f"Probability: {market_title[:50]}", zorder=3)
    ax1.set_ylabel("Implied Probability (%)", color=BLUE, fontsize=11)
    ax1.tick_params(axis="y", labelcolor=BLUE)
    ax1.set_ylim(0, 105)

    # Right axis: freight index
    ax2 = ax1.twinx()
    ax2.plot(freight["date"], freight["value"], color=ORANGE, linewidth=1.8,
             alpha=0.85, label=freight_index_name, zorder=2)
    ax2.set_ylabel(freight_index_name, color=ORANGE, fontsize=11)
    ax2.tick_params(axis="y", labelcolor=ORANGE)
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color(ORANGE)

    # Shade event windows
    if event_timestamps:
        for i, ts in enumerate(event_timestamps[:10]):  # cap at 10 events
            ts = pd.Timestamp(ts)
            ax1.axvspan(ts - pd.Timedelta(days=2), ts + pd.Timedelta(days=2),
                        alpha=0.15, color=BLUE, zorder=1,
                        label="Probability Shift" if i == 0 else "_nolegend_")
            ax1.axvline(ts, color=BLUE, linewidth=0.8, linestyle="--", alpha=0.6, zorder=2)

    # X-axis formatting
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=30, ha="right")

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=9,
               framealpha=0.9)

    title = f"Polymarket Signal vs {freight_index_name}: Leading Indicator Analysis"
    ax1.set_title(title, fontsize=13, fontweight="bold", pad=12)
    ax1.set_xlabel("Date", fontsize=11)

    fig.text(0.99, 0.01,
             "Sources: Polymarket CLOB API | Freight data: Freightos Baltic Exchange / Baltic Exchange",
             ha="right", va="bottom", fontsize=7, color=GRAY)

    plt.tight_layout()

    stem = filename_stem or f"dual_axis_{market_title[:20].replace(' ', '_').lower()}_{freight_index_name.lower()}"
    _save_figure(fig, stem, settings)
    return fig


# ---------------------------------------------------------------------------
# Chart 2: Cross-correlation plot
# ---------------------------------------------------------------------------


def plot_cross_correlation(
    lags: List[int],
    correlations: List[float],
    p_values: List[float],
    market_title: str,
    freight_index_name: str,
    peak_lag: int,
    peak_correlation: float,
    filename_stem: Optional[str] = None,
    settings: Optional[Dict] = None,
) -> plt.Figure:
    """
    Bar chart showing Pearson correlation at each lag (-N to +N days).
    Positive lag = Polymarket leads freight. Peak lag is annotated.

    Args:
        lags: List of lag values tested.
        correlations: Pearson r at each lag.
        p_values: P-values at each lag.
        market_title: Polymarket series label.
        freight_index_name: Freight index label.
        peak_lag: Lag at maximum absolute correlation.
        peak_correlation: Correlation at peak lag.
        filename_stem: Output file stem.
        settings: Settings dict.

    Returns:
        matplotlib Figure.
    """
    fig, ax = plt.subplots(figsize=(12, 5))

    lags_arr = np.array(lags)
    corrs_arr = np.array(correlations, dtype=float)
    pvals_arr = np.array(p_values, dtype=float)

    # Color bars by significance and sign
    colors = []
    for c, p in zip(corrs_arr, pvals_arr):
        if np.isnan(c):
            colors.append(GRAY)
        elif p < 0.05:
            colors.append(BLUE if c >= 0 else ORANGE)
        else:
            colors.append(LIGHT_BLUE if c >= 0 else LIGHT_ORANGE)

    bars = ax.bar(lags_arr, np.where(np.isnan(corrs_arr), 0, corrs_arr),
                  color=colors, width=0.8, edgecolor="none")

    # Annotate peak
    ax.annotate(
        f"Peak: r={peak_correlation:.3f}\nat lag={peak_lag}d",
        xy=(peak_lag, peak_correlation),
        xytext=(peak_lag + (5 if peak_lag < 20 else -15), peak_correlation + 0.05),
        fontsize=9, color=DARK_GRAY,
        arrowprops=dict(arrowstyle="->", color=DARK_GRAY, lw=1.2),
    )

    # Reference lines
    ax.axhline(0, color=DARK_GRAY, linewidth=0.8)
    ax.axvline(0, color=DARK_GRAY, linewidth=0.8, linestyle="--", alpha=0.5,
               label="Contemporaneous (lag=0)")

    # Shade "polymarket leads" region
    ax.axvspan(0, max(lags_arr), alpha=0.06, color=BLUE, label="Polymarket leads →")

    ax.set_xlabel("Lag (days) — positive = Polymarket leads freight", fontsize=11)
    ax.set_ylabel("Pearson Correlation (r)", fontsize=11)
    ax.set_title(
        f"Cross-Correlation: {market_title[:45]} vs {freight_index_name}",
        fontsize=13, fontweight="bold", pad=12
    )
    ax.legend(fontsize=9, framealpha=0.9)

    # Custom legend for bar colours
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=BLUE, label="Significant positive (p<0.05)"),
        Patch(facecolor=ORANGE, label="Significant negative (p<0.05)"),
        Patch(facecolor=LIGHT_BLUE, label="Not significant"),
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=9, framealpha=0.9)

    ax.set_xlim(min(lags_arr) - 1, max(lags_arr) + 1)
    fig.text(0.99, 0.01, "Sources: Polymarket CLOB API | Freight data",
             ha="right", va="bottom", fontsize=7, color=GRAY)

    plt.tight_layout()

    stem = filename_stem or f"xcorr_{market_title[:20].replace(' ', '_').lower()}_{freight_index_name.lower()}"
    _save_figure(fig, stem, settings)
    return fig


# ---------------------------------------------------------------------------
# Chart 3: Event study
# ---------------------------------------------------------------------------


def plot_event_study(
    event_window: List[int],
    mean_freight_change: List[float],
    ci_lower: List[float],
    ci_upper: List[float],
    baseline_change: float,
    market_title: str,
    freight_index_name: str,
    n_events: int,
    filename_stem: Optional[str] = None,
    settings: Optional[Dict] = None,
) -> plt.Figure:
    """
    Plot average freight index behaviour around significant probability shift events.

    Shows mean pct change with 95% confidence bands, vs baseline average.

    Args:
        event_window: Days relative to event (e.g. [-5, ..., +30]).
        mean_freight_change: Mean pct change at each day relative to event.
        ci_lower: Lower 95% CI bound.
        ci_upper: Upper 95% CI bound.
        baseline_change: Average non-event period freight pct change.
        market_title: Polymarket series label.
        freight_index_name: Freight index label.
        n_events: Number of events included in the study.
        filename_stem: Output file stem.
        settings: Settings dict.

    Returns:
        matplotlib Figure.
    """
    fig, ax = plt.subplots(figsize=(10, 5))

    window = np.array(event_window)
    mean = np.array(mean_freight_change, dtype=float)
    lower = np.array(ci_lower, dtype=float)
    upper = np.array(ci_upper, dtype=float)

    ax.plot(window, mean, color=BLUE, linewidth=2.2, label=f"Mean {freight_index_name} change (n={n_events})", zorder=3)
    ax.fill_between(window, lower, upper, alpha=0.2, color=BLUE, label="95% confidence interval")

    # Baseline
    ax.axhline(baseline_change, color=GRAY, linewidth=1.2, linestyle="--",
               label=f"Baseline average ({baseline_change:.2f}%)")
    ax.axhline(0, color=DARK_GRAY, linewidth=0.6)
    ax.axvline(0, color=ORANGE, linewidth=1.5, linestyle="--", label="Event date (t=0)", zorder=4)

    # Shade post-event window
    ax.axvspan(0, max(window), alpha=0.05, color=ORANGE)

    # Annotations
    post_mean = float(np.nanmean(mean[window >= 0]))
    ax.annotate(
        f"Post-event avg: {post_mean:+.1f}%",
        xy=(max(window) * 0.6, post_mean),
        fontsize=9, color=DARK_GRAY,
    )

    ax.set_xlabel("Days relative to probability shift event (t=0)", fontsize=11)
    ax.set_ylabel(f"{freight_index_name} % change vs event-day level", fontsize=11)
    ax.set_title(
        f"Event Study: {freight_index_name} Response to Polymarket Signal\n"
        f"'{market_title[:55]}'",
        fontsize=12, fontweight="bold", pad=12
    )
    ax.legend(fontsize=9, framealpha=0.9)

    fig.text(0.99, 0.01, "Sources: Polymarket CLOB API | Freight data",
             ha="right", va="bottom", fontsize=7, color=GRAY)

    plt.tight_layout()

    stem = filename_stem or f"event_study_{market_title[:20].replace(' ', '_').lower()}_{freight_index_name.lower()}"
    _save_figure(fig, stem, settings)
    return fig


# ---------------------------------------------------------------------------
# Chart 4: Market landscape heatmap
# ---------------------------------------------------------------------------


def plot_correlation_heatmap(
    xcorr_df: pd.DataFrame,
    filename_stem: str = "heatmap_correlation",
    settings: Optional[Dict] = None,
) -> plt.Figure:
    """
    Heatmap of peak correlation strength for all market × freight pairings.

    Args:
        xcorr_df: DataFrame with columns [market_title, freight_index, peak_correlation].
        filename_stem: Output file stem.
        settings: Settings dict.

    Returns:
        matplotlib Figure.
    """
    if xcorr_df.empty:
        logger.warning("No cross-correlation data for heatmap.")
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No data available", ha="center", va="center", transform=ax.transAxes)
        return fig

    import seaborn as sns

    pivot = xcorr_df.pivot_table(
        index="market_title",
        columns="freight_index",
        values="peak_correlation",
        aggfunc="first",
    )

    # Truncate long titles
    pivot.index = [t[:45] + "…" if len(t) > 45 else t for t in pivot.index]

    fig_height = max(5, len(pivot) * 0.45)
    fig, ax = plt.subplots(figsize=(10, fig_height))

    sns.heatmap(
        pivot,
        ax=ax,
        cmap="RdBu_r",
        center=0,
        vmin=-0.6,
        vmax=0.6,
        annot=True,
        fmt=".2f",
        annot_kws={"size": 8},
        linewidths=0.5,
        linecolor="#dddddd",
        cbar_kws={"label": "Peak Pearson r", "shrink": 0.6},
    )

    ax.set_title(
        "Correlation Strength: Polymarket Signals vs Freight Indexes",
        fontsize=13, fontweight="bold", pad=14
    )
    ax.set_xlabel("Freight Index", fontsize=11)
    ax.set_ylabel("Polymarket Market", fontsize=11)
    ax.tick_params(axis="y", labelsize=8)
    ax.tick_params(axis="x", labelsize=9)

    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")

    fig.text(0.99, 0.01, "Sources: Polymarket CLOB API | Freight data",
             ha="right", va="bottom", fontsize=7, color=GRAY)

    plt.tight_layout()
    _save_figure(fig, filename_stem, settings)
    return fig


# ---------------------------------------------------------------------------
# Chart 5: Annotated timeline
# ---------------------------------------------------------------------------


def plot_annotated_timeline(
    poly_df: pd.DataFrame,
    freight_df: pd.DataFrame,
    events_df: pd.DataFrame,
    market_title: str,
    freight_index_name: str,
    filename_stem: Optional[str] = None,
    settings: Optional[Dict] = None,
) -> plt.Figure:
    """
    Annotated timeline showing probability shifts alongside freight rate changes.

    Top panel: Polymarket probability
    Bottom panel: Freight index with event annotations

    Args:
        poly_df: DataFrame with [date, probability].
        freight_df: DataFrame with [date, value].
        events_df: DataFrame of detected events with [timestamp, delta, market_title].
        market_title: Polymarket series label.
        freight_index_name: Freight index label.
        filename_stem: Output file stem.
        settings: Settings dict.

    Returns:
        matplotlib Figure.
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True,
                                    gridspec_kw={"height_ratios": [1, 1.4]})

    poly = poly_df.copy()
    poly["date"] = pd.to_datetime(poly["date"])
    poly = poly.sort_values("date")

    freight = freight_df.copy()
    freight["date"] = pd.to_datetime(freight["date"])
    freight = freight.sort_values("date")

    # Top panel: probability
    ax1.plot(poly["date"], poly["probability"] * 100, color=BLUE, linewidth=2.0)
    ax1.fill_between(poly["date"], 0, poly["probability"] * 100, alpha=0.1, color=BLUE)
    ax1.set_ylabel("Probability (%)", color=BLUE, fontsize=10)
    ax1.tick_params(axis="y", labelcolor=BLUE)
    ax1.set_ylim(0, 105)
    ax1.set_title(f"Timeline: {market_title[:60]}", fontsize=12, fontweight="bold", pad=10)

    # Bottom panel: freight
    ax2.plot(freight["date"], freight["value"], color=ORANGE, linewidth=1.8)
    ax2.fill_between(freight["date"], freight["value"].min() * 0.9, freight["value"],
                     alpha=0.08, color=ORANGE)
    ax2.set_ylabel(freight_index_name, color=ORANGE, fontsize=10)
    ax2.tick_params(axis="y", labelcolor=ORANGE)
    ax2.set_xlabel("Date", fontsize=11)

    # Event annotations
    if not events_df.empty:
        top_events = events_df.nlargest(min(8, len(events_df)), "magnitude")
        for _, ev in top_events.iterrows():
            ts = pd.Timestamp(ev["timestamp"])
            delta_pct = int(ev["delta"] * 100)
            color = BLUE if ev["direction"] == "up" else ORANGE

            # Vertical lines on both panels
            ax1.axvline(ts, color=color, linewidth=1.0, linestyle=":", alpha=0.7)
            ax2.axvline(ts, color=color, linewidth=1.0, linestyle=":", alpha=0.7)

            # Annotation on top panel
            prob_y = poly.loc[poly["date"] <= ts, "probability"].iloc[-1] * 100 if not poly.loc[poly["date"] <= ts].empty else 50
            ax1.annotate(
                f"{delta_pct:+d}pp",
                xy=(ts, min(prob_y + 5, 95)),
                fontsize=7, color=color, ha="center",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor=color, alpha=0.8),
            )

    # X-axis formatting
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=30, ha="right")

    fig.text(0.99, 0.01, "Sources: Polymarket CLOB API | Freight data",
             ha="right", va="bottom", fontsize=7, color=GRAY)

    plt.tight_layout()

    stem = filename_stem or f"timeline_{market_title[:20].replace(' ', '_').lower()}_{freight_index_name.lower()}"
    _save_figure(fig, stem, settings)
    return fig


# ---------------------------------------------------------------------------
# Convenience: generate all charts from analysis results
# ---------------------------------------------------------------------------


def generate_all_charts(
    timeseries: Dict[str, pd.DataFrame],
    freight_data: Dict[str, pd.DataFrame],
    markets_df: pd.DataFrame,
    events_df: pd.DataFrame,
    xcorr_results,
    event_study_results,
    settings: Optional[Dict] = None,
) -> List[Path]:
    """
    Generate all whitepaper charts for all significant market-freight pairings.

    Args:
        timeseries: Dict of {market_id: DataFrame(date, probability)}.
        freight_data: Dict of {index_name: DataFrame(date, value)}.
        markets_df: Discovered markets DataFrame.
        events_df: Detected events DataFrame.
        xcorr_results: List of CrossCorrelationResult objects.
        event_study_results: List of EventStudyResult objects.
        settings: Settings dict.

    Returns:
        List of saved file paths.
    """
    import yaml as _yaml

    if settings is None:
        settings = _load_settings()

    all_paths: List[Path] = []

    # Build a cross-correlation summary DataFrame for heatmap
    xcorr_rows = []
    for r in xcorr_results:
        xcorr_rows.append({
            "market_id": r.market_id,
            "market_title": r.market_title,
            "freight_index": r.freight_index,
            "peak_correlation": r.peak_correlation,
            "peak_lag_days": r.peak_lag,
        })
    xcorr_df = pd.DataFrame(xcorr_rows)

    # 1. Heatmap — all pairings
    if not xcorr_df.empty:
        fig = plot_correlation_heatmap(xcorr_df, settings=settings)
        plt.close(fig)

    # 2. Per-pairing charts: dual axis, xcorr bars, event study, timeline
    for r in xcorr_results[:6]:  # cap at 6 to keep output manageable
        market_id = r.market_id
        fi_name = r.freight_index

        poly_df = timeseries.get(market_id)
        freight_df = freight_data.get(fi_name)
        if poly_df is None or freight_df is None:
            continue

        market_row = markets_df[markets_df["market_id"].astype(str) == str(market_id)]
        title = r.market_title

        mkt_events = events_df[events_df["market_id"].astype(str) == str(market_id)] if not events_df.empty else pd.DataFrame()
        event_ts = list(pd.to_datetime(mkt_events["timestamp"])) if not mkt_events.empty else []

        safe_id = str(market_id)[:12].replace("/", "_")

        # Dual axis
        try:
            fig = plot_dual_axis_overlay(
                poly_df, freight_df, title, fi_name,
                event_timestamps=event_ts,
                filename_stem=f"dual_axis_{safe_id}_{fi_name.lower()}",
                settings=settings,
            )
            plt.close(fig)
        except Exception as exc:
            logger.warning("Dual axis chart failed for %s: %s", market_id, exc)

        # Cross-correlation bars
        try:
            fig = plot_cross_correlation(
                r.lags, r.correlations, r.p_values,
                title, fi_name, r.peak_lag, r.peak_correlation,
                filename_stem=f"xcorr_{safe_id}_{fi_name.lower()}",
                settings=settings,
            )
            plt.close(fig)
        except Exception as exc:
            logger.warning("XCorr chart failed for %s: %s", market_id, exc)

        # Timeline
        if not mkt_events.empty:
            try:
                fig = plot_annotated_timeline(
                    poly_df, freight_df, mkt_events, title, fi_name,
                    filename_stem=f"timeline_{safe_id}_{fi_name.lower()}",
                    settings=settings,
                )
                plt.close(fig)
            except Exception as exc:
                logger.warning("Timeline chart failed for %s: %s", market_id, exc)

    # 3. Event study charts
    for es in event_study_results[:4]:
        try:
            fig = plot_event_study(
                es.event_window, es.mean_freight_change,
                es.ci_lower, es.ci_upper,
                es.baseline_change, es.market_title,
                es.freight_index, es.n_events,
                filename_stem=f"event_study_{es.market_id[:12]}_{es.freight_index.lower()}",
                settings=settings,
            )
            plt.close(fig)
        except Exception as exc:
            logger.warning("Event study chart failed: %s", exc)

    figures_dir = _get_figures_dir(settings)
    all_paths = list(figures_dir.glob("*.png")) + list(figures_dir.glob("*.svg"))
    logger.info("Generated %d chart files in %s", len(all_paths), figures_dir)
    return all_paths

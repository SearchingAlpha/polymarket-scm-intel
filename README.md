# Polymarket Supply Chain Intelligence MVP

**Core thesis:** Probability shifts in Polymarket prediction markets on tariffs, geopolitical conflicts, and trade policy changes precede measurable movements in shipping freight indexes — making prediction markets a viable early warning system for supply chain risk.

This MVP demonstrates the analytical framework for a VC investor whitepaper.

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the full pipeline via notebooks

```bash
jupyter notebook notebooks/
```

Run notebooks in order:
1. `01_market_discovery.ipynb` — Find supply-chain-relevant Polymarket markets
2. `02_data_collection.ipynb` — Fetch probability timeseries and freight data
3. `03_analysis.ipynb` — Cross-correlation, Granger causality, event detection
4. `04_whitepaper_figures.ipynb` — Generate publication-quality charts + report

### 3. Or run programmatically

```python
from src.polymarket.client import PolymarketClient
from src.polymarket.market_discovery import MarketDiscovery
from src.polymarket.timeseries import TimeseriesFetcher
from src.freight.scraper import fetch_all_freight_indexes
from src.freight.normalize import prepare_freight_panel
from src.analysis.events import EventDetector
from src.analysis.correlation import CorrelationAnalyser
from src.analysis.impact_mapper import ImpactMapper
from src.visualization.charts import generate_all_charts

# 1. Discover markets
client = PolymarketClient()
markets_df = MarketDiscovery(client).run()

# 2. Fetch timeseries
timeseries = TimeseriesFetcher(client).fetch_all(markets_df)

# 3. Freight data
freight_raw = fetch_all_freight_indexes(use_synthetic_fallback=True)
freight_data = prepare_freight_panel(freight_raw)

# 4. Analyse
events = EventDetector().detect_all(timeseries, markets_df)
analyser = CorrelationAnalyser()
xcorr = analyser.run_cross_correlations(timeseries, freight_data, markets_df)
granger = analyser.run_granger_tests(timeseries, freight_data, markets_df)

# 5. Impact assessments
assessments = ImpactMapper().generate_assessments(events, markets_df, xcorr)
for a in assessments[:3]:
    print(a.signal, "→", a.predicted_impact_range)
```

---

## Project Structure

```
polymarket-scm-intel/
├── config/
│   ├── settings.yaml           # API endpoints, thresholds, date ranges
│   └── market_mappings.yaml    # Keywords, category definitions, freight index config
├── src/
│   ├── polymarket/
│   │   ├── client.py           # Gamma + CLOB API client (rate limiting, caching)
│   │   ├── market_discovery.py # Tag- and keyword-based market finder
│   │   └── timeseries.py       # Price history fetcher, daily resampler
│   ├── freight/
│   │   ├── scraper.py          # BDI/FBX downloader with synthetic fallback
│   │   └── normalize.py        # Daily upsampling, pct_change, z-score, alignment
│   ├── analysis/
│   │   ├── events.py           # Probability shift event detection
│   │   ├── correlation.py      # Cross-correlation + Granger causality
│   │   └── impact_mapper.py    # Impact assessments + recommended actions
│   └── visualization/
│       └── charts.py           # 5 publication-quality chart types
├── notebooks/
│   ├── 01_market_discovery.ipynb
│   ├── 02_data_collection.ipynb
│   ├── 03_analysis.ipynb
│   └── 04_whitepaper_figures.ipynb
├── data/
│   ├── raw/        # Cached raw API responses (JSON)
│   ├── processed/  # Cleaned timeseries (CSV/Parquet)
│   └── freight/    # Freight index CSVs
└── output/
    ├── figures/    # Charts (PNG + SVG, 300 DPI)
    └── report.md   # Auto-generated analysis summary
```

---

## Freight Data Setup

Freight data can be loaded three ways (tried in order):

### Option A: Manual CSV download (recommended for production)

Place CSV files in `data/freight/` with the following names:

| File | Index | Source |
|------|-------|--------|
| `bdi.csv` | Baltic Dry Index | [TradingEconomics](https://tradingeconomics.com/commodity/baltic) or [Stooq](https://stooq.com/q/d/l/?s=bdi&i=d) |
| `fbx_global.csv` | FBX Global Container Index | [MacroMicro](https://en.macromicro.me/series/17502/fbx-global-container-index-weekly) |
| `fbx01.csv` | FBX01 China→US West Coast | [Freightos Terminal](https://terminal.freightos.com) |
| `fbx03.csv` | FBX03 China→US East Coast | [Freightos Terminal](https://terminal.freightos.com) |
| `fbx11.csv` | FBX11 China→North Europe | [Freightos Terminal](https://terminal.freightos.com) |

Expected CSV format (flexible column matching):
```
date,value
2024-01-05,1456.0
2024-01-08,1489.0
```

### Option B: Programmatic download

BDI is automatically downloaded from Stooq (daily CSV endpoint) if no manual file is found.

### Option C: Synthetic data (default fallback)

If neither of the above is available, the pipeline generates realistic synthetic data for development and pipeline validation. Synthetic files are saved with `_synthetic` suffix so you can identify them.

To disable synthetic fallback:
```python
fetch_all_freight_indexes(use_synthetic_fallback=False)
```

---

## Polymarket API

No API key required for read-only access.

| API | Base URL | Purpose |
|-----|----------|---------|
| Gamma | `https://gamma-api.polymarket.com` | Market discovery, metadata |
| CLOB | `https://clob.polymarket.com` | Price history, current prices |

Rate limit: ~100 req/min (enforced automatically). All responses are cached in `data/raw/` for 24 hours.

---

## Analysis Details

### Event Detection

Three complementary methods:
- **Threshold**: probability delta > 10pp within a 7-day rolling window
- **Z-score**: daily change > 2 standard deviations from historical mean
- Events deduplicated with a 7-day cooldown

### Cross-Correlation

- Pearson correlation between daily probability changes and freight index changes
- Tested at lags from -30 to +30 days
- Positive lag = Polymarket leads freight (the desired leading indicator signature)
- P-values computed for significance testing

### Granger Causality

- Tests whether past prediction market probability changes improve forecasts of freight rate changes
- Uses `statsmodels.tsa.stattools.grangercausalitytests`
- Tested up to lag 14 days

### Event Study

- Computes average freight index behaviour around probability shift events
- Event window: t-5 to t+30 relative to event date
- Cumulative Abnormal Return (CAR) vs non-event baseline

---

## Market Categories

| Category | Polymarket Signal | Freight Indicator | Causal Logic |
|----------|------------------|-------------------|--------------|
| `tariffs_us_china` | US-China tariff rate contracts | FBX01, FBX03 | Tariff escalation → front-loading → container rate spike |
| `iran_hormuz` | Iran conflict / Hormuz contracts | BDI | Conflict risk → Strait closure → Cape rerouting |
| `red_sea_houthi` | Houthi attack contracts | FBX11, FBX Global | Attack risk → Suez avoidance → longer routes |
| `eu_tariffs` | EU trade policy contracts | FBX11 | EU disruption → European import pattern changes |
| `labor_disruption` | Port strike contracts | FBX03, FBX Global | Strike risk → front-loading + rerouting |
| `us_trade_policy` | Supreme Court / general trade policy | FBX Global, FBX01 | Policy uncertainty → importer hedging |

---

## Output

After running notebook 04:

- **`output/figures/`** — 5+ chart types in PNG (300 DPI) and SVG:
  - `fig1_dual_axis_hero.*` — Hero chart: probability vs freight on shared timeline
  - `fig2_xcorr_best.*` — Cross-correlation at each lag
  - `fig3_event_study_*` — Average freight behaviour around events
  - `fig4_heatmap.*` — Correlation strength matrix
  - `fig5_timeline.*` — Annotated event timeline

- **`output/report.md`** — Auto-generated analysis summary with key findings, Granger p-values, and top impact assessments

---

## Definition of Done

- [x] Market discovery pipeline built
- [x] CLOB API timeseries fetcher built
- [x] Freight data loader with synthetic fallback
- [x] Event detection (threshold + z-score)
- [x] Cross-correlation analysis at multiple lags
- [x] Granger causality testing
- [x] Impact assessment generator with recommended actions
- [x] 5 publication-quality chart types
- [x] Auto-generated summary report
- [x] 4 Jupyter notebooks for investor walkthrough

**To complete with real data:**
- [ ] Place real BDI/FBX CSVs in `data/freight/` and re-run
- [ ] Verify ≥15 markets discovered
- [ ] Confirm significant correlation for ≥2 pairings
- [ ] Generate final figures for whitepaper

---

## Tech Stack

- Python 3.10+
- `pandas`, `numpy` — data manipulation
- `requests` — API calls with rate limiting and retry
- `statsmodels` — Granger causality (`grangercausalitytests`)
- `scipy` — Pearson correlation with p-values
- `matplotlib`, `seaborn` — publication-quality charts
- `pyyaml` — configuration
- `jupyter` — interactive analysis notebooks

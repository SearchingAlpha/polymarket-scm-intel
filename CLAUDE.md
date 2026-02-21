# CLAUDE.md — Polymarket Supply Chain Intelligence MVP

## Project Overview

Build a Python data pipeline + analysis tool that demonstrates prediction markets (Polymarket) as leading indicators for supply chain disruption, specifically shipping/freight rate impacts.

**Core thesis:** Probability shifts in Polymarket contracts on tariffs, geopolitical conflicts, and trade policy changes precede measurable movements in shipping freight indexes — making prediction markets a viable early warning system for supply chain risk.

**This is an MVP for a startup whitepaper targeting VC investors.** The output must be polished, data-driven, and tell a compelling visual story.

---

## Architecture

```
polymarket-scm-intel/
├── CLAUDE.md
├── README.md
├── requirements.txt
├── config/
│   ├── market_mappings.yaml        # Maps Polymarket contracts → shipping impact categories
│   └── settings.yaml               # API endpoints, thresholds, date ranges
├── src/
│   ├── __init__.py
│   ├── polymarket/
│   │   ├── __init__.py
│   │   ├── client.py               # Gamma API + CLOB API client
│   │   ├── market_discovery.py     # Find supply-chain-relevant markets
│   │   └── timeseries.py           # Fetch and normalize price histories
│   ├── freight/
│   │   ├── __init__.py
│   │   ├── scraper.py              # Fetch BDI and FBX data from public sources
│   │   └── normalize.py            # Align freight data to Polymarket timeseries
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── correlation.py          # Cross-correlation and lead/lag analysis
│   │   ├── events.py               # Event detection (significant probability shifts)
│   │   └── impact_mapper.py        # Map probability shifts to freight rate changes
│   └── visualization/
│       ├── __init__.py
│       └── charts.py               # Publication-quality charts for whitepaper
├── notebooks/
│   ├── 01_market_discovery.ipynb   # Explore available markets
│   ├── 02_data_collection.ipynb    # Pull and inspect all data
│   ├── 03_analysis.ipynb           # Core analysis and findings
│   └── 04_whitepaper_figures.ipynb # Generate final charts
├── data/
│   ├── raw/                        # Raw API responses cached as JSON
│   ├── processed/                  # Cleaned, aligned timeseries as CSV/Parquet
│   └── freight/                    # Downloaded freight index data
└── output/
    ├── figures/                    # Publication-ready charts (PNG + SVG)
    └── report.md                   # Auto-generated summary of findings
```

---

## Phase 1: Data Collection Layer

### 1A: Polymarket Client (`src/polymarket/client.py`)

Build a Python client wrapping two Polymarket APIs. **No API key or authentication needed for read-only access.**

**Gamma API** (market discovery + metadata):
- Base URL: `https://gamma-api.polymarket.com`
- `GET /events` — list events with pagination (`limit`, `offset`, `closed`, `active`, `tag_id`)
- `GET /markets` — list markets, filterable by tag
- `GET /tags` — list all available tags/categories
- Events contain nested `markets[]`, each with `clobTokenIds`, `outcomes`, `outcomePrices`
- Use `active=true&closed=false` for live markets; omit `closed` filter (or use `closed=true`) for historical/resolved markets

**CLOB API** (pricing + timeseries):
- Base URL: `https://clob.polymarket.com`
- `GET /prices-history` — historical price data for a token
  - Params: `market` (tokenID), `interval` (one of: `max`, `1w`, `1d`, `6h`, `1h`), optional `startTs`, `endTs`, `fidelity`
  - Returns: `{"history": [{"t": unix_timestamp, "p": price_as_string}, ...]}`
  - Price = implied probability (0.0 to 1.0)
- `GET /price` — current midpoint price for a token
- `GET /prices` — current prices for multiple tokens

**Implementation notes:**
- Add rate limiting (respect ~100 requests/minute)
- Cache all raw responses to `data/raw/` as JSON with timestamps
- Handle pagination for Gamma API (loop with offset until empty response)
- Parse `outcomePrices` from string format: `"[\"0.65\", \"0.35\"]"` → `[0.65, 0.35]`

### 1B: Market Discovery (`src/polymarket/market_discovery.py`)

Systematically find all supply-chain-relevant markets. Strategy:

1. **Tag-based discovery**: Fetch all tags via `GET /tags`, identify relevant ones (look for tags related to: tariffs, trade, trade war, economy, geopolitics, China, Iran, Middle East, shipping, ports)
2. **Keyword search**: Use `GET /events?title_contains=<keyword>` or filter locally after fetching. Keywords:
   - Tariffs: `tariff`, `tariffs`, `trade war`, `trade deal`, `IEEPA`, `customs`, `import`, `export`
   - Geopolitical: `Iran`, `strike`, `Hormuz`, `Red Sea`, `Houthi`, `conflict`, `war`, `military`, `sanctions`
   - Trade policy: `China`, `EU`, `trade`, `USMCA`, `NAFTA`, `WTO`, `embargo`
   - Labor/ports: `port`, `strike`, `dock`, `ILA`, `longshoremen`, `shipping`
   - Elections (trade-relevant): `election`, `tariff`, `trade policy`
3. **Include BOTH active and closed/resolved markets** — resolved markets with historical data are critical for backtesting the leading indicator thesis
4. Output a curated list with: event_id, market_id, title, category_tag, clobTokenIds, status (active/closed), volume, creation_date

### 1C: Timeseries Collection (`src/polymarket/timeseries.py`)

For each discovered market:
1. Extract `clobTokenIds` (typically two: Yes and No tokens)
2. Fetch price history using `GET /prices-history?market={tokenId}&interval=max`
3. Convert to pandas DataFrame with columns: `timestamp`, `probability`, `market_id`, `market_title`
4. For Yes/No markets, only keep the "Yes" token probability (No = 1 - Yes)
5. Resample to daily frequency (take last observation per day)
6. Save processed timeseries to `data/processed/`

### 1D: Freight Data (`src/freight/scraper.py`)

Collect shipping index data from publicly available sources. Prioritize:

**Baltic Dry Index (BDI):**
- Source: TradingEconomics or MacroMicro (CSV download)
- If programmatic access is blocked, include a manual download step with clear instructions
- Alternative: scrape from `tradingeconomics.com/commodity/baltic` (check if they have an embeddable data endpoint)
- Frequency: daily
- Coverage: going back at least to Jan 2024

**Freightos Baltic Index (FBX):**
- Source: MacroMicro (`en.macromicro.me/series/17502/fbx-global-container-index-weekly`)
- Key lanes to target: FBX01 (China/E.Asia → US West Coast), FBX03 (China/E.Asia → US East Coast), FBX11 (China/E.Asia → North Europe)
- Frequency: weekly (published Fridays)
- Free Freightos Terminal account may provide chart data

**Fallback approach:** If live scraping is impractical, create a `data/freight/` directory with instructions for manual CSV download, and provide sample/synthetic data for development. The pipeline should work with whatever CSVs are placed in that directory.

**Normalization (`src/freight/normalize.py`):**
- Align freight data to daily frequency (forward-fill weekly data)
- Normalize to percentage change from baseline (or z-scores) for comparability
- Output aligned DataFrames with matching date indexes

---

## Phase 2: Analysis Engine

### 2A: Event Detection (`src/analysis/events.py`)

Detect "significant probability shifts" in Polymarket timeseries:

1. **Threshold-based**: Flag when probability changes by >10 percentage points within a rolling window (e.g., 7 days)
2. **Rate-of-change**: Flag when daily rate of change exceeds 2 standard deviations from the mean
3. **Volume-weighted**: If volume data is available, weight signals by trading volume (high-volume moves are more meaningful)

Output: list of `Event(market_id, timestamp, probability_before, probability_after, delta, direction, magnitude)`

### 2B: Correlation Analysis (`src/analysis/correlation.py`)

The core analytical piece. For each Polymarket-to-freight pairing:

1. **Cross-correlation with lag**: Compute Pearson correlation between Polymarket probability changes and freight index changes at various time lags (-30 to +30 days). If Polymarket leads, the peak correlation should be at a positive lag (freight changes follow prediction market moves).
2. **Granger causality test**: Formally test whether Polymarket probability changes Granger-cause freight index changes (use `statsmodels.tsa.stattools.grangercausalitytests`)
3. **Event study methodology**: For each detected "significant probability shift":
   - Define event window (t-5 to t+30 days)
   - Measure freight index behavior in that window
   - Compare to baseline (average freight behavior in non-event periods)
   - Calculate cumulative abnormal returns (CAR) or cumulative abnormal rate changes

**Primary pairings to analyze:**

| Polymarket Signal Category | Freight Outcome | Causal Logic |
|---|---|---|
| US-China tariff rate contracts | FBX01 (China→US West Coast), FBX03 (China→US East Coast) | Tariff escalation → front-loading imports or rerouting → container rate spike |
| Supreme Court tariff ruling | FBX Global, FBX01, FBX03 | Legal uncertainty → importer hedging behavior → rate volatility |
| Iran strike / Hormuz contracts | BDI, tanker rates (if available) | Conflict probability → Strait of Hormuz risk → rerouting around Cape → rate spike |
| Trade deal contracts | FBX (relevant lanes) | Deal probability → anticipated trade flow changes → rate movements |
| Red Sea / Houthi contracts (if found) | FBX11 (China→N.Europe), FBX Global | Attack probability → Suez avoidance → Cape of Good Hope rerouting → rate spike |
| Europe tariff contracts | FBX11 (China→N.Europe) | EU trade disruption → European import pattern changes |

### 2C: Impact Mapper (`src/analysis/impact_mapper.py`)

Translate analytical results into the "intelligence layer" framework:

1. For each significant probability shift detected, generate an **impact assessment**:
   ```python
   {
       "signal": "US-China tariff rate probability shifted from 30% to 65% (>60% tariff rate)",
       "timestamp": "2025-04-01",
       "affected_routes": ["FBX01: China→US West Coast", "FBX03: China→US East Coast"],
       "predicted_impact": "Container rates on Asia-US lanes likely to increase 15-25% within 2-3 weeks",
       "recommended_actions": [
           "Pre-ship inventory before tariff effective date",
           "Explore alternative sourcing from Vietnam/India",
           "Lock in freight contracts at current rates",
           "Increase safety stock for China-sourced components"
       ],
       "confidence": "high",  # based on historical correlation strength
       "historical_precedent": "Similar probability shift in March 2025 preceded 18% FBX01 increase"
   }
   ```

2. Build a simple scoring model: `impact_score = probability_delta * correlation_strength * volume_weight`

---

## Phase 3: Visualization & Output

### 3A: Charts (`src/visualization/charts.py`)

Use `matplotlib` with a professional style. All charts should be whitepaper-ready.

**Required charts:**

1. **Dual-axis overlay chart** (the hero chart): Polymarket probability timeseries on left y-axis, freight index on right y-axis, shared time x-axis. Shaded regions highlighting significant probability shifts. One chart per pairing (tariffs×FBX, Iran×BDI). Use distinct colors and clear legends.

2. **Cross-correlation plot**: Bar chart showing correlation at each lag (-30 to +30 days). Highlight the peak lag with annotation. Confidence bands shown. One per pairing.

3. **Event study chart**: Average freight index behavior around significant probability shift events. Show t-30 to t+30 day window, with t=0 as the event. Include confidence interval bands. Shows the "leading indicator" effect visually.

4. **Market landscape heatmap**: Matrix showing all discovered Polymarket markets (rows) vs supply chain impact categories (columns), with color intensity showing correlation strength. Demonstrates breadth of signal coverage.

5. **Timeline / narrative chart**: Annotated timeline showing key Polymarket probability shifts alongside real-world events and freight rate movements for the full study period. This tells the story.

**Style requirements:**
- Clean, minimal design (no chartjunk)
- Color palette: use a professional scheme (e.g., blues + accent orange)
- Font: sans-serif, minimum 10pt for labels
- Export as both PNG (300 DPI) and SVG
- All charts should have descriptive titles and source annotations
- Figure dimensions: 10x6 inches for standard, 12x5 for timelines

### 3B: Auto-generated Report (`output/report.md`)

Generate a markdown report summarizing:
- Number of supply-chain-relevant markets discovered
- Data coverage period
- Key findings per pairing (correlation strength, optimal lag, Granger causality p-value)
- Top 5 most predictive probability shift events
- Embedded chart references
- Caveats and limitations

---

## Phase 4: Notebook Workflow

The notebooks are the "demo" — what you'd walk an investor through.

### `01_market_discovery.ipynb`
- Run market discovery
- Display table of all found markets with categories, volumes, status
- Show tag distribution and market creation timeline
- Commentary on market coverage breadth

### `02_data_collection.ipynb`
- Fetch all timeseries data
- Visualize raw Polymarket probability curves for key markets
- Visualize freight index data
- Data quality checks (gaps, coverage, alignment)

### `03_analysis.ipynb`
- Run full analysis pipeline
- Display correlation results, Granger causality tests
- Event study results
- Impact assessment examples
- This is the analytical core — should be thorough and well-annotated

### `04_whitepaper_figures.ipynb`
- Generate all publication-quality figures
- Export to `output/figures/`
- Generate the summary report
- Final polished outputs ready for the whitepaper

---

## Technical Requirements

### Python Dependencies (`requirements.txt`)
```
requests>=2.31.0
pandas>=2.0.0
numpy>=1.24.0
matplotlib>=3.7.0
seaborn>=0.12.0
scipy>=1.10.0
statsmodels>=0.14.0
pyyaml>=6.0
jupyter>=1.0.0
tqdm>=4.65.0
```

### Key Constraints
- **No API keys needed** for Polymarket read-only access
- **Respect rate limits**: ~100 requests/minute for Polymarket APIs
- **Cache everything**: All raw API responses saved to `data/raw/` to avoid re-fetching
- **Freight data may require manual download**: Build the pipeline to accept CSVs in `data/freight/` — include clear instructions for where to download them
- **Network access**: The pipeline needs internet access to call Polymarket APIs and (potentially) scrape freight data. If network is unavailable, the pipeline should gracefully fall back to cached/local data.

### Code Quality
- Type hints on all functions
- Docstrings on all public functions and classes
- Logging (use Python `logging` module, not print statements)
- Error handling with retries for API calls (exponential backoff)
- Configuration via YAML files, not hardcoded values

---

## Build Order

Execute in this exact sequence:

1. **`config/settings.yaml`** — API endpoints, rate limits, date ranges, output paths
2. **`config/market_mappings.yaml`** — keyword lists, tag IDs, category definitions
3. **`requirements.txt`** — pin dependencies
4. **`src/polymarket/client.py`** — API client with caching and rate limiting
5. **`src/polymarket/market_discovery.py`** — market finder
6. **`src/polymarket/timeseries.py`** — timeseries fetcher
7. **`src/freight/scraper.py`** — freight data collection
8. **`src/freight/normalize.py`** — data alignment
9. **`src/analysis/events.py`** — event detection
10. **`src/analysis/correlation.py`** — cross-correlation and Granger causality
11. **`src/analysis/impact_mapper.py`** — impact assessment generator
12. **`src/visualization/charts.py`** — all chart types
13. **Notebooks 01-04** — in order
14. **`README.md`** — project documentation with setup and run instructions

---

## Definition of Done

The MVP is complete when:

- [ ] Market discovery finds ≥15 supply-chain-relevant Polymarket contracts
- [ ] Historical probability timeseries retrieved for all discovered markets
- [ ] At least BDI historical data loaded (FBX as stretch goal)
- [ ] Cross-correlation analysis completed for ≥2 market-freight pairings
- [ ] Granger causality test run and p-values reported
- [ ] Event study analysis completed for top probability shift events
- [ ] ≥5 publication-quality charts generated in `output/figures/`
- [ ] Summary report generated in `output/report.md`
- [ ] All 4 notebooks run end-to-end without errors
- [ ] README documents setup and reproduction steps

---

## Important Context

This MVP supports a startup whitepaper targeting VC investors. The analytical rigor matters, but so does the narrative. The charts and findings should clearly demonstrate:

1. **Prediction markets move first** — probability shifts precede freight rate changes
2. **The signal is specific** — different contract categories map to different shipping lanes/indexes
3. **The framework generalizes** — if it works for tariffs×containers and Iran×tankers, it plausibly works for other categories too
4. **There's a product here** — the "impact mapper" output format shows what a real-time intelligence platform would look like

If the data doesn't show a clean leading indicator relationship, that's okay — document it honestly. Investors respect intellectual honesty. Frame weak results as "the signal exists but requires refinement" rather than forcing a narrative. Showing that you've built the infrastructure to systematically test this is itself valuable.
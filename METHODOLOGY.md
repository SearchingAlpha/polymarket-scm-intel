# Methodology: Polymarket as a Supply Chain Leading Indicator

## Audience

This document is written for supply chain practitioners — logistics managers, procurement directors, freight analysts, and risk officers — who want to understand the analytical logic behind this system in detail. It assumes familiarity with freight markets, incoterms, and trade flows, but does not assume prior knowledge of prediction markets or time-series econometrics.

---

## 1. The Core Thesis

The fundamental claim of this system is straightforward:

> **Traders on prediction markets price in geopolitical and trade policy risk before that risk materializes in physical freight markets. Therefore, probability shifts on prediction market contracts are a leading indicator of freight rate movements.**

This is not a novel idea in spirit — commodity traders have long watched political developments to anticipate supply disruptions. What is new is the availability of a liquid, continuously-priced, publicly observable market that converts qualitative geopolitical assessments into quantitative probability estimates, timestamped to the minute.

The causal chains this system focuses on are:

| Prediction Market Event | Mechanism | Freight Outcome |
|---|---|---|
| US-China tariff rate rises | Importers rush to front-load inventory before tariffs take effect → demand surge for ocean freight | Container rates spike on trans-Pacific lanes (FBX01, FBX03) |
| Iran strike / Hormuz conflict | Tankers reroute around Cape of Good Hope, adding 10–14 days of transit → effective capacity drops | Baltic Dry Index rises; tanker rates spike |
| Red Sea / Houthi attacks | Ships avoid Suez Canal, taking the longer Cape route → capacity reduction on Asia-Europe lanes | FBX11 (China → N. Europe) spikes |
| US East Coast port strike | Importers accelerate bookings before strike deadline; rerouting to West Coast | FBX03 (China → US East Coast) spikes; FBX01 rises as overflow |
| EU tariff implementation | Front-loading of goods into Europe ahead of effective date | FBX11 rises on anticipatory demand |

The key observation is that prediction markets capture the *probability* that each of these events occurs, not just their eventual outcome. A move from 30% to 65% probability of a tariff being imposed should be observable in freight rate data before the tariff itself is announced.

---

## 2. What Is Polymarket?

Polymarket is a decentralized prediction market platform where participants trade binary contracts. Each contract resolves to $1.00 if the stated outcome occurs and $0.00 if it does not. At any moment, the price of a contract (which trades between $0.00 and $1.00) equals the market's implied probability of that outcome.

**Example:** A contract titled "Will US tariffs on Chinese goods exceed 60%?" trading at $0.65 means the market collectively assigns a 65% probability to that outcome.

Critically for this analysis:
- **The market is continuous**: prices update in real time as new information arrives.
- **The market is liquid for major geopolitical contracts**: large contracts on tariffs, elections, and conflicts frequently see millions of dollars in trading volume.
- **Historical data is public**: the CLOB (Central Limit Order Book) API provides full price history for all contracts, including resolved ones.
- **No authentication is required** for read-only access to this data.

Polymarket operates two APIs:
- **Gamma API** (`gamma-api.polymarket.com`): market metadata, titles, event categories, current prices.
- **CLOB API** (`clob.polymarket.com`): full historical price timeseries per token, at resolutions down to 1-hour intervals.

---

## 3. Data Collection

### 3.1 Market Discovery

The system must first identify which Polymarket contracts are relevant to supply chain risk. This is a non-trivial problem because there are thousands of active and historical contracts covering sports, politics, entertainment, and many other domains.

Two complementary discovery methods are used:

**Method 1: Tag-based discovery**
Polymarket assigns thematic tags to each market (e.g., "Tariffs", "Geopolitics", "Trade"). The system fetches all available tags via the API and identifies those whose labels match a curated keyword list covering tariffs, geopolitics, trade policy, and labor disruption. It then fetches all markets (both active and closed) for each matched tag.

**Method 2: Event-level keyword scanning**
The Gamma API groups markets into "events" (an event is the overarching real-world situation; it may contain multiple markets asking different questions about that situation). The system fetches all events — both active and resolved — and filters by title keyword match. This catches markets that may not have been correctly tagged but whose titles are clearly supply-chain relevant.

The combined keyword list covers:

| Category | Keywords |
|---|---|
| Tariffs | tariff, trade war, trade deal, IEEPA, customs, import duty, Section 301, Section 232, reciprocal tariff |
| Geopolitical | Iran, Hormuz, Red Sea, Houthi, conflict, war, military, sanctions, strait, blockade |
| Trade policy | China, trade, USMCA, NAFTA, WTO, embargo, EU tariff, trade agreement |
| Labor / ports | port strike, dock, ILA, longshoremen, shipping, labor, dockworkers |
| Elections | election, president, trade policy |

Each discovered market is categorized into one of six supply-chain impact categories (see Section 5). Markets without CLOB token IDs (which are required to fetch price history) are dropped. Duplicates are resolved by keeping the record with the highest trading volume.

**Why include resolved/closed markets?**
Closed markets are critical for backtesting. A closed market titled "Will US tariffs on Chinese goods exceed 60%?" that resolved YES in April 2025 provides a complete probability timeseries that can be aligned against freight rates in the same period, allowing the system to directly test whether the probability trajectory preceded observable freight rate changes.

### 3.2 Probability Timeseries

For each discovered market, the system fetches the full price history from the CLOB API using the `interval=max` parameter, which returns the maximum available history at a sensible resolution.

Each contract has two CLOB tokens: one representing the "Yes" outcome and one representing the "No" outcome. Since `P(No) = 1 - P(Yes)`, only the "Yes" token is retained. This gives a single probability series ranging from 0.0 to 1.0 for each market.

**Resampling to daily frequency:**
Raw CLOB data arrives at irregular intraday intervals. The system resamples to daily frequency by taking the **last observed price per UTC day** and then forward-filling to close any gaps (e.g., weekends or days with no trading). This produces a clean daily timeseries for each market.

**Date range filtering:**
All timeseries are filtered to the study period defined in `config/settings.yaml` (defaulting to January 2024 through the present), ensuring all series share a common time window for comparison.

**Caching:**
All raw API responses are cached to `data/raw/` as JSON files with a 24-hour TTL. Processed timeseries are saved as CSVs to `data/processed/`. This prevents redundant API calls and allows the pipeline to function without live internet access after the initial data pull.

**Parallel fetching:**
Timeseries are fetched using a thread pool (8 workers by default). A shared rate limiter using a token-bucket algorithm ensures the combined request rate stays within the Polymarket API limit of approximately 100 requests per minute. This means wall-clock fetch time scales sub-linearly with the number of markets.

### 3.3 Freight Index Data

The system collects data for the following freight benchmarks:

| Index | Full Name | What It Measures | Frequency |
|---|---|---|---|
| **BDI** | Baltic Dry Index | Composite rate for shipping dry bulk commodities (iron ore, coal, grain) across major routes | Daily |
| **FBX01** | Freightos Baltic Index 01 | Container freight rates, China/East Asia → US West Coast | Weekly |
| **FBX03** | Freightos Baltic Index 03 | Container freight rates, China/East Asia → US East Coast | Weekly |
| **FBX11** | Freightos Baltic Index 11 | Container freight rates, China/East Asia → North Europe | Weekly |
| **FBX_GLOBAL** | FBX Global Container Index | Composite container freight rate across all major global lanes | Weekly |

**Why these indexes?** The BDI is the canonical benchmark for bulk commodity shipping risk and is sensitive to Strait of Hormuz and Cape rerouting scenarios. The FBX series covers the three major container trade lanes most directly affected by US-China tariff policy (trans-Pacific) and Red Sea disruption (Asia-Europe).

**Data acquisition waterfall:**
The system attempts to load each index in priority order:
1. **Manual CSV**: If a file exists in `data/freight/` (e.g., `bdi.csv`), it is used as-is. This is the recommended production path since BDI and FBX data is freely downloadable from TradingEconomics and the Freightos website.
2. **Stooq programmatic download**: For BDI, the system attempts a direct CSV download from the Stooq financial data service.
3. **TradingEconomics API**: A secondary attempt using a guest-level API endpoint.
4. **Synthetic fallback**: If no real data is available, the system generates a statistically plausible synthetic series using a mean-reverting random walk. This is clearly flagged in logs and outputs and is intended for development only.

**Normalization pipeline:**
Raw freight data arrives at different absolute scales (BDI values ~1,000–3,000 points; FBX values in $/FEU). Before analysis, all indexes are processed through:
1. **Daily upsampling**: Weekly FBX data is forward-filled to daily frequency (last known rate is carried forward to each subsequent day).
2. **Date range filter**: Aligned to the same study period as Polymarket data.
3. **Percentage change**: A `pct_change` column is added showing the day-over-day percentage change in the index.
4. **Rolling z-score**: A `zscore` column is added using a 60-day rolling window, representing how many standard deviations the current value is from the rolling mean. This normalizes for level differences across indexes.
5. **Baseline normalization**: A `normalised` column expresses the value as percentage change from the mean of the first 90 days of the study period, enabling visual comparison across indexes with different units.

---

## 4. Event Detection

Before running correlation analysis, the system identifies specific moments when Polymarket contract probabilities moved significantly. These "probability shift events" are the fundamental unit of analysis — they represent moments when the collective market assessment of a supply chain risk changed materially.

Two detection methods are run in parallel:

### 4.1 Threshold-Based Detection

For each market's daily probability series, the system scans every point and asks: *Did probability change by more than 10 percentage points over the preceding 7 days?*

Formally: for each day `t`, compute `delta = P(t) - P(t-7)`. If `|delta| >= 0.10`, flag as an event.

The 10pp threshold is chosen to filter out routine daily noise while capturing genuine shifts in market consensus. The 7-day window is long enough to capture sustained directional moves rather than intraday noise that resolved quickly.

**Deduplication:** Overlapping events are collapsed. Within any 7-day window, only the event with the largest magnitude is kept. This prevents a single sustained move (e.g., probability rising from 30% to 70% over 14 days) from generating a cascade of overlapping events.

### 4.2 Z-Score-Based Detection

For each market, the system computes the daily first difference of probability (i.e., `dP = P(t) - P(t-1)`). It then calculates the z-score of each daily change against the market's own historical distribution:

```
z = (dP - mean(dP)) / std(dP)
```

If `|z| >= 2.0`, the day is flagged as an event. This method is relative — it identifies moves that are large for *that particular market* regardless of absolute magnitude. A contract that normally moves less than 1pp per day would be flagged for a 3pp move, while a highly volatile contract might require 8pp to trigger.

### 4.3 Combined Output

Events detected by both methods are merged and deduplicated (again using a 7-day cooldown). Each event is represented by a `ProbabilityEvent` object capturing:
- The market and timestamp
- Probability before and after the shift
- The absolute magnitude and direction (up/down) of the shift
- The detection method that flagged it
- The z-score (if applicable)

Events are ranked by magnitude for prioritization.

---

## 5. Correlation Analysis

This is the methodological core of the system. Three complementary statistical approaches are used to test whether Polymarket probability changes precede freight rate changes.

### 5.1 Market-to-Freight Pairings

The analysis does not test every market against every freight index. Instead, pairings are defined by causal logic, encoded in `config/market_mappings.yaml`:

| Market Category | Freight Index | Causal Logic |
|---|---|---|
| `tariffs_us_china` | FBX01, FBX03 | Tariff escalation → front-loading of trans-Pacific imports → container rate spike |
| `iran_hormuz` | BDI | Conflict risk → Strait of Hormuz closure probability → rerouting → capacity reduction → rate spike |
| `red_sea_houthi` | FBX11, FBX_GLOBAL | Attack risk → Suez Canal avoidance → Cape rerouting → Asia-Europe rate spike |
| `eu_tariffs` | FBX11 | EU tariff front-loading → Asia-Europe demand surge |
| `us_trade_policy` | FBX_GLOBAL, FBX01 | Policy uncertainty → broad importer hedging behavior → rate volatility |
| `labor_disruption` | FBX03, FBX_GLOBAL | Port strike risk → front-loading before deadline → East Coast rate spike |

This structure means that a market categorized as `tariffs_us_china` will only be tested against FBX01 and FBX03, not against BDI. This reduces spurious correlations and focuses the analysis on economically meaningful relationships.

### 5.2 Cross-Correlation Analysis

Cross-correlation is the primary tool for testing temporal ordering. It measures the Pearson correlation coefficient between two series at different **time lags** and identifies whether a systematic lead-lag relationship exists.

**Stationarity transformation:** Before computing correlations, both series are differenced:
- Polymarket: daily first difference of probability (`dP = P(t) - P(t-1)`)
- Freight: daily percentage change (`d_freight = (F(t) - F(t-1)) / F(t-1) * 100`)

Using changes rather than levels is critical. Level correlations between two trending series are often spurious (a classic econometric pitfall). Changes are mean-reverting and better reflect genuine information flow.

**Lag structure:** The system computes Pearson r at every lag from -30 to +30 days. At lag `k > 0`, the correlation is between `dP(t)` and `d_freight(t+k)` — a positive lag means freight changes follow the prediction market move. At lag `k < 0`, the correlation is between `dP(t-k)` and `d_freight(t)` — a negative lag means freight is leading the prediction market.

**Interpretation:** The "leading indicator" signature this system is looking for is a **positive peak lag with a statistically significant correlation**. For example:
- Peak correlation at lag +7 means freight rates tend to move in the same direction as prediction market probability shifts, approximately 7 days later.
- A negative peak lag would mean freight is moving first, which would suggest freight markets are the smarter signal (a valid null result worth documenting).

Each pair produces a `CrossCorrelationResult` object that includes the full lag profile, the peak correlation and its statistical significance (two-tailed p-value), and a plain-English interpretation.

**Statistical significance:** A p-value of < 0.05 is used as the threshold for significance, with the caveat that multiple testing is being performed across many pairs. Results are reported with exact p-values so readers can apply their own significance standards.

### 5.3 Granger Causality Test

Granger causality is a formal econometric test for temporal precedence. The concept: variable X "Granger-causes" variable Y if lagged values of X contain information that improves forecasts of Y beyond what Y's own history provides.

**Formulation:** The test is a restricted F-test comparing two regression models:
- **Restricted model**: `d_freight(t) = a + b1*d_freight(t-1) + ... + bk*d_freight(t-k) + error`
- **Unrestricted model**: `d_freight(t) = a + b1*d_freight(t-1) + ... + bk*d_freight(t-k) + c1*dP(t-1) + ... + ck*dP(t-k) + error`

If the F-test rejects the null hypothesis (that all `c` coefficients are jointly zero), then Polymarket probability changes Granger-cause freight rate changes — i.e., adding prediction market data to the model provides statistically significant forecasting power.

The test is run at lags 1 through 14 days, and the minimum p-value across all tested lag orders is reported alongside the lag at which it was achieved. The `statsmodels.tsa.stattools.grangercausalitytests` implementation is used.

**Important caveat:** Granger causality is a test of temporal precedence and predictive improvement, not of structural causation. A significant Granger result tells us that prediction market probability adds information about future freight movements, but it does not prove that the prediction market is the source of information. Both series could be responding to the same underlying news flow with different speeds.

### 5.4 Event Study Analysis

The event study methodology, borrowed from academic finance, provides the most intuitive visual representation of the leading indicator thesis. It asks: *On average, what happens to freight rates in the days and weeks following a significant Polymarket probability shift?*

**Procedure:**
1. Identify all probability shift events for a given market above the significance threshold.
2. For each event at time `t=0`, extract the freight index values in a window from `t-5` to `t+30` days.
3. Express each window as a percentage change relative to the freight rate at `t=0` (the day of the event). This normalizes across events with different absolute rate levels.
4. Average the percentage change at each relative day across all events.
5. Compute 95% confidence intervals using the standard error across events at each relative day.

**Key output — Cumulative Abnormal Return (CAR):** The CAR is the average freight rate change over the entire post-event window, measured relative to the baseline (the average day-over-day freight change in non-event periods). A positive CAR following an "up" probability event confirms that freight rates move in the predicted direction after prediction market shifts. A CAR not distinguishable from the baseline would undermine the leading indicator thesis.

**Minimum event count:** At least 2 events are required to run an event study (to compute variance). In practice, the more events available, the tighter the confidence intervals.

---

## 6. Impact Mapping

The impact mapper is the operational intelligence layer that converts statistical findings into structured, actionable assessments. It is designed to demonstrate what a real-time SCM intelligence product would look like.

### 6.1 Input

For each detected probability shift event, the mapper receives:
- The event itself (market, timestamp, magnitude, direction)
- The market's category (from discovery)
- Cross-correlation results for that market (if available)

### 6.2 Confidence Scoring

A confidence level (high / medium / low) is assigned based on two factors:
1. **Event magnitude**: A 35pp shift in probability is treated as a stronger signal than a 10pp shift.
2. **Historical correlation strength**: If the cross-correlation analysis found a strong lead-lag relationship for this market-freight pairing, it increases confidence that the current shift is meaningful.

The composite score formula weights magnitude at 60% and correlation strength at 40%.

### 6.3 Impact Score

A numeric `impact_score` is computed as:

```
impact_score = probability_delta × |correlation_strength| × volume_weight
```

The `volume_weight` is a log-scaled function of the market's trading volume. High-volume markets are given more weight because the signal from a market with $50M in trading volume is more credible than one with $50K. The score is used to rank alerts by priority.

### 6.4 Output Structure

Each assessment is a structured object containing:
- **Signal**: Plain English description of the probability shift (e.g., "US-China tariff probability rose from 30% to 65% (+35pp shift)")
- **Affected routes**: The shipping lanes likely impacted (e.g., "FBX01: China → US West Coast")
- **Predicted impact**: Narrative description of the expected freight rate response and its mechanism
- **Expected range**: Quantified rate change estimate based on historical precedents
- **Recommended actions**: A category-specific playbook tailored to the direction of the probability shift (e.g., pre-ship inventory, lock in forward contracts, explore alternative sourcing)
- **Historical precedent**: A real example from 2024–2025 where a similar probability shift preceded an observed freight rate move
- **Correlation strength and optimal lag**: The statistical grounding from the cross-correlation analysis

### 6.5 Category-Specific Playbooks

The recommended actions are not generic — they differ by risk category and direction:

**Tariff escalation (up signal):**
Pre-ship high-value inventory, accelerate bookings, explore alternative sourcing (Vietnam, India, Mexico), lock in forward freight contracts, increase safety stock buffer to 60–90 days.

**Tariff de-escalation (down signal):**
Defer non-urgent bookings, review inventory positions to avoid excess stock, renegotiate freight rates.

**Hormuz/Iran conflict risk (up signal):**
Assess energy commodity exposure, evaluate war risk insurance increases, identify alternative energy supply outside the Gulf, build strategic inventory of energy-dependent inputs.

**Red Sea / Houthi (up signal):**
Rebook Asia-Europe shipments via Cape of Good Hope routing (add 14 days to lead times), secure space on Cape-routed vessels, communicate delays to European customers.

**Port strike risk (up signal):**
Accelerate East Coast bookings before the deadline, reroute to US West Coast ports as contingency, expedite air freight for time-sensitive SKUs, build 30–60 day buffer stock.

---

## 7. Data Flow Summary

The end-to-end pipeline follows this sequence:

```
Polymarket Gamma API          CLOB API                   Freight Sources
      │                          │                              │
      ▼                          ▼                              ▼
Market Discovery           Price History             BDI / FBX CSVs
(tag + keyword scan)       (per token, max            (manual download
      │                     interval)                  or synthetic)
      ▼                          │                              │
Categorized Market List     Daily Probability              Daily Alignment
(CSV: discovered_markets)   Timeseries (CSV per             (forward-fill,
      │                     market)                      pct change, z-score)
      └──────────────────────────┴──────────────────────────────┘
                                 │
                                 ▼
                        Event Detection
                    (threshold + z-score)
                                 │
                                 ▼
                     Correlation Analysis
                   (cross-correlation × 61 lags,
                    Granger causality, event study)
                                 │
                                 ▼
                        Impact Mapper
                  (confidence score, playbook,
                   affected routes, precedents)
                                 │
                          ┌──────┴──────┐
                          ▼             ▼
                    Notebooks       Output Figures
                    (01→04)        (PNG + SVG)
                                   Report (MD)
```

---

## 8. Freight Index Reference

For readers unfamiliar with the specific indexes used:

**Baltic Dry Index (BDI):** Published daily by the Baltic Exchange in London. It is a composite of rates for four vessel classes (Capesize, Panamax, Supramax, Handysize) across 23 major shipping routes. The BDI measures the cost of shipping raw materials — iron ore, coal, grain, bauxite — and is widely regarded as a leading economic indicator. Because dry bulk shipping cannot be easily redirected in the short term (vessels are specialized and contracts are long), the BDI responds quickly to supply disruptions. A Strait of Hormuz closure or significant Red Sea rerouting reduces effective tanker fleet capacity, raising the BDI as operators compete for available vessels.

**Freightos Baltic Index (FBX):** Published weekly (Fridays) by the Freightos Baltic Exchange. Unlike the BDI, which covers dry bulk, FBX tracks containerized ocean freight rates. The FBX01, FBX03, and FBX11 sub-indices track specific trade lanes and are directly relevant to containerized manufacturing supply chains. FBX rates reflect spot market conditions for 40-foot equivalent units (FEU) and are the most widely cited benchmarks for container logistics cost forecasting.

---

## 9. Limitations and Honest Caveats

**Market liquidity varies widely.** A major contract on US-China tariffs may have $100M+ in trading volume, making it a credible signal. A niche contract on a specific trade agreement may have $50K in volume and represent the views of very few participants. The impact score partially adjusts for this, but thin markets remain noisy signals.

**Causal chains are assumptions.** The pairing of each market category to specific freight indexes is based on economic reasoning, not empirical discovery. While the logic is sound (tariff escalation → trans-Pacific front-loading → FBX01 spike), real-world freight markets are affected by dozens of simultaneous factors. The correlation analysis may identify a genuine leading relationship, or it may identify coincidental correlation that does not replicate.

**Stationarity is assumed but not formally tested.** The differencing transformation (daily changes rather than levels) is designed to achieve stationarity, but no formal unit root test (ADF, KPSS) is run prior to the Granger test. For publication-quality academic work, this would be necessary. For an MVP, the differencing approach is standard practice and its results are directionally reliable.

**The Granger test does not prove causation.** A significant Granger result means prediction market data adds forecast value for freight rates — it does not mean prediction markets *cause* freight rate changes. Both series could be reacting to the same news flow (e.g., a tariff announcement), with prediction markets updating faster than freight markets. This is still useful from a practitioner standpoint, but should not be overstated.

**Weekly FBX data creates alignment challenges.** FBX is published weekly; daily values are forward-filled (the Friday rate is held constant through the following Thursday). This introduces a structural lag of up to 6 days in the freight series relative to daily Polymarket probability data. At short lag values in the cross-correlation, this forward-fill creates artificial serial correlation. Lags of less than 7 days should be interpreted with caution for FBX indexes.

**Synthetic fallback data is not real.** When real freight data is unavailable, the system generates synthetic series using mean-reverting random walks. Any analysis run against synthetic data shows what the pipeline *could* find, not what the data *does* show. All charts and outputs label synthetic data explicitly.

**The study period is short.** The analysis covers January 2024 to present — roughly 25 months. This is sufficient for exploratory work but limits the number of major events available for backtesting. The event study, in particular, requires multiple comparable events to produce statistically reliable estimates. Extending the study period to 2020 or earlier (covering COVID supply chain disruptions) would significantly strengthen the analysis.

---

## 10. How to Read the Outputs

When interpreting results from this system, a supply chain practitioner should look for:

1. **A positive peak lag in cross-correlation**: If the maximum correlation between a prediction market's probability changes and a freight index's rate changes occurs at lag +7 to +21 days, and that correlation is statistically significant (p < 0.05), this is the primary evidence for the leading indicator thesis.

2. **A significant Granger p-value**: p < 0.05 means prediction market data materially improves freight rate forecasts. The lag at which this significance appears tells you the approximate lead time.

3. **A positive CAR in the event study with tight confidence intervals**: If the average freight rate is meaningfully higher 2–3 weeks after a prediction market "up" event compared to non-event periods, and the confidence intervals do not include zero, this provides intuitive evidence of the leading relationship.

4. **Alignment across all three tests**: A finding that shows positive peak lag, significant Granger p-value, and positive post-event CAR is a much stronger result than any single test alone. Convergence across methods compensates for the weaknesses of each individual approach.

5. **Volume as a quality filter**: Prioritize findings from high-volume markets. A significant result from a $10M-volume market is more credible than the same result from a $100K-volume market.

If the data does not show a clean leading relationship, this should be documented honestly. A weak or negative result is still informative — it tells us either that the specific market-freight pairing does not have a predictable relationship, or that the lead time is outside the tested range, or that other confounding factors dominate in the study period.

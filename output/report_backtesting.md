# Polymarket SCM Intel — Backtesting Report

*Historical signal validation: closed/resolved markets only*

*Generated: 2026-02-22 12:55 UTC*

---

## Overview

This report covers **resolved Polymarket contracts** — markets where the outcome is already known. It validates the leading-indicator thesis by comparing probability shifts detected before resolution against observed freight rate movements in the subsequent days.

---

## Pipeline Statistics

- **Markets discovered:** 35912
- **Active markets:** 12889
- **Historical (closed) markets:** 23023
- **Markets with timeseries data:** 5790
- **Significant probability shift events detected:** 3614
- **Market-freight pairings analysed:** 100
- **Statistically significant correlations (p < 0.05):** 96
- **Granger causality tests run:** 5
- **Significant Granger results:** 2
- **Assessments in this report (backtesting):** 2338

---

## Correlation Analysis

### Cross-Correlation Results
- **Will Trump lower tariffs on Canada by July 31?** × FBX11: r=0.505, lag=-11d (Freight leads, significant)
- **Will Trump lower tariffs on Canada by July 31?** × FBX_GLOBAL: r=0.483, lag=-11d (Freight leads, significant)
- **Will Trump lower tariffs on Canada by July 31?** × FBX03: r=0.470, lag=-11d (Freight leads, significant)
- **Will Trump lower tariffs on Canada by July 31?** × FBX01: r=0.453, lag=-25d (Freight leads, significant)
- **Will the U.S. tariff rate on China be between 25% ** × FBX_GLOBAL: r=0.438, lag=-21d (Freight leads, significant)

---

### Granger Causality
- **Will Trump lower tariffs on Canada by December 31?** → FBX01: p=0.0283 at lag=7d (SIGNIFICANT)
- **Will Trump lower tariffs on Canada by December 31?** → FBX11: p=0.0357 at lag=14d (SIGNIFICANT)
- **Will Trump lower tariffs on Canada by December 31?** → FBX03: p=0.0826 at lag=7d (not significant)
- **Will Trump lower tariffs on Canada by December 31?** → BDI: p=0.1018 at lag=1d (not significant)
- **Will Trump lower tariffs on Canada by December 31?** → FBX_GLOBAL: p=0.1853 at lag=7d (not significant)

---

## Backtesting: Historical Signal Validation

*2338 assessments from resolved markets*

These probability shifts occurred on **closed / resolved** Polymarket contracts. The real-world outcomes are known, enabling direct comparison of prediction-market signals against subsequent freight rate movements.

## Supply Chain Intelligence Alerts

*Generated 2026-02-22 12:55 UTC*

Top 10 highest-impact signals:

### Alert #1 — Confidence: HIGH
**Signal:** 521462: probability rose from 2% to 99% (+97pp shift)
**Date:** 2025-05-02
**Category:** tariffs_us_china
**Impact Score:** 0.1958

**Affected Routes:**
- FBX01: China/East Asia → US West Coast
- FBX03: China/East Asia → US East Coast

**Predicted Impact:** Container rates on Asia-US lanes likely to increase as importers front-load shipments ahead of tariff implementation
**Expected Range:** 15–30% rate increase on FBX01/FBX03 within 2–4 weeks

**Recommended Actions:**
- Pre-ship high-value inventory before tariff effective date
- Accelerate ocean freight bookings to secure current rates
- Explore alternative sourcing from Vietnam, India, Mexico
- Lock in forward freight contracts to hedge rate risk
- Increase safety stock for China-sourced components (60–90 day buffer)
- Audit supplier base for tariff exposure by HTS code

**Historical Precedent:** Similar tariff escalation in Jan 2025 preceded 22% FBX01 increase over 3 weeks

---

### Alert #2 — Confidence: HIGH
**Signal:** 1347653: probability rose from 2% to 99% (+97pp shift)
**Date:** 2026-02-19
**Category:** labor_disruption
**Impact Score:** 0.1951

**Affected Routes:**
- FBX03: China/East Asia → US East Coast
- FBX_GLOBAL: Global Container Index

**Predicted Impact:** Port strike risk drives front-loading and rerouting, spiking East Coast rates and air freight demand
**Expected Range:** 25–50% FBX03 rate increase in the weeks before a strike; air freight rates may double

**Recommended Actions:**
- Accelerate East Coast bookings before strike deadline
- Reroute to US West Coast ports as contingency
- Expedite air freight for time-sensitive components
- Build 30–60 day buffer stock for East Coast-dependent supply chains
- Activate port omission routing via West Coast or Gulf ports

**Historical Precedent:** ILA strike threat in Sep 2024 drove significant pre-strike booking surge on East Coast lanes

---

### Alert #3 — Confidence: HIGH
**Signal:** 838568: probability rose from 2% to 99% (+97pp shift)
**Date:** 2026-02-03
**Category:** iran_hormuz
**Impact Score:** 0.1944

**Affected Routes:**
- BDI: Baltic Dry Index (bulk commodities)
- Tanker rates (VLCC, Suezmax)

**Predicted Impact:** Strait of Hormuz conflict risk increases rerouting probability around Cape of Good Hope, adding 10–14 days transit time for energy shipments
**Expected Range:** 10–25% BDI increase within 1–2 weeks of escalation; tanker rates may spike 30–50%

**Recommended Actions:**
- Assess energy commodity exposure to Strait of Hormuz routing
- Evaluate war risk insurance premium increases
- Identify alternative oil/LNG supply sources outside Gulf region
- Review just-in-time energy procurement policies
- Build strategic inventory of energy-dependent inputs

**Historical Precedent:** 2024 Houthi attack escalation drove 35% BDI spike and rerouting of major tanker fleets

---

### Alert #4 — Confidence: HIGH
**Signal:** 521463: probability rose from 3% to 99% (+96pp shift)
**Date:** 2025-05-01
**Category:** tariffs_us_china
**Impact Score:** 0.1932

**Affected Routes:**
- FBX01: China/East Asia → US West Coast
- FBX03: China/East Asia → US East Coast

**Predicted Impact:** Container rates on Asia-US lanes likely to increase as importers front-load shipments ahead of tariff implementation
**Expected Range:** 15–30% rate increase on FBX01/FBX03 within 2–4 weeks

**Recommended Actions:**
- Pre-ship high-value inventory before tariff effective date
- Accelerate ocean freight bookings to secure current rates
- Explore alternative sourcing from Vietnam, India, Mexico
- Lock in forward freight contracts to hedge rate risk
- Increase safety stock for China-sourced components (60–90 day buffer)
- Audit supplier base for tariff exposure by HTS code

**Historical Precedent:** Similar tariff escalation in Jan 2025 preceded 22% FBX01 increase over 3 weeks

---

### Alert #5 — Confidence: HIGH
**Signal:** 536531: probability rose from 3% to 99% (+96pp shift)
**Date:** 2025-05-29
**Category:** tariffs_us_china
**Impact Score:** 0.1929

**Affected Routes:**
- FBX01: China/East Asia → US West Coast
- FBX03: China/East Asia → US East Coast

**Predicted Impact:** Container rates on Asia-US lanes likely to increase as importers front-load shipments ahead of tariff implementation
**Expected Range:** 15–30% rate increase on FBX01/FBX03 within 2–4 weeks

**Recommended Actions:**
- Pre-ship high-value inventory before tariff effective date
- Accelerate ocean freight bookings to secure current rates
- Explore alternative sourcing from Vietnam, India, Mexico
- Lock in forward freight contracts to hedge rate risk
- Increase safety stock for China-sourced components (60–90 day buffer)
- Audit supplier base for tariff exposure by HTS code

**Historical Precedent:** Similar tariff escalation in Jan 2025 preceded 22% FBX01 increase over 3 weeks

---

### Alert #6 — Confidence: HIGH
**Signal:** 1347853: probability rose from 4% to 99% (+95pp shift)
**Date:** 2026-02-20
**Category:** labor_disruption
**Impact Score:** 0.1919

**Affected Routes:**
- FBX03: China/East Asia → US East Coast
- FBX_GLOBAL: Global Container Index

**Predicted Impact:** Port strike risk drives front-loading and rerouting, spiking East Coast rates and air freight demand
**Expected Range:** 25–50% FBX03 rate increase in the weeks before a strike; air freight rates may double

**Recommended Actions:**
- Accelerate East Coast bookings before strike deadline
- Reroute to US West Coast ports as contingency
- Expedite air freight for time-sensitive components
- Build 30–60 day buffer stock for East Coast-dependent supply chains
- Activate port omission routing via West Coast or Gulf ports

**Historical Precedent:** ILA strike threat in Sep 2024 drove significant pre-strike booking surge on East Coast lanes

---

### Alert #7 — Confidence: HIGH
**Signal:** 1183779: probability rose from 3% to 99% (+95pp shift)
**Date:** 2026-02-01
**Category:** labor_disruption
**Impact Score:** 0.1918

**Affected Routes:**
- FBX03: China/East Asia → US East Coast
- FBX_GLOBAL: Global Container Index

**Predicted Impact:** Port strike risk drives front-loading and rerouting, spiking East Coast rates and air freight demand
**Expected Range:** 25–50% FBX03 rate increase in the weeks before a strike; air freight rates may double

**Recommended Actions:**
- Accelerate East Coast bookings before strike deadline
- Reroute to US West Coast ports as contingency
- Expedite air freight for time-sensitive components
- Build 30–60 day buffer stock for East Coast-dependent supply chains
- Activate port omission routing via West Coast or Gulf ports

**Historical Precedent:** ILA strike threat in Sep 2024 drove significant pre-strike booking surge on East Coast lanes

---

### Alert #8 — Confidence: HIGH
**Signal:** 537672: probability rose from 2% to 98% (+95pp shift)
**Date:** 2025-05-22
**Category:** tariffs_us_china
**Impact Score:** 0.1912

**Affected Routes:**
- FBX01: China/East Asia → US West Coast
- FBX03: China/East Asia → US East Coast

**Predicted Impact:** Container rates on Asia-US lanes likely to increase as importers front-load shipments ahead of tariff implementation
**Expected Range:** 15–30% rate increase on FBX01/FBX03 within 2–4 weeks

**Recommended Actions:**
- Pre-ship high-value inventory before tariff effective date
- Accelerate ocean freight bookings to secure current rates
- Explore alternative sourcing from Vietnam, India, Mexico
- Lock in forward freight contracts to hedge rate risk
- Increase safety stock for China-sourced components (60–90 day buffer)
- Audit supplier base for tariff exposure by HTS code

**Historical Precedent:** Similar tariff escalation in Jan 2025 preceded 22% FBX01 increase over 3 weeks

---

### Alert #9 — Confidence: HIGH
**Signal:** 1346988: probability rose from 5% to 99% (+94pp shift)
**Date:** 2026-02-20
**Category:** labor_disruption
**Impact Score:** 0.1898

**Affected Routes:**
- FBX03: China/East Asia → US East Coast
- FBX_GLOBAL: Global Container Index

**Predicted Impact:** Port strike risk drives front-loading and rerouting, spiking East Coast rates and air freight demand
**Expected Range:** 25–50% FBX03 rate increase in the weeks before a strike; air freight rates may double

**Recommended Actions:**
- Accelerate East Coast bookings before strike deadline
- Reroute to US West Coast ports as contingency
- Expedite air freight for time-sensitive components
- Build 30–60 day buffer stock for East Coast-dependent supply chains
- Activate port omission routing via West Coast or Gulf ports

**Historical Precedent:** ILA strike threat in Sep 2024 drove significant pre-strike booking surge on East Coast lanes

---

### Alert #10 — Confidence: HIGH
**Signal:** 585600: probability rose from 3% to 97% (+94pp shift)
**Date:** 2025-09-30
**Category:** red_sea_houthi
**Impact Score:** 0.1885

**Affected Routes:**
- FBX11: China/East Asia → North Europe
- FBX_GLOBAL: Global Container Index

**Predicted Impact:** Elevated Houthi attack probability forces Suez Canal avoidance; Cape routing adds cost and time to Asia-Europe lanes
**Expected Range:** 20–40% FBX11 increase within 1–3 weeks as Suez rerouting accelerates

**Recommended Actions:**
- Rebook Asia-Europe shipments via Cape of Good Hope routing (add 10–14 days)
- Increase Europe-bound inventory lead times by 2–3 weeks
- Secure space on alternative Cape-routed vessels immediately
- Assess war risk surcharge exposure on current bookings
- Communicate supply chain delays to European customers

**Historical Precedent:** Jan 2024 Houthi escalation drove FBX11 from $2,200 to over $7,000 within 6 weeks

---


---

## Figures Generated
- freight_indexes.png
- market_distribution.png
- polymarket_timeseries_sample.png

---

## Caveats and Limitations
1. **Synthetic freight data**: Synthetic data was generated for BDI, FBX01, FBX03, FBX11, FBX_GLOBAL. Final analysis requires real BDI/FBX data.
2. **Correlation ≠ causation**: Statistical relationships documented here are consistent with the leading indicator thesis but require further validation.
3. **Sample size**: Some pairings have limited overlapping observations, reducing statistical power.
4. **Market selection bias**: Markets were selected by keyword matching; some relevant markets may be missed.
5. **Data gaps**: Some Polymarket timeseries have gaps that could affect correlation estimates.

---

*Polymarket SCM Intelligence MVP — Backtesting Report*
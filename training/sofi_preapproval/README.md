# SOFI preapproval model — training

Builds the model behind `POST /preapproval/sofi` (`src/preapproval`). Inputs are the three values SOFI
sends: annual revenue, average credit score and time in business. For each product group it returns
approved/declined and a preapproval amount.

| Group | Code | Target |
|---|---|---|
| Term Loan + MCA | `tlmca` / `term_mca` | the largest lender offer across both products |
| LOC + Revolving MCA | `locr` / `loc_rmca` | the largest lender offer across both products |

"Approved" means the deal received at least one lender offer in the group. Some offers are conditional:
11% of Term Loan/MCA-approved test deals (8.7% of all test deals) later ended Declined, for example
killed in final review.

## What "accurate" means here

With only these three inputs, a single estimate lands within ±20% of the actual largest offer only 22–24%
of the time, whatever the model. We compared four model families and an unconstrained gradient-boosting
baseline, and none was materially better. So the amount is **coverage-calibrated**: when a lender
approves the deal, its largest offer meets or beats our amount about 85% of the time (the q15 head).

## Backtest

The model was fit on deals created 2024-10..2026-06, and the full policy was applied to deals created
2026-07-01..2026-10-18. Nothing was tuned on those months.

**Deals SBG submitted to lenders** (n = 2,619). 2,540 of these are old-funnel deals, scored on the lead's stated revenue:

| | Term Loan + MCA | LOC + Revolving MCA |
|---|---|---|
| Lender approval rate (actual) | 77.9% | 41.1% |
| We approve | 89.3% | 42.7% |
| Precision: of leads we approve, a lender approved | 81.4% | 58.9% |
| Recall: of lender-approved deals, we approved | 93.3% | 61.2% |
| Coverage: lender's largest offer ≥ our amount, where both approved | 83.9% (monthly 81.3–86.0%) | 86.5% (monthly 79.5–90.9%) |
| Median of our amount ÷ actual largest offer | 0.43 | 0.42 |
| Of leads we approve, a lender offered ≥ our amount | 68.3% | 50.9% |
| Approval AUC | 0.65 | 0.73 |

**All leads** (n = 2,915), including the 10% that SBG's own pre-screen declined before any lender saw
them (mostly volume too low, personal bank account, or poor cash flow). These count as declines.
The endpoint scores leads before that pre-screen, so these are the lead-level figures:

| | Term Loan + MCA | LOC + Revolving MCA |
|---|---|---|
| Got an offer (actual) | 70.0% | 36.9% |
| We approve | 84.6% | 39.5% |
| Precision | 77.2% | 57.3% |
| Of leads we approve, a lender offered ≥ our amount | 64.7% | 49.5% |

**SOFI new funnel, scored on the revenue SOFI actually sends** (n = 79, matured new-funnel deals since
2026-10-13). The new funnel is about half of current SOFI traffic. Its stated revenue is a median 0.67× the
lead revenue the model trains on.

| | Term Loan + MCA | LOC + Revolving MCA |
|---|---|---|
| Lender approval rate (actual) | 77.2% | 38.0% |
| We approve | 72.2% | 16.5% |
| Precision | 77.2% | 53.8% |
| Recall | 72.1% | 23.3% |
| Approval AUC | 0.52 (95% CI ~0.34–0.69) | 0.76 |
| Coverage | 88.6% | 85.7% |
| Median of our amount ÷ actual | 0.33 | 0.36 |

On new-funnel leads, Term Loan/MCA declines are currently no better than chance: 22.7% of our declines
had no lender offer, against a base rate of 22.8%. Amounts come out conservative. Several declines come
from the $100k revenue knock-out applied to SOFI's lower revenue figure. The sample is small. Track
new-funnel recall and decline precision monthly, and refit with new-funnel revenue once about 300
outcomes have matured.

## Model

`model.py` — heteroscedastic log-normal amount model plus a monotone logistic approval model, one per
product group. Each input enters through a piecewise-linear basis with non-negative rises, so the approval
probability and every amount are non-decreasing in revenue, score and TIB.

- **Approval:** `p = sigmoid(a0 + f_rev + f_score + f_tib)`.
- **Amount:** `amount_q = exp(mu(x) + c_q · sigma(x))`.
- **Recency:** samples are weighted by recency (9-month half-life).
- **Intercept recalibration:** the approval intercept is recalibrated on the latest 4 months for Term
  Loan/MCA and the latest 1 month for LOC/RMCA. LOC appetite moves month to month: on train-period months,
  the 1-month window cut mean |p − actual| from 4.3 to 2.8 points.
- **Amount quantiles:** the `c_q` are empirical standardized-residual quantiles on the latest 4 months
  (split-conformal).
- **Small windows:** a window widens month by month until it holds at least 200 approvals, and the fit
  stops with an error if it cannot.

`policy.py` — the decision layer, scored only from the exported JSON. `src/preapproval/index.ts` is a
line-for-line port, and jest replays the vectors `policy.py` generates. The two implementations agree to
floating-point precision; V8 and libm `exp`/`log` can differ in the last ulp, which only matters for an
input sitting exactly on a threshold.

| Rule | Setting |
|---|---|
| Knock-outs (decline both products) | revenue < $100k, credit score missing/invalid or < 450, TIB < 0.25 years |
| Approve threshold | Term Loan/MCA p ≥ 0.70; LOC/RMCA p ≥ 0.50 |
| Amount | q15 head, capped at $250k (Term Loan/MCA), $150k (LOC/RMCA) and 15% of annual revenue |
| Rounding | down to $500 (< $10k), $1k (< $50k), $5k (< $250k), $10k above |
| Minimum | decline the product if the rounded amount is below $5k |

**Term Loan/MCA threshold trade-off** (submitted-deal backtest):

| Threshold | Approve | Precision | Recall |
|---|---|---|---|
| 0.5 | 97.5% | 79.2% | 99.1% |
| 0.7 | 89.3% | 81.4% | 93.3% |
| 0.8 | 72.6% | 83.2% | 77.5% |

**LOC/RMCA threshold trade-off** (submitted-deal backtest):

| Threshold | Approve | Precision |
|---|---|---|
| 0.5 | 42.7% | 58.9% |
| 0.6 | 23.2% | 63.6% |
| 0.7 | 7.8% | 70.7% |

## Data (Salesforce)

**Population.** Opportunities with `LeadSource = 'Sofi'` and `Type = 'New'`, created in the last 24 months,
excluding stage 'Submitted to UW' and deals created on or after `--mature-before`. The model trains on
the deals submitted to at least one lender (`No_of_Submissions__c > 0`). Unsubmitted deals are kept
only for the lead-level backtest.

**Export.** Run the SOQL below and merge each query's pages into one CSV with one header row:
`opps.csv`, `offer_agg.csv` and `leads.csv`. Keep the data outside the repo (e.g. `~/sofi_data`),
because it contains credit and revenue data. `training/sofi_preapproval/data/` and `*.pkl` are
gitignored as a safety net.

**Paging.** Salesforce returns 2,000 rows per call, and an aggregate query cannot page at all. Split
every query into `CreatedDate` windows, and check that each window returns `done: true` and a
`totalSize` under 2,000. Use monthly windows for opps and leads, and half-month windows for
`offer_agg` (busy months exceed 2,000 groups).

**`opps.csv`**

```sql
SELECT Id, CreatedDate, StageName, Acct_Annual_Revenue__c, A_Annual_Revenue__c, Annual_True_Revenue__c,
       Average_Score__c, Years_in_Business_at_Funding__c, TIB_at_Opportunity_Creation__c, No_of_Submissions__c
FROM Opportunity
WHERE LeadSource = 'Sofi' AND Type = 'New' AND CreatedDate >= <start> AND CreatedDate < <end>
```

**`offer_agg.csv`** (columns `opp, prod, mx, mn, n, subs`). Credibly's "overview" integration writes
its WCL (working-capital loan) offers as `Line of Credit` copies of its MCA offer (since 2026-10-09), so
they are excluded:

```sql
SELECT CMBCG__Opportunity__c opp, Product__c prod, MAX(Funding_Amount__c) mx, MIN(Funding_Amount__c) mn,
       COUNT(Id) n, COUNT_DISTINCT(CMBCG__Submission__c) subs
FROM CMBCG__Offer__c
WHERE CMBCG__Opportunity__r.LeadSource = 'Sofi' AND CMBCG__Opportunity__r.Type = 'New'
  AND CMBCG__Opportunity__r.CreatedDate >= <start> AND CMBCG__Opportunity__r.CreatedDate < <end>
  AND (NOT Offer_ID__c LIKE '%-overview-WCL-%')
GROUP BY CMBCG__Opportunity__c, Product__c
```

**`leads.csv`**. `AnnualRevenue` is the model's revenue input. The Account copy on the Opportunity is
edited during underwriting on about 5% of deals, often toward bank-statement revenue, so it is only a
fallback:

```sql
SELECT Id, CreatedDate, ConvertedOpportunityId, Sofi_New_Funnel__c, AnnualRevenue
FROM Lead
WHERE IsConverted = true AND ConvertedOpportunity.LeadSource = 'Sofi' AND ConvertedOpportunity.Type = 'New'
  AND ConvertedOpportunity.CreatedDate >= <start> AND ConvertedOpportunity.CreatedDate < <end>
```

**What `build_dataset.py` checks:**
- required columns and unique Ids
- coerces numbers and reports values it could not parse
- reports unexpected `Product__c` values and fails if a product group has no approvals
- excludes implausible offer amounts from the amount model (under $1k, or over max($5M, 3× revenue)), while keeping the approval

`Largest_Approval__c` equals the max offer across all products, checked on all 16,094 approved deals.

## Retrain (monthly)

```bash
pip install pandas numpy scipy
cd training/sofi_preapproval
python3 build_dataset.py --data-dir ~/sofi_data --test-start <first day, 4 months back> --mature-before <today minus 3 days>
python3 train.py --data-dir ~/sofi_data --out ../../src/preapproval/model.json \
    --vectors-out ../../src/preapproval/__tests__/model-vectors.json
cd ../.. && npm test   # TypeScript parity, monotonicity, input and route tests
```

- **`--mature-before`** excludes the newest deals, whose outcomes are still pending. 96% of first offers
  arrive within 3 days, but deals already holding offers can still collect larger ones for a few weeks.
  A 14-day lag is safer when there is enough history.
- **`--test-start`** sets the out-of-time backtest window, so rebuild the dataset whenever it changes.
  Keep it about four months back so the backtest reflects current lenders.
- **`model_version`** ends with a hash of the exported coefficients and policy, so every distinct model
  has a distinct version.
- **Outputs:** `train.py` prints the backtest for all three populations above, the calibration windows
  and the model version. It writes `backtest.json` and `rate_card.csv` (a readable revenue × score × TIB
  grid for sales) to the data directory.

## Known limits and what to monitor

**Revenue input.** The model trains on the revenue stated on the converted lead. SOFI's original value
(`A_Annual_Revenue__c`) was coarse bands before the new funnel (Oct 2026): about 43% of deals were
exactly $1.8M (46% between Feb 2025 and Sep 2026). The new funnel sends granular monthly revenue × 12.
See the new-funnel table above for what that does to decisions.

**Credit score.** The new funnel sends a real score that equals our `Average_Score__c` on 97.6% of deals.
The old funnel sent only a band (575/700/800).

**TIB.** About 40% of deals carry SOFI's "5+ years" value (~5.1 years), so TIB adds little beyond revenue
and score.

**LOC label regime.** From Sep 2026, Byzfunder's API attaches a "ByzFlex" Revolving MCA offer next to
most of its MCA offers. LOC/RMCA approval rose from about 35% (Jul) to about 45% (Sep–Oct), driven by
these offers. LOC-only approval stayed at 34–39%. They are real, fundable offers, so they count, and
LOC/RMCA calibration uses the latest month.

**Lender appetite.** Term Loan/MCA approval fell from about 83% (H1 2026) to about 78% (Jul–Oct 2026). Recalibrate
monthly.

**Monthly alerts:**
- any product's monthly coverage leaves 80–90%
- mean predicted approval differs from actual by more than 5 points
- new-funnel recall drops
- a lender's per-product offer volume jumps (a new integration mapping, like the Credibly WCL case)

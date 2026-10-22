# SOFI preapproval model — training

Builds the model behind `POST /preapproval/sofi` (`src/preapproval`). Inputs are the three values SOFI
sends: annual revenue, average credit score, and time in business. For each product group it returns
approved/declined and a preapproval amount:

- **Term Loan + MCA** (`tlmca` / `term_mca`): target is the largest lender offer across both products
- **LOC + Revolving MCA** (`locr` / `loc_rmca`): target is the largest lender offer across both products

## What "accurate" means here

With only these three inputs, a single estimate of the largest lender approval lands within ±20% of
the actual offer just ~23% of the time, whatever the model. The full analysis compared four model
families against an unconstrained gradient-boosting baseline and found no material accuracy
difference. So the amount is a **coverage-calibrated** preapproval: when a lender approves the deal,
its largest approval meets or beats our amount ~85% of the time (the q15 head).

Out-of-time backtest: fit on deals created 2024-10..2026-06, full policy applied to the 2,619 deals
created 2026-07-01..2026-10-18 (nothing tuned on them).

| | Term Loan + MCA | LOC + Revolving MCA |
|---|---|---|
| Lender approval rate (actual) | 77.9% | 41.3% |
| We approve | 89.4% | 43.6% |
| Precision (a lender approved when we said approved) | 81.6% | 58.8% |
| Coverage (lender's largest offer ≥ our amount, given approval) | 83.7% (monthly 81.6–85.7%) | 87.1% (monthly 82.6–90.5%) |
| Median of our amount ÷ actual largest offer | 0.43 | 0.41 |
| Approved by us AND lender offered ≥ our amount | 68.3% | 51.2% |

## Model

`model.py` — heteroscedastic log-normal amount model plus a monotone logistic approval model, one per
product group. Each input enters through a piecewise-linear basis with non-negative rises, so the
approval probability and every amount are non-decreasing in revenue, score and TIB.

- **Approval:** `p = sigmoid(a0 + f_rev + f_score + f_tib)`.
- **Amount:** `amount_q = exp(mu(x) + c_q · sigma(x))`. The `c_q` are empirical standardized-residual
  quantiles on the latest 4 months (split-conformal).
- **Recency:** samples are recency weighted (9-month half-life).
- **Monthly recalibration:** the approval intercept and the `c_q` are recalibrated every month on the
  latest 4 mature months, so the model tracks lender appetite.

`policy.py` — the decision layer, scored only from the exported JSON. `src/preapproval/index.ts` is a
line-for-line port, and jest replays the vectors it generates.

| Rule | Setting |
|---|---|
| Knock-outs (decline both products) | revenue < $100k, score missing/invalid or < 450, TIB < 0.25 years |
| Approve threshold | Term Loan/MCA p ≥ 0.70; LOC/RMCA p ≥ 0.50 |
| Amount | q15 head, capped at $250k (Term Loan/MCA), $150k (LOC/RMCA) and 15% of annual revenue |
| Rounding | down to $500 (< $10k), $1k (< $50k), $5k (< $250k), $10k above |
| Minimum | decline the product if the rounded amount is below $5k |

**Term Loan/MCA threshold trade-off** (backtest):

| Threshold | Approve | Precision | Recall |
|---|---|---|---|
| 0.5 | 97% | 79% | 99% |
| 0.7 | 89% | 82% | 94% |
| 0.8 | 73% | 83% | 78% |

**LOC/RMCA threshold trade-off** (backtest):

| Threshold | Approve | Precision |
|---|---|---|
| 0.5 | 44% | 59% |
| 0.6 | 24% | 63% |
| 0.7 | 8% | 70% |

## Data (Salesforce)

Population: Opportunities with `LeadSource = 'Sofi'`, `Type = 'New'`, created in the last 24 months, that
were submitted to at least one lender (`No_of_Submissions__c > 0`) and have a final outcome.

Export these with SOQL (Salesforce returns 2,000 rows per page, so page by `CreatedDate` window), and save
them as CSV in a data directory. Keep the data out of git, because it contains credit and revenue data.

**`opps.csv`**

```sql
SELECT Id, CreatedDate, CloseDate, StageName, Acct_Annual_Revenue__c, A_Annual_Revenue__c,
       Annual_True_Revenue__c, Average_Score__c, Years_in_Business_at_Funding__c,
       TIB_at_Opportunity_Creation__c, No_of_Submissions__c
FROM Opportunity
WHERE LeadSource = 'Sofi' AND Type = 'New' AND CreatedDate >= <start> AND CreatedDate < <end>
```

**`offer_agg.csv`** (columns `opp, prod, mx, mn, n, subs`)

```sql
SELECT CMBCG__Opportunity__c opp, Product__c prod, MAX(Funding_Amount__c) mx, MIN(Funding_Amount__c) mn,
       COUNT(Id) n, COUNT_DISTINCT(CMBCG__Submission__c) subs
FROM CMBCG__Offer__c
WHERE CMBCG__Opportunity__r.LeadSource = 'Sofi' AND CMBCG__Opportunity__r.Type = 'New'
  AND CMBCG__Opportunity__r.CreatedDate >= <start> AND CMBCG__Opportunity__r.CreatedDate < <end>
GROUP BY CMBCG__Opportunity__c, Product__c
```

**`leads.csv`**

```sql
SELECT Id, CreatedDate, ConvertedOpportunityId, Sofi_New_Funnel__c
FROM Lead
WHERE IsConverted = true AND ConvertedOpportunity.LeadSource = 'Sofi' AND ConvertedOpportunity.Type = 'New'
  AND ConvertedOpportunity.CreatedDate >= <start> AND ConvertedOpportunity.CreatedDate < <end>
```

`Largest_Approval__c` on the Opportunity equals the max offer across all products, which was checked
on all 16,094 approved deals. The per-product split needs the offer aggregate.

## Retrain (monthly)

```bash
pip install pandas numpy scipy
python3 build_dataset.py --data-dir ./data --mature-before <today minus 3 days>
python3 train.py --data-dir ./data --out ../../src/preapproval/model.json \
    --vectors-out ../../src/preapproval/__tests__/model-vectors.json
npm test   # from the repo root: TypeScript parity, monotonicity, edge cases
```

- **`--mature-before`:** excludes the most recent deals, whose outcomes are still pending.
- **`--test-start`:** defaults to 2026-07-01. Move it forward each quarter so the backtest stays out-of-time.
- **Outputs:** `train.py` prints the backtest and writes `backtest.json` and `rate_card.csv` (a readable
  revenue × score × TIB grid for sales) to the data directory.

## Known limits and what to monitor

- **Revenue input.** The model trains on the stated annual revenue on the lead/account. Before SOFI's
  new funnel (Oct 2026), the revenue SOFI originally sent (`A_Annual_Revenue__c`) was coarse bands:
  46% of deals were exactly $1.8M. The new funnel sends granular monthly revenue × 12, which runs about
  1/3 below the lead revenue on the first 79 matured deals. Preapprovals for new-funnel leads are
  therefore conservative: we approve fewer and amounts are lower.
  Refit once ~300+ new-funnel outcomes have matured.
- **Credit score.** The new funnel sends a real score that equals our `Average_Score__c` on 97.6% of
  deals. The old funnel sent only a band (575/700/800).
- **TIB.** 40% of historical deals carry SOFI's "5+ years" value (~5.1 years), so TIB adds little signal
  beyond revenue and score.
- **Drift.** Lender appetite tightened in Jul 2026. Recalibrate monthly, and alert if monthly coverage
  leaves 80–90% or mean predicted approval differs from actual by more than 5 points.

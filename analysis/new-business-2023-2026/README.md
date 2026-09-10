# SBG New Business Story, 2023–2026

Plain-language analysis of how SBG Funding's NEW business (renewals excluded) changed from
January 2023 through August 2026, using calendar years and monthly averages.

* `out/new_business_story.html` – the report (also published as a Claude artifact).
* `out/metrics.json` – every computed metric behind the report.
* `scripts/` – Python used to build the numbers, run in this order:
  1. `prep.py` – turns the raw Salesforce pulls (aggregate SOQL results and opportunity records)
     into tidy TSV tables under `data/`.
  2. `load.py` – loaders shared by the metric scripts (year windows, opportunity derivations).
  3. `metrics.py`, `metrics2.py`, `metrics3.py` – compute funnel, per-rep, manager, segment,
     cycle, seasonality, lender and win-back metrics into `out/metrics.json`.
  4. `report.py` – renders the HTML story with inline SVG charts from `metrics.json`.
* `tools/` – jq/shell helpers used to convert SOQL JSON results to TSV.
* `data/` – the small aggregate tables (distribution-log, lead and submission roll-ups).
  Raw opportunity record pulls (~300 MB) are not committed.

## Method notes

* Leads assigned come from Distribution Engine logs (`n2de__Distribution_log__c`), counting each
  lead once per calendar month and excluding the Renewals distribution team.
* 2026 = January–August monthly averages; September 2026 (partial) is excluded.
* Manager attribution uses the Distribution Engine's Assigned User Manager stamp (from Nov 2024):
  each rep-month is credited to the manager who received most of that rep's leads that month.
* Distribution Teams 1–7 are lead tiers (the same reps belong to every tier), not manager teams.
* Approval bands use Largest Approval because Max Approval is empty on every record.

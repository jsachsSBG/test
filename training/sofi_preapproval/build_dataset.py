"""Build the SOFI preapproval modeling table from Salesforce exports.

Inputs (CSV exports of the SOQL in README.md, all in --data-dir):
  opps.csv       one row per SOFI New Opportunity
  offer_agg.csv  max/min offer amount and counts per (Opportunity, Product)
  leads.csv      the converted SOFI Lead behind each Opportunity

Output: <data-dir>/model_data.pkl, one row per opportunity that was submitted to at least
one lender and has a final outcome.

    python3 build_dataset.py --data-dir ./data --test-start 2026-07-01 --mature-before 2026-10-19
"""
import argparse
import os

import numpy as np
import pandas as pd

GROUPS = {"Term Loan": "tlmca", "MCA": "tlmca", "Line of Credit": "locr", "Revolving MCA": "locr"}
PRODUCTS = {"Term Loan": "tl", "MCA": "mca", "Line of Credit": "loc", "Revolving MCA": "rmca"}


def _offer_pivot(offers: pd.DataFrame, key: str) -> pd.DataFrame:
    g = offers.dropna(subset=[key]).groupby(["opp", key]).agg(mx=("mx", "max"), n=("n", "sum")).reset_index()
    w = g.pivot(index="opp", columns=key)
    w.columns = [f"{k}_{c}" for c, k in w.columns]
    return w


def build(data_dir: str, test_start: str, mature_before: str) -> pd.DataFrame:
    opps = pd.read_csv(os.path.join(data_dir, "opps.csv"), low_memory=False).set_index("Id")
    offers = pd.read_csv(os.path.join(data_dir, "offer_agg.csv"))
    leads = pd.read_csv(os.path.join(data_dir, "leads.csv"), low_memory=False)

    offers["grp"] = offers["prod"].map(GROUPS)
    offers["p"] = offers["prod"].map(PRODUCTS)
    d = opps.join([_offer_pivot(offers, "grp"), _offer_pivot(offers, "p")])

    leads = leads.sort_values("CreatedDate").drop_duplicates("ConvertedOpportunityId", keep="last")
    d = d.join(leads.set_index("ConvertedOpportunityId")[["Sofi_New_Funnel__c"]].rename(columns={"Sofi_New_Funnel__c": "lead_new_funnel"}))

    created = pd.to_datetime(d["CreatedDate"], utc=True)
    # Only deals that reached lenders and have a final outcome
    keep = (d["No_of_Submissions__c"].fillna(0) > 0) & (d["StageName"] != "Submitted to UW") & (created < pd.Timestamp(mature_before, tz="UTC"))
    d, created = d[keep], created[keep]

    out = pd.DataFrame(index=d.index)
    out["created"] = created.dt.tz_convert(None)
    out["ym"] = created.dt.strftime("%Y-%m")
    out["split"] = np.where(created < pd.Timestamp(test_start, tz="UTC"), "train", "test")
    out["new_funnel"] = d["lead_new_funnel"].astype(str).str.lower().eq("true")
    # Stated annual revenue (Lead.AnnualRevenue -> Opportunity.Acct_Annual_Revenue__c) is the model input.
    # A_Annual_Revenue__c is what SOFI originally sent: banded before the Oct-2026 funnel, granular after.
    out["rev"] = d["Acct_Annual_Revenue__c"]
    out["rev_sofi_orig"] = d["A_Annual_Revenue__c"]
    out["rev_true"] = d["Annual_True_Revenue__c"]
    out["score"] = d["Average_Score__c"]
    # TIB at funding exists only on funded deals; TIB at opportunity creation differs by days
    out["tib"] = d["Years_in_Business_at_Funding__c"].fillna(d["TIB_at_Opportunity_Creation__c"])
    out["stage"] = d["StageName"]
    for g in ["tlmca", "locr", "tl", "mca", "loc", "rmca"]:
        amt = d.get(f"{g}_mx", pd.Series(np.nan, index=d.index))
        approved = amt.fillna(0) > 0
        out[f"y_{g}_approved"] = approved.astype(int)
        out[f"y_{g}_amt"] = amt.where(approved)
    # Any lender offer, including products outside the two groups (SBA, HELOC, equipment)
    any_mx = offers.groupby("opp")["mx"].max().reindex(out.index)
    out["y_any_approved"] = (any_mx.fillna(0) > 0).astype(int)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--test-start", default="2026-07-01", help="first created date of the out-of-time test split")
    ap.add_argument("--mature-before", required=True, help="exclude deals created on/after this date (outcomes still pending)")
    a = ap.parse_args()
    out = build(a.data_dir, a.test_start, a.mature_before)
    out.to_pickle(os.path.join(a.data_dir, "model_data.pkl"))
    print(out.shape, out["split"].value_counts().to_dict())


if __name__ == "__main__":
    main()

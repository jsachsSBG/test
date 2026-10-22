"""Build the SOFI preapproval modeling table from Salesforce exports.

Inputs (CSV exports of the SOQL in README.md, all in --data-dir):
  opps.csv       one row per SOFI New Opportunity
  offer_agg.csv  max/min offer amount and counts per (Opportunity, Product)
  leads.csv      the converted SOFI Lead behind each Opportunity

Output: <data-dir>/model_data.pkl, one row per mature opportunity. `submitted` marks deals that reached
at least one lender; the model trains on those, and the unsubmitted ones (SBG pre-screen declines) are
kept with no offers so the backtest can also report lead-level metrics.

    python3 build_dataset.py --data-dir ~/sofi_data --test-start 2026-07-01 --mature-before 2026-10-19
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

GROUPS = {"Term Loan": "tlmca", "MCA": "tlmca", "Line of Credit": "locr", "Revolving MCA": "locr"}
PRODUCTS = {"Term Loan": "tl", "MCA": "mca", "Line of Credit": "loc", "Revolving MCA": "rmca"}
# Lender products outside both groups; anything not here or in GROUPS is reported as unexpected
OUT_OF_SCOPE_PRODUCTS = {"HELOC", "SBA", "Equipment Financing", "Real Estate", "ABL", "Cannabis", "Factoring"}
# Offer amounts outside [MIN_OFFER, max(MAX_OFFER, MAX_OFFER_TO_REVENUE x revenue)] are entry errors
# ($K-unit typos, doubled digits); the deal still counts as approved but its amount is not used
MIN_OFFER, MAX_OFFER, MAX_OFFER_TO_REVENUE = 1_000, 5_000_000, 3.0

REQUIRED = {
    "opps.csv": ["Id", "CreatedDate", "StageName", "Acct_Annual_Revenue__c", "A_Annual_Revenue__c", "Annual_True_Revenue__c",
                 "Average_Score__c", "Years_in_Business_at_Funding__c", "TIB_at_Opportunity_Creation__c", "No_of_Submissions__c"],
    "offer_agg.csv": ["opp", "prod", "mx", "n"],
    "leads.csv": ["CreatedDate", "ConvertedOpportunityId", "Sofi_New_Funnel__c", "AnnualRevenue"],
}
NUMERIC = {
    "opps.csv": ["Acct_Annual_Revenue__c", "A_Annual_Revenue__c", "Annual_True_Revenue__c", "Average_Score__c",
                 "Years_in_Business_at_Funding__c", "TIB_at_Opportunity_Creation__c", "No_of_Submissions__c"],
    "offer_agg.csv": ["mx", "n"],
    "leads.csv": ["AnnualRevenue"],
}


def fail(msg: str) -> None:
    sys.exit(f"build_dataset: {msg}")


def _read(data_dir: str, name: str) -> pd.DataFrame:
    df = pd.read_csv(os.path.join(data_dir, name), low_memory=False)
    missing = [c for c in REQUIRED[name] if c not in df.columns]
    if missing:
        fail(f"{name} is missing columns {missing}")
    for c in NUMERIC[name]:
        before = df[c].notna().sum()
        df[c] = pd.to_numeric(df[c], errors="coerce")
        lost = before - df[c].notna().sum()
        if lost:
            print(f"warning: {name}.{c}: {lost} non-numeric values set to empty")
    return df


def _as_bool(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def _offer_pivot(offers: pd.DataFrame, key: str) -> pd.DataFrame:
    g = offers.dropna(subset=[key]).groupby(["opp", key]).agg(mx=("mx", "max"), n=("n", "sum")).reset_index()
    w = g.pivot(index="opp", columns=key)
    w.columns = [f"{k}_{c}" for c, k in w.columns]
    return w


def build(data_dir: str, test_start: str, mature_before: str) -> pd.DataFrame:
    if pd.Timestamp(test_start) >= pd.Timestamp(mature_before):
        fail("--test-start must be before --mature-before, or the test split is empty")
    opps = _read(data_dir, "opps.csv")
    offers = _read(data_dir, "offer_agg.csv")
    leads = _read(data_dir, "leads.csv")

    dup = opps["Id"].duplicated().sum()
    if dup:
        fail(f"opps.csv has {dup} duplicate Ids (overlapping export windows?)")
    if offers.duplicated(["opp", "prod"]).sum():
        fail("offer_agg.csv has duplicate (opp, prod) rows (overlapping export windows?)")
    opps = opps.set_index("Id")

    counts = offers.groupby(offers["prod"].fillna("(none)"))["n"].sum()
    unexpected = {p: int(n) for p, n in counts.items() if p not in GROUPS and p not in OUT_OF_SCOPE_PRODUCTS and p != "(none)"}
    if unexpected:
        print(f"warning: unexpected Product__c values (ignored): {unexpected}")
    print("offers by product:", {p: int(n) for p, n in counts.items()})

    offers["grp"] = offers["prod"].map(GROUPS)
    offers["p"] = offers["prod"].map(PRODUCTS)
    d = opps.join([_offer_pivot(offers, "grp"), _offer_pivot(offers, "p")])

    leads = leads.sort_values("CreatedDate").drop_duplicates("ConvertedOpportunityId", keep="last").set_index("ConvertedOpportunityId")
    d = d.join(leads[["Sofi_New_Funnel__c", "AnnualRevenue"]].rename(columns={"Sofi_New_Funnel__c": "lead_new_funnel", "AnnualRevenue": "lead_revenue"}))

    created = pd.to_datetime(d["CreatedDate"], utc=True)
    keep = (d["StageName"] != "Submitted to UW") & (created < pd.Timestamp(mature_before, tz="UTC"))
    d, created = d[keep], created[keep]

    out = pd.DataFrame(index=d.index)
    out["created"] = created.dt.tz_convert(None)
    out["ym"] = created.dt.strftime("%Y-%m")
    out["split"] = np.where(created < pd.Timestamp(test_start, tz="UTC"), "train", "test")
    out["submitted"] = d["No_of_Submissions__c"].fillna(0) > 0
    out["new_funnel"] = _as_bool(d["lead_new_funnel"])
    # Model input: the revenue stated on the converted lead. The Account copy (Acct_Annual_Revenue__c) is
    # edited during underwriting on ~5% of deals, often toward bank-statement revenue, so it is only a fallback.
    out["rev"] = d["lead_revenue"].fillna(d["Acct_Annual_Revenue__c"])
    out["rev_account"] = d["Acct_Annual_Revenue__c"]
    # A_Annual_Revenue__c is what SOFI originally sent: banded before the Oct-2026 funnel, granular after
    out["rev_sofi_orig"] = d["A_Annual_Revenue__c"]
    out["rev_true"] = d["Annual_True_Revenue__c"]
    out["score"] = d["Average_Score__c"]
    # TIB at funding exists only on funded deals; TIB at opportunity creation differs by days
    out["tib"] = d["Years_in_Business_at_Funding__c"].fillna(d["TIB_at_Opportunity_Creation__c"])
    out["stage"] = d["StageName"]

    cap = np.maximum(MAX_OFFER, MAX_OFFER_TO_REVENUE * out["rev"].fillna(0))
    for g in ["tlmca", "locr", "tl", "mca", "loc", "rmca"]:
        amt = d.get(f"{g}_mx", pd.Series(np.nan, index=d.index))
        approved = amt.fillna(0) > 0
        valid = approved & (amt >= MIN_OFFER) & (amt <= cap)
        out[f"y_{g}_approved"] = approved.astype(int)
        out[f"y_{g}_amt"] = amt.where(valid)
        bad = int((approved & ~valid).sum())
        if bad and g in ("tlmca", "locr"):
            print(f"{g}: {bad} approved deals have an implausible largest offer; amount excluded, approval kept")
    any_mx = offers.groupby("opp")["mx"].max().reindex(out.index)
    out["y_any_approved"] = (any_mx.fillna(0) > 0).astype(int)

    sub = out[out["submitted"]]
    for g in ("tlmca", "locr"):
        if sub[f"y_{g}_approved"].sum() == 0:
            fail(f"no {g} approvals among submitted deals - check the product mapping and the offer export")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--test-start", default="2026-07-01",
                    help="first created date of the out-of-time test split (rebuild the dataset after changing it)")
    ap.add_argument("--mature-before", required=True, help="exclude deals created on/after this date (outcomes still pending)")
    a = ap.parse_args()
    out = build(a.data_dir, a.test_start, a.mature_before)
    out.to_pickle(os.path.join(a.data_dir, "model_data.pkl"))
    s = out[out["submitted"]]
    print(f"{len(out)} mature deals, {len(s)} submitted to lenders {s['split'].value_counts().to_dict()}, "
          f"{int(out['new_funnel'].sum())} from SOFI's new funnel")


if __name__ == "__main__":
    main()

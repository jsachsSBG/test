"""Manager attribution by owner-month (from distribution logs) + final headline table."""
import sys, json, os
import pandas as pd, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from load import *
R = json.load(open(f"{S}/out/metrics.json"))
def r(x, n=3):
    try: return None if x is None or pd.isna(x) else round(float(x), n)
    except Exception: return None
users = load_users(); uprof = users.set_index("Id").Profile.to_dict(); uname = users.set_index("Id").Name.to_dict()
opps = load_opps(); o = opps[in_window(opps.cym)].copy()
o["owner_profile"] = o.OwnerId.map(uprof).fillna("?"); o["is_ae"] = o.owner_profile.isin(["Sales Rep","Sales Rep - Manager"])
dl = load_dir("dl")
mr = dl["dl_mgr_rep_month"]; mr["ym"] = num(mr.yr).astype(int)*100+num(mr.mo).astype(int); mr = mr[in_window(mr.ym)]
for c in ["logs","uleads","uleads_conv"]: mr[c] = num(mr[c]).fillna(0)
# owner-month -> manager with most unique leads
top = mr.sort_values("uleads", ascending=False).drop_duplicates(["ym","owner_id"])[["ym","owner_id","manager","uleads","uleads_conv"]]
excl_mgr = ["Alex Miller","Trevor Eastin","Sarah Martin"]
top = top[~top.manager.isin(excl_mgr)]
key = top.set_index(["ym","owner_id"]).manager
o["mgr_month"] = pd.Series(list(zip(o.cym, o.OwnerId))).map(key).values
oo = o[o.mgr_month.notna() & (o.cym >= 202411)].copy()
# per manager-year: opps outcomes
g = oo.groupby(["mgr_month", oo.cym//100]).agg(opps=("Id","size"), approved=("approved","sum"), funded=("funded","sum"),
     funded_amt=("funded_amt", lambda s: s[oo.loc[s.index,"funded"]].sum()), sbg_rev=("sbg_rev", lambda s: s[oo.loc[s.index,"funded"]].sum()),
     med_fico=("fico","median"), med_acct_rev=("acct_rev","median")).reset_index().rename(columns={"mgr_month":"manager","cym":"yr"})
# rep-months and leads from the DL side (AE profile only, >=10 leads)
tt = top.copy(); tt["profile"] = tt.owner_id.map(uprof).fillna("?"); tt = tt[tt.profile.isin(["Sales Rep","Sales Rep - Manager"]) & (tt.uleads>=10)]
lm = tt.groupby(["manager", tt.ym//100]).agg(rep_months=("owner_id","size"), reps=("owner_id","nunique"), uleads=("uleads","sum"), uleads_conv=("uleads_conv","sum"), months=("ym","nunique")).reset_index().rename(columns={"ym":"yr"})
g = g.merge(lm, on=["manager","yr"], how="left")
g["approval_rate"] = g.approved/g.opps; g["close_on_approvals"] = g.funded/g.approved; g["close_on_subs"] = g.funded/g.opps
g["avg_deal"] = g.funded_amt/g.funded; g["avg_rev"] = g.sbg_rev/g.funded; g["conv_rate"] = g.uleads_conv/g.uleads
g["leads_per_rep_month"] = g.uleads/g.rep_months; g["opps_per_rep_month"] = g.opps/g.rep_months; g["funded_per_rep_month"] = g.funded/g.rep_months; g["rev_per_rep_month"] = g.sbg_rev/g.rep_months
g["avg_reps"] = g.rep_months/g.months
g["funded_per_1000_leads"] = 1000*g.funded/g.uleads; g["rev_per_lead"] = g.sbg_rev/g.uleads
g = g[g.opps >= 200].sort_values(["yr","funded"], ascending=[True,False])
R["manager_attrib"] = g.round(3).to_dict("records")
# composite rank (steady-state managers, excluding Adam Block new-hire/VSS pool and Jake Rotman VP pool)
core = g[~g.manager.isin(["Adam Block","Jake Rotman"])].copy()
for c in ["close_on_subs","funded_per_rep_month","rev_per_rep_month","conv_rate","funded_per_1000_leads","rev_per_lead"]:
    core[c+"_rank"] = core.groupby("yr")[c].rank(ascending=False)
core["composite"] = core[["close_on_subs_rank","funded_per_rep_month_rank","rev_per_rep_month_rank","conv_rate_rank"]].mean(axis=1)
R["manager_attrib_rank"] = core.sort_values(["yr","composite"])[["manager","yr","composite","reps","avg_reps","uleads","leads_per_rep_month","conv_rate","opps","approval_rate","close_on_approvals","close_on_subs","funded","funded_per_rep_month","rev_per_rep_month","avg_deal","avg_rev","rev_per_lead","med_fico"]].round(3).to_dict("records")
# tenure mix per manager (share of rep-months from reps with <=6 months tenure at opp creation) -- from opps
oo["ten"] = num(oo.Tenure_Months_at_Created_Date__c)
tm = oo[oo.is_ae].groupby(["mgr_month", oo.cym//100]).apply(lambda d: pd.Series({"share_opps_new_reps": (d.ten<=6).mean(), "median_tenure": d.ten.median()}), include_groups=False).reset_index().rename(columns={"mgr_month":"manager","cym":"yr"})
R["manager_tenure"] = tm.round(3).to_dict("records")
json.dump(R, open(f"{S}/out/metrics.json","w"), indent=1, default=lambda x: None if pd.isna(x) else (int(x) if isinstance(x,(np.integer,)) else float(x) if isinstance(x,(np.floating,)) else str(x)))
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
print(pd.DataFrame(R["manager_attrib_rank"]).to_string(index=False))
print(pd.DataFrame(R["manager_tenure"]).pivot(index="manager", columns="yr", values=["share_opps_new_reps","median_tenure"]).round(2).to_string())
Y=["2023","2024","2025","2026"]
print("\n=== HEADLINE (final) ===")
for k in ["leads_created_mavg","leads_300k_created_mavg","assigned_mavg","assigned_300k_mavg","assigned_300k_share","assigned_pct_of_created","lead_assigned_ever_share","reassign_ratio","qualified_pct_of_first_assigned","assigned_conv_rate","assigned_300k_conv_rate","opps_per_assigned","opps_created_mavg","approved_mavg","approval_rate","close_on_approvals","close_on_submissions","close_on_assigned","close_on_created","funded_mavg","funded_amt_mavg","sbg_rev_mavg","avg_deal_size","avg_sbg_rev_per_deal","rev_pct_of_funded","decline_rate","closed_lost_rate_of_approved"]:
    print(f"{k:34s}", "  ".join(f"{y}: {R[k].get(y)}" for y in Y))
print("headcount", R["headcount_mavg"]); print("per_rep", R["per_rep_mavg"]); print("growth_index", R["growth_index"])

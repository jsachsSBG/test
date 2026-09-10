"""Supplementary metrics: lead-source mix, distributor families, tenure, rep spread, manager scorecard, subs/opp, headcount index."""
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
dl = load_dir("dl"); oth = load_dir("other"); leads = load_dir("leads")
def ymcol(df, y="yr", m="mo"): return num(df[y]).astype(int)*100 + num(df[m]).astype(int)

# --- submissions per opportunity (submission-month view) ---
sm = oth["sub_month"]; sm["ym"] = ymcol(sm); sm = sm[in_window(sm.ym)]
for c in ["n_subs","n_opps","avg_days_in_uw"]: sm[c] = num(sm[c])
R["subs_per_submitted_opp"] = {y: r(sm[sm.ym//100==y].n_subs.sum()/sm[sm.ym//100==y].n_opps.sum(),2) for y in YEARS}
R["subs_month_table"] = sm[["ym","n_subs","n_opps"]].to_dict("records")

# --- lead source mix (unique assigned leads, excluding renewal-routed leads is not possible at source level; renewals team leads ~5%) ---
s = dl["dl_source_month"]; s["ym"] = ymcol(s); s = s[in_window(s.ym)]
for c in ["uleads","uleads_conv"]: s[c] = num(s[c]).fillna(0)
ss = s.groupby(["lead_source", s.ym//100]).agg(uleads=("uleads","sum"), conv=("uleads_conv","sum")).reset_index().rename(columns={"ym":"yr"})
ss["conv_rate"] = ss.conv/ss.uleads; ss["share"] = ss.uleads/ss.groupby("yr").uleads.transform("sum")
top = ss.groupby("lead_source").uleads.sum().sort_values(ascending=False).index[:12]
ss["src"] = np.where(ss.lead_source.isin(top), ss.lead_source, "All other")
ss2 = ss.groupby(["src","yr"]).agg(uleads=("uleads","sum"), conv=("conv","sum")).reset_index(); ss2["conv_rate"] = ss2.conv/ss2.uleads; ss2["share"] = ss2.uleads/ss2.groupby("yr").uleads.transform("sum")
R["assigned_source_year"] = ss2.round(4).to_dict("records")
# opp-level by source: funded per assigned lead (leads assigned -> funded), joining opp seg_source funded counts by created year
segsrc = pd.DataFrame(R["seg_source"]); segsrc = segsrc.rename(columns={"src":"lead_source"})
j = ss.merge(segsrc[["lead_source","cyr","opps","funded","funded_amt","sbg_rev"]], left_on=["lead_source","yr"], right_on=["lead_source","cyr"], how="inner")
j["funded_per_1000_assigned"] = 1000*j.funded/j.uleads; j["rev_per_assigned_lead"] = j.sbg_rev/j.uleads
R["source_economics_year"] = j[["lead_source","yr","uleads","conv_rate","opps","funded","funded_per_1000_assigned","rev_per_assigned_lead","funded_amt","sbg_rev"]].round(3).to_dict("records")

# --- distributor families ---
d = dl["dl_distributor_month"]; d["ym"] = ymcol(d); d = d[in_window(d.ym)]
for c in ["logs","uleads","uleads_conv"]: d[c] = num(d[c]).fillna(0)
def fam(rw):
    t, ds = rw.team, rw.distributor
    if t.startswith("Renewals"): return "Existing-customer leads routed to Renewals (excluded)"
    if "Sofi" in ds: return "Sofi partner distributors"
    if "Bluevine" in ds or "Bluevine" in t: return "Bluevine partner distributor"
    if t.startswith("Apps") or "Apps" in ds: return "Online applications"
    if t in ("Team 1","Team 2","Team 3","Team 4","Team 5","Team 6","Team 7","Team A","Team B","Team C"): return "Round-robin sales teams"
    if t == "Team VSS": return "VSS (virtual sales)"
    if "Nurture" in t: return "Nurture"
    if "Misc" in t: return "Misc leads"
    if "ATC" in t: return "ATC redistribution"
    if "Review" in t: return "Review queue"
    if "Deal Lost" in t: return "Deal-lost win-back"
    return "Other / tests"
d["fam"] = d.apply(fam, axis=1)
g = d.groupby(["fam", d.ym//100]).agg(uleads=("uleads","sum"), conv=("uleads_conv","sum"), logs=("logs","sum")).reset_index().rename(columns={"ym":"yr"})
g["conv_rate"] = g.conv/g.uleads
nb = g[~g.fam.str.contains("excluded")]; nb["share"] = nb.uleads/nb.groupby("yr").uleads.transform("sum")
R["distributor_family_year"] = nb.round(4).to_dict("records")
# team-level (Team 1..6) shares within round robin, by year
rr = d[d.team.isin(["Team 1","Team 2","Team 3","Team 4","Team 5","Team 6","Team 7","Team A","Team B","Team C"])].groupby(["team", d.ym//100]).agg(uleads=("uleads","sum"), conv=("uleads_conv","sum")).reset_index().rename(columns={"ym":"yr"})
rr["conv_rate"] = rr.conv/rr.uleads; rr["share"] = rr.uleads/rr.groupby("yr").uleads.transform("sum")
R["rr_team_year"] = rr.round(4).to_dict("records")
# redistribution share (2026 only has the Assignment_Type stamp)
dm = dl["dl_month"]; dm["ym"] = ymcol(dm); dm = dm[in_window(dm.ym)]
for c in ["logs","uleads","logs_initial","logs_redistribution","uleads_redistribution","uleads_incl_renewals"]: dm[c] = num(dm[c]).fillna(0)
x = dm[dm.logs_initial>0]
R["redistribution_share_2026"] = r(x.logs_redistribution.sum()/(x.logs_initial.sum()+x.logs_redistribution.sum()))
R["renewal_routed_leads_year"] = {y: int(dm[dm.ym//100==y].uleads_incl_renewals.sum() - dm[dm.ym//100==y].uleads.sum()) for y in YEARS}

# --- tenure at opportunity creation (AE-owned opps) ---
o["ten"] = num(o.Tenure_Months_at_Created_Date__c)
o["tenband"] = pd.cut(o.ten, [-100,3,6,12,24,48,1000], labels=["0-3 mo","4-6 mo","7-12 mo","13-24 mo","25-48 mo","49+ mo"])
ta = o[o.is_ae].groupby(["cyr","tenband"], observed=True).agg(opps=("Id","size"), approved=("approved","sum"), funded=("funded","sum"), famt=("funded_amt", lambda s: s[o.loc[s.index,"funded"]].sum())).reset_index()
ta["approval_rate"] = ta.approved/ta.opps; ta["close_on_subs"] = ta.funded/ta.opps; ta["avg_deal"] = ta.famt/ta.funded.replace(0,np.nan); ta["opp_share"] = ta.opps/ta.groupby("cyr").opps.transform("sum")
ta["tenband"] = ta.tenband.astype(str)
R["tenure_year"] = ta.round(4).to_dict("records")
# share of AE opps from reps with <= 6 months tenure
R["new_rep_opp_share"] = {y: r(ta[(ta.cyr==y)&(ta.tenband.isin(["0-3 mo","4-6 mo"]))].opps.sum()/ta[ta.cyr==y].opps.sum()) for y in YEARS}

# --- rep spread (funded per AE by funded year) ---
f = o[o.funded & in_window(o.fym) & o.is_ae].copy(); f["fyr"] = f.fym//100
rep = f.groupby(["fyr","OwnerId"]).agg(n=("Id","size"), amt=("funded_amt","sum"), rev=("sbg_rev","sum"), months=("fym","nunique")).reset_index()
rep["per_month"] = rep.n/rep.months
spread = {}
for y in YEARS:
    rr_ = rep[rep.fyr==y].sort_values("n", ascending=False); tot = rr_.n.sum(); k = max(1, int(round(len(rr_)*0.2)))
    full = rr_[rr_.months >= (FULL_MONTHS[y] if y != 2026 else 6)]
    spread[y] = {"aes_with_funding": int(len(rr_)), "top20pct_share": r(rr_.n.head(k).sum()/tot), "bottom50pct_share": r(rr_.n.tail(len(rr_)//2).sum()/tot), "median_funded_per_month_fullyear_reps": r(full.per_month.median(),2), "p25_per_month": r(full.per_month.quantile(.25),2), "p75_per_month": r(full.per_month.quantile(.75),2), "full_year_reps": int(len(full))}
R["rep_spread"] = spread

# --- headcount index (2023 = 100) ---
hc = pd.DataFrame(R["headcount_table"]); hc = hc[in_window(hc.ym)]
pr = pd.DataFrame(R["per_rep_table"]); pr = pr[in_window(pr.ym)]
om = pd.DataFrame(R["opp_month_table"]); om = om[in_window(om.ym)]
def yavg(df, col, y): 
    x = df[(df.ym//100==y) & (df.ym%100 <= FULL_MONTHS[y])]; return x[col].mean()
idx = {}
for y in YEARS:
    idx[y] = {"reps_ae": r(yavg(hc,"reps_ae",y)), "assigned": r(yavg(dm,"uleads",y)), "opps": r(yavg(om,"opps",y)), "funded": r(yavg(om,"funded",y)), "funded_amt": r(yavg(om,"funded_amt",y)), "sbg_rev": r(yavg(om,"sbg_rev",y))}
base = idx[2023]
R["growth_index"] = {y: {k: r(100*idx[y][k]/base[k],1) for k in base} for y in YEARS}

# --- manager scorecard: historical team stamp (opp outcomes) + distribution-log manager view (lead handling) ---
th = pd.DataFrame(R["team_hist_year"]); th["manager"] = th.team_hist.str.replace("Team ","")
name_map = {"Kyle":"Kyle Lyons","Andrew":"Andrew Wolff","Cameron":"Cameron Clearfield","Cole":"Cole Norman","Brian":"Brian Kim","Raphael":"Raphael Kanner","Frank":"Frank Tricamo","Newberry":"Brendan Newberry","Berkey":"Jared Berkey","Herrera":"Alexander Herrera","Jake":"Jake Rotman","Adam":"Adam Block","VSS":"VSS (Adam Block)","Unknown":"No distribution stamp (direct/referral/ops)"}
th["manager_full"] = th.manager.map(name_map).fillna(th.manager)
mg = pd.DataFrame(R["manager_dl_year"])
mg2 = mg.rename(columns={"manager":"manager_full","yr":"cyr","rep_months":"dl_rep_months","months":"dl_months"})
sc = th.merge(mg2, on=["manager_full","cyr"], how="left")
sc = sc[sc.opps >= 300]
keep = ["manager_full","cyr","opps","approved","funded","funded_amt","sbg_rev","approval_rate","close_on_approvals","close_on_subs","avg_deal","avg_rev","avg_reps","rep_months","funded_per_rep_month","rev_per_rep_month","opps_per_rep_month","med_fico","med_cycle","uleads","uleads_conv","conv_rate","leads_per_rep_month"]
R["manager_scorecard"] = sc[keep].round(3).to_dict("records")
# manager rank within year (steady-state managers only) on a composite: close_on_subs, funded_per_rep_month, avg_rev
core = sc[~sc.manager_full.isin(["VSS (Adam Block)","No distribution stamp (direct/referral/ops)","Adam Block","Jake Rotman"])].copy()
for c in ["close_on_subs","funded_per_rep_month","rev_per_rep_month","approval_rate","close_on_approvals","conv_rate"]:
    core[c+"_rank"] = core.groupby("cyr")[c].rank(ascending=False)
core["composite_rank"] = core[[c+"_rank" for c in ["close_on_subs","funded_per_rep_month","rev_per_rep_month","conv_rate"]]].mean(axis=1)
R["manager_rank"] = core.sort_values(["cyr","composite_rank"])[["manager_full","cyr","composite_rank","close_on_subs","funded_per_rep_month","rev_per_rep_month","conv_rate","approval_rate","close_on_approvals","avg_deal","avg_reps","opps","funded"]].round(3).to_dict("records")

# --- owner-profile mix of New opps (who actually works new business) ---
pm = o.groupby(["cyr","owner_profile"]).agg(opps=("Id","size"), funded=("funded","sum"), famt=("funded_amt", lambda s: s[o.loc[s.index,"funded"]].sum())).reset_index()
pm["opp_share"] = pm.opps/pm.groupby("cyr").opps.transform("sum"); pm["funded_share"] = pm.funded/pm.groupby("cyr").funded.transform("sum")
R["owner_profile_year"] = pm.round(4).to_dict("records")

# --- lead-level created->converted by source (lead report view) ---
ls = leads["lead_source_year"]; 
for c in ["created","conv","k300"]: ls[c] = num(ls[c]).fillna(0)
ls["LeadSource"] = ls.LeadSource.replace("", "(blank)")
top = ls.groupby("LeadSource").created.sum().sort_values(ascending=False).index[:12]
ls["src"] = np.where(ls.LeadSource.isin(top), ls.LeadSource, "All other")
ls2 = ls.groupby(["src","yr"]).agg(created=("created","sum"), conv=("conv","sum"), k300=("k300","sum")).reset_index()
ls2["conv_rate"] = ls2.conv/ls2.created; ls2["share"] = ls2.created/ls2.groupby("yr").created.transform("sum"); ls2["k300_share"] = ls2.k300/ls2.created
R["created_source_year"] = ls2.round(4).to_dict("records")
# CPL vs RS lead created & conv
ct = leads["lead_campaign_type_month"]; ct["ym"] = ymcol(ct); ct = ct[in_window(ct.ym)]
for c in ["created","conv"]: ct[c] = num(ct[c]).fillna(0)
ct["ctype"] = ct.ctype.replace("", "Untagged")
c2 = ct.groupby(["ctype", ct.ym//100]).agg(created=("created","sum"), conv=("conv","sum")).reset_index().rename(columns={"ym":"yr"}); c2["conv_rate"] = c2.conv/c2.created; c2["share"] = c2.created/c2.groupby("yr").created.transform("sum")
R["campaign_type_created_year"] = c2.round(4).to_dict("records")
# FICO and revenue bands at lead level
for nm in ["lead_fico_band_year","lead_rev_band_year"]:
    t = leads[nm]; t["created"] = num(t.created); t["conv"] = num(t.conv); t["conv_rate"] = t.conv/t.created; t["share"] = t.created/t.groupby("yr").created.transform("sum")
    R[nm] = t.round(4).to_dict("records")

json.dump(R, open(f"{S}/out/metrics.json","w"), indent=1, default=lambda x: None if pd.isna(x) else (int(x) if isinstance(x,(np.integer,)) else float(x) if isinstance(x,(np.floating,)) else str(x)))
print("subs_per_submitted_opp", R["subs_per_submitted_opp"]); print("growth_index", R["growth_index"]); print("renewal_routed", R["renewal_routed_leads_year"]); print("redistribution_share_2026", R["redistribution_share_2026"]); print("rep_spread", R["rep_spread"]); print("new_rep_opp_share", R["new_rep_opp_share"])
print(pd.DataFrame(R["manager_rank"]).to_string(index=False))
print(pd.DataFrame(R["assigned_source_year"]).pivot_table(index="src", columns="yr", values=["share","conv_rate"]).round(3).to_string())
print(pd.DataFrame(R["distributor_family_year"]).pivot_table(index="fam", columns="yr", values=["share","conv_rate"]).round(3).to_string())

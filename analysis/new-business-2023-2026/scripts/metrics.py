"""Compute every metric for the new-business story. Writes out/metrics.json and prints a summary."""
import sys, json, os
import pandas as pd, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from load import *

OUT = f"{S}/out"
os.makedirs(OUT, exist_ok=True)
R = {}   # results

def yr_of(ymv): return ymv // 100
def mo_of(ymv): return ymv % 100
def safe_div(a, b): return float(a) / float(b) if b not in (0, None) and not pd.isna(b) and b != 0 else None
def r(x, n=3): return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)
def monthly_avg(series_by_ym, agg="sum"):
    """series_by_ym: Series indexed by ym (int). Returns dict year -> monthly average over full months."""
    out = {}
    for y in YEARS:
        s = series_by_ym[(yr_of(series_by_ym.index) == y) & (mo_of(series_by_ym.index) <= FULL_MONTHS[y])]
        if len(s) == 0: out[y] = None; continue
        out[y] = r(s.sum() / FULL_MONTHS[y] if agg == "sum" else s.mean())
    return out
def yearly_total(series_by_ym):
    return {y: r(series_by_ym[(yr_of(series_by_ym.index) == y) & (mo_of(series_by_ym.index) <= FULL_MONTHS[y])].sum()) for y in YEARS}

users = load_users()
uprof = users.set_index("Id").Profile.to_dict()
uname = users.set_index("Id").Name.to_dict()
umgr = users.set_index("Id").ManagerName.to_dict()
opps = load_opps()
leads = load_dir("leads")
dl = load_dir("dl")
oth = load_dir("other")
print("opps:", None if opps is None else opps.shape, "| leads files:", sorted(leads), "| dl files:", sorted(dl), "| other:", sorted(oth))

def ymcol(df, y="yr", m="mo"):
    return num(df[y]).astype(int) * 100 + num(df[m]).astype(int)

# ---------- 1. Lead volume (created) ----------
lm = leads.get("lead_month")
lead_created = lead_conv = lead_k300 = lead_assigned_ever = None
if lm is not None:
    lm["ym"] = ymcol(lm)
    lm = lm[in_window(lm.ym)].set_index("ym").sort_index()
    for c in lm.columns:
        if c != "ym": lm[c] = num(lm[c]).fillna(0)
    lead_created = lm.created; lead_conv = lm.conv; lead_k300 = lm.k300; lead_assigned_ever = lm.assigned_ever
    R["leads_created_mavg"] = monthly_avg(lm.created)
    R["leads_created_total"] = yearly_total(lm.created)
    R["leads_300k_created_mavg"] = monthly_avg(lm.k300)
    R["lead_conv_rate_created"] = {y: r(safe_div(lm.conv[yr_of(lm.index)==y].sum(), lm.created[yr_of(lm.index)==y].sum())) for y in YEARS}
    R["lead_assigned_ever_share"] = {y: r(safe_div(lm.assigned_ever[yr_of(lm.index)==y].sum(), lm.created[yr_of(lm.index)==y].sum())) for y in YEARS}
    R["lead_dupe_share"] = {y: r(safe_div((lm.dup_existing_lead[yr_of(lm.index)==y]).sum(), lm.created[yr_of(lm.index)==y].sum())) for y in YEARS} if "dup_existing_lead" in lm else None
    R["lead_month_table"] = lm.reset_index().to_dict("records")

# ---------- 2. Distribution-log assigned (unique lead per month) ----------
dm = dl.get("dl_month")
if dm is not None:
    dm["ym"] = ymcol(dm)
    dm = dm[in_window(dm.ym)].set_index("ym").sort_index()
    for c in dm.columns:
        if c != "ym": dm[c] = num(dm[c]).fillna(0)
    R["assigned_mavg"] = monthly_avg(dm.uleads)
    R["assigned_300k_mavg"] = monthly_avg(dm.uleads_300k)
    R["assigned_total"] = yearly_total(dm.uleads)
    R["reassign_ratio"] = {y: r(safe_div(dm.logs[yr_of(dm.index)==y].sum(), dm.uleads[yr_of(dm.index)==y].sum())) for y in YEARS}
    R["assigned_conv_rate"] = {y: r(safe_div(dm.uleads_conv[yr_of(dm.index)==y].sum(), dm.uleads[yr_of(dm.index)==y].sum())) for y in YEARS}
    R["assigned_300k_conv_rate"] = {y: r(safe_div(dm.uleads_300k_conv[yr_of(dm.index)==y].sum(), dm.uleads_300k[yr_of(dm.index)==y].sum())) for y in YEARS} if "uleads_300k_conv" in dm else None
    R["assigned_300k_share"] = {y: r(safe_div(dm.uleads_300k[yr_of(dm.index)==y].sum(), dm.uleads[yr_of(dm.index)==y].sum())) for y in YEARS}
    if lead_created is not None:
        j = pd.concat([dm.uleads, lead_created.rename("created")], axis=1).dropna()
        R["assigned_pct_of_created"] = {y: r(safe_div(j.uleads[yr_of(j.index)==y].sum(), j.created[yr_of(j.index)==y].sum())) for y in YEARS}
        R["assigned_pct_of_created_month"] = {int(k): r(v) for k, v in (j.uleads / j.created).items()}
    R["dl_month_table"] = dm.reset_index().to_dict("records")

# qualified % of assigned: first-assigned cohort
fc = leads.get("lead_first_assigned_cohort")
if fc is not None:
    fc["ym"] = ymcol(fc, "ayr", "amo")
    fc = fc[in_window(fc.ym)].set_index("ym").sort_index()
    for c in fc.columns:
        if c != "ym": fc[c] = num(fc[c]).fillna(0)
    q = np.maximum(fc.qual_ever, fc.conv)  # converted leads passed through qualified
    R["qualified_pct_of_first_assigned"] = {y: r(safe_div(q[yr_of(fc.index)==y].sum(), fc.n[yr_of(fc.index)==y].sum())) for y in YEARS}
    R["conv_pct_of_first_assigned"] = {y: r(safe_div(fc.conv[yr_of(fc.index)==y].sum(), fc.n[yr_of(fc.index)==y].sum())) for y in YEARS}
    R["k300_pct_of_first_assigned"] = {y: r(safe_div(fc.k300[yr_of(fc.index)==y].sum(), fc.n[yr_of(fc.index)==y].sum())) for y in YEARS}
    R["first_assigned_cohort_table"] = fc.reset_index().to_dict("records")

# ---------- 3. Opportunity funnel ----------
if opps is not None:
    o = opps[in_window(opps.cym)].copy()
    by = o.groupby("cym").agg(opps=("Id","size"), approved=("approved","sum"), funded_cohort=("funded","sum"),
                              funded_amt_cohort=("funded_amt", lambda s: s[o.loc[s.index,"funded"]].sum()),
                              declined=("declined","sum"), closed_lost=("closed_lost","sum"), owners=("OwnerId","nunique"))
    fund = o[o.funded & in_window(o.fym)].groupby("fym").agg(funded=("Id","size"), funded_amt=("funded_amt","sum"), sbg_rev=("sbg_rev","sum"),
                                                                 tot_rev=("tot_rev","sum"), fowners=("OwnerId","nunique"))
    m = by.join(fund, how="outer").fillna(0)
    m.index.name = "ym"
    R["opps_created_mavg"] = monthly_avg(m.opps); R["opps_created_total"] = yearly_total(m.opps)
    R["approved_mavg"] = monthly_avg(m.approved)
    R["funded_mavg"] = monthly_avg(m.funded); R["funded_total"] = yearly_total(m.funded)
    R["funded_amt_mavg"] = monthly_avg(m.funded_amt); R["funded_amt_total"] = yearly_total(m.funded_amt)
    R["sbg_rev_mavg"] = monthly_avg(m.sbg_rev); R["sbg_rev_total"] = yearly_total(m.sbg_rev)
    R["approval_rate"] = {y: r(safe_div(m.approved[yr_of(m.index)==y].sum(), m.opps[yr_of(m.index)==y].sum())) for y in YEARS}
    R["close_on_approvals"] = {y: r(safe_div(m.funded_cohort[yr_of(m.index)==y].sum(), m.approved[yr_of(m.index)==y].sum())) for y in YEARS}
    R["close_on_submissions"] = {y: r(safe_div(m.funded_cohort[yr_of(m.index)==y].sum(), m.opps[yr_of(m.index)==y].sum())) for y in YEARS}
    R["avg_deal_size"] = {y: r(safe_div(m.funded_amt[yr_of(m.index)==y].sum(), m.funded[yr_of(m.index)==y].sum()), 0) for y in YEARS}
    R["avg_sbg_rev_per_deal"] = {y: r(safe_div(m.sbg_rev[yr_of(m.index)==y].sum(), m.funded[yr_of(m.index)==y].sum()), 0) for y in YEARS}
    R["rev_pct_of_funded"] = {y: r(safe_div(m.sbg_rev[yr_of(m.index)==y].sum(), m.funded_amt[yr_of(m.index)==y].sum()), 4) for y in YEARS}
    R["decline_rate"] = {y: r(safe_div(m.declined[yr_of(m.index)==y].sum(), m.opps[yr_of(m.index)==y].sum())) for y in YEARS}
    R["closed_lost_rate_of_approved"] = {y: r(safe_div(m.closed_lost[yr_of(m.index)==y].sum(), m.approved[yr_of(m.index)==y].sum())) for y in YEARS}
    if dm is not None:
        jj = m.join(dm[["uleads","uleads_300k","ureps"]], how="inner")
        R["opps_per_assigned"] = {y: r(safe_div(jj.opps[yr_of(jj.index)==y].sum(), jj.uleads[yr_of(jj.index)==y].sum())) for y in YEARS}
        R["close_on_assigned"] = {y: r(safe_div(jj.funded[yr_of(jj.index)==y].sum(), jj.uleads[yr_of(jj.index)==y].sum())) for y in YEARS}
    if lead_created is not None:
        jj = m.join(lead_created.rename("created"), how="inner")
        R["close_on_created"] = {y: r(safe_div(jj.funded[yr_of(jj.index)==y].sum(), jj.created[yr_of(jj.index)==y].sum())) for y in YEARS}
    R["opp_month_table"] = m.reset_index().to_dict("records")

    # ---------- 4. Headcount & per-rep ----------
    # Active reps = distinct users who received >= 10 unique leads in the month (dist logs), profile Sales Rep (AE) vs VSS
    rm = dl.get("dl_rep_month")
    if rm is not None:
        rm["ym"] = ymcol(rm); rm = rm[in_window(rm.ym)].copy()
        for c in ["logs","uleads","uleads_300k","uleads_conv"]:
            if c in rm: rm[c] = num(rm[c]).fillna(0)
        rm["profile"] = rm.owner_id.map(uprof).fillna("?")
        rm["is_ae"] = rm.profile.isin(["Sales Rep","Sales Rep - Manager"])
        rm["is_vss"] = rm.profile.eq("Sales Rep - VSS")
        act = rm[(rm.uleads >= 10) & rm.profile.isin(["Sales Rep","Sales Rep - Manager","Sales Rep - VSS"])]
        hc = act.groupby("ym").agg(reps_all=("owner_id","nunique"), reps_ae=("owner_id", lambda s: s[act.loc[s.index,"is_ae"]].nunique()),
                                   reps_vss=("owner_id", lambda s: s[act.loc[s.index,"is_vss"]].nunique()))
        # opp-owner based headcount: distinct owners creating >= 3 New opps in month
        oc = o.groupby(["cym","OwnerId"]).size().reset_index(name="n")
        oc["profile"] = oc.OwnerId.map(uprof).fillna("?")
        oc2 = oc[oc.n >= 3].groupby("cym").agg(opp_owners=("OwnerId","nunique"), opp_owners_ae=("OwnerId", lambda s: s[oc.loc[s.index,"profile"].isin(["Sales Rep","Sales Rep - Manager"])].nunique()))
        hc = hc.join(oc2, how="outer").fillna(0)
        hc.index.name = "ym"
        R["headcount_mavg"] = {k: monthly_avg(hc[k], "mean") for k in hc.columns}
        R["headcount_table"] = hc.reset_index().to_dict("records")
        # per-rep (AE) productivity: use AE headcount; leads per rep from AE-only uleads
        ae_leads = rm[rm.is_ae].groupby("ym").uleads.sum()
        ae_opps = o[o.OwnerId.map(uprof).isin(["Sales Rep","Sales Rep - Manager"])].groupby("cym").size()
        ae_fund = o[o.funded & in_window(o.fym) & o.OwnerId.map(uprof).isin(["Sales Rep","Sales Rep - Manager"])].groupby("fym").agg(f=("Id","size"), fa=("funded_amt","sum"), rev=("sbg_rev","sum"))
        pr = pd.DataFrame({"reps_ae": hc.reps_ae, "ae_leads": ae_leads, "ae_opps": ae_opps, "ae_funded": ae_fund.f, "ae_funded_amt": ae_fund.fa, "ae_rev": ae_fund.rev}).fillna(0)
        pr = pr[in_window(pr.index)]
        pr["leads_per_rep"] = pr.ae_leads / pr.reps_ae.replace(0, np.nan)
        pr["opps_per_rep"] = pr.ae_opps / pr.reps_ae.replace(0, np.nan)
        pr["funded_per_rep"] = pr.ae_funded / pr.reps_ae.replace(0, np.nan)
        pr["rev_per_rep"] = pr.ae_rev / pr.reps_ae.replace(0, np.nan)
        pr["funded_amt_per_rep"] = pr.ae_funded_amt / pr.reps_ae.replace(0, np.nan)
        R["per_rep_mavg"] = {k: monthly_avg(pr[k].dropna(), "mean") for k in ["leads_per_rep","opps_per_rep","funded_per_rep","rev_per_rep","funded_amt_per_rep","reps_ae"]}
        pr.index.name = "ym"
        R["per_rep_table"] = pr.reset_index().to_dict("records")
        # VSS share of opps
        o["owner_profile"] = o.OwnerId.map(uprof).fillna("?")
        R["opps_by_owner_profile_year"] = o.groupby(["cyr","owner_profile"]).size().unstack(fill_value=0).to_dict("index")
        R["funded_by_owner_profile_year"] = o[o.funded].groupby(["cyr","owner_profile"]).size().unstack(fill_value=0).to_dict("index")

    # ---------- 5. Teams / managers ----------
    def team_stats(col, min_opps=100):
        g = o.groupby([col,"cyr"]).agg(opps=("Id","size"), approved=("approved","sum"), funded=("funded","sum"),
                                       funded_amt=("funded_amt", lambda s: s[o.loc[s.index,"funded"]].sum()),
                                       sbg_rev=("sbg_rev", lambda s: s[o.loc[s.index,"funded"]].sum()),
                                       reps=("OwnerId","nunique"), months=("cym","nunique"),
                                       med_fico=("fico","median"), med_cycle=("opp_to_fund_days", lambda s: s[o.loc[s.index,"funded"]].median()),
                                       k300=("acct_rev", lambda s: (s>=300000).mean()))
        g = g[g.opps >= min_opps].reset_index()
        g["approval_rate"] = g.approved / g.opps
        g["close_on_approvals"] = g.funded / g.approved.replace(0, np.nan)
        g["close_on_subs"] = g.funded / g.opps
        g["avg_deal"] = g.funded_amt / g.funded.replace(0, np.nan)
        g["avg_rev"] = g.sbg_rev / g.funded.replace(0, np.nan)
        # rep-months: sum over months of distinct owners with >=3 opps in that month
        om = o.groupby([col,"cym","OwnerId"]).size().reset_index(name="n")
        om = om[om.n >= 3]
        om["cyr"] = om.cym // 100
        rmn = om.groupby([col,"cyr"]).size().rename("rep_months").reset_index()
        g = g.merge(rmn, on=[col,"cyr"], how="left")
        g["funded_per_rep_month"] = g.funded / g.rep_months
        g["rev_per_rep_month"] = g.sbg_rev / g.rep_months
        g["opps_per_rep_month"] = g.opps / g.rep_months
        g["avg_reps"] = g.rep_months / g.months
        return g.round(4)
    R["team_hist_year"] = team_stats("team_hist").to_dict("records")
    R["team_now_year"] = team_stats("team_now").to_dict("records")
    # manager view from distribution logs (Assigned_User_Manager__c, Nov-2024+)
    mm = dl.get("dl_manager_month")
    if mm is not None:
        mm["ym"] = ymcol(mm); mm = mm[in_window(mm.ym) & ~mm.manager.isin(["Alex Miller","Trevor Eastin","Sarah Martin"])].copy()
        for c in ["logs","uleads","uleads_300k","uleads_conv","ureps"]:
            if c in mm: mm[c] = num(mm[c]).fillna(0)
        mg = mm.groupby(["manager", mm.ym//100]).agg(uleads=("uleads","sum"), uleads_conv=("uleads_conv","sum"), uleads_300k=("uleads_300k","sum"), rep_months=("ureps","sum"), months=("ym","nunique")).reset_index()
        mg.columns = ["manager","yr","uleads","uleads_conv","uleads_300k","rep_months","months"]
        mg["conv_rate"] = mg.uleads_conv / mg.uleads
        mg["leads_per_rep_month"] = mg.uleads / mg.rep_months
        R["manager_dl_year"] = mg.round(4).to_dict("records")

    # ---------- 6. Segments ----------
    def seg(col, min_n=200, top=None):
        g = o.groupby([col,"cyr"]).agg(opps=("Id","size"), approved=("approved","sum"), funded=("funded","sum"),
                                       funded_amt=("funded_amt", lambda s: s[o.loc[s.index,"funded"]].sum()),
                                       sbg_rev=("sbg_rev", lambda s: s[o.loc[s.index,"funded"]].sum())).reset_index()
        tot = g.groupby(col).opps.sum().sort_values(ascending=False)
        keep = tot[tot >= min_n].index
        if top: keep = keep[:top]
        g = g[g[col].isin(keep)]
        g["approval_rate"] = g.approved / g.opps; g["close_on_approvals"] = g.funded / g.approved.replace(0,np.nan)
        g["close_on_subs"] = g.funded / g.opps; g["avg_deal"] = g.funded_amt / g.funded.replace(0,np.nan); g["avg_rev"] = g.sbg_rev / g.funded.replace(0,np.nan)
        return g.round(4).to_dict("records")
    R["seg_source"] = seg("src", 300, 25)
    R["seg_campaign_type"] = seg("Lead_Source_Campaign_Type__c", 1)
    R["seg_industry"] = seg("Account_Industry__c", 500, 25)
    R["seg_fico_band"] = seg("A_FICO_Band__c", 1)
    R["seg_credit_rating"] = seg("Credit_Rating__c", 1)
    R["seg_rev_band"] = seg("Annual_Revenue_Band__c", 1)
    R["seg_product"] = seg("Product__c", 1)
    R["seg_distributor"] = seg("DE_Initial_Distributor__c", 1)
    # approval size bands (approved opps only)
    a = o[o.approved].copy()
    amt = a.max_app.fillna(a.largest_app)
    a["app_band"] = pd.cut(amt, [-1, 0, 25000, 50000, 100000, 250000, 500000, 1e12], labels=["unknown/0","1-25K","25-50K","50-100K","100-250K","250-500K","500K+"]).astype(str)
    ab = a.groupby(["app_band","cyr"]).agg(approved=("Id","size"), funded=("funded","sum"), funded_amt=("funded_amt", lambda s: s[a.loc[s.index,"funded"]].sum()), sbg_rev=("sbg_rev", lambda s: s[a.loc[s.index,"funded"]].sum())).reset_index()
    ab["close_on_approvals"] = ab.funded / ab.approved; ab["avg_deal"] = ab.funded_amt / ab.funded.replace(0,np.nan)
    R["seg_approval_band"] = ab.round(4).to_dict("records")
    R["max_approval_fill_rate"] = {y: r(a[a.cyr==y].max_app.notna().mean()) for y in YEARS}
    # lost / decline reasons
    R["lost_reasons_year"] = o[o.closed_lost].groupby(["cyr","Deal_Lost_Reasons__c"]).size().unstack(fill_value=0).to_dict("index")
    R["decline_reasons_year"] = o[o.declined].groupby(["cyr","Deal_Decline_Reasons__c"]).size().unstack(fill_value=0).to_dict("index")

    # ---------- 7. Cycle times ----------
    cyc = o[o.lead_to_opp_days.between(0, 365)]
    c1 = cyc.groupby("cym").lead_to_opp_days.agg(["median","mean","size"])
    f = o[o.funded & in_window(o.fym) & o.opp_to_fund_days.between(0, 365)]
    c2 = f.groupby("fym").opp_to_fund_days.agg(["median","mean","size"])
    c3 = f.groupby("fym").opp_to_approve_days.agg(["median","mean"])
    R["cycle_lead_to_opp"] = {y: {"median": r(cyc[cyc.cyr==y].lead_to_opp_days.median(),1), "mean": r(cyc[cyc.cyr==y].lead_to_opp_days.mean(),1), "p75": r(cyc[cyc.cyr==y].lead_to_opp_days.quantile(.75),1), "same_day_share": r((cyc[cyc.cyr==y].lead_to_opp_days<1).mean())} for y in YEARS}
    R["cycle_opp_to_fund"] = {y: {"median": r(f[f.fym//100==y].opp_to_fund_days.median(),1), "mean": r(f[f.fym//100==y].opp_to_fund_days.mean(),1), "p75": r(f[f.fym//100==y].opp_to_fund_days.quantile(.75),1), "within_7d": r((f[f.fym//100==y].opp_to_fund_days<=7).mean())} for y in YEARS}
    R["cycle_opp_to_approve"] = {y: {"median": r(f[f.fym//100==y].opp_to_approve_days.median(),1), "mean": r(f[f.fym//100==y].opp_to_approve_days.mean(),1)} for y in YEARS}
    R["cycle_month_table"] = c1.join(c2, lsuffix="_l2o", rsuffix="_o2f", how="outer").reset_index().rename(columns={"index":"ym"}).to_dict("records")
    # full-cycle: first assigned -> funded
    f2 = o[o.funded & in_window(o.fym)].copy(); f2["full"] = (f2.funded_dts - f2.fa).dt.total_seconds()/86400
    f2 = f2[f2.full.between(0, 730)]
    R["cycle_full"] = {y: {"median": r(f2[f2.fym//100==y].full.median(),1), "mean": r(f2[f2.fym//100==y].full.mean(),1)} for y in YEARS}

    # ---------- 8. Win-back ----------
    prior = opps[opps.lost][["AccountId","created"]].rename(columns={"created":"lost_at"})
    p23 = oth.get("opps_pre2023_lost")
    if p23 is not None:
        p23 = p23.copy(); p23["lost_at"] = dt(p23.CreatedDate); prior = pd.concat([prior, p23[["AccountId","lost_at"]]])
    prior = prior[prior.AccountId != ""]
    first_lost = prior.groupby("AccountId").lost_at.min()
    fo = o[o.funded & in_window(o.fym)].copy()
    fo["first_lost"] = fo.AccountId.map(first_lost)
    fo["winback"] = fo.first_lost.notna() & (fo.first_lost < fo.created)
    fo["deal_lost_src"] = fo.src.eq("Deal Lost") | fo.Most_Recent_Lead_Source__c.eq("Deal Lost")
    wb = fo.groupby(fo.fym//100).agg(funded=("Id","size"), winback=("winback","sum"), winback_amt=("funded_amt", lambda s: s[fo.loc[s.index,"winback"]].sum()), funded_amt=("funded_amt","sum"), deal_lost_src=("deal_lost_src","sum"), deal_lost_src_amt=("funded_amt", lambda s: s[fo.loc[s.index,"deal_lost_src"]].sum()))
    wb["winback_share"] = wb.winback / wb.funded; wb["winback_amt_share"] = wb.winback_amt / wb.funded_amt; wb["deal_lost_src_share"] = wb.deal_lost_src / wb.funded
    R["winback_year"] = wb.round(4).reset_index().rename(columns={"fym":"yr"}).to_dict("records")
    # lost-lead re-entry: opps created from 'Deal Lost' source per year
    R["deal_lost_src_opps_year"] = o[o.src.eq("Deal Lost")].groupby("cyr").agg(opps=("Id","size"), funded=("funded","sum")).to_dict("index")

    # ---------- 9. Seasonality ----------
    def season(series):  # index ym over full years 2023-2025
        s = series[(yr_of(series.index) >= 2023) & (yr_of(series.index) <= 2025)]
        df = pd.DataFrame({"v": s, "y": yr_of(s.index), "m": mo_of(s.index)})
        df["idx"] = df.v / df.groupby("y").v.transform("mean")
        return df.groupby("m").idx.mean().round(3).to_dict()
    R["season_opps"] = season(m.opps); R["season_funded"] = season(m.funded); R["season_funded_amt"] = season(m.funded_amt)
    if lead_created is not None: R["season_leads"] = season(lead_created)
    if dm is not None: R["season_assigned"] = season(dm.uleads)

    # ---------- 10. Lender concentration (fundings) ----------
    fl = o[o.funded & in_window(o.fym)].copy(); fl["lender"] = fl.Lender_Name__c.replace("", "Unknown"); fl["yr"] = fl.fym//100
    lg = fl.groupby(["yr","lender"]).agg(n=("Id","size"), amt=("funded_amt","sum"), rev=("sbg_rev","sum")).reset_index()
    conc = {}
    for y in YEARS:
        g = lg[lg.yr==y].sort_values("n", ascending=False); tot = g.n.sum(); ta = g.amt.sum()
        if len(g)==0: continue
        sh = g.n/tot
        conc[y] = {"lenders_used": int((g.n>0).sum()), "top1_share": r(sh.iloc[0]), "top3_share": r(sh.iloc[:3].sum()), "top5_share": r(sh.iloc[:5].sum()), "top10_share": r(sh.iloc[:10].sum()), "hhi": r((sh**2).sum()*10000,0),
                   "top1_amt_share": r((g.amt/ta).iloc[0]), "top5_amt_share": r((g.amt/ta).iloc[:5].sum()), "top": [{"lender": a, "n": int(b), "share": r(b/tot), "amt": r(c,0), "avg": r(c/b,0)} for a,b,c in g[["lender","n","amt"]].head(12).values]}
    R["lender_funded_conc"] = conc
    # submissions concentration
    sl = oth.get("sub_lender_month")
    if sl is not None:
        sl = sl.copy(); sl["ym"] = ymcol(sl); sl = sl[in_window(sl.ym)]
        for c in ["n_subs","n_opps","n_preapproved","n_funder_approved","n_offer_won"]:
            if c in sl: sl[c] = num(sl[c]).fillna(0)
        sg = sl.groupby([sl.ym//100, "lender"]).agg(n=("n_subs","sum"), pre=("n_preapproved","sum") if "n_preapproved" in sl else ("n_subs","sum")).reset_index().rename(columns={"ym":"yr"})
        sc = {}
        for y in YEARS:
            g = sg[sg.yr==y].sort_values("n", ascending=False); tot = g.n.sum()
            if len(g)==0: continue
            sh = g.n/tot
            sc[y] = {"lenders": int((g.n>0).sum()), "subs": int(tot), "top1_share": r(sh.iloc[0]), "top5_share": r(sh.iloc[:5].sum()), "top10_share": r(sh.iloc[:10].sum()), "hhi": r((sh**2).sum()*10000,0),
                     "top": [{"lender": a, "n": int(b), "share": r(b/tot), "pre": int(c)} for a,b,c in g[["lender","n","pre"]].head(12).values]}
        R["lender_sub_conc"] = sc
        sm = sl.groupby("ym").agg(subs=("n_subs","sum"), opps=("n_opps","max"))
        R["subs_per_opp_mavg"] = monthly_avg(sm.subs)
    R["subs_per_opp_field"] = {y: r(o[o.cyr==y].n_subs.mean(),2) for y in YEARS}

    # ---------- 11. Product mix & deal economics ----------
    R["product_mix_funded_year"] = fl.groupby(["yr","Product__c"]).size().unstack(fill_value=0).to_dict("index")
    R["funded_amt_dist"] = {y: {"median": r(fl[fl.yr==y].funded_amt.median(),0), "p25": r(fl[fl.yr==y].funded_amt.quantile(.25),0), "p75": r(fl[fl.yr==y].funded_amt.quantile(.75),0), "p90": r(fl[fl.yr==y].funded_amt.quantile(.9),0), "share_100k_plus": r((fl[fl.yr==y].funded_amt>=100000).mean()), "share_under_25k": r((fl[fl.yr==y].funded_amt<25000).mean())} for y in YEARS}
    R["fico_funded"] = {y: r(fl[fl.yr==y].fico.median(),0) for y in YEARS}
    R["fico_created"] = {y: r(o[o.cyr==y].fico.median(),0) for y in YEARS}
    R["acct_rev_created_median"] = {y: r(o[o.cyr==y].acct_rev.median(),0) for y in YEARS}
    R["acct_rev_300k_share_created"] = {y: r((o[o.cyr==y].acct_rev>=300000).mean()) for y in YEARS}

json.dump(R, open(f"{OUT}/metrics.json","w"), indent=1, default=lambda x: None if pd.isna(x) else (int(x) if isinstance(x,(np.integer,)) else float(x) if isinstance(x,(np.floating,)) else str(x)))
print("keys:", len(R))
for k in ["leads_created_mavg","assigned_mavg","assigned_pct_of_created","qualified_pct_of_first_assigned","assigned_conv_rate","opps_created_mavg","approval_rate","close_on_approvals","close_on_submissions","close_on_assigned","close_on_created","funded_mavg","avg_deal_size","avg_sbg_rev_per_deal","headcount_mavg","per_rep_mavg","cycle_lead_to_opp","cycle_opp_to_fund","winback_year","lender_funded_conc"]:
    if k in R: print(k, "=>", json.dumps(R[k], default=str)[:600])

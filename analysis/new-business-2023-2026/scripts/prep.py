"""Build canonical input files (data/leads, data/dl, data/other) from the raw aggregate TSVs in data/agg."""
import pandas as pd, numpy as np, glob, os, ast
S = "/tmp/claude-0/-home-user-test/4450fde6-d7f1-5400-906d-a37991314de6/scratchpad"
A = f"{S}/data/agg"
def rd(name): return pd.read_csv(f"{A}/{name}.tsv", sep="\t", dtype=str, keep_default_na=False)
def numcols(df, cols):
    for c in cols: df[c] = pd.to_numeric(df[c].replace("", np.nan), errors="coerce").fillna(0)
    return df
for d in ["leads","dl","other"]: os.makedirs(f"{S}/data/{d}", exist_ok=True)

# ---- leads/lead_month ----
m = None
for nm, col in [("leads_raw_m_created","created"),("leads_raw_m_conv","conv"),("leads_raw_m_k300","k300"),("leads_raw_m_k300_conv","k300_conv"),
                ("leads_raw_m_assigned_ever","assigned_ever"),("leads_raw_m_assigned_ever_conv","assigned_ever_conv"),("leads_raw_m_qual_ever","qual_ever"),
                ("leads_raw_m_qual_ever_conv","qual_ever_conv"),("leads_raw_m_dup_matching_lead","dup_existing_lead"),("leads_raw_m_online_app","online_app")]:
    d = rd(nm).rename(columns={"n": col})[["yr","mo",col]]
    m = d if m is None else m.merge(d, on=["yr","mo"], how="outer")
m = m.fillna("0"); m.to_csv(f"{S}/data/leads/lead_month.tsv", sep="\t", index=False)
# lead source year
sy = rd("leads_raw_sy_created").rename(columns={"n":"created"}).merge(rd("leads_raw_sy_conv").rename(columns={"n":"conv"}), on=["LeadSource","yr"], how="left").merge(rd("leads_raw_sy_k300").rename(columns={"n":"k300"}), on=["LeadSource","yr"], how="left").fillna("0")
sy.to_csv(f"{S}/data/leads/lead_source_year.tsv", sep="\t", index=False)
# industry year
ind = rd("lead_industry_year_conv"); ind = numcols(ind, ["n"])
iy = ind.groupby(["yr","Industry"]).apply(lambda g: pd.Series({"created": g.n.sum(), "conv": g[g.conv=="True"].n.sum()}), include_groups=False).reset_index()
iy.to_csv(f"{S}/data/leads/lead_industry_year.tsv", sep="\t", index=False)
# campaign type month
cs = numcols(rd("lead_campaign_status_month"), ["n"])
ct = cs.groupby(["yr","mo","ctype"]).apply(lambda g: pd.Series({"created": g.n.sum(), "conv": g[g.conv=="True"].n.sum(), "qual_or_conv": g[g.Status.isin(["Qualified","Incomplete Pkg","Converted"])].n.sum()}), include_groups=False).reset_index()
ct.to_csv(f"{S}/data/leads/lead_campaign_type_month.tsv", sep="\t", index=False)
for nm in ["lead_first_assigned_cohort","lead_rev_band_year","lead_fico_band_year"]:
    rd(nm).to_csv(f"{S}/data/leads/{nm}.tsv", sep="\t", index=False)

# ---- dl/dl_month ----
dm = rd("dl_raw_m_base")
for nm in ["dl_raw_m_conv","dl_raw_m_300k","dl_raw_m_300k_conv","dl_raw_m_initial","dl_raw_m_redis"]:
    dm = dm.merge(rd(nm), on=["yr","mo"], how="left")
dm = dm.fillna("0"); dm.to_csv(f"{S}/data/dl/dl_month.tsv", sep="\t", index=False)
# dl rep month
base = pd.concat([rd(f"dl_rep_month_{p}_base") for p in ["2023_2024","2025","2026"]])
conv = pd.concat([rd(f"dl_rep_month_{p}_conv") for p in ["2023_2024","2025","2026"]])
k3 = pd.concat([rd(f"dl_rep_month_{p}_300k") for p in ["2023_2024","2025","2026"]])
rm = base.merge(conv, on=["yr","mo","owner_id"], how="left").merge(k3, on=["yr","mo","owner_id"], how="left").fillna("0")
rm.to_csv(f"{S}/data/dl/dl_rep_month.tsv", sep="\t", index=False)
# dl manager x rep month, and manager month
mb = pd.concat([rd("dl_mgr_rep_month_2024_2025_base"), rd("dl_mgr_rep_month_2026_base")])
mc = pd.concat([rd("dl_mgr_rep_month_2024_2025_conv"), rd("dl_mgr_rep_month_2026_conv")])
mr = mb.merge(mc, on=["yr","mo","manager","owner_id"], how="left").fillna("0")
mr.to_csv(f"{S}/data/dl/dl_mgr_rep_month.tsv", sep="\t", index=False)
mr2 = numcols(mr.copy(), ["logs","uleads","uleads_conv"])
mm = mr2.groupby(["yr","mo","manager"]).agg(logs=("logs","sum"), uleads=("uleads","sum"), uleads_conv=("uleads_conv","sum"), ureps=("owner_id","nunique")).reset_index()
mm["uleads_300k"] = 0
mm.to_csv(f"{S}/data/dl/dl_manager_month.tsv", sep="\t", index=False)
# dl team month (subagent files)
tm = pd.concat([rd(f"dl_raw_tm_{y}_base") for y in [2023,2024,2025,2026]]); tm.to_csv(f"{S}/data/dl/dl_team_month.tsv", sep="\t", index=False)
# distributor month
db = rd("dl_distributor_month_base").merge(rd("dl_distributor_month_conv"), on=["yr","mo","team","distributor"], how="left").fillna("0")
db.to_csv(f"{S}/data/dl/dl_distributor_month.tsv", sep="\t", index=False)
# source month (aggregate the team-dimension versions back to yr, mo, source)
def agg_src(names, col):
    frames = []
    for nm in names:
        d = numcols(rd(nm), [col]); frames.append(d.groupby(["yr","mo","lead_source"])[col].sum().reset_index())
    return pd.concat(frames)
sb = agg_src(["dl_src_month_2023_base_team","dl_src_month_2024_base","dl_src_month_2025_base","dl_src_month_2026_base"], "uleads")
sc = agg_src(["dl_src_month_2023_conv_team","dl_src_month_2024H1_conv_team","dl_src_month_2024H2_conv_team","dl_src_month_2025_conv","dl_src_month_2026H1_conv_team","dl_src_month_2026H2_conv_team"], "uleads_conv")
sm = sb.merge(sc, on=["yr","mo","lead_source"], how="left").fillna(0)
sm.to_csv(f"{S}/data/dl/dl_source_month.tsv", sep="\t", index=False)
# team members (parse nested relationship dicts)
tmem = rd("team_members")
def nm_of(s):
    try: return ast.literal_eval(s).get("Name","")
    except Exception: return ""
tmem["team"] = tmem["n2de__Team__r"].map(nm_of); tmem["user_name"] = tmem["n2de__User__r"].map(nm_of)
tmem = tmem.rename(columns={"n2de__User__c":"user_id","n2de__Is_active__c":"active","n2de__Weighting__c":"weight"})[["Id","team","user_id","user_name","active","weight","CreatedDate"]]
tmem.to_csv(f"{S}/data/dl/team_members.tsv", sep="\t", index=False)

# ---- other ----
sl = pd.concat([rd("sub_lender_month_2023_2024"), rd("sub_lender_month_2025_2026")])
sp = pd.concat([rd("sub_pre_month_2023_2024"), rd("sub_pre_month_2025_2026")]).rename(columns={"n_pre":"n_preapproved"})
sl = sl.merge(sp, on=["yr","mo","lender"], how="left").fillna("0"); sl.to_csv(f"{S}/data/other/sub_lender_month.tsv", sep="\t", index=False)
for nm, out in [("other_raw_sub_month","sub_month"),("other_raw_sub_declined_reason_year","sub_declined_reason_year"),("other_raw_new_funded_month_check","new_funded_month_check"),("other_raw_renewal_month","renewal_month"),("other_raw_renewal_funded_month","renewal_funded_month")]:
    rd(nm).to_csv(f"{S}/data/other/{out}.tsv", sep="\t", index=False)
print("prep done")
for d in ["leads","dl","other"]:
    for f in sorted(glob.glob(f"{S}/data/{d}/*.tsv")): print(f"  {d}/{os.path.basename(f)}: {sum(1 for _ in open(f))-1} rows")

"""Shared loaders for the new-business analysis."""
import os, glob, json
import pandas as pd, numpy as np

S = "/tmp/claude-0/-home-user-test/4450fde6-d7f1-5400-906d-a37991314de6/scratchpad"
D = f"{S}/data"
YEARS = [2023, 2024, 2025, 2026]
# months of the year that count as "complete" for monthly averages (2026 = Jan-Aug)
FULL_MONTHS = {2023: 12, 2024: 12, 2025: 12, 2026: 8}
CUTOFF = pd.Timestamp("2026-09-01", tz="UTC")   # exclude partial September 2026

def read_tsv(path, **kw):
    if not os.path.exists(path):
        return None
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False, **kw)

def num(s):
    return pd.to_numeric(s.replace("", np.nan), errors="coerce")

def dt(s):
    return pd.to_datetime(s.replace("", np.nan), utc=True, errors="coerce")

def ym(ts):
    return ts.dt.year * 100 + ts.dt.month

def in_window(ymv):
    """True if year-month is inside the study window (2023-01 .. 2026-08)."""
    return (ymv >= 202301) & (ymv <= 202608)

def load_users():
    u = read_tsv(f"{D}/users.tsv", header=None)
    u.columns = ["Id","Name","IsActive","Title","Department","Division","Role","ManagerName","StartDate",
                 "TeamCurrent","TeamLegacy","TeamCutover","TeamOverride","CreatedDate","Profile"]
    return u

def load_opps():
    frames = []
    for y in YEARS:
        f = f"{D}/opps/opps_{y}.tsv"
        if os.path.exists(f):
            frames.append(read_tsv(f))
    if not frames:
        return None
    o = pd.concat(frames, ignore_index=True)
    o = o.drop_duplicates("Id")
    o["created"] = dt(o.CreatedDate)
    o["cym"] = ym(o.created)
    o["cyr"] = o.created.dt.year
    o["funded_dts"] = dt(o.Funded_DTS__c)
    o["funded_date"] = pd.to_datetime(o.Funded_Date__c.replace("", np.nan), errors="coerce", utc=True)
    # prefer Funded_Date__c (business date) for funded-month; fall back to Funded_DTS__c
    fd = o.funded_date.fillna(o.funded_dts)
    o["fym"] = ym(fd)
    o["funded"] = o.StageName.eq("Funded")
    o["funded_amt"] = num(o.Funded_Amount__c)
    o["sbg_rev"] = num(o.SBG_Revenue__c)
    o["tot_rev"] = num(o.Total_Revenue__c)
    o["approved"] = o.Approved__c.eq("true") | o.Pre_Approved_DTS__c.ne("") | o.StageName.isin(["Pre-Approved","Contracts Out","Contracts In","Funded"])
    o["max_app"] = num(o.Max_Approval__c)
    o["largest_app"] = num(o.Largest_Approval__c)
    o["fa"] = dt(o.DE_First_Assigned_DTS__c)
    o["preapp_dts"] = dt(o.Pre_Approved_DTS__c)
    o["lost"] = o.StageName.isin(["Closed Lost","Declined"])
    o["closed_lost"] = o.StageName.eq("Closed Lost")
    o["declined"] = o.StageName.eq("Declined")
    o["lead_to_opp_days"] = (o.created - o.fa).dt.total_seconds()/86400
    o["opp_to_fund_days"] = (o.funded_dts - o.created).dt.total_seconds()/86400
    o["opp_to_approve_days"] = (o.preapp_dts - o.created).dt.total_seconds()/86400
    o["fico"] = num(o.Average_Score__c)
    o["acct_rev"] = num(o.Acct_Annual_Revenue__c)
    o["n_subs"] = num(o.No_of_Submissions__c)
    o["team_hist"] = o.DE_First_Assigned_Team__c.replace("", "Unknown")
    o["team_now"] = o.Team_Sharing_Logic__c.replace("", "Unknown")
    o["src"] = o.LeadSource.replace("", "Unknown")
    return o

def load_dir(sub):
    out = {}
    for f in glob.glob(f"{D}/{sub}/*.tsv"):
        k = os.path.basename(f)[:-4]
        out[k] = read_tsv(f)
    return out

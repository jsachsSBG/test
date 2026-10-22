"""Train, backtest and export the SOFI preapproval model.

    python3 build_dataset.py --data-dir ~/sofi_data --test-start 2026-07-01 --mature-before <today - 3 days>
    python3 train.py --data-dir ~/sofi_data --out ../../src/preapproval/model.json \
        --vectors-out ../../src/preapproval/__tests__/model-vectors.json

1. Backtest: fit on the train split (submitted deals created before --test-start), apply the full decision
   policy to the out-of-time test split and report decision + amount metrics (nothing is tuned on test).
   Also reported: lead-level metrics that count SBG pre-screen declines (never submitted) as declines,
   and SOFI new-funnel deals scored on the revenue SOFI actually sends.
2. Production fit: refit on ALL mature submitted deals; the approval intercept and the amount quantiles
   are recalibrated on the latest months, so the model tracks current lender appetite.
3. Export model + policy JSON for src/preapproval, plus parity test vectors produced by policy.py.
"""
import argparse
import datetime as dt
import hashlib
import itertools
import json
import os
import sys

import numpy as np
import pandas as pd

import harness
import model as M
import policy as PL

MODEL_VERSION_PREFIX = "sofi-preapproval-hetero"


def export_json(m, data, policy):
    E = M.export(m)
    E.pop("approve_threshold")  # superseded by policy.approve_threshold (per product)
    E["description"] = E["description"].replace("approved = p >= approve_threshold; ", "") + \
        " Decisions (knock-outs, per-product thresholds, caps, rounding, minimum) follow `policy`; see training/sofi_preapproval/policy.py."
    E["policy"] = policy
    E["training"] = {
        "rows": int(len(data)),
        "months": [str(data.ym.min()), str(data.ym.max())],
        "calibration_windows": m["windows"],
        "approval_rate_in_intercept_window": {
            P: float(data.loc[data.ym.between(*m["windows"][P]["intercept"]), f"y_{P}_approved"].mean()) for P in PL.PRODUCTS},
        "config": {k: (list(v) if isinstance(v, tuple) else v) for k, v in m["cfg"].items()},
    }
    return E


def backtest(E, te, policy):
    """Apply the full policy to every test lead; amounts compared against the lender's largest offer."""
    rows = []
    for idx, r in te.iterrows():
        score = None if pd.isna(r.score) else float(r.score)
        tib = 0.0 if pd.isna(r.tib) else float(r.tib)
        d = PL.preapprove(E, float(r.rev), score, tib, policy)
        row = {"opp": idx}
        for P in PL.PRODUCTS:
            row[f"{P}_approve"] = int(d[P]["decision"] == "approved")
            row[f"{P}_amount"] = d[P]["amount"]
            row[f"{P}_p"] = d[P]["p"]
        rows.append(row)
    b = pd.DataFrame(rows).set_index("opp").join(te)
    out = {}
    nan = float("nan")
    for P in PL.PRODUCTS:
        y, a = b[f"y_{P}_approved"].values, b[f"{P}_approve"].values
        amt = b[f"y_{P}_amt"]
        # approved deals whose largest offer was an entry error have no usable amount: left out of amount metrics
        known = ~((y == 1) & amt.isna().values)
        both = (a == 1) & (y == 1) & known
        ratio = b.loc[both, f"{P}_amount"] / amt[both]
        hit = amt[both] >= b.loc[both, f"{P}_amount"]
        we = (a == 1) & known
        out[P] = {
            "n": int(len(b)), "lender_approval_rate": float(y.mean()), "auc": harness._auc(y, b[f"{P}_p"].values),
            "approve_rate": float(a.mean()),
            "precision": float(y[a == 1].mean()) if (a == 1).any() else nan,
            "recall": float(a[y == 1].mean()) if (y == 1).any() else nan,
            "decline_precision": float(1 - y[a == 0].mean()) if (a == 0).any() else nan,
            # share of deals where both we and a lender approved, whose largest offer is >= our amount
            "coverage_given_lender_approval": float(hit.mean()) if both.any() else nan,
            "median_amount_to_actual": float(ratio.median()) if both.any() else nan,
            # share of OUR approvals where a lender offered >= our amount
            "joint_hit_rate": float(((y == 1) & (amt.fillna(0).values >= b[f"{P}_amount"].fillna(np.inf).values))[we].mean()) if we.any() else nan,
            "coverage_by_month": {k: [round(float(v.mean()), 3), int(len(v))] for k, v in hit.groupby(b.loc[both, "ym"])},
            "precision_by_month": {k: [round(float(g[f"y_{P}_approved"].mean()), 3), int(len(g))] for k, g in b[b[f"{P}_approve"] == 1].groupby("ym")},
        }
        curve = []
        for t in [0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9]:
            k = b[f"{P}_p"].values >= t
            curve.append({"threshold": t, "approve_rate": float(k.mean()), "precision": float(y[k].mean()) if k.any() else None,
                          "recall": float(k[y == 1].mean()) if (y == 1).any() else None})
        out[P]["threshold_curve"] = curve
    return out, b


def vector_inputs():
    revs = [0, 50e3, 99_999, 100e3, 150e3, 300e3, 600e3, 1.2e6, 1.8e6, 3e6, 10e6, 50e6, 1e9]
    scores = [None, 449, 450, 500, 600, 650, 700, 750, 820, 850]
    tibs = [0, 0.24, 0.25, 0.5, 1, 2, 5.08, 15, 40, 120]
    grid = list(itertools.product(revs, scores, tibs))
    # keep the file small: every 7th grid point plus every edge case on a fixed profile
    picked = grid[::7]
    picked += [(r, 700, 5.0) for r in revs] + [(1e6, s, 5.0) for s in scores] + [(1e6, 700, t) for t in tibs]
    seen, out = set(), []
    for v in picked:
        if v not in seen:
            seen.add(v); out.append(v)
    return out


def test_vectors(E, policy):
    vecs = []
    for rev, score, tib in vector_inputs():
        raw = PL.score_raw(E, rev, score, tib)
        dec = PL.preapprove(E, rev, score, tib, policy)
        vecs.append({"input": {"annualRevenue": rev, "creditScore": score, "timeInBusinessYears": tib},
                     "raw": raw, "decision": dec})
    return vecs


def rate_card(E, policy):
    rows = []
    for rev, score, tib in itertools.product([150e3, 250e3, 400e3, 600e3, 800e3, 1e6, 1.5e6, 2e6, 3e6, 5e6],
                                             [550, 600, 650, 700, 750, 800], [1, 2, 3, 5, 10]):
        d = PL.preapprove(E, rev, score, tib, policy)
        rows.append({"annual_revenue": rev, "credit_score": score, "tib_years": tib,
                     **{f"{P}_{k}": d[P][k2] for P in PL.PRODUCTS for k, k2 in
                        [("decision", "decision"), ("amount", "amount"), ("typical", "typical_amount"), ("p", "p")]}})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", required=True, help="path of the exported model JSON (src/preapproval/model.json)")
    ap.add_argument("--vectors-out", required=True, help="parity test vectors for the TypeScript port")
    ap.add_argument("--report-dir", default=None, help="where to write backtest/rate-card artifacts (default: data dir)")
    a = ap.parse_args()
    report_dir = a.report_dir or a.data_dir
    os.makedirs(report_dir, exist_ok=True)

    d = harness.load(os.path.join(a.data_dir, "model_data.pkl"))
    tr, te = harness.split(d)
    if tr.empty or te.empty:
        sys.exit("train.py: the train or test split is empty - rebuild the dataset with a --test-start inside the data")

    # 1. out-of-time backtest of the whole procedure
    m_bt = M.fit(tr)
    E_bt = export_json(m_bt, tr, PL.POLICY)
    rep_raw = harness.evaluate(M.predict(m_bt, te), te, "backtest/raw-model")
    bt, _ = backtest(E_bt, te, PL.POLICY)
    bt_lead, _ = backtest(E_bt, harness.lead_level_test(d), PL.POLICY)
    nf = harness.new_funnel_view(te)
    if nf.empty:
        print("warning: no SOFI new-funnel deals in the test split; new-funnel backtest skipped")
        rep_nf, bt_nf = None, None
    else:
        rep_nf = harness.evaluate(M.predict(m_bt, nf), nf, "backtest/new-funnel")
        bt_nf, _ = backtest(E_bt, nf, PL.POLICY)

    # 2. production fit on all mature submitted deals
    d_sub = d[d.submitted]
    m = M.fit(d_sub)
    E = export_json(m, d_sub, PL.POLICY)
    E["trained_on"] = dt.date.today().isoformat()
    digest = hashlib.sha256(json.dumps({"products": E["products"], "policy": E["policy"]}, sort_keys=True).encode()).hexdigest()[:8]
    E["model_version"] = f"{MODEL_VERSION_PREFIX}-{d_sub.ym.max()}-{digest}"
    with open(a.out, "w") as f:
        json.dump(E, f, indent=1, allow_nan=False)
    with open(a.vectors_out, "w") as f:
        json.dump({"model_version": E["model_version"], "vectors": test_vectors(E, PL.POLICY)}, f, allow_nan=False)

    bt_report = {
        "model_version": E["model_version"],
        "backtest_train_months": [str(tr.ym.min()), str(tr.ym.max())],
        "backtest_test_months": [str(te.ym.min()), str(te.ym.max())],
        "policy_backtest": bt, "policy_backtest_lead_level": bt_lead, "policy_backtest_new_funnel": bt_nf,
        "raw_model_summary": harness.summary(rep_raw), "raw_model_new_funnel_summary": harness.summary(rep_nf) if rep_nf else None,
        "raw_model_report": rep_raw,
    }
    with open(os.path.join(report_dir, "backtest.json"), "w") as f:
        json.dump(bt_report, f, indent=1, default=float)
    rate_card(E, PL.POLICY).to_csv(os.path.join(report_dir, "rate_card.csv"), index=False)

    for label, res in [("submitted deals", bt), ("all leads (pre-screen declines count as declines)", bt_lead),
                       ("new funnel, SOFI revenue", bt_nf)]:
        if res is None:
            continue
        print(f"backtest, {label}:")
        for P in PL.PRODUCTS:
            r = res[P]
            print(f"  {P}: n {r['n']} approve {r['approve_rate']:.3f} precision {r['precision']:.3f} recall {r['recall']:.3f} "
                  f"decline-precision {r['decline_precision']:.3f} auc {r['auc']:.3f} coverage {r['coverage_given_lender_approval']:.3f} "
                  f"amount/actual {r['median_amount_to_actual']:.3f} promise-kept {r['joint_hit_rate']:.3f}")
    print("calibration windows:", json.dumps(m["windows"]))
    print("wrote", a.out, E["model_version"])


if __name__ == "__main__":
    main()

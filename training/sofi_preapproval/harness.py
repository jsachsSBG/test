"""Shared evaluation harness for SOFI preapproval candidates.

Every candidate must expose:
    fit(train_df) -> model
    predict(model, df) -> DataFrame indexed like df with, for P in {tlmca, locr}:
        p_P          probability the lender side approves product group P (0..1)
        approve_P    0/1 decision the candidate recommends
        amt_P_point  point estimate of the largest approval (median-type)
        amt_P_q10, amt_P_q15, amt_P_q20  conservative amounts: lender's largest approval
                     should be >= this amount ~90% / 85% / 80% of the time (given approval)

Allowed model inputs: rev, score, tib ONLY (annual revenue, average credit score, TIB in years).
Never use rev_true, rev_sofi_orig, stage, y_* or funded_amt as features.

Product groups: tlmca = Term Loan + MCA (largest offer across both),
                locr  = Line of Credit + Revolving MCA.

Usage:
    import harness
    data = harness.load('<data-dir>/model_data.pkl')
    train, test = harness.split(data)
    model = fit(train); pred = predict(model, test)
    report = harness.evaluate(pred, test)            # out-of-time test
    nf = harness.new_funnel_view(test)               # rev replaced by SOFI's granular stated revenue
    report_nf = harness.evaluate(predict(model, nf), nf)
"""
import json

import numpy as np
import pandas as pd

PRODUCTS = ['tlmca', 'locr']
QUANTS = {'q10': 0.90, 'q15': 0.85, 'q20': 0.80}  # name -> target coverage
FEATURES = ['rev', 'score', 'tib']

REV_BANDS = [0, 250e3, 500e3, 1e6, 2e6, np.inf]
SCORE_BANDS = [0, 600, 650, 700, 750, 900]
TIB_BANDS = [-np.inf, 2, 5, 10, np.inf]


def load(path):
    d = pd.read_pickle(path).copy()
    d.loc[d.score < 300, 'score'] = np.nan
    return d


def split(d):
    """Train/test rows among deals submitted to lenders (the population the model is fit on)."""
    if 'submitted' in d:
        d = d[d.submitted]
    return d[d.split == 'train'].copy(), d[d.split == 'test'].copy()


def all_opportunities_test(d):
    """All mature test-period SOFI opportunities, including SBG pre-screen declines that never reached a lender."""
    return d[d.split == 'test'].copy()


def new_funnel_view(d):
    """Rows from SOFI's new funnel with rev swapped to what SOFI actually sends (granular stated revenue)."""
    x = d[d.new_funnel].copy()
    x['rev'] = x['rev_sofi_orig']
    return x


def _auc(y, p):
    y = np.asarray(y); p = np.asarray(p)
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float('nan')
    r = pd.Series(np.concatenate([pos, neg])).rank().values
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def _band(s, edges):
    return pd.cut(s, edges, right=False).astype(str)


def evaluate(pred, df, label=''):
    pred = pred.reindex(df.index)
    out = {'label': label, 'n': int(len(df))}
    for P in PRODUCTS:
        y = df[f'y_{P}_approved'].values
        p = pred[f'p_{P}'].clip(0, 1).values
        a = pred[f'approve_{P}'].astype(int).values
        r = {'base_rate': float(y.mean()), 'auc': _auc(y, p), 'brier': float(np.mean((p - y) ** 2))}
        r['decision'] = {
            'approve_rate': float(a.mean()),
            'precision': float(y[a == 1].mean()) if a.sum() else float('nan'),
            'recall': float(a[y == 1].mean()) if y.sum() else float('nan'),
            'decline_precision': float(1 - y[a == 0].mean()) if (a == 0).sum() else float('nan'),
            'accuracy': float(np.mean(a == y)),
        }
        curve = []
        for t in [0.3, 0.4, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]:
            k = p >= t
            curve.append({'t': t, 'approve_rate': float(k.mean()),
                          'precision': float(y[k].mean()) if k.sum() else float('nan')})
        r['threshold_curve'] = curve

        ok = (y == 1) & df[f'y_{P}_amt'].notna().values  # implausible offer amounts are excluded
        act = df.loc[ok, f'y_{P}_amt'].values
        amt = {}
        pt = pred.loc[ok, f'amt_{P}_point'].values
        ratio = pt / act
        ape = np.abs(ratio - 1)
        ly, lp = np.log(act), np.log(np.clip(pt, 1, None))
        amt['point'] = {
            'median_ape': float(np.median(ape)), 'mean_ape': float(np.mean(ape)),
            'within_10pct': float(np.mean(ape <= .10)), 'within_20pct': float(np.mean(ape <= .20)),
            'within_30pct': float(np.mean(ape <= .30)), 'median_ratio': float(np.median(ratio)),
            'log_r2': float(1 - np.sum((ly - lp) ** 2) / np.sum((ly - ly.mean()) ** 2)),
        }
        for qn, target in QUANTS.items():
            c = pred.loc[ok, f'amt_{P}_{qn}'].values
            cov = act >= c
            seg = {}
            sub = df.loc[ok].assign(_cov=cov)
            for name, col, edges in [('rev', 'rev', REV_BANDS), ('score', 'score', SCORE_BANDS), ('tib', 'tib', TIB_BANDS)]:
                g = sub.groupby(_band(sub[col], edges))['_cov'].agg(['mean', 'size'])
                seg[name] = {k: [round(float(v['mean']), 3), int(v['size'])] for k, v in g.iterrows()}
            gm = sub.groupby('ym')['_cov'].agg(['mean', 'size'])
            seg['month'] = {k: [round(float(v['mean']), 3), int(v['size'])] for k, v in gm.iterrows()}
            devs = [abs(v[0] - target) for s in ('rev', 'score', 'tib') for v in seg[s].values() if v[1] >= 50]
            amt[qn] = {
                'target_coverage': target, 'coverage': float(cov.mean()),
                'median_ratio_to_actual': float(np.median(c / act)),
                'mean_ratio_to_actual': float(np.mean(c / act)),
                'max_segment_dev': float(max(devs)) if devs else float('nan'),
                'segments': seg,
            }
        # joint: of leads we tell "approved", share where a lender approved >= our q15 amount
        # approved deals whose amount was excluded as an entry error are left out, as in train.backtest
        k = (a == 1) & ~((y == 1) & df[f'y_{P}_amt'].isna().values)
        if k.sum():
            q15 = pred.loc[k, f'amt_{P}_q15'].values
            actual_all = df.loc[k, f'y_{P}_amt'].fillna(0).values
            r['joint_q15_hit_rate'] = float(np.mean(actual_all >= q15))
        r['amount'] = amt
        out[P] = r
    return out


def summary(rep):
    """Compact one-screen summary of an evaluate() report."""
    s = {'label': rep['label'], 'n': rep['n']}
    for P in PRODUCTS:
        r = rep[P]
        s[P] = {
            'auc': round(r['auc'], 3), 'base_rate': round(r['base_rate'], 3),
            'approve_rate': round(r['decision']['approve_rate'], 3), 'precision': round(r['decision']['precision'], 3),
            'accuracy': round(r['decision']['accuracy'], 3),
            'joint_q15_hit': round(r.get('joint_q15_hit_rate', float('nan')), 3),
            'point_medAPE': round(r['amount']['point']['median_ape'], 3),
            'point_within20': round(r['amount']['point']['within_20pct'], 3),
            'point_logR2': round(r['amount']['point']['log_r2'], 3),
        }
        for qn in QUANTS:
            q = r['amount'][qn]
            s[P][qn] = {'cov': round(q['coverage'], 3), 'med_ratio': round(q['median_ratio_to_actual'], 3),
                        'max_seg_dev': round(q['max_segment_dev'], 3)}
    return s


def save(rep, path):
    with open(path, 'w') as f:
        json.dump(rep, f, indent=1, default=float)

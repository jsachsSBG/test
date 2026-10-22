"""hetero_lognormal: heteroscedastic location-scale model of log(largest approval) + monotone logistic GAM.

Inputs: rev (annual revenue), score (avg owner credit score), tib (years in business). Nothing else.

Transforms (all clipped, so absurd inputs extrapolate flat):
    lr = ln(clip(rev, REV_LO, REV_HI))            rev missing/<=0 -> REV_LO
    s  = clip(score, S_LO, S_HI)                   score missing/<300 -> S_MISSING (conservative imputation)
    t  = ln(1 + clip(tib, T_LO, T_HI))             tib missing -> T_LO
Basis: per variable a piecewise-linear "segment" spline basis on knots k_0 < ... < k_K (k_0 / k_K = clip bounds):
    phi_j(x) = clip((x - k_j) / (k_{j+1} - k_j), 0, 1)      j = 0..K-1
    f(x) = sum_j c_j * phi_j(x)   (c_j = rise of f across segment j;  all c_j >= 0  <=>  f non-decreasing)
Smoothness: ridge penalty on second differences of the segment slopes (P-spline style, on the [0,1]-normalised axis).

For each product P in {tlmca, locr}:
  approval  logit p = a0 + sum_v f_v^a(x_v)           monotone logistic GAM (a_j >= 0), recency weighted,
            intercept re-calibrated on the most recent `cal_months` of training data (mean p = observed rate).
  location  mu(x)    = m0 + sum_v f_v^m(x_v)          monotone (c_j >= 0), Huber-robust, recency + 1/sigma^2 weighted LS
  scale     sigma(x) = max(SIG_FLOOR, d0 + sum_v f_v^d(x_v))  additive model of the residual scale (E|r| or the
            downside semi-scale E[max(-r,0)]); its segment rises are box-bounded so that every quantile below is
            monotone:  c^m_j + c_q * c^d_j >= 0 for all c_q in [C_LO, C_HI].
  amounts   amt_q(x) = exp(mu(x) + c_q * sigma(x)),   c_q = EMPIRICAL quantile of z = (y - mu)/sigma on the most recent
            `cal_months` of training data (split-conformal; q10 -> 10th pct, q15 -> 15th, q20 -> 20th, point -> median).
"""
import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear, minimize

PRODUCTS = ['tlmca', 'locr']
QLEVELS = {'q10': 0.10, 'q15': 0.15, 'q20': 0.20, 'point': 0.50}

DEFAULT = dict(
    rev_clip=(50e3, 25e6),
    rev_knots=[100e3, 150e3, 200e3, 300e3, 450e3, 700e3, 1e6, 1.5e6, 2.5e6, 4e6, 7e6, 12e6],
    score_clip=(480., 840.),
    score_knots=[540., 580., 620., 660., 700., 740., 780.],
    score_missing=480.,      # missing / <300 scores sit at the floor so they can never beat a real score
    tib_clip=(0.25, 40.),
    tib_knots=[0.5, 1., 1.5, 2., 3., 5., 8., 12., 20.],
    half_life_months=9.0,     # recency weight half-life (months before the last month of the fitting data); None = flat
    cal_months=4,             # most recent months of the fitting data used for conformal c_q + p intercept
    conf_mode='insample',     # 'insample' : fit mu/sigma on all data, c_q from residuals on the window
                              # 'holdout'  : fit mu/sigma excluding the window, c_q on window, keep that (stale) fit
                              # 'holdout_refit': c_q from holdout as above, then refit mu/sigma on all data
    sigma_kind='abs',         # 'abs' : sigma = E[|r| | x];  'neg': sigma = E[max(-r, 0) | x] (downside semi-scale)
                              # 'const': homoscedastic (sigma = constant) - ablation
    hetero_iters=2,           # number of (mu WLS with 1/sigma^2 weights -> sigma) refinements; 0 = unweighted mu
    huber_k=2.0,              # Huber threshold on standardized residuals for the mu fit
    lam_mu=1e-6, lam_sig=1e-5, lam_logit=1e-6,   # smoothness penalties (relative to sum of weights = n)
    ridge_logit=1e-6,         # small L2 on logit coefficients (relative to n)
    p_recal='intercept',      # 'intercept' | 'none'
    sig_floor=0.05,
    c_guard=(-2.5, 0.25),     # guard range for c_q: [g_lo*|z_q10|, z_q50 + g_hi*|z_q10|] of provisional train z
    conf_weighted=False,      # recency-weight the empirical quantile inside the window
    placeholder_revs=(1.8e6,),  # historical banded placeholder revenue values in the training proxy `rev`
    placeholder_fit_weight=1.0, # weight of those rows in the mu/sigma fit (1 = treat like any other row)
    placeholder_in_conformal=True,  # include those rows when estimating c_q on the window
)


# ---------------------------------------------------------------------------------------------- basis
class Basis:
    VARS = ('lr', 's', 't')

    def __init__(self, cfg):
        self.cfg = cfg
        rlo, rhi = cfg['rev_clip']; slo, shi = cfg['score_clip']; tlo, thi = cfg['tib_clip']
        spec = {
            'lr': (np.log(rlo), np.log(rhi), [np.log(k) for k in cfg['rev_knots']]),
            's': (slo, shi, list(cfg['score_knots'])),
            't': (np.log1p(tlo), np.log1p(thi), [np.log1p(k) for k in cfg['tib_knots']]),
        }
        self.k = {}
        for v, (lo, hi, kn) in spec.items():
            self.k[v] = np.array([lo] + [x for x in kn if lo < x < hi] + [hi], dtype=float)
        self.sizes = [len(self.k[v]) - 1 for v in self.VARS]
        self.p = int(sum(self.sizes))
        self.slices = {}
        o = 0
        for v, sz in zip(self.VARS, self.sizes):
            self.slices[v] = slice(o, o + sz); o += sz

    def transform(self, df):
        c = self.cfg
        rev = pd.to_numeric(df['rev'], errors='coerce').astype(float).values
        rev = np.where(np.isfinite(rev) & (rev > 0), rev, c['rev_clip'][0])
        sc = pd.to_numeric(df['score'], errors='coerce').astype(float).values
        sc = np.where(np.isfinite(sc) & (sc >= 300), sc, c['score_missing'])
        tib = pd.to_numeric(df['tib'], errors='coerce').astype(float).values
        tib = np.where(np.isfinite(tib), tib, c['tib_clip'][0])
        return {'lr': np.log(np.clip(rev, *c['rev_clip'])),
                's': np.clip(sc, *c['score_clip']),
                't': np.log1p(np.clip(tib, *c['tib_clip']))}

    def matrix(self, df):
        x = self.transform(df)
        cols = []
        for v in self.VARS:
            k = self.k[v]
            xv = x[v][:, None]
            cols.append(np.clip((xv - k[:-1][None, :]) / np.diff(k)[None, :], 0., 1.))
        return np.hstack(cols)

    def penalty(self):
        """Rows of D such that ||D c||^2 ~ integral of f''^2 on the [0,1]-normalised axis of each variable."""
        rows = []
        for v in self.VARS:
            k = self.k[v]
            u = (k - k[0]) / (k[-1] - k[0])
            w = np.diff(u)
            sl = self.slices[v]
            for j in range(len(w) - 1):
                r = np.zeros(self.p)
                h = np.sqrt(0.5 * (w[j] + w[j + 1]))
                # slope_j = c_j / w_j
                r[sl.start + j] = -1.0 / w[j] / h
                r[sl.start + j + 1] = 1.0 / w[j + 1] / h
                rows.append(r)
        return np.array(rows)


# ---------------------------------------------------------------------------------------------- helpers
def _month_index(ym):
    s = pd.Series(ym).astype(str)
    return (s.str[:4].astype(int) * 12 + s.str[5:7].astype(int)).values


def _recency_weights(ym, half_life):
    mi = _month_index(ym)
    if half_life is None:
        w = np.ones(len(mi))
    else:
        w = 0.5 ** ((mi.max() - mi) / float(half_life))
    return w / w.mean()


def _wquantile(x, q, w=None):
    x = np.asarray(x, float)
    if w is None:
        return float(np.quantile(x, q))
    o = np.argsort(x); x = x[o]; w = np.asarray(w, float)[o]
    cw = (np.cumsum(w) - 0.5 * w) / w.sum()
    return float(np.interp(q, cw, x))


def _bounded_ls(B, y, w, D, lam, lb, ub):
    """min sum w (y - b0 - B c)^2 + lam*n*||D c||^2  s.t. lb <= c <= ub (b0 free). Returns (b0, c)."""
    n, p = B.shape
    lb = np.asarray(lb, float); ub = np.asarray(ub, float)
    fixed = (ub - lb) <= 1e-12            # e.g. sigma rise forced to 0 where mu is flat
    c = np.where(fixed, lb, 0.0)
    free = ~fixed
    sw = np.sqrt(w)
    yy = y - B[:, fixed] @ c[fixed]
    pen_off = -(np.sqrt(lam * n) * D[:, fixed]) @ c[fixed]
    A = np.vstack([np.hstack([sw[:, None], B[:, free] * sw[:, None]]),
                   np.hstack([np.zeros((D.shape[0], 1)), np.sqrt(lam * n) * D[:, free]])])
    b = np.concatenate([sw * yy, pen_off])
    lo = np.concatenate([[-np.inf], lb[free]]); hi = np.concatenate([[np.inf], ub[free]])
    res = lsq_linear(A, b, bounds=(lo, hi), method='bvls', max_iter=2000)
    c[free] = res.x[1:]
    return float(res.x[0]), c


def _fit_logit(B, y, w, D, lam, ridge):
    n, p = B.shape
    P = lam * n * (D.T @ D) + ridge * n * np.eye(p)
    ybar = np.clip(np.average(y, weights=w), 1e-4, 1 - 1e-4)
    x0 = np.concatenate([[np.log(ybar / (1 - ybar))], np.zeros(p)])

    def f(th):
        eta = th[0] + B @ th[1:]
        # logloss = log(1+e^eta) - y*eta
        ll = np.sum(w * (np.logaddexp(0, eta) - y * eta))
        pr = 1. / (1. + np.exp(-eta))
        g = w * (pr - y)
        grad = np.concatenate([[g.sum()], B.T @ g + P @ th[1:]])
        return ll + 0.5 * th[1:] @ P @ th[1:], grad

    bounds = [(None, None)] + [(0., None)] * p
    r = minimize(f, x0, jac=True, method='L-BFGS-B', bounds=bounds, options={'maxiter': 5000, 'gtol': 1e-8})
    return float(r.x[0]), r.x[1:]


def _sigmoid(z):
    return 1. / (1. + np.exp(-z))


# ---------------------------------------------------------------------------------------------- amount model
def _fit_location_scale(B, y, w, D, cfg):
    """Returns dict(m0, cm, d0, cd, guards) for mu and sigma, with monotonicity guards on sigma."""
    p = B.shape[1]
    lb_m, ub_m = np.zeros(p), np.full(p, np.inf)
    # --- initial mu: Huber IRLS, homoscedastic
    hw = np.ones(len(y))
    sig = np.ones(len(y))
    for it in range(4):
        m0, cm = _bounded_ls(B, y, w * hw / sig ** 2 * np.mean(sig ** 2), D, cfg['lam_mu'], lb_m, ub_m)
        r = y - m0 - B @ cm
        s = 1.4826 * np.median(np.abs(r - np.median(r)))
        z = np.abs(r) / (s * sig / np.mean(sig))
        hw = np.minimum(1., cfg['huber_k'] / np.maximum(z, 1e-12))
    # winsorized residuals for the scale fit (upper outliers are data errors like 1e11 offers)
    s_rob = 1.4826 * np.median(np.abs(r - np.median(r)))

    def scale_target(r):
        rr = np.clip(r, -5 * s_rob, 5 * s_rob)
        if cfg['sigma_kind'] == 'neg':
            return np.maximum(-rr, 0.)
        return np.abs(rr)

    guards = None
    d0, cd = None, None
    n_outer = max(1, int(cfg['hetero_iters']))
    for it in range(n_outer):
        tgt = scale_target(r)
        if cfg['sigma_kind'] == 'const':
            d0, cd = float(np.average(tgt, weights=w)), np.zeros(p)
        else:
            # pass 1: unconstrained sigma (only to derive provisional z-quantiles -> guard range)
            d0u, cdu = _bounded_ls(B, tgt, w, D, cfg['lam_sig'], np.full(p, -np.inf), np.full(p, np.inf))
            su = np.maximum(cfg['sig_floor'], d0u + B @ cdu)
            zu = r / su
            zq_lo = min(np.quantile(zu, 0.10), -1e-3)
            zq_hi = max(np.quantile(zu, 0.50), 0.0)
            # guard: allow c_q as low as g_lo x the provisional q10 and as high as the provisional median
            # + g_hi x |provisional q10|; final conformal c_q are clipped into this range.
            c_lo = cfg['c_guard'][0] * abs(zq_lo)
            c_hi = max(zq_hi + cfg['c_guard'][1] * abs(zq_lo), 0.05)
            guards = (float(c_lo), float(c_hi))
            # monotone bounds: cm_j + c * cd_j >= 0 for c in [c_lo, c_hi]
            ub_d = cm / abs(c_lo)
            lb_d = -cm / c_hi
            d0, cd = _bounded_ls(B, tgt, w, D, cfg['lam_sig'], lb_d, ub_d)
        sig = np.maximum(cfg['sig_floor'], d0 + B @ cd)
        if cfg['hetero_iters'] == 0 or it == n_outer - 1:
            break
        # --- refit mu with 1/sigma^2 weights (heteroscedastic WLS) + Huber on standardized residuals
        hw = np.ones(len(y))
        for jt in range(3):
            ww = w * hw / sig ** 2
            ww = ww / ww.mean()
            m0, cm = _bounded_ls(B, y, ww, D, cfg['lam_mu'], lb_m, ub_m)
            r = y - m0 - B @ cm
            z = r / sig
            zs = 1.4826 * np.median(np.abs(z - np.median(z)))
            hw = np.minimum(1., cfg['huber_k'] / np.maximum(np.abs(z) / zs, 1e-12))
    if guards is None:
        guards = (-1e9, 1e9)
    return dict(m0=m0, cm=cm, d0=d0, cd=cd, guards=guards)


def _ls_eval(ls, B, floor):
    mu = ls['m0'] + B @ ls['cm']
    sig = np.maximum(floor, ls['d0'] + B @ ls['cd'])
    return mu, sig


# ---------------------------------------------------------------------------------------------- fit / predict
def fit(train_df, cfg=None):
    cfg = dict(DEFAULT, **(cfg or {}))
    basis = Basis(cfg)
    D = basis.penalty()
    df = train_df
    mi = _month_index(df['ym'])
    last = mi.max()
    in_win = mi > last - cfg['cal_months']
    w_all = _recency_weights(df['ym'], cfg['half_life_months'])
    B_all = basis.matrix(df)
    model = {'cfg': cfg, 'basis': basis, 'cal_window': (str(df['ym'][in_win].min()), str(df['ym'][in_win].max()))}
    for P in PRODUCTS:
        y_ap = df[f'y_{P}_approved'].values.astype(float)
        # ---------------- approval (logistic GAM, monotone)
        a0, ca = _fit_logit(B_all, y_ap, w_all, D, cfg['lam_logit'], cfg['ridge_logit'])
        if cfg['p_recal'] == 'intercept':
            eta = a0 + B_all[in_win] @ ca
            target = y_ap[in_win].mean()
            lo, hi = -5., 5.
            for _ in range(80):
                mid = 0.5 * (lo + hi)
                if _sigmoid(eta + mid).mean() > target:
                    hi = mid
                else:
                    lo = mid
            a0 = a0 + 0.5 * (lo + hi)
        model[P, 'logit'] = (a0, ca)

        # ---------------- amounts
        ok = y_ap == 1
        amt = df[f'y_{P}_amt'].values
        yl = np.log(np.clip(amt, 100., None))
        is_ph = np.isin(pd.to_numeric(df['rev'], errors='coerce').values, np.asarray(cfg['placeholder_revs'], float))
        w_amt = w_all * np.where(is_ph, cfg['placeholder_fit_weight'], 1.0)
        if cfg['conf_mode'] in ('holdout', 'holdout_refit'):
            fit_mask = ok & ~in_win & (w_amt > 0)
        else:
            fit_mask = ok & (w_amt > 0)
        wf = w_amt[fit_mask] / w_amt[fit_mask].mean()
        ls = _fit_location_scale(B_all[fit_mask], yl[fit_mask], wf, D, cfg)
        # conformal: empirical standardized-residual quantiles on the window
        cw = ok & in_win
        if not cfg['placeholder_in_conformal']:
            cw = cw & ~is_ph
        mu_c, sig_c = _ls_eval(ls, B_all[cw], cfg['sig_floor'])
        z = (yl[cw] - mu_c) / sig_c
        wq = w_all[cw] if cfg['conf_weighted'] else None
        cq = {qn: _wquantile(z, q, wq) for qn, q in QLEVELS.items()}
        if cfg['conf_mode'] == 'holdout_refit':
            fm = ok & (w_amt > 0)
            ls = _fit_location_scale(B_all[fm], yl[fm], w_amt[fm] / w_amt[fm].mean(), D, cfg)
        g_lo, g_hi = ls['guards']
        cq_raw = dict(cq)
        cq = {k: float(np.clip(v, g_lo, g_hi)) for k, v in cq.items()}
        model[P, 'ls'] = ls
        model[P, 'cq'] = cq
        model[P, 'cq_raw'] = cq_raw
        model[P, 'n_cal'] = int(cw.sum())
    return model


def predict(model, df):
    cfg = model['cfg']; basis = model['basis']
    B = basis.matrix(df)
    o = pd.DataFrame(index=df.index)
    for P in PRODUCTS:
        a0, ca = model[P, 'logit']
        o[f'p_{P}'] = _sigmoid(a0 + B @ ca)
        o[f'approve_{P}'] = (o[f'p_{P}'] >= 0.5).astype(int)
        mu, sig = _ls_eval(model[P, 'ls'], B, cfg['sig_floor'])
        for qn in ('q10', 'q15', 'q20', 'point'):
            o[f'amt_{P}_{qn}'] = np.exp(mu + model[P, 'cq'][qn] * sig)
        o[f'mu_{P}'] = mu
        o[f'sigma_{P}'] = sig
    return o


# ---------------------------------------------------------------------------------------------- export
def export(model):
    cfg = model['cfg']; basis = model['basis']
    names = {'lr': 'ln_rev', 's': 'score', 't': 'ln1p_tib'}
    raw_knots = {'lr': np.exp(basis.k['lr']), 's': basis.k['s'], 't': np.expm1(basis.k['t'])}
    out = {
        'model': 'hetero_lognormal',
        'description': (
            'Inputs rev (annual revenue $), score (avg owner credit score), tib (years in business). '
            'x_rev = ln(clip(rev, REV_LO, REV_HI)) [rev missing/<=0 -> REV_LO]; '
            'x_score = clip(score, S_LO, S_HI) [score missing or < 300 -> score_missing]; '
            'x_tib = ln(1 + clip(tib, T_LO, T_HI)) [tib missing -> T_LO]. '
            'For each variable v with knots k[0..K] (k[0], k[K] = clip bounds, in transformed units): '
            'phi_j = clip((x_v - k[j]) / (k[j+1] - k[j]), 0, 1), j = 0..K-1, and f_v(c) = sum_j c[j] * phi_j. '
            'Per product P: p = 1/(1+exp(-(logit.intercept + f_rev(logit.rev) + f_score(logit.score) + f_tib(logit.tib)))); '
            'approved = p >= approve_threshold; '
            'mu = mu.intercept + f_rev(mu.rev) + f_score(mu.score) + f_tib(mu.tib); '
            'sigma = max(sigma_floor, sigma.intercept + f_rev(sigma.rev) + f_score(sigma.score) + f_tib(sigma.tib)); '
            'amount_q = exp(mu + c[q] * sigma) for q in q10 (90% coverage), q15 (85%), q20 (80%), point (median). '
            'Round amounts DOWN to the business step after computing.'),
        'inputs': {
            'rev': {'transform': 'ln', 'clip': list(cfg['rev_clip']), 'missing': cfg['rev_clip'][0]},
            'score': {'transform': 'identity', 'clip': list(cfg['score_clip']), 'missing': cfg['score_missing'],
                      'treat_below_300_as_missing': True},
            'tib': {'transform': 'ln1p', 'clip': list(cfg['tib_clip']), 'missing': cfg['tib_clip'][0]},
        },
        'knots': {names[v]: [float(x) for x in basis.k[v]] for v in basis.VARS},
        'knots_raw_units': {v2: [float(x) for x in raw_knots[v]] for v, v2 in zip(basis.VARS, ['rev', 'score', 'tib'])},
        'sigma_floor': cfg['sig_floor'],
        'approve_threshold': 0.5,
        'products': {},
    }

    def split_coefs(c):
        return {nm: [float(x) for x in c[basis.slices[v]]] for v, nm in zip(basis.VARS, ['rev', 'score', 'tib'])}

    for P in PRODUCTS:
        a0, ca = model[P, 'logit']
        ls = model[P, 'ls']
        out['products'][P] = {
            'logit': dict(intercept=float(a0), **split_coefs(ca)),
            'mu': dict(intercept=float(ls['m0']), **split_coefs(ls['cm'])),
            'sigma': dict(intercept=float(ls['d0']), **split_coefs(ls['cd'])),
            'c': {k: float(v) for k, v in model[P, 'cq'].items()},
        }
    return out

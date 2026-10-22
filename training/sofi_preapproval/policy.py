"""Reference implementation of the SOFI preapproval decision, scored ONLY from the exported model JSON.

src/preapproval/*.ts must reproduce `preapprove()` to floating-point precision (V8 and libm exp/log can differ in the
last ulp, which only matters for inputs sitting exactly on a threshold or rounding boundary); train.py writes its
outputs as parity test vectors.
"""
import math

PRODUCTS = ("tlmca", "locr")

POLICY = {
    # Hard knock-outs (decline both products) at the invalid / extreme edges only; the model handles the rest.
    "knockouts": {"min_revenue": 100_000, "min_score": 450, "min_tib_years": 0.25},
    # Approve when the modeled lender-approval probability reaches this threshold
    "approve_threshold": {"tlmca": 0.70, "locr": 0.50},
    # Preapproval amount = q15 head: lenders' largest approval meets or beats it ~85% of the time
    "amount_quantile": "q15",
    "coverage_target": 0.85,
    "max_amount": {"tlmca": 250_000, "locr": 150_000},
    "max_pct_of_revenue": 0.15,
    "min_amount": 5_000,
    # Round DOWN: amounts below `below` use `step`; the last tier has no upper bound
    "rounding": [{"below": 10_000, "step": 500}, {"below": 50_000, "step": 1_000},
                 {"below": 250_000, "step": 5_000}, {"below": None, "step": 10_000}],
    # Profile used to name the weakest factor behind a low-probability decline
    "reference_profile": {"rev": 1_000_000, "score": 700, "tib": 5},
}

FACTOR_LABELS = {"rev": "annual revenue", "score": "credit score", "tib": "time in business"}


def _pct(x):
    """Whole percent, rounding half up (matches Math.round in the TypeScript port)."""
    return int(math.floor(x * 100 + 0.5))


def _usd(n):
    return f"${int(n):,}"


def _clip(x, lo, hi):
    return min(hi, max(lo, x))


def features(E, rev, score, tib):
    I = E["inputs"]
    r = rev if rev is not None and math.isfinite(rev) and rev > 0 else I["rev"]["missing"]
    s = score if score is not None and math.isfinite(score) and score >= 300 else I["score"]["missing"]
    t = tib if tib is not None and math.isfinite(tib) else I["tib"]["missing"]
    return {"rev": math.log(_clip(r, *I["rev"]["clip"])),
            "score": _clip(s, *I["score"]["clip"]),
            "tib": math.log1p(_clip(t, *I["tib"]["clip"]))}


KNOT_KEYS = {"rev": "ln_rev", "score": "score", "tib": "ln1p_tib"}


def seg(knots, c, x):
    return sum(c[j] * _clip((x - knots[j]) / (knots[j + 1] - knots[j]), 0.0, 1.0) for j in range(len(c)))


def terms(E, head, x):
    return {v: seg(E["knots"][KNOT_KEYS[v]], head[v], x[v]) for v in ("rev", "score", "tib")}


def linear(E, head, x):
    return head["intercept"] + sum(terms(E, head, x).values())


def score_raw(E, rev, score, tib):
    """Raw model outputs per product: p, mu, sigma and the four amount heads."""
    x = features(E, rev, score, tib)
    out = {}
    for P in PRODUCTS:
        M = E["products"][P]
        p = 1.0 / (1.0 + math.exp(-linear(E, M["logit"], x)))
        mu = linear(E, M["mu"], x)
        sigma = max(E["sigma_floor"], linear(E, M["sigma"], x))
        out[P] = {"p": p, **{q: math.exp(mu + M["c"][q] * sigma) for q in ("q10", "q15", "q20", "point")}}
    return out


def round_down(amount, tiers):
    for t in tiers:
        if t["below"] is None or amount < t["below"]:
            return math.floor(amount / t["step"]) * t["step"]
    raise ValueError("rounding tiers must end with an unbounded tier")


def _weakest_factor(E, P, x, policy):
    ref = features(E, *(policy["reference_profile"][k] for k in ("rev", "score", "tib")))
    head = E["products"][P]["logit"]
    tx, tr = terms(E, head, x), terms(E, head, ref)
    gaps = {v: tx[v] - tr[v] for v in tx}
    v = min(gaps, key=gaps.get)
    return v if gaps[v] < 0 else None


def preapprove(E, rev, score, tib, policy=POLICY):
    """Decision for one lead. Inputs are already-validated numbers (score may be None)."""
    ko = policy["knockouts"]
    knock = []
    if rev < ko["min_revenue"]:
        knock.append(f"Annual revenue below {_usd(ko['min_revenue'])}")
    if score is None:
        knock.append("Credit score missing or invalid")
    elif score < ko["min_score"]:
        knock.append(f"Credit score below {ko['min_score']}")
    if tib < ko["min_tib_years"]:
        knock.append(f"Time in business under {ko['min_tib_years']} years")

    raw = score_raw(E, rev, score, tib)
    x = features(E, rev, score, tib)
    res = {}
    for P in PRODUCTS:
        r = raw[P]
        out = {"decision": "declined", "amount": None, "typical_amount": None, "p": r["p"], "reasons": list(knock)}
        if not knock:
            thr = policy["approve_threshold"][P]
            if r["p"] < thr:
                # floor so a probability just under the threshold never displays as equal to it
                why = f"Estimated lender approval likelihood {int(math.floor(r['p'] * 100))}% is below {_pct(thr)}%"
                weak = _weakest_factor(E, P, x, policy)
                if weak:
                    why += f"; weakest factor: {FACTOR_LABELS[weak]}"
                out["reasons"].append(why)
            else:
                cap = min(policy["max_amount"][P], policy["max_pct_of_revenue"] * rev)
                amount = round_down(min(r[policy["amount_quantile"]], cap), policy["rounding"])
                typical = round_down(min(r["point"], cap), policy["rounding"])
                if amount < policy["min_amount"]:
                    out["reasons"].append(f"Preapproval amount below the {_usd(policy['min_amount'])} minimum")
                else:
                    out.update(decision="approved", amount=amount, typical_amount=max(typical, amount))
                    if r[policy["amount_quantile"]] > cap:
                        if policy["max_amount"][P] <= policy["max_pct_of_revenue"] * rev:
                            out["reasons"].append(f"Amount capped at the {_usd(policy['max_amount'][P])} product maximum")
                        else:
                            out["reasons"].append(f"Amount capped at {_pct(policy['max_pct_of_revenue'])}% of annual revenue")
        res[P] = out
    return res

/**
 * Scorer for the exported SOFI preapproval model (training/sofi_preapproval).
 *
 * Heteroscedastic log-normal amount model + monotone logistic approval model, one per product group.
 * Every input enters through a piecewise-linear "segment" basis with non-negative rises, so the approval
 * probability and every amount are non-decreasing in revenue, credit score and time in business.
 * Mirrors training/sofi_preapproval/policy.py (score_raw) to floating-point precision; parity is enforced by unit tests.
 */
import modelJson from "./model.json";

export type ModelProduct = "tlmca" | "locr";
export const MODEL_PRODUCTS: ModelProduct[] = ["tlmca", "locr"];

export interface Head {
  intercept: number;
  rev: number[];
  score: number[];
  tib: number[];
}

export interface RoundingTier {
  below: number | null;
  step: number;
}

export interface Policy {
  knockouts: { min_revenue: number; min_score: number; min_tib_years: number };
  approve_threshold: Record<ModelProduct, number>;
  amount_quantile: "q10" | "q15" | "q20";
  coverage_target: number;
  max_amount: Record<ModelProduct, number>;
  max_pct_of_revenue: number;
  min_amount: number;
  rounding: RoundingTier[];
  reference_profile: { rev: number; score: number; tib: number };
}

export interface ModelExport {
  model_version: string;
  inputs: {
    rev: { clip: [number, number]; missing: number };
    score: { clip: [number, number]; missing: number };
    tib: { clip: [number, number]; missing: number };
  };
  knots: { ln_rev: number[]; score: number[]; ln1p_tib: number[] };
  sigma_floor: number;
  products: Record<ModelProduct, { logit: Head; mu: Head; sigma: Head; c: Record<"q10" | "q15" | "q20" | "point", number> }>;
  policy: Policy;
}

export const MODEL = modelJson as unknown as ModelExport;

export interface Features {
  rev: number;
  score: number;
  tib: number;
}

export interface RawScore {
  p: number;
  q10: number;
  q15: number;
  q20: number;
  point: number;
}

const clip = (x: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, x));

export function features(E: ModelExport, rev: number | null, score: number | null, tib: number | null): Features {
  const I = E.inputs;
  const r = rev != null && Number.isFinite(rev) && rev > 0 ? rev : I.rev.missing;
  const s = score != null && Number.isFinite(score) && score >= 300 ? score : I.score.missing;
  const t = tib != null && Number.isFinite(tib) ? tib : I.tib.missing;
  return {
    rev: Math.log(clip(r, I.rev.clip[0], I.rev.clip[1])),
    score: clip(s, I.score.clip[0], I.score.clip[1]),
    tib: Math.log1p(clip(t, I.tib.clip[0], I.tib.clip[1])),
  };
}

/** Sum of segment rises c[j] times the share of segment j covered by x */
function segment(knots: number[], c: number[], x: number): number {
  let s = 0;
  for (let j = 0; j < c.length; j++) {
    s += c[j] * clip((x - knots[j]) / (knots[j + 1] - knots[j]), 0, 1);
  }
  return s;
}

/** Per-input contributions of one additive head */
export function terms(E: ModelExport, head: Head, x: Features): Features {
  return {
    rev: segment(E.knots.ln_rev, head.rev, x.rev),
    score: segment(E.knots.score, head.score, x.score),
    tib: segment(E.knots.ln1p_tib, head.tib, x.tib),
  };
}

function linear(E: ModelExport, head: Head, x: Features): number {
  const t = terms(E, head, x);
  return head.intercept + t.rev + t.score + t.tib;
}

export function scoreRaw(
  E: ModelExport,
  rev: number | null,
  score: number | null,
  tib: number | null,
): Record<ModelProduct, RawScore> {
  const x = features(E, rev, score, tib);
  const out = {} as Record<ModelProduct, RawScore>;
  for (const P of MODEL_PRODUCTS) {
    const M = E.products[P];
    const p = 1 / (1 + Math.exp(-linear(E, M.logit, x)));
    const mu = linear(E, M.mu, x);
    const sigma = Math.max(E.sigma_floor, linear(E, M.sigma, x));
    const amount = (q: "q10" | "q15" | "q20" | "point") => Math.exp(mu + M.c[q] * sigma);
    out[P] = { p, q10: amount("q10"), q15: amount("q15"), q20: amount("q20"), point: amount("point") };
  }
  return out;
}

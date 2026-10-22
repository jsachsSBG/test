/**
 * SOFI preapproval engine.
 *
 * Takes the three inputs SOFI sends (annual revenue, average credit score, time in business) and returns,
 * for Term Loan/MCA and for LOC/Revolving MCA, an approved/declined decision and a preapproval amount.
 * The amount is calibrated so that, when a lender approves the deal, its largest approval is at or above
 * the preapproval amount ~85% of the time (policy.coverage_target). Mirrors
 * training/sofi_preapproval/policy.py (preapprove) to floating-point precision; parity is enforced by unit tests.
 */
import { normalizeInputs } from "./inputs";
import { features, MODEL, ModelExport, ModelProduct, Policy, RoundingTier, scoreRaw, terms } from "./model";
import { PreapprovalResult, ProductPreapproval, SofiLeadInput } from "./types";

export { InvalidLeadError } from "./inputs";
export * from "./types";

export interface ProductDecision {
  decision: "approved" | "declined";
  amount: number | null;
  typicalAmount: number | null;
  p: number;
  reasons: string[];
}

const FACTOR_LABELS: Record<"rev" | "score" | "tib", string> = {
  rev: "annual revenue",
  score: "credit score",
  tib: "time in business",
};

/** Whole percent, rounding half up */
const pct = (x: number): number => Math.floor(x * 100 + 0.5);

const usd = (n: number): string => "$" + Math.trunc(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");

export function roundDown(amount: number, tiers: RoundingTier[]): number {
  for (const t of tiers) {
    if (t.below === null || amount < t.below) return Math.floor(amount / t.step) * t.step;
  }
  throw new Error("rounding tiers must end with an unbounded tier");
}

/** Input whose logit contribution falls furthest below the reference profile, if any */
function weakestFactor(E: ModelExport, P: ModelProduct, rev: number, score: number | null, tib: number): string | null {
  const ref = E.policy.reference_profile;
  const head = E.products[P].logit;
  const tx = terms(E, head, features(E, rev, score, tib));
  const tr = terms(E, head, features(E, ref.rev, ref.score, ref.tib));
  let worst: "rev" | "score" | "tib" | null = null;
  let gap = 0;
  for (const v of ["rev", "score", "tib"] as const) {
    const g = tx[v] - tr[v];
    if (worst === null || g < gap) {
      worst = v;
      gap = g;
    }
  }
  return worst !== null && gap < 0 ? FACTOR_LABELS[worst] : null;
}

/**
 * Decision for already-normalized inputs (score null when missing).
 * Exposed separately so tests can replay the training-side reference vectors.
 */
export function decide(
  rev: number,
  score: number | null,
  tib: number,
  E: ModelExport = MODEL,
): Record<ModelProduct, ProductDecision> {
  const policy: Policy = E.policy;
  const ko = policy.knockouts;
  const knock: string[] = [];
  if (rev < ko.min_revenue) knock.push(`Annual revenue below ${usd(ko.min_revenue)}`);
  if (score === null) knock.push("Credit score missing or invalid");
  else if (score < ko.min_score) knock.push(`Credit score below ${ko.min_score}`);
  if (tib < ko.min_tib_years) knock.push(`Time in business under ${ko.min_tib_years} years`);

  const raw = scoreRaw(E, rev, score, tib);
  const res = {} as Record<ModelProduct, ProductDecision>;
  for (const P of ["tlmca", "locr"] as ModelProduct[]) {
    const r = raw[P];
    const out: ProductDecision = { decision: "declined", amount: null, typicalAmount: null, p: r.p, reasons: [...knock] };
    if (knock.length === 0) {
      const thr = policy.approve_threshold[P];
      if (r.p < thr) {
        // floor so a probability just under the threshold never displays as equal to it
        let why = `Estimated lender approval likelihood ${Math.floor(r.p * 100)}% is below ${pct(thr)}%`;
        const weak = weakestFactor(E, P, rev, score, tib);
        if (weak) why += `; weakest factor: ${weak}`;
        out.reasons.push(why);
      } else {
        const q = r[policy.amount_quantile];
        const cap = Math.min(policy.max_amount[P], policy.max_pct_of_revenue * rev);
        const amount = roundDown(Math.min(q, cap), policy.rounding);
        const typical = roundDown(Math.min(r.point, cap), policy.rounding);
        if (amount < policy.min_amount) {
          out.reasons.push(`Preapproval amount below the ${usd(policy.min_amount)} minimum`);
        } else {
          out.decision = "approved";
          out.amount = amount;
          out.typicalAmount = Math.max(typical, amount);
          if (q > cap) {
            out.reasons.push(
              policy.max_amount[P] <= policy.max_pct_of_revenue * rev
                ? `Amount capped at the ${usd(policy.max_amount[P])} product maximum`
                : `Amount capped at ${pct(policy.max_pct_of_revenue)}% of annual revenue`,
            );
          }
        }
      }
    }
    res[P] = out;
  }
  return res;
}

function toProduct(product: ProductPreapproval["product"], d: ProductDecision): ProductPreapproval {
  return {
    product,
    decision: d.decision,
    amount: d.amount,
    typicalAmount: d.typicalAmount,
    // floored so a probability just under the approval threshold never displays as reaching it
    approvalProbability: Math.floor(d.p * 1000) / 1000,
    reasons: d.reasons,
  };
}

/**
 * Preapprove a SOFI lead.
 * Throws InvalidLeadError when revenue or time in business is missing, malformed or implausible.
 */
export function preapprove(input: SofiLeadInput, now: Date = new Date()): PreapprovalResult {
  const x = normalizeInputs(input, now);
  const d = decide(x.annualRevenue, x.creditScore, x.timeInBusinessYears);
  return {
    modelVersion: MODEL.model_version,
    coverageTarget: MODEL.policy.coverage_target,
    inputs: x,
    termLoanMca: toProduct("term_mca", d.tlmca),
    lineOfCreditRmca: toProduct("loc_rmca", d.locr),
  };
}

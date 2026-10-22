import vectorsJson from "./model-vectors.json";
import { decide, InvalidLeadError, preapprove, roundDown } from "../index";
import { MODEL, ModelProduct, scoreRaw } from "../model";

interface Vector {
  input: { annualRevenue: number; creditScore: number | null; timeInBusinessYears: number };
  raw: Record<ModelProduct, { p: number; q10: number; q15: number; q20: number; point: number }>;
  decision: Record<
    ModelProduct,
    { decision: string; amount: number | null; typical_amount: number | null; p: number; reasons: string[] }
  >;
}

const { model_version, vectors } = vectorsJson as unknown as { model_version: string; vectors: Vector[] };
const PRODUCTS: ModelProduct[] = ["tlmca", "locr"];

const relClose = (a: number, b: number) => Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(b));

describe("parity with training/sofi_preapproval/policy.py", () => {
  it("vectors were generated from the shipped model", () => {
    expect(model_version).toBe(MODEL.model_version);
    expect(vectors.length).toBeGreaterThan(100);
  });

  it("raw probabilities and amounts match", () => {
    for (const v of vectors) {
      const raw = scoreRaw(MODEL, v.input.annualRevenue, v.input.creditScore, v.input.timeInBusinessYears);
      for (const P of PRODUCTS) {
        for (const k of ["p", "q10", "q15", "q20", "point"] as const) {
          if (!relClose(raw[P][k], v.raw[P][k])) {
            throw new Error(`${P}.${k} ${raw[P][k]} != ${v.raw[P][k]} for ${JSON.stringify(v.input)}`);
          }
        }
      }
    }
  });

  it("decisions, amounts and reasons match", () => {
    for (const v of vectors) {
      const d = decide(v.input.annualRevenue, v.input.creditScore, v.input.timeInBusinessYears);
      for (const P of PRODUCTS) {
        const want = v.decision[P];
        expect({ input: v.input, P, decision: d[P].decision, amount: d[P].amount, typical: d[P].typicalAmount, reasons: d[P].reasons })
          .toEqual({ input: v.input, P, decision: want.decision, amount: want.amount, typical: want.typical_amount, reasons: want.reasons });
      }
    }
  });
});

describe("model behaviour", () => {
  const revs = [0, 1e3, ...Array.from({ length: 40 }, (_, i) => 2e4 * Math.pow(5000, i / 39))];
  const scores = [300, ...Array.from({ length: 51 }, (_, i) => 400 + i * 10)];
  const tibs = [0, ...Array.from({ length: 30 }, (_, i) => 0.05 * Math.pow(2400, i / 29))];
  const base = { rev: [5e4, 3e5, 1e6, 3e6, 2e7], score: [520, 620, 700, 780, 850], tib: [0.3, 1.5, 5, 15, 60] };
  const keys = ["p", "q10", "q15", "q20", "point"] as const;

  function checkAxis(axis: "rev" | "score" | "tib", values: number[]) {
    const others = (["rev", "score", "tib"] as const).filter((k) => k !== axis);
    for (const a of base[others[0]]) {
      for (const b of base[others[1]]) {
        let prev: ReturnType<typeof scoreRaw> | null = null;
        for (const x of values) {
          const inp = { rev: 0, score: 0, tib: 0, [axis]: x, [others[0]]: a, [others[1]]: b };
          const cur = scoreRaw(MODEL, inp.rev, inp.score, inp.tib);
          if (prev) {
            for (const P of PRODUCTS) {
              for (const k of keys) {
                if (cur[P][k] < prev[P][k] * (1 - 1e-12)) {
                  throw new Error(`${P}.${k} decreases along ${axis} at ${JSON.stringify(inp)}`);
                }
              }
            }
          }
          prev = cur;
        }
      }
    }
  }

  it("is non-decreasing in revenue, credit score and time in business", () => {
    checkAxis("rev", revs);
    checkAxis("score", scores);
    checkAxis("tib", tibs);
  });

  it("orders amount quantiles q10 <= q15 <= q20 <= point", () => {
    for (const r of revs) {
      for (const s of [500, 650, 800]) {
        for (const t of [0.5, 5, 20]) {
          const raw = scoreRaw(MODEL, r, s, t);
          for (const P of PRODUCTS) {
            expect(raw[P].q10).toBeLessThanOrEqual(raw[P].q15);
            expect(raw[P].q15).toBeLessThanOrEqual(raw[P].q20);
            expect(raw[P].q20).toBeLessThanOrEqual(raw[P].point);
          }
        }
      }
    }
  });

  it("never lets a missing score beat a real one", () => {
    for (const r of [2e5, 1e6, 5e6]) {
      const missing = scoreRaw(MODEL, r, null, 5);
      const floor = scoreRaw(MODEL, r, 300, 5);
      for (const P of PRODUCTS) expect(missing[P].p).toBeLessThanOrEqual(floor[P].p);
    }
  });

  it("rounds down on the policy tiers", () => {
    const tiers = MODEL.policy.rounding;
    expect(roundDown(9_999, tiers)).toBe(9_500);
    expect(roundDown(10_000, tiers)).toBe(10_000);
    expect(roundDown(49_999, tiers)).toBe(49_000);
    expect(roundDown(123_456, tiers)).toBe(120_000);
    expect(roundDown(612_345, tiers)).toBe(610_000);
  });
});

describe("preapprove()", () => {
  const now = new Date("2026-10-22T00:00:00Z");

  it("approves a strong lead for both products with amounts inside the caps", () => {
    const r = preapprove({ annualRevenue: 1_500_000, creditScore: 760, timeInBusinessYears: 8 }, now);
    expect(r.termLoanMca.decision).toBe("approved");
    expect(r.lineOfCreditRmca.decision).toBe("approved");
    for (const p of [r.termLoanMca, r.lineOfCreditRmca]) {
      expect(p.amount).toBeGreaterThanOrEqual(MODEL.policy.min_amount);
      expect(p.amount!).toBeLessThanOrEqual(0.15 * 1_500_000);
      expect(p.typicalAmount!).toBeGreaterThanOrEqual(p.amount!);
    }
    expect(r.termLoanMca.amount!).toBeLessThanOrEqual(MODEL.policy.max_amount.tlmca);
    expect(r.lineOfCreditRmca.amount!).toBeLessThanOrEqual(MODEL.policy.max_amount.locr);
    expect(r.modelVersion).toBe(MODEL.model_version);
  });

  it("declines both products on knock-outs with a reason", () => {
    const r = preapprove({ annualRevenue: 60_000, creditScore: 720, timeInBusinessYears: 3 }, now);
    expect(r.termLoanMca.decision).toBe("declined");
    expect(r.lineOfCreditRmca.decision).toBe("declined");
    expect(r.termLoanMca.amount).toBeNull();
    expect(r.termLoanMca.reasons).toContain("Annual revenue below $100,000");
  });

  it("treats missing or out-of-range credit scores as a knock-out", () => {
    for (const creditScore of [null, undefined, 0, 250, 1000, Number.NaN]) {
      const r = preapprove({ annualRevenue: 900_000, creditScore, timeInBusinessYears: 4 }, now);
      expect(r.inputs.creditScore).toBeNull();
      expect(r.termLoanMca.decision).toBe("declined");
      expect(r.termLoanMca.reasons).toContain("Credit score missing or invalid");
    }
  });

  it("derives time in business from the business start date", () => {
    const r = preapprove({ annualRevenue: 900_000, creditScore: 700, businessStartDate: "2021-10-22" }, now);
    expect(r.inputs.timeInBusinessYears).toBeCloseTo(5, 2);
  });

  it("rejects leads without revenue or time in business", () => {
    expect(() => preapprove({ annualRevenue: Number.NaN, creditScore: 700, timeInBusinessYears: 3 }, now)).toThrow(InvalidLeadError);
    expect(() => preapprove({ annualRevenue: -5, creditScore: 700, timeInBusinessYears: 3 }, now)).toThrow(InvalidLeadError);
    expect(() => preapprove({ annualRevenue: 500_000, creditScore: 700 }, now)).toThrow(InvalidLeadError);
    expect(() => preapprove({ annualRevenue: Infinity, creditScore: 700, timeInBusinessYears: 3 }, now)).toThrow(InvalidLeadError);
  });
});

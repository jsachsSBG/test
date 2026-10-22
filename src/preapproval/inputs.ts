import { SofiLeadInput } from "./types";

export interface NormalizedInputs {
  annualRevenue: number;
  /** null when missing or outside the valid range */
  creditScore: number | null;
  timeInBusinessYears: number;
}

export class InvalidLeadError extends Error {}

const MS_PER_YEAR = 365.25 * 24 * 60 * 60 * 1000;
export const MIN_CREDIT_SCORE = 300;
export const MAX_CREDIT_SCORE = 850;
/** Larger stated revenues are treated as entry errors rather than scored as top-band businesses */
export const MAX_ANNUAL_REVENUE = 1_000_000_000;
const NUMERIC = /^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$/;
const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/**
 * A finite number from a JSON number or a plain numeric string; null for anything else
 * (null, "", booleans, arrays, objects, "1,000", "0x10"), so a missing field is never read as 0.
 */
export function toNumber(v: unknown): number | null {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string" && NUMERIC.test(v.trim())) {
    const n = Number(v.trim());
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

/** Strict YYYY-MM-DD calendar date (UTC midnight), or null */
export function parseIsoDate(v: unknown): Date | null {
  if (typeof v !== "string") return null;
  const m = ISO_DATE.exec(v.trim());
  if (!m) return null;
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const date = new Date(Date.UTC(y, mo - 1, d));
  // reject roll-overs such as 2021-02-30
  if (date.getUTCFullYear() !== y || date.getUTCMonth() !== mo - 1 || date.getUTCDate() !== d) return null;
  return date;
}

/**
 * Validate and normalize raw lead fields.
 * Throws InvalidLeadError when revenue or time in business is missing, malformed or implausible.
 * A missing or out-of-range credit score is returned as null (the decision layer declines it).
 */
export function normalizeInputs(input: SofiLeadInput, now: Date = new Date()): NormalizedInputs {
  const annualRevenue = toNumber(input.annualRevenue);
  if (annualRevenue === null || annualRevenue < 0) {
    throw new InvalidLeadError("annualRevenue must be a non-negative number");
  }
  if (annualRevenue > MAX_ANNUAL_REVENUE) {
    throw new InvalidLeadError(`annualRevenue above $${MAX_ANNUAL_REVENUE.toLocaleString("en-US")} looks like an entry error`);
  }

  const score = toNumber(input.creditScore);
  const creditScore = score !== null && score >= MIN_CREDIT_SCORE && score <= MAX_CREDIT_SCORE ? score : null;

  let tib = toNumber(input.timeInBusinessYears);
  if (tib === null && input.businessStartDate != null && input.businessStartDate !== "") {
    const start = parseIsoDate(input.businessStartDate);
    if (!start) throw new InvalidLeadError("businessStartDate must be a valid YYYY-MM-DD date");
    if (start.getUTCFullYear() < 1900) throw new InvalidLeadError("businessStartDate is before 1900");
    tib = (now.getTime() - start.getTime()) / MS_PER_YEAR;
    if (tib < 0) throw new InvalidLeadError("businessStartDate is in the future");
  }
  if (tib === null) {
    throw new InvalidLeadError("timeInBusinessYears or businessStartDate is required");
  }
  if (tib < 0) throw new InvalidLeadError("timeInBusinessYears must not be negative");

  return { annualRevenue, creditScore, timeInBusinessYears: tib };
}

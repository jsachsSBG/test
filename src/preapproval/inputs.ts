import { SofiLeadInput } from "./types";

export interface NormalizedInputs {
  annualRevenue: number;
  /** null when missing or outside the valid FICO range */
  creditScore: number | null;
  timeInBusinessYears: number;
}

export class InvalidLeadError extends Error {}

const MS_PER_YEAR = 365.25 * 24 * 60 * 60 * 1000;

/**
 * Validate and normalize raw lead fields.
 * Throws InvalidLeadError when revenue or time in business cannot be determined.
 */
export function normalizeInputs(input: SofiLeadInput, now: Date = new Date()): NormalizedInputs {
  const annualRevenue = Number(input.annualRevenue);
  if (!Number.isFinite(annualRevenue) || annualRevenue < 0) {
    throw new InvalidLeadError("annualRevenue must be a non-negative number");
  }

  const rawScore = input.creditScore == null ? NaN : Number(input.creditScore);
  // Scores below 300 are bureau placeholders (no-hit / frozen), not real FICO scores
  const creditScore = Number.isFinite(rawScore) && rawScore >= 300 && rawScore <= 900 ? rawScore : null;

  let tib = input.timeInBusinessYears == null ? NaN : Number(input.timeInBusinessYears);
  if (!Number.isFinite(tib) && input.businessStartDate) {
    const start = Date.parse(input.businessStartDate);
    if (Number.isFinite(start)) tib = (now.getTime() - start) / MS_PER_YEAR;
  }
  if (!Number.isFinite(tib)) {
    throw new InvalidLeadError("timeInBusinessYears or businessStartDate is required");
  }

  return { annualRevenue, creditScore, timeInBusinessYears: Math.max(0, tib) };
}

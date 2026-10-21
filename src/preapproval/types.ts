/**
 * SOFI preapproval types.
 *
 * Two product groups are scored independently:
 *  - term_mca: Term Loans and MCAs (largest lender offer across both)
 *  - loc_rmca: Lines of Credit and Revolving MCAs (largest lender offer across both)
 */

export type ProductGroup = "term_mca" | "loc_rmca";

export interface SofiLeadInput {
  /** Annual revenue in dollars as stated on the SOFI lead */
  annualRevenue: number;
  /** Average owner credit score (300-850); null/undefined when SOFI has not sent one */
  creditScore?: number | null;
  /** Time in business in years (e.g. 2.5). Alternatively pass businessStartDate. */
  timeInBusinessYears?: number | null;
  /** ISO date (YYYY-MM-DD) the business started; used when timeInBusinessYears is absent */
  businessStartDate?: string | null;
}

export interface ProductPreapproval {
  product: ProductGroup;
  decision: "approved" | "declined";
  /**
   * Preapproval amount (rounded down), or null when declined.
   * Calibrated so that, when a lender approves the deal, the lender's largest
   * approval is at or above this amount for the target share of deals (see coverageTarget).
   */
  amount: number | null;
  /** Typical (median) largest lender approval for similar deals, for context; null when declined */
  typicalAmount: number | null;
  /** Modeled probability that at least one lender approves this product group */
  approvalProbability: number;
  /** Human-readable reasons for the decision (knock-outs, low probability, caps) */
  reasons: string[];
}

export interface PreapprovalResult {
  modelVersion: string;
  /** Share of lender-approved deals expected to meet or beat `amount` */
  coverageTarget: number;
  inputs: { annualRevenue: number; creditScore: number | null; timeInBusinessYears: number };
  termLoanMca: ProductPreapproval;
  lineOfCreditRmca: ProductPreapproval;
}

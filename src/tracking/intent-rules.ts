/**
 * Intent scoring rules.
 * Each rule maps a condition to a score delta.
 * Higher scores = higher purchase/conversion intent.
 */

export interface IntentRule {
  name: string;
  description: string;
  /** Points awarded when this rule fires */
  score: number;
  /** Evaluate against an event; return true to award points */
  match: (event: TrackingEvent) => boolean;
}

export interface TrackingEvent {
  eventType: string;
  pageUrl: string;
  referrer?: string;
  metadata?: Record<string, unknown>;
}

export const intentRules: IntentRule[] = [
  {
    name: "visited_apply",
    description: "Visited /apply page",
    score: 30,
    match: (e) => e.pageUrl.includes("/apply"),
  },
  {
    name: "viewed_loan_calculator",
    description: "Viewed loan calculator page or widget",
    score: 25,
    match: (e) =>
      e.pageUrl.includes("/calculator") ||
      e.pageUrl.includes("/loan-calculator") ||
      e.eventType === "calculator_interaction",
  },
  {
    name: "visited_pricing",
    description: "Viewed pricing or rates page",
    score: 20,
    match: (e) =>
      e.pageUrl.includes("/pricing") || e.pageUrl.includes("/rates"),
  },
  {
    name: "visited_contact",
    description: "Viewed contact or schedule page",
    score: 15,
    match: (e) =>
      e.pageUrl.includes("/contact") || e.pageUrl.includes("/schedule"),
  },
  {
    name: "form_interaction",
    description: "Started filling out a form",
    score: 20,
    match: (e) => e.eventType === "form_start",
  },
  {
    name: "form_submission",
    description: "Submitted a form (self-identified)",
    score: 40,
    match: (e) => e.eventType === "form_submit",
  },
  {
    name: "pageview",
    description: "General page view (baseline engagement)",
    score: 2,
    match: (e) => e.eventType === "pageview",
  },
];

/**
 * Bonus score for returning visitors (applied once per visit, not per event).
 * visitCount >= 2 => +15, >= 4 => +25
 */
export function returnVisitorBonus(visitCount: number): number {
  if (visitCount >= 4) return 25;
  if (visitCount >= 2) return 15;
  return 0;
}

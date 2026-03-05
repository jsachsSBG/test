import { getDb } from "../db/database";
import { config } from "../config";
import { sendSlackAlert } from "./slack";
import { sendEmailAlert } from "./email";
import { VisitorAlert } from "./types";

/**
 * Check if a visitor has crossed the intent threshold
 * and should trigger a notification.
 */
export async function evaluateAndNotify(visitorId: string): Promise<void> {
  const db = getDb();

  const visitor = db
    .prepare("SELECT * FROM visitors WHERE visitor_id = ?")
    .get(visitorId) as Record<string, unknown> | undefined;

  if (!visitor) return;

  const intentScore = visitor.intent_score as number;
  if (intentScore < config.highIntentScoreThreshold) return;

  // Cooldown: don't spam notifications for the same visitor
  if (visitor.last_notified) {
    const lastNotified = new Date(visitor.last_notified as string).getTime();
    const cooldownMs = config.notifyCooldownMinutes * 60 * 1000;
    if (Date.now() - lastNotified < cooldownMs) return;
  }

  // Build behavior summary from recent events
  const events = db
    .prepare(
      `SELECT event_type, page_url, created_at FROM events
       WHERE visitor_id = ? ORDER BY created_at DESC LIMIT 20`
    )
    .all(visitorId) as { event_type: string; page_url: string; created_at: string }[];

  const keyBehaviors = summarizeBehaviors(events, visitor.visit_count as number);

  const alert: VisitorAlert = {
    visitorId,
    intentScore,
    visitCount: visitor.visit_count as number,
    email: (visitor.email as string) || undefined,
    name: (visitor.name as string) || undefined,
    company: (visitor.company as string) || undefined,
    phone: (visitor.phone as string) || undefined,
    keyBehaviors,
  };

  console.log(`[notifier] Sending alert for visitor ${visitorId} (score: ${intentScore})`);

  // Fire both channels in parallel
  const [slackOk, emailOk] = await Promise.all([
    sendSlackAlert(alert),
    sendEmailAlert(alert),
  ]);

  if (slackOk || emailOk) {
    db.prepare("UPDATE visitors SET last_notified = ? WHERE visitor_id = ?").run(
      new Date().toISOString(),
      visitorId
    );
  }
}

function summarizeBehaviors(
  events: { event_type: string; page_url: string; created_at: string }[],
  visitCount: number
): string[] {
  const behaviors: string[] = [];
  const pages = new Set(events.map((e) => e.page_url));

  if (visitCount >= 2) behaviors.push(`Returned ${visitCount} times`);

  for (const page of pages) {
    if (page.includes("/apply")) behaviors.push("Visited /apply page");
    if (page.includes("/calculator") || page.includes("/loan-calculator"))
      behaviors.push("Used loan calculator");
    if (page.includes("/pricing") || page.includes("/rates"))
      behaviors.push("Viewed pricing/rates");
    if (page.includes("/contact") || page.includes("/schedule"))
      behaviors.push("Visited contact page");
  }

  const formStart = events.find((e) => e.event_type === "form_start");
  const formSubmit = events.find((e) => e.event_type === "form_submit");
  if (formSubmit) behaviors.push("Submitted a form");
  else if (formStart) behaviors.push("Started filling out a form");

  if (behaviors.length === 0) behaviors.push(`Viewed ${pages.size} pages`);

  return behaviors;
}

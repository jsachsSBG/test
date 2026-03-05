import { v4 as uuidv4 } from "uuid";
import { getDb } from "../db/database";
import { intentRules, returnVisitorBonus, TrackingEvent } from "./intent-rules";

export interface RawEvent {
  visitorId?: string;
  eventType: string;
  pageUrl: string;
  referrer?: string;
  metadata?: Record<string, unknown>;
  ip?: string;
  userAgent?: string;
}

export interface ProcessedVisitor {
  visitorId: string;
  intentScore: number;
  visitCount: number;
  isNewSession: boolean;
}

const SESSION_GAP_MS = 30 * 60 * 1000; // 30 minutes

export function processEvent(raw: RawEvent): ProcessedVisitor {
  const db = getDb();
  const now = new Date().toISOString();
  let visitorId = raw.visitorId || uuidv4();
  let isNewSession = false;

  const existing = db
    .prepare("SELECT * FROM visitors WHERE visitor_id = ?")
    .get(visitorId) as Record<string, unknown> | undefined;

  if (existing) {
    const lastSeen = new Date(existing.last_seen as string).getTime();
    isNewSession = Date.now() - lastSeen > SESSION_GAP_MS;

    const visitIncrement = isNewSession ? 1 : 0;
    db.prepare(
      `UPDATE visitors SET last_seen = ?, visit_count = visit_count + ?,
       ip_address = COALESCE(?, ip_address), user_agent = COALESCE(?, user_agent)
       WHERE visitor_id = ?`
    ).run(now, visitIncrement, raw.ip || null, raw.userAgent || null, visitorId);
  } else {
    isNewSession = true;
    db.prepare(
      `INSERT INTO visitors (visitor_id, ip_address, user_agent, first_seen, last_seen)
       VALUES (?, ?, ?, ?, ?)`
    ).run(visitorId, raw.ip || null, raw.userAgent || null, now, now);
  }

  // Store event
  db.prepare(
    `INSERT INTO events (visitor_id, event_type, page_url, referrer, metadata, created_at)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).run(
    visitorId,
    raw.eventType,
    raw.pageUrl,
    raw.referrer || null,
    raw.metadata ? JSON.stringify(raw.metadata) : null,
    now
  );

  // Score the event
  const trackingEvent: TrackingEvent = {
    eventType: raw.eventType,
    pageUrl: raw.pageUrl,
    referrer: raw.referrer,
    metadata: raw.metadata,
  };

  let scoreDelta = 0;
  for (const rule of intentRules) {
    if (rule.match(trackingEvent)) {
      scoreDelta += rule.score;
    }
  }

  // Apply return visitor bonus on new sessions
  if (isNewSession) {
    const visitor = db
      .prepare("SELECT visit_count FROM visitors WHERE visitor_id = ?")
      .get(visitorId) as { visit_count: number };
    scoreDelta += returnVisitorBonus(visitor.visit_count);
  }

  if (scoreDelta > 0) {
    db.prepare(
      "UPDATE visitors SET intent_score = intent_score + ? WHERE visitor_id = ?"
    ).run(scoreDelta, visitorId);
  }

  const updated = db
    .prepare("SELECT intent_score, visit_count FROM visitors WHERE visitor_id = ?")
    .get(visitorId) as { intent_score: number; visit_count: number };

  return {
    visitorId,
    intentScore: updated.intent_score,
    visitCount: updated.visit_count,
    isNewSession,
  };
}

/** Form submissions self-identify the visitor — store their info directly. */
export function identifyVisitor(
  visitorId: string,
  info: { email?: string; name?: string; phone?: string; company?: string }
): void {
  const db = getDb();
  db.prepare(
    `UPDATE visitors SET
       email = COALESCE(?, email),
       name = COALESCE(?, name),
       phone = COALESCE(?, phone),
       company = COALESCE(?, company)
     WHERE visitor_id = ?`
  ).run(info.email || null, info.name || null, info.phone || null, info.company || null, visitorId);
}

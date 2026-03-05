import { getDb } from "../db/database";
import { config } from "../config";

interface EnrichmentResult {
  email?: string;
  name?: string;
  company?: string;
  enriched: boolean;
}

/**
 * Attempts to de-anonymize a visitor using IP-based reverse lookup.
 * Uses Clearbit Reveal (or similar) to resolve IP -> company/person.
 * Falls back gracefully if no API key is configured or lookup fails.
 */
export async function enrichVisitor(visitorId: string): Promise<EnrichmentResult> {
  const db = getDb();
  const visitor = db
    .prepare("SELECT ip_address, enriched, email FROM visitors WHERE visitor_id = ?")
    .get(visitorId) as { ip_address: string; enriched: number; email: string | null } | undefined;

  if (!visitor) return { enriched: false };
  // Skip if already enriched or already self-identified
  if (visitor.enriched || visitor.email) return { enriched: true };

  const ip = visitor.ip_address;
  if (!ip || !config.clearbitApiKey) return { enriched: false };

  try {
    const result = await revealByIp(ip);

    if (result.company || result.name || result.email) {
      db.prepare(
        `UPDATE visitors SET
           company = COALESCE(?, company),
           name    = COALESCE(?, name),
           email   = COALESCE(?, email),
           enriched = 1
         WHERE visitor_id = ?`
      ).run(result.company || null, result.name || null, result.email || null, visitorId);
    }

    return { ...result, enriched: true };
  } catch (err) {
    console.error(`[enrich] Failed for visitor ${visitorId}:`, err);
    return { enriched: false };
  }
}

/**
 * IP reveal via Clearbit Reveal API.
 * Replace this with any enrichment provider (ZoomInfo, Apollo, etc.)
 */
async function revealByIp(ip: string): Promise<{ email?: string; name?: string; company?: string }> {
  const res = await fetch(
    `https://reveal.clearbit.com/v1/companies/find?ip=${encodeURIComponent(ip)}`,
    {
      headers: { Authorization: `Bearer ${config.clearbitApiKey}` },
    }
  );

  if (!res.ok) {
    if (res.status === 404) return {}; // No match
    throw new Error(`Clearbit API error: ${res.status}`);
  }

  const data = (await res.json()) as {
    company?: { name?: string; domain?: string };
    person?: { email?: string; name?: { fullName?: string } };
  };

  return {
    company: data.company?.name,
    name: data.person?.name?.fullName,
    email: data.person?.email,
  };
}

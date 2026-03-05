import Database from "better-sqlite3";
import path from "path";

const DB_PATH = path.join(process.cwd(), "visitors.db");

let db: Database.Database;

export function getDb(): Database.Database {
  if (!db) {
    db = new Database(DB_PATH);
    db.pragma("journal_mode = WAL");
    initSchema(db);
  }
  return db;
}

function initSchema(db: Database.Database): void {
  db.exec(`
    CREATE TABLE IF NOT EXISTS visitors (
      visitor_id   TEXT PRIMARY KEY,
      ip_address   TEXT,
      user_agent   TEXT,
      first_seen   TEXT NOT NULL,
      last_seen    TEXT NOT NULL,
      visit_count  INTEGER DEFAULT 1,
      intent_score INTEGER DEFAULT 0,
      -- de-anonymized fields
      email        TEXT,
      name         TEXT,
      company      TEXT,
      phone        TEXT,
      enriched     INTEGER DEFAULT 0,
      -- notification state
      last_notified TEXT
    );

    CREATE TABLE IF NOT EXISTS events (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      visitor_id  TEXT NOT NULL,
      event_type  TEXT NOT NULL,
      page_url    TEXT,
      referrer    TEXT,
      metadata    TEXT,
      created_at  TEXT NOT NULL,
      FOREIGN KEY (visitor_id) REFERENCES visitors(visitor_id)
    );

    CREATE INDEX IF NOT EXISTS idx_events_visitor ON events(visitor_id);
    CREATE INDEX IF NOT EXISTS idx_visitors_score ON visitors(intent_score);
  `);
}

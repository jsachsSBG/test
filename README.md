# Visitor Intent Detection Agent

Monitors your website for high-intent visitor behaviors, de-anonymizes visitors where possible, and pings your team via Slack or email with contact info and a behavior summary.

## How It Works

```
┌─────────────┐     ┌──────────────────┐     ┌────────────────┐
│  Your Site   │────▶│  Tracking Server │────▶│  Intent Scorer │
│ (snippet.js) │     │  POST /track     │     │  (rule engine) │
└─────────────┘     └──────────────────┘     └───────┬────────┘
                                                      │
                                              ┌───────▼────────┐
                                              │  Enrichment    │
                                              │  (Clearbit IP  │
                                              │   reveal)      │
                                              └───────┬────────┘
                                                      │
                                              ┌───────▼────────┐
                                              │  Notifier      │
                                              │  Slack + Email  │
                                              └────────────────┘
```

### Intent Scoring Rules

| Behavior | Points |
|---|---|
| Visited `/apply` | +30 |
| Viewed loan calculator | +25 |
| Viewed pricing/rates | +20 |
| Visited contact page | +15 |
| Started filling a form | +20 |
| Submitted a form | +40 |
| General page view | +2 |
| Returning visitor (2+ visits) | +15 bonus |
| Returning visitor (4+ visits) | +25 bonus |

Default threshold for notification: **50 points**

### De-anonymization

1. **Self-identification** — Form submissions auto-capture email, name, phone, company
2. **IP enrichment** — Uses Clearbit Reveal to resolve visitor IP → company + contact (swappable for ZoomInfo, Apollo, etc.)

## Quick Start

```bash
# Install
npm install

# Configure
cp .env.example .env
# Edit .env with your Slack token, SMTP creds, Clearbit key

# Run
npm run dev

# Or build & run
npm run build && npm start
```

## Add to Your Site

```html
<script src="https://track.yourdomain.com/snippet.js"></script>
```

The snippet automatically tracks:
- Page views (including SPA navigation)
- Form focus events (intent signal)
- Form submissions (captures identity fields)

## API

### `POST /track`
```json
{
  "eventType": "pageview",
  "pageUrl": "https://yoursite.com/apply",
  "referrer": "https://google.com",
  "metadata": {}
}
```

### `POST /identify`
```json
{
  "visitorId": "uuid",
  "email": "jane@acme.com",
  "name": "Jane Smith",
  "company": "Acme Corp"
}
```

### `GET /snippet.js`
Returns the auto-tracking JavaScript snippet.

## Configuration

All config via environment variables — see `.env.example` for the full list.

Key settings:
- `HIGH_INTENT_SCORE_THRESHOLD` — score at which to fire alerts (default: 50)
- `NOTIFY_COOLDOWN_MINUTES` — don't re-alert for same visitor within this window (default: 60)

## Salesforce CLI (for SF data analysis)

Claude Code on the web sessions install the [Salesforce CLI](https://developer.salesforce.com/tools/salesforcecli) (`sf`, with the legacy `sfdx` alias) automatically via `.claude/hooks/session-start.sh`.

### Connect an org (headless, no browser)

1. On a machine where you're already logged in, print the org's auth URL:
   ```bash
   sf org display --target-org <alias> --verbose --json   # copy the "sfdxAuthUrl" value
   ```
2. In the Claude Code environment settings, add a secret environment variable named `SFDX_AUTH_URL` with that value (optionally `SF_ORG_ALIAS` to name the org; defaults to `sfdata`).
3. New sessions will authenticate on startup and set that org as the default.

The auth URL grants full API access to the org — keep it as a secret, never commit it.

### Run analysis

```bash
sf org display                                              # confirm connection
sf data query -q "SELECT Id, Name FROM Account LIMIT 10"    # quick SOQL
sf data query -q "SELECT ... FROM Opportunity" -r csv --output-file opps.csv
sf data export bulk -q "SELECT ... FROM Lead" --output-file leads.csv --wait 10   # large datasets (Bulk API 2.0)
sf sobject describe -s Opportunity                           # inspect fields
```

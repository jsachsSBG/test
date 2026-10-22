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

## SOFI Preapproval

`POST /preapproval/sofi` scores an incoming SOFI lead from three inputs: annual revenue, average credit
score and time in business. It returns approved/declined and a preapproval amount for two product
groups: Term Loan + MCA, and Line of Credit + Revolving MCA.

The route is server-to-server. It requires the `x-api-key` header to match `PREAPPROVAL_API_KEY`, and it
answers 503 while that variable is unset.

```json
// request (POST /preapproval/sofi, header x-api-key: <PREAPPROVAL_API_KEY>)
{ "annualRevenue": 1500000, "creditScore": 760, "timeInBusinessYears": 8 }
// (or "businessStartDate": "2018-10-01" instead of timeInBusinessYears)

// response
{
  "modelVersion": "sofi-preapproval-hetero-2026-10-e34371c2",
  "coverageTarget": 0.85,
  "inputs": { "annualRevenue": 1500000, "creditScore": 760, "timeInBusinessYears": 8 },
  "termLoanMca": { "product": "term_mca", "decision": "approved", "amount": 50000, "typicalAmount": 130000, "approvalProbability": 0.865, "reasons": [] },
  "lineOfCreditRmca": { "product": "loc_rmca", "decision": "approved", "amount": 45000, "typicalAmount": 95000, "approvalProbability": 0.706, "reasons": [] }
}
```

- **`amount`:** a conservative preapproval. When a lender approves the deal, its largest offer meets or
  beats this amount about 85% of the time.
- **`typicalAmount`:** the median largest offer for similar deals. It is context, not a promise.
- **`reasons`:** explains declines and caps. Declines come from knock-outs (revenue under $100k, credit
  score missing or under 450, under 3 months in business) or from a low approval likelihood, in which
  case the weakest factor is named.
- **Errors:** HTTP 400 when revenue or time in business is missing, non-numeric or implausible (revenue
  over $1B, time in business over 100 years), a start date is not a real past `YYYY-MM-DD` date, or the
  body is not valid JSON.

The model was trained on 24 months of SOFI New deals from Salesforce. Methodology, backtest results
(including how the model does on SOFI's new funnel) and the monthly retrain process are in
[`training/sofi_preapproval/README.md`](training/sofi_preapproval/README.md).

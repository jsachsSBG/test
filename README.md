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

`POST /preapproval/sofi` scores an incoming SOFI lead from three inputs (annual revenue, average credit
score, time in business). It returns approved/declined and a preapproval amount for two product groups:
Term Loan + MCA, and Line of Credit + Revolving MCA.

```json
// request
{ "annualRevenue": 1500000, "creditScore": 760, "timeInBusinessYears": 8 }
// (or "businessStartDate": "2018-10-01" instead of timeInBusinessYears)

// response
{
  "modelVersion": "sofi-preapproval-hetero-2026-10-cal2026-07..2026-10",
  "coverageTarget": 0.85,
  "inputs": { "annualRevenue": 1500000, "creditScore": 760, "timeInBusinessYears": 8 },
  "termLoanMca": { "product": "term_mca", "decision": "approved", "amount": 50000, "typicalAmount": 135000, "approvalProbability": 0.868, "reasons": [] },
  "lineOfCreditRmca": { "product": "loc_rmca", "decision": "approved", "amount": 46000, "typicalAmount": 100000, "approvalProbability": 0.667, "reasons": [] }
}
```

- **`amount`:** a conservative preapproval. When a lender approves the deal, its largest approval meets
  or beats this amount ~85% of the time.
- **`typicalAmount`:** the median largest approval for similar deals. It is context, not a promise.
- **`reasons`:** explains declines (knock-outs, or low approval likelihood with the weakest factor) and caps.
- **Errors:** a lead without a numeric revenue or time in business returns HTTP 400.

The model was trained on 24 months of SOFI New deals from Salesforce. Methodology, backtest results and
the monthly retrain process are in [`training/sofi_preapproval/README.md`](training/sofi_preapproval/README.md).

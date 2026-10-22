export const config = {
  port: parseInt(process.env.PORT || "3100", 10),
  trackerDomain: process.env.TRACKER_DOMAIN || "http://localhost:3100",

  slack: {
    botToken: process.env.SLACK_BOT_TOKEN || "",
    channelId: process.env.SLACK_CHANNEL_ID || "",
  },

  email: {
    host: process.env.SMTP_HOST || "",
    port: parseInt(process.env.SMTP_PORT || "587", 10),
    user: process.env.SMTP_USER || "",
    pass: process.env.SMTP_PASS || "",
    to: process.env.ALERT_EMAIL_TO || "",
    from: process.env.ALERT_EMAIL_FROM || "",
  },

  clearbitApiKey: process.env.CLEARBIT_API_KEY || "",

  /** Shared secret SOFI sends in the x-api-key header; POST /preapproval/sofi is disabled while empty */
  preapprovalApiKey: process.env.PREAPPROVAL_API_KEY || "",

  highIntentScoreThreshold: parseInt(process.env.HIGH_INTENT_SCORE_THRESHOLD || "50", 10),
  notifyCooldownMinutes: parseInt(process.env.NOTIFY_COOLDOWN_MINUTES || "60", 10),
};

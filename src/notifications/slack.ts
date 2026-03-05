import { WebClient } from "@slack/web-api";
import { config } from "../config";
import { VisitorAlert } from "./types";

let slackClient: WebClient | null = null;

function getClient(): WebClient | null {
  if (!config.slack.botToken) return null;
  if (!slackClient) {
    slackClient = new WebClient(config.slack.botToken);
  }
  return slackClient;
}

export async function sendSlackAlert(alert: VisitorAlert): Promise<boolean> {
  const client = getClient();
  if (!client || !config.slack.channelId) {
    console.log("[slack] Slack not configured, skipping notification");
    return false;
  }

  const fields: { title: string; value: string; short: boolean }[] = [
    { title: "Intent Score", value: `${alert.intentScore}`, short: true },
    { title: "Visit Count", value: `${alert.visitCount}`, short: true },
  ];

  if (alert.email) fields.push({ title: "Email", value: alert.email, short: true });
  if (alert.name) fields.push({ title: "Name", value: alert.name, short: true });
  if (alert.company) fields.push({ title: "Company", value: alert.company, short: true });
  if (alert.phone) fields.push({ title: "Phone", value: alert.phone, short: true });

  try {
    await client.chat.postMessage({
      channel: config.slack.channelId,
      text: `High-intent visitor detected! Score: ${alert.intentScore}`,
      blocks: [
        {
          type: "header",
          text: { type: "plain_text", text: "🔥 High-Intent Visitor Detected" },
        },
        {
          type: "section",
          text: {
            type: "mrkdwn",
            text: alert.name
              ? `*${alert.name}*${alert.company ? ` at ${alert.company}` : ""}`
              : `Anonymous visitor${alert.company ? ` from ${alert.company}` : ""}`,
          },
        },
        {
          type: "section",
          fields: fields.map((f) => ({
            type: "mrkdwn" as const,
            text: `*${f.title}:*\n${f.value}`,
          })),
        },
        {
          type: "section",
          text: {
            type: "mrkdwn",
            text: `*Key Behaviors:*\n${alert.keyBehaviors.map((b) => `• ${b}`).join("\n")}`,
          },
        },
      ],
    });
    return true;
  } catch (err) {
    console.error("[slack] Failed to send alert:", err);
    return false;
  }
}

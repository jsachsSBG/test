import nodemailer from "nodemailer";
import { config } from "../config";
import { VisitorAlert } from "./types";

let transporter: nodemailer.Transporter | null = null;

function getTransporter(): nodemailer.Transporter | null {
  if (!config.email.host || !config.email.user) return null;
  if (!transporter) {
    transporter = nodemailer.createTransport({
      host: config.email.host,
      port: config.email.port,
      secure: config.email.port === 465,
      auth: { user: config.email.user, pass: config.email.pass },
    });
  }
  return transporter;
}

export async function sendEmailAlert(alert: VisitorAlert): Promise<boolean> {
  const t = getTransporter();
  if (!t || !config.email.to) {
    console.log("[email] Email not configured, skipping notification");
    return false;
  }

  const identity = alert.name
    ? `${alert.name}${alert.company ? ` (${alert.company})` : ""}`
    : alert.company
      ? `Visitor from ${alert.company}`
      : "Anonymous visitor";

  const html = `
    <h2>High-Intent Visitor Detected</h2>
    <p><strong>${identity}</strong></p>
    <table style="border-collapse:collapse;margin:16px 0;">
      <tr><td style="padding:4px 12px;font-weight:bold;">Intent Score</td><td style="padding:4px 12px;">${alert.intentScore}</td></tr>
      <tr><td style="padding:4px 12px;font-weight:bold;">Visits</td><td style="padding:4px 12px;">${alert.visitCount}</td></tr>
      ${alert.email ? `<tr><td style="padding:4px 12px;font-weight:bold;">Email</td><td style="padding:4px 12px;"><a href="mailto:${alert.email}">${alert.email}</a></td></tr>` : ""}
      ${alert.phone ? `<tr><td style="padding:4px 12px;font-weight:bold;">Phone</td><td style="padding:4px 12px;">${alert.phone}</td></tr>` : ""}
    </table>
    <h3>Key Behaviors</h3>
    <ul>${alert.keyBehaviors.map((b) => `<li>${b}</li>`).join("")}</ul>
  `;

  try {
    await t.sendMail({
      from: config.email.from,
      to: config.email.to,
      subject: `🔥 High-Intent Visitor: ${identity} (Score: ${alert.intentScore})`,
      html,
    });
    return true;
  } catch (err) {
    console.error("[email] Failed to send alert:", err);
    return false;
  }
}

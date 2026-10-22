import express from "express";
import cookieParser from "cookie-parser";
import cors from "cors";
import { v4 as uuidv4 } from "uuid";
import { config } from "./config";
import { processEvent, identifyVisitor, RawEvent } from "./tracking/tracker";
import { enrichVisitor } from "./enrichment/enrich";
import { evaluateAndNotify } from "./notifications/notifier";
import { InvalidLeadError, preapprove } from "./preapproval";

export function createServer(): express.Express {
  const app = express();

  app.use(cors({ origin: true, credentials: true }));
  app.use(cookieParser());
  app.use(express.json());

  // Health check
  app.get("/health", (_req, res) => {
    res.json({ status: "ok" });
  });

  /**
   * POST /track — receives events from the client-side snippet.
   * Body: { eventType, pageUrl, referrer?, metadata? }
   * The visitor ID is stored in a first-party cookie.
   */
  app.post("/track", async (req, res) => {
    try {
      let visitorId = req.cookies?.vid;
      if (!visitorId) {
        visitorId = uuidv4();
      }

      const raw: RawEvent = {
        visitorId,
        eventType: req.body.eventType || "pageview",
        pageUrl: req.body.pageUrl || "",
        referrer: req.body.referrer,
        metadata: req.body.metadata,
        ip: (req.headers["x-forwarded-for"] as string)?.split(",")[0]?.trim() || req.socket.remoteAddress,
        userAgent: req.headers["user-agent"],
      };

      const result = processEvent(raw);

      // Set visitor cookie (1 year)
      res.cookie("vid", result.visitorId, {
        maxAge: 365 * 24 * 60 * 60 * 1000,
        httpOnly: true,
        sameSite: "none",
        secure: true,
      });

      // If form submission included identity info, store it
      if (req.body.metadata?.email || req.body.metadata?.name) {
        identifyVisitor(result.visitorId, {
          email: req.body.metadata.email,
          name: req.body.metadata.name,
          phone: req.body.metadata.phone,
          company: req.body.metadata.company,
        });
      }

      // Async: enrich + evaluate (don't block the response)
      setImmediate(async () => {
        try {
          await enrichVisitor(result.visitorId);
          await evaluateAndNotify(result.visitorId);
        } catch (err) {
          console.error("[server] Background processing error:", err);
        }
      });

      res.json({ ok: true, visitorId: result.visitorId });
    } catch (err) {
      console.error("[server] /track error:", err);
      res.status(500).json({ error: "Internal server error" });
    }
  });

  /**
   * POST /identify — explicit identification (e.g., after login or form fill).
   * Body: { visitorId, email?, name?, phone?, company? }
   */
  app.post("/identify", (req, res) => {
    try {
      const visitorId = req.body.visitorId || req.cookies?.vid;
      if (!visitorId) {
        return res.status(400).json({ error: "visitorId required" });
      }

      identifyVisitor(visitorId, {
        email: req.body.email,
        name: req.body.name,
        phone: req.body.phone,
        company: req.body.company,
      });

      res.json({ ok: true });
    } catch (err) {
      console.error("[server] /identify error:", err);
      res.status(500).json({ error: "Internal server error" });
    }
  });

  /**
   * POST /preapproval/sofi — preapproval for an incoming SOFI lead.
   * Body: { annualRevenue, creditScore?, timeInBusinessYears? | businessStartDate? }
   * Returns approved/declined plus a preapproval amount for Term Loan/MCA and for LOC/Revolving MCA.
   */
  app.post("/preapproval/sofi", (req, res) => {
    try {
      res.json(
        preapprove({
          annualRevenue: req.body.annualRevenue,
          creditScore: req.body.creditScore,
          timeInBusinessYears: req.body.timeInBusinessYears,
          businessStartDate: req.body.businessStartDate,
        }),
      );
    } catch (err) {
      if (err instanceof InvalidLeadError) {
        return res.status(400).json({ error: err.message });
      }
      console.error("[server] /preapproval/sofi error:", err);
      res.status(500).json({ error: "Internal server error" });
    }
  });

  /**
   * GET /snippet.js — serves the client-side tracking snippet.
   */
  app.get("/snippet.js", (_req, res) => {
    res.setHeader("Content-Type", "application/javascript");
    res.send(getSnippetJs());
  });

  return app;
}

function getSnippetJs(): string {
  return `
(function() {
  var TRACKER_URL = "${config.trackerDomain}";

  function post(path, data) {
    fetch(TRACKER_URL + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(data)
    }).catch(function() {});
  }

  // Track page views
  function trackPageview() {
    post("/track", {
      eventType: "pageview",
      pageUrl: window.location.href,
      referrer: document.referrer
    });
  }

  // Track form interactions
  function trackForms() {
    document.addEventListener("focusin", function(e) {
      var form = e.target.closest && e.target.closest("form");
      if (form && !form._tracked) {
        form._tracked = true;
        post("/track", {
          eventType: "form_start",
          pageUrl: window.location.href
        });
      }
    });

    document.addEventListener("submit", function(e) {
      var form = e.target;
      if (!form || form.tagName !== "FORM") return;
      var data = {};
      try {
        var fd = new FormData(form);
        fd.forEach(function(v, k) {
          var kl = k.toLowerCase();
          if (kl.includes("email")) data.email = v;
          else if (kl.includes("name")) data.name = v;
          else if (kl.includes("phone") || kl.includes("tel")) data.phone = v;
          else if (kl.includes("company") || kl.includes("org")) data.company = v;
        });
      } catch(err) {}
      post("/track", {
        eventType: "form_submit",
        pageUrl: window.location.href,
        metadata: data
      });
    });
  }

  // Track SPA navigation
  var lastUrl = window.location.href;
  function checkUrlChange() {
    if (window.location.href !== lastUrl) {
      lastUrl = window.location.href;
      trackPageview();
    }
  }
  setInterval(checkUrlChange, 1000);

  // Init
  trackPageview();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", trackForms);
  } else {
    trackForms();
  }
})();
`.trim();
}

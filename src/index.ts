import { config } from "./config";
import { createServer } from "./server";

const app = createServer();

app.listen(config.port, () => {
  console.log(`
  ╔══════════════════════════════════════════════════╗
  ║   Visitor Intent Detection Agent                 ║
  ║   Running on port ${String(config.port).padEnd(30)}║
  ╠══════════════════════════════════════════════════╣
  ║   POST /track      — ingest visitor events       ║
  ║   POST /identify   — identify a visitor          ║
  ║   POST /preapproval/sofi — SOFI lead preapproval ║
  ║   GET  /snippet.js — client tracking snippet     ║
  ║   GET  /health     — health check                ║
  ╚══════════════════════════════════════════════════╝

  Add this to your site:
  <script src="${config.trackerDomain}/snippet.js"></script>
  `);
});

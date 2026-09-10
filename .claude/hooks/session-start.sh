#!/bin/bash
# SessionStart hook: prepares the environment for Claude Code on the web.
# - Installs project dependencies
# - Installs the Salesforce CLI (`sf`, with `sfdx` alias) for SF data analysis
# - Authenticates to a Salesforce org if SFDX_AUTH_URL is set in the environment
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# --- Project dependencies -------------------------------------------------
# Non-fatal: a broken project dependency must not block the Salesforce CLI.
if [ -f package.json ]; then
  npm install --no-audit --no-fund || echo "WARNING: npm install failed; continuing."
fi

# --- Salesforce CLI ---------------------------------------------------------
if ! command -v sf >/dev/null 2>&1; then
  echo "Installing Salesforce CLI..."
  npm install -g @salesforce/cli --no-audit --no-fund
fi
echo "Salesforce CLI: $(sf --version)"

# Non-interactive, no telemetry, no update nags in a headless container.
sf config set disable-telemetry true --global >/dev/null 2>&1 || true
{
  echo 'export SF_DISABLE_TELEMETRY=true'
  echo 'export SF_AUTOUPDATE_DISABLE=true'
  echo 'export SF_DISABLE_AUTOUPDATE=true'
} >> "$CLAUDE_ENV_FILE"

# --- Salesforce org auth (optional) ----------------------------------------
# Set SFDX_AUTH_URL as an environment variable/secret in the Claude Code
# environment. Generate it once from an authenticated machine with:
#   sf org display --target-org <alias> --verbose --json  (field: sfdxAuthUrl)
if [ -n "${SFDX_AUTH_URL:-}" ]; then
  echo "Authenticating to Salesforce org from SFDX_AUTH_URL..."
  auth_file="$(mktemp)"
  printf '%s' "$SFDX_AUTH_URL" > "$auth_file"
  sf org login sfdx-url --sfdx-url-file "$auth_file" --alias "${SF_ORG_ALIAS:-sfdata}" --set-default
  rm -f "$auth_file"
  sf org display --target-org "${SF_ORG_ALIAS:-sfdata}" || true
else
  echo "SFDX_AUTH_URL not set; skipping Salesforce org auth."
fi

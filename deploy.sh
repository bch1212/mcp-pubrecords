#!/usr/bin/env bash
# Halverson IQ Data — Railway deploy script.
#
# Run on Brett's Mac (the Cowork sandbox blocks Railway/Stripe/Cloudflare APIs).
# Inherits secrets from ../. deploy-secrets.env.
#
# Usage:
#   cd ~/Projects/agentic-builds/Build\ Prompts\ from\ OpenClaw/mcp-pubrecords
#   ./deploy.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

SECRETS_FILE="$(cd "$PROJECT_DIR/.." && pwd)/.deploy-secrets.env"
if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "ERROR: $SECRETS_FILE not found" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a
source "$SECRETS_FILE"
set +a

# Railway CLI rejects when both RAILWAY_TOKEN and RAILWAY_API_TOKEN are set.
# Promote the shared TOKEN to API_TOKEN, then unset the legacy var.
if [[ -n "${RAILWAY_TOKEN:-}" ]]; then
  export RAILWAY_API_TOKEN="$RAILWAY_TOKEN"
  unset RAILWAY_TOKEN
fi

if ! command -v railway >/dev/null 2>&1; then
  echo "Installing Railway CLI..."
  brew install railway || npm i -g @railway/cli
fi

# Always (re)install deps locally so smoke checks work
if [[ ! -d ".venv" ]] || ! .venv/bin/python -c "import fastapi, fastmcp, httpx, respx" 2>/dev/null; then
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip
  ./.venv/bin/pip install -r requirements.txt
fi

echo "==> Running test suite locally before deploy"
./.venv/bin/python -m pytest -q

# Initialize Railway project on first run
if [[ ! -f ".railway/config.json" ]] && [[ ! -f "railway.json" ]]; then
  echo "==> Initializing Railway project (interactive)"
  railway init
fi

echo "==> Setting Railway environment variables"
# Keep an existing admin token. Generating a new one on every deploy would
# lock out /admin/keys. The value is sent to Railway and is not printed.
if [[ -z "${PUBRECORDS_ADMIN_TOKEN:-}" ]]; then
  PUBRECORDS_ADMIN_TOKEN="$(openssl rand -hex 24)"
  echo "PUBRECORDS_ADMIN_TOKEN was unset. A new token was stored in Railway."
  echo "Read it from the Railway dashboard. It is not printed here."
fi
railway variables --set "PUBRECORDS_SEC_USER_AGENT=HalversonIQData brett.halverson@gmail.com" \
                  --set "PUBRECORDS_CACHE_TTL=86400" \
                  --set "PUBRECORDS_LOG_LEVEL=INFO" \
                  --set "PUBRECORDS_ADMIN_TOKEN=${PUBRECORDS_ADMIN_TOKEN}"

# Optional upstream tokens. Values are passed to Railway and are not printed.
[[ -n "${OPENCORPORATES_TOKEN:-}" ]] && railway variables --set "OPENCORPORATES_TOKEN=$OPENCORPORATES_TOKEN"
[[ -n "${COURTLISTENER_TOKEN:-}" ]] && railway variables --set "COURTLISTENER_TOKEN=$COURTLISTENER_TOKEN"
[[ -n "${SAM_API_KEY:-}" ]] && railway variables --set "SAM_API_KEY=$SAM_API_KEY"

echo "==> Deploying"
railway up --detach

echo "==> Waiting 25s for boot"
sleep 25

DOMAIN="$(railway domain 2>/dev/null | tail -1 || true)"
if [[ -z "$DOMAIN" ]]; then
  DOMAIN="$(railway status --json 2>/dev/null | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("domain",""))' || true)"
fi
[[ -z "$DOMAIN" ]] && DOMAIN="mcp-pubrecords.up.railway.app"

echo "==> Smoke checks against https://$DOMAIN"
curl -fsS "https://$DOMAIN/health" | python3 -m json.tool
if [[ -n "${HALVERSON_SMOKE_API_KEY:-}" ]]; then
  curl -fsS -H "X-API-Key: ${HALVERSON_SMOKE_API_KEY}" \
    "https://$DOMAIN/usage" | python3 -m json.tool
else
  echo "Skipping /usage smoke. Set HALVERSON_SMOKE_API_KEY to an issued customer key."
fi

echo
echo "==> Done. Add to Claude with a per-user API key:"
echo "    claude mcp add --transport http halverson-iq-data https://$DOMAIN/mcp/"

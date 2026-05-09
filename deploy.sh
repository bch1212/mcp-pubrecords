#!/usr/bin/env bash
# PubRecords MCP — Railway deploy script.
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
railway variables --set "PUBRECORDS_SEC_USER_AGENT=PubRecordsMCP brett.halverson@gmail.com" \
                  --set "PUBRECORDS_CACHE_TTL=86400" \
                  --set "PUBRECORDS_LOG_LEVEL=INFO" \
                  --set "PUBRECORDS_ADMIN_TOKEN=$(openssl rand -hex 24)"

# Optional: set tokens if present in secrets file
[[ -n "${OPENCORPORATES_TOKEN:-}" ]] && railway variables --set "OPENCORPORATES_TOKEN=$OPENCORPORATES_TOKEN"
[[ -n "${COURTLISTENER_TOKEN:-}" ]] && railway variables --set "COURTLISTENER_TOKEN=$COURTLISTENER_TOKEN"

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
curl -fsS -H "X-API-Key: pubrecords-dev-key-001" \
  "https://$DOMAIN/usage" | python3 -m json.tool

echo
echo "==> Done. Add to Claude:"
echo "    claude mcp add pubrecords-mcp --url https://$DOMAIN/mcp"

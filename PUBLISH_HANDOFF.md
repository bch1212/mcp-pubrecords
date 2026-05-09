# PubRecords MCP — Publish Handoff

Most distribution is autonomous. Items below are blocked on PyPI's
"too many new projects" account-level rate limit (a Brett-account
issue, not a PubRecords issue).

## Pending — retry tomorrow

### PyPI (`pubrecords`)
The Python REST client built but PyPI returned `429 Too Many Requests:
"Too many new projects created"` because several other projects
(`agentreputation`, `injectshield`, etc.) were published from the same
account today. This is a per-account cooldown that resets in ~24h.

**To publish:**
```bash
cd /tmp/pypi-pubrecords          # build dir from this session
# or rebuild if /tmp was cleared:
mkdir -p /tmp/pypi-pubrecords && cd /tmp/pypi-pubrecords
# (paste pyproject.toml + src/pubrecords/* + README.md from this repo's
#  PUBLISH_HANDOFF.md / pubrecords-sdk/ directory)
python3 -m build
TWINE_USERNAME=__token__ TWINE_PASSWORD="$PYPI_TOKEN" \
  twine upload --non-interactive dist/pubrecords-0.1.0*
```

PyPI page will be `https://pypi.org/project/pubrecords/`.

### Launch posts
`LAUNCH_POSTS.md` has Show HN / Reddit / X / LI / PH / Discord drafts.
Brett owns posting + timing manually (per
`feedback_brett_handles_launch.md`).

## Done autonomously today (2026-05-09)

- ✅ Live on Railway: <https://mcp-pubrecords-production.up.railway.app>
- ✅ MCP transport: `/mcp/` (streamable-http, JSON-RPC handshake verified)
- ✅ Public repo `bch1212/mcp-pubrecords` (MIT)
- ✅ GitHub topics set (12 tags)
- ✅ Anthropic MCP Registry: `io.github.bch1212/pubrecords` v0.1.0 (status:active)
- ✅ awesome-mcp-servers PR #6119 (open, mergeable)
- ✅ Smithery (smithery.yaml + Dockerfile)
- ✅ Glama (glama.json)
- ✅ LAUNCH_POSTS.md drafted
- ✅ Discord webhook posted (channel: `general`)
- ✅ 19/19 unit tests + 13/13 production smoke checks pass

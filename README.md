# WhenPeak Integrations

Reference integrations for the [WhenPeak](https://whenpeak.com) performance-intelligence API —
the API that predicts when a person's brain works best from their sleep data.

Everything here is a **thin client over the public API**. No prediction logic lives in this repo;
the model stays behind the API. These are meant to be copied, learned from, and adapted.

## What's inside

| Path | What it is |
|---|---|
| `mcp_server.py` | A Model Context Protocol server (FastMCP) exposing WhenPeak to Claude, Claude Code, and other MCP agents. Serves both the current Streamable HTTP transport and the legacy SSE transport from one process. A working reference for "MCP server that proxies a REST API." |
| `server.json` | Manifest for the [Official MCP Registry](https://modelcontextprotocol.io/registry). Metadata only; it does not affect how the server runs. |
| `skill_example.py` | A minimal end-to-end example of the agentic tool-use loop with the Anthropic SDK: model → `tool_use` → API call → `tool_result` → final answer. Includes `--auto` behavioural checks. |
| `gpt/instructions.md` | The system prompt + setup for wiring WhenPeak into a ChatGPT GPT. |
| `gpt/openapi_action.yaml` | The OpenAPI action schema for the public `/api/v1/predict` endpoint. |
| `claude/` | A [Claude Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills) — drop-in folder that teaches Claude (Claude.ai, Claude Code, Cowork) to collect sleep data, call the API, and turn the response into scheduling advice with a performance-curve chart. |

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env        # fill in keys
```

**MCP server** (the public `predict` tools need no key; the authed tools need `WHENPEAK_API_KEY`):

```bash
python mcp_server.py        # /mcp, /sse, /messages/ and /health on :8080
```

Point an MCP client at `http://localhost:8080/mcp`. That is Streamable HTTP, the current spec
transport. `/sse` is still served for older clients that only speak the legacy transport, but new
clients should use `/mcp`.

Already hosted: `https://mcp.whenpeak.com/mcp`. You only need to run your own copy if you want the
authenticated tools against your own API key.

### Deploying your own copy

Set `WHENPEAK_API_URL` and `WHENPEAK_API_KEY` as environment variables on your host, plus the two
allowlists:

```bash
WHENPEAK_API_URL=https://api.whenpeak.com
WHENPEAK_API_KEY=pk_live_...              # only needed for the two authed tools
MCP_ALLOWED_HOSTS=mcp.example.com,mcp-prod.up.somehost.app
MCP_ALLOWED_ORIGINS=https://claude.ai,https://example.com
```

The server validates the `Host` and `Origin` headers on MCP requests, which the spec requires as
DNS-rebinding protection. The built-in default only covers localhost, so **a deployed copy with no
`MCP_ALLOWED_HOSTS` returns 421 to every MCP client**. List every hostname the service actually
answers on, including any platform-assigned domain. Only `:*` port wildcards are matched, so
`example.com:*` works and `*.example.com` does not.

`MCP_ALLOWED_ORIGINS` applies to browser-based clients only. A request with no `Origin` header
passes, so curl and server-side agents are unaffected; a rejected origin returns 403 and is fixed by
adding it to the list. `/health` sits outside both checks, so a wrong allowlist can never fail a
platform health probe.

**Agentic skill example** (needs `ANTHROPIC_API_KEY`):

```bash
python skill_example.py --auto   # conversation-flow checks
python skill_example.py          # interactive
```

## Get an API key

The `/api/v1/predict` endpoint is public — no key needed. For the authenticated
endpoints, register a free key (1,000 calls/month):

Create a free account at [whenpeak.com/dashboard.html](https://whenpeak.com/dashboard.html) — your `pk_live` key is issued on signup (Free tier: 1,000 calls/month).

Full API docs: https://whenpeak.com/docs

## Calling /predict

`POST /api/v1/predict` (single day) and `POST /api/v1/predict/week?days=N` (7–30 day flat projection)
take one JSON body. A few contract details that trip standard clients:

- **Required:** `wake_time`, `sleep_time` — both `"HH:MM"`.
- `sleep_quality` — `good` / `fair` / `poor` (defaults to `fair`).
- **Optional — omit if unknown, do not send as `null`:** `exercise_yesterday` (bool) and
  `exercise_timing` (`morning` / `afternoon` / `evening`) are typed as plain values, so an explicit
  `null` returns a **422 that looks like a missing required field**. Leave the keys out instead.
  `sleep_latency_minutes` and `waso_minutes` (numbers) are also optional; these two *do* accept
  `null`, but omitting is still cleaner.
- **Response scores are floats:** `dps`, and each `peak_1` / `peak_2` / `dip` `value`, come back like
  `82.5`, not `82`. Don't type them as `int`.

The pitfall: a client that serializes its whole model — sending unset optionals as `null` — 422s on
the exercise fields. Send only the fields you actually have. The bundled `whenpeak_predict.py`,
the GPT action, and the MCP server all do this correctly; copy that pattern.

```bash
# correct — optional fields simply omitted
curl -s -X POST https://api.whenpeak.com/api/v1/predict -H 'Content-Type: application/json' \
  -d '{"wake_time":"07:00","sleep_time":"00:30","sleep_quality":"good"}'
```

## License

MIT — see [LICENSE](LICENSE). Use it however you like.

## Claude Skill

The `claude/` folder is a self-contained [Agent Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills):

```
claude/
├── README.md                     # full bundle: skill + connector setup
├── SKILL.md                      # instructions + when to trigger
├── scripts/
│   ├── whenpeak_predict.py       # stdlib-only API client (no installs)
│   └── whenpeak_chart.py         # single-day curve (matplotlib, code-execution fallback)
├── templates/daily_plan.md       # answer structure
└── examples/                     # worked single-day + week flows, sample JSON
```

Use it by uploading the folder as a skill in Claude.ai (Settings → Capabilities → Skills), or in Claude Code by placing it under `.claude/skills/whenpeak/`.

**How the skill reaches the API.** The prediction is always fetched server-side, never from a browser
artifact (Claude.ai's artifact and code sandboxes both block outbound calls to `api.whenpeak.com`).
Inside the app the skill uses the **WhenPeak connector**, which runs on Anthropic's side outside the
sandbox — the same way the GPT reaches the API through ChatGPT's server side. Connect it in
**Claude Desktop or Claude Code** (setup in [`claude/README.md`](claude/README.md)); the claude.ai
web custom-connector flow is currently unreliable. In Claude Code (or any host with network egress)
the bundled script reaches the public endpoints directly. The scripts also work standalone:

```bash
python claude/scripts/whenpeak_predict.py --wake 07:00 --sleep 00:30 --quality good
python claude/scripts/whenpeak_predict.py --wake 07:00 --sleep 00:30 --quality good --days 7
```

## Changelog

### August 2026
- **Streamable HTTP transport.** The MCP server now speaks the current transport at `/mcp` alongside the legacy SSE transport at `/sse`, from a single process. Point new clients at `/mcp`; SSE was deprecated in the 2025-03-26 spec revision and is kept only for backwards compatibility. Sessions are stateless, so no `Mcp-Session-Id` is issued, matching the stateless API underneath. `Host` and `Origin` validation is on by default as the spec requires, configured through `MCP_ALLOWED_HOSTS` and `MCP_ALLOWED_ORIGINS`.
- **`server.json`.** Manifest for the Official MCP Registry, describing the hosted server and its endpoints.
- **Suggestion endpoint: the model in reverse.** New `POST /api/v1/performance/suggest` on the authenticated API. Prediction answers "given my behaviour, what is my curve"; suggestion answers "given a target, what behaviour gets me there", working backward from a future target to tonight. Three target shapes: `point` (be sharp at a moment), `window` (hold capacity across a span), and `shift` (move your whole body clock, for jet lag or for waking earlier permanently). Returns a night-by-night plan, a projected event-day outcome, an honest feasibility label, and a confidence label that matures as sleep history accumulates. Full reference at https://whenpeak.com/docs
- Note for this repo: the integrations here are keyless clients over the public prediction endpoints, so none of them wrap `/suggest`. It needs an API key and a stored sleep history. Call it from your own authenticated client, or use the WhenPeak app.

### June 2026
- **/predict contract clarified.** Optional fields must be omitted, not sent as `null`
  (`exercise_yesterday` / `exercise_timing` 422 on an explicit `null`); response scores are floats
  (`dps: 82.5`, not `82`). The skill, GPT action, and MCP server all build requests this way.
- **Claude Skill.** New `claude/` folder — a drop-in Agent Skill for Claude.ai, Claude Code, and Cowork, with a stdlib-only API client and a performance-curve chart.
- **Multi-day predictions.** New MCP tool `whenpeak_multiday_predict` and GPT action `predictWeek` (`POST /api/v1/predict/week?days=N`, 7–30 days). Authenticated users get the behavioural forecast at `GET /api/v1/performance/forecast`.
- **Scoring v2.** Responses now include `internal_dps` and a `scoring` breakdown alongside `dps`. Missing sensors are no longer scored as zero; behaviours (exercise, mindfulness) are positive-only bonuses; the maximum score scales with data breadth (sleep only → 90, two sources → 95, three+ → 100). No breaking changes — `dps` keeps its key and range.

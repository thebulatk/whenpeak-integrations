# WhenPeak Integrations

Reference integrations for the [WhenPeak](https://whenpeak.com) performance-intelligence API —
the API that predicts when a person's brain works best from their sleep data.

Everything here is a **thin client over the public API**. No prediction logic lives in this repo;
the model stays behind the API. These are meant to be copied, learned from, and adapted.

## What's inside

| Path | What it is |
|---|---|
| `mcp_server.py` | A Model Context Protocol server (FastMCP) exposing WhenPeak to Claude Desktop and other MCP agents. A working reference for "MCP server that proxies a REST API." |
| `skill_example.py` | A minimal end-to-end example of the agentic tool-use loop with the Anthropic SDK: model → `tool_use` → API call → `tool_result` → final answer. Includes `--auto` behavioural checks. |
| `gpt/instructions.md` | The system prompt + setup for wiring WhenPeak into a ChatGPT GPT. |
| `gpt/openapi_action.yaml` | The OpenAPI action schema for the public `/api/v1/predict` endpoint. |
| `claude/` | A [Claude Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills) — drop-in folder that teaches Claude (Claude.ai, Claude Code, Cowork) to collect sleep data, call the API, and turn the response into scheduling advice with a brand-styled performance-curve chart. |

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env        # fill in keys
```

**MCP server** (the public `predict` tool needs no key; the authed tools need `WHENPEAK_API_KEY`):

```bash
python mcp_server.py        # serves SSE at /sse, health at /health
```

Point an MCP client at `http://localhost:8080/sse`. To deploy, set `WHENPEAK_API_URL` and
`WHENPEAK_API_KEY` as environment variables on your host.

**Agentic skill example** (needs `ANTHROPIC_API_KEY`):

```bash
python skill_example.py --auto   # conversation-flow checks
python skill_example.py          # interactive
```

## Get an API key

The `/api/v1/predict` endpoint is public — no key needed. For the authenticated
endpoints, register a free key (1,000 calls/month):

```bash
curl -X POST https://api.whenpeak.com/api/v1/auth/register \
  -H "Content-Type: application/json" -d '{"label":"my app"}'
```

Full API docs: https://whenpeak.com/docs

## License

MIT — see [LICENSE](LICENSE). Use it however you like.

## Claude Skill

The `claude/` folder is a self-contained [Agent Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills):

```
claude/
├── SKILL.md                      # instructions + when to trigger
├── scripts/
│   ├── whenpeak_predict.py       # stdlib-only API client (no installs)
│   └── whenpeak_chart.py         # brand-styled single-day curve (matplotlib)
├── templates/daily_plan.md       # answer structure
└── examples/                     # worked single-day + week flows, sample JSON
```

Use it by uploading the folder as a skill in Claude.ai (Settings → Capabilities → Skills), or in Claude Code by placing it under `.claude/skills/whenpeak/`. The scripts also work standalone:

```bash
python claude/scripts/whenpeak_predict.py --wake 07:00 --sleep 23:00 --quality good
python claude/scripts/whenpeak_predict.py --wake 07:00 --sleep 23:00 --quality good --days 7
```

## Changelog

### June 2026
- **Claude Skill.** New `claude/` folder — a drop-in Agent Skill for Claude.ai, Claude Code, and Cowork, with a stdlib-only API client and a brand-styled curve chart script.
- **Multi-day predictions.** New MCP tool `whenpeak_multiday_predict` and GPT action `predictWeek` (`POST /api/v1/predict/week?days=N`, 7–30 days). Authenticated users get the behavioural forecast at `GET /api/v1/performance/forecast`.
- **Scoring v2.** Responses now include `internal_dps` and a `scoring` breakdown alongside `dps`. Missing sensors are no longer scored as zero; behaviours (exercise, mindfulness) are positive-only bonuses; the maximum score scales with data breadth (sleep only → 90, two sources → 95, three+ → 100). No breaking changes — `dps` keeps its key and range.

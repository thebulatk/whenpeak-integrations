# WhenPeak for Claude — the full bundle (skill + connector)

[WhenPeak](https://whenpeak.com) predicts when a person's brain works best from their sleep —
the peak windows, the natural dip, and how strong the day will be. This folder makes that work
inside Claude.

It has **two pieces, and you need both**:

- **The connector** — the *transport*. It gives Claude the WhenPeak tools and is the only thing
  that can actually reach the API from inside the Claude.ai app (the in-app sandbox blocks direct
  calls to `api.whenpeak.com`).
- **The skill** — the *behaviour*. It teaches Claude how to collect sleep data, read the
  prediction, and turn it into scheduling advice: lead with timing, draw the curve, handle
  multi-day, talk about the score honestly.

| You have… | Result |
|---|---|
| Connector only | Works, but generic — Claude wraps the raw tools however it likes |
| Skill only | **Doesn't work in the Claude.ai app** — no transport, so it can't fetch a prediction |
| **Skill + connector** | The actual product: WhenPeak's tools *and* WhenPeak's behaviour |

## Install

### 1. Connect the WhenPeak connector (the transport)

**Claude Desktop** — add to `claude_desktop_config.json`
(Settings -> Developer -> Edit Config), then restart Claude Desktop:

```json
{
  "mcpServers": {
    "whenpeak": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://mcp.whenpeak.com/sse"]
    }
  }
}
```

**Claude Code:**

```bash
claude mcp add --transport sse --scope user whenpeak https://mcp.whenpeak.com/sse
```

**claude.ai (web):** the web custom-connector flow is currently unreliable for servers like this
one (it assumes OAuth and frequently fails). Use Claude Desktop or Claude Code above, or the
zero-setup channels: the WhenPeak GPT and [whenpeak.com](https://whenpeak.com) itself.

Confirm it's working by running a prediction directly:

> "Run whenpeak_quick_predict: wake 07:00, sleep 23:00, quality good"

You should get a performance curve with peak and dip times. If Claude says the tool doesn't exist,
clear the mcp-remote cache (`rm -rf ~/.mcp-auth ~/.npm/_npx`) and restart Claude Desktop.

### 2. Add the skill (the behaviour)

- **Claude.ai / Desktop:** Settings -> Capabilities -> Skills -> upload this folder.
- **Claude Code:** place this folder at `.claude/skills/whenpeak/`.

### 3. Use it

The skill triggers automatically — you don't need to mention WhenPeak. It activates whenever
someone asks about timing, focus, scheduling, chronotype, or how last night's sleep affects today.
The SKILL.md description handles this; the connector handles the API call.

> "I slept 1am to 7:30am, fair quality — when should I do my deep work today?"

Claude recognises the intent, collects any missing sleep details, calls `whenpeak_quick_predict`
through the connector, and answers with peak windows, the dip, and a performance curve.

## What's in this folder

```
.
├── SKILL.md                      # the behaviour + when to trigger (read this first)
├── README.md                     # this file
├── scripts/
│   ├── whenpeak_predict.py       # stdlib-only API client (Claude Code / open-network hosts)
│   └── whenpeak_chart.py         # single-day curve as a PNG (matplotlib, code-execution path)
├── templates/
│   └── daily_plan.md             # the answer structure
└── examples/
    ├── example_single_day.md     # full single-day flow: inputs -> JSON -> ideal answer
    ├── example_week.md           # multi-day flow incl. the consistency question
    └── sample_response.json      # a real response shape for testing offline
```

## How it reaches the API

The prediction is **always fetched server-side**, never from a browser artifact — Claude.ai's
artifact and code sandboxes both block outbound calls to `api.whenpeak.com`. There are two
server-side transports, and the skill uses whichever is present:

- **The connector** runs on Anthropic's infrastructure, outside the sandbox — this is the path
  inside the Claude.ai app and Claude Desktop. It's the same way the WhenPeak GPT reaches the API
  through ChatGPT's server side.
- **The bundled `scripts/whenpeak_predict.py`** runs wherever the code sandbox has network egress
  (Claude Code, or any host that allows it). Stdlib only, no installs:

  ```bash
  python scripts/whenpeak_predict.py --wake 07:00 --sleep 00:30 --quality good
  python scripts/whenpeak_predict.py --wake 07:00 --sleep 00:30 --quality good --days 7
  ```

If neither is available, the skill says so and points to the connector or whenpeak.com — it never
invents a prediction.

### Request-contract gotchas (only if you call the API by hand)

The bundled script and the connector both handle these for you.

- **Optional fields must be omitted, not sent as `null`.** `exercise_yesterday` and
  `exercise_timing` are plain-typed, so an explicit `null` returns a **422 that looks like a missing
  required field**. Leave unknown keys out. (`sleep_latency_minutes` / `waso_minutes` do accept
  `null`, but omitting is still cleaner.)
- **Response scores are floats** — `dps`, and each peak/dip `value`, come back like `82.5`, not
  `82`. Don't type them as `int`.

## Scope

This is the free, no-account channel: **today's prediction** and a flat multi-day projection from
one self-report. It deliberately does **not** do wearable sync, the personalised behavioural
forecast, suggestions, or calendar management — those live in the WhenPeak app and the
authenticated API. Scope matches the WhenPeak ChatGPT GPT.

## Troubleshooting

- **"The code sandbox can't reach api.whenpeak.com" / "Could not reach the WhenPeak API."**
  The connector isn't connected. Connect it (step 1) or use whenpeak.com. Reinstalling the skill
  won't fix this — the skill needs the connector as its transport.
- **Connector won't connect on claude.ai web.** Known limitation. Use Claude Desktop or Claude
  Code instead.
- **Tool call returns "not found" despite the connector being listed.** Clear the cache:
  `rm -rf ~/.mcp-auth ~/.npm/_npx`, restart Claude Desktop, then call the tool directly rather
  than asking "what tools do you have?" — Desktop's tool search surfaces a subset, not the full list.

## License

MIT. Use it however you like.

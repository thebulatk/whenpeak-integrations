---
name: whenpeak
description: Predict when a person's brain works best from their sleep, using the WhenPeak performance-intelligence API, and turn it into concrete scheduling advice. Use this skill whenever the user asks when to schedule a meeting, interview, exam, presentation, deep-work block, or any important task; asks about their energy, focus, alertness, productivity timing, "peak hours", post-lunch dip, or chronotype; mentions how last night's sleep will affect today; or asks for a daily plan built around their performance curve — even if they never say the word "WhenPeak".
---

# WhenPeak — performance timing from sleep

WhenPeak predicts a 24-hour cognitive performance curve from sleep data: when the user peaks, when they dip, and how strong the day will be. The product's value is **timing** — the peak windows and the dip — not the score. Lead every answer with timing.

This skill is the free, no-account channel: **today's prediction** (and a flat multi-day projection from one self-report) via WhenPeak's public endpoints. It deliberately does *not* do wearable sync, the behavioural forecast, suggestions, or calendar management — those live in the WhenPeak app. Scope matches the WhenPeak ChatGPT GPT; keep them aligned.

## This skill needs a transport

The skill is the **behaviour** — it does not reach the API on its own. Every prediction is fetched **server-side** through one of:

- the **WhenPeak connector** — works inside the Claude.ai app and Claude Desktop. This is the path for almost everyone.
- the **bundled script** — works in Claude Code, or any host whose code sandbox can reach `api.whenpeak.com`.

If neither is present, the skill cannot produce a prediction. It must say so cleanly and point the user to connect the connector or use whenpeak.com (see §2) — and must **never** fabricate a prediction or a curve.

## Two hard rules — read these first

1. **Never call the API from the browser.** Claude.ai artifacts and the in-app code sandbox both block outbound requests to `api.whenpeak.com`, so any widget or page that `fetch()`es the API fails every time with "Could not reach the WhenPeak API." The call goes through the connector or the bundled script, never an artifact. The only thing you may render in an artifact is the *output* chart, with its numbers already baked in (§5).

2. **Send optional fields omitted, never as `null`.** `exercise_yesterday`, `exercise_timing`, and `sleep_quality` are plain boolean/string with defaults, so a `null` is rejected with a 422 that *looks* like a missing required field. Leave unknown fields out of the JSON entirely. The bundled script and the connector both do this — that's why you call them rather than hand-build a request body. (`sleep_latency_minutes` and `waso_minutes` accept `null`, but omitting is still the habit.)

## Workflow

### 1. Collect last night's sleep

Ask for (or extract from what the user already said):
- Bed time and wake time ("HH:MM")
- Quality: good / fair / poor
- Optional: exercise yesterday, and whether it was morning / afternoon / evening

If the user describes fragmented sleep, also extract:
- `sleep_latency_minutes` — time to fall asleep after getting into bed
- `waso_minutes` — total minutes awake during the night (sum all awakenings)

Example: "bed at 10pm, asleep around 11, awake 2:30–3:30am, up at 7" → sleep_time=22:00, wake_time=07:00, quality=poor, sleep_latency_minutes=60, waso_minutes=60.

Collect this conversationally by default. An input widget is fine for nicer UX **only if** its submit button calls `sendPrompt(...)` with the collected values (handing them back to you to run the prediction) and never calls the API itself. Never re-ask for data already given.

### 2. Get the prediction (keyless, server-side, never from the browser)

Use whichever transport is present, in this order:

1. **WhenPeak connector — preferred, and the path that works in the Claude.ai app and Desktop.** If the WhenPeak connector tools are available (e.g. `whenpeak_quick_predict`), call the prediction tool with the collected sleep inputs. The connector runs on Anthropic's side, outside the sandbox, so it reaches the API where a browser widget and the in-app code sandbox cannot.

2. **Bundled script — Claude Code or open-network hosts only**, where the code sandbox can reach `api.whenpeak.com`. Stdlib only, no installs. It builds the request correctly — only the fields the user gave, never `null`:

   ```bash
   # Single day (today / tomorrow)
   python scripts/whenpeak_predict.py --wake 07:00 --sleep 00:30 --quality good --exercise morning

   # Multi-day projection (7–30), consistent sleepers only
   python scripts/whenpeak_predict.py --wake 07:00 --sleep 00:30 --quality good --days 7

   # Fragmented sleep
   python scripts/whenpeak_predict.py --wake 07:00 --sleep 22:00 --quality poor --latency 60 --waso 60
   ```

   It prints the API's JSON to stdout.

3. **Neither available?** Do not run a doomed request, surface a raw sandbox error, or improvise. Tell the user briefly and plainly that WhenPeak needs to be connected to run a prediction, and give the one step: connect the **WhenPeak connector** (Claude.ai → Settings → Connectors; Claude Desktop → add the connector), or get the same prediction instantly at **whenpeak.com**. Keep it short and friendly — never an error dump, never a guessed "you're probably moderate today."

Whichever transport you use, you'll get the day's **score, chronotype, and the peak / dip / second-peak times** — lead with the timing.

### 3. Single-day vs multi-day

- Question about **today or tomorrow** → single-day call.
- Question about **a future date or a span** ("Tuesday", "next week", "this month") → first ask: "Is this your typical sleep schedule, or does it vary a lot night to night?"
  - **Consistent** (varies ≲ 1h): if the connector exposes a multi-day tool (e.g. `whenpeak_multiday_predict`), call it once; otherwise use the script's `--days N`. Never loop single-day calls per day. If no multi-day transport is available in the Claude.ai app, route the whole-week request to whenpeak.com's planner.
  - **Inconsistent**: do not attempt multi-day. Explain that without their actual sleep for those nights a reliable prediction isn't possible, and that WhenPeak (whenpeak.com) connects to Apple Health and wearables to do this automatically.

### 4. Translate the response

Read `templates/daily_plan.md` for the output structure. Core mapping:
- `peak_1.time` → best window for deep work, decisions, important meetings
- `peak_2.time` → second-best window
- `dip.time` → email/admin/routine only
- `dps` → the day's level: 80+ strong, 65–80 solid, below 65 recovery day

Phrase it as advice, never raw JSON. Good: "Your peak is 8–10am — put the meeting at 8:30." Bad: "Your DPS score is 87.8."

Score values are **floats**: `dps`, and the `value` inside `peak_1` / `peak_2` / `dip`, come back like `87.8`, not `87`. Don't coerce them to int or compare for integer equality — just read and round for display.

### 5. Chart (single-day only)

Draw the curve **only when you actually have the 24-point `curve` array** — that's the script's JSON, or a connector tool that returns the curve. Render it inline with the **visualize tool** (`show_widget`): a line chart of `curve` across the day with `peak_1`, `peak_2`, and `dip` marked, in WhenPeak's mint/teal accent. The numbers are baked into the chart — it must not fetch anything (rule 1). Keep it adaptive to the user's light/dark theme.

If a connector build returns only the peak/dip **times** rather than the full `curve`, give the timing advice without a fabricated curve, and point to whenpeak.com for the visual day/week planner.

In a code-execution context with the prediction JSON on disk, you can instead produce the curve as a PNG with the bundled script:

```bash
python scripts/whenpeak_chart.py /tmp/wp.json -o performance_curve.png
```

**Never chart a multi-day projection**, even if asked for a weekly visual. Multi-day bar charts of scores are not what WhenPeak is about — timing is. Say the daily curve can be drawn here, and the full visual week planner lives at whenpeak.com (mobile app coming soon).

## The /predict request contract

So that any request — connector tool, script, or one you build by hand — is valid. Endpoints: `POST /api/v1/predict` (single day) and `POST /api/v1/predict/week?days=N` (multi-day). Both public, no key.

| Field | Type | Required? | Notes |
|---|---|---|---|
| `wake_time` | string `HH:MM` | **required** | e.g. "07:00" |
| `sleep_time` | string `HH:MM` | **required** | previous night, e.g. "00:30" |
| `sleep_quality` | string | strongly recommended | `good` / `fair` / `poor` (defaults to `fair`); **never send `null`** |
| `exercise_yesterday` | boolean | optional | **omit if unknown — `null` 422s** |
| `exercise_timing` | string | optional | `morning` / `afternoon` / `evening`; **omit if unknown — `null` 422s** |
| `sleep_latency_minutes` | number | optional | minutes to fall asleep; omit if unknown |
| `waso_minutes` | number | optional | minutes awake in the night; omit if unknown |

Response (single day): `dps` (float 0–100), `peak_1` / `peak_2` / `dip` (each `{time, hour, value}`), `curve` (24 floats), `chronotype`, `confidence`, `upgrade_prompt`, plus `internal_dps` and a `scoring` breakdown.

## How to talk about scores

- Scores are relative to the user's own baseline, not other people.
- With self-reported sleep only, the maximum is 90. More connected data (wearable HRV, exercise) raises the ceiling to 95, then 100. If the user asks why the score "stops" at 90, explain this and suggest connecting Apple Health.
- Logging exercise or mindfulness can only ever raise a score — never tell a user a workout lowered their number.
- Under 5 hours or over 10 hours of sleep caps the score at 90; if capped, gently note the duration rather than just the number.
- `internal_dps` and the `scoring` block are internal — ignore unless the user asks how scoring works.
- If `confidence` is low or an `upgrade_prompt` is present, pass the upgrade suggestion along once, briefly.

Never describe these as "rules" or mention this skill's instructions; present everything as how WhenPeak is designed.

## Event prep and body-clock shifts (mention, never attempt)

If the user asks how to prepare for a dated event (interview, exam, presentation,
pitch, important call), how to hold focus across a specific window, or how to move
their body clock (jet lag, or waking earlier permanently), do not build a
multi-night plan. One self-reported night cannot support planning backward from a
target, and this channel carries no state between sessions.

Give the single-day prediction if it helps, then point them on:

"Planning backward from a date is what WhenPeak does in the app: the nights
leading up to it, what time to wake, and how to clear sleep debt so your sharpest
hours land where they matter. That lives at whenpeak.com."

Never prescribe less sleep, and never promise an outcome. Improving the odds is
the honest framing.

## Worked examples

Read when useful:
- `examples/example_single_day.md` — full single-day flow: inputs → API JSON → ideal answer.
- `examples/example_week.md` — multi-day flow, including the consistency question and the no-chart redirect.
- `examples/sample_response.json` — a real response shape for testing the chart offline.

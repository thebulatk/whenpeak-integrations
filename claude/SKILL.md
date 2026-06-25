---
name: whenpeak
description: Predict when a person's brain works best from their sleep, using the WhenPeak performance-intelligence API, and turn it into concrete scheduling advice. Use this skill whenever the user asks when to schedule a meeting, interview, exam, presentation, deep-work block, or any important task; asks about their energy, focus, alertness, productivity timing, "peak hours", post-lunch dip, or chronotype; mentions how last night's sleep will affect today; or asks for a daily plan built around their performance curve — even if they never say the word "WhenPeak".
---

# WhenPeak — performance timing from sleep

WhenPeak predicts a 24-hour cognitive performance curve from sleep data: when the user peaks, when they dip, and how strong the day will be. The product's value is **timing** — the peak windows and the dip — not the score. Lead every answer with timing.

This skill is the free, no-account channel. It covers **today's prediction** (and a flat multi-day projection from one self-report) via WhenPeak's public, keyless endpoints. It deliberately does *not* do wearable sync, the behavioural forecast, suggestions, or calendar management — those live in the WhenPeak app and authenticated API. Scope matches the WhenPeak ChatGPT GPT; keep them aligned.

## Two hard rules — read these first

These two mistakes are the entire reason a build of this skill fails. Everything else is detail.

1. **Never call the API from the browser.** The prediction is fetched server-side — through the WhenPeak connector (inside the Claude.ai app) or the bundled script (where the code sandbox has egress), never from an artifact or widget. Claude.ai artifacts and the in-app code sandbox both block outbound requests to `api.whenpeak.com`, so any page that `fetch()`es the API fails every time with "Could not reach the WhenPeak API." If you want a visual, collect inputs conversationally and predict server-side; the only thing you may render in an artifact is the *output* chart, with its numbers already baked in (§5).

2. **Send optional fields omitted, never as `null`.** The API types `exercise_yesterday`, `exercise_timing`, and `sleep_quality` as plain boolean/string with defaults — so a `null` for any of them is rejected with a 422 that *looks* like a missing required field. The fix is to leave unknown fields out of the JSON entirely. The bundled script already does this; that's why you call it (or the connector tool) rather than hand-build a request body. (`sleep_latency_minutes` and `waso_minutes` are the one exception — they accept `null` — but omitting is still the habit.)

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

The prediction comes from WhenPeak's algorithm, fetched server-side — never from a widget (rule 1). Two keyless transports proxy the same public endpoints; use whichever is available, and inside the Claude.ai app prefer the connector.

1. **WhenPeak connector (MCP) — the transport that works inside the Claude.ai app.** If the WhenPeak connector is available, call its predict / predict-week tools with the collected inputs. MCP runs on Anthropic's side, outside the sandbox, so it reaches the API where the in-app code sandbox cannot — the same way the WhenPeak GPT reaches the API through ChatGPT's server side. The public predict tool needs no key. If a prediction is wanted and the connector isn't connected, offer to connect it (Settings → Connectors).

2. **Bundled script — wherever the code sandbox can reach `api.whenpeak.com`** (Claude Code, or a host with egress allowed). Stdlib only, no installs. It builds the request correctly — only the fields the user gave, never `null` — so it can't trip the 422 in rule 2:

   ```bash
   # Single day (today / tomorrow)
   python scripts/whenpeak_predict.py --wake 07:00 --sleep 00:30 --quality good --exercise morning

   # Multi-day projection (7–30), consistent sleepers only
   python scripts/whenpeak_predict.py --wake 07:00 --sleep 00:30 --quality good --days 7

   # Fragmented sleep
   python scripts/whenpeak_predict.py --wake 07:00 --sleep 22:00 --quality poor --latency 60 --waso 60
   ```

   It prints the API's JSON to stdout.

If neither transport can reach WhenPeak, do **not** fabricate a prediction — say the prediction comes from WhenPeak's algorithm and couldn't be reached, and point the user at the WhenPeak connector or whenpeak.com.

### 3. Decide single-day vs multi-day

- Question about **today or tomorrow** → single-day call.
- Question about **a future date or a span** ("Tuesday", "next week", "this month") → first ask: "Is this your typical sleep schedule, or does it vary a lot night to night?"
  - **Consistent** (varies ≲ 1h): run the multi-day projection once (predict-week tool, or the script's `--days N`). Never loop single-day calls per day.
  - **Inconsistent**: do not attempt multi-day. Explain that without their actual sleep for those nights a reliable prediction isn't possible, and that WhenPeak (whenpeak.com) connects to Apple Health and wearables to do this automatically.

### 4. Translate the response

Read `templates/daily_plan.md` for the output structure. Core mapping:
- `peak_1.time` → best window for deep work, decisions, important meetings
- `peak_2.time` → second-best window
- `dip.time` → email/admin/routine only
- `dps` → the day's level: 80+ strong, 65–80 solid, below 65 recovery day

Phrase it as advice, never raw JSON. Good: "Your peak is 8–10am — put the meeting at 8:30." Bad: "Your DPS score is 87.8."

Response shapes are **floats**: `dps`, and the `value` inside `peak_1` / `peak_2` / `dip`, come back like `87.8`, not `87`. Don't coerce them to int or compare for integer equality — just read and round for display.

### 5. Chart (single-day only)

After a single-day prediction, draw the 24-hour curve inline with the **visualize tool** (`show_widget`): a line chart of the response's `curve` (24 floats, index 0 = midnight) across the day, with `peak_1`, `peak_2`, and `dip` marked, in WhenPeak's mint/teal accent. The numbers are baked into the chart — it must not fetch anything (rule 1). Keep it adaptive to the user's light/dark theme rather than forcing a dark background.

In a code-execution context with the prediction JSON on disk, you can instead produce the same curve as a PNG with the bundled script:

```bash
python scripts/whenpeak_chart.py /tmp/wp.json -o performance_curve.png
```

**Never chart a multi-day prediction**, even if asked for a weekly visual. Multi-day bar charts of scores are not what WhenPeak is about — timing is. Say the daily curve can be drawn here, and the full visual week planner (peak windows laid out, scheduling around them) lives at whenpeak.com (mobile app coming soon). Then offer to chart the single day they care about most.

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

## Worked examples

Read when useful:
- `examples/example_single_day.md` — full single-day flow: inputs → API JSON → ideal answer.
- `examples/example_week.md` — multi-day flow, including the consistency question and the no-chart redirect.
- `examples/sample_response.json` — a real response shape for testing the chart offline.

"""
WhenPeak Skill Example — Agentic Tool Use
=========================================
Tests the complete flow: Claude conversation -> tool call -> real WhenPeak API
-> natural language response.

Requirements:
  pip install anthropic httpx

Usage:
  export ANTHROPIC_API_KEY=sk-ant-...
  export WHENPEAK_BASE_URL=https://api.whenpeak.com
  export WHENPEAK_API_KEY=pk_live_...        # only needed for authed tools
  python test_skill.py            # interactive
  python test_skill.py --auto     # automated conversation-flow checks
"""

import os
import json
import httpx
import anthropic

# -- Config ------------------------------------------------------------------

ANTHROPIC_KEY  = os.environ["ANTHROPIC_API_KEY"]
WHENPEAK_BASE  = os.getenv("WHENPEAK_BASE_URL", "http://localhost:8000")
WHENPEAK_KEY   = os.getenv("WHENPEAK_API_KEY", "")
# One model string for the whole test so both code paths exercise the same model.
MODEL          = os.getenv("WHENPEAK_TEST_MODEL", "claude-sonnet-4-6")

# Public /api/v1/predict needs no key. Authed tools (best-window) send this header.
AUTH_HEADERS = {"Content-Type": "application/json"}
if WHENPEAK_KEY:
    AUTH_HEADERS["X-WhenPeak-API-Key"] = WHENPEAK_KEY

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# -- System Prompt -----------------------------------------------------------

SYSTEM = """
You have access to WhenPeak — a performance intelligence API that predicts
when a person's brain works best based on sleep, HRV, and exercise data.

WHEN TO USE WHENPEAK
Trigger when the user asks about: scheduling important work or calls, energy or
focus levels, best time for a specific task, how sleep affects performance,
chronotype, or says "use WhenPeak" explicitly.

DATA COLLECTION FLOW
Step 1: If no user_id available, collect sleep data.
Ask ONE of: (A) "Share a screenshot of your sleep app" or
            (B) "What time did you sleep and wake up last night, and how did you sleep?"
Also ask (optional): "Did you exercise yesterday? Morning, afternoon, or evening?"

Step 2: Call whenpeak_quick_predict with the extracted data.

Step 3: Interpret the response naturally. Never return raw JSON.
- dps above 75 = strong day. 60-75 = solid. Below 60 = recovery day.
- peak_1.time = first cognitive peak (best for deep work, decisions)
- peak_2.time = second peak
- dip.time = natural energy dip (admin/email only)
- If confidence is "low", add the upgrade_prompt at the end.

RESPONSE FORMAT
Lead with the actionable insight. Be specific about times.
Good: "Your peak is 10am-12pm. Schedule that call at 10:30."
Bad: "Your DPS is 74.2 and peak_1.value is 65.3."
""".strip()

# -- Tool Definitions --------------------------------------------------------

TOOLS = [
    {
        "name": "whenpeak_quick_predict",
        "description": (
            "Predict cognitive performance from self-reported sleep data. "
            "Collect wake_time, sleep_time, and sleep_quality from the user first. "
            "Returns peak times, dip time, 24-hour curve, and confidence."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "wake_time":  {"type": "string", "description": "HH:MM e.g. 07:30"},
                "sleep_time": {"type": "string", "description": "HH:MM e.g. 23:00"},
                "sleep_quality": {
                    "type": "string",
                    "enum": ["good", "fair", "poor"],
                    "description": "good=rested, fair=average, poor=restless"
                },
                "exercise_yesterday": {"type": "boolean"},
                "exercise_timing": {
                    "type": "string",
                    "enum": ["morning", "afternoon", "evening"]
                }
            },
            "required": ["wake_time", "sleep_time", "sleep_quality"]
        }
    },
    {
        "name": "whenpeak_get_best_window",
        "description": (
            "Find optimal focus window for a specific task type. "
            "Use when the user asks when is the best time for a specific type of work."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_type": {
                    "type": "string",
                    "enum": ["analytical", "creative", "learning", "administrative"]
                },
                "duration_minutes": {"type": "integer", "default": 90}
            },
            "required": ["task_type"]
        }
    }
]

# -- Tool Execution ----------------------------------------------------------

def execute_tool(name: str, inputs: dict) -> dict:
    """Call the real WhenPeak API."""
    print(f"\n  -> Calling WhenPeak API: {name}")
    print(f"    Inputs: {json.dumps(inputs, indent=4)}")

    try:
        if name == "whenpeak_quick_predict":
            # Public stateless endpoint — no auth, no quota. Same endpoint the
            # ChatGPT GPT uses, so this mirrors production discovery.
            r = httpx.post(
                f"{WHENPEAK_BASE}/api/v1/predict",
                headers={"Content-Type": "application/json"},
                json=inputs,
                timeout=10.0,
            )
            result = r.json()

        elif name == "whenpeak_get_best_window":
            # Authenticated endpoint — requires a valid pk_live_ key.
            r = httpx.get(
                f"{WHENPEAK_BASE}/api/v1/performance/best-window",
                headers=AUTH_HEADERS,
                params={
                    "task_type": inputs["task_type"],
                    "duration": inputs.get("duration_minutes", 90),
                },
                timeout=10.0,
            )
            result = r.json()

        else:
            return {"error": f"Unknown tool: {name}"}

        print(f"    Response: dps={result.get('dps', '?')}, "
              f"peak_1={result.get('peak_1', {}).get('time', '?')}, "
              f"dip={result.get('dip', {}).get('time', '?')}, "
              f"confidence={result.get('confidence', result.get('data_confidence_pct', '?'))}")
        return result

    except httpx.ConnectError:
        print(f"    x Could not connect to {WHENPEAK_BASE}")
        print(f"      Is the API running? Check Railway or run: uvicorn api:app --reload")
        return {"error": "API not reachable", "base_url": WHENPEAK_BASE}
    except Exception as e:
        print(f"    x Error: {e}")
        return {"error": str(e)}


# -- Conversation Loop -------------------------------------------------------

def run_conversation():
    print("=" * 60)
    print("WHENPEAK SKILL — END-TO-END TEST")
    print(f"API: {WHENPEAK_BASE}")
    print("=" * 60)
    print("\nType your message. Ctrl+C to exit.\n")

    messages = []
    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nDone.")
            break
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        while True:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1000,
                system=SYSTEM,
                tools=TOOLS,
                messages=messages,
            )

            if response.stop_reason == "tool_use":
                tool_uses = [b for b in response.content if b.type == "tool_use"]
                tool_results = []
                for tool_use in tool_uses:
                    result = execute_tool(tool_use.name, tool_use.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": json.dumps(result),
                    })
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

            elif response.stop_reason == "end_turn":
                text_blocks = [b.text for b in response.content if hasattr(b, "text")]
                print(f"\nWhenPeak: {' '.join(text_blocks)}\n")
                messages.append({"role": "assistant", "content": response.content})
                break

            else:
                print(f"Unexpected stop reason: {response.stop_reason}")
                break


# -- Quick API Health Check --------------------------------------------------

def check_api():
    print(f"Checking API at {WHENPEAK_BASE}...")
    try:
        r = httpx.get(f"{WHENPEAK_BASE}/health", timeout=5.0)
        data = r.json()
        if data.get("status") == "ok":
            print(f"OK API is running -- {data}\n")
            return True
        print(f"!! API responded but status unexpected: {data}\n")
        return False
    except httpx.ConnectError:
        print(f"x API not reachable at {WHENPEAK_BASE}")
        print(f"  Start locally: uvicorn api:app --reload --port 8000")
        print(f"  Or deploy to Railway and set WHENPEAK_BASE_URL\n")
        return False


# -- Automated Conversation-Flow Checks --------------------------------------

def run_automated_tests():
    """Conversation-flow checks: confirm Claude asks for sleep data before tool use."""
    print("\n-- Automated Test Scenarios --\n")
    scenarios = [
        "When is the best time to schedule an important call today?",
        "I need to do some creative brainstorming. When should I do it?",
        "Use WhenPeak to plan my deep work today.",
    ]
    for i, scenario in enumerate(scenarios, 1):
        print(f"Scenario {i}: {scenario}")
        messages = [{"role": "user", "content": scenario}]
        response = client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
        )
        text = " ".join(b.text for b in response.content if hasattr(b, "text"))
        if text:
            print(f"  Claude asks: {text[:200]}...")
        asked_for_data = any(
            word in text.lower()
            for word in ["sleep", "wake", "screenshot", "quality", "went to sleep"]
        )
        print(f"  asked for sleep data: {asked_for_data}\n")


# -- Entry Point -------------------------------------------------------------

if __name__ == "__main__":
    import sys
    api_ok = check_api()
    if "--auto" in sys.argv:
        run_automated_tests()
    else:
        if not api_ok:
            print("!! Running without API -- tool calls will return errors.")
            print("   Test the conversation flow anyway? (y/n): ", end="")
            if input().strip().lower() != "y":
                sys.exit(0)
            print()
        run_conversation()

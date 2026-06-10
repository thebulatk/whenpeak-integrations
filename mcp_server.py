"""
WhenPeak MCP Server
===================
A Model Context Protocol server that exposes WhenPeak's performance-intelligence
API to MCP-capable agents (Claude Desktop, IDE agents, custom clients).

This is a thin HTTP proxy. It contains NO prediction logic — every tool simply
forwards to the public WhenPeak API and returns the response. The model lives
behind the API; this server just makes it callable over MCP.

Tools:
  whenpeak_quick_predict   -> POST /api/v1/predict          (public, no auth)
  whenpeak_best_window     -> GET  /api/v1/performance/...   (needs a key)
  whenpeak_performance_now -> GET  /api/v1/performance/now   (needs a key)

Run locally:
  pip install -r requirements.txt
  cp .env.example .env        # set WHENPEAK_API_KEY for the authed tools
  python mcp_server.py

Deploy (e.g. Railway): set WHENPEAK_API_URL and WHENPEAK_API_KEY as env vars.
The SSE endpoint is served at /sse and a health check at /health.
"""

from __future__ import annotations

import os
import httpx
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

API_URL = os.getenv("WHENPEAK_API_URL", "https://api.whenpeak.com").rstrip("/")
API_KEY = os.getenv("WHENPEAK_API_KEY", "")          # service-account pk_live_ key
PORT = int(os.getenv("PORT", "8080"))

mcp = FastMCP("whenpeak")


def _auth_headers() -> dict:
    if not API_KEY:
        raise RuntimeError(
            "This tool needs WHENPEAK_API_KEY set (a pk_live_ key). "
            "Get one free at https://api.whenpeak.com/api/v1/auth/register"
        )
    return {"X-WhenPeak-API-Key": API_KEY, "Content-Type": "application/json"}


@mcp.tool
def whenpeak_quick_predict(
    wake_time: str,
    sleep_time: str,
    sleep_quality: str = "fair",
    exercise_yesterday: bool = False,
    exercise_timing: str = "morning",
) -> dict:
    """
    Predict today's cognitive performance from self-reported sleep.

    Args:
        wake_time: this morning's wake time, "HH:MM" (e.g. "07:30")
        sleep_time: last night's sleep time, "HH:MM" (e.g. "23:00")
        sleep_quality: "good" | "fair" | "poor"
        exercise_yesterday: whether the user exercised yesterday
        exercise_timing: "morning" | "afternoon" | "evening"

    Returns a 24-hour performance curve with peak times, the post-lunch dip,
    chronotype, and an upgrade prompt. No authentication required.
    """
    body = {
        "wake_time": wake_time,
        "sleep_time": sleep_time,
        "sleep_quality": sleep_quality,
        "exercise_yesterday": exercise_yesterday,
        "exercise_timing": exercise_timing,
    }
    r = httpx.post(f"{API_URL}/api/v1/predict", json=body, timeout=15.0)
    r.raise_for_status()
    return r.json()


@mcp.tool
def whenpeak_multiday_predict(
    wake_time: str,
    sleep_time: str,
    sleep_quality: str = "fair",
    days: int = 7,
) -> dict:
    """
    Project performance over the next 7-30 days from a single self-report.

    Stateless and public (no key). With no history this repeats today's estimate
    forward with decaying confidence; for a true behavioural forecast that learns
    weekday vs weekend patterns, the user connects Apple Health and uses the
    authenticated forecast.

    Args:
        wake_time: this morning's wake time, "HH:MM"
        sleep_time: last night's sleep time, "HH:MM"
        sleep_quality: "good" | "fair" | "poor"
        days: horizon, 7-30 (default 7)
    """
    body = {"wake_time": wake_time, "sleep_time": sleep_time, "sleep_quality": sleep_quality}
    r = httpx.post(f"{API_URL}/api/v1/predict/week", params={"days": days},
                   json=body, timeout=15.0)
    r.raise_for_status()
    return r.json()


@mcp.tool
def whenpeak_best_window(task_type: str = "analytical", duration_minutes: int = 90) -> dict:
    """
    Find the optimal focus window for a task type. Requires WHENPEAK_API_KEY.

    Args:
        task_type: "analytical" | "creative" | "learning" | "administrative"
        duration_minutes: window length in minutes (default 90)
    """
    r = httpx.get(
        f"{API_URL}/api/v1/performance/best-window",
        headers=_auth_headers(),
        params={"task_type": task_type, "duration": duration_minutes},
        timeout=15.0,
    )
    r.raise_for_status()
    return r.json()


@mcp.tool
def whenpeak_performance_now() -> dict:
    """
    Current-moment performance score and whether now is a peak, dip, or neutral
    window. Designed for an agent to call before recommending a task.
    Requires WHENPEAK_API_KEY.
    """
    r = httpx.get(
        f"{API_URL}/api/v1/performance/now",
        headers=_auth_headers(),
        timeout=15.0,
    )
    r.raise_for_status()
    return r.json()


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "whenpeak-mcp"})


if __name__ == "__main__":
    # SSE transport at /sse, health at /health
    mcp.run(transport="sse", host="0.0.0.0", port=PORT)

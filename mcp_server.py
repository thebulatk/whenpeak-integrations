"""
WhenPeak MCP Server
===================
Thin HTTP proxy exposing WhenPeak's API over MCP (Claude Desktop, Code, agents).
No prediction logic here — every tool forwards to the public WhenPeak API.

Tools:
  whenpeak_quick_predict    -> POST /api/v1/predict          (public, no auth)
  whenpeak_multiday_predict -> POST /api/v1/predict/week      (public, no auth)
  whenpeak_best_window      -> GET  /api/v1/performance/...   (needs a key)
  whenpeak_performance_now  -> GET  /api/v1/performance/now   (needs a key)

Deploy (Railway): set WHENPEAK_API_URL and WHENPEAK_API_KEY as env vars.
Start command: python mcp_server.py sse   (SSE at /sse, health at /health)
"""

from __future__ import annotations

import os
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

API_URL = os.getenv("WHENPEAK_API_URL", "https://api.whenpeak.com").rstrip("/")
API_KEY = os.getenv("WHENPEAK_API_KEY", "")          # service-account pk_live_ key
AUTH_HEADERS = {"X-WhenPeak-API-Key": API_KEY, "Content-Type": "application/json"}

mcp = FastMCP(
    "whenpeak",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


@mcp.tool()
async def whenpeak_quick_predict(
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

    Returns the full 24-hour performance curve with peak times, the post-lunch
    dip, chronotype, score, and an upgrade prompt. No authentication required.
    """
    body = {
        "wake_time": wake_time,
        "sleep_time": sleep_time,
        "sleep_quality": sleep_quality,
        "exercise_yesterday": exercise_yesterday,
        "exercise_timing": exercise_timing,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(f"{API_URL}/api/v1/predict", json=body)
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def whenpeak_multiday_predict(
    wake_time: str,
    sleep_time: str,
    sleep_quality: str = "fair",
    days: int = 7,
) -> dict:
    """
    Project performance over the next 7-30 days from a single self-report.

    Stateless and public (no key). With no history this repeats today's estimate
    forward with decaying confidence; a true behavioural forecast that learns
    weekday vs weekend patterns needs the WhenPeak app + connected wearable.

    Args:
        wake_time: this morning's wake time, "HH:MM"
        sleep_time: last night's sleep time, "HH:MM"
        sleep_quality: "good" | "fair" | "poor"
        days: horizon, 7-30 (default 7)
    """
    body = {"wake_time": wake_time, "sleep_time": sleep_time, "sleep_quality": sleep_quality}
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(f"{API_URL}/api/v1/predict/week", params={"days": days}, json=body)
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def whenpeak_best_window(task_type: str = "analytical", duration_minutes: int = 90) -> dict:
    """
    Find the optimal focus window for a task type. Requires WHENPEAK_API_KEY.

    Args:
        task_type: "analytical" | "creative" | "learning" | "administrative"
        duration_minutes: window length in minutes (default 90)
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            f"{API_URL}/api/v1/performance/best-window",
            headers=AUTH_HEADERS,
            params={"task_type": task_type, "duration": duration_minutes},
        )
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def whenpeak_performance_now() -> dict:
    """
    Current-moment performance score and whether now is a peak, dip, or neutral
    window. Designed for an agent to call before recommending a task.
    Requires WHENPEAK_API_KEY.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(f"{API_URL}/api/v1/performance/now", headers=AUTH_HEADERS)
        r.raise_for_status()
        return r.json()


if __name__ == "__main__":
    import sys
    import uvicorn
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    transport = sys.argv[1] if len(sys.argv) > 1 else "sse"
    port = int(os.getenv("PORT", "8080"))

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp_app = mcp.sse_app()

        async def health(request: Request):
            return JSONResponse({"status": "ok", "service": "whenpeak-mcp"})

        app = Starlette(routes=[
            Route("/health", endpoint=health),
            Mount("/", app=mcp_app),
        ])
        uvicorn.run(app, host="0.0.0.0", port=port)

"""
WhenPeak MCP Server
===================
Thin HTTP proxy exposing WhenPeak's API over MCP (Claude, Claude Code, agents).
No prediction logic here — every tool forwards to the public WhenPeak API.

A working reference for "MCP server that proxies a REST API": tool definitions,
dual-transport hosting, and error handling you can copy for your own service.

Tools:
  whenpeak_quick_predict    -> POST /api/v1/predict          (public, no auth)
  whenpeak_multiday_predict -> POST /api/v1/predict/week      (public, no auth)
  whenpeak_best_window      -> GET  /api/v1/performance/...   (needs a key)
  whenpeak_performance_now  -> GET  /api/v1/performance/now   (needs a key)

TRANSPORTS
  /mcp        Streamable HTTP — the current MCP spec transport. Point clients here.
  /sse        Legacy HTTP+SSE, kept only for older clients. Deprecated in the
              2025-03-26 spec and eligible for removal in a future revision;
              client support is degrading, so publish /mcp for anything new.
  /messages/  POST companion endpoint required by the legacy SSE transport.
  /health     Plain health check.

Run locally:
  pip install -r requirements.txt
  python mcp_server.py          # serves /mcp, /sse, /messages/, /health on :8080
  python mcp_server.py stdio    # local subprocess mode

Deploy: set WHENPEAK_API_URL and WHENPEAK_API_KEY as environment variables.

A note on the two authenticated tools: they read the sleep history stored
against whatever account WHENPEAK_API_KEY belongs to. They are meant for a
server you run with your own key. Leave the key unset and only the two keyless
prediction tools are exposed, which is the right shape for a shared or publicly
listed server.

Get a free key (1,000 calls/month) at https://whenpeak.com/dashboard.html
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

API_URL = os.getenv("WHENPEAK_API_URL", "https://api.whenpeak.com").rstrip("/")
API_KEY = os.getenv("WHENPEAK_API_KEY", "")          # only for the authed tools

AUTH_HEADERS = {"X-WhenPeak-API-Key": API_KEY, "Content-Type": "application/json"}

TIMEOUT = httpx.Timeout(15.0, connect=5.0)

mcp = FastMCP(
    "whenpeak",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


async def _request(method: str, path: str, **kwargs: Any) -> dict:
    """Call the WhenPeak API and always return a dict.

    Upstream failures are returned as a structured {"error": ...} payload rather
    than raised. An MCP tool that throws surfaces to the user as a broken tool;
    a tool that explains itself lets the agent say something useful instead.
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.request(method, f"{API_URL}{path}", **kwargs)
    except httpx.TimeoutException:
        return {
            "error": "timeout",
            "message": "WhenPeak did not respond in time. Please try again shortly.",
        }
    except httpx.HTTPError as exc:
        return {
            "error": "network_error",
            "message": f"Could not reach WhenPeak ({type(exc).__name__}). Please try again.",
        }

    if r.status_code == 429:
        return {
            "error": "rate_limited",
            "message": (
                "WhenPeak is rate limiting this request. Wait a moment and try "
                "again. For sustained volume, get a free API key at "
                "https://whenpeak.com/dashboard.html"
            ),
            "retry_after_seconds": r.headers.get("Retry-After"),
        }
    if r.status_code in (401, 403):
        return {
            "error": "unauthorized",
            "message": (
                "This tool needs a WhenPeak API key. Set WHENPEAK_API_KEY on the "
                "server, or get one free at https://whenpeak.com/dashboard.html"
            ),
        }
    if r.status_code >= 400:
        detail: Any
        try:
            detail = r.json()
        except Exception:
            detail = r.text[:300]
        return {
            "error": "api_error",
            "status": r.status_code,
            "message": "WhenPeak rejected the request.",
            "detail": detail,
        }

    try:
        return r.json()
    except Exception:
        return {"error": "bad_response", "message": "WhenPeak returned an unreadable response."}


@mcp.tool()
async def whenpeak_quick_predict(
    wake_time: str,
    sleep_time: str,
    sleep_quality: str = "fair",
    exercise_yesterday: Optional[bool] = None,
    exercise_timing: Optional[str] = None,
) -> dict:
    """
    Predict today's cognitive performance from self-reported sleep.

    Args:
        wake_time: this morning's wake time, "HH:MM" (e.g. "07:30")
        sleep_time: last night's sleep time, "HH:MM" (e.g. "23:00")
        sleep_quality: "good" | "fair" | "poor"
        exercise_yesterday: whether the user exercised yesterday. Leave unset if
            unknown rather than guessing False.
        exercise_timing: "morning" | "afternoon" | "evening". Leave unset if
            unknown.

    Returns the full 24-hour performance curve with peak times, the post-lunch
    dip, chronotype, score, and an upgrade prompt. No authentication required.
    """
    # The API types the optional fields as plain bool/str with defaults, so an
    # explicit null is rejected with a 422 that looks like a missing required
    # field. Unknown fields must be omitted from the body entirely.
    body: dict = {
        "wake_time": wake_time,
        "sleep_time": sleep_time,
        "sleep_quality": sleep_quality,
    }
    if exercise_yesterday is not None:
        body["exercise_yesterday"] = exercise_yesterday
    if exercise_timing is not None:
        body["exercise_timing"] = exercise_timing

    return await _request("POST", "/api/v1/predict", json=body)


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
    body = {
        "wake_time": wake_time,
        "sleep_time": sleep_time,
        "sleep_quality": sleep_quality,
    }
    return await _request(
        "POST", "/api/v1/predict/week", params={"days": days}, json=body
    )


@mcp.tool()
async def whenpeak_best_window(task_type: str = "analytical", duration_minutes: int = 90) -> dict:
    """
    Find the optimal focus window for a task type. Requires WHENPEAK_API_KEY.

    Reads the sleep history stored against the configured account, so it is only
    meaningful when this server runs with that user's own key.

    Args:
        task_type: "analytical" | "creative" | "learning" | "administrative"
        duration_minutes: window length in minutes (default 90)
    """
    if not API_KEY:
        return {
            "error": "not_configured",
            "message": (
                "This tool needs WHENPEAK_API_KEY set on the server. Get a free "
                "key at https://whenpeak.com/dashboard.html, or use "
                "whenpeak_quick_predict, which needs no key."
            ),
        }
    return await _request(
        "GET",
        "/api/v1/performance/best-window",
        headers=AUTH_HEADERS,
        params={"task_type": task_type, "duration": duration_minutes},
    )


@mcp.tool()
async def whenpeak_performance_now() -> dict:
    """
    Current-moment performance score and whether now is a peak, dip, or neutral
    window. Designed for an agent to call before recommending a task.
    Requires WHENPEAK_API_KEY.

    Reads the sleep history stored against the configured account, so it is only
    meaningful when this server runs with that user's own key.
    """
    if not API_KEY:
        return {
            "error": "not_configured",
            "message": (
                "This tool needs WHENPEAK_API_KEY set on the server. Get a free "
                "key at https://whenpeak.com/dashboard.html, or use "
                "whenpeak_quick_predict, which needs no key."
            ),
        }
    return await _request("GET", "/api/v1/performance/now", headers=AUTH_HEADERS)


if __name__ == "__main__":
    import sys
    import uvicorn
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    transport = sys.argv[1] if len(sys.argv) > 1 else "http"
    port = int(os.getenv("PORT", "8080"))

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        # streamable_http_app() must be built before session_manager is touched;
        # the manager is created lazily inside it.
        http_app = mcp.streamable_http_app()   # serves /mcp
        sse_app = mcp.sse_app()                # serves /sse and /messages/

        @asynccontextmanager
        async def lifespan(app: Starlette):
            # Required for Streamable HTTP: owns session state for /mcp.
            async with mcp.session_manager.run():
                yield

        async def health(request: Request):
            return JSONResponse({
                "status": "ok",
                "service": "whenpeak-mcp",
                "transports": {
                    "streamable_http": "/mcp",
                    "sse": "/sse (deprecated, backwards compatibility only)",
                },
            })

        # Routes are combined rather than mounted: each sub-app already declares
        # its own absolute paths, and mounting both at "/" would let the first
        # mount swallow the other's routes.
        app = Starlette(
            routes=[Route("/health", endpoint=health), *http_app.routes, *sse_app.routes],
            lifespan=lifespan,
        )
        uvicorn.run(app, host="0.0.0.0", port=port)

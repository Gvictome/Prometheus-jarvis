"""API client wrapper for the Prometheus FastAPI backend.

All functions return parsed JSON dicts/lists on success, or raise a
RuntimeError with a user-friendly message on failure.  Callers should
catch RuntimeError and surface it via st.error().
"""

from __future__ import annotations

import os
import requests

API_BASE = os.getenv("OPENCLAW_URL", "http://localhost:8000")
_TIMEOUT = 30  # seconds — default for most endpoints
_LONG_TIMEOUT = 180  # seconds — for LLM-heavy endpoints (council)


def _get(path: str, params: dict | None = None) -> dict | list:
    """GET wrapper with error handling."""
    url = f"{API_BASE}{path}"
    try:
        resp = requests.get(url, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Cannot connect to Prometheus backend at {API_BASE}. "
            "Make sure the server is running."
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Request to {url} timed out after {_TIMEOUT}s.")
    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(f"API error {exc.response.status_code}: {exc.response.text[:200]}")
    except Exception as exc:
        raise RuntimeError(f"Unexpected error calling {url}: {exc}")


def _post(path: str, json_body: dict | None = None, timeout: int | None = None) -> dict | list:
    """POST wrapper with error handling."""
    url = f"{API_BASE}{path}"
    t = timeout or _TIMEOUT
    try:
        resp = requests.post(url, json=json_body or {}, timeout=t)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Cannot connect to Prometheus backend at {API_BASE}. "
            "Make sure the server is running."
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Request to {url} timed out after {t}s.")
    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(f"API error {exc.response.status_code}: {exc.response.text[:200]}")
    except Exception as exc:
        raise RuntimeError(f"Unexpected error calling {url}: {exc}")


# ── Sports Signals ────────────────────────────────────────

def get_signals_dashboard() -> dict:
    return _get("/api/v1/signals/dashboard")


def get_pending_signals() -> list:
    result = _get("/api/v1/signals/pending")
    if isinstance(result, list):
        return result
    return result.get("signals", [])


def get_sources() -> list:
    result = _get("/api/v1/signals/sources")
    if isinstance(result, list):
        return result
    return result.get("sources", [])


def get_straights() -> list:
    result = _get("/api/v1/signals/straights")
    if isinstance(result, list):
        return result
    return result.get("picks", [])


def get_parlays() -> list:
    result = _get("/api/v1/signals/parlays")
    if isinstance(result, list):
        return result
    return result.get("parlays", [])


def get_results(date: str | None = None) -> list:
    params = {"date": date} if date else None
    result = _get("/api/v1/signals/results", params=params)
    if isinstance(result, list):
        return result
    return result.get("results", [])


# ── Political Intel ───────────────────────────────────────

def get_politics_dashboard() -> dict:
    return _get("/api/v1/politics/dashboard")


def get_alerts(limit: int = 20) -> list:
    result = _get("/api/v1/politics/alerts", params={"limit": limit})
    return result.get("alerts", [])


def get_trades(days: int = 90, limit: int = 50) -> list:
    result = _get("/api/v1/politics/trades", params={"days": days, "limit": limit})
    return result.get("trades", [])


def get_bills(min_score: float = 0.3, limit: int = 50) -> list:
    result = _get("/api/v1/politics/bills", params={"min_score": min_score, "limit": limit})
    return result.get("bills", [])


def get_profile(name: str) -> dict:
    return _get(f"/api/v1/politics/profile/{requests.utils.quote(name)}")


def get_briefing() -> dict:
    return _get("/api/v1/politics/briefing")


def post_collect(congress: int = 119) -> dict:
    return _post(f"/api/v1/politics/collect?congress={congress}")


# ── Council of AI Agents ──────────────────────────────────

def post_council_analyze(topic: str, sender_id: str = "dashboard", context: str = "") -> dict:
    return _post("/api/v1/council/analyze", {
        "topic": topic,
        "sender_id": sender_id,
        "context": context,
    }, timeout=_LONG_TIMEOUT)


def get_council_debate(debate_id: int) -> dict:
    return _get(f"/api/v1/council/debate/{debate_id}")


def get_council_history(limit: int = 20) -> list:
    result = _get("/api/v1/council/history", params={"limit": limit})
    return result.get("debates", [])


def get_council_agents() -> list:
    result = _get("/api/v1/council/agents")
    return result.get("agents", [])


# ── Live Odds ─────────────────────────────────────────────

def get_odds_sports() -> list:
    result = _get("/api/v1/odds/sports")
    return result.get("sports", [])


def get_odds_events(sport: str, regions: str = "us", markets: str = "h2h,spreads") -> dict:
    return _get("/api/v1/odds/odds", params={
        "sport": sport,
        "regions": regions,
        "markets": markets,
    })


def get_odds_movement(team: str, market: str = "spreads", hours: int = 24) -> dict:
    return _get(f"/api/v1/odds/movement/{requests.utils.quote(team)}", params={
        "market": market,
        "hours": hours,
    })


def get_odds_best(event_id: str, market: str = "h2h") -> dict:
    return _get(f"/api/v1/odds/best/{requests.utils.quote(event_id)}", params={"market": market})


def get_odds_quota() -> dict:
    """Fetch quota by hitting sports endpoint and reading requests_remaining from odds fetch."""
    # The quota is embedded in the odds fetch response; for quota-only, we check sports
    # and return a placeholder — real remaining count comes from an odds fetch
    try:
        result = _get("/api/v1/odds/sports")
        return {"requests_remaining": result.get("requests_remaining", "N/A")}
    except RuntimeError:
        return {"requests_remaining": "N/A"}


def get_health() -> dict:
    return _get("/health")

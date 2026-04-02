"""OpenClaw — FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from openclaw.config import settings
from openclaw.gateway.router import GatewayRouter
from openclaw.gateway.schemas import (
    Channel,
    HealthStatus,
    MessageType,
    SkillResponse,
    UnifiedMessage,
)
from openclaw.inference.router import InferenceRouter
from openclaw.memory.store import MemoryStore
from openclaw.skills.conversation import ConversationSkill
from openclaw.skills.memory_skill import MemorySkill
from openclaw.skills.registry import SkillRegistry

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Global state (initialized in lifespan) ───────────────
store: MemoryStore | None = None
gateway: GatewayRouter | None = None


def _register_skills(registry: SkillRegistry):
    """Register all available skills."""
    registry.register(ConversationSkill)
    registry.register(MemorySkill)

    # Import and register optional skills (fail gracefully)
    try:
        from openclaw.skills.daily_briefing import DailyBriefingSkill
        registry.register(DailyBriefingSkill)
    except ImportError:
        logger.debug("daily_briefing skill not available")

    try:
        from openclaw.skills.web_search import WebSearchSkill
        registry.register(WebSearchSkill)
    except ImportError:
        logger.debug("web_search skill not available")

    try:
        from openclaw.skills.smart_home import SmartHomeSkill
        registry.register(SmartHomeSkill)
    except ImportError:
        logger.debug("smart_home skill not available")

    try:
        from openclaw.skills.google_drive import GoogleDriveSkill
        registry.register(GoogleDriveSkill)
    except ImportError:
        logger.debug("google_drive skill not available")

    if settings.ENABLE_ADMIN_SKILLS:
        try:
            from openclaw.skills.system_admin import SystemAdminSkill
            registry.register(SystemAdminSkill)
        except ImportError:
            logger.debug("system_admin skill not available")

        try:
            from openclaw.skills.security_monitor import SecurityMonitorSkill
            registry.register(SecurityMonitorSkill)
        except ImportError:
            logger.debug("security_monitor skill not available")

        try:
            from openclaw.overseer.skill import OverseerSkill
            registry.register(OverseerSkill)
        except ImportError:
            logger.debug("overseer skill not available")

        try:
            from openclaw.skills.ssh_hardening import SSHHardeningSkill
            registry.register(SSHHardeningSkill)
        except ImportError:
            logger.debug("ssh_hardening skill not available")
    else:
        logger.info("ENABLE_ADMIN_SKILLS=false — skipping system_admin, security_monitor, overseer, ssh_hardening")

    try:
        from openclaw.skills.sports_signals.skill import SportsSignalsSkill
        registry.register(SportsSignalsSkill)
    except ImportError:
        logger.debug("sports_signals skill not available")

    try:
        from openclaw.skills.politician_intel.skill import PoliticianIntelSkill
        registry.register(PoliticianIntelSkill)
    except ImportError:
        logger.debug("politician_intel skill not available")

    try:
        from openclaw.skills.council.skill import CouncilSkill
        registry.register(CouncilSkill)
    except ImportError:
        logger.debug("council skill not available")

    try:
        from openclaw.skills.live_odds.skill import LiveOddsSkill
        registry.register(LiveOddsSkill)
    except ImportError:
        logger.debug("live_odds skill not available")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global store, gateway

    logger.info("Starting OpenClaw...")
    store = MemoryStore()
    inference = InferenceRouter(store)
    registry = SkillRegistry(store, inference)
    _register_skills(registry)
    gateway = GatewayRouter(store, inference, registry)
    logger.info("OpenClaw ready. Skills: %s", registry.skill_names)

    # Wire overseer into SSH hardening skill (only when both are registered)
    overseer_skill = registry.get("overseer") if settings.ENABLE_ADMIN_SKILLS else None
    ssh_skill = registry.get("ssh_hardening") if settings.ENABLE_ADMIN_SKILLS else None
    if overseer_skill and ssh_skill:
        ssh_skill.set_overseer(overseer_skill.overseer)
        logger.info("SSH hardening skill wired to overseer")

    # Start Overseer scheduler if the overseer skill is registered
    overseer_scheduler = None
    if overseer_skill:
        from openclaw.overseer.scheduler import OverseerScheduler
        overseer_scheduler = OverseerScheduler(
            overseer=overseer_skill.overseer,
            store=store,
            gateway=gateway,
        )
        overseer_scheduler.start()
        # Give the overseer a reference to the scheduler so check-ins can
        # report next_audit_at
        overseer_skill.overseer.set_scheduler(overseer_scheduler)
        logger.info("Overseer scheduler started")

    # Wire sports signals skill instances to app.state for JSON API
    signals_skill = registry.get("sports_signals")
    if signals_skill:
        app.state.signals_db = signals_skill.db
        app.state.signals_perf = signals_skill.perf
        app.state.signals_rec = signals_skill.rec
        logger.info("Sports signals API endpoints wired")

    # Wire politician intel DB to app.state for JSON API
    polint_skill = registry.get("politician_intel")
    if polint_skill:
        app.state.polint_db = polint_skill.db
        logger.info("Politician intel API endpoints wired")

    # Wire council skill + DB to app.state for JSON API
    council_skill = registry.get("council")
    if council_skill:
        app.state.council_skill = council_skill
        app.state.council_db = council_skill.db
        logger.info("Council API endpoints wired")

    # Wire live odds DB + client to app.state for JSON API
    odds_skill = registry.get("live_odds")
    if odds_skill:
        app.state.odds_db = odds_skill.db
        app.state.odds_client = odds_skill.client
        logger.info("Live odds API endpoints wired")

    yield

    logger.info("Shutting down OpenClaw...")
    if overseer_scheduler:
        overseer_scheduler.stop()
    if store:
        store.close()


app = FastAPI(
    title="OpenClaw",
    description="Jarvis AI Assistant — Core Gateway",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API Models ───────────────────────────────────────────

class MessageRequest(BaseModel):
    channel: str = "api"
    sender_id: str = "anonymous"
    content: str
    message_type: str = "text"
    conversation_id: str | None = None
    metadata: dict | None = None


class MessageResponse(BaseModel):
    text: str
    metadata: dict | None = None
    error: str | None = None


# ── Endpoints ────────────────────────────────────────────

@app.post("/api/v1/message", response_model=MessageResponse)
async def handle_message(req: MessageRequest):
    """Process a message through the OpenClaw pipeline."""
    if not gateway:
        raise HTTPException(status_code=503, detail="Service not ready")

    # Normalize channel
    try:
        channel = Channel(req.channel)
    except ValueError:
        channel = Channel.API

    message = UnifiedMessage(
        channel=channel,
        sender_id=req.sender_id,
        content=req.content,
        message_type=MessageType(req.message_type) if req.message_type else MessageType.TEXT,
        conversation_id=req.conversation_id,
        metadata=req.metadata or {},
    )

    response: SkillResponse = await gateway.handle_message(message)

    return MessageResponse(
        text=response.text,
        metadata=response.metadata,
        error=response.error,
    )


@app.get("/health", response_model=HealthStatus)
async def health():
    """Health check endpoint."""
    services = {}

    # Check Ollama
    if gateway:
        try:
            healthy = await gateway.inference.ollama.is_healthy()
            services["ollama"] = "ok" if healthy else "down"
        except Exception:
            services["ollama"] = "error"

        # Check OpenRouter availability
        services["openrouter"] = "ok" if gateway.inference.openrouter.is_available() else "unconfigured"

        # Budget status
        budget = gateway.inference.cost_tracker.get_budget_status()
        services["budget"] = f"${budget['spent_usd']}/{budget['budget_usd']}"

    return HealthStatus(services=services)


@app.get("/api/v1/skills")
async def list_skills():
    """List all registered skills."""
    if not gateway:
        raise HTTPException(status_code=503, detail="Service not ready")
    return gateway.registry.list_skills()


# ── Sports Signals JSON API ──────────────────────────────

class IngestRequest(BaseModel):
    source: str = "source_b"
    text: str


class GradeRequest(BaseModel):
    signal_id: int
    status: str


def _get_signals_db():
    db = getattr(app.state, "signals_db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Sports signals not available")
    return db


@app.get("/api/v1/signals/dashboard")
async def signals_dashboard():
    db = _get_signals_db()
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pending = db.get_pending_signals(limit=500)
    todays = db.get_signals_by_date(today)
    all_perf = db.get_source_performance()
    total_wins = sum(s.get("wins", 0) for s in all_perf)
    total_picks = sum(s.get("total_picks", 0) for s in all_perf)
    return {
        "date": today,
        "pending_count": len(pending),
        "today_count": len(todays),
        "source_count": len(all_perf),
        "overall_win_rate": round(total_wins / total_picks, 4) if total_picks else 0,
        "sources": all_perf,
    }


@app.get("/api/v1/signals/pending")
async def signals_pending():
    db = _get_signals_db()
    return db.get_pending_signals(limit=200)


@app.get("/api/v1/signals/straights")
async def signals_straights():
    db = _get_signals_db()
    perf = app.state.signals_perf
    rec = app.state.signals_rec
    return rec.generate_straights(db, perf)


@app.get("/api/v1/signals/parlays")
async def signals_parlays():
    db = _get_signals_db()
    perf = app.state.signals_perf
    rec = app.state.signals_rec
    return rec.generate_parlays(db, perf)


@app.get("/api/v1/signals/sources")
async def signals_sources():
    db = _get_signals_db()
    perf = app.state.signals_perf
    return perf.rank_sources(db)


@app.get("/api/v1/signals/results")
async def signals_results(date: str = Query(default=None)):
    db = _get_signals_db()
    from datetime import datetime, timezone
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return db.get_results_by_date(date)


@app.post("/api/v1/signals/ingest")
async def signals_ingest(req: IngestRequest):
    db = _get_signals_db()
    from openclaw.skills.sports_signals.parsers import parse_message
    raw_id = db.store_raw_message(req.source, req.text)
    parsed = parse_message(req.source, req.text)
    stored_ids = []
    for sig in parsed:
        if sig.get("_raw_only"):
            continue
        sig_id = db.store_signal(
            raw_message_id=raw_id,
            source=req.source,
            team_or_player=sig.get("team_or_player"),
            market=sig.get("market"),
            line=sig.get("line"),
            odds=sig.get("odds"),
            odds_decimal=sig.get("odds_decimal"),
            units=sig.get("units", 1.0),
            is_parlay_leg=sig.get("is_parlay_leg", False),
            parlay_group_id=sig.get("parlay_group_id"),
        )
        stored_ids.append(sig_id)
    return {
        "raw_id": raw_id,
        "signals_stored": len(stored_ids),
        "signal_ids": stored_ids,
        "parsed": [s for s in parsed if not s.get("_raw_only")],
    }


@app.post("/api/v1/signals/grade")
async def signals_grade(req: GradeRequest):
    db = _get_signals_db()
    if req.status not in ("win", "loss", "push", "void"):
        raise HTTPException(status_code=400, detail="Status must be win/loss/push/void")
    # Look up the source by ID before grading (works even if already graded)
    sig = db.get_signal_by_id(req.signal_id)
    db.grade_signal(req.signal_id, req.status)
    if sig:
        db.update_source_performance(sig["source"])
    return {"signal_id": req.signal_id, "status": req.status, "ok": True}


# ── Politician Intel JSON API ────────────────────────────

def _get_polint_db():
    db = getattr(app.state, "polint_db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Politician intel not available")
    return db


@app.get("/api/v1/politics/dashboard")
async def politics_dashboard():
    """Aggregate stats: politician count, alert counts, trade count, bill count."""
    db = _get_polint_db()
    from datetime import datetime, timezone
    alerts_undelivered = db.get_undelivered_alerts(limit=500)
    alerts_recent = db.get_recent_alerts(days=7, limit=500)
    trades_recent = db.get_gaming_trades(days=90, limit=500)
    bills = db.get_relevant_bills(min_score=0.3, limit=500)
    politicians = db.get_tracked_politicians()
    critical_count = sum(1 for a in alerts_recent if a.get("severity") == "critical")
    high_count = sum(1 for a in alerts_recent if a.get("severity") == "high")
    return {
        "tracked_politicians": len(politicians),
        "undelivered_alerts": len(alerts_undelivered),
        "alerts_7d": len(alerts_recent),
        "critical_alerts_7d": critical_count,
        "high_alerts_7d": high_count,
        "gaming_trades_90d": len(trades_recent),
        "relevant_bills": len(bills),
    }


@app.get("/api/v1/politics/alerts")
async def politics_alerts(limit: int = Query(default=20, le=100)):
    """Undelivered alerts first, then recent alerts as fallback."""
    db = _get_polint_db()
    alerts = db.get_undelivered_alerts(limit=limit)
    if not alerts:
        alerts = db.get_recent_alerts(days=7, limit=limit)
    return {"alerts": alerts, "count": len(alerts)}


@app.get("/api/v1/politics/trades")
async def politics_trades(days: int = Query(default=90, le=365), limit: int = Query(default=50, le=200)):
    """Gaming stock trades filed in the last N days."""
    db = _get_polint_db()
    trades = db.get_gaming_trades(days=days, limit=limit)
    return {"trades": trades, "count": len(trades)}


@app.get("/api/v1/politics/bills")
async def politics_bills(min_score: float = Query(default=0.3), limit: int = Query(default=50, le=200)):
    """Gambling-relevant bills above the relevance threshold."""
    db = _get_polint_db()
    bills = db.get_relevant_bills(min_score=min_score, limit=limit)
    return {"bills": bills, "count": len(bills)}


@app.get("/api/v1/politics/profile/{name}")
async def politics_profile(name: str):
    """Search for a politician by name and return their full profile."""
    db = _get_polint_db()
    politicians = db.search_politicians(name)
    if not politicians:
        raise HTTPException(status_code=404, detail=f"No politician found matching '{name}'")
    politician = politicians[0]
    trades = db.get_trades_by_politician(politician["id"], limit=20)
    return {"politician": politician, "trades": trades, "matches": len(politicians)}


@app.get("/api/v1/politics/briefing")
async def politics_briefing():
    """Combined daily intelligence briefing."""
    db = _get_polint_db()
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    alerts = db.get_recent_alerts(days=1, limit=20)
    trades = db.get_gaming_trades(days=7, limit=10)
    bills = db.get_relevant_bills(min_score=0.5, limit=10)
    return {
        "date": today,
        "alerts": alerts,
        "trades": trades,
        "bills": bills,
    }


@app.post("/api/v1/politics/collect")
async def politics_collect(congress: int = Query(default=119)):
    """Trigger a Congress.gov data collection run."""
    db = _get_polint_db()
    from openclaw.skills.politician_intel.collectors.congress import CongressCollector
    collector = CongressCollector(db)
    members = await collector.fetch_members(congress=congress)
    bills = await collector.fetch_bills(congress=congress)
    return {
        "congress": congress,
        "members_upserted": len(members),
        "bills_stored": len(bills),
        "ok": True,
    }


# ── Council of AI Agents JSON API ────────────────────────

class CouncilAnalyzeRequest(BaseModel):
    topic: str
    sender_id: str = "api"
    context: str = ""


def _get_council_skill():
    skill = getattr(app.state, "council_skill", None)
    if skill is None:
        raise HTTPException(status_code=503, detail="Council skill not available")
    return skill


def _get_council_db():
    db = getattr(app.state, "council_db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Council DB not available")
    return db


@app.post("/api/v1/council/analyze")
async def council_analyze(req: CouncilAnalyzeRequest):
    """Run a full 7-agent council debate on a topic."""
    from openclaw.skills.council.agents import AGENT_DEFINITIONS, CouncilAgent, Moderator
    import asyncio

    if not gateway:
        raise HTTPException(status_code=503, detail="Service not ready")

    council_skill = _get_council_skill()
    db = _get_council_db()

    # Instantiate agents
    agents = [CouncilAgent(defn, gateway.inference) for defn in AGENT_DEFINITIONS]

    # Run all agents in parallel
    opinion_coros = [agent.analyze(req.topic, req.context) for agent in agents]
    opinions = await asyncio.gather(*opinion_coros, return_exceptions=True)

    valid_opinions = []
    for i, op in enumerate(opinions):
        if isinstance(op, Exception):
            logger.warning("Council agent %s failed: %s", agents[i].name, op)
        else:
            valid_opinions.append(op)

    moderator = Moderator(gateway.inference)
    verdict = await moderator.synthesize(req.topic, valid_opinions)

    opinions_dicts = [
        {
            "agent_name": op.agent_name,
            "stance": op.stance,
            "confidence": op.confidence,
            "reasoning": op.reasoning,
            "key_factors": op.key_factors,
        }
        for op in valid_opinions
    ]
    debate_id = db.store_debate(
        topic=req.topic,
        consensus=verdict.consensus,
        confidence=verdict.confidence,
        summary=verdict.summary,
        bull_score=verdict.bull_score,
        bear_score=verdict.bear_score,
    )
    db.store_opinions(debate_id, opinions_dicts)

    return {
        "debate_id": debate_id,
        "topic": verdict.topic,
        "consensus": verdict.consensus,
        "confidence": verdict.confidence,
        "summary": verdict.summary,
        "bull_score": verdict.bull_score,
        "bear_score": verdict.bear_score,
        "agent_opinions": opinions_dicts,
    }


@app.get("/api/v1/council/debate/{debate_id}")
async def council_debate(debate_id: int):
    """Retrieve a specific council debate by ID."""
    db = _get_council_db()
    debate = db.get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail=f"Debate #{debate_id} not found")
    return debate


@app.get("/api/v1/council/history")
async def council_history(limit: int = Query(default=20, le=100)):
    """Return the N most recent council debates."""
    db = _get_council_db()
    return {"debates": db.get_history(limit=limit)}


@app.get("/api/v1/council/agents")
async def council_agents():
    """Return the list of council agent definitions."""
    from openclaw.skills.council.agents import AGENT_DEFINITIONS
    return {
        "agents": [
            {"name": d["name"], "display": d["display"]}
            for d in AGENT_DEFINITIONS
        ]
    }


# ── Live Odds JSON API ────────────────────────────────────

def _get_odds_db():
    db = getattr(app.state, "odds_db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Live odds not available")
    return db


def _get_odds_client():
    client = getattr(app.state, "odds_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="Live odds client not available")
    return client


@app.get("/api/v1/odds/sports")
async def odds_sports():
    """Return list of active sports from The Odds API."""
    client = _get_odds_client()
    if not client.is_available:
        return {"sports": [], "error": "ODDS_API_KEY not configured"}
    try:
        sports = await client.get_sports()
        return {"sports": sports}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/api/v1/odds/odds")
async def odds_fetch(
    sport: str = Query(..., description="Sport key, e.g. basketball_nba"),
    regions: str = Query(default="us"),
    markets: str = Query(default="h2h,spreads"),
):
    """Fetch live odds for a sport and store snapshots."""
    client = _get_odds_client()
    db = _get_odds_db()

    if not client.is_available:
        return {"events": [], "error": "ODDS_API_KEY not configured"}

    try:
        events = await client.get_odds(sport=sport, regions=regions, markets=markets)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Store snapshots
    for event in events[:20]:
        event_id = event.get("id", "")
        if not event_id:
            continue
        db.store_event(
            event_id=event_id,
            sport_key=event.get("sport_key", sport),
            sport_title=event.get("sport_title"),
            home_team=event.get("home_team", ""),
            away_team=event.get("away_team", ""),
            commence_time=event.get("commence_time"),
        )
        for bookmaker in event.get("bookmakers", []):
            bk_key = bookmaker.get("key", "")
            for market_data in bookmaker.get("markets", []):
                market_key = market_data.get("key", "")
                for outcome in market_data.get("outcomes", []):
                    db.store_snapshot(
                        event_id=event_id,
                        bookmaker=bk_key,
                        market=market_key,
                        outcome_name=outcome.get("name", ""),
                        price=outcome.get("price"),
                        point=outcome.get("point"),
                    )

    return {
        "sport": sport,
        "events": events,
        "count": len(events),
        "requests_remaining": client.requests_remaining,
    }


@app.get("/api/v1/odds/movement/{team}")
async def odds_movement(
    team: str,
    market: str = Query(default="spreads"),
    hours: int = Query(default=24, le=168),
):
    """Return line movement snapshots for a team."""
    db = _get_odds_db()
    snapshots = db.get_movement(team=team, market=market, hours=hours)
    return {"team": team, "market": market, "snapshots": snapshots, "count": len(snapshots)}


@app.get("/api/v1/odds/best/{event_id}")
async def odds_best(event_id: str, market: str = Query(default="h2h")):
    """Return best available price per outcome across all bookmakers for an event."""
    db = _get_odds_db()
    best = db.get_best_odds(event_id=event_id, market=market)
    return {"event_id": event_id, "market": market, "best_odds": best}

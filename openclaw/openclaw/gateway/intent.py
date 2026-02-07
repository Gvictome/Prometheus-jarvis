"""Intent classification: regex → heuristic → LLM fallback."""

from __future__ import annotations

import logging
import re
from typing import Any

from openclaw.gateway.schemas import SkillMatch

logger = logging.getLogger(__name__)

# ── Regex patterns: fast, exact matches ──────────────────
# Maps skill_name -> [(pattern, optional entity extractor)]
_REGEX_PATTERNS: dict[str, list[tuple[str, list[str]]]] = {
    "system_admin": [
        (r"\b(disk|storage)\s*(space|usage|free)\b", []),
        (r"\b(cpu|memory|ram|mem)\s*(usage|load|status)\b", []),
        (r"\bdocker\s+(ps|status|restart|logs|stats)\b", ["action"]),
        (r"\b(restart|stop|start)\s+(service|container|docker)\s+(\w+)\b", ["action", "_", "target"]),
        (r"\buptime\b", []),
        (r"\bsystem\s*(status|health|info)\b", []),
        (r"\bcheck\s+(disk|cpu|memory|ram|services?|ports?)\b", ["target"]),
    ],
    "daily_briefing": [
        (r"\b(daily\s*)?briefing\b", []),
        (r"\bwhat('s| is) (on )?(my )?(schedule|calendar|agenda)\b", []),
        (r"\bwhat('s| is) (on )?(for )?today\b", []),
        (r"\bmorning\s*(report|update|summary)\b", []),
        (r"\bmy\s*tasks?\b", []),
    ],
    "web_search": [
        (r"\bsearch\s+(for\s+)?(.+)", ["_", "query"]),
        (r"\bgoogle\s+(.+)", ["query"]),
        (r"\blook\s*up\s+(.+)", ["query"]),
        (r"\bfind\s+(info|information)\s+(about|on)\s+(.+)", ["_", "_", "query"]),
    ],
    "smart_home": [
        (r"\bturn\s+(on|off)\s+(the\s+)?(.+)", ["action", "_", "device"]),
        (r"\b(dim|brighten)\s+(the\s+)?(.+)", ["action", "_", "device"]),
        (r"\bset\s+(the\s+)?(.+?)\s+to\s+(.+)", ["_", "device", "value"]),
        (r"\b(lights?|lamp|fan|ac|thermostat)\s+(on|off)\b", ["device", "action"]),
        (r"\b(lock|unlock)\s+(the\s+)?(.+)", ["action", "_", "device"]),
    ],
    "security_monitor": [
        (r"\b(security|intrusion)\s*(check|status|scan|report)\b", []),
        (r"\bopen\s*ports?\b", []),
        (r"\bfail2ban\s*(status|report)\b", []),
        (r"\bsuspicious\s*(activity|connections?|login)\b", []),
    ],
    "memory": [
        (r"\bremember\s+(that\s+)?(.+)", ["_", "content"]),
        (r"\bwhat do you (know|remember) about\s+(.+)", ["_", "query"]),
        (r"\bforget\s+(about\s+)?(.+)", ["_", "target"]),
    ],
}

# ── Heuristic keywords: medium confidence ────────────────
_KEYWORD_MAP: dict[str, list[str]] = {
    "system_admin": ["server", "ssh", "process", "service", "nginx", "systemctl", "journalctl"],
    "daily_briefing": ["calendar", "schedule", "tasks", "todos", "agenda", "plan"],
    "web_search": ["search", "look up", "find out", "what is", "who is", "when did"],
    "smart_home": ["light", "switch", "temperature", "thermostat", "door", "camera"],
    "security_monitor": ["security", "firewall", "attack", "breach", "vulnerability"],
}


def classify_intent(
    text: str,
    available_skills: list[str] | None = None,
) -> SkillMatch:
    """Classify intent using regex patterns, then keyword heuristics.

    Returns SkillMatch with skill_name and confidence.
    Falls back to "conversation" if nothing matches.
    """
    text_lower = text.lower().strip()

    # Phase 1: Regex patterns (high confidence)
    for skill_name, patterns in _REGEX_PATTERNS.items():
        if available_skills and skill_name not in available_skills:
            continue
        for pattern, entity_names in patterns:
            match = re.search(pattern, text_lower)
            if match:
                entities = _extract_entities(match, entity_names)
                return SkillMatch(
                    skill_name=skill_name,
                    confidence=0.95,
                    entities=entities,
                    raw_intent=pattern,
                )

    # Phase 2: Keyword heuristics (medium confidence)
    best_skill = None
    best_score = 0

    for skill_name, keywords in _KEYWORD_MAP.items():
        if available_skills and skill_name not in available_skills:
            continue
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > best_score:
            best_score = score
            best_skill = skill_name

    if best_skill and best_score >= 1:
        confidence = min(0.8, 0.5 + best_score * 0.15)
        return SkillMatch(skill_name=best_skill, confidence=confidence)

    # Phase 3: Fallback to conversation
    return SkillMatch(skill_name="conversation", confidence=0.5)


async def classify_with_llm(
    text: str,
    skill_descriptions: str,
    inference_router,
) -> SkillMatch:
    """Use LLM to classify intent when heuristics are uncertain."""
    prompt = f"""Classify the following user message into exactly one skill category.

Available skills:
{skill_descriptions}

User message: "{text}"

Reply with ONLY the skill name, nothing else."""

    try:
        result = await inference_router.generate(
            prompt=prompt,
            system="You are an intent classifier. Reply with only the skill name.",
            force_provider="ollama",
            temperature=0.1,
        )
        skill_name = result["text"].strip().lower().replace('"', "").replace("'", "")
        return SkillMatch(skill_name=skill_name, confidence=0.7, raw_intent="llm")
    except Exception:
        logger.exception("LLM intent classification failed")
        return SkillMatch(skill_name="conversation", confidence=0.3)


def _extract_entities(
    match: re.Match, entity_names: list[str]
) -> dict[str, Any]:
    """Extract named entities from regex groups."""
    entities = {}
    for i, name in enumerate(entity_names):
        if name == "_":
            continue
        try:
            val = match.group(i + 1)
            if val:
                entities[name] = val.strip()
        except IndexError:
            pass
    return entities

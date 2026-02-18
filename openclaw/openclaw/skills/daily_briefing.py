"""Daily briefing skill — aggregates calendar, tasks, weather into a morning report."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, ClassVar

import httpx

from openclaw.config import settings
from openclaw.gateway.schemas import SkillContext, SkillResponse
from openclaw.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class NotionFetcher:
    """Lightweight Notion API wrapper for briefing data."""

    def __init__(self):
        self.token = settings.NOTION_TOKEN
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }
        self.base = "https://api.notion.com/v1"

    async def fetch_calendar(self, days_ahead: int = 7) -> list[dict[str, Any]]:
        if not settings.NOTION_CALENDAR_DB:
            return []
        today = datetime.now().strftime("%Y-%m-%d")
        payload = {
            "filter": {
                "property": "Date",
                "date": {"on_or_after": today},
            },
            "sorts": [{"property": "Date", "direction": "ascending"}],
            "page_size": 20,
        }
        return await self._query_db(settings.NOTION_CALENDAR_DB, payload)

    async def fetch_tasks(self) -> list[dict[str, Any]]:
        if not settings.NOTION_TASKS_DB:
            return []
        payload = {
            "filter": {
                "property": "Status",
                "status": {"does_not_equal": "Done"},
            },
            "sorts": [
                {"property": "Due", "direction": "ascending"},
            ],
            "page_size": 20,
        }
        return await self._query_db(settings.NOTION_TASKS_DB, payload)

    async def fetch_projects(self) -> list[dict[str, Any]]:
        if not settings.NOTION_PROJECTS_DB:
            return []
        payload = {
            "filter": {
                "property": "Status",
                "status": {"does_not_equal": "Completed"},
            },
            "sorts": [{"property": "Deadline", "direction": "ascending"}],
            "page_size": 10,
        }
        return await self._query_db(settings.NOTION_PROJECTS_DB, payload)

    async def _query_db(
        self, db_id: str, payload: dict
    ) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self.base}/databases/{db_id}/query",
                    headers=self.headers,
                    json=payload,
                )
                resp.raise_for_status()
                results = resp.json().get("results", [])
                return [self._parse_page(p) for p in results]
        except Exception:
            logger.exception("Notion query failed for db %s", db_id)
            return []

    @staticmethod
    def _parse_page(page: dict) -> dict[str, Any]:
        props = page.get("properties", {})
        parsed: dict[str, Any] = {"id": page["id"]}

        for key, val in props.items():
            ptype = val.get("type")
            if ptype == "title":
                arr = val.get("title", [])
                parsed["title"] = arr[0]["plain_text"] if arr else ""
            elif ptype == "date" and val.get("date"):
                parsed[key.lower()] = val["date"].get("start", "")
            elif ptype == "select" and val.get("select"):
                parsed[key.lower()] = val["select"].get("name", "")
            elif ptype == "status" and val.get("status"):
                parsed[key.lower()] = val["status"].get("name", "")
            elif ptype == "number":
                parsed[key.lower()] = val.get("number")

        return parsed


class DailyBriefingSkill(BaseSkill):
    name: ClassVar[str] = "daily_briefing"
    description: ClassVar[str] = "Daily briefing with calendar, tasks, and schedule"
    min_tier: ClassVar[int] = 0
    examples: ClassVar[list[str]] = [
        "daily briefing",
        "what's on my calendar",
        "what's on for today",
    ]

    async def execute(self, ctx: SkillContext) -> SkillResponse:
        if not settings.NOTION_TOKEN:
            return await self._llm_briefing(ctx)

        notion = NotionFetcher()
        calendar = await notion.fetch_calendar()
        tasks = await notion.fetch_tasks()
        projects = await notion.fetch_projects()

        # Build context for LLM summarization
        today = datetime.now()
        context = self._build_context(calendar, tasks, projects, today)

        prompt = f"""Based on the following data, create a concise daily briefing for today ({today.strftime('%A, %B %d, %Y')}).

{context}

Format the briefing with sections: Schedule, Priority Tasks, Active Projects, and a brief motivational note. Keep it concise and actionable."""

        try:
            result = await self.inference.generate(
                prompt=prompt,
                system="You are Jarvis creating a morning briefing. Be concise, structured, and actionable.",
                force_provider="openrouter" if len(context) > 1000 else None,
                sender_id=ctx.message.sender_id,
            )
            return self._reply(result["text"])
        except Exception as e:
            logger.exception("Briefing generation failed")
            return self._reply(self._fallback_briefing(calendar, tasks, today))

    async def _llm_briefing(self, ctx: SkillContext) -> SkillResponse:
        """Generate briefing without Notion (just LLM chat)."""
        result = await self.inference.generate(
            prompt=(
                f"Today is {datetime.now().strftime('%A, %B %d, %Y')}. "
                "Give me a brief, motivating morning briefing. Include the day/date, "
                "and suggest a productive structure for the day."
            ),
            system="You are Jarvis, a personal assistant. Be concise and encouraging.",
            sender_id=ctx.message.sender_id,
        )
        return self._reply(result["text"])

    @staticmethod
    def _build_context(
        calendar: list[dict],
        tasks: list[dict],
        projects: list[dict],
        today: datetime,
    ) -> str:
        sections = [f"Today is {today.strftime('%A, %B %d, %Y')}\n"]

        if calendar:
            sections.append("## Calendar Events")
            for evt in calendar:
                date = evt.get("date", evt.get("due", ""))
                sections.append(f"- {evt.get('title', 'Untitled')} — {date}")

        if tasks:
            sections.append("\n## Tasks")
            for task in tasks:
                status = task.get("status", "")
                due = task.get("due", "no due date")
                priority = task.get("priority", "")
                prefix = f"[{priority}] " if priority else ""
                sections.append(f"- {prefix}{task.get('title', 'Untitled')} ({status}, due: {due})")

        if projects:
            sections.append("\n## Active Projects")
            for proj in projects:
                deadline = proj.get("deadline", "no deadline")
                sections.append(f"- {proj.get('title', 'Untitled')} — deadline: {deadline}")

        return "\n".join(sections)

    @staticmethod
    def _fallback_briefing(
        calendar: list[dict], tasks: list[dict], today: datetime
    ) -> str:
        lines = [f"**Daily Briefing — {today.strftime('%A, %B %d, %Y')}**\n"]

        if calendar:
            lines.append("**Schedule:**")
            for evt in calendar[:5]:
                lines.append(f"  - {evt.get('title', '?')} — {evt.get('date', '?')}")
        else:
            lines.append("**Schedule:** No events today.")

        if tasks:
            lines.append("\n**Tasks:**")
            for task in tasks[:5]:
                lines.append(f"  - {task.get('title', '?')}")
        else:
            lines.append("\n**Tasks:** All clear!")

        lines.append("\nHave a productive day!")
        return "\n".join(lines)

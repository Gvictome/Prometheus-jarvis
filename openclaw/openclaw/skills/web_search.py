"""Web search skill — search the web and summarize results."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

import httpx

from openclaw.config import settings
from openclaw.gateway.schemas import SkillContext, SkillResponse
from openclaw.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class WebSearchSkill(BaseSkill):
    name: ClassVar[str] = "web_search"
    description: ClassVar[str] = "Search the web and summarize results"
    min_tier: ClassVar[int] = 0
    examples: ClassVar[list[str]] = [
        "search for Python FastAPI tutorial",
        "look up latest news about AI",
        "google best pizza recipe",
    ]

    async def execute(self, ctx: SkillContext) -> SkillResponse:
        query = ctx.match.entities.get("query", "").strip()
        if not query:
            # Extract query from the message by removing command words
            query = ctx.message.content
            for prefix in ("search for", "search", "look up", "google", "find info about", "find information on"):
                if query.lower().startswith(prefix):
                    query = query[len(prefix):].strip()
                    break

        if not query:
            return self._error("What would you like me to search for?")

        if not settings.SEARCH_API_KEY:
            # Fall back to LLM knowledge
            return await self._llm_answer(query)

        results = await self._google_search(query)
        if not results:
            return await self._llm_answer(query)

        # Summarize results with LLM
        return await self._summarize_results(query, results)

    async def _google_search(self, query: str) -> list[dict[str, Any]]:
        """Search using Google Custom Search API."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={
                        "key": settings.SEARCH_API_KEY,
                        "cx": settings.SEARCH_ENGINE_ID,
                        "q": query,
                        "num": 5,
                    },
                )
                resp.raise_for_status()
                items = resp.json().get("items", [])
                return [
                    {
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", ""),
                        "link": item.get("link", ""),
                    }
                    for item in items
                ]
        except Exception:
            logger.exception("Google search failed")
            return []

    async def _summarize_results(
        self, query: str, results: list[dict[str, Any]]
    ) -> SkillResponse:
        """Use LLM to summarize search results."""
        results_text = "\n\n".join(
            f"**{r['title']}**\n{r['snippet']}\nSource: {r['link']}"
            for r in results
        )

        prompt = f"""The user asked: "{query}"

Here are the search results:

{results_text}

Provide a concise, informative answer based on these results. Cite sources where relevant."""

        try:
            result = await self.inference.generate(
                prompt=prompt,
                system="Summarize search results concisely. Cite sources with URLs.",
            )
            return self._reply(result["text"])
        except Exception as e:
            # Fall back to raw results
            return self._reply(results_text)

    async def _llm_answer(self, query: str) -> SkillResponse:
        """Fall back to LLM knowledge when search API unavailable."""
        result = await self.inference.generate(
            prompt=f"Answer this question concisely: {query}",
            system="You are Jarvis. Answer questions directly and concisely. If you're not sure, say so.",
        )
        text = result["text"]
        if not settings.SEARCH_API_KEY:
            text += "\n\n_Note: Web search is not configured. This answer is from my training data._"
        return self._reply(text)

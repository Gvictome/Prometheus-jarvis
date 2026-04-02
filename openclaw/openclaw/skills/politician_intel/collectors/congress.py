"""Congress.gov API collector — v0.2

Fetches members, bills, votes, and committee assignments from the
Congress.gov REST API.  Requires a free API key set as env var
CONGRESS_API_KEY.

Rate limit: 5,000 requests/hour on the free tier.
Base URL: https://api.congress.gov/v3/
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.congress.gov/v3"
_API_KEY = os.getenv("CONGRESS_API_KEY", "")

# Committees with direct jurisdiction over gambling/sports/gaming legislation
TARGET_COMMITTEES = [
    "Senate Commerce, Science, and Transportation",
    "Senate Judiciary",
    "House Energy and Commerce",
    "House Judiciary",
    "House Ways and Means",
    "Senate Finance",
]

# Gaming/gambling keywords for bill filtering
_BILL_KEYWORDS = [
    "gambling", "gaming", "sports betting", "wagering", "lottery",
    "casino", "sportsbook", "igaming", "stadium", "sports franchise",
    "draftkings", "fanduel", "betmgm", "sports wager",
]

# Gaming stock tickers for trade classification
GAMING_TICKERS = {
    "DKNG", "PENN", "MGM", "CZR", "WYNN", "LVS", "BYD", "GDEN",
    "FLUT", "RSI", "EVRI", "AGS", "PDYPY", "GMBL", "BALY",
}


class CongressCollector:
    """Fetches and stores congressional data from the Congress.gov API.

    All methods are async and use httpx for non-blocking I/O.
    Results are written directly to the PoliticianDB instance passed at init.

    Usage:
        collector = CongressCollector(db)
        await collector.fetch_members()   # populates politicians table
        await collector.fetch_bills()     # populates bills table
    """

    def __init__(self, db: Any, http_client: Any | None = None) -> None:
        """Initialise the collector.

        Args:
            db: PoliticianDB instance for storing fetched data.
            http_client: Optional pre-configured httpx.AsyncClient. If None,
                         a new client is created per request (dev convenience).
        """
        self._db = db
        self._http = http_client
        if not _API_KEY:
            logger.warning(
                "CONGRESS_API_KEY not set — Congress.gov requests will fail. "
                "Get a free key at https://api.congress.gov/sign-up/"
            )

    # ── Public methods ────────────────────────────────────

    async def fetch_members(
        self,
        congress: int = 119,
        chamber: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all members of Congress for the given session and store them.

        Hits GET /v3/member?congress={congress}&chamber={chamber}.
        Pages through all results (limit=250 per page).
        Filters to TARGET_COMMITTEES and marks as tracked=True.

        Args:
            congress: Congress number, e.g. 119 for the 119th (2025-2026).
            chamber: 'senate', 'house', or None for both.

        Returns:
            List of raw member dicts from the API response.
        """
        if not _API_KEY:
            logger.error("fetch_members: CONGRESS_API_KEY not set")
            return []

        all_members: list[dict[str, Any]] = []
        offset = 0
        limit = 250

        while True:
            params: dict[str, Any] = {
                "congress": congress,
                "limit": limit,
                "offset": offset,
            }
            if chamber:
                params["chamber"] = chamber

            try:
                data = await self._get("/member", params)
            except Exception as exc:
                logger.error("fetch_members: API error at offset %d: %s", offset, exc)
                break

            members = data.get("members", [])
            if not members:
                break

            for m in members:
                raw_member = m.get("member", m)  # Congress.gov nests differently
                bioguide_id = raw_member.get("bioguideId", "")
                if not bioguide_id:
                    continue

                name = raw_member.get("name", "")
                if not name:
                    given = raw_member.get("firstName", "")
                    family = raw_member.get("lastName", "")
                    name = f"{given} {family}".strip()

                party_data = raw_member.get("partyHistory", [{}])
                party = party_data[0].get("partyAbbreviation", "") if party_data else ""

                terms = raw_member.get("terms", {})
                if isinstance(terms, dict):
                    term_items = terms.get("item", [])
                else:
                    term_items = []
                current_term = term_items[-1] if term_items else {}
                member_chamber = current_term.get("chamber", "").lower()
                state = raw_member.get("state", "")
                district = str(current_term.get("district", "")) if current_term.get("district") else None

                # Only track members on target committees (or all if no committee data)
                committees: list[str] = []
                try:
                    committee_data = await self._get(f"/member/{bioguide_id}/committee-assignments")
                    for ca in committee_data.get("committeeAssignments", []):
                        cname = ca.get("committee", {}).get("name", "")
                        if cname:
                            committees.append(cname)
                except Exception:
                    pass  # committee fetch is best-effort

                tracked = any(self._is_target_committee(c) for c in committees) if committees else True

                pol_id = self._db.upsert_politician(
                    bioguide_id=bioguide_id,
                    name=name,
                    party=party,
                    state=state,
                    chamber=member_chamber or ("senate" if chamber == "senate" else "house"),
                    district=district,
                    committees=committees,
                    tracked=tracked,
                )
                logger.debug("Upserted politician %s id=%d tracked=%s", name, pol_id, tracked)
                all_members.append(raw_member)

            # Pagination
            total = data.get("pagination", {}).get("count", 0)
            offset += limit
            if offset >= total or not members:
                break

        logger.info("fetch_members: upserted %d members for congress=%d", len(all_members), congress)
        return all_members

    async def fetch_bills(
        self,
        congress: int = 119,
        keywords: list[str] | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Fetch bills related to gambling/sports/stadium topics.

        Hits GET /v3/bill?congress={congress}&sort=updateDate+desc.
        Filters results by keyword match on title/subject.
        Scores relevance via RelevanceScorer before storing.

        Args:
            congress: Congress number to query.
            keywords: Additional keyword filters. Defaults to gambling/gaming/stadium keywords.
            limit: Maximum number of bills to return across all pages.

        Returns:
            List of relevant bill dicts from the API.
        """
        if not _API_KEY:
            logger.error("fetch_bills: CONGRESS_API_KEY not set")
            return []

        from openclaw.skills.politician_intel.analysis.relevance import RelevanceScorer
        scorer = RelevanceScorer()
        search_keywords = (keywords or []) + _BILL_KEYWORDS

        stored_bills: list[dict[str, Any]] = []
        offset = 0
        page_limit = 250

        while len(stored_bills) < limit:
            params: dict[str, Any] = {
                "congress": congress,
                "sort": "updateDate+desc",
                "limit": page_limit,
                "offset": offset,
            }

            try:
                data = await self._get("/bill", params)
            except Exception as exc:
                logger.error("fetch_bills: API error at offset %d: %s", offset, exc)
                break

            bills = data.get("bills", [])
            if not bills:
                break

            for bill in bills:
                title = bill.get("title", "")
                title_lower = title.lower()

                # Quick keyword filter before scoring (avoid unnecessary DB writes)
                if not any(kw in title_lower for kw in search_keywords):
                    # Check subjects too
                    subjects = [s.get("name", "") for s in bill.get("subjects", {}).get("legislativeSubjects", [])]
                    subjects_text = " ".join(subjects).lower()
                    if not any(kw in subjects_text for kw in search_keywords):
                        continue

                bill_type = bill.get("type", "").lower()
                bill_number = str(bill.get("number", ""))
                congress_bill_id = f"{bill_type}-{congress}-{bill_number}"

                summary_text = bill.get("latestAction", {}).get("text", "")
                subjects = [s.get("name", "") for s in bill.get("subjects", {}).get("legislativeSubjects", [])]

                relevance_score, category = scorer.score_bill(
                    title=title,
                    summary=summary_text,
                    subjects=subjects,
                )

                if relevance_score < 0.15:
                    continue

                # Resolve sponsor politician_id
                sponsor_id: int | None = None
                sponsor_data = bill.get("sponsors", [])
                if sponsor_data:
                    sponsor_bioguide = sponsor_data[0].get("bioguideId", "")
                    if sponsor_bioguide:
                        pol = self._db.get_politician(sponsor_bioguide)
                        if pol:
                            sponsor_id = pol["id"]

                introduced = bill.get("introducedDate", None)
                last_action_date = bill.get("latestAction", {}).get("actionDate", None)
                source_url = bill.get("url", None)

                # Map status
                action_text = bill.get("latestAction", {}).get("text", "").lower()
                if "became public law" in action_text or "signed by president" in action_text:
                    status = "enacted"
                elif "passed senate" in action_text:
                    status = "passed_senate"
                elif "passed house" in action_text:
                    status = "passed_house"
                elif "failed" in action_text or "defeated" in action_text:
                    status = "failed"
                else:
                    status = "introduced"

                bill_id = self._db.upsert_bill(
                    congress_bill_id=congress_bill_id,
                    title=title,
                    summary=summary_text,
                    status=status,
                    category=category,
                    relevance_score=relevance_score,
                    sponsor_id=sponsor_id,
                    congress_number=congress,
                    bill_type=bill_type,
                    bill_number=bill_number,
                    introduced_at=introduced,
                    last_action_at=last_action_date,
                    source_url=source_url,
                )
                logger.debug(
                    "Upserted bill id=%d %s score=%.3f category=%s",
                    bill_id, congress_bill_id, relevance_score, category,
                )
                stored_bills.append(bill)

            # Pagination
            total = data.get("pagination", {}).get("count", 0)
            offset += page_limit
            if offset >= total or not bills:
                break

        logger.info("fetch_bills: stored %d relevant bills for congress=%d", len(stored_bills), congress)
        return stored_bills

    async def fetch_votes(
        self,
        bioguide_id: str,
        congress: int = 119,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch voting record for a specific member.

        Hits GET /v3/member/{bioguide_id}/sponsored-legislation and
        cross-references with bills in the database.

        Args:
            bioguide_id: Member's BioGuide ID (e.g., 'P000197' for Pelosi).
            congress: Congress session to query.
            limit: Maximum votes to fetch.

        Returns:
            List of vote records stored.
        """
        if not _API_KEY:
            logger.error("fetch_votes: CONGRESS_API_KEY not set")
            return []

        pol = self._db.get_politician(bioguide_id)
        if not pol:
            logger.warning("fetch_votes: politician %s not in DB", bioguide_id)
            return []
        politician_id = pol["id"]

        stored: list[dict[str, Any]] = []
        params: dict[str, Any] = {"limit": min(limit, 250), "congress": congress}

        try:
            data = await self._get(f"/member/{bioguide_id}/votes", params)
        except Exception as exc:
            logger.error("fetch_votes %s: %s", bioguide_id, exc)
            return []

        for vote_item in data.get("votes", []):
            congress_vote_id = vote_item.get("rollNumber", "")
            vote_cast = vote_item.get("votePositionCode", vote_item.get("vote", "Not Voting"))
            voted_at = vote_item.get("actionDate", None)

            # Try to link to a known bill
            bill_id: int | None = None
            bill_ref = vote_item.get("bill", {})
            if bill_ref:
                btype = bill_ref.get("type", "").lower()
                bnum = str(bill_ref.get("number", ""))
                bcongress = bill_ref.get("congress", congress)
                cbid = f"{btype}-{bcongress}-{bnum}"
                row = self._db._conn.execute(
                    "SELECT id, relevance_score, category FROM bills WHERE congress_bill_id = ?",
                    (cbid,),
                ).fetchone()
                if row:
                    bill_id = row["id"]
                    relevance_score = row["relevance_score"]
                    category = row["category"]
                else:
                    relevance_score = 0.0
                    category = "other"
            else:
                relevance_score = 0.0
                category = "other"

            # Only store votes on relevant bills
            if relevance_score > 0:
                self._db.store_vote(
                    politician_id=politician_id,
                    vote_cast=vote_cast,
                    bill_id=bill_id,
                    congress_vote_id=str(congress_vote_id),
                    category=category,
                    relevance_score=relevance_score,
                    voted_at=voted_at,
                )
                stored.append(vote_item)

        logger.info("fetch_votes %s: stored %d relevant votes", bioguide_id, len(stored))
        return stored

    async def fetch_committees(
        self,
        congress: int = 119,
        chamber: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch committee membership for all tracked politicians.

        Hits GET /v3/committee for committee list, then fetches members for
        target committees and updates the politicians.committees column.

        Args:
            congress: Congress session to query.
            chamber: 'senate', 'house', or None for both.

        Returns:
            List of committee dicts fetched.
        """
        if not _API_KEY:
            logger.error("fetch_committees: CONGRESS_API_KEY not set")
            return []

        chambers = [chamber] if chamber else ["senate", "house"]
        all_committees: list[dict[str, Any]] = []

        for ch in chambers:
            params: dict[str, Any] = {"congress": congress, "chamber": ch, "limit": 250}
            try:
                data = await self._get("/committee", params)
            except Exception as exc:
                logger.error("fetch_committees %s: %s", ch, exc)
                continue

            for committee in data.get("committees", []):
                cname = committee.get("name", "")
                if not self._is_target_committee(cname):
                    continue

                all_committees.append(committee)
                committee_code = committee.get("systemCode", "")
                if not committee_code:
                    continue

                # Fetch members of this target committee
                try:
                    member_data = await self._get(f"/committee/{ch}/{committee_code}/members")
                    for member in member_data.get("members", []):
                        bioguide_id = member.get("bioguideId", "")
                        if not bioguide_id:
                            continue
                        pol = self._db.get_politician(bioguide_id)
                        if pol:
                            existing = pol.get("committees", [])
                            if cname not in existing:
                                existing.append(cname)
                                self._db.upsert_politician(
                                    bioguide_id=bioguide_id,
                                    name=pol["name"],
                                    party=pol.get("party"),
                                    state=pol.get("state"),
                                    chamber=pol.get("chamber"),
                                    district=pol.get("district"),
                                    committees=existing,
                                    tracked=True,
                                )
                except Exception as exc:
                    logger.warning("fetch_committees members %s: %s", committee_code, exc)

        logger.info("fetch_committees: processed %d target committees", len(all_committees))
        return all_committees

    # ── Private helpers ───────────────────────────────────

    async def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make an authenticated GET request to the Congress.gov API.

        Handles rate limiting (429) with exponential backoff.
        Uses scrape_cache to avoid redundant requests within the TTL.

        Args:
            endpoint: API path, e.g. '/member' (leading slash included).
            params: Query parameters dict.

        Returns:
            Parsed JSON response as dict.
        """
        try:
            import httpx
        except ImportError:
            raise RuntimeError(
                "httpx is required for CongressCollector. "
                "Add httpx to requirements.txt."
            )

        # Build full URL with API key
        full_params = dict(params or {})
        full_params["api_key"] = _API_KEY
        full_params["format"] = "json"

        url = f"{_BASE_URL}{endpoint}"

        # Check cache first (1-hour TTL for member data, 15-min for bills)
        cache_key = f"{url}?{json.dumps(full_params, sort_keys=True)}"
        cached = self._db.cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached["body"])
            except (json.JSONDecodeError, KeyError):
                pass

        # Exponential backoff on 429
        max_retries = 4
        for attempt in range(max_retries):
            try:
                if self._http:
                    response = await self._http.get(url, params=full_params)
                else:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.get(url, params=full_params)

                if response.status_code == 429:
                    wait_secs = 2 ** attempt * 15  # 15s, 30s, 60s, 120s
                    logger.warning(
                        "Congress.gov rate limit hit (attempt %d/%d), waiting %ds",
                        attempt + 1, max_retries, wait_secs,
                    )
                    await asyncio.sleep(wait_secs)
                    continue

                response.raise_for_status()
                body = response.text

                # Cache with 1-hour expiry
                from datetime import timedelta
                expires = (
                    datetime.now(timezone.utc) + timedelta(hours=1)
                ).strftime("%Y-%m-%d %H:%M:%S")
                self._db.cache_set(cache_key, body, status_code=response.status_code, expires_at=expires)

                return response.json()

            except Exception as exc:
                if attempt == max_retries - 1:
                    raise
                wait_secs = 2 ** attempt * 2
                logger.warning("_get %s attempt %d failed: %s — retrying in %ds", endpoint, attempt + 1, exc, wait_secs)
                await asyncio.sleep(wait_secs)

        raise RuntimeError(f"All {max_retries} retries failed for {endpoint}")

    def _is_target_committee(self, committee_name: str) -> bool:
        """Return True if the committee is in TARGET_COMMITTEES."""
        return any(
            target.lower() in committee_name.lower()
            for target in TARGET_COMMITTEES
        )

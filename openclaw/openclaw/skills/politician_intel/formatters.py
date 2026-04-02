"""Politician Intel — Telegram/WhatsApp output formatters.

All formatters return plain text strings suitable for Telegram and WhatsApp
(no markdown that requires special parsing — consistent with existing
skills/sports_signals/skill.py formatting style).

Divider width matched to _DIVIDER in sports_signals/skill.py.
"""

from __future__ import annotations

from typing import Any

_DIVIDER = "━" * 22

_SEVERITY_ICON = {
    "critical": "[CRITICAL]",
    "high":     "[HIGH]",
    "medium":   "[MED]",
    "low":      "[LOW]",
}

_IMPACT_ICON = {
    "bullish":          "[+]",
    "bearish":          "[-]",
    "mixed":            "[~]",
    "slightly_bearish": "[-]",
    "unknown":          "[?]",
}


def format_alert_list(alerts: list[dict[str, Any]]) -> str:
    """Format a list of intel alerts for Telegram/WhatsApp.

    Args:
        alerts: List of alert dicts from db.get_undelivered_alerts()
                or db.get_recent_alerts(). Must have keys: title, severity,
                alert_type, politician_name, ticker, created_at.

    Returns:
        Formatted text string ready to send as a message.
    """
    if not alerts:
        return (
            "Politician Intel — No New Alerts\n"
            + _DIVIDER
            + "\nAll clear. No undelivered alerts in the queue.\n"
            "Use 'politician briefing' for a full status summary."
        )

    lines = [f"Politician Intel Alerts ({len(alerts)} new)", _DIVIDER]

    for alert in alerts:
        sev_icon = _SEVERITY_ICON.get(alert.get("severity", "low"), "[?]")
        title = alert.get("title", "Untitled Alert")
        politician = alert.get("politician_name", "Unknown")
        ticker = alert.get("ticker", "")
        ticker_str = f" [{ticker}]" if ticker else ""
        created = alert.get("created_at", "")[:10]  # YYYY-MM-DD

        lines.append(f"{sev_icon} {title}{ticker_str}")
        lines.append(f"   {politician} — {created}")

        detail = alert.get("detail", "")
        if detail:
            # Truncate long detail strings for message format
            if len(detail) > 120:
                detail = detail[:117] + "..."
            lines.append(f"   {detail}")
        lines.append("")

    lines.append("Reply 'politician briefing' for full summary.")
    return "\n".join(lines).strip()


def format_trade_list(trades: list[dict[str, Any]]) -> str:
    """Format a list of gaming stock trades for Telegram/WhatsApp.

    Args:
        trades: List of trade dicts from db.get_gaming_trades(). Must have
                keys: politician_name, party, state, ticker, transaction_type,
                amount_range, filed_date, traded_date, source.

    Returns:
        Formatted text string.
    """
    if not trades:
        return (
            "Congressional Gaming Trades\n"
            + _DIVIDER
            + "\nNo gaming stock trades in the last 90 days.\n"
            "Trades appear within 45 days of the actual transaction."
        )

    lines = [f"Congressional Gaming Trades ({len(trades)} filed)", _DIVIDER]

    for t in trades:
        name = t.get("politician_name", "Unknown")
        party = t.get("party", "?")
        state = t.get("state", "?")
        ticker = t.get("ticker", "?")
        txn_type = t.get("transaction_type", "?").upper()
        amount = t.get("amount_range", "n/a")
        filed = t.get("filed_date", "?")
        traded = t.get("traded_date", "?")

        lines.append(f"{ticker} — {txn_type} — {amount}")
        lines.append(f"  {name} ({party}-{state})")
        lines.append(f"  Traded: {traded}  Filed: {filed}")
        lines.append("")

    return "\n".join(lines).strip()


def format_bill_list(bills: list[dict[str, Any]]) -> str:
    """Format a list of gambling/sports-relevant bills for Telegram/WhatsApp.

    Args:
        bills: List of bill dicts from db.get_relevant_bills(). Must have
               keys: title, status, category, relevance_score,
               congress_bill_id, introduced_at.

    Returns:
        Formatted text string.
    """
    if not bills:
        return (
            "Gambling Legislation Tracker\n"
            + _DIVIDER
            + "\nNo relevant bills above threshold score.\n"
            "Threshold: relevance_score >= 0.4"
        )

    lines = [f"Gambling Legislation ({len(bills)} tracked)", _DIVIDER]

    for b in bills:
        title = b.get("title", "Unknown Bill")
        status = b.get("status", "unknown").replace("_", " ").title()
        cat = b.get("category", "other").replace("_", " ").title()
        score = b.get("relevance_score", 0.0)
        bill_id = b.get("congress_bill_id", "")
        introduced = b.get("introduced_at", "?")[:10] if b.get("introduced_at") else "?"

        score_str = f"{int(score * 100)}%"
        lines.append(f"[{score_str}] {title}")
        lines.append(f"  {bill_id}  |  {status}  |  {cat}  |  {introduced}")
        lines.append("")

    return "\n".join(lines).strip()


def format_politician_profile(
    politician: dict[str, Any],
    trades: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
) -> str:
    """Format a politician intelligence profile for Telegram/WhatsApp.

    Args:
        politician: Politician dict from db.get_politician(). Must have keys:
                    name, party, state, chamber, committees.
        trades: List of recent trade dicts for this politician.
        alerts: List of recent alert dicts for this politician.

    Returns:
        Formatted text string.
    """
    name = politician.get("name", "Unknown")
    party = politician.get("party", "?")
    state = politician.get("state", "?")
    chamber = politician.get("chamber", "?").title()
    committees = politician.get("committees", [])

    lines = [
        f"Politician Profile: {name}",
        _DIVIDER,
        f"{party}  |  {state}  |  {chamber}",
    ]

    if committees:
        lines.append("")
        lines.append("Committees:")
        for c in committees[:5]:  # show max 5 committees
            lines.append(f"  - {c}")

    if trades:
        lines.append("")
        lines.append(f"Recent Gaming Trades ({len(trades)}):")
        for t in trades[:5]:
            ticker = t.get("ticker", "?")
            txn_type = t.get("transaction_type", "?").upper()
            amount = t.get("amount_range", "n/a")
            filed = t.get("filed_date", "?")
            lines.append(f"  {ticker} {txn_type} {amount} — filed {filed}")
    else:
        lines.append("")
        lines.append("Gaming Trades: None on record")

    if alerts:
        lines.append("")
        lines.append(f"Recent Alerts ({len(alerts)}):")
        for a in alerts[:3]:
            sev = _SEVERITY_ICON.get(a.get("severity", "low"), "[?]")
            lines.append(f"  {sev} {a.get('title', '?')}")
    else:
        lines.append("")
        lines.append("Recent Alerts: None")

    return "\n".join(lines)


def format_briefing(
    date: str,
    alerts: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    bills: list[dict[str, Any]],
) -> str:
    """Format a daily intelligence briefing for Telegram/WhatsApp.

    Args:
        date: Date string in YYYY-MM-DD format.
        alerts: List of recent alert dicts (last 24h).
        trades: List of recent gaming trade dicts (last 7 days).
        bills: List of high-relevance bill dicts.

    Returns:
        Formatted briefing text string.
    """
    critical = [a for a in alerts if a.get("severity") == "critical"]
    high = [a for a in alerts if a.get("severity") == "high"]

    lines = [
        f"Politician Intel Briefing — {date}",
        _DIVIDER,
        f"Alerts (24h):  {len(alerts)} total  |  {len(critical)} critical  |  {len(high)} high",
        f"Gaming Trades: {len(trades)} in last 7 days",
        f"Active Bills:  {len(bills)} above threshold",
    ]

    if critical:
        lines.append("")
        lines.append("CRITICAL ALERTS:")
        for a in critical[:3]:
            lines.append(f"  [!] {a.get('title', '?')}")
            lines.append(f"      {a.get('politician_name', '?')} — {a.get('ticker', '')}")

    if trades:
        lines.append("")
        lines.append("Recent Gaming Trades:")
        for t in trades[:3]:
            ticker = t.get("ticker", "?")
            txn_type = t.get("transaction_type", "?").upper()
            name = t.get("politician_name", "?")
            lines.append(f"  {ticker} {txn_type} — {name}")

    if bills:
        lines.append("")
        lines.append("Top Tracked Bills:")
        for b in bills[:3]:
            score = int(b.get("relevance_score", 0) * 100)
            lines.append(f"  [{score}%] {b.get('title', '?')[:60]}")

    lines.append("")
    lines.append("Use 'politician alerts' or 'politician trades' for details.")

    return "\n".join(lines)

"""api/routes/notes.py — GET /api/notes.

Returns the authenticated user's research notes, newest first. Read-only and
parameterized (``%s`` placeholders only). Registered with the read-only
routers so it works in public demo mode; a degraded Lakebase or any query
failure degrades to an empty envelope instead of crashing.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from loguru import logger

from api.deps import AppUser, get_current_user
from api.schemas import Envelope, Freshness, ResearchNote, iso

router = APIRouter()

_MAX_NOTES = 200


@router.get("", response_model=Envelope[ResearchNote])
def list_notes(user: AppUser = Depends(get_current_user)) -> Envelope[ResearchNote]:
    """The caller's research notes, newest first (never anyone else's)."""
    if user.degraded:
        return Envelope(
            data=[],
            count=0,
            empty=True,
            source="research_notes",
            freshness=Freshness(
                state="unavailable",
                table="research_notes",
                detail="account services unavailable",
            ),
        )

    state = "fresh"
    detail = ""
    try:
        from db.lakebase import get_lakebase

        db = get_lakebase()
        rows = db.execute(
            """
            SELECT note_id, symbol, note_text, created_at
            FROM research_notes
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user.user_id, _MAX_NOTES),
        )
    except Exception as exc:  # noqa: BLE001 - degrade, never crash the API
        logger.debug("research notes read failed: {}", type(exc).__name__)
        rows = []
        state = "unavailable"

    data = [
        ResearchNote(
            note_id=str(r[0] or ""),
            symbol=str(r[1] or ""),
            note_text=str(r[2] or ""),
            created_at=iso(r[3]) or "",
        )
        for r in (rows or [])
    ]
    if state == "fresh" and not data:
        state = "empty"
    detail = f"{len(data)} rows"
    return Envelope(
        data=data,
        count=len(data),
        empty=not data,
        source="research_notes",
        freshness=Freshness(state=state, table="research_notes", detail=detail),
    )

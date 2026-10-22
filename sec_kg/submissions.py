"""sec_kg/submissions.py — pure parser for SEC submissions API payloads.

Source: ``https://data.sec.gov/submissions/CIK##########.json`` (KG-0).

The parser is deliberately dependency-free and side-effect free so it can be
unit-tested offline and re-used by the ingestion job.  It returns exactly the
registrant fields the knowledge graph needs:

* ``cik10`` — the CIK zero-padded to ten digits (join key)
* ``name`` — the registrant's *current* legal name
* ``former_names`` — ``[{name, from_date, to_date}]`` as published: the SEC
  ``from`` / ``to`` values are inclusive and are never shifted.  The API
  publishes them as ISO-8601 midnight-UTC timestamps
  (``2001-04-02T00:00:00.000Z``); the parser keeps the published calendar date
  (``2001-04-02``) and drops only the redundant time component.
* ``sic`` / ``sic_description``
* ``tickers`` / ``exchanges`` — observations at ingest time, in payload order
* ``state_of_incorporation`` / ``fiscal_year_end`` / ``entity_type``
* ``data_source`` — always ``sec_edgar`` (controlled vocabulary in
  ``config/data_sources.py``)
* ``observed_at`` — the fetch timestamp supplied by the caller

No field is fabricated: a missing key becomes ``None`` (or an empty list for the
list-valued fields), never a default string.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping as MappingABC
from collections.abc import Sequence as SequenceABC
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from config.data_sources import validate_data_source

# Every record produced by this parser is an SEC EDGAR submissions observation.
SEC_EDGAR_DATA_SOURCE = validate_data_source("sec_edgar")

# Sentinel hash recorded for a 404 miss.  Hash of a fixed marker (not of an
# empty body) so a miss is distinguishable from a genuinely empty payload and
# so repeated 404s collapse to one bronze row under the (cik, payload_sha256)
# idempotency key.
MISS_PAYLOAD_SHA256 = hashlib.sha256(b"sec-submissions-missing").hexdigest()


def payload_sha256(payload: bytes) -> str:
    """SHA-256 hex digest of the raw payload bytes (stored verbatim)."""
    return hashlib.sha256(payload).hexdigest()


def normalize_cik(value: Any) -> str:
    """Return a CIK as a zero-padded ten-digit string.

    Raises ``ValueError`` for a missing or non-numeric CIK — a submissions
    payload without a usable CIK must fail loudly rather than produce a row
    that cannot be joined.
    """
    if value is None:
        raise ValueError("submissions payload has no cik")
    text = str(value).strip()
    if not text:
        raise ValueError("submissions payload has an empty cik")
    if not text.isdigit():
        raise ValueError(f"submissions payload has a non-numeric cik: {text!r}")
    return text.zfill(10)


@dataclass(frozen=True)
class FormerName:
    """One registrant former name interval, dates inclusive as published."""

    name: str
    from_date: Optional[str] = None
    to_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "from_date": self.from_date,
            "to_date": self.to_date,
        }


@dataclass(frozen=True)
class RegistrantRecord:
    """One parsed registrant observation from a submissions payload."""

    cik10: str
    name: Optional[str]
    data_source: str
    former_names: List[FormerName] = field(default_factory=list)
    sic: Optional[str] = None
    sic_description: Optional[str] = None
    tickers: List[str] = field(default_factory=list)
    exchanges: List[str] = field(default_factory=list)
    state_of_incorporation: Optional[str] = None
    fiscal_year_end: Optional[str] = None
    entity_type: Optional[str] = None
    observed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cik10": self.cik10,
            "name": self.name,
            "data_source": self.data_source,
            "former_names": [fn.to_dict() for fn in self.former_names],
            "sic": self.sic,
            "sic_description": self.sic_description,
            "tickers": list(self.tickers),
            "exchanges": list(self.exchanges),
            "state_of_incorporation": self.state_of_incorporation,
            "fiscal_year_end": self.fiscal_year_end,
            "entity_type": self.entity_type,
            "observed_at": self.observed_at,
        }


def _opt_str(value: Any) -> Optional[str]:
    """Return a stripped string, or ``None`` when the value is absent/blank."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# The submissions API publishes former-name intervals as ISO-8601 midnight-UTC
# timestamps ("2001-04-02T00:00:00.000Z"); plain "YYYY-MM-DD" also appears in
# older payloads and in our own fixtures/tests.
_ISO_CALENDAR_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})(?:[T ].*)?")


def _sec_date(value: Any) -> Optional[str]:
    """Return the published SEC calendar date (``YYYY-MM-DD``), or ``None``.

    A full ISO-8601 timestamp is truncated to its date part, which drops only a
    midnight-UTC time component: the calendar date is never shifted by a day, a
    timezone, or an inclusive/exclusive conversion.  Values that match neither
    shape are returned verbatim (stripped) rather than fabricated or dropped, so
    a future SEC format stays visible downstream instead of becoming NULL.
    """
    text = _opt_str(value)
    if text is None:
        return None
    match = _ISO_CALENDAR_DATE.fullmatch(text)
    if match:
        return match.group(1)
    return text


def _str_list(value: Any) -> List[str]:
    """Normalise a JSON list of strings, preserving payload order.

    Non-list values (missing, ``null``, a bare string) yield ``[]`` — the SEC
    contract is a list and inventing a one-element list would fabricate an
    observation.
    """
    if not isinstance(value, (list, tuple)):
        return []
    out: List[str] = []
    for item in value:
        text = _opt_str(item)
        if text is not None:
            out.append(text)
    return out


def parse_registrant(
    payload: Mapping[str, Any],
    observed_at: datetime,
) -> RegistrantRecord:
    """Parse one submissions API JSON object into a registrant record."""
    if not isinstance(payload, MappingABC):
        raise TypeError(
            f"submissions payload must be a mapping, got {type(payload).__name__}"
        )

    former_names: List[FormerName] = []
    raw_former = payload.get("formerNames")
    if isinstance(raw_former, SequenceABC) and not isinstance(
        raw_former, (str, bytes)
    ):
        for entry in raw_former:
            if not isinstance(entry, MappingABC):
                continue
            entry_name = _opt_str(entry.get("name"))
            if entry_name is None:
                # A nameless interval carries no usable identity; skip it
                # rather than emit a placeholder.
                continue
            former_names.append(
                FormerName(
                    name=entry_name,
                    # ``from`` / ``to`` are inclusive and stay on the published
                    # calendar date (ISO-8601 timestamps are date-truncated).
                    from_date=_sec_date(entry.get("from")),
                    to_date=_sec_date(entry.get("to")),
                )
            )

    # ``name`` is the current legal name; ``entityName`` is the same value in
    # the submissions schema and is used only as a fallback.
    name = _opt_str(payload.get("name")) or _opt_str(payload.get("entityName"))

    return RegistrantRecord(
        cik10=normalize_cik(payload.get("cik")),
        name=name,
        data_source=SEC_EDGAR_DATA_SOURCE,
        former_names=former_names,
        sic=_opt_str(payload.get("sic")),
        sic_description=_opt_str(payload.get("sicDescription")),
        tickers=_str_list(payload.get("tickers")),
        exchanges=_str_list(payload.get("exchanges")),
        state_of_incorporation=_opt_str(payload.get("stateOfIncorporation")),
        # SEC publishes fiscal year end as MMDD; keep it verbatim.
        fiscal_year_end=_opt_str(payload.get("fiscalYearEnd")),
        entity_type=_opt_str(payload.get("entityType")),
        observed_at=observed_at,
    )


def parse_registrant_json(
    payload_json: str,
    observed_at: datetime,
) -> RegistrantRecord:
    """Parse a raw submissions JSON string (convenience for the job)."""
    return parse_registrant(json.loads(payload_json), observed_at)

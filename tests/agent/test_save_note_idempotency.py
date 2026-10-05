"""Offline regression for save_research_note idempotency (REPLAY-INSERTS).

Drives the PRODUCTION agent.tools_write.save_research_note against an in-memory
fake of the research_notes table. The fake honours `ON CONFLICT
(idempotency_key) DO NOTHING` only when the production SQL actually contains
it, so deleting that clause (the REPLAY-INSERTS mutation) inserts a second
note and this test fails.
"""
from __future__ import annotations

import contextlib
import re

import pytest

import agent.tools_write as tw


class _FakeNotesDB:
    def __init__(self):
        self.notes: list[dict] = []  # rows of research_notes

    @contextlib.contextmanager
    def transaction(self):
        yield _FakeConn(self)


class _FakeConn:
    def __init__(self, db):
        self._db = db

    @contextlib.contextmanager
    def cursor(self):
        yield _FakeCursor(self._db)


class _FakeCursor:
    def __init__(self, db):
        self._db = db
        self._next = None

    def execute(self, sql, params=None):
        s = " ".join(sql.split())
        self._next = None
        if s.startswith("INSERT INTO research_notes"):
            note_id, user_id, symbol, signal_id, note_text, key = params[:6]
            on_conflict = re.search(r"ON CONFLICT \(idempotency_key\)( WHERE idempotency_key IS NOT NULL)? DO NOTHING", s)
            if on_conflict and any(n["key"] == key for n in self._db.notes):
                self._next = None  # DO NOTHING -> RETURNING yields no row
                return
            self._db.notes.append({"note_id": note_id, "symbol": symbol, "key": key})
            self._next = (note_id, symbol)
        elif s.startswith("SELECT note_id, symbol FROM research_notes"):
            key = params[0]
            match = [n for n in self._db.notes if n["key"] == key]
            self._next = (match[0]["note_id"], match[0]["symbol"]) if match else None
        else:
            # user upsert / agent_actions audit insert: accept, return a benign row
            self._next = ("ok",)

    def fetchone(self):
        return self._next


def test_replay_with_same_key_does_not_insert_twice(monkeypatch):
    monkeypatch.setattr(tw, "_reject_public_demo_write", lambda: None)
    db = _FakeNotesDB()
    first = tw.save_research_note("NVDA", "export-control note", user_id="u1",
                                  idempotency_key="trace-1:save", db=db)
    second = tw.save_research_note("NVDA", "export-control note", user_id="u1",
                                   idempotency_key="trace-1:save", db=db)
    assert len(db.notes) == 1, "replaying the same idempotency key inserted a second note"
    assert second["note_id"] == first["note_id"]
    assert second.get("replay") is True


def test_different_keys_insert_separately(monkeypatch):
    monkeypatch.setattr(tw, "_reject_public_demo_write", lambda: None)
    db = _FakeNotesDB()
    a = tw.save_research_note("NVDA", "a", user_id="u1", idempotency_key="k-a", db=db)
    b = tw.save_research_note("NVDA", "b", user_id="u1", idempotency_key="k-b", db=db)
    assert len(db.notes) == 2 and a["note_id"] != b["note_id"]

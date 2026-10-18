"""Incident state machine: the table, the single-statement guard, and the API codes."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from vigil.war import alert_bridge
from vigil.war.alert_bridge import (
    ALLOWED_TRANSITIONS,
    IncidentState,
    TransitionResult,
    can_transition,
    transition,
    try_transition,
)

S = IncidentState


def test_every_state_has_an_entry() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(IncidentState)


@pytest.mark.parametrize("terminal", [S.RESOLVED, S.DISMISSED])
def test_terminal_states_go_nowhere(terminal: IncidentState) -> None:
    assert all(not can_transition(terminal, t) for t in IncidentState)


@pytest.mark.parametrize(
    ("src", "dst", "ok"),
    [
        (S.TRIAGE, S.OPEN, True),
        (S.TRIAGE, S.ACTIVE, False),   # a CS report must be confirmed before anyone is paged
        (S.TRIAGE, S.RESOLVED, False),
        (S.OPEN, S.ACTIVE, True),
        (S.OPEN, S.RESOLVED, True),
        (S.ACTIVE, S.OPEN, False),
        (S.ACTIVE, S.RESOLVED, True),
        (S.ACTIVE, S.DISMISSED, False),  # something happened; resolve it, don't call it a false positive
        (S.OPEN, S.OPEN, False),
    ],
)
def test_transition_table(src: IncidentState, dst: IncidentState, ok: bool) -> None:
    assert can_transition(src, dst) is ok


class _FakeCursor:
    def __init__(self, db: _FakeDB) -> None:
        self.db = db
        self._row: tuple | None = None

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.db.statements.append((sql, params))
        if sql.lstrip().startswith("UPDATE"):
            _, _, incident_id, sources = params
            state = self.db.rows.get(incident_id)
            if state in sources:
                self.db.rows[incident_id] = params[0]
                self._row = (2,)
            else:
                self._row = None
        elif sql.lstrip().startswith("SELECT state"):
            state = self.db.rows.get(params[0])
            self._row = (state,) if state else None

    def fetchone(self) -> tuple | None:
        return self._row


class _FakeDB:
    def __init__(self, rows: dict[str, str]) -> None:
        self.rows = rows
        self.statements: list[tuple[str, tuple]] = []
        self.committed = False

    def __enter__(self) -> _FakeDB:
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)

    def commit(self) -> None:
        self.committed = True


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> _FakeDB:
    fake = _FakeDB({"inc1": "open", "inc2": "resolved"})
    mod = types.ModuleType("psycopg")
    mod.connect = lambda dsn: fake  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "psycopg", mod)
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://test")
    return fake


def test_legal_move_updates_and_audits(db: _FakeDB) -> None:
    assert try_transition("inc1", S.ACTIVE, "alice.dev") is TransitionResult.OK
    assert db.rows["inc1"] == "active"
    assert db.committed
    audit = [p for sql, p in db.statements if "incident_events" in sql]
    assert audit and audit[0][2] == '{"new_state": "active"}'


def test_guard_is_part_of_the_update_statement(db: _FakeDB) -> None:
    try_transition("inc1", S.RESOLVED, "alice.dev")
    sql, params = db.statements[0]
    assert "state = ANY(%s)" in sql
    assert params[3] == ["active", "open"]  # only states that may move to resolved


def test_resolved_incident_cannot_be_resolved_again(db: _FakeDB) -> None:
    assert try_transition("inc2", S.RESOLVED, "alice.dev") is TransitionResult.ILLEGAL
    assert db.rows["inc2"] == "resolved"
    assert not db.committed
    assert not any("incident_events" in sql for sql, _ in db.statements)


def test_unknown_incident_is_not_found(db: _FakeDB) -> None:
    assert try_transition("nope", S.ACTIVE, "alice.dev") is TransitionResult.NOT_FOUND


def test_bool_wrapper(db: _FakeDB) -> None:
    assert transition("inc1", S.ACTIVE, "alice.dev") is True
    assert transition("inc1", S.OPEN, "alice.dev") is False


def test_no_dsn_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "psycopg", types.ModuleType("psycopg"))
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    assert try_transition("inc1", S.ACTIVE, "a") is TransitionResult.UNAVAILABLE


# --- API status codes -------------------------------------------------------

@pytest.mark.parametrize(
    ("result", "status"),
    [
        (TransitionResult.OK, 200),
        (TransitionResult.NOT_FOUND, 404),
        (TransitionResult.ILLEGAL, 409),
        (TransitionResult.UNAVAILABLE, 503),
    ],
)
def test_api_maps_results_to_status(
    monkeypatch: pytest.MonkeyPatch, result: TransitionResult, status: int
) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from vigil.war import api

    published: list[dict] = []

    async def fake_publish(incident_id: str, event: dict) -> None:
        published.append(event)

    monkeypatch.setattr(alert_bridge, "try_transition", lambda *a, **k: result)
    monkeypatch.setattr(api, "_publish_sse", fake_publish)

    r = TestClient(api.app).post(
        "/incident/inc1/transition", json={"target_state": "active", "actor": "alice.dev"}
    )

    assert r.status_code == status
    assert bool(published) is (status == 200)  # nothing is broadcast for a refused move

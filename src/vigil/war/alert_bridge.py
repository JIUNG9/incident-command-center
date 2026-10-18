"""Incident creation flow.

Three sources converge on one DB row + one pre-load pipeline:
- AUTO         — MTTD detector confidence ≥ threshold
- ENG_MANUAL   — /war command from an engineer
- CS_MANUAL    — /war-report from CS, lands in triage state until on-call confirms
"""

from __future__ import annotations

import enum
import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

log = logging.getLogger(__name__)


class IncidentSource(enum.StrEnum):
    AUTO = "auto"             # MTTD detector
    ENG_MANUAL = "eng"        # engineer /war
    CS_MANUAL = "cs"          # CS / external /war-report


class IncidentState(enum.StrEnum):
    TRIAGE = "triage"         # CS-reported, awaiting on-call confirm
    OPEN = "open"             # confirmed, war-room created but participants not yet DM'd
    ACTIVE = "active"         # DMs sent, client-agent mirroring
    RESOLVED = "resolved"
    DISMISSED = "dismissed"   # closed without action (false positive)


@dataclass
class Incident:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    source: IncidentSource = IncidentSource.AUTO
    state: IncidentState = IncidentState.OPEN
    title: str = ""
    summary: str = ""
    severity: str = "medium"
    affected_service: str | None = None
    declared_by: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    version: int = 1          # for optimistic locking


def create_incident(
    *,
    source: IncidentSource,
    title: str,
    summary: str = "",
    severity: str = "medium",
    affected_service: str | None = None,
    declared_by: str = "",
    skip_triage: bool = False,
) -> Incident:
    """Create incident, persist to Postgres, run pre-load pipeline.

    For CS source, the state starts as TRIAGE unless skip_triage=True.
    """
    state = IncidentState.OPEN
    if source == IncidentSource.CS_MANUAL and not skip_triage:
        state = IncidentState.TRIAGE

    incident = Incident(
        source=source,
        state=state,
        title=title,
        summary=summary,
        severity=severity,
        affected_service=affected_service,
        declared_by=declared_by,
    )

    _persist(incident)
    log.info("incident %s created: state=%s source=%s", incident.id, state.value, source.value)

    # Run pre-load pipeline IF not in triage (triage incidents wait for on-call review)
    if state != IncidentState.TRIAGE:
        from vigil.war.preload import preload_panels
        try:
            preload_panels(incident)
        except Exception as exc:
            log.warning("preload failed for %s: %s — incident still created", incident.id, exc)

    return incident


# Legal moves. RESOLVED and DISMISSED are terminal: a recurrence is a new incident,
# so resolved_at and the postmortem are written once.
ALLOWED_TRANSITIONS: dict[IncidentState, frozenset[IncidentState]] = {
    IncidentState.TRIAGE: frozenset({IncidentState.OPEN, IncidentState.DISMISSED}),
    IncidentState.OPEN: frozenset(
        {IncidentState.ACTIVE, IncidentState.RESOLVED, IncidentState.DISMISSED}
    ),
    IncidentState.ACTIVE: frozenset({IncidentState.RESOLVED}),
    IncidentState.RESOLVED: frozenset(),
    IncidentState.DISMISSED: frozenset(),
}


class TransitionResult(enum.StrEnum):
    OK = "ok"
    NOT_FOUND = "not_found"
    ILLEGAL = "illegal"          # incident exists but isn't in a state that may move there
    UNAVAILABLE = "unavailable"  # no psycopg / no DSN


def can_transition(current: IncidentState, target: IncidentState) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def try_transition(incident_id: str, target_state: IncidentState, actor: str) -> TransitionResult:
    """Move an incident to target_state if its current state allows it.

    The legality check lives in the UPDATE's WHERE clause, so check and write are one
    statement: two racing requests can't both pass a stale read.
    """
    try:
        import psycopg
    except ImportError:
        log.error("psycopg not installed; cannot transition state")
        return TransitionResult.UNAVAILABLE

    dsn = os.environ.get("POSTGRES_DSN", "")
    if not dsn:
        log.error("POSTGRES_DSN not set")
        return TransitionResult.UNAVAILABLE

    sources = sorted(s.value for s, targets in ALLOWED_TRANSITIONS.items() if target_state in targets)

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE incidents
                   SET state = %s, version = version + 1,
                       resolved_at = CASE WHEN %s = 'resolved' THEN now() ELSE resolved_at END
                   WHERE id = %s AND state = ANY(%s) RETURNING version""",
            (target_state.value, target_state.value, incident_id, sources),
        )
        if not cur.fetchone():
            cur.execute("SELECT state FROM incidents WHERE id = %s", (incident_id,))
            row = cur.fetchone()
            if not row:
                return TransitionResult.NOT_FOUND
            log.warning("incident %s: %s -> %s refused (actor %s)",
                        incident_id, row[0], target_state.value, actor)
            return TransitionResult.ILLEGAL
        cur.execute(
            """INSERT INTO incident_events (incident_id, event_type, actor, payload)
                   VALUES (%s, 'state_change', %s, %s::jsonb)""",
            (incident_id, actor, json.dumps({"new_state": target_state.value})),
        )
        conn.commit()
    log.info("incident %s → %s by %s", incident_id, target_state.value, actor)
    return TransitionResult.OK


def transition(incident_id: str, target_state: IncidentState, actor: str) -> bool:
    """Bool wrapper over try_transition for callers that don't need the reason."""
    return try_transition(incident_id, target_state, actor) is TransitionResult.OK


def _persist(incident: Incident) -> None:
    """Insert into Postgres `incidents` table. Idempotent on incident.id."""
    try:
        import psycopg
    except ImportError:
        log.warning("psycopg not installed; incident persisted to log only")
        return

    dsn = os.environ.get("POSTGRES_DSN", "")
    if not dsn:
        log.warning("POSTGRES_DSN not set; incident persisted to log only: %s", asdict(incident))
        return

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO incidents
               (id, source, state, title, summary, severity, affected_service, declared_by, created_at, version)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO NOTHING""",
            (
                incident.id, incident.source.value, incident.state.value,
                incident.title, incident.summary, incident.severity,
                incident.affected_service, incident.declared_by,
                incident.created_at, incident.version,
            ),
        )
        conn.commit()

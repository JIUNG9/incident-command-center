"""MTTD "detective" — what to watch now, recovery, and new watch candidates.

Reframes MTTD from a synthetic latency chart into an action layer over the
incident history (incidents table) + the pattern miner (patterns table):

  - watch_now      : services with the most/most-recent incidents (last N days)
                     — the detective's current focus.
  - recovery       : MTTR (median minutes) by service x p_class — where recovery
                     is slow.
  - new_candidates : unapproved miner patterns (recurring signals not yet a rule)
                     — newly should-be-watched.

All read-only from Postgres via POSTGRES_DSN. Each section degrades to a small
synthetic sample on any failure and reports source=real|synthetic so the UI can
show a demo badge honestly. Tries the configured schema then public.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Query

log = logging.getLogger(__name__)

detective_router = APIRouter(prefix="/mttd", tags=["mttd-detective"])

# Schema search order — override with INCIDENT_SCHEMA (default: public only).
_SCHEMAS = [s for s in (os.environ.get("INCIDENT_SCHEMA", ""), "") if s is not None]
if not _SCHEMAS:
    _SCHEMAS = [""]

_WATCH_SQL = """
SELECT affected_service,
       COUNT(*)                                              AS incidents,
       MAX(created_at)                                       AS last_seen,
       COUNT(*) FILTER (WHERE detection_mode = 'auto')       AS auto,
       COUNT(*) FILTER (WHERE detection_mode = 'peer')       AS peer,
       COUNT(*) FILTER (WHERE detection_mode = 'customer')   AS customer,
       COUNT(*) FILTER (WHERE p_class IN ('P0','P1'))        AS critical
FROM {schema}incidents
WHERE created_at > now() - (%s || ' days')::interval
  AND affected_service IS NOT NULL
GROUP BY affected_service
ORDER BY incidents DESC, last_seen DESC
LIMIT 15
"""

_RECOVERY_SQL = """
WITH r AS (
  SELECT affected_service, p_class,
         EXTRACT(EPOCH FROM (resolved_at - created_at))/60.0 AS mttr_min
  FROM {schema}incidents
  WHERE created_at > now() - (%s || ' days')::interval
    AND resolved_at IS NOT NULL AND affected_service IS NOT NULL AND p_class IS NOT NULL
)
SELECT affected_service, p_class, COUNT(*) AS samples,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mttr_min) AS median_min
FROM r GROUP BY affected_service, p_class
ORDER BY median_min DESC NULLS LAST
LIMIT 15
"""

_CANDIDATES_SQL = """
SELECT name, description, confidence,
       COALESCE(jsonb_array_length(evidence_incidents), 0) AS hits, created_at
FROM {schema}patterns
WHERE approved = FALSE AND created_at > now() - interval '60 days'
ORDER BY confidence DESC NULLS LAST, created_at DESC
LIMIT 10
"""


def _query(sql_tmpl: str, params: list[Any]) -> list[tuple] | None:
    dsn = os.environ.get("POSTGRES_DSN", "")
    if not dsn:
        return None
    try:
        import psycopg
    except ImportError:
        return None
    for schema in _SCHEMAS:
        prefix = f"{schema}." if schema else ""
        try:
            with psycopg.connect(dsn, connect_timeout=2) as conn, conn.cursor() as cur:
                cur.execute(sql_tmpl.format(schema=prefix), params)
                return cur.fetchall()
        except Exception:  # noqa: BLE001 — next schema / synthetic fallback
            continue
    return None


def _synthetic() -> dict:
    return {
        "source": "synthetic",
        "watch_now": [
            {"service": "checkout-service", "incidents": 8, "last_seen": None,
             "auto": 5, "peer": 2, "customer": 1, "critical": 4},
            {"service": "auth-service", "incidents": 5, "last_seen": None,
             "auto": 3, "peer": 1, "customer": 1, "critical": 2},
            {"service": "api-gateway", "incidents": 3, "last_seen": None,
             "auto": 1, "peer": 1, "customer": 1, "critical": 0},
        ],
        "recovery": [
            {"service": "auth-service", "p_class": "P1", "samples": 2, "median_min": 95},
            {"service": "checkout-service", "p_class": "P1", "samples": 4, "median_min": 68},
        ],
        "new_candidates": [
            {"name": "recurring-alert-auth-service",
             "description": "recurring pattern: 3 hits. top service auth-service.",
             "confidence": 0.3, "hits": 3},
        ],
    }


@detective_router.get("/detective")
def detective(window_days: int = Query(30, ge=1, le=180)) -> dict:
    """Detective view: watch-now + recovery + new candidates. Real (DB) or synthetic."""
    out: dict[str, Any] = {}
    real_ok = False

    watch = _query(_WATCH_SQL, [str(window_days)])
    if watch is not None:
        real_ok = True
        out["watch_now"] = [
            {"service": r[0], "incidents": r[1],
             "last_seen": r[2].isoformat() if r[2] else None,
             "auto": r[3], "peer": r[4], "customer": r[5], "critical": r[6]}
            for r in watch
        ]

    recovery = _query(_RECOVERY_SQL, [str(window_days)])
    if recovery is not None:
        real_ok = True
        out["recovery"] = [
            {"service": r[0], "p_class": r[1], "samples": r[2],
             "median_min": round(float(r[3]), 1) if r[3] is not None else None}
            for r in recovery
        ]

    cands = _query(_CANDIDATES_SQL, [])
    if cands is not None:
        real_ok = True
        out["new_candidates"] = [
            {"name": r[0], "description": r[1],
             "confidence": round(float(r[2]), 2) if r[2] is not None else None, "hits": r[3]}
            for r in cands
        ]

    if not real_ok:
        return _synthetic()
    out.setdefault("watch_now", [])
    out.setdefault("recovery", [])
    out.setdefault("new_candidates", [])
    out["source"] = "real"
    return out

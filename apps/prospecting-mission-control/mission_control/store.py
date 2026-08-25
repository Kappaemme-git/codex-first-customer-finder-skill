"""Durable local SQLite control-plane store for the Phase 4 registered worker.

The store is repository-local. It initializes additively and idempotently, keeps
every governed multi-record change inside one serialized transaction, and never
uses DROP, TRUNCATE, or delete-and-recreate recovery.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Callable

from .application import MissionControlError

SCHEMA_VERSION = 2
BUSY_TIMEOUT_MS = 2_000
MAX_CONFIG_BYTES = 16_384
MAX_SNAPSHOT_BYTES = 262_144
RUN_STATES = {
    "queued",
    "running",
    "succeeded",
    "failed_retryable",
    "failed_terminal",
    "timed_out",
    "cancelled",
}

PHASE4_TABLES = (
    """CREATE TABLE IF NOT EXISTS schema_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS id_counters (
        prefix TEXT PRIMARY KEY,
        value INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS worker_runs (
        run_id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        agent_version TEXT NOT NULL,
        campaign_family_id TEXT NOT NULL,
        campaign_version INTEGER NOT NULL,
        business_unit TEXT NOT NULL,
        initiating_actor TEXT NOT NULL,
        skill_id TEXT NOT NULL,
        skill_version TEXT NOT NULL,
        skill_integrity TEXT NOT NULL,
        configuration_snapshot TEXT NOT NULL,
        configuration_hash TEXT NOT NULL,
        idempotency_key TEXT NOT NULL UNIQUE,
        request_fingerprint TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN (
            'queued','running','succeeded','failed_retryable',
            'failed_terminal','timed_out','cancelled')),
        attempt_count INTEGER NOT NULL DEFAULT 0,
        max_attempts INTEGER NOT NULL,
        timeout_seconds INTEGER NOT NULL,
        cost_cap_usd INTEGER NOT NULL,
        actual_cost_usd INTEGER,
        cancel_requested INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        updated_at TEXT NOT NULL,
        failure_class TEXT,
        retryable INTEGER,
        remediation TEXT,
        output_id TEXT,
        review_task_id TEXT,
        row_version INTEGER NOT NULL DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS worker_attempts (
        attempt_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES worker_runs(run_id),
        attempt_number INTEGER NOT NULL,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        starting_state TEXT NOT NULL,
        terminal_state TEXT,
        worker_version TEXT NOT NULL,
        timeout_seconds INTEGER NOT NULL,
        outcome TEXT,
        failure_class TEXT,
        retryable INTEGER,
        estimated_cost_usd INTEGER,
        output_hash TEXT,
        audit_correlation_id TEXT NOT NULL,
        UNIQUE (run_id, attempt_number)
    )""",
    """CREATE TABLE IF NOT EXISTS worker_outputs (
        output_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL UNIQUE REFERENCES worker_runs(run_id),
        attempt_number INTEGER NOT NULL,
        business_unit TEXT NOT NULL,
        campaign_family_id TEXT NOT NULL,
        campaign_version INTEGER NOT NULL,
        skill_id TEXT NOT NULL,
        skill_version TEXT NOT NULL,
        output_schema TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        byte_length INTEGER NOT NULL,
        fixture_source_ids TEXT NOT NULL,
        result_ids TEXT NOT NULL,
        estimated_cost_usd INTEGER NOT NULL,
        errors TEXT NOT NULL,
        stop_reason TEXT NOT NULL,
        result_snapshot TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS review_tasks (
        task_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL UNIQUE REFERENCES worker_runs(run_id),
        output_id TEXT NOT NULL UNIQUE REFERENCES worker_outputs(output_id),
        business_unit TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending_review',
        allowed_reviewers TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS audit_events (
        audit_id TEXT PRIMARY KEY,
        run_id TEXT,
        event_type TEXT NOT NULL,
        actor TEXT NOT NULL,
        business_unit TEXT,
        correlation_id TEXT NOT NULL,
        safe_status TEXT NOT NULL,
        recorded_at TEXT NOT NULL
    )""",
)

_PHASE5_TABLES = (
    """CREATE TABLE IF NOT EXISTS shadow_schedule_versions (
        schedule_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        business_unit TEXT NOT NULL,
        name TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        weekday INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
        utc_hour INTEGER NOT NULL CHECK (utc_hour BETWEEN 0 AND 23),
        utc_minute INTEGER NOT NULL CHECK (utc_minute BETWEEN 0 AND 59),
        prospect_cap INTEGER NOT NULL CHECK (prospect_cap BETWEEN 1 AND 15),
        cost_cap_usd INTEGER NOT NULL CHECK (cost_cap_usd = 0),
        open_discovery_every INTEGER NOT NULL CHECK (open_discovery_every >= 0),
        configuration_hash TEXT NOT NULL,
        PRIMARY KEY (schedule_id, version)
    )""",
    """CREATE TABLE IF NOT EXISTS shadow_schedule_campaigns (
        schedule_id TEXT NOT NULL,
        schedule_version INTEGER NOT NULL,
        position INTEGER NOT NULL,
        campaign_family_id TEXT NOT NULL,
        campaign_version INTEGER NOT NULL,
        discovery_scope TEXT NOT NULL CHECK (discovery_scope IN ('open','filtered')),
        configuration_snapshot TEXT NOT NULL,
        configuration_hash TEXT NOT NULL,
        PRIMARY KEY (schedule_id, schedule_version, position),
        UNIQUE (schedule_id, schedule_version, campaign_family_id, campaign_version),
        FOREIGN KEY (schedule_id, schedule_version)
            REFERENCES shadow_schedule_versions(schedule_id, version)
    )""",
    """CREATE TABLE IF NOT EXISTS shadow_schedules (
        schedule_id TEXT PRIMARY KEY,
        business_unit TEXT NOT NULL,
        current_version INTEGER NOT NULL,
        state TEXT NOT NULL DEFAULT 'disabled'
            CHECK (state IN ('disabled','enabled','paused')),
        next_due_at TEXT,
        occurrence_ordinal INTEGER NOT NULL DEFAULT 0,
        health TEXT NOT NULL DEFAULT 'not_run'
            CHECK (health IN ('not_run','healthy','unhealthy','paused','disabled')),
        last_stop_reason TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        row_version INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (schedule_id, current_version)
            REFERENCES shadow_schedule_versions(schedule_id, version)
    )""",
    """CREATE TABLE IF NOT EXISTS shadow_occurrences (
        occurrence_id TEXT PRIMARY KEY,
        schedule_id TEXT NOT NULL,
        schedule_version INTEGER NOT NULL,
        business_unit TEXT NOT NULL,
        scheduled_for TEXT NOT NULL,
        ordinal INTEGER NOT NULL,
        campaign_family_id TEXT NOT NULL,
        campaign_version INTEGER NOT NULL,
        discovery_scope TEXT NOT NULL,
        idempotency_key TEXT NOT NULL UNIQUE,
        opportunity_key TEXT UNIQUE,
        state TEXT NOT NULL CHECK (state IN ('claimed','completed','failed','blocked')),
        history_snapshot TEXT,
        history_hash TEXT,
        worker_run_id TEXT REFERENCES worker_runs(run_id),
        result_count INTEGER,
        duplicate_count INTEGER,
        duplicate_rate REAL,
        failure_class TEXT,
        stop_reason TEXT,
        claimed_at TEXT NOT NULL,
        completed_at TEXT,
        UNIQUE (schedule_id, scheduled_for),
        FOREIGN KEY (schedule_id, schedule_version)
            REFERENCES shadow_schedule_versions(schedule_id, version)
    )""",
    """CREATE TABLE IF NOT EXISTS shadow_alerts (
        alert_id TEXT PRIMARY KEY,
        schedule_id TEXT NOT NULL REFERENCES shadow_schedules(schedule_id),
        occurrence_id TEXT REFERENCES shadow_occurrences(occurrence_id),
        business_unit TEXT NOT NULL,
        failure_class TEXT NOT NULL,
        safe_message TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS shadow_schedule_audits (
        audit_id TEXT PRIMARY KEY,
        schedule_id TEXT NOT NULL REFERENCES shadow_schedules(schedule_id),
        occurrence_id TEXT REFERENCES shadow_occurrences(occurrence_id),
        event_type TEXT NOT NULL,
        actor TEXT NOT NULL,
        business_unit TEXT NOT NULL,
        safe_status TEXT NOT NULL,
        recorded_at TEXT NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS shadow_schedule_due_idx
        ON shadow_schedules(state, next_due_at, schedule_id)""",
    """CREATE INDEX IF NOT EXISTS shadow_occurrence_schedule_idx
        ON shadow_occurrences(schedule_id, scheduled_for DESC)""",
    """CREATE INDEX IF NOT EXISTS shadow_alert_bu_idx
        ON shadow_alerts(business_unit, created_at DESC)""",
)


def canonical_json(value: Any, *, limit: int, label: str) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > limit:
        raise MissionControlError(400, f"{label} exceeds the bounded local storage size.")
    return serialized


def decoded_list(raw: str, label: str) -> list[Any]:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError, UnicodeError) as exc:
        raise MissionControlError(500, f"Stored {label} has an unexpected shape.") from exc
    if not isinstance(value, list):
        raise MissionControlError(500, f"Stored {label} has an unexpected shape.")
    return value


def shadow_result_metrics(results: list[Any]) -> tuple[int, int, float]:
    """Return result count, identity-classified count, and duplicate rate."""
    if not isinstance(results, list) or any(not isinstance(item, dict) for item in results):
        raise MissionControlError(500, "Stored result snapshot has an unexpected shape.")
    duplicate_count = 0
    for item in results:
        classification = item.get("duplicate_classification")
        if classification is not None and (
            not isinstance(classification, str) or not classification or len(classification) > 100
        ):
            raise MissionControlError(500, "Stored result snapshot has an unexpected shape.")
        duplicate_count += classification is not None
    result_count = len(results)
    return result_count, duplicate_count, duplicate_count / result_count if result_count else 0.0


def worker_request_fingerprint(fields: dict[str, Any], *, scheduled: bool = False) -> str:
    """Preserve the finalized manual fingerprint while namespacing scheduled work."""
    payload = {
        "agent_id": fields["agent_id"],
        "campaign_family_id": fields["campaign_family_id"],
        "campaign_version": fields["campaign_version"],
        "business_unit": fields["business_unit"],
        "initiating_actor": fields["initiating_actor"],
        "configuration_hash": fields["configuration_hash"],
        "skill_id": fields["skill_id"],
        "skill_version": fields["skill_version"],
    }
    if scheduled:
        payload["request_kind"] = "scheduled_shadow"
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


class IdempotencyKeyExists(Exception):
    """A concurrent create already persisted this idempotency key.

    Raised instead of a storage error so the service can resolve the race as an
    idempotent replay or a safe conflict, never a 500.
    """


class SqliteStore:
    """Connection-per-operation adapter. All governed writes are transactional."""

    def __init__(self, path: Path, fault_hook: Callable[[str], None] | None = None):
        self.path = Path(path)
        self.fault_hook = fault_hook
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _fault(self, label: str) -> None:
        if self.fault_hook:
            self.fault_hook(label)

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_MS / 1000)
        except sqlite3.Error as exc:
            raise MissionControlError(500, "The local durable store is unavailable.") from exc
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        return connection

    def _initialize(self) -> None:
        with self.transaction() as connection:
            for statement in PHASE4_TABLES:
                connection.execute(statement)
            row = connection.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?)",
                    ("1",),
                )
                current = 1
            else:
                try:
                    current = int(row["value"])
                except (TypeError, ValueError) as exc:
                    raise MissionControlError(500, "The local state schema version is invalid.") from exc
            if current > SCHEMA_VERSION:
                raise MissionControlError(500, "The local state file uses a newer schema version.")
            if current < 1:
                raise MissionControlError(500, "The local state schema version is invalid.")
            if current == 1:
                for statement in _PHASE5_TABLES:
                    connection.execute(statement)
                connection.execute(
                    "UPDATE schema_meta SET value = ? WHERE key = 'schema_version'",
                    (str(SCHEMA_VERSION),),
                )

    class _Transaction:
        def __init__(self, store: "SqliteStore"):
            self.store = store
            self.connection: sqlite3.Connection | None = None

        def __enter__(self) -> sqlite3.Connection:
            self.connection = self.store._connect()
            try:
                self.connection.execute("BEGIN IMMEDIATE")
            except sqlite3.Error as exc:
                self.connection.close()
                raise MissionControlError(500, "The local durable store is busy or unavailable.") from exc
            return self.connection

        def __exit__(self, exc_type, exc, tb) -> bool:
            assert self.connection is not None
            try:
                if exc_type is None:
                    self.connection.commit()
                else:
                    self.connection.rollback()
            finally:
                self.connection.close()
            if exc_type is not None and issubclass(exc_type, sqlite3.Error):
                raise MissionControlError(500, "The durable transaction was rolled back.") from exc
            return False

    def transaction(self) -> "SqliteStore._Transaction":
        return SqliteStore._Transaction(self)

    def next_id(self, connection: sqlite3.Connection, prefix: str) -> str:
        connection.execute(
            "INSERT INTO id_counters (prefix, value) VALUES (?, 0) ON CONFLICT (prefix) DO NOTHING",
            (prefix,),
        )
        connection.execute("UPDATE id_counters SET value = value + 1 WHERE prefix = ?", (prefix,))
        value = connection.execute(
            "SELECT value FROM id_counters WHERE prefix = ?", (prefix,)
        ).fetchone()["value"]
        return f"{prefix}-{value:04d}"

    def insert_audit(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str | None,
        event_type: str,
        actor: str,
        business_unit: str | None,
        correlation_id: str,
        safe_status: str,
        recorded_at: str,
    ) -> str:
        self._fault("insert_audit")
        audit_id = self.next_id(connection, "waudit")
        connection.execute(
            "INSERT INTO audit_events (audit_id, run_id, event_type, actor, business_unit,"
            " correlation_id, safe_status, recorded_at) VALUES (?,?,?,?,?,?,?,?)",
            (audit_id, run_id, event_type, actor, business_unit, correlation_id, safe_status, recorded_at),
        )
        return audit_id

    def record_audit(self, **kwargs: Any) -> str:
        with self.transaction() as connection:
            return self.insert_audit(connection, **kwargs)

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> dict[str, Any]:
        run = dict(row)
        run["configuration"] = json.loads(run.pop("configuration_snapshot"))
        run["cancel_requested"] = bool(run["cancel_requested"])
        run["retryable"] = None if run["retryable"] is None else bool(run["retryable"])
        return run

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM worker_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        finally:
            connection.close()
        return self._row_to_run(row) if row else None

    def find_run_by_key(self, idempotency_key: str) -> dict[str, Any] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM worker_runs WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
        finally:
            connection.close()
        return self._row_to_run(row) if row else None

    def list_runs(self, business_units: set[str]) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM worker_runs ORDER BY run_id"
            ).fetchall()
        finally:
            connection.close()
        return [self._row_to_run(row) for row in rows if row["business_unit"] in business_units]

    def create_run(
        self, fields: dict[str, Any], *, now: str, shadow_occurrence_id: str | None = None,
    ) -> dict[str, Any]:
        snapshot = canonical_json(fields["configuration"], limit=MAX_CONFIG_BYTES, label="Configuration snapshot")
        with self.transaction() as connection:
            self._fault("insert_run")
            existing = connection.execute(
                "SELECT run_id FROM worker_runs WHERE idempotency_key = ?",
                (fields["idempotency_key"],),
            ).fetchone()
            if existing is not None:
                raise IdempotencyKeyExists(existing["run_id"])
            run_id = self.next_id(connection, "wrun")
            correlation_id = self.next_id(connection, "wcorr")
            statement = (
                "INSERT INTO worker_runs (run_id, agent_id, agent_version, campaign_family_id,"
                " campaign_version, business_unit, initiating_actor, skill_id, skill_version,"
                " skill_integrity, configuration_snapshot, configuration_hash, idempotency_key,"
                " request_fingerprint, state, attempt_count, max_attempts, timeout_seconds,"
                " cost_cap_usd, cancel_requested, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'queued', 0, ?, ?, ?, 0, ?, ?)"
            )
            values = (
                    run_id,
                    fields["agent_id"],
                    fields["agent_version"],
                    fields["campaign_family_id"],
                    fields["campaign_version"],
                    fields["business_unit"],
                    fields["initiating_actor"],
                    fields["skill_id"],
                    fields["skill_version"],
                    fields["skill_integrity"],
                    snapshot,
                    fields["configuration_hash"],
                    fields["idempotency_key"],
                    fields["request_fingerprint"],
                    fields["max_attempts"],
                    fields["timeout_seconds"],
                    fields["cost_cap_usd"],
                    now,
                    now,
                )
            try:
                connection.execute(statement, values)
            except sqlite3.IntegrityError as exc:
                if "idempotency_key" in str(exc):
                    raise IdempotencyKeyExists(fields["idempotency_key"]) from exc
                raise
            if shadow_occurrence_id is not None:
                self._fault("link_shadow_run")
                cursor = connection.execute(
                    "UPDATE shadow_occurrences SET worker_run_id=?"
                    " WHERE occurrence_id=? AND state='claimed' AND worker_run_id IS NULL"
                    " AND business_unit=? AND campaign_family_id=? AND campaign_version=?"
                    " AND idempotency_key=?",
                    (
                        run_id, shadow_occurrence_id, fields["business_unit"],
                        fields["campaign_family_id"], fields["campaign_version"],
                        fields["idempotency_key"],
                    ),
                )
                if cursor.rowcount != 1:
                    raise MissionControlError(409, "The shadow occurrence run link conflicts.")
            self.insert_audit(
                connection,
                run_id=run_id,
                event_type=fields.get("request_event", "manual_request_accepted"),
                actor=fields["initiating_actor"],
                business_unit=fields["business_unit"],
                correlation_id=correlation_id,
                safe_status="queued",
                recorded_at=now,
            )
        run = self.get_run(run_id)
        assert run is not None
        return run

    def claim_attempt(
        self,
        run_id: str,
        *,
        expected_states: tuple[str, ...],
        actor: str,
        worker_version: str,
        now: str,
        retry_accepted: bool = False,
    ) -> dict[str, Any] | None:
        """Atomically move the run to running and append the next attempt.

        Returns None when another transition already won, so a double claim can
        never start two attempts. Stale terminal-only metadata (completed_at,
        failure class, retryability, remediation) is cleared in the same atomic
        transition; first-start history stays on the logical run's started_at
        and on the earlier append-only attempt rows. When retry_accepted is
        set, the acceptance audit commits inside this same transaction, so it
        can never claim acceptance without a claimed attempt.
        """
        placeholders = ",".join("?" for _ in expected_states)
        with self.transaction() as connection:
            self._fault("claim_attempt")
            cursor = connection.execute(
                f"UPDATE worker_runs SET state = 'running', attempt_count = attempt_count + 1,"
                f" started_at = COALESCE(started_at, ?), completed_at = NULL, updated_at = ?,"
                f" failure_class = NULL, retryable = NULL, remediation = NULL,"
                f" row_version = row_version + 1"
                f" WHERE run_id = ? AND state IN ({placeholders})"
                f" AND cancel_requested = 0 AND attempt_count < max_attempts"
                f" AND NOT EXISTS (SELECT 1 FROM shadow_occurrences occurrence"
                f" WHERE occurrence.worker_run_id = worker_runs.run_id"
                f" AND occurrence.state <> 'claimed')"
                f" AND NOT EXISTS (SELECT 1 FROM worker_runs active"
                f" WHERE active.state = 'running' AND active.run_id <> ?)",
                (now, now, run_id, *expected_states, run_id),
            )
            if cursor.rowcount != 1:
                return None
            run = connection.execute(
                "SELECT * FROM worker_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            attempt_id = self.next_id(connection, "wattempt")
            correlation_id = self.next_id(connection, "wcorr")
            connection.execute(
                "INSERT INTO worker_attempts (attempt_id, run_id, attempt_number, started_at,"
                " starting_state, worker_version, timeout_seconds, audit_correlation_id)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (
                    attempt_id,
                    run_id,
                    run["attempt_count"],
                    now,
                    "running",
                    worker_version,
                    run["timeout_seconds"],
                    correlation_id,
                ),
            )
            if retry_accepted:
                self.insert_audit(
                    connection,
                    run_id=run_id,
                    event_type="retry_accepted",
                    actor=actor,
                    business_unit=run["business_unit"],
                    correlation_id=correlation_id,
                    safe_status=f"attempt {run['attempt_count']} of {run['max_attempts']}",
                    recorded_at=now,
                )
            self.insert_audit(
                connection,
                run_id=run_id,
                event_type="attempt_started",
                actor=actor,
                business_unit=run["business_unit"],
                correlation_id=correlation_id,
                safe_status=f"attempt {run['attempt_count']} of {run['max_attempts']}",
                recorded_at=now,
            )
            return {
                "attempt_id": attempt_id,
                "attempt_number": run["attempt_count"],
                "correlation_id": correlation_id,
            }

    def commit_success(
        self,
        run_id: str,
        *,
        attempt_number: int,
        actor: str,
        correlation_id: str,
        output: dict[str, Any],
        allowed_reviewers: list[str],
        now: str,
    ) -> dict[str, Any] | None:
        """Atomically persist output, attempt completion, run success, the review
        task, and the audit trail. Returns None when cancellation already won.
        """
        snapshot = canonical_json(output["result_snapshot"], limit=MAX_SNAPSHOT_BYTES, label="Result snapshot")
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE worker_runs SET state = 'succeeded', completed_at = ?, updated_at = ?,"
                " actual_cost_usd = ?, row_version = row_version + 1"
                " WHERE run_id = ? AND state = 'running' AND cancel_requested = 0",
                (now, now, output["estimated_cost_usd"], run_id),
            )
            if cursor.rowcount != 1:
                return None
            run = connection.execute(
                "SELECT * FROM worker_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            self._fault("insert_output")
            output_id = self.next_id(connection, "woutput")
            connection.execute(
                "INSERT INTO worker_outputs (output_id, run_id, attempt_number, business_unit,"
                " campaign_family_id, campaign_version, skill_id, skill_version, output_schema,"
                " content_hash, byte_length, fixture_source_ids, result_ids, estimated_cost_usd,"
                " errors, stop_reason, result_snapshot, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    output_id,
                    run_id,
                    attempt_number,
                    run["business_unit"],
                    run["campaign_family_id"],
                    run["campaign_version"],
                    run["skill_id"],
                    run["skill_version"],
                    output["output_schema"],
                    output["content_hash"],
                    output["byte_length"],
                    json.dumps(output["fixture_source_ids"]),
                    json.dumps(output["result_ids"]),
                    output["estimated_cost_usd"],
                    json.dumps(output["errors"]),
                    output["stop_reason"],
                    snapshot,
                    now,
                ),
            )
            connection.execute(
                "UPDATE worker_attempts SET completed_at = ?, terminal_state = 'succeeded',"
                " outcome = 'succeeded', estimated_cost_usd = ?, output_hash = ?, retryable = 0"
                " WHERE run_id = ? AND attempt_number = ?",
                (now, output["estimated_cost_usd"], output["content_hash"], run_id, attempt_number),
            )
            self._fault("insert_review_task")
            task_id = self.next_id(connection, "wreview")
            connection.execute(
                "INSERT INTO review_tasks (task_id, run_id, output_id, business_unit, state,"
                " allowed_reviewers, created_at) VALUES (?,?,?,?, 'pending_review', ?, ?)",
                (task_id, run_id, output_id, run["business_unit"], json.dumps(sorted(allowed_reviewers)), now),
            )
            connection.execute(
                "UPDATE worker_runs SET output_id = ?, review_task_id = ? WHERE run_id = ?",
                (output_id, task_id, run_id),
            )
            for event_type, safe_status in (
                ("attempt_succeeded", f"attempt {attempt_number}"),
                ("output_committed", output["content_hash"][:16]),
                ("review_task_created", task_id),
            ):
                self.insert_audit(
                    connection,
                    run_id=run_id,
                    event_type=event_type,
                    actor=actor,
                    business_unit=run["business_unit"],
                    correlation_id=correlation_id,
                    safe_status=safe_status,
                    recorded_at=now,
                )
            return {"output_id": output_id, "review_task_id": task_id}

    def commit_failure(
        self,
        run_id: str,
        *,
        attempt_number: int,
        terminal_state: str,
        failure_class: str,
        retryable: bool,
        remediation: str,
        event_type: str,
        actor: str,
        correlation_id: str,
        now: str,
        estimated_cost_usd: int | None = None,
    ) -> bool:
        if terminal_state not in RUN_STATES or terminal_state in {"queued", "running", "succeeded"}:
            raise MissionControlError(500, "Unknown terminal worker state.")
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE worker_runs SET state = ?, completed_at = ?, updated_at = ?,"
                " failure_class = ?, retryable = ?, remediation = ?,"
                " actual_cost_usd = COALESCE(?, actual_cost_usd), row_version = row_version + 1"
                " WHERE run_id = ? AND state = 'running'",
                (
                    terminal_state,
                    now,
                    now,
                    failure_class,
                    int(retryable),
                    remediation,
                    estimated_cost_usd,
                    run_id,
                ),
            )
            if cursor.rowcount != 1:
                return False
            run = connection.execute(
                "SELECT * FROM worker_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            connection.execute(
                "UPDATE worker_attempts SET completed_at = ?, terminal_state = ?, outcome = ?,"
                " failure_class = ?, retryable = ?,"
                " estimated_cost_usd = COALESCE(?, estimated_cost_usd)"
                " WHERE run_id = ? AND attempt_number = ?",
                (
                    now,
                    terminal_state,
                    failure_class,
                    failure_class,
                    int(retryable),
                    estimated_cost_usd,
                    run_id,
                    attempt_number,
                ),
            )
            self.insert_audit(
                connection,
                run_id=run_id,
                event_type=event_type,
                actor=actor,
                business_unit=run["business_unit"],
                correlation_id=correlation_id,
                safe_status=failure_class,
                recorded_at=now,
            )
            return True

    def cancel_queued(self, run_id: str, *, actor: str, now: str) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE worker_runs SET state = 'cancelled', cancel_requested = 1,"
                " completed_at = ?, updated_at = ?, failure_class = 'cancelled', retryable = 0,"
                " remediation = 'Create a new manual run with a new idempotency key if needed.',"
                " row_version = row_version + 1 WHERE run_id = ? AND state = 'queued'",
                (now, now, run_id),
            )
            if cursor.rowcount != 1:
                return False
            run = connection.execute(
                "SELECT business_unit FROM worker_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            correlation_id = self.next_id(connection, "wcorr")
            for event_type in ("cancellation_requested", "cancellation_completed"):
                self.insert_audit(
                    connection,
                    run_id=run_id,
                    event_type=event_type,
                    actor=actor,
                    business_unit=run["business_unit"],
                    correlation_id=correlation_id,
                    safe_status="cancelled before execution",
                    recorded_at=now,
                )
            return True

    def request_running_cancellation(self, run_id: str, *, actor: str, now: str) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE worker_runs SET cancel_requested = 1, updated_at = ?,"
                " row_version = row_version + 1"
                " WHERE run_id = ? AND state = 'running' AND cancel_requested = 0",
                (now, run_id),
            )
            if cursor.rowcount != 1:
                return False
            run = connection.execute(
                "SELECT business_unit FROM worker_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            self.insert_audit(
                connection,
                run_id=run_id,
                event_type="cancellation_requested",
                actor=actor,
                business_unit=run["business_unit"],
                correlation_id=self.next_id(connection, "wcorr"),
                safe_status="cooperative cancellation requested",
                recorded_at=now,
            )
            return True

    def complete_cancellation(
        self, run_id: str, *, attempt_number: int, actor: str, correlation_id: str, now: str
    ) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE worker_runs SET state = 'cancelled', completed_at = ?, updated_at = ?,"
                " failure_class = 'cancelled', retryable = 0,"
                " remediation = 'Create a new manual run with a new idempotency key if needed.',"
                " row_version = row_version + 1 WHERE run_id = ? AND state = 'running'",
                (now, now, run_id),
            )
            if cursor.rowcount != 1:
                return False
            run = connection.execute(
                "SELECT business_unit FROM worker_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            connection.execute(
                "UPDATE worker_attempts SET completed_at = ?, terminal_state = 'cancelled',"
                " outcome = 'cancelled', failure_class = 'cancelled', retryable = 0"
                " WHERE run_id = ? AND attempt_number = ?",
                (now, run_id, attempt_number),
            )
            self.insert_audit(
                connection,
                run_id=run_id,
                event_type="cancellation_completed",
                actor=actor,
                business_unit=run["business_unit"],
                correlation_id=correlation_id,
                safe_status="cooperative cancellation completed",
                recorded_at=now,
            )
            return True

    def recover_interrupted(self, *, now: str) -> list[str]:
        """Reconcile runs abandoned in running state by a prior process exit."""
        recovered: list[str] = []
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT run_id, attempt_count FROM worker_runs WHERE state = 'running' ORDER BY run_id"
            ).fetchall()
        finally:
            connection.close()
        for row in rows:
            with self.transaction() as connection:
                cursor = connection.execute(
                    "UPDATE worker_runs SET state = 'failed_retryable', updated_at = ?,"
                    " cancel_requested = 0,"
                    " failure_class = 'interrupted_execution_recovered', retryable = 1,"
                    " remediation = 'A prior process exit interrupted this attempt."
                    " Review the run and retry manually if the budget remains.',"
                    " row_version = row_version + 1 WHERE run_id = ? AND state = 'running'",
                    (now, row["run_id"]),
                )
                if cursor.rowcount != 1:
                    continue
                run = connection.execute(
                    "SELECT business_unit FROM worker_runs WHERE run_id = ?", (row["run_id"],)
                ).fetchone()
                connection.execute(
                    "UPDATE worker_attempts SET completed_at = ?, terminal_state = 'failed_retryable',"
                    " outcome = 'interrupted', failure_class = 'interrupted_execution_recovered',"
                    " retryable = 1 WHERE run_id = ? AND attempt_number = ? AND completed_at IS NULL",
                    (now, row["run_id"], row["attempt_count"]),
                )
                self.insert_audit(
                    connection,
                    run_id=row["run_id"],
                    event_type="startup_interruption_recovered",
                    actor="system-startup-recovery",
                    business_unit=run["business_unit"],
                    correlation_id=self.next_id(connection, "wcorr"),
                    safe_status="interrupted attempt reconciled; manual retry required",
                    recorded_at=now,
                )
                recovered.append(row["run_id"])
        return recovered

    def attempts_for(self, run_id: str) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM worker_attempts WHERE run_id = ? ORDER BY attempt_number", (run_id,)
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def get_output(self, run_id: str) -> dict[str, Any] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM worker_outputs WHERE run_id = ?", (run_id,)
            ).fetchone()
        finally:
            connection.close()
        if not row:
            return None
        return self._decode_output_row(row)

    @staticmethod
    def _decode_output_row(row: sqlite3.Row) -> dict[str, Any]:
        output = dict(row)
        snapshot = output["result_snapshot"]
        if not isinstance(snapshot, str):
            raise MissionControlError(500, "Stored result snapshot failed its integrity check.")
        snapshot_bytes = snapshot.encode("utf-8")
        if (
            type(output["byte_length"]) is not int
            or not 0 <= output["byte_length"] <= MAX_SNAPSHOT_BYTES
            or len(snapshot_bytes) != output["byte_length"]
            or hashlib.sha256(snapshot_bytes).hexdigest() != output["content_hash"]
        ):
            raise MissionControlError(500, "Stored result snapshot failed its integrity check.")
        output["fixture_source_ids"] = decoded_list(output["fixture_source_ids"], "fixture source ids")
        output["result_ids"] = decoded_list(output["result_ids"], "result ids")
        output["errors"] = decoded_list(output["errors"], "errors")
        try:
            output["result_snapshot"] = json.loads(snapshot)
        except (json.JSONDecodeError, TypeError, UnicodeError) as exc:
            raise MissionControlError(500, "Stored result snapshot has an unexpected shape.") from exc
        if not isinstance(output["result_snapshot"], list):
            raise MissionControlError(500, "Stored result snapshot has an unexpected shape.")
        if any(not isinstance(item, dict) for item in output["result_snapshot"]):
            raise MissionControlError(500, "Stored result snapshot has an unexpected shape.")
        return output

    def list_review_tasks(self, business_units: set[str]) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            rows = connection.execute("SELECT * FROM review_tasks ORDER BY task_id").fetchall()
        finally:
            connection.close()
        tasks = []
        for row in rows:
            if row["business_unit"] not in business_units:
                continue
            task = dict(row)
            task["allowed_reviewers"] = decoded_list(task["allowed_reviewers"], "allowed reviewers")
            tasks.append(task)
        return tasks

    def get_review_task(self, task_id: str) -> dict[str, Any] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM review_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        finally:
            connection.close()
        if not row:
            return None
        task = dict(row)
        task["allowed_reviewers"] = decoded_list(task["allowed_reviewers"], "allowed reviewers")
        return task

    def audits_for(self, run_id: str) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM audit_events WHERE run_id = ? ORDER BY audit_id", (run_id,)
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    # --- Phase 5 shadow schedules ----------------------------------------

    @staticmethod
    def _occurrence_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        if item.get("history_snapshot"):
            item["history"] = json.loads(item["history_snapshot"])
        item.pop("history_snapshot", None)
        return item

    def _insert_schedule_audit(
        self,
        connection: sqlite3.Connection,
        *,
        schedule_id: str,
        occurrence_id: str | None,
        event_type: str,
        actor: str,
        business_unit: str,
        safe_status: str,
        now: str,
    ) -> str:
        self._fault("insert_shadow_audit")
        audit_id = self.next_id(connection, "saudit")
        connection.execute(
            "INSERT INTO shadow_schedule_audits"
            " (audit_id,schedule_id,occurrence_id,event_type,actor,business_unit,safe_status,recorded_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (audit_id, schedule_id, occurrence_id, event_type, actor, business_unit, safe_status, now),
        )
        return audit_id

    def create_shadow_schedule(self, fields: dict[str, Any], *, now: str) -> dict[str, Any]:
        with self.transaction() as connection:
            schedule_id = self.next_id(connection, "schedule")
            version = 1
            connection.execute(
                "INSERT INTO shadow_schedule_versions"
                " (schedule_id,version,business_unit,name,created_by,created_at,weekday,utc_hour,"
                " utc_minute,prospect_cap,cost_cap_usd,open_discovery_every,configuration_hash)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    schedule_id, version, fields["business_unit"], fields["name"], fields["created_by"],
                    now, fields["weekday"], fields["utc_hour"], fields["utc_minute"],
                    fields["prospect_cap"], 0, fields["open_discovery_every"], fields["configuration_hash"],
                ),
            )
            for position, campaign in enumerate(fields["campaigns"]):
                snapshot = canonical_json(
                    campaign["configuration"], limit=MAX_CONFIG_BYTES, label="Schedule campaign snapshot"
                )
                connection.execute(
                    "INSERT INTO shadow_schedule_campaigns"
                    " (schedule_id,schedule_version,position,campaign_family_id,campaign_version,"
                    " discovery_scope,configuration_snapshot,configuration_hash) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        schedule_id, version, position, campaign["family_id"], campaign["version"],
                        campaign["configuration"]["discovery_scope"], snapshot, campaign["configuration_hash"],
                    ),
                )
            connection.execute(
                "INSERT INTO shadow_schedules"
                " (schedule_id,business_unit,current_version,state,next_due_at,occurrence_ordinal,health,"
                " created_at,updated_at,row_version) VALUES (?,?,?,'disabled',NULL,0,'not_run',?,?,1)",
                (schedule_id, fields["business_unit"], version, now, now),
            )
            self._insert_schedule_audit(
                connection, schedule_id=schedule_id, occurrence_id=None,
                event_type="schedule_created", actor=fields["created_by"],
                business_unit=fields["business_unit"], safe_status="disabled", now=now,
            )
        item = self.get_shadow_schedule(schedule_id)
        assert item is not None
        return item

    def get_shadow_schedule(self, schedule_id: str) -> dict[str, Any] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT s.*,v.name,v.created_by,v.weekday,v.utc_hour,v.utc_minute,v.prospect_cap,"
                " v.cost_cap_usd,v.open_discovery_every,v.configuration_hash,"
                " (SELECT o.duplicate_rate FROM shadow_occurrences o"
                "  WHERE o.schedule_id=s.schedule_id AND o.duplicate_rate IS NOT NULL"
                "  ORDER BY o.scheduled_for DESC,o.occurrence_id DESC LIMIT 1) AS duplicate_rate"
                " FROM shadow_schedules s JOIN shadow_schedule_versions v"
                " ON v.schedule_id=s.schedule_id AND v.version=s.current_version"
                " WHERE s.schedule_id=?", (schedule_id,),
            ).fetchone()
            if not row:
                return None
            campaigns = connection.execute(
                "SELECT * FROM shadow_schedule_campaigns WHERE schedule_id=? AND schedule_version=?"
                " ORDER BY position", (schedule_id, row["current_version"]),
            ).fetchall()
        finally:
            connection.close()
        item = dict(row)
        item["campaigns"] = []
        for campaign in campaigns:
            value = dict(campaign)
            value["configuration"] = json.loads(value.pop("configuration_snapshot"))
            item["campaigns"].append(value)
        return item

    def list_shadow_schedules(self, business_units: set[str]) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            ids = [row["schedule_id"] for row in connection.execute(
                "SELECT schedule_id FROM shadow_schedules WHERE business_unit IN ({}) ORDER BY schedule_id".format(
                    ",".join("?" for _ in business_units)
                ), tuple(sorted(business_units)),
            ).fetchall()] if business_units else []
        finally:
            connection.close()
        return [item for schedule_id in ids if (item := self.get_shadow_schedule(schedule_id))]

    def transition_shadow_schedule(
        self, schedule_id: str, *, expected_version: int, expected_states: tuple[str, ...],
        new_state: str, next_due_at: str | None, actor: str, now: str,
    ) -> dict[str, Any] | None:
        placeholders = ",".join("?" for _ in expected_states)
        health = {"enabled": "not_run", "paused": "paused", "disabled": "disabled"}[new_state]
        with self.transaction() as connection:
            cursor = connection.execute(
                f"UPDATE shadow_schedules SET state=?,next_due_at=?,health=?,updated_at=?,"
                f" row_version=row_version+1 WHERE schedule_id=? AND row_version=?"
                f" AND state IN ({placeholders})",
                (new_state, next_due_at, health, now, schedule_id, expected_version, *expected_states),
            )
            if cursor.rowcount != 1:
                return None
            row = connection.execute(
                "SELECT business_unit FROM shadow_schedules WHERE schedule_id=?", (schedule_id,)
            ).fetchone()
            self._insert_schedule_audit(
                connection, schedule_id=schedule_id, occurrence_id=None,
                event_type=f"schedule_{'resumed' if new_state == 'enabled' and 'paused' in expected_states else new_state}",
                actor=actor, business_unit=row["business_unit"], safe_status=new_state, now=now,
            )
        return self.get_shadow_schedule(schedule_id)

    def due_shadow_schedule(self, now: str) -> dict[str, Any] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT schedule_id FROM shadow_schedules"
                " WHERE state='enabled' AND next_due_at IS NOT NULL AND next_due_at<=?"
                " ORDER BY next_due_at,schedule_id LIMIT 1", (now,),
            ).fetchone()
        finally:
            connection.close()
        return self.get_shadow_schedule(row["schedule_id"]) if row else None

    @staticmethod
    def _rotation_campaign(schedule: dict[str, Any], ordinal: int) -> dict[str, Any]:
        campaigns = schedule["campaigns"]
        opens = [item for item in campaigns if item["discovery_scope"] == "open"]
        filtered = [item for item in campaigns if item["discovery_scope"] == "filtered"]
        every = schedule["open_discovery_every"]
        if every and ordinal % every == 0:
            return opens[(ordinal // every - 1) % len(opens)]
        pool = filtered or opens
        non_open_before = ordinal - (ordinal // every if every else 0)
        return pool[(non_open_before - 1) % len(pool)]

    def claim_shadow_occurrence(
        self, schedule_id: str, *, expected_row_version: int, scheduled_for: str,
        next_due_at: str, idempotency_key: str, actor: str, now: str,
    ) -> dict[str, Any] | None:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM shadow_schedules WHERE schedule_id=? AND state='enabled'"
                " AND row_version=? AND next_due_at=?", (schedule_id, expected_row_version, scheduled_for),
            ).fetchone()
            if not row:
                return None
            schedule = self.get_shadow_schedule(schedule_id)
            assert schedule is not None
            ordinal = row["occurrence_ordinal"] + 1
            campaign = self._rotation_campaign(schedule, ordinal)
            occurrence_id = self.next_id(connection, "occurrence")
            opportunity_key = "|".join((
                row["business_unit"], campaign["campaign_family_id"],
                str(campaign["campaign_version"]), scheduled_for,
            ))
            conflict = connection.execute(
                "SELECT occurrence_id FROM shadow_occurrences WHERE opportunity_key=?", (opportunity_key,)
            ).fetchone()
            state = "blocked" if conflict else "claimed"
            failure_class = "overlap_prevented" if conflict else None
            stop_reason = "A concurrent shadow occurrence already claimed this opportunity." if conflict else None
            connection.execute(
                "INSERT INTO shadow_occurrences"
                " (occurrence_id,schedule_id,schedule_version,business_unit,scheduled_for,ordinal,"
                " campaign_family_id,campaign_version,discovery_scope,idempotency_key,opportunity_key,"
                " state,failure_class,stop_reason,claimed_at,completed_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    occurrence_id, schedule_id, row["current_version"], row["business_unit"], scheduled_for,
                    ordinal, campaign["campaign_family_id"], campaign["campaign_version"],
                    campaign["discovery_scope"], idempotency_key, None if conflict else opportunity_key,
                    state, failure_class, stop_reason, now, now if conflict else None,
                ),
            )
            connection.execute(
                "UPDATE shadow_schedules SET occurrence_ordinal=?,next_due_at=?,updated_at=?,"
                " row_version=row_version+1 WHERE schedule_id=?",
                (ordinal, next_due_at, now, schedule_id),
            )
            self._insert_schedule_audit(
                connection, schedule_id=schedule_id, occurrence_id=occurrence_id,
                event_type="occurrence_blocked" if conflict else "occurrence_claimed", actor=actor,
                business_unit=row["business_unit"], safe_status=state, now=now,
            )
            if conflict:
                self._insert_shadow_alert(
                    connection, schedule_id=schedule_id, occurrence_id=occurrence_id,
                    business_unit=row["business_unit"], failure_class=failure_class,
                    safe_message=stop_reason, now=now,
                )
        return self.get_shadow_occurrence(occurrence_id)

    def _insert_shadow_alert(
        self, connection: sqlite3.Connection, *, schedule_id: str, occurrence_id: str | None,
        business_unit: str, failure_class: str, safe_message: str, now: str,
    ) -> str:
        alert_id = self.next_id(connection, "salert")
        connection.execute(
            "INSERT INTO shadow_alerts"
            " (alert_id,schedule_id,occurrence_id,business_unit,failure_class,safe_message,created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (alert_id, schedule_id, occurrence_id, business_unit, failure_class, safe_message[:240], now),
        )
        return alert_id

    def get_shadow_occurrence(self, occurrence_id: str) -> dict[str, Any] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM shadow_occurrences WHERE occurrence_id=?", (occurrence_id,)
            ).fetchone()
        finally:
            connection.close()
        return self._occurrence_row(row) if row else None

    def list_shadow_occurrences(self, business_units: set[str]) -> list[dict[str, Any]]:
        if not business_units:
            return []
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM shadow_occurrences WHERE business_unit IN ({})"
                " ORDER BY scheduled_for DESC,occurrence_id".format(",".join("?" for _ in business_units)),
                tuple(sorted(business_units)),
            ).fetchall()
        finally:
            connection.close()
        return [self._occurrence_row(row) for row in rows]

    def set_shadow_history(self, occurrence_id: str, *, history: dict[str, Any], history_hash: str) -> None:
        snapshot = canonical_json(history, limit=MAX_SNAPSHOT_BYTES, label="History snapshot")
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE shadow_occurrences SET history_snapshot=?,history_hash=?"
                " WHERE occurrence_id=? AND state='claimed' AND history_snapshot IS NULL",
                (snapshot, history_hash, occurrence_id),
            )
            if cursor.rowcount != 1:
                raise MissionControlError(409, "The shadow occurrence history could not be recorded.")

    def link_shadow_run(self, occurrence_id: str, run_id: str) -> None:
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE shadow_occurrences SET worker_run_id=?"
                " WHERE occurrence_id=? AND state='claimed' AND worker_run_id IS NULL"
                " AND EXISTS (SELECT 1 FROM worker_runs worker WHERE worker.run_id=?"
                " AND worker.business_unit=shadow_occurrences.business_unit"
                " AND worker.campaign_family_id=shadow_occurrences.campaign_family_id"
                " AND worker.campaign_version=shadow_occurrences.campaign_version"
                " AND worker.idempotency_key=shadow_occurrences.idempotency_key)",
                (run_id, occurrence_id, run_id),
            )
            if cursor.rowcount != 1:
                existing = connection.execute(
                    "SELECT worker_run_id FROM shadow_occurrences WHERE occurrence_id=?", (occurrence_id,)
                ).fetchone()
                if not existing or existing["worker_run_id"] != run_id:
                    raise MissionControlError(409, "The shadow occurrence run link conflicts.")

    def shadow_occurrence_for_run(self, run_id: str) -> dict[str, Any] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT occurrence_id,state FROM shadow_occurrences WHERE worker_run_id=?",
                (run_id,),
            ).fetchone()
        finally:
            connection.close()
        return dict(row) if row else None

    def shadow_context_for_run(self, run_id: str) -> dict[str, Any] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT o.history_snapshot,o.history_hash,v.prospect_cap"
                " FROM shadow_occurrences o JOIN shadow_schedule_versions v"
                " ON v.schedule_id=o.schedule_id AND v.version=o.schedule_version"
                " WHERE o.worker_run_id=?", (run_id,),
            ).fetchone()
        finally:
            connection.close()
        if not row:
            return None
        return {
            "history": json.loads(row["history_snapshot"]),
            "history_hash": row["history_hash"],
            "prospect_cap": row["prospect_cap"],
        }

    def _invalidate_shadow_output(
        self, connection: sqlite3.Connection, *, run_id: str, business_unit: str, now: str,
    ) -> None:
        connection.execute(
            "UPDATE worker_runs SET state='failed_terminal',failure_class='shadow_output_invalid',"
            " retryable=0,remediation='Inspect the local state integrity before creating new work.',"
            " updated_at=?,row_version=row_version+1 WHERE run_id=? AND state='succeeded'",
            (now, run_id),
        )
        connection.execute(
            "UPDATE review_tasks SET state='invalidated' WHERE run_id=? AND state='pending_review'",
            (run_id,),
        )
        self.insert_audit(
            connection, run_id=run_id, event_type="shadow_output_invalidated",
            actor="system-startup-recovery", business_unit=business_unit,
            correlation_id=self.next_id(connection, "wcorr"),
            safe_status="shadow_output_invalid", recorded_at=now,
        )

    def finish_shadow_occurrence(
        self, occurrence_id: str, *, state: str, failure_class: str | None,
        stop_reason: str, result_count: int | None, duplicate_count: int | None,
        duplicate_rate: float | None, actor: str, now: str,
    ) -> dict[str, Any]:
        with self.transaction() as connection:
            occurrence = connection.execute(
                "SELECT * FROM shadow_occurrences WHERE occurrence_id=? AND state='claimed'",
                (occurrence_id,),
            ).fetchone()
            if not occurrence:
                current = self.get_shadow_occurrence(occurrence_id)
                if current is None:
                    raise MissionControlError(404, "Shadow occurrence not found.")
                return current
            if failure_class == "shadow_output_invalid" and occurrence["worker_run_id"]:
                self._invalidate_shadow_output(
                    connection, run_id=occurrence["worker_run_id"],
                    business_unit=occurrence["business_unit"], now=now,
                )
            connection.execute(
                "UPDATE shadow_occurrences SET state=?,failure_class=?,stop_reason=?,result_count=?,"
                " duplicate_count=?,duplicate_rate=?,completed_at=? WHERE occurrence_id=?",
                (state, failure_class, stop_reason[:240], result_count, duplicate_count, duplicate_rate, now, occurrence_id),
            )
            health = "healthy" if state == "completed" else "unhealthy"
            connection.execute(
                "UPDATE shadow_schedules SET health=?,last_stop_reason=?,updated_at=?,"
                " row_version=row_version+1 WHERE schedule_id=?",
                (health, stop_reason[:240], now, occurrence["schedule_id"]),
            )
            self._insert_schedule_audit(
                connection, schedule_id=occurrence["schedule_id"], occurrence_id=occurrence_id,
                event_type=f"occurrence_{state}", actor=actor,
                business_unit=occurrence["business_unit"], safe_status=state, now=now,
            )
            if state != "completed":
                self._insert_shadow_alert(
                    connection, schedule_id=occurrence["schedule_id"], occurrence_id=occurrence_id,
                    business_unit=occurrence["business_unit"], failure_class=failure_class or "shadow_failure",
                    safe_message=stop_reason, now=now,
                )
        item = self.get_shadow_occurrence(occurrence_id)
        assert item is not None
        return item

    def recover_shadow_occurrences(self, *, now: str) -> list[str]:
        """Close occurrence claims interrupted by a previous local process.

        Phase 4 startup recovery has already converted any interrupted worker
        attempt to a retryable terminal fact. If its durable output committed
        first, preserve that success; otherwise fail closed with a local alert.
        """
        recovered: list[str] = []
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT o.* FROM shadow_occurrences o"
                " WHERE o.state='claimed' ORDER BY o.occurrence_id"
            ).fetchall()
            for row in rows:
                worker_run_id = row["worker_run_id"]
                worker = None
                if worker_run_id:
                    worker = connection.execute(
                        "SELECT run_id,state FROM worker_runs WHERE run_id=?", (worker_run_id,)
                    ).fetchone()
                output = None
                if worker_run_id:
                    output = connection.execute(
                        "SELECT * FROM worker_outputs WHERE run_id=?",
                        (worker_run_id,),
                    ).fetchone()
                completed = worker is not None and worker["state"] == "succeeded" and output is not None
                if completed:
                    try:
                        decoded = self._decode_output_row(output)
                        result_count, duplicate_count, duplicate_rate = shadow_result_metrics(
                            decoded["result_snapshot"]
                        )
                    except MissionControlError:
                        completed = False
                        state = "failed"
                        failure_class = "shadow_output_invalid"
                        stop_reason = "The recovered shadow output failed its integrity check."
                        result_count = duplicate_count = duplicate_rate = None
                        self._invalidate_shadow_output(
                            connection, run_id=worker_run_id,
                            business_unit=row["business_unit"], now=now,
                        )
                    else:
                        state = "completed"
                        failure_class = None
                        stop_reason = decoded["stop_reason"]
                else:
                    state = "failed"
                    failure_class = "interrupted_shadow_recovered"
                    stop_reason = "An interrupted local shadow occurrence was recovered without partial output."
                    result_count = duplicate_count = duplicate_rate = None
                connection.execute(
                    "UPDATE shadow_occurrences SET state=?,failure_class=?,stop_reason=?,result_count=?,"
                    " duplicate_count=?,duplicate_rate=?,completed_at=? WHERE occurrence_id=? AND state='claimed'",
                    (
                        state, failure_class, stop_reason, result_count, duplicate_count,
                        duplicate_rate, now, row["occurrence_id"],
                    ),
                )
                connection.execute(
                    "UPDATE shadow_schedules SET health=?,last_stop_reason=?,updated_at=?,"
                    " row_version=row_version+1 WHERE schedule_id=?",
                    ("healthy" if completed else "unhealthy", stop_reason, now, row["schedule_id"]),
                )
                self._insert_schedule_audit(
                    connection, schedule_id=row["schedule_id"], occurrence_id=row["occurrence_id"],
                    event_type="occurrence_recovered_completed" if completed else "occurrence_recovered_failed",
                    actor="system-startup-recovery", business_unit=row["business_unit"],
                    safe_status=state, now=now,
                )
                if not completed:
                    self._insert_shadow_alert(
                        connection, schedule_id=row["schedule_id"], occurrence_id=row["occurrence_id"],
                        business_unit=row["business_unit"], failure_class=failure_class,
                        safe_message=stop_reason, now=now,
                    )
                recovered.append(row["occurrence_id"])
        return recovered

    def shadow_schedule_audits(self, schedule_id: str) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM shadow_schedule_audits WHERE schedule_id=? ORDER BY audit_id",
                (schedule_id,),
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def list_shadow_alerts(self, business_units: set[str]) -> list[dict[str, Any]]:
        if not business_units:
            return []
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM shadow_alerts WHERE business_unit IN ({})"
                " ORDER BY created_at DESC,alert_id".format(",".join("?" for _ in business_units)),
                tuple(sorted(business_units)),
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def successful_outputs_for_business_unit(self, business_unit: str) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT o.* FROM worker_outputs o JOIN worker_runs r ON r.run_id=o.run_id"
                " WHERE r.business_unit=? AND r.state='succeeded'"
                " ORDER BY r.completed_at,r.run_id",
                (business_unit,),
            ).fetchall()
        finally:
            connection.close()
        total_bytes = 0
        outputs = []
        for row in rows:
            total_bytes += row["byte_length"] if type(row["byte_length"]) is int else MAX_SNAPSHOT_BYTES + 1
            if total_bytes > MAX_SNAPSHOT_BYTES:
                raise MissionControlError(500, "Stored history output set exceeds its bounded size.")
            outputs.append(self._decode_output_row(row))
        return outputs

    def integrity_report(self) -> tuple[str, list[Any]]:
        connection = self._connect()
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        finally:
            connection.close()
        return integrity, [tuple(row) for row in foreign_keys]

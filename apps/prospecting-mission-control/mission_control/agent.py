"""Phase 4 registered prospecting agent with Phase 5 control-plane reuse.

One locally registered worker executes the existing Phase 3 deterministic
fixture adapter behind a durable, bounded control plane. Direct worker control
remains manual; Phase 5 may submit one occurrence from an explicitly enabled
local schedule. The worker itself has no scheduler, network client, creative,
likeness, or outreach capability.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from .application import (
    ACTOR_SCOPE,
    REPOSITORY_ROOT,
    MissionControlError,
    Repository,
)
from .store import (
    IdempotencyKeyExists,
    MAX_SNAPSHOT_BYTES,
    SqliteStore,
    canonical_json,
    worker_request_fingerprint,
)

# application.py placed the shared deterministic core on sys.path at import.
from common import ValidationError  # noqa: E402
from validate_campaign import validate_campaign  # noqa: E402

AGENT_ID = "brand-prospecting-agent"
AGENT_CONTRACT_VERSION = "1.0.0"
WORKER_RUNTIME_VERSION = "brand-prospecting-agent/1.0.0"
OUTPUT_SCHEMA = "phase3-review-projection@1"
INPUT_SCHEMA = "phase1-campaign-configuration@1"
DEFAULT_TIMEOUT_SECONDS = 10
TIMEOUT_BOUNDS = (1, 30)
COST_CAP_USD = 0
MAX_ATTEMPTS = 3  # one initial execution plus at most two manual retries
MAX_CONCURRENCY = 1
SQLITE_MAX_INTEGER = 2**63 - 1
SCHEDULE_MANAGER = "noah"

# Server-owned business-unit routing. The client can never supply a skill name,
# import path, executable, file path, command, or version.
SKILL_BINDINGS = {
    "unreal-media-group": {
        "skill_id": "unreal-media-brand-prospector",
        "skill_version": "1.0.0-phase1-frozen",
    },
    "unreal-talent": {
        "skill_id": "unreal-talent-campaign-prospector",
        "skill_version": "1.0.0-phase1-frozen",
    },
}

RETRYABLE_CLASSES = {
    "executor_failure",
    "storage_unavailable",
    "transaction_rolled_back",
    "timeout",
    "interrupted_execution_recovered",
}
TERMINAL_CLASSES = {
    "invalid_input",
    "business_unit_mismatch",
    "unsupported_skill_version",
    "cost_limit_exceeded",
    "cancelled",
}


class _DeadlineExceeded(Exception):
    pass


class _CancellationRequested(Exception):
    pass


class WorkerInputError(MissionControlError):
    """A durable replay input failed validation; carries its safe failure class."""

    def __init__(self, status: int, message: str, failure_class: str = "invalid_input"):
        super().__init__(status, message)
        self.failure_class = failure_class


class WorkerExecutor(Protocol):
    """The bounded execution boundary. `checkpoint` must be called between steps."""

    def execute(self, run: dict[str, Any], checkpoint: Callable[[str], None]) -> dict[str, Any]: ...


class FixtureWorkerExecutor:
    """Executes the repository-owned deterministic synthetic fixture adapter.

    Every attempt replays the run's durable validated input — persisted
    configuration snapshot, hash, business-unit binding, exact skill version,
    and integrity reference — so a manual retry works in a fresh process
    without any Phase 3 in-memory campaign, run, idempotency, or prospect
    state. Corrupted or mismatched durable input fails closed.
    """

    def __init__(
        self,
        repository: Repository,
        integrity: Callable[[str], str] | None = None,
        scheduled_context: Callable[[str], dict[str, Any] | None] | None = None,
    ):
        self.repository = repository
        self.integrity = integrity or skill_integrity_hash
        self.scheduled_context = scheduled_context

    def _validate_durable_input(self, run: dict[str, Any]) -> dict[str, Any]:
        config = run["configuration"]
        if not isinstance(config, dict):
            raise WorkerInputError(409, "The durable configuration snapshot has an unexpected shape.")
        serialized = json.dumps(config, sort_keys=True, separators=(",", ":"))
        if hashlib.sha256(serialized.encode("utf-8")).hexdigest() != run["configuration_hash"]:
            raise WorkerInputError(409, "The durable configuration snapshot failed its integrity check.")
        if config.get("business_unit") != run["business_unit"]:
            raise WorkerInputError(409, "The durable business unit does not match the configuration snapshot.")
        binding = SKILL_BINDINGS.get(run["business_unit"])
        if (
            binding is None
            or binding["skill_id"] != run["skill_id"]
            or binding["skill_version"] != run["skill_version"]
        ):
            raise WorkerInputError(
                409,
                "The recorded skill binding is not the server-owned binding for this business unit.",
                failure_class="unsupported_skill_version",
            )
        if self.integrity(binding["skill_id"]) != run["skill_integrity"]:
            raise WorkerInputError(
                409,
                "The reviewed skill content changed after this run was recorded; the run cannot replay.",
                failure_class="unsupported_skill_version",
            )
        try:
            validate_campaign(config, base_dir=REPOSITORY_ROOT)
        except ValidationError as exc:
            raise WorkerInputError(400, str(exc)) from exc
        return config

    def execute(self, run: dict[str, Any], checkpoint: Callable[[str], None]) -> dict[str, Any]:
        checkpoint("validate_durable_input")
        actor = run["initiating_actor"]
        config = self._validate_durable_input(run)
        checkpoint("rehydrate_campaign_version")
        self.repository.ensure_campaign_version(
            actor,
            run["campaign_family_id"],
            run["campaign_version"],
            config,
            run["configuration_hash"],
            run["created_at"],
        )
        checkpoint("execute_fixture_adapter")
        context = self.scheduled_context(run["run_id"]) if self.scheduled_context else None
        if context:
            history = context.get("history")
            serialized_history = json.dumps(history, sort_keys=True, separators=(",", ":"))
            if hashlib.sha256(serialized_history.encode("utf-8")).hexdigest() != context.get("history_hash"):
                raise WorkerInputError(409, "The scheduled history snapshot failed its integrity check.")
            prepared = self.repository.prepare_run(
                actor, run["campaign_family_id"], run["campaign_version"], run["idempotency_key"],
                history=history, prospect_cap=context.get("prospect_cap"),
            )
        else:
            prepared = self.repository.prepare_run(
                actor, run["campaign_family_id"], run["campaign_version"], run["idempotency_key"]
            )
        checkpoint("assemble_result_snapshot")
        fixture_run = prepared.get("existing_run", prepared.get("fixture_run"))
        results = prepared.get("results")
        if results is None:
            results = [
                self.repository.get_prospect(actor, run["business_unit"], prospect_id)
                for prospect_id in fixture_run["output_ids"]
            ]
        return {
            "fixture_run": fixture_run,
            "results": results,
            "estimated_cost_usd": fixture_run["estimated_cost_usd"],
            "process_local_projection": prepared,
        }


def skill_integrity_hash(skill_id: str) -> str:
    """Deterministic manifest hash proving which reviewed skill version ran."""
    skill_root = REPOSITORY_ROOT / ".agents" / "skills" / skill_id
    if not skill_root.is_dir():
        raise MissionControlError(500, "The reviewed skill reference is missing locally.")
    digest = hashlib.sha256()
    for path in sorted(p for p in skill_root.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        digest.update(path.relative_to(skill_root).as_posix().encode("utf-8"))
        digest.update(b"\x00")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _valid_idempotency_key(key: str) -> bool:
    return bool(key) and len(key) <= 100 and all(
        character.isalnum() or character in "_-" for character in key
    )


class RegisteredAgentService:
    """Durable control plane for the single registered prospecting agent."""

    def __init__(
        self,
        repository: Repository,
        store: SqliteStore,
        *,
        clock: Callable[[], datetime],
        executor: WorkerExecutor | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        if not TIMEOUT_BOUNDS[0] <= timeout_seconds <= TIMEOUT_BOUNDS[1]:
            raise MissionControlError(500, "The server-owned timeout is outside its reviewed bounds.")
        self.repository = repository
        self.store = store
        self.clock = clock
        self.timeout_seconds = timeout_seconds
        self._execution_slot = threading.Semaphore(MAX_CONCURRENCY)
        self.executor = executor or FixtureWorkerExecutor(
            repository,
            integrity=self._integrity,
            scheduled_context=self.store.shadow_context_for_run,
        )
        self.recovered_run_ids = self.store.recover_interrupted(now=self._now())

    def _now(self) -> str:
        return self.clock().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _integrity(self, skill_id: str) -> str:
        # Recompute at every governed boundary. A cached manifest could allow a
        # run to execute after reviewed skill content changed in this process.
        return skill_integrity_hash(skill_id)

    def registration(self) -> dict[str, Any]:
        return {
            "agent_id": AGENT_ID,
            "agent_contract_version": AGENT_CONTRACT_VERSION,
            "worker_runtime_version": WORKER_RUNTIME_VERSION,
            "registration_state": "registered and enabled for manual synthetic execution",
            "business_units": sorted(SKILL_BINDINGS),
            "skill_bindings": {
                unit: {
                    **binding,
                    "skill_integrity_sha256": self._integrity(binding["skill_id"]),
                }
                for unit, binding in sorted(SKILL_BINDINGS.items())
            },
            "input_schema": INPUT_SCHEMA,
            "output_schema": OUTPUT_SCHEMA,
            "trigger": "manual human form only",
            "scheduled_shadow_trigger": "explicitly enabled local weekly schedule occurrence only",
            "max_concurrency": MAX_CONCURRENCY,
            "timeout_seconds": self.timeout_seconds,
            "cost_cap_usd": COST_CAP_USD,
            "max_attempts": MAX_ATTEMPTS,
            "cancellation": True,
            "durable_store_adapter": "sqlite-local-v1",
            "credentials": False,
            "scheduler": False,
            "recurring_loop": False,
            "network": False,
            "creative": False,
            "likeness": False,
            "outreach": False,
        }

    def _authorize(self, actor: str, business_unit: str) -> None:
        if actor not in ACTOR_SCOPE:
            raise MissionControlError(403, "Actor is not allowed in this local review surface.")
        if business_unit not in ACTOR_SCOPE[actor]:
            raise MissionControlError(403, "Business-unit access denied.")

    def create_manual_run(
        self, actor: str, family_id: str, version: int, idempotency_key: str,
        *, request_kind: str = "manual", shadow_occurrence_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Create (or idempotently replay) the durable logical run. Returns
        (run, created) where created is False for an idempotent replay."""
        try:
            campaign = self.repository.get_campaign(actor, family_id, version)
            business_unit = campaign["business_unit"]
            self._authorize(actor, business_unit)
            binding = SKILL_BINDINGS.get(business_unit)
            if binding is None:
                raise MissionControlError(409, "No reviewed skill is bound to this business unit.")
            if not _valid_idempotency_key(idempotency_key):
                raise MissionControlError(400, "A bounded alphanumeric idempotency key is required.")
            if request_kind not in {"manual", "scheduled_shadow"}:
                raise MissionControlError(400, "Unknown registered-agent request kind.")
            if request_kind == "scheduled_shadow" and not shadow_occurrence_id:
                raise MissionControlError(409, "A scheduled request requires its claimed occurrence.")
            if request_kind == "scheduled_shadow" and actor != SCHEDULE_MANAGER:
                raise MissionControlError(403, "Noah must create a scheduled shadow run.")
            if request_kind == "manual" and shadow_occurrence_id is not None:
                raise MissionControlError(409, "A manual request cannot link a shadow occurrence.")
        except MissionControlError as exc:
            self.store.record_audit(
                run_id=None,
                event_type=(
                    "shadow_occurrence_rejected"
                    if request_kind == "scheduled_shadow"
                    else "manual_request_rejected"
                ),
                actor=actor if actor in ACTOR_SCOPE else "unknown-actor",
                business_unit=None,
                correlation_id="request-validation",
                safe_status=f"http {exc.status}",
                recorded_at=self._now(),
            )
            raise
        fingerprint = worker_request_fingerprint({
            "agent_id": AGENT_ID,
            "campaign_family_id": family_id,
            "campaign_version": version,
            "business_unit": business_unit,
            "initiating_actor": actor,
            "configuration_hash": campaign["configuration_hash"],
            "skill_id": binding["skill_id"],
            "skill_version": binding["skill_version"],
        }, scheduled=request_kind == "scheduled_shadow")
        existing = self.store.find_run_by_key(idempotency_key)
        if existing is not None:
            return self._resolve_existing_key(actor, business_unit, fingerprint, existing), False
        try:
            run = self.store.create_run(
                {
                    "agent_id": AGENT_ID,
                    "agent_version": AGENT_CONTRACT_VERSION,
                    "campaign_family_id": family_id,
                    "campaign_version": version,
                    "business_unit": business_unit,
                    "initiating_actor": actor,
                    "skill_id": binding["skill_id"],
                    "skill_version": binding["skill_version"],
                    "skill_integrity": self._integrity(binding["skill_id"]),
                    "configuration": campaign["configuration"],
                    "configuration_hash": campaign["configuration_hash"],
                    "idempotency_key": idempotency_key,
                    "request_fingerprint": fingerprint,
                    "max_attempts": MAX_ATTEMPTS,
                    "timeout_seconds": self.timeout_seconds,
                    "cost_cap_usd": COST_CAP_USD,
                    "request_event": (
                        "shadow_occurrence_accepted"
                        if request_kind == "scheduled_shadow"
                        else "manual_request_accepted"
                    ),
                },
                now=self._now(),
                shadow_occurrence_id=shadow_occurrence_id,
            )
        except IdempotencyKeyExists:
            # A concurrent identical or conflicting submission won the durable
            # unique insert; resolve the race as a replay or a safe conflict.
            existing = self.store.find_run_by_key(idempotency_key)
            if existing is None:
                raise MissionControlError(500, "The durable store is briefly inconsistent; retry the request.")
            return self._resolve_existing_key(actor, business_unit, fingerprint, existing), False
        return run, True

    def create_shadow_run(
        self, actor: str, family_id: str, version: int, idempotency_key: str,
        *, occurrence_id: str,
    ) -> tuple[dict[str, Any], bool]:
        """Create a scheduler-owned shadow run through the same governed control plane."""
        run, created = self.create_manual_run(
            actor, family_id, version, idempotency_key,
            request_kind="scheduled_shadow", shadow_occurrence_id=occurrence_id,
        )
        if not created:
            self.store.link_shadow_run(occurrence_id, run["run_id"])
        return run, created

    def _resolve_existing_key(
        self, actor: str, business_unit: str, fingerprint: str, existing: dict[str, Any]
    ) -> dict[str, Any]:
        """Resolve a reused idempotency key. Keys are global by contract, but a
        conflict never appends to, alters, or identifies a run in a business
        unit the actor cannot access."""
        if existing["request_fingerprint"] != fingerprint:
            authorized = existing["business_unit"] in ACTOR_SCOPE.get(actor, set())
            self.store.record_audit(
                run_id=existing["run_id"] if authorized else None,
                event_type="idempotency_conflict",
                actor=actor,
                business_unit=business_unit if not authorized else existing["business_unit"],
                correlation_id="idempotency",
                safe_status="409 idempotency_conflict",
                recorded_at=self._now(),
            )
            raise MissionControlError(409, "idempotency_conflict: the idempotency key was already used with different input.")
        self._authorize(actor, existing["business_unit"])
        self.store.record_audit(
            run_id=existing["run_id"],
            event_type="idempotent_replay",
            actor=actor,
            business_unit=existing["business_unit"],
            correlation_id="idempotency",
            safe_status=existing["state"],
            recorded_at=self._now(),
        )
        return existing

    def get_run(self, actor: str, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        if run is None:
            raise MissionControlError(404, "Worker run not found.")
        self._authorize(actor, run["business_unit"])
        return run

    def list_runs(self, actor: str, business_unit: str) -> list[dict[str, Any]]:
        self._authorize(actor, business_unit)
        return [run for run in self.store.list_runs({business_unit}) if run["business_unit"] == business_unit]

    def run_detail(self, actor: str, run_id: str) -> dict[str, Any]:
        run = self.get_run(actor, run_id)
        run["attempts"] = self.store.attempts_for(run_id)
        run["output"] = self.store.get_output(run_id)
        run["audit_events"] = self.store.audits_for(run_id)
        run["review_task"] = (
            self.store.get_review_task(run["review_task_id"]) if run["review_task_id"] else None
        )
        run["retry_budget_remaining"] = max(0, run["max_attempts"] - run["attempt_count"])
        occurrence = self.store.shadow_occurrence_for_run(run_id)
        run["retry_block_reason"] = (
            "scheduled_run"
            if occurrence is not None
            else None
        )
        if occurrence is not None and run["state"] in {"failed_retryable", "timed_out"}:
            run["retryable"] = False
            run["remediation"] = (
                "The linked occurrence owns final settlement; no manual retry is available."
            )
        run["retry_allowed"] = (
            run["state"] in {"failed_retryable", "timed_out"}
            and run["retry_budget_remaining"] > 0
            and occurrence is None
        )
        run["cancel_allowed"] = run["state"] in {"queued", "running"}
        return run

    def execute_run(self, actor: str, run_id: str) -> dict[str, Any]:
        """Bounded one-shot execution of a queued run in the calling thread."""
        run = self.get_run(actor, run_id)
        return self._attempt(actor, run, expected_states=("queued",))

    def retry_run(self, actor: str, run_id: str) -> dict[str, Any]:
        run = self.get_run(actor, run_id)
        state = run["state"]
        if state == "succeeded":
            raise MissionControlError(409, "The run already succeeded; a retry cannot execute again.")
        if state in {"failed_terminal", "cancelled"}:
            raise MissionControlError(409, "This terminal failure class is not retryable.")
        if state in {"queued", "running"}:
            raise MissionControlError(409, "The run is not in a retryable terminal state.")
        if run["attempt_count"] >= run["max_attempts"]:
            self.store.record_audit(
                run_id=run_id,
                event_type="retry_denied",
                actor=actor,
                business_unit=run["business_unit"],
                correlation_id="retry",
                safe_status="retry budget exhausted",
                recorded_at=self._now(),
            )
            raise MissionControlError(409, "The retry budget is exhausted; no further attempts are allowed.")
        # retry_accepted is audited inside the atomic claim transaction, so a
        # lost claim race can never leave a stale acceptance fact.
        return self._attempt(actor, run, expected_states=("failed_retryable", "timed_out"), retry=True)

    def cancel_run(self, actor: str, run_id: str) -> dict[str, Any]:
        run = self.get_run(actor, run_id)
        now = self._now()
        if run["state"] == "queued" and self.store.cancel_queued(run_id, actor=actor, now=now):
            return self.get_run(actor, run_id)
        if run["state"] == "running" and self.store.request_running_cancellation(run_id, actor=actor, now=now):
            return self.get_run(actor, run_id)
        if run["state"] == "succeeded":
            raise MissionControlError(409, "The run already succeeded; the committed output is preserved.")
        raise MissionControlError(409, "Only queued or running work can be cancelled.")

    def review_tasks(self, actor: str, business_unit: str) -> list[dict[str, Any]]:
        self._authorize(actor, business_unit)
        return self.store.list_review_tasks({business_unit})

    def get_review_task(self, actor: str, task_id: str) -> dict[str, Any]:
        task = self.store.get_review_task(task_id)
        if task is None:
            raise MissionControlError(404, "Review task not found.")
        self._authorize(actor, task["business_unit"])
        return task

    # --- attempt execution -------------------------------------------------

    def _attempt(
        self, actor: str, run: dict[str, Any], *, expected_states: tuple[str, ...], retry: bool = False
    ) -> dict[str, Any]:
        run_id = run["run_id"]
        occurrence = self.store.shadow_occurrence_for_run(run_id)
        if retry and occurrence is not None:
            raise MissionControlError(409, "A scheduled shadow run cannot be retried manually.")
        if occurrence is not None and occurrence["state"] != "claimed":
            raise MissionControlError(
                409,
                "The scheduled occurrence is terminal; its linked worker run cannot execute or retry.",
            )
        if not self._execution_slot.acquire(blocking=False):
            raise MissionControlError(409, "concurrency_conflict: another worker attempt is executing.")
        try:
            claim = self.store.claim_attempt(
                run_id,
                expected_states=expected_states,
                actor=actor,
                worker_version=WORKER_RUNTIME_VERSION,
                now=self._now(),
                retry_accepted=retry,
            )
            if claim is None:
                current = self.store.get_run(run_id)
                state = current["state"] if current else "missing"
                raise MissionControlError(
                    409, f"The run could not be claimed for execution (current state: {state})."
                )
            self._execute_claimed(actor, run_id, claim)
        finally:
            self._execution_slot.release()
        return self.get_run(actor, run_id)

    def _checkpoint_factory(self, run_id: str, deadline: datetime) -> Callable[[str], None]:
        def checkpoint(_step: str) -> None:
            if self.clock() > deadline:
                raise _DeadlineExceeded()
            current = self.store.get_run(run_id)
            if current is None or current["cancel_requested"]:
                raise _CancellationRequested()

        return checkpoint

    def _execute_claimed(self, actor: str, run_id: str, claim: dict[str, Any]) -> None:
        run = self.store.get_run(run_id)
        assert run is not None
        attempt_number = claim["attempt_number"]
        correlation_id = claim["correlation_id"]
        deadline = self.clock() + timedelta(seconds=run["timeout_seconds"])
        checkpoint = self._checkpoint_factory(run_id, deadline)

        def fail(
            terminal_state: str,
            failure_class: str,
            remediation: str,
            *,
            event_type: str = "attempt_failed",
            estimated_cost_usd: int | None = None,
        ) -> None:
            retryable = failure_class in RETRYABLE_CLASSES and run["attempt_count"] < run["max_attempts"]
            committed = self.store.commit_failure(
                run_id,
                attempt_number=attempt_number,
                terminal_state=terminal_state,
                failure_class=failure_class,
                retryable=retryable,
                remediation=remediation,
                event_type=event_type,
                actor=actor,
                correlation_id=correlation_id,
                now=self._now(),
                estimated_cost_usd=estimated_cost_usd,
            )
            if not committed:
                raise MissionControlError(409, "The attempt reached a terminal state in another transition.")

        try:
            result = self.executor.execute(run, checkpoint)
        except _DeadlineExceeded:
            fail(
                "timed_out",
                "timeout",
                "The cooperative deadline elapsed. Retry manually while the retry budget remains.",
                event_type="attempt_timed_out",
            )
            return
        except _CancellationRequested:
            if not self.store.complete_cancellation(
                run_id, attempt_number=attempt_number, actor=actor,
                correlation_id=correlation_id, now=self._now(),
            ):
                raise MissionControlError(409, "Cancellation lost the terminal-state race safely.")
            return
        except WorkerInputError as exc:
            fail("failed_terminal", exc.failure_class, exc.message)
            return
        except MissionControlError as exc:
            if exc.status >= 500:
                fail("failed_retryable", "storage_unavailable", "The local durable store failed. Retry manually.")
            else:
                fail("failed_terminal", "invalid_input", exc.message)
            return
        except Exception:
            fail(
                "failed_retryable",
                "executor_failure",
                "The synthetic executor failed. Retry manually while the retry budget remains.",
            )
            return

        if not isinstance(result, dict):
            fail(
                "failed_retryable",
                "executor_failure",
                "The synthetic executor returned an invalid result. Retry manually while the retry budget remains.",
            )
            return
        cost = result.get("estimated_cost_usd")
        if type(cost) is not int or cost < 0 or cost > SQLITE_MAX_INTEGER:
            fail(
                "failed_terminal",
                "cost_limit_exceeded",
                "The executor did not report a bounded integer zero cost; the result was discarded.",
            )
            return
        if cost != COST_CAP_USD:
            fail(
                "failed_terminal",
                "cost_limit_exceeded",
                "The executor reported a cost above the fixed zero-dollar cap; the result was discarded.",
                estimated_cost_usd=cost,
            )
            return
        try:
            fixture_run = result["fixture_run"]
            results = result["results"]
            process_local_projection = result["process_local_projection"]
            if (
                not isinstance(fixture_run, dict)
                or not isinstance(results, list)
                or not isinstance(process_local_projection, dict)
            ):
                raise TypeError("unexpected executor result shape")
            self.repository.validate_prepared_run(
                actor,
                process_local_projection,
                fixture_run=fixture_run,
                results=results,
            )
            fixture_source_ids = fixture_run["fixture_source_ids"]
            result_ids = fixture_run["output_ids"]
            errors = fixture_run["errors"]
            stop_reason = fixture_run["stop_reason"]
            if (
                not isinstance(fixture_source_ids, (list, tuple))
                or not isinstance(result_ids, (list, tuple))
                or not isinstance(errors, (list, tuple))
                or not isinstance(stop_reason, str)
                or not all(isinstance(value, str) for value in fixture_source_ids)
                or not all(isinstance(value, str) for value in result_ids)
                or not all(isinstance(value, str) for value in errors)
                or not all(isinstance(value, dict) for value in results)
                or fixture_run["estimated_cost_usd"] != cost
            ):
                raise TypeError("unexpected executor result shape")
            snapshot = canonical_json(results, limit=MAX_SNAPSHOT_BYTES, label="Result snapshot")
            content_hash = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
            output = {
                "output_schema": OUTPUT_SCHEMA,
                "content_hash": content_hash,
                "byte_length": len(snapshot.encode("utf-8")),
                "fixture_source_ids": list(fixture_source_ids),
                "result_ids": list(result_ids),
                "estimated_cost_usd": cost,
                "errors": list(errors),
                "stop_reason": stop_reason,
                "result_snapshot": results,
            }
        except Exception:
            fail(
                "failed_retryable",
                "executor_failure",
                "The synthetic executor returned an invalid result. Retry manually while the retry budget remains.",
            )
            return
        if fixture_run.get("status") == "failed_validation":
            fail("failed_terminal", "invalid_input", "A synthetic fixture failed bounded validation.")
            return
        reviewers = [name for name in ACTOR_SCOPE if run["business_unit"] in ACTOR_SCOPE[name]]
        try:
            committed = self.store.commit_success(
                run_id,
                attempt_number=attempt_number,
                actor=actor,
                correlation_id=correlation_id,
                output=output,
                allowed_reviewers=reviewers,
                now=self._now(),
            )
        except Exception:
            fail(
                "failed_retryable",
                "transaction_rolled_back",
                "Atomic output persistence rolled back; no partial output or review task exists. Retry manually.",
            )
            return
        if committed is None:
            # Cancellation won the race; the output transaction rolled back whole.
            if not self.store.complete_cancellation(
                run_id, attempt_number=attempt_number, actor=actor,
                correlation_id=correlation_id, now=self._now(),
            ):
                raise MissionControlError(409, "The attempt reached a terminal state in another transition.")
            return
        self.repository.commit_prepared_run(actor, process_local_projection)


def default_state_path() -> Path:
    return REPOSITORY_ROOT / "apps" / "prospecting-mission-control" / "local_state" / "phase4-state.sqlite3"

"""Phase 4 registered prospecting agent tests.

Everything here is deterministic and repository-local: injected clocks,
deterministic IDs, executor fakes, one-shot storage fault injection, and
temporary SQLite state files. No real delay, network, or external service.
"""

from __future__ import annotations

import copy
import http.client
import json
import re
import sqlite3
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = ROOT / "apps" / "prospecting-mission-control"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from mission_control.agent import (  # noqa: E402
    AGENT_ID,
    COST_CAP_USD,
    MAX_ATTEMPTS,
    SKILL_BINDINGS,
    FixtureWorkerExecutor,
    RegisteredAgentService,
)
from mission_control.application import (  # noqa: E402
    CounterIds,
    FixtureRepository,
    MissionControl,
    MissionControlError,
)
from mission_control.store import MAX_SNAPSHOT_BYTES, SqliteStore  # noqa: E402
from mission_control.web import WebApplication, build_server  # noqa: E402

FIXED_TIME = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
PHASE3_FIXTURE = ROOT / "fixtures" / "prospecting" / "phase3" / "prospects.json"
PHASE4_FIXTURE = ROOT / "fixtures" / "prospecting" / "phase4" / "worker-scenarios.json"
SCENARIOS = {
    item["scenario_id"]: item
    for item in json.loads(PHASE4_FIXTURE.read_text(encoding="utf-8"))["scenarios"]
}


class FakeClock:
    def __init__(self, start: datetime = FIXED_TIME):
        self.value = start

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)


class FaultInjector:
    """Raises one synthetic sqlite fault the next time the armed label runs."""

    def __init__(self):
        self.armed: str | None = None

    def __call__(self, label: str) -> None:
        if self.armed == label:
            self.armed = None
            raise sqlite3.OperationalError("synthetic storage fault")


class FailingExecutor:
    """Fails a configured number of times, then delegates to the real adapter."""

    def __init__(self, repository, failures: int):
        self.real = FixtureWorkerExecutor(repository)
        self.failures = failures
        self.calls = 0

    def execute(self, run, checkpoint):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("synthetic executor fault")
        return self.real.execute(run, checkpoint)


class CostViolationExecutor:
    def __init__(self, repository):
        self.real = FixtureWorkerExecutor(repository)

    def execute(self, run, checkpoint):
        result = self.real.execute(run, checkpoint)
        result["estimated_cost_usd"] = 1
        return result


class MutatingResultExecutor:
    """Returns a deterministic mutation of the real executor result."""

    def __init__(self, repository, mutate):
        self.real = FixtureWorkerExecutor(repository)
        self.mutate = mutate

    def execute(self, run, checkpoint):
        return self.mutate(self.real.execute(run, checkpoint))


class TimeoutExecutor:
    """Advances the injected clock past the deadline between two checkpoints."""

    def __init__(self, clock: FakeClock, advance_seconds: int = 3_600):
        self.clock = clock
        self.advance_seconds = advance_seconds

    def execute(self, run, checkpoint):
        checkpoint("bounded_step_one")
        self.clock.advance(self.advance_seconds)
        checkpoint("bounded_step_two")
        raise AssertionError("the cooperative deadline checkpoint must interrupt execution")


class CancelDuringExecutionExecutor:
    """Requests cooperative cancellation between two bounded steps."""

    def __init__(self, store: SqliteStore, now: str):
        self.store = store
        self.now = now

    def execute(self, run, checkpoint):
        checkpoint("bounded_step_one")
        self.store.request_running_cancellation(run["run_id"], actor="noah", now=self.now)
        checkpoint("bounded_step_two")
        raise AssertionError("the cooperative cancellation checkpoint must interrupt execution")


class CancelAfterLastCheckpointExecutor:
    """Races cancellation against the atomic success commit itself."""

    def __init__(self, repository, store: SqliteStore, now: str):
        self.real = FixtureWorkerExecutor(repository)
        self.store = store
        self.now = now

    def execute(self, run, checkpoint):
        result = self.real.execute(run, checkpoint)
        self.store.request_running_cancellation(run["run_id"], actor="noah", now=self.now)
        return result


class Phase4Env:
    def __init__(
        self,
        state_dir: Path,
        *,
        clock=None,
        executor=None,
        fault_hook=None,
        timeout_seconds: int = 10,
    ):
        self.clock = clock or FakeClock()
        self.repository = FixtureRepository(
            clock=self.clock, next_id=CounterIds(), fixture_path=PHASE3_FIXTURE
        )
        self.control = MissionControl(self.repository)
        self.state_path = state_dir / "phase4-test-state.sqlite3"
        self.store = SqliteStore(self.state_path, fault_hook=fault_hook)
        self.service = RegisteredAgentService(
            self.repository,
            self.store,
            clock=self.clock,
            executor=executor,
            timeout_seconds=timeout_seconds,
        )

    def campaign(self, scenario_id: str = "phase4-umg-success", actor: str = "noah") -> dict:
        scenario = SCENARIOS[scenario_id]
        unit = scenario["business_unit"]
        form = {
            "business_unit": unit,
            "campaign_name": f"Synthetic {scenario_id}",
            "discovery_scope": scenario["discovery_scope"],
            "verticals": ", ".join(scenario["verticals"]),
            "target_prospect_count": "20",
            "minimum_qualification_score": "72" if unit == "unreal-media-group" else "78",
            "cooldown_days": "120" if unit == "unreal-media-group" else "180",
            "maximum_evidence_age_days": "180",
            "geography": "United States",
            "rights_territory": "United States" if unit == "unreal-talent" else "",
            "talent_categories": "athlete archetype" if unit == "unreal-talent" else "",
        }
        config = self.control.campaign_config(form)
        return self.repository.add_campaign(actor, config)

    def run_to_completion(self, campaign: dict, *, actor: str = "noah", key: str = "phase4-key") -> dict:
        run, created = self.service.create_manual_run(
            actor, campaign["family_id"], campaign["version"], key
        )
        if created and run["state"] == "queued":
            run = self.service.execute_run(actor, run["run_id"])
        return run


class Phase4TestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._state_dir.cleanup)
        self.state_dir = Path(self._state_dir.name)


def process_local_state(repository: FixtureRepository) -> dict:
    """Snapshot the Phase 3 collections that worker failures must not expose."""
    return {
        "run_records": copy.deepcopy(repository.run_records),
        "prospect_history": copy.deepcopy(repository.prospect_history),
        "prospect_records": copy.deepcopy(repository.prospect_records),
        "idempotency": copy.deepcopy(repository.idempotency),
        "manual_fixture_run_audits": copy.deepcopy([
            event for event in repository.audit_events
            if event["action"] == "manual_fixture_run"
        ]),
    }


class RegistrationTests(Phase4TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.env = Phase4Env(self.state_dir)

    def test_exact_registration_and_server_owned_bindings(self) -> None:
        registration = self.env.service.registration()
        self.assertEqual(registration["agent_id"], "brand-prospecting-agent")
        self.assertEqual(registration["registration_state"], "registered and enabled for manual synthetic execution")
        self.assertEqual(registration["trigger"], "manual human form only")
        self.assertEqual(registration["max_concurrency"], 1)
        self.assertEqual(registration["cost_cap_usd"], 0)
        self.assertEqual(registration["max_attempts"], MAX_ATTEMPTS)
        self.assertTrue(registration["cancellation"])
        self.assertEqual(registration["durable_store_adapter"], "sqlite-local-v1")
        self.assertEqual(
            registration["skill_bindings"]["unreal-media-group"]["skill_id"],
            "unreal-media-brand-prospector",
        )
        self.assertEqual(
            registration["skill_bindings"]["unreal-talent"]["skill_id"],
            "unreal-talent-campaign-prospector",
        )
        for binding in registration["skill_bindings"].values():
            self.assertEqual(binding["skill_version"], "1.0.0-phase1-frozen")
            self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", binding["skill_integrity_sha256"]))

    def test_registration_exposes_no_prohibited_capability(self) -> None:
        registration = self.env.service.registration()
        for key in ["credentials", "scheduler", "recurring_loop", "network", "creative", "likeness", "outreach"]:
            self.assertFalse(registration[key], key)
        serialized = json.dumps(registration).casefold()
        for term in ["token", "secret", "password", "cron", "webhook"]:
            self.assertNotIn(term, serialized)

    def test_client_cannot_select_skill_or_executable(self) -> None:
        # The manual-run boundary accepts only campaign family, version, actor,
        # and idempotency key; skill routing is resolved from server constants.
        campaign = self.env.campaign()
        run = self.env.run_to_completion(campaign, key="binding-check")
        self.assertEqual(run["skill_id"], SKILL_BINDINGS["unreal-media-group"]["skill_id"])
        self.assertEqual(run["skill_version"], SKILL_BINDINGS["unreal-media-group"]["skill_version"])
        self.assertEqual(run["agent_id"], AGENT_ID)

    def test_unknown_actor_fails_closed_with_rejection_audit(self) -> None:
        campaign = self.env.campaign()
        with self.assertRaisesRegex(MissionControlError, "not allowed"):
            self.env.service.create_manual_run("intruder", campaign["family_id"], 1, "bad-actor")
        with self.assertRaisesRegex(MissionControlError, "idempotency key"):
            self.env.service.create_manual_run("noah", campaign["family_id"], 1, "unsafe key!")
        with self.assertRaisesRegex(MissionControlError, "not found"):
            self.env.service.create_manual_run("noah", "invented-family", 1, "missing-campaign")


class EndToEndTests(Phase4TestCase):
    def test_umg_manual_run_end_to_end_with_durable_records(self) -> None:
        env = Phase4Env(self.state_dir)
        campaign = env.campaign("phase4-umg-success")
        run = env.run_to_completion(campaign, key="umg-e2e")
        self.assertEqual(run["state"], "succeeded")
        self.assertEqual(run["attempt_count"], 1)
        self.assertEqual(run["actual_cost_usd"], 0)
        self.assertEqual(run["cost_cap_usd"], 0)
        detail = env.service.run_detail("noah", run["run_id"])
        self.assertEqual(len(detail["attempts"]), 1)
        self.assertEqual(detail["attempts"][0]["outcome"], "succeeded")
        output = detail["output"]
        self.assertIsNotNone(output)
        self.assertTrue(output["result_ids"])
        self.assertEqual(output["estimated_cost_usd"], 0)
        self.assertEqual(output["byte_length"], len(json.dumps(output["result_snapshot"], sort_keys=True, separators=(",", ":")).encode()))
        self.assertEqual(detail["review_task"]["state"], "pending_review")
        self.assertEqual(detail["review_task"]["run_id"], run["run_id"])
        events = [item["event_type"] for item in detail["audit_events"]]
        for expected in ["manual_request_accepted", "attempt_started", "attempt_succeeded", "output_committed", "review_task_created"]:
            self.assertIn(expected, events)
        # The Phase 3 fixture adapter executed exactly once as the data source.
        self.assertEqual(len(env.repository.run_records), 1)
        self.assertEqual(env.repository.run_records[0].skill_name, "unreal-media-brand-prospector")

    def test_talent_manual_run_binds_talent_skill_and_protections_hold(self) -> None:
        env = Phase4Env(self.state_dir)
        campaign = env.campaign("phase4-talent-success")
        run = env.run_to_completion(campaign, key="talent-e2e")
        self.assertEqual(run["state"], "succeeded")
        self.assertEqual(run["skill_id"], "unreal-talent-campaign-prospector")
        output = env.store.get_output(run["run_id"])
        snapshot_ids = {item["prospect_id"] for item in output["result_snapshot"]}
        self.assertIn("talent-named-person", snapshot_ids)
        # Worker output cannot weaken the named-talent protection downstream.
        with self.assertRaisesRegex(MissionControlError, "named talent"):
            env.repository.act("dan", "unreal-talent", "talent-named-person", "approve_deeper_research", {})
        named = env.repository.get_prospect("dan", "unreal-talent", "talent-named-person")
        self.assertEqual(named["queue"], "rejections")

    def test_no_results_run_is_a_visible_empty_success(self) -> None:
        env = Phase4Env(self.state_dir)
        campaign = env.campaign("phase4-no-results")
        run = env.run_to_completion(campaign, key="no-results")
        self.assertEqual(run["state"], "succeeded")
        output = env.store.get_output(run["run_id"])
        self.assertEqual(output["result_ids"], [])
        self.assertIn("No synthetic fixtures matched", output["stop_reason"])
        self.assertIsNotNone(run["review_task_id"])

    def test_terminal_validation_failure_persists_no_output(self) -> None:
        env = Phase4Env(self.state_dir)
        candidate = json.loads(PHASE4_FIXTURE.read_text(encoding="utf-8"))["validation_failure_candidate"]
        env.repository.fixture_candidates += (candidate,)
        scenario_campaign = env.control.campaign_config({
            "business_unit": "unreal-media-group",
            "campaign_name": "Synthetic validation terminal",
            "discovery_scope": "filtered",
            "verticals": "phase4 validation fixture",
            "target_prospect_count": "20",
            "minimum_qualification_score": "72",
            "cooldown_days": "120",
            "maximum_evidence_age_days": "180",
            "geography": "United States",
            "rights_territory": "",
            "talent_categories": "",
        })
        campaign = env.repository.add_campaign("noah", scenario_campaign)
        run = env.run_to_completion(campaign, key="validation-terminal")
        self.assertEqual(run["state"], "failed_terminal")
        self.assertEqual(run["failure_class"], "invalid_input")
        self.assertFalse(run["retryable"])
        self.assertIsNone(env.store.get_output(run["run_id"]))
        self.assertEqual(env.store.list_review_tasks({"unreal-media-group"}), [])
        with self.assertRaisesRegex(MissionControlError, "not retryable"):
            env.service.retry_run("noah", run["run_id"])

    def test_durable_state_survives_store_and_service_restart(self) -> None:
        env = Phase4Env(self.state_dir)
        campaign = env.campaign()
        run = env.run_to_completion(campaign, key="durable")
        reopened_store = SqliteStore(env.state_path)
        reopened = RegisteredAgentService(env.repository, reopened_store, clock=env.clock)
        self.assertEqual(reopened.recovered_run_ids, [])
        persisted = reopened.run_detail("noah", run["run_id"])
        self.assertEqual(persisted["state"], "succeeded")
        self.assertEqual(len(persisted["attempts"]), 1)
        self.assertIsNotNone(persisted["output"])
        self.assertEqual(persisted["review_task"]["state"], "pending_review")
        self.assertTrue(persisted["audit_events"])
        integrity, foreign_keys = reopened_store.integrity_report()
        self.assertEqual(integrity, "ok")
        self.assertEqual(foreign_keys, [])


class StateMachineTests(Phase4TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.env = Phase4Env(self.state_dir)

    def _queued_run(self, key: str = "sm-key") -> dict:
        campaign = self.env.campaign()
        run, _ = self.env.service.create_manual_run("noah", campaign["family_id"], campaign["version"], key)
        return run

    def test_every_allowed_and_prohibited_transition_is_enforced(self) -> None:
        store, now = self.env.store, "2026-07-18T12:00:00Z"
        run = self._queued_run()
        run_id = run["run_id"]
        # Prohibited while queued: success, failure, and running-cancel completion.
        self.assertIsNone(store.commit_success(run_id, attempt_number=1, actor="noah", correlation_id="c", output=_minimal_output(), allowed_reviewers=["noah"], now=now))
        self.assertFalse(store.commit_failure(run_id, attempt_number=1, terminal_state="failed_retryable", failure_class="executor_failure", retryable=True, remediation="r", event_type="attempt_failed", actor="noah", correlation_id="c", now=now))
        self.assertFalse(store.complete_cancellation(run_id, attempt_number=1, actor="noah", correlation_id="c", now=now))
        # Allowed: queued -> running.
        claim = store.claim_attempt(run_id, expected_states=("queued",), actor="noah", worker_version="test", now=now)
        self.assertEqual(claim["attempt_number"], 1)
        # Prohibited while running: queued-cancel and a second claim.
        self.assertFalse(store.cancel_queued(run_id, actor="noah", now=now))
        self.assertIsNone(store.claim_attempt(run_id, expected_states=("queued", "failed_retryable", "timed_out"), actor="noah", worker_version="test", now=now))
        # Allowed: running -> succeeded, then every further transition is refused.
        self.assertIsNotNone(store.commit_success(run_id, attempt_number=1, actor="noah", correlation_id="c", output=_minimal_output(), allowed_reviewers=["noah"], now=now))
        self.assertIsNone(store.claim_attempt(run_id, expected_states=("queued", "failed_retryable", "timed_out"), actor="noah", worker_version="test", now=now))
        self.assertFalse(store.commit_failure(run_id, attempt_number=1, terminal_state="timed_out", failure_class="timeout", retryable=False, remediation="r", event_type="attempt_timed_out", actor="noah", correlation_id="c", now=now))
        self.assertFalse(store.cancel_queued(run_id, actor="noah", now=now))
        self.assertFalse(store.request_running_cancellation(run_id, actor="noah", now=now))

    def test_double_claim_cannot_start_two_attempts(self) -> None:
        run = self._queued_run("double-claim")
        first = self.env.store.claim_attempt(run["run_id"], expected_states=("queued",), actor="noah", worker_version="test", now="2026-07-18T12:00:00Z")
        second = self.env.store.claim_attempt(run["run_id"], expected_states=("queued",), actor="noah", worker_version="test", now="2026-07-18T12:00:00Z")
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(len(self.env.store.attempts_for(run["run_id"])), 1)

    def test_success_and_cancellation_race_has_exactly_one_winner(self) -> None:
        env = Phase4Env(self.state_dir / "race")
        env.service.executor = CancelAfterLastCheckpointExecutor(env.repository, env.store, "2026-07-18T12:00:01Z")
        campaign = env.campaign()
        run = env.run_to_completion(campaign, key="race")
        self.assertEqual(run["state"], "cancelled")
        self.assertIsNone(env.store.get_output(run["run_id"]))
        self.assertEqual(env.store.list_review_tasks({"unreal-media-group"}), [])
        events = [item["event_type"] for item in env.store.audits_for(run["run_id"])]
        self.assertEqual(events.count("cancellation_completed"), 1)
        self.assertNotIn("output_committed", events)

    def test_startup_recovery_is_visible_and_not_automatic(self) -> None:
        run = self._queued_run("interrupted")
        self.env.store.claim_attempt(run["run_id"], expected_states=("queued",), actor="noah", worker_version="test", now="2026-07-18T12:00:00Z")
        # Simulate a process exit while running: reopen the same state file.
        reopened_store = SqliteStore(self.env.state_path)
        service = RegisteredAgentService(self.env.repository, reopened_store, clock=self.env.clock)
        self.assertEqual(service.recovered_run_ids, [run["run_id"]])
        recovered = service.run_detail("noah", run["run_id"])
        self.assertEqual(recovered["state"], "failed_retryable")
        self.assertEqual(recovered["failure_class"], "interrupted_execution_recovered")
        self.assertTrue(recovered["retry_allowed"])
        self.assertEqual(recovered["attempts"][0]["outcome"], "interrupted")
        self.assertIn("startup_interruption_recovered", [item["event_type"] for item in recovered["audit_events"]])
        # Recovery never executes anything by itself.
        self.assertEqual(len(recovered["attempts"]), 1)
        retried = service.retry_run("noah", run["run_id"])
        self.assertEqual(retried["state"], "succeeded")
        self.assertEqual(len(reopened_store.attempts_for(run["run_id"])), 2)


class IdempotencyAndRetryTests(Phase4TestCase):
    def test_identical_replay_returns_existing_run_without_duplicate_output(self) -> None:
        env = Phase4Env(self.state_dir)
        campaign = env.campaign()
        first = env.run_to_completion(campaign, key="replay")
        replay, created = env.service.create_manual_run("noah", campaign["family_id"], 1, "replay")
        self.assertFalse(created)
        self.assertEqual(replay["run_id"], first["run_id"])
        self.assertEqual(replay["attempt_count"], 1)
        self.assertEqual(len(env.store.attempts_for(first["run_id"])), 1)
        self.assertEqual(len(env.store.list_review_tasks({"unreal-media-group"})), 1)
        self.assertEqual(len(env.repository.run_records), 1)
        events = [item["event_type"] for item in env.store.audits_for(first["run_id"])]
        self.assertIn("idempotent_replay", events)

    def test_conflicting_key_reuse_fails_safely(self) -> None:
        env = Phase4Env(self.state_dir)
        campaign = env.campaign()
        other = env.campaign("phase4-no-results")
        env.run_to_completion(campaign, key="conflict")
        with self.assertRaises(MissionControlError) as caught:
            env.service.create_manual_run("noah", other["family_id"], other["version"], "conflict")
        self.assertEqual(caught.exception.status, 409)
        self.assertIn("idempotency_conflict", caught.exception.message)
        run = env.store.find_run_by_key("conflict")
        self.assertIn("idempotency_conflict", [item["event_type"] for item in env.store.audits_for(run["run_id"])])
        self.assertEqual(len(env.store.list_runs({"unreal-media-group"})), 1)

    def test_retryable_failure_then_manual_retry_without_duplicates(self) -> None:
        env = Phase4Env(self.state_dir)
        executor = FailingExecutor(env.repository, failures=1)
        env.service.executor = executor
        campaign = env.campaign()
        run = env.run_to_completion(campaign, key="flaky")
        self.assertEqual(run["state"], "failed_retryable")
        self.assertEqual(run["failure_class"], "executor_failure")
        self.assertTrue(run["retryable"])
        self.assertIsNone(env.store.get_output(run["run_id"]))
        retried = env.service.retry_run("noah", run["run_id"])
        self.assertEqual(retried["state"], "succeeded")
        attempts = env.store.attempts_for(run["run_id"])
        self.assertEqual([item["attempt_number"] for item in attempts], [1, 2])
        self.assertEqual(attempts[0]["outcome"], "executor_failure")
        self.assertEqual(attempts[1]["outcome"], "succeeded")
        # No duplicate business work anywhere: one output, one review task, one
        # Phase 3 discovery run.
        self.assertIsNotNone(env.store.get_output(run["run_id"]))
        self.assertEqual(len(env.store.list_review_tasks({"unreal-media-group"})), 1)
        self.assertEqual(len(env.repository.run_records), 1)

    def test_retry_cap_boundary_has_no_off_by_one(self) -> None:
        env = Phase4Env(self.state_dir)
        env.service.executor = FailingExecutor(env.repository, failures=100)
        campaign = env.campaign()
        run = env.run_to_completion(campaign, key="exhaust")
        self.assertEqual(run["attempt_count"], 1)
        run = env.service.retry_run("noah", run["run_id"])
        self.assertEqual(run["attempt_count"], 2)
        self.assertTrue(run["retryable"])
        run = env.service.retry_run("noah", run["run_id"])
        self.assertEqual(run["attempt_count"], MAX_ATTEMPTS)
        self.assertFalse(run["retryable"])
        with self.assertRaisesRegex(MissionControlError, "exhausted"):
            env.service.retry_run("noah", run["run_id"])
        self.assertEqual(len(env.store.attempts_for(run["run_id"])), MAX_ATTEMPTS)
        self.assertIn("retry_denied", [item["event_type"] for item in env.store.audits_for(run["run_id"])])

    def test_retry_after_success_is_denied_without_execution(self) -> None:
        env = Phase4Env(self.state_dir)
        campaign = env.campaign()
        run = env.run_to_completion(campaign, key="success-retry")
        with self.assertRaisesRegex(MissionControlError, "already succeeded"):
            env.service.retry_run("noah", run["run_id"])
        self.assertEqual(len(env.store.attempts_for(run["run_id"])), 1)


class TimeoutCancellationCostTests(Phase4TestCase):
    def test_timeout_produces_no_partial_output_and_is_retryable(self) -> None:
        clock = FakeClock()
        env = Phase4Env(self.state_dir, clock=clock)
        env.service.executor = TimeoutExecutor(clock)
        campaign = env.campaign()
        run = env.run_to_completion(campaign, key="timeout")
        self.assertEqual(run["state"], "timed_out")
        self.assertEqual(run["failure_class"], "timeout")
        self.assertTrue(run["retryable"])
        self.assertIsNone(run["actual_cost_usd"])
        self.assertIsNone(env.store.get_output(run["run_id"]))
        self.assertEqual(env.store.list_review_tasks({"unreal-media-group"}), [])
        self.assertIsNone(env.store.attempts_for(run["run_id"])[0]["estimated_cost_usd"])
        env.service.executor = FixtureWorkerExecutor(env.repository)
        retried = env.service.retry_run("noah", run["run_id"])
        self.assertEqual(retried["state"], "succeeded")

    def test_cancellation_before_execution(self) -> None:
        env = Phase4Env(self.state_dir)
        campaign = env.campaign()
        run, _ = env.service.create_manual_run("noah", campaign["family_id"], 1, "cancel-queued")
        cancelled = env.service.cancel_run("noah", run["run_id"])
        self.assertEqual(cancelled["state"], "cancelled")
        self.assertEqual(env.store.attempts_for(run["run_id"]), [])
        with self.assertRaisesRegex(MissionControlError, "could not be claimed"):
            env.service.execute_run("noah", run["run_id"])
        events = [item["event_type"] for item in env.store.audits_for(run["run_id"])]
        self.assertIn("cancellation_requested", events)
        self.assertIn("cancellation_completed", events)

    def test_cooperative_cancellation_during_execution(self) -> None:
        env = Phase4Env(self.state_dir)
        env.service.executor = CancelDuringExecutionExecutor(env.store, "2026-07-18T12:00:01Z")
        campaign = env.campaign()
        run = env.run_to_completion(campaign, key="cancel-running")
        self.assertEqual(run["state"], "cancelled")
        self.assertFalse(run["retryable"])
        self.assertIsNone(env.store.get_output(run["run_id"]))
        attempts = env.store.attempts_for(run["run_id"])
        self.assertEqual(attempts[0]["outcome"], "cancelled")
        # Cancellation does not silently consume an extra retry attempt.
        self.assertEqual(len(attempts), 1)
        with self.assertRaisesRegex(MissionControlError, "not retryable"):
            env.service.retry_run("noah", run["run_id"])

    def test_cancellation_after_success_fails_safely_and_preserves_output(self) -> None:
        env = Phase4Env(self.state_dir)
        campaign = env.campaign()
        run = env.run_to_completion(campaign, key="cancel-after-success")
        with self.assertRaisesRegex(MissionControlError, "output is preserved"):
            env.service.cancel_run("noah", run["run_id"])
        self.assertEqual(env.service.get_run("noah", run["run_id"])["state"], "succeeded")
        self.assertIsNotNone(env.store.get_output(run["run_id"]))

    def test_positive_cost_fails_closed_against_the_zero_cap(self) -> None:
        env = Phase4Env(self.state_dir)
        env.service.executor = CostViolationExecutor(env.repository)
        campaign = env.campaign()
        run = env.run_to_completion(campaign, key="cost")
        self.assertEqual(run["state"], "failed_terminal")
        self.assertEqual(run["failure_class"], "cost_limit_exceeded")
        self.assertEqual(run["cost_cap_usd"], COST_CAP_USD)
        self.assertIsNone(env.store.get_output(run["run_id"]))
        self.assertEqual(env.store.list_review_tasks({"unreal-media-group"}), [])


class TransactionAndRecoveryTests(Phase4TestCase):
    def _run_with_fault(self, label: str) -> tuple[Phase4Env, dict]:
        injector = FaultInjector()
        env = Phase4Env(self.state_dir / label, fault_hook=injector)
        campaign = env.campaign()
        injector.armed = label
        run = env.run_to_completion(campaign, key=f"fault-{label}")
        return env, run

    def test_output_persistence_failure_rolls_back_success(self) -> None:
        env, run = self._run_with_fault("insert_output")
        self.assertEqual(run["state"], "failed_retryable")
        self.assertEqual(run["failure_class"], "transaction_rolled_back")
        self.assertIsNone(env.store.get_output(run["run_id"]))
        self.assertEqual(env.store.list_review_tasks({"unreal-media-group"}), [])
        retried = env.service.retry_run("noah", run["run_id"])
        self.assertEqual(retried["state"], "succeeded")
        integrity, foreign_keys = env.store.integrity_report()
        self.assertEqual((integrity, foreign_keys), ("ok", []))

    def test_review_task_failure_rolls_back_output_and_success(self) -> None:
        env, run = self._run_with_fault("insert_review_task")
        self.assertEqual(run["state"], "failed_retryable")
        self.assertIsNone(env.store.get_output(run["run_id"]))
        self.assertEqual(env.store.list_review_tasks({"unreal-media-group"}), [])
        retried = env.service.retry_run("noah", run["run_id"])
        self.assertEqual(retried["state"], "succeeded")
        self.assertEqual(len(env.store.list_review_tasks({"unreal-media-group"})), 1)

    def test_audit_failure_rolls_back_the_governed_claim(self) -> None:
        injector = FaultInjector()
        env = Phase4Env(self.state_dir / "audit", fault_hook=injector)
        campaign = env.campaign()
        run, _ = env.service.create_manual_run("noah", campaign["family_id"], 1, "audit-fault")
        injector.armed = "insert_audit"
        with self.assertRaisesRegex(MissionControlError, "rolled back"):
            env.service.execute_run("noah", run["run_id"])
        current = env.store.get_run(run["run_id"])
        self.assertEqual(current["state"], "queued")
        self.assertEqual(current["attempt_count"], 0)
        self.assertEqual(env.store.attempts_for(run["run_id"]), [])
        # After the transient fault clears, the same run executes normally.
        recovered = env.service.execute_run("noah", run["run_id"])
        self.assertEqual(recovered["state"], "succeeded")

    def test_claim_failure_is_safe_and_bounded(self) -> None:
        injector = FaultInjector()
        env = Phase4Env(self.state_dir / "claim", fault_hook=injector)
        campaign = env.campaign()
        run, _ = env.service.create_manual_run("noah", campaign["family_id"], 1, "claim-fault")
        injector.armed = "claim_attempt"
        with self.assertRaises(MissionControlError) as caught:
            env.service.execute_run("noah", run["run_id"])
        self.assertEqual(caught.exception.status, 500)
        self.assertNotIn("sqlite", caught.exception.message.casefold())
        self.assertNotIn("/", caught.exception.message)
        self.assertEqual(env.store.get_run(run["run_id"])["state"], "queued")

    def test_no_destructive_sql_exists_in_the_store(self) -> None:
        source = (APP_ROOT / "mission_control" / "store.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"(?i)\b(DROP|TRUNCATE|DELETE)\s+(TABLE|FROM)\b", source))


class ProcessLocalCommitBoundaryTests(Phase4TestCase):
    def _assert_no_projection(self, before: dict, env: Phase4Env) -> None:
        self.assertEqual(process_local_state(env.repository), before)

    def _assert_single_projection(self, before: dict, env: Phase4Env, run: dict) -> None:
        after = process_local_state(env.repository)
        output = env.store.get_output(run["run_id"])
        self.assertIsNotNone(output)
        expected_keys = {
            f"{run['business_unit']}:{prospect_id}"
            for prospect_id in output["result_ids"]
        }
        self.assertEqual(len(after["run_records"]), len(before["run_records"]) + 1)
        self.assertEqual(
            len(after["prospect_history"]),
            len(before["prospect_history"]) + len(output["result_ids"]),
        )
        self.assertEqual(
            set(after["prospect_records"]) - set(before["prospect_records"]),
            expected_keys,
        )
        self.assertEqual(len(after["idempotency"]), len(before["idempotency"]) + 1)
        self.assertEqual(
            len(after["manual_fixture_run_audits"]),
            len(before["manual_fixture_run_audits"]) + 1,
        )
        self.assertEqual(len(env.store.list_review_tasks({run["business_unit"]})), 1)

    def test_ordinary_cancellation_checkpoint_leaves_no_process_local_projection(self) -> None:
        env = Phase4Env(self.state_dir)
        env.service.executor = CancelDuringExecutionExecutor(env.store, "2026-07-18T12:00:01Z")
        campaign = env.campaign()
        before = process_local_state(env.repository)
        run = env.run_to_completion(campaign, key="boundary-cancel-checkpoint")
        self.assertEqual(run["state"], "cancelled")
        self._assert_no_projection(before, env)

    def test_cancellation_after_execution_leaves_no_process_local_projection(self) -> None:
        env = Phase4Env(self.state_dir)
        env.service.executor = CancelAfterLastCheckpointExecutor(
            env.repository, env.store, "2026-07-18T12:00:01Z"
        )
        campaign = env.campaign()
        before = process_local_state(env.repository)
        run = env.run_to_completion(campaign, key="boundary-cancel-after-execution")
        self.assertEqual(run["state"], "cancelled")
        self._assert_no_projection(before, env)

    def test_cost_rejection_leaves_no_projection_and_persists_reported_cost(self) -> None:
        env = Phase4Env(self.state_dir)
        env.service.executor = CostViolationExecutor(env.repository)
        campaign = env.campaign()
        before = process_local_state(env.repository)
        run = env.run_to_completion(campaign, key="boundary-cost")
        attempt = env.store.attempts_for(run["run_id"])[0]
        self.assertEqual(run["state"], "failed_terminal")
        self.assertEqual(run["failure_class"], "cost_limit_exceeded")
        self.assertEqual(run["actual_cost_usd"], 1)
        self.assertEqual(attempt["estimated_cost_usd"], 1)
        self.assertIsNone(env.store.get_output(run["run_id"]))
        self._assert_no_projection(before, env)

    def test_invalid_cost_values_fail_closed_without_unsafe_metadata(self) -> None:
        invalid_costs = (2**100, -1, True, "1")
        for index, invalid_cost in enumerate(invalid_costs):
            with self.subTest(cost=invalid_cost):
                env = Phase4Env(self.state_dir / f"invalid-cost-{index}")
                env.service.executor = MutatingResultExecutor(
                    env.repository,
                    lambda result, value=invalid_cost: {
                        **result,
                        "estimated_cost_usd": value,
                    },
                )
                campaign = env.campaign()
                before = process_local_state(env.repository)
                run = env.run_to_completion(campaign, key=f"invalid-cost-{index}")
                attempt = env.store.attempts_for(run["run_id"])[0]
                self.assertEqual(run["state"], "failed_terminal")
                self.assertEqual(run["failure_class"], "cost_limit_exceeded")
                self.assertFalse(run["retryable"])
                self.assertIsNotNone(run["completed_at"])
                self.assertIsNone(run["actual_cost_usd"])
                self.assertEqual(attempt["terminal_state"], "failed_terminal")
                self.assertEqual(attempt["outcome"], "cost_limit_exceeded")
                self.assertEqual(attempt["failure_class"], "cost_limit_exceeded")
                self.assertFalse(attempt["retryable"])
                self.assertIsNotNone(attempt["completed_at"])
                self.assertIsNone(attempt["estimated_cost_usd"])
                self.assertIsNone(env.store.get_output(run["run_id"]))
                self.assertEqual(env.store.list_review_tasks({run["business_unit"]}), [])
                self.assertIn(
                    "attempt_failed",
                    [item["event_type"] for item in env.store.audits_for(run["run_id"])],
                )
                self._assert_no_projection(before, env)

    def test_oversized_executor_snapshot_becomes_durable_failure(self) -> None:
        env = Phase4Env(self.state_dir / "oversized-result")
        env.service.executor = MutatingResultExecutor(
            env.repository,
            lambda result: {
                **result,
                "results": [{"oversized": "x" * (MAX_SNAPSHOT_BYTES + 1)}],
            },
        )
        campaign = env.campaign()
        before = process_local_state(env.repository)
        run = env.run_to_completion(campaign, key="oversized-result")
        attempt = env.store.attempts_for(run["run_id"])[0]
        self.assertEqual(run["state"], "failed_retryable")
        self.assertEqual(run["failure_class"], "executor_failure")
        self.assertTrue(run["retryable"])
        self.assertIsNotNone(run["completed_at"])
        self.assertIsNone(run["actual_cost_usd"])
        self.assertEqual(attempt["terminal_state"], "failed_retryable")
        self.assertEqual(attempt["outcome"], "executor_failure")
        self.assertEqual(attempt["failure_class"], "executor_failure")
        self.assertTrue(attempt["retryable"])
        self.assertIsNotNone(attempt["completed_at"])
        self.assertIsNone(attempt["estimated_cost_usd"])
        self.assertIsNone(env.store.get_output(run["run_id"]))
        self.assertEqual(env.store.list_review_tasks({run["business_unit"]}), [])
        self.assertIn(
            "attempt_failed",
            [item["event_type"] for item in env.store.audits_for(run["run_id"])],
        )
        self._assert_no_projection(before, env)

    def test_malformed_executor_result_becomes_durable_failure(self) -> None:
        mutations = (
            lambda _result: {"estimated_cost_usd": 0},
            lambda result: {**result, "process_local_projection": {}},
            lambda result: {
                **result,
                "process_local_projection": {
                    **result["process_local_projection"],
                    "run": "not-a-manual-run",
                },
            },
            lambda result: {
                **result,
                "process_local_projection": {
                    **result["process_local_projection"],
                    "projections": [{}],
                },
            },
            lambda result: {
                **result,
                "process_local_projection": {"existing_run": result["fixture_run"]},
            },
            lambda result: {
                **result,
                "fixture_run": {
                    **result["fixture_run"],
                    "fixture_source_ids": [object()],
                },
            },
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(malformed_case=index):
                env = Phase4Env(self.state_dir / f"malformed-result-{index}")
                env.service.executor = MutatingResultExecutor(env.repository, mutate)
                campaign = env.campaign()
                before = process_local_state(env.repository)
                run = env.run_to_completion(campaign, key=f"malformed-result-{index}")
                attempt = env.store.attempts_for(run["run_id"])[0]
                self.assertEqual(run["state"], "failed_retryable")
                self.assertEqual(run["failure_class"], "executor_failure")
                self.assertTrue(run["retryable"])
                self.assertIsNotNone(run["completed_at"])
                self.assertEqual(attempt["terminal_state"], "failed_retryable")
                self.assertEqual(attempt["outcome"], "executor_failure")
                self.assertEqual(attempt["failure_class"], "executor_failure")
                self.assertTrue(attempt["retryable"])
                self.assertIsNotNone(attempt["completed_at"])
                self.assertIsNone(attempt["estimated_cost_usd"])
                self.assertIsNone(env.store.get_output(run["run_id"]))
                self.assertEqual(env.store.list_review_tasks({run["business_unit"]}), [])
                self.assertIn(
                    "attempt_failed",
                    [item["event_type"] for item in env.store.audits_for(run["run_id"])],
                )
                self._assert_no_projection(before, env)

    def test_validation_rejection_leaves_no_process_local_projection(self) -> None:
        env = Phase4Env(self.state_dir)
        candidate = json.loads(PHASE4_FIXTURE.read_text(encoding="utf-8"))[
            "validation_failure_candidate"
        ]
        env.repository.fixture_candidates += (candidate,)
        config = env.control.campaign_config({
            "business_unit": "unreal-media-group",
            "campaign_name": "Synthetic process-local validation boundary",
            "discovery_scope": "filtered",
            "verticals": "phase4 validation fixture",
            "target_prospect_count": "20",
            "minimum_qualification_score": "72",
            "cooldown_days": "120",
            "maximum_evidence_age_days": "180",
            "geography": "United States",
            "rights_territory": "",
            "talent_categories": "",
        })
        campaign = env.repository.add_campaign("noah", config)
        before = process_local_state(env.repository)
        run = env.run_to_completion(campaign, key="boundary-validation")
        self.assertEqual(run["state"], "failed_terminal")
        self.assertEqual(run["failure_class"], "invalid_input")
        self._assert_no_projection(before, env)

    def _assert_storage_failure_then_single_retry_projection(self, label: str) -> None:
        injector = FaultInjector()
        env = Phase4Env(self.state_dir / label, fault_hook=injector)
        campaign = env.campaign()
        before = process_local_state(env.repository)
        injector.armed = label
        run = env.run_to_completion(campaign, key=f"boundary-{label}")
        self.assertEqual(run["state"], "failed_retryable")
        self.assertEqual(run["failure_class"], "transaction_rolled_back")
        self.assertIsNone(env.store.get_output(run["run_id"]))
        self.assertEqual(env.store.list_review_tasks({"unreal-media-group"}), [])
        self._assert_no_projection(before, env)
        retried = env.service.retry_run("noah", run["run_id"])
        self.assertEqual(retried["state"], "succeeded")
        self._assert_single_projection(before, env, retried)
        self.assertEqual(len(env.store.attempts_for(run["run_id"])), 2)

    def test_insert_output_rollback_then_retry_projects_exactly_once(self) -> None:
        self._assert_storage_failure_then_single_retry_projection("insert_output")

    def test_insert_review_task_rollback_then_retry_projects_exactly_once(self) -> None:
        self._assert_storage_failure_then_single_retry_projection("insert_review_task")

    def test_ordinary_success_projects_once_and_governed_review_remains_usable(self) -> None:
        env = Phase4Env(self.state_dir)
        campaign = env.campaign()
        before = process_local_state(env.repository)
        run = env.run_to_completion(campaign, key="boundary-success")
        self.assertEqual(run["state"], "succeeded")
        self._assert_single_projection(before, env, run)
        output = env.store.get_output(run["run_id"])
        prospect = env.repository.get_prospect(
            "noah", run["business_unit"], output["result_ids"][0]
        )
        event = env.repository.act(
            "noah", run["business_unit"], prospect["prospect_id"], "note", {"text": "Synthetic review note"}
        )
        self.assertEqual(event["kind"], "note")

    def test_later_snapshot_preserves_existing_governed_review_projection(self) -> None:
        env = Phase4Env(self.state_dir / "existing-review-projection")
        campaign = env.campaign()
        first = env.run_to_completion(campaign, key="review-projection-first")
        self.assertEqual(first["state"], "succeeded")
        rejection = env.repository.act(
            "rob",
            "unreal-media-group",
            "umg-new-orbit",
            "reject",
            {"reason": "Synthetic prior governed rejection"},
        )
        suppression = env.repository.act(
            "rob",
            "unreal-media-group",
            "umg-subbrand-ember",
            "suppress",
            {"reason": "Synthetic prior governed suppression"},
        )
        review_events_before = copy.deepcopy(env.repository.review_events)

        second = env.run_to_completion(campaign, key="review-projection-second")
        self.assertEqual(second["state"], "succeeded")
        snapshot = next(
            item for item in env.store.get_output(second["run_id"])["result_snapshot"]
            if item["prospect_id"] == "umg-new-orbit"
        )
        live = env.repository.get_prospect(
            "noah", "unreal-media-group", "umg-new-orbit"
        )
        self.assertEqual(snapshot["review_history"], live["review_history"])
        self.assertEqual(snapshot["current_review"], live["current_review"])
        self.assertEqual(snapshot["current_decision"], live["current_decision"])
        self.assertEqual(snapshot["current_decision"], "rejected")
        self.assertEqual(snapshot["current_review"]["decision"]["event_id"], rejection["event_id"])
        suppressed_snapshot = next(
            item for item in env.store.get_output(second["run_id"])["result_snapshot"]
            if item["prospect_id"] == "umg-subbrand-ember"
        )
        self.assertTrue(suppressed_snapshot["effective_suppressed"])
        self.assertEqual(
            suppressed_snapshot["current_review"]["suppress"]["event_id"],
            suppression["event_id"],
        )
        self.assertEqual(env.repository.review_events, review_events_before)

        restarted_output = SqliteStore(env.state_path).get_output(second["run_id"])
        restarted = next(
            item for item in restarted_output["result_snapshot"]
            if item["prospect_id"] == "umg-new-orbit"
        )
        self.assertEqual(restarted["review_history"], live["review_history"])
        self.assertEqual(restarted["current_review"], live["current_review"])
        self.assertEqual(restarted["current_decision"], "rejected")
        self.assertEqual(env.repository.review_events, review_events_before)

        app = WebApplication(
            MissionControl(FixtureRepository(
                clock=FakeClock(), next_id=CounterIds(), fixture_path=PHASE3_FIXTURE
            )),
            csrf_token="deterministic-csrf",
            state_path=env.state_path,
        )
        server = build_server(app, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection(
                "127.0.0.1", server.server_address[1], timeout=3
            )
            connection.request(
                "GET",
                f'/worker-runs/{second["run_id"]}?actor=noah&business_unit=unreal-media-group',
            )
            response = connection.getresponse()
            body = response.read().decode()
            connection.close()
            self.assertEqual(response.status, 200)
            row = re.search(r"<tr><td>umg-new-orbit</td>.*?</tr>", body)
            self.assertIsNotNone(row)
            self.assertIn("rejected", row.group(0))
            self.assertNotIn("eligible review", row.group(0))
            suppressed_row = re.search(r"<tr><td>umg-subbrand-ember</td>.*?</tr>", body)
            self.assertIsNotNone(suppressed_row)
            self.assertIn("suppressed", suppressed_row.group(0))
            self.assertNotIn("pending", suppressed_row.group(0))
            self.assertNotIn("eligible review", suppressed_row.group(0))
            self.assertIn("after a restart those actions are unavailable", body)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertFalse(thread.is_alive())

    def test_existing_process_local_run_settles_durably_without_duplicate_projection(self) -> None:
        env = Phase4Env(self.state_dir / "existing-process-local-run")
        campaign = env.campaign()
        existing = env.repository.start_run(
            "noah", campaign["family_id"], campaign["version"], "existing-local-run"
        )
        before = process_local_state(env.repository)

        durable = env.run_to_completion(campaign, key="existing-local-run")
        attempt = env.store.attempts_for(durable["run_id"])[0]
        output = env.store.get_output(durable["run_id"])
        self.assertEqual(durable["state"], "succeeded")
        self.assertEqual(attempt["outcome"], "succeeded")
        self.assertIsNotNone(attempt["completed_at"])
        self.assertEqual(output["result_ids"], list(existing["output_ids"]))
        self.assertEqual(len(env.store.list_review_tasks({durable["business_unit"]})), 1)
        self.assertEqual(process_local_state(env.repository), before)


class SecurityAndPrivacyTests(Phase4TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.env = Phase4Env(self.state_dir)
        self.campaign = self.env.campaign()
        self.run = self.env.run_to_completion(self.campaign, key="security")

    def test_cross_business_unit_access_fails_closed(self) -> None:
        run_id = self.run["run_id"]
        for action in [
            lambda: self.env.service.get_run("dan", run_id),
            lambda: self.env.service.run_detail("dan", run_id),
            lambda: self.env.service.retry_run("dan", run_id),
            lambda: self.env.service.cancel_run("dan", run_id),
            lambda: self.env.service.list_runs("dan", "unreal-media-group"),
            lambda: self.env.service.review_tasks("dan", "unreal-media-group"),
            lambda: self.env.service.create_manual_run("dan", self.campaign["family_id"], 1, "cross-bu"),
        ]:
            with self.assertRaises(MissionControlError) as caught:
                action()
            self.assertEqual(caught.exception.status, 403)
        task = self.env.store.list_review_tasks({"unreal-media-group"})[0]
        with self.assertRaises(MissionControlError):
            self.env.service.get_review_task("dan", task["task_id"])

    def test_worker_cannot_appear_as_a_governed_review_actor(self) -> None:
        with self.assertRaisesRegex(MissionControlError, "not allowed"):
            self.env.repository.act(AGENT_ID, "unreal-media-group", "umg-new-orbit", "approve_deeper_research", {})
        task = self.env.store.list_review_tasks({"unreal-media-group"})[0]
        self.assertEqual(task["state"], "pending_review")
        self.assertNotIn(AGENT_ID, task["allowed_reviewers"])

    def test_stored_records_contain_no_private_or_unsafe_values(self) -> None:
        output = self.env.store.get_output(self.run["run_id"])
        serialized = json.dumps(output)
        self.assertIsNone(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", serialized), "email-like value stored")
        self.assertNotIn(str(self.env.state_path), serialized)
        for item in output["result_snapshot"]:
            self.assertTrue(item["domain"].endswith(".example"))
        run = self.env.service.get_run("noah", self.run["run_id"])
        self.assertNotIn(str(self.env.state_path), json.dumps({k: v for k, v in run.items() if isinstance(v, str)}))

    def test_module_boundaries_have_no_external_or_dynamic_execution(self) -> None:
        import ast

        forbidden = {"requests", "httpx", "socket", "smtplib", "subprocess", "sched", "asyncio", "multiprocessing"}
        for name in ["store.py", "agent.py"]:
            tree = ast.parse((APP_ROOT / "mission_control" / name).read_text(encoding="utf-8"))
            imports = {
                alias.name.split(".")[0]
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names
            }
            self.assertFalse(imports & forbidden, name)
            calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
            self.assertFalse(calls & {"eval", "exec", "compile", "__import__"}, name)


class HttpWorkflowTests(Phase4TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock()
        self.repository = FixtureRepository(clock=self.clock, next_id=CounterIds(), fixture_path=PHASE3_FIXTURE)
        self.control = MissionControl(self.repository)
        self.app = WebApplication(
            self.control,
            csrf_token="deterministic-csrf",
            state_path=self.state_dir / "http-state.sqlite3",
        )
        self.server = build_server(self.app, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())

    def request(self, method: str, path: str, fields: dict[str, str] | None = None) -> tuple[int, str]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        body = urlencode(fields or {}).encode() if fields is not None else None
        headers = {"Content-Type": "application/x-www-form-urlencoded"} if body is not None else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        text = response.read().decode()
        connection.close()
        return response.status, text

    def _create_campaign_and_run(self, key: str = "http-worker-run") -> str:
        fields = {
            "csrf_token": "deterministic-csrf",
            "actor": "noah",
            "business_unit": "unreal-media-group",
            "campaign_name": "Synthetic HTTP Worker Campaign",
            "discovery_scope": "open",
            "verticals": "",
            "target_prospect_count": "20",
            "minimum_qualification_score": "72",
            "cooldown_days": "120",
            "maximum_evidence_age_days": "180",
            "geography": "United States",
            "rights_territory": "",
            "talent_categories": "",
        }
        status, _ = self.request("POST", "/campaigns", fields)
        assert status == 201
        campaign = self.control.repository.campaigns("noah")[0]
        run_fields = {"csrf_token": "deterministic-csrf", "actor": "noah", "business_unit": "unreal-media-group", "idempotency_key": key}
        status, body = self.request("POST", f'/campaigns/{campaign["family_id"]}/1/run', run_fields)
        assert status == 200, body
        return body

    def test_manual_run_replay_conflict_and_run_pages_over_http(self) -> None:
        body = self._create_campaign_and_run()
        self.assertIn("Registered-agent manual run executed", body)
        self.assertIn("succeeded · review pending", body)
        self.assertIn("Skill Integrity", body)
        self.assertIn("Append-only attempt history", body)
        self.assertIn("Output manifest", body)
        self.assertIn("Bounded audit history", body)
        run = self.app.agent.store.list_runs({"unreal-media-group"})[0]
        # Idempotent replay over HTTP.
        campaign = self.control.repository.campaigns("noah")[0]
        run_fields = {"csrf_token": "deterministic-csrf", "actor": "noah", "business_unit": "unreal-media-group", "idempotency_key": "http-worker-run"}
        status, replay_body = self.request("POST", f'/campaigns/{campaign["family_id"]}/1/run', run_fields)
        self.assertEqual(status, 200)
        self.assertIn("Idempotent replay", replay_body)
        # Conflicting reuse of the key over HTTP fails safely.
        fields = {
            "csrf_token": "deterministic-csrf", "actor": "noah", "business_unit": "unreal-media-group",
            "campaign_name": "Synthetic Conflicting Campaign", "discovery_scope": "open", "verticals": "",
            "target_prospect_count": "20", "minimum_qualification_score": "72", "cooldown_days": "120",
            "maximum_evidence_age_days": "180", "geography": "United States", "rights_territory": "", "talent_categories": "",
        }
        status, _ = self.request("POST", "/campaigns", fields)
        self.assertEqual(status, 201)
        other = self.control.repository.campaigns("noah")[1]
        status, conflict_body = self.request("POST", f'/campaigns/{other["family_id"]}/1/run', run_fields)
        self.assertEqual(status, 409)
        self.assertIn("idempotency_conflict", conflict_body)
        self.assertNotIn("Traceback", conflict_body)
        # Worker-run and review-task pages render with safe metadata.
        status, list_body = self.request("GET", "/worker-runs?actor=noah&business_unit=unreal-media-group")
        self.assertEqual(status, 200)
        self.assertIn(run["run_id"], list_body)
        status, detail_body = self.request("GET", f'/worker-runs/{run["run_id"]}?actor=noah&business_unit=unreal-media-group')
        self.assertEqual(status, 200)
        for label in ["Cost Cap Usd", "Actual Cost Usd", "Timeout Seconds", "Retry Budget Remaining", "Idempotency Key", "Stop Reason"]:
            self.assertIn(label, detail_body)
        self.assertNotIn("sqlite3", detail_body)
        self.assertNotIn(str(self.state_dir), detail_body)
        status, tasks_body = self.request("GET", "/review-tasks?actor=noah&business_unit=unreal-media-group")
        self.assertEqual(status, 200)
        task = self.app.agent.store.list_review_tasks({"unreal-media-group"})[0]
        self.assertIn(task["task_id"], tasks_body)
        status, task_body = self.request("GET", f'/review-tasks/{task["task_id"]}?actor=noah&business_unit=unreal-media-group')
        self.assertEqual(status, 200)
        self.assertIn("cannot approve", task_body)

    def test_http_cross_business_unit_and_csrf_protection_for_worker_actions(self) -> None:
        self._create_campaign_and_run(key="http-secure")
        run = self.app.agent.store.list_runs({"unreal-media-group"})[0]
        status, body = self.request("GET", f'/worker-runs/{run["run_id"]}?actor=dan&business_unit=unreal-talent')
        self.assertEqual(status, 403)
        status, body = self.request("GET", "/worker-runs?actor=dan&business_unit=unreal-media-group")
        self.assertEqual(status, 403)
        fields = {"csrf_token": "wrong", "actor": "noah", "business_unit": "unreal-media-group"}
        status, body = self.request("POST", f'/worker-runs/{run["run_id"]}/retry', fields)
        self.assertEqual(status, 403)
        self.assertIn("CSRF validation failed", body)
        fields["csrf_token"] = "deterministic-csrf"
        status, body = self.request("POST", f'/worker-runs/{run["run_id"]}/retry', fields)
        self.assertEqual(status, 409)
        self.assertIn("already succeeded", body)
        fields.update({"actor": "dan", "business_unit": "unreal-talent"})
        status, body = self.request("POST", f'/worker-runs/{run["run_id"]}/cancel', fields)
        self.assertEqual(status, 403)


class GateExecutor:
    """Blocks between two checkpoints on deterministic events, so a second real
    HTTP client can observe and cancel the running attempt. No sleeps."""

    def __init__(self):
        self.started = threading.Event()
        self.proceed = threading.Event()

    def execute(self, run, checkpoint):
        checkpoint("bounded_step_one")
        self.started.set()
        assert self.proceed.wait(timeout=10), "test driver never released the gate"
        checkpoint("bounded_step_two")
        raise AssertionError("the cooperative cancellation checkpoint must interrupt execution")


class StaleReadStore(SqliteStore):
    """Simulates the lost find/create race deterministically: the first lookups
    report no run even though a concurrent identical create then wins."""

    def __init__(self, path, stale_reads: int = 0):
        super().__init__(path)
        self.stale_reads = stale_reads

    def find_run_by_key(self, idempotency_key):
        if self.stale_reads > 0:
            self.stale_reads -= 1
            return None
        return super().find_run_by_key(idempotency_key)


def fresh_environment(state_path: Path, *, executor=None, clock=None) -> Phase4Env:
    """A genuinely fresh process image: new repository, new control, new store
    over the same durable SQLite file, sharing no in-memory Phase 3 state."""
    env = Phase4Env.__new__(Phase4Env)
    env.clock = clock or FakeClock()
    env.repository = FixtureRepository(clock=env.clock, next_id=CounterIds(), fixture_path=PHASE3_FIXTURE)
    env.control = MissionControl(env.repository)
    env.state_path = state_path
    env.store = SqliteStore(state_path)
    env.service = RegisteredAgentService(env.repository, env.store, clock=env.clock, executor=executor)
    return env


class FreshProcessReplayTests(Phase4TestCase):
    """Defect 1: durable retryable runs must replay from persisted validated
    input in a fresh process, not from vanished Phase 3 in-memory state."""

    def _failed_run(self) -> tuple[Phase4Env, dict]:
        env = Phase4Env(self.state_dir)
        env.service.executor = FailingExecutor(env.repository, failures=1)
        campaign = env.campaign()
        run = env.run_to_completion(campaign, key="fresh-retry")
        self.assertEqual(run["state"], "failed_retryable")
        return env, run

    def test_fresh_process_manual_retry_replays_durable_input(self) -> None:
        old_env, run = self._failed_run()
        fresh = fresh_environment(old_env.state_path)
        # Evidence that no Phase 3 in-memory state is shared or reused.
        self.assertIsNot(fresh.repository, old_env.repository)
        self.assertEqual(fresh.repository.campaigns("noah"), [])
        self.assertEqual(fresh.repository.prospects("noah", "unreal-media-group"), [])
        retried = fresh.service.retry_run("noah", run["run_id"])
        self.assertEqual(retried["state"], "succeeded")
        attempts = fresh.store.attempts_for(run["run_id"])
        self.assertEqual([item["attempt_number"] for item in attempts], [1, 2])
        self.assertIsNotNone(fresh.store.get_output(run["run_id"]))
        self.assertEqual(len(fresh.store.list_review_tasks({"unreal-media-group"})), 1)
        # The durable snapshot rehydrated exactly one campaign version and ran
        # the adapter exactly once; server-owned routing was preserved.
        self.assertEqual(len(fresh.repository.campaign_versions), 1)
        rehydrated = fresh.repository.campaign_versions[0]
        self.assertEqual(rehydrated.configuration_hash, run["configuration_hash"])
        self.assertEqual(len(fresh.repository.run_records), 1)
        self.assertEqual(fresh.repository.run_records[0].skill_name, retried["skill_id"])

    def test_fresh_process_recovered_running_attempt_is_manually_retryable(self) -> None:
        env = Phase4Env(self.state_dir)
        campaign = env.campaign()
        run, _ = env.service.create_manual_run("noah", campaign["family_id"], 1, "fresh-recover")
        env.store.claim_attempt(run["run_id"], expected_states=("queued",), actor="noah", worker_version="test", now="2026-07-18T12:00:00Z")
        fresh = fresh_environment(env.state_path)
        self.assertEqual(fresh.service.recovered_run_ids, [run["run_id"]])
        recovered = fresh.service.run_detail("noah", run["run_id"])
        self.assertEqual(recovered["state"], "failed_retryable")
        self.assertEqual(len(recovered["attempts"]), 1)  # recovery never executes
        retried = fresh.service.retry_run("noah", run["run_id"])
        self.assertEqual(retried["state"], "succeeded")
        self.assertEqual(len(fresh.store.attempts_for(run["run_id"])), 2)
        self.assertEqual(len(fresh.store.list_review_tasks({"unreal-media-group"})), 1)

    def test_corrupted_durable_snapshot_fails_closed(self) -> None:
        old_env, run = self._failed_run()
        connection = sqlite3.connect(old_env.state_path)
        connection.execute(
            "UPDATE worker_runs SET configuration_snapshot = ? WHERE run_id = ?",
            ('{"business_unit":"unreal-media-group","tampered":true}', run["run_id"]),
        )
        connection.commit()
        connection.close()
        fresh = fresh_environment(old_env.state_path)
        tampered = fresh.service.retry_run("noah", run["run_id"])
        self.assertEqual(tampered["state"], "failed_terminal")
        self.assertEqual(tampered["failure_class"], "invalid_input")
        self.assertIsNone(fresh.store.get_output(run["run_id"]))
        self.assertEqual(fresh.repository.campaign_versions, [])

    def test_changed_skill_content_fails_closed_as_unsupported_version(self) -> None:
        old_env, run = self._failed_run()
        fresh = fresh_environment(old_env.state_path)
        fresh.service.executor = FixtureWorkerExecutor(fresh.repository, integrity=lambda skill_id: "0" * 64)
        mismatched = fresh.service.retry_run("noah", run["run_id"])
        self.assertEqual(mismatched["state"], "failed_terminal")
        self.assertEqual(mismatched["failure_class"], "unsupported_skill_version")
        self.assertIsNone(fresh.store.get_output(run["run_id"]))

    def test_same_process_retry_rechecks_changed_skill_content(self) -> None:
        env, run = self._failed_run()
        env.service.executor = FixtureWorkerExecutor(
            env.repository, integrity=env.service._integrity
        )
        with patch("mission_control.agent.skill_integrity_hash", return_value="0" * 64):
            mismatched = env.service.retry_run("noah", run["run_id"])
        self.assertEqual(mismatched["state"], "failed_terminal")
        self.assertEqual(mismatched["failure_class"], "unsupported_skill_version")
        self.assertIsNone(env.store.get_output(run["run_id"]))


class FreshProcessInspectionTests(Phase4TestCase):
    """Defect 2: durable outputs and review tasks must stay inspectable through
    the real application routes after a fresh process restart."""

    def test_durable_output_and_review_task_inspectable_after_restart(self) -> None:
        old_env = Phase4Env(self.state_dir)
        run = old_env.run_to_completion(old_env.campaign(), key="restart-inspect")
        self.assertEqual(run["state"], "succeeded")
        # Fresh process image over the same durable state file.
        clock = FakeClock()
        repository = FixtureRepository(clock=clock, next_id=CounterIds(), fixture_path=PHASE3_FIXTURE)
        control = MissionControl(repository)
        app = WebApplication(control, csrf_token="deterministic-csrf", state_path=old_env.state_path)
        server = build_server(app, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]

            def get(path):
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
                connection.request("GET", path)
                response = connection.getresponse()
                text = response.read().decode()
                connection.close()
                return response.status, text

            status, detail = get(f'/worker-runs/{run["run_id"]}?actor=noah&business_unit=unreal-media-group')
            self.assertEqual(status, 200)
            self.assertIn("Durable validated result snapshot", detail)
            self.assertIn("Synthetic Orbit Collective", detail)
            self.assertIn("remains inspectable after an application restart", detail)
            self.assertIn("after a restart those actions are unavailable", detail)
            task = app.agent.store.list_review_tasks({"unreal-media-group"})[0]
            status, task_page = get(f'/review-tasks/{task["task_id"]}?actor=noah&business_unit=unreal-media-group')
            self.assertEqual(status, 200)
            self.assertIn("Durable validated result snapshot", task_page)
            self.assertIn("Synthetic Orbit Collective", task_page)
            self.assertIn("cannot approve", task_page)
            # The process-local queue really is empty, and the page says which
            # review surface is which instead of dead-linking the user.
            status, queue_page = get("/prospects?actor=noah&business_unit=unreal-media-group&queue=new")
            self.assertEqual(status, 200)
            self.assertIn("This queue is empty", queue_page)
            # Business-unit isolation holds for the durable projection too.
            status, _ = get(f'/worker-runs/{run["run_id"]}?actor=dan&business_unit=unreal-talent')
            self.assertEqual(status, 403)
            status, _ = get(f'/review-tasks/{task["task_id"]}?actor=dan&business_unit=unreal-talent')
            self.assertEqual(status, 403)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertFalse(thread.is_alive())

    def test_tampered_durable_snapshot_is_rejected_by_store_and_web_route(self) -> None:
        env = Phase4Env(self.state_dir / "tampered-output")
        run = env.run_to_completion(env.campaign(), key="tampered-output")
        stored = env.store.get_output(run["run_id"])
        tampered = json.dumps(
            [{
                "account_name": "Tampered Account",
                "domain": "tampered.example",
                "prospect_id": "tampered-id",
            }],
            sort_keys=True,
            separators=(",", ":"),
        )
        connection = sqlite3.connect(env.state_path)
        try:
            connection.execute(
                "UPDATE worker_outputs SET result_snapshot = ? WHERE run_id = ?",
                (tampered, run["run_id"]),
            )
            connection.commit()
            unchanged = connection.execute(
                "SELECT content_hash, byte_length FROM worker_outputs WHERE run_id = ?",
                (run["run_id"],),
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(unchanged, (stored["content_hash"], stored["byte_length"]))
        with self.assertRaises(MissionControlError) as caught:
            env.store.get_output(run["run_id"])
        self.assertEqual(caught.exception.status, 500)
        self.assertNotIn("Tampered", caught.exception.message)
        self.assertNotIn("sqlite", caught.exception.message.casefold())
        self.assertNotIn("/", caught.exception.message)
        self.assertEqual(env.store.get_run(run["run_id"])["state"], "succeeded")

        app = WebApplication(
            MissionControl(FixtureRepository(
                clock=FakeClock(), next_id=CounterIds(), fixture_path=PHASE3_FIXTURE
            )),
            csrf_token="deterministic-csrf",
            state_path=env.state_path,
        )
        server = build_server(app, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection(
                "127.0.0.1", server.server_address[1], timeout=3
            )
            connection.request(
                "GET",
                f'/worker-runs/{run["run_id"]}?actor=noah&business_unit=unreal-media-group',
            )
            response = connection.getresponse()
            body = response.read().decode()
            connection.close()
            self.assertEqual(response.status, 500)
            self.assertIn("Stored result snapshot failed its integrity check", body)
            self.assertNotIn("Tampered Account", body)
            self.assertNotIn("UPDATE worker_outputs", body)
            self.assertNotIn("Traceback", body)
            self.assertNotIn(str(env.state_path), body)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(env.store.get_run(run["run_id"])["state"], "succeeded")


class IdempotencyIsolationTests(Phase4TestCase):
    """Defect 3: a foreign-business-unit key collision must not append to,
    alter, or identify the existing run or its audit history."""

    def test_cross_unit_key_collision_leaves_foreign_run_untouched(self) -> None:
        env = Phase4Env(self.state_dir)
        umg_campaign = env.campaign("phase4-umg-success")
        umg_run = env.run_to_completion(umg_campaign, key="shared-key")
        talent_campaign = env.campaign("phase4-talent-success", actor="dan")
        audits_before = env.store.audits_for(umg_run["run_id"])
        with self.assertRaises(MissionControlError) as caught:
            env.service.create_manual_run("dan", talent_campaign["family_id"], 1, "shared-key")
        self.assertEqual(caught.exception.status, 409)
        self.assertIn("idempotency_conflict", caught.exception.message)
        self.assertNotIn(umg_run["run_id"], caught.exception.message)
        # The foreign run's audit history is byte-identical.
        self.assertEqual(env.store.audits_for(umg_run["run_id"]), audits_before)
        # The rejection fact exists but is unlinked and scoped to the caller.
        connection = sqlite3.connect(env.state_path)
        connection.row_factory = sqlite3.Row
        unlinked = connection.execute(
            "SELECT * FROM audit_events WHERE event_type = 'idempotency_conflict' AND run_id IS NULL"
        ).fetchall()
        connection.close()
        self.assertEqual(len(unlinked), 1)
        self.assertEqual(unlinked[0]["actor"], "dan")
        self.assertEqual(unlinked[0]["business_unit"], "unreal-talent")

    def test_same_unit_authorized_collision_still_links_the_conflict(self) -> None:
        env = Phase4Env(self.state_dir)
        first = env.run_to_completion(env.campaign(), key="linked-key")
        other = env.campaign("phase4-no-results")
        with self.assertRaises(MissionControlError):
            env.service.create_manual_run("noah", other["family_id"], other["version"], "linked-key")
        events = [item["event_type"] for item in env.store.audits_for(first["run_id"])]
        self.assertIn("idempotency_conflict", events)

    def test_http_cross_unit_key_collision_is_isolated(self) -> None:
        env = Phase4Env(self.state_dir)
        umg_run = env.run_to_completion(env.campaign(), key="http-shared-key")
        talent_campaign = env.campaign("phase4-talent-success", actor="dan")
        audits_before = env.store.audits_for(umg_run["run_id"])
        app = WebApplication(env.control, csrf_token="deterministic-csrf", agent_service=env.service)
        server = build_server(app, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            body = urlencode({
                "csrf_token": "deterministic-csrf", "actor": "dan", "business_unit": "unreal-talent",
                "idempotency_key": "http-shared-key",
            }).encode()
            connection.request("POST", f'/campaigns/{talent_campaign["family_id"]}/1/run', body=body,
                               headers={"Content-Type": "application/x-www-form-urlencoded"})
            response = connection.getresponse()
            text = response.read().decode()
            connection.close()
            self.assertEqual(response.status, 409)
            self.assertIn("idempotency_conflict", text)
            self.assertNotIn(umg_run["run_id"], text)
            self.assertEqual(env.store.audits_for(umg_run["run_id"]), audits_before)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


class ConcurrentCreationTests(Phase4TestCase):
    """Defect 4: simultaneous submissions must resolve as one run plus a replay
    or a safe conflict — never a 500 or a duplicate."""

    def test_lost_find_create_race_resolves_as_idempotent_replay(self) -> None:
        # Deterministic replay of the exact race: the loser's lookup was stale,
        # its insert collides, and the service must return the existing run.
        env = Phase4Env.__new__(Phase4Env)
        env.clock = FakeClock()
        env.repository = FixtureRepository(clock=env.clock, next_id=CounterIds(), fixture_path=PHASE3_FIXTURE)
        env.control = MissionControl(env.repository)
        env.state_path = self.state_dir / "stale.sqlite3"
        env.store = StaleReadStore(env.state_path)
        env.service = RegisteredAgentService(env.repository, env.store, clock=env.clock)
        campaign = env.campaign()
        first, created_first = env.service.create_manual_run("noah", campaign["family_id"], 1, "race-key")
        self.assertTrue(created_first)
        env.store.stale_reads = 1  # the next find misses the row it would have seen
        second, created_second = env.service.create_manual_run("noah", campaign["family_id"], 1, "race-key")
        self.assertFalse(created_second)
        self.assertEqual(second["run_id"], first["run_id"])
        self.assertEqual(len(env.store.list_runs({"unreal-media-group"})), 1)
        events = [item["event_type"] for item in env.store.audits_for(first["run_id"])]
        self.assertIn("idempotent_replay", events)

    def test_two_threads_identical_create_one_run_one_replay_no_500(self) -> None:
        env = Phase4Env(self.state_dir)
        campaign = env.campaign()
        barrier = threading.Barrier(2)
        outcomes: list[tuple[str, object]] = []

        def submit() -> None:
            barrier.wait(timeout=5)
            try:
                run, created = env.service.create_manual_run("noah", campaign["family_id"], 1, "thread-key")
                outcomes.append(("ok", (run["run_id"], created)))
            except MissionControlError as exc:
                outcomes.append(("error", exc.status))

        threads = [threading.Thread(target=submit) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
        self.assertEqual([kind for kind, _ in outcomes], ["ok", "ok"], outcomes)
        run_ids = {value[0] for _, value in outcomes}
        created_flags = sorted(value[1] for _, value in outcomes)
        self.assertEqual(len(run_ids), 1)
        self.assertEqual(created_flags, [False, True])
        self.assertEqual(len(env.store.list_runs({"unreal-media-group"})), 1)

    def test_two_threads_conflicting_create_safe_conflict_no_500(self) -> None:
        env = Phase4Env(self.state_dir)
        first_campaign = env.campaign()
        second_campaign = env.campaign("phase4-no-results")
        barrier = threading.Barrier(2)
        outcomes: list[tuple[str, object]] = []

        def submit(family_id: str) -> None:
            barrier.wait(timeout=5)
            try:
                run, created = env.service.create_manual_run("noah", family_id, 1, "conflict-thread-key")
                outcomes.append(("ok", created))
            except MissionControlError as exc:
                outcomes.append(("error", exc.status))

        threads = [
            threading.Thread(target=submit, args=(first_campaign["family_id"],)),
            threading.Thread(target=submit, args=(second_campaign["family_id"],)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
        kinds = sorted(kind for kind, _ in outcomes)
        self.assertEqual(kinds, ["error", "ok"], outcomes)
        error_status = next(value for kind, value in outcomes if kind == "error")
        self.assertEqual(error_status, 409)
        self.assertEqual(len(env.store.list_runs({"unreal-media-group"})), 1)


class HttpCancellationTests(Phase4TestCase):
    """Defect 5: an authorized human must be able to observe and cancel a
    running bounded attempt through the real loopback HTTP surface."""

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock()
        self.repository = FixtureRepository(clock=self.clock, next_id=CounterIds(), fixture_path=PHASE3_FIXTURE)
        self.control = MissionControl(self.repository)
        self.gate = GateExecutor()
        store = SqliteStore(self.state_dir / "cancel.sqlite3")
        service = RegisteredAgentService(self.repository, store, clock=self.clock, executor=self.gate)
        self.app = WebApplication(self.control, csrf_token="deterministic-csrf", agent_service=service)
        self.server = build_server(self.app, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self) -> None:
        self.gate.proceed.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())

    def request(self, method: str, path: str, fields: dict[str, str] | None = None) -> tuple[int, str]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        body = urlencode(fields or {}).encode() if fields is not None else None
        headers = {"Content-Type": "application/x-www-form-urlencoded"} if body is not None else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        text = response.read().decode()
        connection.close()
        return response.status, text

    def test_real_http_cancellation_wins_exactly_once_while_running(self) -> None:
        config = self.control.campaign_config({
            "business_unit": "unreal-media-group", "campaign_name": "Synthetic Cancel Campaign",
            "discovery_scope": "open", "verticals": "", "target_prospect_count": "20",
            "minimum_qualification_score": "72", "cooldown_days": "120",
            "maximum_evidence_age_days": "180", "geography": "United States",
            "rights_territory": "", "talent_categories": "",
        })
        campaign = self.repository.add_campaign("noah", config)
        run_response: list[tuple[int, str]] = []

        def start_run() -> None:
            run_response.append(self.request("POST", f'/campaigns/{campaign["family_id"]}/1/run', {
                "csrf_token": "deterministic-csrf", "actor": "noah",
                "business_unit": "unreal-media-group", "idempotency_key": "http-cancel-run",
            }))

        runner = threading.Thread(target=start_run)
        runner.start()
        self.assertTrue(self.gate.started.wait(timeout=10), "the attempt never reached its gate")
        # A second real client observes the running attempt...
        status, listing = self.request("GET", "/worker-runs?actor=noah&business_unit=unreal-media-group")
        self.assertEqual(status, 200)
        self.assertIn("running", listing)
        status, detail = self.request("GET", "/worker-runs/wrun-0001?actor=noah&business_unit=unreal-media-group")
        self.assertEqual(status, 200)
        self.assertIn("Cancel this run", detail)
        # ...and cancels it while it is running.
        status, cancel_page = self.request("POST", "/worker-runs/wrun-0001/cancel", {
            "csrf_token": "deterministic-csrf", "actor": "noah", "business_unit": "unreal-media-group",
        })
        self.assertEqual(status, 200)
        self.assertIn("Cancellation recorded", cancel_page)
        self.gate.proceed.set()
        runner.join(timeout=10)
        self.assertFalse(runner.is_alive())
        status, body = run_response[0]
        self.assertEqual(status, 200)
        self.assertIn("cancelled", body)
        run = self.app.agent.store.get_run("wrun-0001")
        self.assertEqual(run["state"], "cancelled")
        self.assertIsNone(self.app.agent.store.get_output("wrun-0001"))
        self.assertEqual(self.app.agent.store.list_review_tasks({"unreal-media-group"}), [])
        events = [item["event_type"] for item in self.app.agent.store.audits_for("wrun-0001")]
        self.assertEqual(events.count("cancellation_requested"), 1)
        self.assertEqual(events.count("cancellation_completed"), 1)
        attempts = self.app.agent.store.attempts_for("wrun-0001")
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["outcome"], "cancelled")


class RetryClaimSemanticsTests(Phase4TestCase):
    """Defect 6: retry transitions must clear stale terminal metadata and emit
    only truthful, atomic audit facts."""

    def _failed_env(self, name: str, fault: FaultInjector | None = None) -> tuple[Phase4Env, dict]:
        env = Phase4Env(self.state_dir / name, fault_hook=fault)
        env.service.executor = FailingExecutor(env.repository, failures=1)
        campaign = env.campaign()
        run = env.run_to_completion(campaign, key=f"retry-{name}")
        self.assertEqual(run["state"], "failed_retryable")
        return env, run

    def test_retry_claim_clears_stale_completion_metadata(self) -> None:
        env, run = self._failed_env("metadata")
        self.assertIsNotNone(run["completed_at"])
        first_started_at = run["started_at"]
        claim = env.store.claim_attempt(
            run["run_id"], expected_states=("failed_retryable", "timed_out"),
            actor="noah", worker_version="test", now="2026-07-18T12:05:00Z", retry_accepted=True,
        )
        self.assertEqual(claim["attempt_number"], 2)
        claimed = env.store.get_run(run["run_id"])
        self.assertEqual(claimed["state"], "running")
        self.assertIsNone(claimed["completed_at"])
        self.assertIsNone(claimed["failure_class"])
        self.assertEqual(claimed["started_at"], first_started_at)  # first start preserved
        events = [item["event_type"] for item in env.store.audits_for(run["run_id"])]
        self.assertEqual(events.count("retry_accepted"), 1)

    def test_lost_retry_claim_leaves_no_acceptance_audit(self) -> None:
        env, run = self._failed_env("lost-claim")
        first = env.store.claim_attempt(
            run["run_id"], expected_states=("failed_retryable", "timed_out"),
            actor="noah", worker_version="test", now="2026-07-18T12:05:00Z", retry_accepted=True,
        )
        self.assertIsNotNone(first)
        second = env.store.claim_attempt(
            run["run_id"], expected_states=("failed_retryable", "timed_out"),
            actor="noah", worker_version="test", now="2026-07-18T12:05:01Z", retry_accepted=True,
        )
        self.assertIsNone(second)
        events = [item["event_type"] for item in env.store.audits_for(run["run_id"])]
        self.assertEqual(events.count("retry_accepted"), 1)
        self.assertEqual(len(env.store.attempts_for(run["run_id"])), 2)

    def test_retry_audit_fault_rolls_back_acceptance_and_attempt(self) -> None:
        fault = FaultInjector()
        env, run = self._failed_env("audit-fault", fault)
        fault.armed = "insert_audit"
        with self.assertRaisesRegex(MissionControlError, "rolled back"):
            env.service.retry_run("noah", run["run_id"])
        current = env.store.get_run(run["run_id"])
        self.assertEqual(current["state"], "failed_retryable")
        self.assertEqual(current["attempt_count"], 1)
        self.assertIsNotNone(current["completed_at"])
        events = [item["event_type"] for item in env.store.audits_for(run["run_id"])]
        self.assertNotIn("retry_accepted", events)
        self.assertEqual(len(env.store.attempts_for(run["run_id"])), 1)
        # After the transient fault clears, the same manual retry succeeds.
        env.service.executor = FixtureWorkerExecutor(env.repository)
        retried = env.service.retry_run("noah", run["run_id"])
        self.assertEqual(retried["state"], "succeeded")


def _minimal_output() -> dict:
    return {
        "output_schema": "phase3-review-projection@1",
        "content_hash": "0" * 64,
        "byte_length": 2,
        "fixture_source_ids": [],
        "result_ids": [],
        "estimated_cost_usd": 0,
        "errors": [],
        "stop_reason": "synthetic",
        "result_snapshot": [],
    }


if __name__ == "__main__":
    unittest.main()

"""Phase 5 weekly shadow-loop regressions.

All execution is deterministic, synthetic, zero-cost, SQLite-local, and driven
by injected clocks/events. Tests never sleep or contact an external system.
"""

from __future__ import annotations

import copy
import hashlib
import http.client
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = ROOT / "apps" / "prospecting-mission-control"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from mission_control.agent import RegisteredAgentService  # noqa: E402
from mission_control.application import CounterIds, FixtureRepository, MissionControl, MissionControlError  # noqa: E402
from mission_control.shadow import ShadowLoopService, ShadowScheduler, weekly_due_at_or_after  # noqa: E402
from mission_control.store import PHASE4_TABLES, SCHEMA_VERSION, SqliteStore  # noqa: E402
from mission_control.web import WebApplication, build_server  # noqa: E402

FIXED = datetime(2026, 7, 20, 9, 30, tzinfo=timezone.utc)  # Monday
PHASE3_FIXTURE = ROOT / "fixtures" / "prospecting" / "phase3" / "prospects.json"
PHASE5_HISTORY = ROOT / "fixtures" / "prospecting" / "phase5" / "history-seeds.json"


class Clock:
    def __init__(self, value: datetime = FIXED):
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def set(self, value: datetime) -> None:
        self.value = value


class FaultInjector:
    def __init__(self) -> None:
        self.armed: str | None = None

    def __call__(self, label: str) -> None:
        if self.armed == label:
            self.armed = None
            raise sqlite3.OperationalError("synthetic storage fault")


class GatedScheduledRetryExecutor:
    def __init__(self, delegate, retry_path: dict, condition: threading.Condition):
        self.delegate = delegate
        self.retry_path = retry_path
        self.condition = condition
        self.release_retry = threading.Event()
        self.calls = 0

    def execute(self, run, checkpoint):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("synthetic first-attempt failure")
        with self.condition:
            self.retry_path["value"] = "claimed"
            self.condition.notify_all()
        if not self.release_retry.wait(5):
            raise RuntimeError("scheduled retry gate timed out")
        return self.delegate.execute(run, checkpoint)


class Phase5Env:
    def __init__(self, directory: Path, *, clock: Clock | None = None, history_path: Path = PHASE5_HISTORY):
        self.clock = clock or Clock()
        self.repository = FixtureRepository(self.clock, CounterIds(), PHASE3_FIXTURE)
        self.control = MissionControl(self.repository)
        self.path = directory / "phase5.sqlite3"
        self.store = SqliteStore(self.path)
        self.agent = RegisteredAgentService(self.repository, self.store, clock=self.clock)
        self.loop = ShadowLoopService(
            self.store,
            self.agent,
            clock=self.clock,
            history_seed_path=history_path,
        )

    def campaign(self, name: str, *, unit: str = "unreal-media-group", scope: str = "open", verticals: str = "") -> dict:
        config = self.control.campaign_config({
            "business_unit": unit,
            "campaign_name": name,
            "discovery_scope": scope,
            "verticals": verticals,
            "target_prospect_count": "20",
            "minimum_qualification_score": "72" if unit == "unreal-media-group" else "78",
            "cooldown_days": "120" if unit == "unreal-media-group" else "180",
            "maximum_evidence_age_days": "180",
            "geography": "United States",
            "rights_territory": "United States" if unit == "unreal-talent" else "",
            "talent_categories": "athlete archetype" if unit == "unreal-talent" else "",
        })
        return self.repository.add_campaign("noah", config)

    def schedule(self, campaigns: list[dict], **overrides) -> dict:
        values = {
            "actor": "noah",
            "business_unit": campaigns[0]["business_unit"],
            "name": "Synthetic weekly shadow rotation",
            "campaign_refs": [(item["family_id"], item["version"]) for item in campaigns],
            "weekday": 0,
            "utc_hour": 9,
            "utc_minute": 30,
            "prospect_cap": 10,
            "open_discovery_every": 0,
        }
        values.update(overrides)
        return self.loop.create_schedule(**values)


class Phase5Case(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)


class CadenceAndControlTests(Phase5Case):
    def test_disabled_by_default_and_exact_weekly_utc_boundary(self) -> None:
        env = Phase5Env(self.directory)
        campaign = env.campaign("Open")
        schedule = env.schedule([campaign])
        self.assertEqual(schedule["state"], "disabled")
        self.assertIsNone(schedule["next_due_at"])
        self.assertEqual(env.loop.evaluate_due(), [])
        self.assertEqual(weekly_due_at_or_after(FIXED, 0, 9, 30), FIXED)
        self.assertEqual(
            weekly_due_at_or_after(FIXED + timedelta(microseconds=1), 0, 9, 30),
            FIXED + timedelta(days=7),
        )
        self.assertEqual(
            env.agent.registration()["scheduled_shadow_trigger"],
            "explicitly enabled local weekly schedule occurrence only",
        )

    def test_explicit_enable_pause_resume_disable_are_atomic_and_audited(self) -> None:
        env = Phase5Env(self.directory)
        schedule = env.schedule([env.campaign("Open")])
        schedule = env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        self.assertEqual(schedule["state"], "enabled")
        self.assertEqual(schedule["next_due_at"], "2026-07-20T09:30:00Z")
        schedule = env.loop.pause("noah", schedule["schedule_id"], schedule["row_version"])
        self.assertEqual(schedule["state"], "paused")
        self.assertEqual(env.loop.evaluate_due(), [])
        schedule = env.loop.resume("noah", schedule["schedule_id"], schedule["row_version"])
        self.assertEqual(schedule["state"], "enabled")
        schedule = env.loop.disable("noah", schedule["schedule_id"], schedule["row_version"])
        self.assertEqual(schedule["state"], "disabled")
        self.assertIsNone(schedule["next_due_at"])
        events = [item["event_type"] for item in env.loop.schedule_detail("noah", schedule["schedule_id"])["audits"]]
        self.assertEqual(events, ["schedule_created", "schedule_enabled", "schedule_paused", "schedule_resumed", "schedule_disabled"])

    def test_rotation_uses_filtered_versions_and_configured_open_weeks(self) -> None:
        env = Phase5Env(self.directory)
        open_campaign = env.campaign("Open", scope="open")
        fitness = env.campaign("Fitness", scope="filtered", verticals="fitness")
        beauty = env.campaign("Beauty", scope="filtered", verticals="beauty")
        schedule = env.schedule([fitness, beauty, open_campaign], open_discovery_every=3)
        schedule = env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        selected = []
        for week in range(3):
            env.clock.set(FIXED + timedelta(days=7 * week))
            occurrence = env.loop.evaluate_due()[0]
            selected.append((occurrence["campaign_family_id"], occurrence["discovery_scope"]))
        self.assertEqual(selected, [
            (fitness["family_id"], "filtered"),
            (beauty["family_id"], "filtered"),
            (open_campaign["family_id"], "open"),
        ])

    def test_scheduled_request_rejections_use_scheduled_audit_truth(self) -> None:
        env = Phase5Env(self.directory)
        campaign = env.campaign("Open")
        with self.assertRaisesRegex(MissionControlError, "idempotency key"):
            env.agent.create_shadow_run(
                "noah", campaign["family_id"], campaign["version"], "invalid key",
                occurrence_id="occurrence-not-created",
            )
        connection = env.store._connect()
        try:
            events = [row[0] for row in connection.execute("SELECT event_type FROM audit_events")]
        finally:
            connection.close()
        self.assertEqual(events, ["shadow_occurrence_rejected"])
        schedule = env.schedule([campaign])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        occurrence = env.loop.evaluate_due()[0]
        self.assertEqual(
            env.store.audits_for(occurrence["worker_run_id"])[0]["event_type"],
            "shadow_occurrence_accepted",
        )


class OccurrenceAndHistoryTests(Phase5Case):
    def test_repeated_and_concurrent_ticks_create_one_occurrence_and_one_run(self) -> None:
        env = Phase5Env(self.directory)
        schedule = env.schedule([env.campaign("Open")])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        barrier = threading.Barrier(3)
        results: list[list[dict]] = []

        def tick() -> None:
            barrier.wait()
            results.append(env.loop.evaluate_due())

        threads = [threading.Thread(target=tick) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        occurrences = env.loop.occurrences("noah", "unreal-media-group")
        self.assertEqual(len(occurrences), 1)
        self.assertEqual(sum(len(value) for value in results), 1)
        self.assertEqual(len(env.store.list_runs({"unreal-media-group"})), 1)
        self.assertEqual(occurrences[0]["state"], "completed")

    def test_two_service_instances_share_the_durable_claim_gate(self) -> None:
        env = Phase5Env(self.directory)
        schedule = env.schedule([env.campaign("Open")])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        other_store = SqliteStore(env.path)
        other_agent = RegisteredAgentService(env.repository, other_store, clock=env.clock)
        other_loop = ShadowLoopService(
            other_store, other_agent, clock=env.clock, history_seed_path=PHASE5_HISTORY
        )
        barrier = threading.Barrier(3)
        results: list[list[dict]] = []
        errors: list[Exception] = []

        def tick(loop: ShadowLoopService) -> None:
            try:
                barrier.wait()
                results.append(loop.evaluate_due())
            except Exception as exc:  # captured for assertion in the test thread
                errors.append(exc)

        threads = [
            threading.Thread(target=tick, args=(loop,))
            for loop in (env.loop, other_loop)
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(sum(len(value) for value in results), 1)
        occurrences = env.store.list_shadow_occurrences({"unreal-media-group"})
        runs = env.store.list_runs({"unreal-media-group"})
        self.assertEqual(len(occurrences), 1)
        self.assertEqual(occurrences[0]["state"], "completed")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["state"], "succeeded")
        self.assertEqual(occurrences[0]["worker_run_id"], runs[0]["run_id"])

    def test_restart_persists_state_and_reconciles_at_most_one_missed_occurrence(self) -> None:
        env = Phase5Env(self.directory)
        schedule = env.schedule([env.campaign("Open")])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        env.clock.set(FIXED + timedelta(days=35))
        first = env.loop.evaluate_due()
        self.assertEqual(len(first), 1)
        reopened_repository = FixtureRepository(env.clock, CounterIds(), PHASE3_FIXTURE)
        reopened_store = SqliteStore(env.path)
        reopened_agent = RegisteredAgentService(reopened_repository, reopened_store, clock=env.clock)
        reopened = ShadowLoopService(reopened_store, reopened_agent, clock=env.clock, history_seed_path=PHASE5_HISTORY)
        self.assertEqual(reopened.evaluate_due(), [])
        current = reopened.get_schedule("noah", schedule["schedule_id"])
        self.assertGreater(datetime.fromisoformat(current["next_due_at"].replace("Z", "+00:00")), env.clock())

    def test_restart_closes_an_interrupted_occurrence_without_partial_output(self) -> None:
        env = Phase5Env(self.directory)
        schedule = env.schedule([env.campaign("Open")])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        claimed = env.loop.claim_due()
        self.assertEqual(claimed["state"], "claimed")

        restarted_agent = RegisteredAgentService(env.repository, SqliteStore(env.path), clock=env.clock)
        restarted = ShadowLoopService(
            restarted_agent.store,
            restarted_agent,
            clock=env.clock,
            history_seed_path=PHASE5_HISTORY,
        )
        recovered = restarted.occurrences("noah", "unreal-media-group")[0]
        self.assertEqual(recovered["state"], "failed")
        self.assertEqual(recovered["failure_class"], "interrupted_shadow_recovered")
        self.assertIsNone(recovered["worker_run_id"])
        self.assertEqual(len(restarted.alerts("noah", "unreal-media-group")), 1)

    def test_recovery_never_links_a_manual_run_with_the_occurrence_key(self) -> None:
        env = Phase5Env(self.directory)
        campaign = env.campaign("Open")
        schedule = env.schedule([campaign])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        claimed = env.loop.claim_due()
        manual_run, created = env.agent.create_manual_run(
            "noah", campaign["family_id"], campaign["version"], claimed["idempotency_key"]
        )
        self.assertTrue(created)

        restarted_store = SqliteStore(env.path)
        restarted_agent = RegisteredAgentService(env.repository, restarted_store, clock=env.clock)
        restarted_loop = ShadowLoopService(
            restarted_store, restarted_agent, clock=env.clock, history_seed_path=PHASE5_HISTORY
        )
        recovered = restarted_loop.occurrences("noah", "unreal-media-group")[0]
        self.assertEqual(recovered["state"], "failed")
        self.assertIsNone(recovered["worker_run_id"])
        completed_manual = restarted_agent.execute_run("noah", manual_run["run_id"])
        self.assertEqual(completed_manual["state"], "succeeded")

    def test_missing_corrupt_and_inconsistent_history_stop_before_worker_execution(self) -> None:
        missing = Phase5Env(self.directory / "missing", history_path=self.directory / "absent.json")
        campaign = missing.campaign("Open")
        schedule = missing.schedule([campaign])
        missing.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        occurrence = missing.loop.evaluate_due()[0]
        self.assertEqual(occurrence["state"], "blocked")
        self.assertEqual(occurrence["failure_class"], "history_unavailable")
        self.assertEqual(missing.store.list_runs({"unreal-media-group"}), [])

        bad_path = self.directory / "bad.json"
        bad_path.write_text(json.dumps({"unreal-media-group": {"version": 1, "generated_at": "bad", "prospects": []}}))
        corrupt = Phase5Env(self.directory / "corrupt", history_path=bad_path)
        campaign = corrupt.campaign("Open")
        schedule = corrupt.schedule([campaign])
        corrupt.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        occurrence = corrupt.loop.evaluate_due()[0]
        self.assertEqual(occurrence["failure_class"], "history_invalid")
        self.assertEqual(corrupt.store.list_runs({"unreal-media-group"}), [])

    def test_unreadable_history_terminalizes_claim_alerts_and_keeps_scheduler_alive(self) -> None:
        history_directory = self.directory / "history-directory"
        history_directory.mkdir()
        env = Phase5Env(self.directory / "unreadable", history_path=history_directory)
        schedule = env.schedule([env.campaign("Open")])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        evaluated = threading.Event()
        original_evaluate = env.loop.evaluate_due

        def evaluate(actor: str = "noah") -> list[dict]:
            try:
                return original_evaluate(actor)
            finally:
                evaluated.set()

        env.loop.evaluate_due = evaluate
        app = WebApplication(
            env.control, csrf_token="phase5-csrf", agent_service=env.agent,
            shadow_service=env.loop,
        )
        server = build_server(app, port=0)
        server_thread = threading.Thread(target=server.serve_forever)
        scheduler = ShadowScheduler(env.loop, actor="noah")
        server_thread.start()
        scheduler.start()
        try:
            self.assertTrue(evaluated.wait(2), "scheduler did not evaluate the due occurrence")
            self.assertTrue(scheduler.is_alive(), "unreadable history terminated the scheduler thread")
            host, port = server.server_address
            connection = http.client.HTTPConnection(host, port, timeout=2)
            try:
                connection.request(
                    "GET", "/shadow-schedules?actor=noah&business_unit=unreal-media-group"
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertIn("history_unavailable", response.read().decode("utf-8"))
            finally:
                connection.close()
        finally:
            server.shutdown()
            server.server_close()
            scheduler.stop()
            scheduler.join(timeout=2)
            server_thread.join(timeout=2)
        self.assertFalse(scheduler.is_alive())
        self.assertFalse(server_thread.is_alive())
        occurrence = env.loop.occurrences("noah", "unreal-media-group")[0]
        self.assertEqual(occurrence["state"], "blocked")
        self.assertEqual(occurrence["failure_class"], "history_unavailable")
        self.assertIsNone(occurrence["worker_run_id"])
        self.assertEqual(env.store.list_runs({"unreal-media-group"}), [])
        self.assertEqual(len(env.loop.alerts("noah", "unreal-media-group")), 1)

    def test_durable_prior_identity_is_not_rediscovered_as_new(self) -> None:
        env = Phase5Env(self.directory)
        campaign = env.campaign("Open")
        schedule = env.schedule([campaign])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        first = env.loop.evaluate_due()[0]
        env.clock.set(FIXED + timedelta(days=7))
        second = env.loop.evaluate_due()[0]
        first_output = env.store.get_output(first["worker_run_id"])
        second_output = env.store.get_output(second["worker_run_id"])
        first_new = {item["global_identity_id"] for item in first_output["result_snapshot"] if item["queue"] == "new"}
        second_new = {item["global_identity_id"] for item in second_output["result_snapshot"] if item["queue"] == "new"}
        self.assertTrue(first_new)
        self.assertTrue(first_new.isdisjoint(second_new))
        self.assertGreater(second["duplicate_rate"], 0)
        second_by_id = {item["prospect_id"]: item for item in second_output["result_snapshot"]}
        for prospect_id, classification in (
            ("umg-shared-account", "existing_client"),
            ("umg-suppressed", "suppressed"),
        ):
            self.assertEqual(second_by_id[prospect_id]["queue"], "rejections")
            self.assertEqual(
                second_by_id[prospect_id]["duplicate_classification"], classification
            )
        self.assertEqual(
            second["duplicate_count"],
            sum(item["duplicate_classification"] is not None for item in second_output["result_snapshot"]),
        )

    def test_prospect_cap_and_zero_cost_cap_hold(self) -> None:
        env = Phase5Env(self.directory)
        campaign = env.campaign("Open")
        with self.assertRaisesRegex(MissionControlError, "prospect cap"):
            env.schedule([campaign], prospect_cap=16)
        schedule = env.schedule([campaign], prospect_cap=1)
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        occurrence = env.loop.evaluate_due()[0]
        output = env.store.get_output(occurrence["worker_run_id"])
        self.assertLessEqual(sum(item["queue"] == "new" for item in output["result_snapshot"]), 1)
        cap_rejections = [
            item for item in output["result_snapshot"]
            if item["effective_rejection"] == "target_cap"
        ]
        self.assertTrue(cap_rejections)
        self.assertTrue(all(item.get("duplicate_classification") is None for item in cap_rejections))
        self.assertEqual(output["estimated_cost_usd"], 0)
        self.assertEqual(
            env.loop.get_schedule("noah", schedule["schedule_id"])["duplicate_rate"],
            occurrence["duplicate_rate"],
        )

    def test_duplicate_metric_counts_identity_classifications_not_other_rejections(self) -> None:
        env = Phase5Env(self.directory)
        schedule = env.schedule([env.campaign("Open")])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        occurrence = env.loop.evaluate_due()[0]
        results = env.store.get_output(occurrence["worker_run_id"])["result_snapshot"]
        classified = {
            item["prospect_id"] for item in results if item.get("duplicate_classification")
        }
        self.assertEqual(classified, {"umg-duplicate-prism", "umg-reengage-comet"})
        self.assertEqual(occurrence["result_count"], len(results))
        self.assertEqual(occurrence["duplicate_count"], 2)
        self.assertEqual(occurrence["duplicate_rate"], 2 / len(results))
        by_id = {item["prospect_id"]: item for item in results}
        for prospect_id in (
            "umg-below-threshold", "umg-missing-evidence", "umg-suppressed",
            "umg-active-outreach",
        ):
            self.assertEqual(by_id[prospect_id]["queue"], "rejections")
            self.assertIsNone(by_id[prospect_id].get("duplicate_classification"))

        talent = env.campaign(
            "Talent protections", unit="unreal-talent", scope="open"
        )
        talent_schedule = env.schedule([talent])
        env.loop.enable("noah", talent_schedule["schedule_id"], talent_schedule["row_version"])
        talent_occurrence = env.loop.evaluate_due()[0]
        talent_results = env.store.get_output(talent_occurrence["worker_run_id"])["result_snapshot"]
        talent_by_id = {item["prospect_id"]: item for item in talent_results}
        for prospect_id, rejection in (
            ("talent-rights-conflict", "rights_conflict"),
            ("talent-brand-conflict", "brand_safety_conflict"),
        ):
            self.assertEqual(talent_by_id[prospect_id]["effective_rejection"], rejection)
            self.assertIsNone(talent_by_id[prospect_id].get("duplicate_classification"))

    def test_success_has_one_output_and_one_pending_review_task(self) -> None:
        env = Phase5Env(self.directory)
        schedule = env.schedule([env.campaign("Open")])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        occurrence = env.loop.evaluate_due()[0]
        run = env.agent.run_detail("noah", occurrence["worker_run_id"])
        self.assertEqual(occurrence["state"], "completed")
        self.assertIsNotNone(run["output"])
        self.assertEqual(run["review_task"]["state"], "pending_review")
        self.assertEqual(len(env.store.attempts_for(run["run_id"])), 1)


class RaceIsolationAndFailureTests(Phase5Case):
    def test_pause_or_disable_before_claim_wins_and_claimed_occurrence_finishes(self) -> None:
        env = Phase5Env(self.directory)
        schedule = env.schedule([env.campaign("Open")])
        enabled = env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        paused = env.loop.pause("noah", schedule["schedule_id"], enabled["row_version"])
        self.assertEqual(env.loop.evaluate_due(), [])
        resumed = env.loop.resume("noah", schedule["schedule_id"], paused["row_version"])
        claimed = env.loop.claim_due("noah", schedule["schedule_id"])
        self.assertIsNotNone(claimed)
        disabled = env.loop.disable("noah", schedule["schedule_id"], resumed["row_version"] + 1)
        self.assertEqual(disabled["state"], "disabled")
        completed = env.loop.execute_claimed("noah", claimed)
        self.assertEqual(completed["state"], "completed")

    def test_storage_failure_is_visible_as_unhealthy_with_local_alert(self) -> None:
        env = Phase5Env(self.directory)
        schedule = env.schedule([env.campaign("Open")])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        original = env.agent.execute_run

        def fail(*_args, **_kwargs):
            raise MissionControlError(500, "synthetic local storage failure")

        env.agent.execute_run = fail
        try:
            occurrence = env.loop.evaluate_due()[0]
        finally:
            env.agent.execute_run = original
        self.assertEqual(occurrence["state"], "failed")
        schedule = env.loop.get_schedule("noah", schedule["schedule_id"])
        self.assertEqual(schedule["health"], "unhealthy")
        alerts = env.loop.alerts("noah", "unreal-media-group")
        self.assertEqual(len(alerts), 1)
        self.assertNotIn("sqlite", json.dumps(alerts).casefold())
        status, body = WebApplication(
            env.control, agent_service=env.agent, shadow_service=env.loop
        ).get(
            "/shadow-schedules", {"actor": ["noah"], "business_unit": ["unreal-media-group"]}
        )
        self.assertEqual(status, 200)
        self.assertIn("shadow_execution_failed", body)
        self.assertIn("The local shadow occurrence failed safely.", body)

    def test_transient_failure_settlement_is_retried_without_stranding_claim(self) -> None:
        env = Phase5Env(self.directory)
        schedule = env.schedule([env.campaign("Open")])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        original_execute = env.agent.execute_run
        original_finish = env.store.finish_shadow_occurrence
        finish_calls = 0

        def fail_execution(*_args, **_kwargs):
            raise MissionControlError(500, "synthetic local storage failure")

        def fail_settlement_twice(*args, **kwargs):
            nonlocal finish_calls
            finish_calls += 1
            if finish_calls <= 2:
                raise MissionControlError(500, "synthetic settlement failure")
            return original_finish(*args, **kwargs)

        env.agent.execute_run = fail_execution
        env.store.finish_shadow_occurrence = fail_settlement_twice
        with self.assertRaisesRegex(MissionControlError, "settlement failure"):
            env.loop.evaluate_due()
        env.agent.execute_run = original_execute
        env.store.finish_shadow_occurrence = original_finish
        settled = env.loop.evaluate_due()[0]
        self.assertEqual(settled["state"], "failed")
        self.assertEqual(settled["failure_class"], "shadow_execution_failed")
        self.assertEqual(len(env.loop.alerts("noah", "unreal-media-group")), 1)

    def test_transient_output_read_is_reconciled_before_new_work(self) -> None:
        env = Phase5Env(self.directory)
        schedule = env.schedule([env.campaign("Open")])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        original = env.store.get_output
        failed = False

        def fail_once(run_id):
            nonlocal failed
            if not failed:
                failed = True
                raise MissionControlError(500, "synthetic output read failure")
            return original(run_id)

        env.store.get_output = fail_once
        with self.assertRaisesRegex(MissionControlError, "output read failure"):
            env.loop.evaluate_due()
        occurrence = env.loop.occurrences("noah", "unreal-media-group")[0]
        self.assertEqual(occurrence["state"], "claimed")
        self.assertEqual(env.store.get_run(occurrence["worker_run_id"])["state"], "succeeded")
        completed = env.loop.evaluate_due()[0]
        env.store.get_output = original
        self.assertEqual(completed["state"], "completed")
        self.assertEqual(env.store.get_run(completed["worker_run_id"])["state"], "succeeded")

    def test_business_unit_isolation_and_foreign_ids_do_not_leak(self) -> None:
        env = Phase5Env(self.directory)
        talent = env.campaign("Talent", unit="unreal-talent", scope="filtered", verticals="sports")
        schedule = env.schedule([talent])
        with self.assertRaisesRegex(MissionControlError, "Shadow schedule not found"):
            env.loop.get_schedule("rob", schedule["schedule_id"])
        with self.assertRaisesRegex(MissionControlError, "Shadow schedule not found"):
            env.loop.get_schedule("rob", "schedule-does-not-exist")
        with self.assertRaisesRegex(MissionControlError, "Noah"):
            env.loop.enable("dan", schedule["schedule_id"], schedule["row_version"])

    def test_run_creation_and_occurrence_link_roll_back_together(self) -> None:
        injector = FaultInjector()
        env = Phase5Env(self.directory)
        env.store.fault_hook = injector
        schedule = env.schedule([env.campaign("Open")])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        injector.armed = "link_shadow_run"
        occurrence = env.loop.evaluate_due()[0]
        self.assertEqual(occurrence["state"], "failed")
        self.assertIsNone(occurrence["worker_run_id"])
        self.assertEqual(env.store.list_runs({"unreal-media-group"}), [])

    def test_scheduled_run_link_requires_noah_and_exact_occurrence_scope(self) -> None:
        env = Phase5Env(self.directory)
        umg = env.campaign("Open")
        talent = env.campaign("Talent", unit="unreal-talent", scope="filtered", verticals="sports")
        schedule = env.schedule([umg])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        occurrence = env.loop.claim_due()
        with self.assertRaisesRegex(MissionControlError, "Noah"):
            env.agent.create_shadow_run(
                "rob", umg["family_id"], umg["version"], occurrence["idempotency_key"],
                occurrence_id=occurrence["occurrence_id"],
            )
        with self.assertRaisesRegex(MissionControlError, "link conflicts"):
            env.agent.create_shadow_run(
                "noah", talent["family_id"], talent["version"], occurrence["idempotency_key"],
                occurrence_id=occurrence["occurrence_id"],
            )
        current = env.store.get_shadow_occurrence(occurrence["occurrence_id"])
        self.assertIsNone(current["worker_run_id"])
        self.assertEqual(env.store.list_runs({"unreal-media-group", "unreal-talent"}), [])
        connection = env.store._connect()
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0], 1)
        finally:
            connection.close()

    def test_post_output_audit_fault_retries_completion_without_split_truth(self) -> None:
        injector = FaultInjector()
        env = Phase5Env(self.directory)
        env.store.fault_hook = injector
        schedule = env.schedule([env.campaign("Open")])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        occurrence = env.loop.claim_due()
        injector.armed = "insert_shadow_audit"
        completed = env.loop.execute_claimed("noah", occurrence)
        run = env.store.get_run(completed["worker_run_id"])
        self.assertEqual(completed["state"], "completed")
        self.assertEqual(run["state"], "succeeded")
        self.assertIsNotNone(env.store.get_output(run["run_id"]))
        self.assertEqual(env.store.get_review_task(run["review_task_id"])["state"], "pending_review")

    def test_recovered_scheduled_attempt_cannot_retry_after_occurrence_terminalizes(self) -> None:
        env = Phase5Env(self.directory)
        schedule = env.schedule([env.campaign("Open")])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        occurrence = env.loop.claim_due()
        history = env.loop._load_history(occurrence["business_unit"])
        serialized = json.dumps(history, sort_keys=True, separators=(",", ":"))
        env.store.set_shadow_history(
            occurrence["occurrence_id"],
            history=history,
            history_hash=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        )
        run, created = env.agent.create_shadow_run(
            "noah", occurrence["campaign_family_id"], occurrence["campaign_version"],
            occurrence["idempotency_key"], occurrence_id=occurrence["occurrence_id"],
        )
        self.assertTrue(created)
        claim = env.store.claim_attempt(
            run["run_id"], expected_states=("queued",), actor="noah",
            worker_version="test", now="2026-07-20T09:30:00Z",
        )
        self.assertIsNotNone(claim)

        restarted_store = SqliteStore(env.path)
        restarted_agent = RegisteredAgentService(env.repository, restarted_store, clock=env.clock)
        restarted_loop = ShadowLoopService(
            restarted_store, restarted_agent, clock=env.clock, history_seed_path=PHASE5_HISTORY
        )
        recovered_occurrence = restarted_loop.occurrences("noah", "unreal-media-group")[0]
        self.assertEqual(recovered_occurrence["state"], "failed")
        self.assertEqual(restarted_agent.get_run("noah", run["run_id"])["state"], "failed_retryable")
        self.assertFalse(restarted_agent.run_detail("noah", run["run_id"])["retry_allowed"])
        with self.assertRaisesRegex(MissionControlError, "scheduled shadow run"):
            restarted_agent.retry_run("noah", run["run_id"])
        self.assertIsNone(restarted_store.get_output(run["run_id"]))
        self.assertEqual(restarted_store.list_review_tasks({"unreal-media-group"}), [])
        app = WebApplication(
            env.control, agent_service=restarted_agent, shadow_service=restarted_loop
        )
        status, body = app.get(
            f'/worker-runs/{run["run_id"]}',
            {"actor": ["noah"], "business_unit": ["unreal-media-group"]},
        )
        self.assertEqual(status, 200)
        self.assertIn("Scheduled shadow runs are not manually retryable", body)
        self.assertNotIn(f'/worker-runs/{run["run_id"]}/retry', body)

    def test_scheduled_retry_cannot_race_stale_occurrence_settlement(self) -> None:
        env = Phase5Env(self.directory)
        schedule = env.schedule([env.campaign("Open")])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        retry_path: dict[str, str | None] = {"value": None}
        condition = threading.Condition()
        executor = GatedScheduledRetryExecutor(env.agent.executor, retry_path, condition)
        env.agent.executor = executor
        attempt_one_returned = threading.Event()
        release_settlement = threading.Event()
        original_execute_run = env.agent.execute_run

        def pause_before_settlement(*args, **kwargs):
            run = original_execute_run(*args, **kwargs)
            self.assertEqual(run["state"], "failed_retryable")
            attempt_one_returned.set()
            self.assertTrue(release_settlement.wait(5))
            return run

        env.agent.execute_run = pause_before_settlement
        tick_results: list[list[dict]] = []
        tick_errors: list[Exception] = []
        retry_errors: list[Exception] = []

        def tick() -> None:
            try:
                tick_results.append(env.loop.evaluate_due())
            except Exception as exc:  # captured for assertion in the test thread
                tick_errors.append(exc)

        def retry(run_id: str) -> None:
            try:
                env.agent.retry_run("noah", run_id)
            except Exception as exc:  # captured for assertion in the test thread
                retry_errors.append(exc)
                with condition:
                    if retry_path["value"] is None:
                        retry_path["value"] = "denied"
                    condition.notify_all()

        tick_thread = threading.Thread(target=tick, name="phase5-stale-settlement")
        retry_thread = None
        tick_thread.start()
        try:
            self.assertTrue(attempt_one_returned.wait(5))
            occurrence = env.loop.occurrences("noah", "unreal-media-group")[0]
            run_id = occurrence["worker_run_id"]
            detail = env.agent.run_detail("noah", run_id)
            self.assertFalse(detail["retry_allowed"])
            self.assertFalse(detail["retryable"])
            self.assertEqual(detail["retry_block_reason"], "scheduled_run")
            self.assertNotIn("retry manually", detail["remediation"].casefold())
            app = WebApplication(
                env.control, agent_service=env.agent, shadow_service=env.loop
            )
            status, body = app.get(
                f"/worker-runs/{run_id}",
                {"actor": ["noah"], "business_unit": ["unreal-media-group"]},
            )
            self.assertEqual(status, 200)
            self.assertIn("Scheduled shadow runs are not manually retryable", body)
            self.assertNotIn("Retryable</dt><dd>True", body)
            self.assertNotIn("retry manually", body.casefold())
            self.assertNotIn(f"/worker-runs/{run_id}/retry", body)
            retry_thread = threading.Thread(
                target=retry, args=(run_id,), name="phase5-forbidden-retry"
            )
            retry_thread.start()
            with condition:
                self.assertTrue(condition.wait_for(lambda: retry_path["value"] is not None, 5))
            if retry_path["value"] == "claimed":
                release_settlement.set()
                tick_thread.join(5)
                self.assertFalse(tick_thread.is_alive())
                executor.release_retry.set()
            else:
                release_settlement.set()
        finally:
            release_settlement.set()
            executor.release_retry.set()
            tick_thread.join(5)
            if retry_thread is not None:
                retry_thread.join(5)
            env.agent.execute_run = original_execute_run

        self.assertFalse(tick_thread.is_alive())
        self.assertIsNotNone(retry_thread)
        self.assertFalse(retry_thread.is_alive())
        self.assertEqual(tick_errors, [])
        self.assertEqual(retry_path["value"], "denied")
        self.assertEqual(len(retry_errors), 1)
        self.assertIsInstance(retry_errors[0], MissionControlError)
        self.assertEqual(retry_errors[0].status, 409)
        self.assertIn("scheduled shadow run", retry_errors[0].message.casefold())
        self.assertEqual(len(tick_results), 1)
        occurrence = env.loop.occurrences("noah", "unreal-media-group")[0]
        run = env.store.get_run(occurrence["worker_run_id"])
        self.assertEqual(occurrence["state"], "failed")
        self.assertEqual(run["state"], "failed_retryable")
        self.assertEqual(executor.calls, 1)
        self.assertEqual(len(env.store.attempts_for(run["run_id"])), 1)
        self.assertIsNone(env.store.get_output(run["run_id"]))
        self.assertEqual(env.store.list_review_tasks({"unreal-media-group"}), [])
        audits = env.loop.schedule_detail("noah", occurrence["schedule_id"])["audits"]
        self.assertEqual(
            [item["event_type"] for item in audits].count("occurrence_failed"), 1
        )
        alerts = env.loop.alerts("noah", "unreal-media-group")
        self.assertEqual(
            len([item for item in alerts if item["occurrence_id"] == occurrence["occurrence_id"]]),
            1,
        )

    def test_recovery_between_retry_precheck_and_claim_cannot_split_truth(self) -> None:
        env = Phase5Env(self.directory)
        schedule = env.schedule([env.campaign("Open")])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        occurrence = env.loop.claim_due()
        history = env.loop._load_history(occurrence["business_unit"])
        serialized = json.dumps(history, sort_keys=True, separators=(",", ":"))
        env.store.set_shadow_history(
            occurrence["occurrence_id"], history=history,
            history_hash=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        )
        run, _ = env.agent.create_shadow_run(
            "noah", occurrence["campaign_family_id"], occurrence["campaign_version"],
            occurrence["idempotency_key"], occurrence_id=occurrence["occurrence_id"],
        )
        claim = env.store.claim_attempt(
            run["run_id"], expected_states=("queued",), actor="noah",
            worker_version="test", now="2026-07-20T09:30:00Z",
        )
        self.assertTrue(env.store.commit_failure(
            run["run_id"], attempt_number=claim["attempt_number"],
            terminal_state="failed_retryable", failure_class="storage_unavailable",
            retryable=True, remediation="Retry locally.", event_type="attempt_failed",
            actor="noah", correlation_id=claim["correlation_id"],
            now="2026-07-20T09:30:01Z",
        ))

        precheck_done = threading.Event()
        allow_claim = threading.Event()
        original = env.store.shadow_occurrence_for_run
        first_call = True

        def pause_after_precheck(run_id):
            nonlocal first_call
            row = original(run_id)
            if first_call:
                first_call = False
                precheck_done.set()
                self.assertTrue(allow_claim.wait(5))
            return row

        env.store.shadow_occurrence_for_run = pause_after_precheck
        errors = []

        def retry() -> None:
            try:
                env.agent.retry_run("noah", run["run_id"])
            except Exception as exc:  # captured for assertion in the test thread
                errors.append(exc)

        thread = threading.Thread(target=retry, name="phase5-retry-race")
        thread.start()
        try:
            self.assertTrue(precheck_done.wait(5))
            env.store.recover_shadow_occurrences(now="2026-07-20T09:30:02Z")
        finally:
            allow_claim.set()
            thread.join(5)
            env.store.shadow_occurrence_for_run = original
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], MissionControlError)
        self.assertEqual(errors[0].status, 409)
        self.assertEqual(env.store.get_run(run["run_id"])["state"], "failed_retryable")
        self.assertEqual(env.store.get_shadow_occurrence(occurrence["occurrence_id"])["state"], "failed")
        self.assertIsNone(env.store.get_output(run["run_id"]))
        self.assertEqual(env.store.list_review_tasks({"unreal-media-group"}), [])

    def test_tampered_success_output_cannot_complete_recovered_occurrence(self) -> None:
        env = Phase5Env(self.directory)
        schedule = env.schedule([env.campaign("Open")])
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        occurrence = env.loop.evaluate_due()[0]
        with env.store.transaction() as connection:
            connection.execute(
                "UPDATE shadow_occurrences SET state='claimed',completed_at=NULL,"
                " failure_class=NULL,stop_reason=NULL,result_count=NULL,duplicate_count=NULL,"
                " duplicate_rate=NULL WHERE occurrence_id=?",
                (occurrence["occurrence_id"],),
            )
            connection.execute(
                "UPDATE worker_outputs SET result_snapshot='[]' WHERE run_id=?",
                (occurrence["worker_run_id"],),
            )
        restarted_store = SqliteStore(env.path)
        restarted_agent = RegisteredAgentService(env.repository, restarted_store, clock=env.clock)
        restarted_loop = ShadowLoopService(
            restarted_store, restarted_agent, clock=env.clock, history_seed_path=PHASE5_HISTORY
        )
        recovered = restarted_loop.occurrences("noah", "unreal-media-group")[0]
        self.assertEqual(recovered["state"], "failed")
        self.assertEqual(recovered["failure_class"], "shadow_output_invalid")
        self.assertIsNone(recovered["result_count"])
        self.assertEqual(len(restarted_loop.alerts("noah", "unreal-media-group")), 1)
        invalidated_run = restarted_store.get_run(occurrence["worker_run_id"])
        self.assertEqual(invalidated_run["state"], "failed_terminal")
        self.assertEqual(invalidated_run["failure_class"], "shadow_output_invalid")
        self.assertEqual(
            restarted_store.get_review_task(invalidated_run["review_task_id"])["state"],
            "invalidated",
        )
        with self.assertRaisesRegex(MissionControlError, "integrity check"):
            restarted_store.get_output(occurrence["worker_run_id"])


class UpgradeWebAndLifecycleTests(Phase5Case):
    def test_fresh_schema_and_real_phase4_schema_upgrade_preserve_existing_rows(self) -> None:
        fresh = SqliteStore(self.directory / "fresh.sqlite3")
        connection = fresh._connect()
        try:
            self.assertEqual(connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0], str(SCHEMA_VERSION))
        finally:
            connection.close()

        source_directory = self.directory / "phase4-source"
        source_directory.mkdir()
        source = Phase5Env(source_directory)
        campaign = source.campaign("Phase 4 durable source")
        run, _created = source.agent.create_manual_run(
            "noah", campaign["family_id"], campaign["version"], "phase4-upgrade-source"
        )
        legacy_fingerprint = hashlib.sha256(json.dumps({
            "agent_id": run["agent_id"],
            "campaign_family_id": run["campaign_family_id"],
            "campaign_version": run["campaign_version"],
            "business_unit": run["business_unit"],
            "initiating_actor": run["initiating_actor"],
            "configuration_hash": run["configuration_hash"],
            "skill_id": run["skill_id"],
            "skill_version": run["skill_version"],
        }, sort_keys=True).encode("utf-8")).hexdigest()
        with source.store.transaction() as source_connection:
            source_connection.execute(
                "UPDATE worker_runs SET request_fingerprint=? WHERE run_id=?",
                (legacy_fingerprint, run["run_id"]),
            )

        legacy_path = self.directory / "legacy.sqlite3"
        connection = sqlite3.connect(legacy_path)
        for statement in PHASE4_TABLES:
            connection.execute(statement)
        connection.execute("INSERT INTO schema_meta(key,value) VALUES('schema_version','1')")
        phase4_tables = (
            "id_counters", "worker_runs", "worker_attempts", "worker_outputs",
            "review_tasks", "audit_events",
        )
        source_connection = sqlite3.connect(source.path)
        for table in phase4_tables:
            cursor = source_connection.execute(f"SELECT * FROM {table} ORDER BY rowid")
            columns = [item[0] for item in cursor.description]
            rows = cursor.fetchall()
            if rows:
                placeholders = ",".join("?" for _ in columns)
                connection.executemany(
                    f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})", rows
                )
        source_connection.close()
        connection.commit()
        before = {
            table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
            for table in phase4_tables
        }
        connection.close()
        upgraded = SqliteStore(legacy_path)
        connection = upgraded._connect()
        try:
            for table in phase4_tables:
                self.assertEqual(
                    [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")],
                    before[table],
                )
            self.assertEqual(connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0], "2")
            names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"shadow_schedules", "shadow_occurrences", "shadow_alerts"}.issubset(names))
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            connection.close()
        upgraded_agent = RegisteredAgentService(source.repository, upgraded, clock=source.clock)
        replayed, created = upgraded_agent.create_manual_run(
            "noah", campaign["family_id"], campaign["version"], "phase4-upgrade-source"
        )
        self.assertFalse(created)
        self.assertEqual(replayed["run_id"], run["run_id"])
        self.assertEqual(replayed["attempt_count"], 0)
        self.assertEqual(len(upgraded.list_runs({"unreal-media-group"})), 1)
        self.assertIsNone(upgraded.get_output(run["run_id"]))
        self.assertEqual(
            [item["event_type"] for item in upgraded.audits_for(run["run_id"])],
            ["manual_request_accepted", "idempotent_replay"],
        )

    def test_phase4_positional_state_path_constructor_contract_is_preserved(self) -> None:
        env = Phase5Env(self.directory / "repository")
        state_path = self.directory / "legacy-positional.sqlite3"
        app = WebApplication(env.control, "legacy-csrf", None, state_path)
        self.assertEqual(app.csrf_token, "legacy-csrf")
        self.assertEqual(app.agent.store.path, state_path)

    def test_http_routes_enforce_csrf_scope_and_render_truthful_shadow_state(self) -> None:
        env = Phase5Env(self.directory)
        campaign = env.campaign("Open")
        app = WebApplication(env.control, csrf_token="phase5-csrf", agent_service=env.agent, shadow_service=env.loop)
        status, body = app.get("/shadow-schedules", {"actor": ["noah"], "business_unit": ["unreal-media-group"]})
        self.assertEqual(status, 200)
        self.assertIn("disabled by default", body)
        with self.assertRaisesRegex(MissionControlError, "CSRF"):
            app.post("/shadow-schedules", {"actor": "noah", "business_unit": "unreal-media-group"})
        form = {
            "csrf_token": "phase5-csrf", "actor": "noah", "business_unit": "unreal-media-group",
            "name": "HTTP shadow", "campaign_refs": f"{campaign['family_id']}:{campaign['version']}",
            "weekday": "0", "utc_hour": "9", "utc_minute": "30", "prospect_cap": "5",
            "open_discovery_every": "0",
        }
        status, body = app.post("/shadow-schedules", form)
        self.assertEqual(status, 201)
        self.assertIn("Synthetic local shadow schedule", body)
        self.assertNotIn("outreach action", body.casefold())
        schedule = env.loop.schedules("noah", "unreal-media-group")[0]
        talent_schedule = env.schedule([
            env.campaign("Talent", unit="unreal-talent", scope="filtered", verticals="sports")
        ])
        for actor, unit, visible_schedule in (
            ("rob", "unreal-media-group", schedule),
            ("dan", "unreal-talent", talent_schedule),
        ):
            status, read_only = app.get(
                "/shadow-schedules", {"actor": [actor], "business_unit": [unit]}
            )
            self.assertEqual(status, 200)
            self.assertIn("read-only", read_only.casefold())
            self.assertIn("Not available", read_only)
            self.assertNotIn("Configure a disabled shadow schedule", read_only)
            status, read_only_form = app.get(
                "/shadow-schedules/new", {"actor": [actor], "business_unit": [unit]}
            )
            self.assertEqual(status, 200)
            self.assertIn("read-only", read_only_form.casefold())
            self.assertNotIn('action="/shadow-schedules"', read_only_form)
            self.assertNotIn("Create disabled shadow schedule", read_only_form)
            status, read_only_detail = app.get(
                f'/shadow-schedules/{visible_schedule["schedule_id"]}',
                {"actor": [actor], "business_unit": [unit]},
            )
            self.assertEqual(status, 200)
            self.assertIn("read-only", read_only_detail.casefold())
            self.assertIn("Not available", read_only_detail)
            self.assertNotIn("/enable", read_only_detail)
            with self.assertRaisesRegex(MissionControlError, "Noah"):
                app.post(
                    f'/shadow-schedules/{visible_schedule["schedule_id"]}/enable',
                    {"csrf_token": "phase5-csrf", "actor": actor, "business_unit": unit, "row_version": str(visible_schedule["row_version"])},
                )
        with self.assertRaisesRegex(MissionControlError, "Noah"):
            app.post("/shadow-schedules", {**form, "actor": "rob"})
        env.loop.enable("noah", schedule["schedule_id"], schedule["row_version"])
        env.loop.evaluate_due()
        status, body = app.get(
            f'/shadow-schedules/{schedule["schedule_id"]}',
            {"actor": ["noah"], "business_unit": ["unreal-media-group"]},
        )
        self.assertEqual(status, 200)
        self.assertIn("wrun-", body)
        self.assertIn("pending human review", body)

    def test_real_loopback_server_and_scheduler_stop_and_join_every_thread(self) -> None:
        env = Phase5Env(self.directory)
        schedule = env.schedule([env.campaign("Open")])
        talent_schedule = env.schedule([
            env.campaign("Talent", unit="unreal-talent", scope="filtered", verticals="sports")
        ])
        app = WebApplication(env.control, csrf_token="phase5-csrf", agent_service=env.agent, shadow_service=env.loop)
        server = build_server(app, port=0)
        scheduler = ShadowScheduler(env.loop, actor="noah")
        scheduler.start()
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.start()
        host, port = server.server_address
        self.assertEqual(host, "127.0.0.1")
        def request(method: str, path: str, body: str | None = None) -> tuple[int, str]:
            connection = http.client.HTTPConnection(host, port, timeout=2)
            try:
                headers = {"Content-Type": "application/x-www-form-urlencoded"} if body is not None else {}
                connection.request(method, path, body=body, headers=headers)
                response = connection.getresponse()
                return response.status, response.read().decode("utf-8")
            finally:
                connection.close()

        status, noah_body = request("GET", "/shadow-schedules?actor=noah&business_unit=unreal-media-group")
        self.assertEqual(status, 200)
        self.assertIn("Configure a disabled shadow schedule", noah_body)
        status, rob_body = request("GET", "/shadow-schedules?actor=rob&business_unit=unreal-media-group")
        self.assertEqual(status, 200)
        self.assertIn("read-only", rob_body.casefold())
        self.assertNotIn("Configure a disabled shadow schedule", rob_body)
        status, dan_body = request("GET", "/shadow-schedules?actor=dan&business_unit=unreal-talent")
        self.assertEqual(status, 200)
        self.assertIn("read-only", dan_body.casefold())
        self.assertNotIn("Configure a disabled shadow schedule", dan_body)
        forged = urlencode({
            "csrf_token": "phase5-csrf", "actor": "rob", "business_unit": "unreal-media-group",
            "row_version": schedule["row_version"],
        })
        status, forged_body = request(
            "POST", f'/shadow-schedules/{schedule["schedule_id"]}/enable', forged
        )
        self.assertEqual(status, 403)
        self.assertIn("Noah", forged_body)
        forged_dan = urlencode({
            "csrf_token": "phase5-csrf", "actor": "dan", "business_unit": "unreal-talent",
            "row_version": talent_schedule["row_version"],
        })
        status, forged_dan_body = request(
            "POST", f'/shadow-schedules/{talent_schedule["schedule_id"]}/enable', forged_dan
        )
        self.assertEqual(status, 403)
        self.assertIn("Noah", forged_dan_body)
        status, _ = request("GET", "/shadow-schedules?actor=rob&business_unit=unreal-talent")
        self.assertEqual(status, 403)
        server.shutdown()
        server.server_close()
        scheduler.stop()
        scheduler.join(timeout=2)
        server_thread.join(timeout=2)
        self.assertFalse(scheduler.is_alive())
        self.assertFalse(server_thread.is_alive())

    def test_executable_surface_has_no_outbound_or_phase6_capability(self) -> None:
        source = "\n".join(
            (APP_ROOT / "mission_control" / name).read_text(encoding="utf-8")
            for name in ["shadow.py", "store.py", "agent.py", "application.py", "web.py"]
        ).casefold()
        for token in ["requests.", "urllib.request", "socket.create_connection", "subprocess.", "eval(", "exec(", "smtp", "send_outreach", "generate_creative"]:
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()

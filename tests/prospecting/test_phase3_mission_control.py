from __future__ import annotations

import http.client
import json
import ast
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = ROOT / "apps" / "prospecting-mission-control"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from mission_control.application import (  # noqa: E402
    CounterIds,
    FixtureRepository,
    MissionControl,
    MissionControlError,
    safe_evidence_url,
)
from mission_control.agent import RegisteredAgentService  # noqa: E402
from mission_control.store import SqliteStore  # noqa: E402
from mission_control.web import MAX_BODY, WebApplication, build_server  # noqa: E402


FIXED_TIME = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)


def make_control() -> MissionControl:
    repository = FixtureRepository(
        clock=lambda: FIXED_TIME,
        next_id=CounterIds(),
        fixture_path=ROOT / "fixtures" / "prospecting" / "phase3" / "prospects.json",
    )
    return MissionControl(repository)


def form(unit: str = "unreal-media-group", *, scope: str = "open", verticals: str = "", name: str = "Synthetic Campaign", target: str = "20", score: str = "72") -> dict[str, str]:
    return {
        "business_unit": unit,
        "campaign_name": name,
        "discovery_scope": scope,
        "verticals": verticals,
        "target_prospect_count": target,
        "minimum_qualification_score": score,
        "cooldown_days": "120" if unit == "unreal-media-group" else "180",
        "maximum_evidence_age_days": "180",
        "geography": "United States",
        "rights_territory": "United States" if unit == "unreal-talent" else "",
        "talent_categories": "athlete archetype" if unit == "unreal-talent" else "",
    }


def create_campaign(control: MissionControl, actor: str = "noah", **kwargs: str) -> dict:
    config = control.campaign_config(form(**kwargs))
    return control.repository.add_campaign(actor, config)


def run_campaign(control: MissionControl, campaign: dict, actor: str = "noah", key: str = "fixture-run-key") -> dict:
    return control.repository.start_run(actor, campaign["family_id"], campaign["version"], key)


class DomainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.control = make_control()

    def test_campaign_validation_open_filtered_and_versions(self) -> None:
        open_config = self.control.campaign_config(form())
        self.assertEqual(open_config["verticals"], [])
        first = self.control.repository.add_campaign("noah", open_config)
        filtered = self.control.campaign_config(form(scope="filtered", verticals=" Apparel , FITNESS "))
        second = self.control.repository.add_campaign("noah", filtered, first["family_id"])
        self.assertEqual((first["version"], second["version"]), (1, 2))
        self.assertEqual(first["configuration"]["discovery_scope"], "open")
        self.assertEqual(second["configuration"]["verticals"], ["Apparel", "FITNESS"])
        with self.assertRaisesRegex(MissionControlError, "filtered discovery"):
            self.control.campaign_config(form(scope="filtered"))
        with self.assertRaisesRegex(MissionControlError, "target_prospect_count"):
            self.control.campaign_config(form(target="not-a-number"))

    def test_talent_contract_fields_and_named_person_remain_disabled(self) -> None:
        config = self.control.campaign_config(form(unit="unreal-talent", scope="filtered", verticals="sports apparel"))
        self.assertEqual(config["rights_territory"], ["United States"])
        self.assertFalse(config["allow_named_talent_recommendations"])
        with self.assertRaisesRegex(MissionControlError, "rights_territory"):
            bad = form(unit="unreal-talent", scope="filtered", verticals="sports apparel")
            bad["rights_territory"] = ""
            self.control.campaign_config(bad)

    def test_open_filtered_normalized_and_no_results_are_distinct(self) -> None:
        open_run = run_campaign(self.control, create_campaign(self.control), key="open")
        filtered_campaign = create_campaign(self.control, scope="filtered", verticals="ACTIVE-WEAR", name="Filtered")
        filtered_run = run_campaign(self.control, filtered_campaign, key="filtered")
        unmatched = create_campaign(self.control, scope="filtered", verticals="synthetic unmatched vertical", name="Unmatched")
        unmatched_run = run_campaign(self.control, unmatched, key="unmatched")
        self.assertNotEqual(open_run["output_ids"], filtered_run["output_ids"])
        self.assertIn("umg-new-orbit", filtered_run["output_ids"])
        self.assertEqual(unmatched_run["status"], "no_results")
        self.assertEqual(unmatched_run["output_ids"], ())

    def test_failed_validation_and_blocked_protection_terminal_runs_remain_visible(self) -> None:
        template = dict(self.control.repository.fixture_candidates[0])
        template.update({"prospect_id": "umg-validation-fixture", "global_identity_id": "global-validation-fixture", "verticals": ["validation fixture"], "fixture_validation_error": True})
        protected = dict(template)
        protected.update({"prospect_id": "umg-protected-fixture", "global_identity_id": "global-protected-fixture", "verticals": ["protected fixture"], "fixture_validation_error": False, "relationship": "client"})
        self.control.repository.fixture_candidates += (template, protected)
        invalid_campaign = create_campaign(self.control, scope="filtered", verticals="validation fixture", name="Validation terminal")
        protected_campaign = create_campaign(self.control, scope="filtered", verticals="protected fixture", name="Protection terminal")
        self.assertEqual(run_campaign(self.control, invalid_campaign, key="validation-terminal")["status"], "failed_validation")
        self.assertEqual(run_campaign(self.control, protected_campaign, key="protection-terminal")["status"], "blocked_by_protection")
        self.assertEqual(len(self.control.repository.run_records), 2)

    def test_determinism_idempotency_conflict_and_visibility(self) -> None:
        campaign = create_campaign(self.control)
        first = run_campaign(self.control, campaign, key="same")
        again = run_campaign(self.control, campaign, key="same")
        self.assertEqual(first, again)
        self.assertEqual(len(self.control.repository.run_records), 1)
        other = create_campaign(self.control, name="Other")
        with self.assertRaisesRegex(MissionControlError, "different input"):
            run_campaign(self.control, other, key="same")
        with self.assertRaisesRegex(MissionControlError, "alphanumeric"):
            run_campaign(self.control, other, key="unsafe key")
        self.assertEqual(first["estimated_cost_usd"], 0)
        self.assertTrue(first["fixture_adapter"])
        self.assertTrue(any("Synthetic source two" in error for error in first["errors"]))
        self.assertEqual(first["stop_reason"], "Fixture evaluation completed with partial source errors.")

    def test_target_cap_threshold_and_queue_partition(self) -> None:
        campaign = create_campaign(self.control, target="1", score="72")
        run = run_campaign(self.control, campaign)
        prospects = self.control.repository.prospects("noah", "unreal-media-group")
        expected_umg = sum(item["business_unit"] == "unreal-media-group" for item in self.control.repository.fixture_candidates)
        self.assertEqual(len(prospects), expected_umg)
        self.assertEqual(set(run["output_ids"]), {item["prospect_id"] for item in prospects})
        queues = {"new", "duplicate_reengagement", "rejections"}
        self.assertTrue(all(item["queue"] in queues for item in prospects))
        self.assertEqual(sum(1 for queue in queues for item in prospects if item["queue"] == queue), len(prospects))
        self.assertEqual(sum(item["queue"] == "new" for item in prospects), 1)
        self.assertTrue(any(item["effective_rejection"] == "target_cap" for item in prospects))
        shared = next(item for item in prospects if item["prospect_id"] == "umg-shared-account")
        self.assertEqual(shared["effective_rejection"], "existing_client")

    def test_evidence_freshness_and_reengagement_choice_are_applied(self) -> None:
        values = form()
        values["maximum_evidence_age_days"] = "1"
        config = self.control.campaign_config(values)
        campaign = self.control.repository.add_campaign("noah", config)
        run_campaign(self.control, campaign, key="freshness")
        orbit = self.control.repository.get_prospect("noah", "unreal-media-group", "umg-new-orbit")
        reengagement = self.control.repository.get_prospect("noah", "unreal-media-group", "umg-reengage-comet")
        self.assertEqual(orbit["effective_rejection"], "stale_evidence")
        self.assertEqual(reengagement["effective_rejection"], "reengagement_disabled")

    def test_business_unit_isolation_and_shared_global_account(self) -> None:
        umg = create_campaign(self.control)
        talent = create_campaign(self.control, unit="unreal-talent", scope="filtered", verticals="sports apparel", score="78", name="Talent")
        run_campaign(self.control, umg, key="umg")
        run_campaign(self.control, talent, key="talent")
        umg_shared = self.control.repository.get_prospect("noah", "unreal-media-group", "umg-shared-account")
        talent_shared = self.control.repository.get_prospect("noah", "unreal-talent", "talent-shared-account")
        self.assertEqual(umg_shared["global_identity_id"], talent_shared["global_identity_id"])
        self.assertEqual(umg_shared["relationship"], "client")
        self.assertEqual(talent_shared["relationship"], "none")
        with self.assertRaisesRegex(MissionControlError, "not found"):
            self.control.repository.get_prospect("noah", "unreal-talent", "umg-shared-account")
        with self.assertRaisesRegex(MissionControlError, "Business-unit"):
            self.control.repository.prospects("rob", "unreal-talent")
        with self.assertRaisesRegex(MissionControlError, "Business-unit"):
            self.control.repository.prospects("dan", "unreal-media-group")

    def test_duplicate_merge_is_append_only_and_non_destructive(self) -> None:
        run_campaign(self.control, create_campaign(self.control), key="merge")
        event = self.control.repository.act("noah", "unreal-media-group", "umg-duplicate-prism", "resolve_identity", {"matched_identity_id": "synthetic-prism-parent"})
        item = self.control.repository.get_prospect("noah", "unreal-media-group", "umg-duplicate-prism")
        self.assertEqual(event["kind"], "resolve_identity")
        self.assertEqual(item["global_identity_id"], "global-prism-studio")
        self.assertEqual(len(item["review_history"]), 1)
        with self.assertRaisesRegex(MissionControlError, "exact listed"):
            self.control.repository.act("noah", "unreal-media-group", "umg-duplicate-prism", "resolve_identity", {"matched_identity_id": "invented-target"})

    def test_suppression_precedence_separation_of_duty_and_approval(self) -> None:
        run_campaign(self.control, create_campaign(self.control), key="approve")
        with self.assertRaisesRegex(MissionControlError, "own request"):
            self.control.repository.act("noah", "unreal-media-group", "umg-new-orbit", "approve_deeper_research", {})
        approved = self.control.repository.act("rob", "unreal-media-group", "umg-new-orbit", "approve_deeper_research", {})
        self.assertEqual(approved["value"]["decision"], "approved")
        self.control.repository.act("rob", "unreal-media-group", "umg-subbrand-ember", "suppress", {"reason": "Synthetic governance hold"})
        suppressed = self.control.repository.get_prospect("noah", "unreal-media-group", "umg-subbrand-ember")
        self.assertTrue(suppressed["effective_suppressed"])
        with self.assertRaisesRegex(MissionControlError, "Suppressed"):
            self.control.repository.act("noah", "unreal-media-group", "umg-subbrand-ember", "approve_deeper_research", {})

    def test_cooldown_uses_effective_time_not_field_presence(self) -> None:
        repository = FixtureRepository(
            clock=lambda: datetime(2027, 1, 1, tzinfo=timezone.utc),
            next_id=CounterIds(),
            fixture_path=ROOT / "fixtures" / "prospecting" / "phase3" / "prospects.json",
        )
        control = MissionControl(repository)
        run_campaign(control, create_campaign(control), key="expired-cooldown")
        item = repository.get_prospect("noah", "unreal-media-group", "umg-cooldown")
        self.assertFalse(item["effective_cooldown"])
        self.assertEqual(item["queue"], "new")

    def test_ineligible_relationship_cooldown_rejection_rights_brand_and_named_person(self) -> None:
        run_campaign(self.control, create_campaign(self.control), key="umg-protections")
        for prospect_id in ["umg-shared-account", "umg-active-outreach", "umg-cooldown", "umg-rejected", "umg-below-threshold"]:
            with self.assertRaises(MissionControlError, msg=prospect_id):
                self.control.repository.act("rob", "unreal-media-group", prospect_id, "approve_deeper_research", {})
        talent = create_campaign(self.control, unit="unreal-talent", scope="filtered", verticals="sports apparel, sports beverage", score="70", name="Talent")
        run_campaign(self.control, talent, key="talent-protections")
        for prospect_id in ["talent-named-person", "talent-rights-conflict", "talent-brand-conflict"]:
            with self.assertRaises(MissionControlError, msg=prospect_id):
                self.control.repository.act("dan", "unreal-talent", prospect_id, "approve_deeper_research", {})
        eligible = self.control.repository.get_prospect("dan", "unreal-talent", "talent-archetype")
        self.assertIsNone(eligible["named_talent"])
        self.assertIn("archetype", eligible["talent_archetype"].lower())

    def test_assignment_notes_rejection_supersession_and_deterministic_current_state(self) -> None:
        run_campaign(self.control, create_campaign(self.control), key="events")
        first = self.control.repository.act("rob", "unreal-media-group", "umg-new-orbit", "assign", {"assignee": "rob"})
        with self.assertRaisesRegex(MissionControlError, "supersede"):
            self.control.repository.act("noah", "unreal-media-group", "umg-new-orbit", "assign", {"assignee": "noah"})
        second = self.control.repository.act("noah", "unreal-media-group", "umg-new-orbit", "assign", {"assignee": "noah", "supersedes_id": first["event_id"]})
        self.control.repository.act("rob", "unreal-media-group", "umg-new-orbit", "note", {"text": "Synthetic review note"})
        self.control.repository.act("rob", "unreal-media-group", "umg-new-orbit", "reject", {"reason": "Synthetic review rejection"})
        item = self.control.repository.get_prospect("noah", "unreal-media-group", "umg-new-orbit")
        self.assertEqual(len(item["review_history"]), 4)
        self.assertEqual(item["current_review"]["assign"]["event_id"], second["event_id"])
        self.assertEqual(item["current_review"]["assign"]["supersedes_id"], first["event_id"])
        self.assertEqual(item["current_decision"], "rejected")
        self.assertEqual(item["notes"], ["Synthetic review note"])
        with self.assertRaisesRegex(MissionControlError, "Rejected"):
            self.control.repository.act("noah", "unreal-media-group", "umg-new-orbit", "approve_deeper_research", {})

    def test_approval_then_rejection_supersedes_within_one_decision_stream(self) -> None:
        run_campaign(self.control, create_campaign(self.control), key="approve-then-reject")
        approved = self.control.repository.act("rob", "unreal-media-group", "umg-new-orbit", "approve_deeper_research", {})
        item = self.control.repository.get_prospect("noah", "unreal-media-group", "umg-new-orbit")
        self.assertEqual(item["current_decision"], "approved_for_deeper_research")
        with self.assertRaisesRegex(MissionControlError, "supersede the current event"):
            self.control.repository.act("rob", "unreal-media-group", "umg-new-orbit", "reject", {"reason": "Synthetic correction"})
        rejected = self.control.repository.act("rob", "unreal-media-group", "umg-new-orbit", "reject", {"reason": "Synthetic correction", "supersedes_id": approved["event_id"]})
        item = self.control.repository.get_prospect("noah", "unreal-media-group", "umg-new-orbit")
        self.assertEqual(item["current_decision"], "rejected")
        self.assertEqual(rejected["supersedes_id"], approved["event_id"])
        self.assertEqual([event["event_id"] for event in item["review_history"]], [approved["event_id"], rejected["event_id"]])

    def test_rejection_then_approval_supersedes_and_keeps_separation_of_duty(self) -> None:
        run_campaign(self.control, create_campaign(self.control), key="reject-then-approve")
        rejected = self.control.repository.act("rob", "unreal-media-group", "umg-new-orbit", "reject", {"reason": "Synthetic first pass"})
        with self.assertRaisesRegex(MissionControlError, "Rejected"):
            self.control.repository.act("rob", "unreal-media-group", "umg-new-orbit", "approve_deeper_research", {})
        with self.assertRaisesRegex(MissionControlError, "own request"):
            self.control.repository.act("noah", "unreal-media-group", "umg-new-orbit", "approve_deeper_research", {"supersedes_id": rejected["event_id"]})
        approved = self.control.repository.act("rob", "unreal-media-group", "umg-new-orbit", "approve_deeper_research", {"supersedes_id": rejected["event_id"]})
        item = self.control.repository.get_prospect("noah", "unreal-media-group", "umg-new-orbit")
        self.assertEqual(item["current_decision"], "approved_for_deeper_research")
        self.assertEqual(approved["supersedes_id"], rejected["event_id"])
        self.assertEqual([event["event_id"] for event in item["review_history"]], [rejected["event_id"], approved["event_id"]])

    def test_invalid_decision_supersession_targets_fail_closed(self) -> None:
        run_campaign(self.control, create_campaign(self.control), key="bad-supersession")
        talent = create_campaign(self.control, unit="unreal-talent", scope="filtered", verticals="sports beverage", score="78", name="Talent")
        run_campaign(self.control, talent, key="bad-supersession-talent")
        approved = self.control.repository.act("rob", "unreal-media-group", "umg-new-orbit", "approve_deeper_research", {})
        current = self.control.repository.act("rob", "unreal-media-group", "umg-new-orbit", "reject", {"reason": "Synthetic correction", "supersedes_id": approved["event_id"]})
        assignment = self.control.repository.act("rob", "unreal-media-group", "umg-subbrand-ember", "assign", {"assignee": "rob"})
        other_unit = self.control.repository.act("dan", "unreal-talent", "talent-archetype", "reject", {"reason": "Synthetic talent rejection"})
        before_events = len(self.control.repository.review_events)
        before_audit = len(self.control.repository.audit_events)
        with self.assertRaisesRegex(MissionControlError, "supersede the current event"):
            self.control.repository.act("rob", "unreal-media-group", "umg-new-orbit", "reject", {"reason": "Stale target", "supersedes_id": approved["event_id"]})
        for label, target in [("wrong prospect", current), ("wrong business unit", other_unit), ("other state domain", assignment)]:
            with self.assertRaisesRegex(MissionControlError, "not part of this prospect state domain", msg=label):
                self.control.repository.act("rob", "unreal-media-group", "umg-subbrand-ember", "reject", {"reason": "Invalid target", "supersedes_id": target["event_id"]})
        with self.assertRaisesRegex(MissionControlError, "supersede the current event"):
            self.control.repository.act("rob", "unreal-media-group", "umg-new-orbit", "reject", {"reason": "Invented target", "supersedes_id": "event-9999"})
        self.assertEqual(len(self.control.repository.review_events), before_events)
        self.assertEqual(len(self.control.repository.audit_events), before_audit)

    def test_decision_ordering_breaks_timestamp_ties_by_stable_event_id(self) -> None:
        run_campaign(self.control, create_campaign(self.control), key="tie-break")
        approved = self.control.repository.act("rob", "unreal-media-group", "umg-new-orbit", "approve_deeper_research", {})
        rejected = self.control.repository.act("rob", "unreal-media-group", "umg-new-orbit", "reject", {"reason": "Synthetic tie", "supersedes_id": approved["event_id"]})
        self.assertEqual(approved["effective_at"], rejected["effective_at"])
        self.assertEqual(approved["recorded_at"], rejected["recorded_at"])
        self.assertLess(approved["event_id"], rejected["event_id"])
        item = self.control.repository.get_prospect("noah", "unreal-media-group", "umg-new-orbit")
        self.assertEqual(item["current_review"]["decision"]["event_id"], rejected["event_id"])
        self.assertEqual(item["current_decision"], "rejected")

    def test_identity_resolution_is_effective_append_only_and_correctable(self) -> None:
        run_campaign(self.control, create_campaign(self.control), key="identity")
        before = self.control.repository.get_prospect("noah", "unreal-media-group", "umg-duplicate-prism")
        self.assertEqual(before["effective_duplicate_state"], "possible_duplicate")
        self.assertIsNone(before["effective_matched_identity_id"])
        first = self.control.repository.act("noah", "unreal-media-group", "umg-duplicate-prism", "resolve_identity", {"matched_identity_id": "synthetic-prism-parent"})
        resolved = self.control.repository.get_prospect("noah", "unreal-media-group", "umg-duplicate-prism")
        self.assertEqual(resolved["effective_duplicate_state"], "resolved_duplicate")
        self.assertEqual(resolved["effective_matched_identity_id"], "synthetic-prism-parent")
        self.assertEqual(resolved["current_review"]["resolve_identity"]["event_id"], first["event_id"])
        self.assertEqual(resolved["duplicate_state"], "possible_duplicate")
        self.assertEqual(resolved["global_identity_id"], "global-prism-studio")
        self.assertEqual(resolved["matched_identity_ids"], ["synthetic-prism-parent"])
        with self.assertRaisesRegex(MissionControlError, "supersede the current event"):
            self.control.repository.act("noah", "unreal-media-group", "umg-duplicate-prism", "resolve_identity", {"matched_identity_id": "synthetic-prism-parent"})
        second = self.control.repository.act("noah", "unreal-media-group", "umg-duplicate-prism", "resolve_identity", {"matched_identity_id": "synthetic-prism-parent", "supersedes_id": first["event_id"]})
        corrected = self.control.repository.get_prospect("noah", "unreal-media-group", "umg-duplicate-prism")
        self.assertEqual([event["event_id"] for event in corrected["review_history"]], [first["event_id"], second["event_id"]])
        self.assertEqual(corrected["current_review"]["resolve_identity"]["event_id"], second["event_id"])
        self.assertEqual(corrected["effective_duplicate_state"], "resolved_duplicate")
        with self.assertRaisesRegex(MissionControlError, "exact listed"):
            self.control.repository.act("noah", "unreal-media-group", "umg-duplicate-prism", "resolve_identity", {"matched_identity_id": "invented-target", "supersedes_id": second["event_id"]})

    def test_resolved_identity_drives_approval_eligibility_reason(self) -> None:
        run_campaign(self.control, create_campaign(self.control), key="identity-eligibility")
        with self.assertRaisesRegex(MissionControlError, "must be resolved"):
            self.control.repository.act("rob", "unreal-media-group", "umg-duplicate-prism", "approve_deeper_research", {})
        self.control.repository.act("noah", "unreal-media-group", "umg-duplicate-prism", "resolve_identity", {"matched_identity_id": "synthetic-prism-parent"})
        with self.assertRaises(MissionControlError) as caught:
            self.control.repository.act("rob", "unreal-media-group", "umg-duplicate-prism", "approve_deeper_research", {})
        self.assertEqual(caught.exception.status, 409)
        self.assertIn("Resolved duplicate of synthetic identity synthetic-prism-parent", caught.exception.message)
        self.assertNotIn("must be resolved", caught.exception.message)
        with self.assertRaisesRegex(MissionControlError, "Existing relationship"):
            self.control.repository.act("rob", "unreal-media-group", "umg-shared-account", "approve_deeper_research", {})

    def test_audit_failure_has_no_partial_mutation(self) -> None:
        run_campaign(self.control, create_campaign(self.control), key="audit")
        before = len(self.control.repository.review_events)
        self.control.repository.fail_next_audit = True
        with self.assertRaisesRegex(MissionControlError, "could not be recorded"):
            self.control.repository.act("rob", "unreal-media-group", "umg-new-orbit", "note", {"text": "Must not persist"})
        self.assertEqual(len(self.control.repository.review_events), before)

    def test_worker_registration_is_manual_only_with_no_outbound_capability(self) -> None:
        # Phase 4 replaced the inert placeholder with a locally registered,
        # manual-only synthetic worker. It still has no outbound capability.
        with tempfile.TemporaryDirectory() as state_dir:
            service = RegisteredAgentService(
                self.control.repository,
                SqliteStore(Path(state_dir) / "state.sqlite3"),
                clock=lambda: FIXED_TIME,
            )
            registration = service.registration()
        self.assertEqual(registration["trigger"], "manual human form only")
        for key in ["credentials", "scheduler", "recurring_loop", "network", "creative", "likeness", "outreach"]:
            self.assertFalse(registration[key])

    def test_fixture_catalog_is_obviously_synthetic_and_example_only(self) -> None:
        for candidate in self.control.repository.fixture_candidates:
            self.assertTrue(candidate["account_name"].startswith("Synthetic "))
            self.assertTrue(candidate["domain"].endswith(".example"))
            for evidence in candidate["evidence"]:
                self.assertTrue(evidence["url"].split("/", 3)[2].endswith(".example"))
            serialized = json.dumps(candidate)
            self.assertNotIn("@", serialized)

    def test_executable_modules_have_no_outbound_or_dynamic_execution_imports(self) -> None:
        forbidden_imports = {"requests", "httpx", "socket", "smtplib", "subprocess"}
        for path in (APP_ROOT / "mission_control").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = {
                alias.name.split(".")[0]
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names
            }
            calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
            self.assertFalse(imports & forbidden_imports, path)
            self.assertFalse(calls & {"eval", "exec", "compile"}, path)

    def test_safe_evidence_url(self) -> None:
        self.assertTrue(safe_evidence_url("https://evidence.example/item"))
        for value in ["file:///etc/passwd", "javascript:alert(1)", "https://user:pass@evidence.example/item", "/relative"]:
            self.assertFalse(safe_evidence_url(value))


class HttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.control = make_control()
        self.state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.state_dir.cleanup)
        self.app = WebApplication(
            self.control,
            csrf_token="deterministic-csrf",
            state_path=Path(self.state_dir.name) / "state.sqlite3",
        )
        self.server = build_server(self.app, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method: str, path: str, fields: dict[str, str] | None = None, *, content_type: str = "application/x-www-form-urlencoded", raw: bytes | None = None, length: int | None = None) -> tuple[int, str, dict[str, str]]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        body = raw if raw is not None else (urlencode(fields or {}).encode() if fields is not None else None)
        headers: dict[str, str] = {}
        if body is not None:
            headers["Content-Type"] = content_type
            headers["Content-Length"] = str(len(body) if length is None else length)
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        text = response.read().decode()
        result_headers = {key: value for key, value in response.getheaders()}
        connection.close()
        return response.status, text, result_headers

    def campaign_fields(self, **overrides: str) -> dict[str, str]:
        fields = form()
        fields.update({"csrf_token": "deterministic-csrf", "actor": "noah"})
        fields.update(overrides)
        return fields

    def test_loopback_server_security_headers_and_accessible_empty_state(self) -> None:
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        status, body, headers = self.request("GET", "/campaigns?actor=noah&business_unit=unreal-media-group")
        self.assertEqual(status, 200)
        self.assertIn("Synthetic local review surface", body)
        self.assertIn("No campaigns exist", body)
        self.assertIn('aria-label="Primary"', body)
        self.assertIn("Content-Security-Policy", headers)
        self.assertEqual(headers["X-Frame-Options"], "DENY")

    def test_http_campaign_run_queues_detail_and_html_escaping(self) -> None:
        fields = self.campaign_fields(campaign_name="Synthetic &lt;script&gt; Campaign")
        status, body, _ = self.request("POST", "/campaigns", fields)
        self.assertEqual(status, 201)
        self.assertIn("Synthetic &amp;lt;script&amp;gt; Campaign", body)
        campaign = self.control.repository.campaigns("noah")[0]
        run_fields = {"csrf_token": "deterministic-csrf", "actor": "noah", "business_unit": "unreal-media-group", "idempotency_key": "http-run"}
        status, body, _ = self.request("POST", f'/campaigns/{campaign["family_id"]}/1/run', run_fields)
        self.assertEqual(status, 200)
        for value in ["Skill Version", "Skill Integrity", "Fixture Source Ids", "Estimated Cost Usd", "Cost Cap Usd", "Errors", "Stop Reason", "review pending"]:
            self.assertIn(value, body)
        status, queue_body, _ = self.request("GET", "/prospects?actor=noah&business_unit=unreal-media-group&queue=duplicate_reengagement")
        self.assertEqual(status, 200)
        self.assertIn("Synthetic Prism Studio", queue_body)
        status, detail, _ = self.request("GET", "/prospects/umg-new-orbit?actor=noah&business_unit=unreal-media-group")
        self.assertEqual(status, 200)
        self.assertIn("Append-only review history", detail)
        self.assertIn("credential-free source", detail)
        status, missing, _ = self.request("GET", "/prospects/umg-missing-evidence?actor=noah&business_unit=unreal-media-group")
        self.assertEqual(status, 200)
        self.assertIn("Missing evidence", missing)
        self.assertNotIn("<script>", body)

    def test_csrf_method_content_type_size_and_safe_errors(self) -> None:
        fields = self.campaign_fields(csrf_token="wrong", actor="rob")
        status, body, _ = self.request("POST", "/campaigns", fields)
        self.assertEqual(status, 403)
        self.assertIn("CSRF validation failed", body)
        self.assertIn('<option value="rob" selected>', body)
        self.assertNotIn('<option value="noah" selected>', body)
        status, _, _ = self.request("PUT", "/campaigns", {})
        self.assertEqual(status, 405)
        status, _, _ = self.request("HEAD", "/campaigns")
        self.assertEqual(status, 405)
        status, _, _ = self.request("POST", "/campaigns", fields, content_type="application/json")
        self.assertEqual(status, 400)
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        connection.putrequest("POST", "/campaigns")
        connection.putheader("Content-Type", "application/x-www-form-urlencoded")
        connection.putheader("Content-Length", str(MAX_BODY + 1))
        connection.endheaders()
        response = connection.getresponse()
        response.read()
        self.assertEqual(response.status, 400)
        connection.close()
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        connection.request("GET", "/campaigns", headers={"Host": "not-loopback.example"})
        response = connection.getresponse()
        response.read()
        self.assertEqual(response.status, 403)
        connection.close()
        status, body, _ = self.request("GET", "/../../etc/passwd?actor=noah&business_unit=unreal-media-group")
        self.assertEqual(status, 404)
        self.assertNotIn("Traceback", body)

    def test_validation_error_is_field_specific_and_preserves_input(self) -> None:
        fields = self.campaign_fields(
            campaign_name="Synthetic Invalid Filter",
            discovery_scope="filtered",
            verticals="",
        )
        status, body, _ = self.request("POST", "/campaigns", fields)
        self.assertEqual(status, 400)
        self.assertIn('id="verticals"', body)
        self.assertIn('aria-invalid="true"', body)
        self.assertIn('aria-describedby="verticals_error"', body)
        self.assertIn("filtered discovery requires at least one vertical", body)
        self.assertIn('value="Synthetic Invalid Filter"', body)

    def test_audit_failure_returns_bounded_500_without_partial_event(self) -> None:
        run_campaign(self.control, create_campaign(self.control), key="http-audit")
        before = len(self.control.repository.review_events)
        self.control.repository.fail_next_audit = True
        fields = {"csrf_token": "deterministic-csrf", "actor": "rob", "business_unit": "unreal-media-group", "action": "note", "text": "Synthetic note must roll back"}
        status, body, _ = self.request("POST", "/prospects/umg-new-orbit/actions", fields)
        self.assertEqual(status, 500)
        self.assertIn("could not be recorded", body)
        self.assertNotIn("Traceback", body)
        self.assertEqual(len(self.control.repository.review_events), before)

    def test_cross_business_unit_mutation_fails_before_run_creation(self) -> None:
        campaign = create_campaign(self.control)
        fields = {"csrf_token": "deterministic-csrf", "actor": "noah", "business_unit": "unreal-talent", "idempotency_key": "cross-bu"}
        status, body, _ = self.request("POST", f'/campaigns/{campaign["family_id"]}/1/run', fields)
        self.assertEqual(status, 403)
        self.assertIn("Business-unit access denied", body)
        self.assertEqual(len(self.control.repository.run_records), 0)

    def test_governed_http_actions_and_actor_allowlist(self) -> None:
        run_campaign(self.control, create_campaign(self.control), key="actions")
        fields = {"csrf_token": "deterministic-csrf", "actor": "rob", "business_unit": "unreal-media-group", "action": "note", "text": "Synthetic HTTP note"}
        status, body, _ = self.request("POST", "/prospects/umg-new-orbit/actions", fields)
        self.assertEqual(status, 200)
        self.assertIn("Append-only governed event recorded", body)
        for denied_actor in ["worker", "viewer", "prospecting_ingestion_service", "prospecting_projection_service"]:
            fields["actor"] = denied_actor
            status, _, _ = self.request("POST", "/prospects/umg-new-orbit/actions", fields)
            self.assertEqual(status, 403, denied_actor)

    def test_decision_forms_submit_the_current_decision_leaf(self) -> None:
        run_campaign(self.control, create_campaign(self.control), key="http-decision-forms")
        status, detail, _ = self.request("GET", "/prospects/umg-new-orbit?actor=rob&business_unit=unreal-media-group")
        self.assertEqual(status, 200)
        for kind in ["approve_deeper_research", "reject"]:
            self.assertIn(f'name="supersedes_id" value=""><input type="hidden" name="action" value="{kind}">', detail, kind)
        fields = {"csrf_token": "deterministic-csrf", "actor": "rob", "business_unit": "unreal-media-group", "action": "approve_deeper_research"}
        status, _, _ = self.request("POST", "/prospects/umg-new-orbit/actions", fields)
        self.assertEqual(status, 200)
        approved = self.control.repository.review_events[-1]
        status, detail, _ = self.request("GET", "/prospects/umg-new-orbit?actor=rob&business_unit=unreal-media-group")
        self.assertEqual(status, 200)
        for kind in ["approve_deeper_research", "reject"]:
            self.assertIn(f'name="supersedes_id" value="{approved.event_id}"><input type="hidden" name="action" value="{kind}">', detail, kind)

    def test_stale_decision_correction_returns_409_without_partial_mutation(self) -> None:
        run_campaign(self.control, create_campaign(self.control), key="http-stale")
        approved = self.control.repository.act("rob", "unreal-media-group", "umg-new-orbit", "approve_deeper_research", {})
        self.control.repository.act("rob", "unreal-media-group", "umg-new-orbit", "reject", {"reason": "Synthetic correction", "supersedes_id": approved["event_id"]})
        before_events = len(self.control.repository.review_events)
        before_audit = len(self.control.repository.audit_events)
        fields = {"csrf_token": "deterministic-csrf", "actor": "rob", "business_unit": "unreal-media-group", "action": "reject", "reason": "Synthetic stale correction", "supersedes_id": approved["event_id"]}
        status, body, _ = self.request("POST", "/prospects/umg-new-orbit/actions", fields)
        self.assertEqual(status, 409)
        self.assertIn("supersede the current event", body)
        self.assertNotIn("Traceback", body)
        self.assertEqual(len(self.control.repository.review_events), before_events)
        self.assertEqual(len(self.control.repository.audit_events), before_audit)

    def test_identity_detail_and_queue_display_the_effective_resolution(self) -> None:
        run_campaign(self.control, create_campaign(self.control), key="http-identity")
        status, detail, _ = self.request("GET", "/prospects/umg-duplicate-prism?actor=noah&business_unit=unreal-media-group")
        self.assertEqual(status, 200)
        self.assertIn("possible_duplicate", detail)
        self.assertIn("unresolved", detail)
        fields = {"csrf_token": "deterministic-csrf", "actor": "noah", "business_unit": "unreal-media-group", "action": "resolve_identity", "matched_identity_id": "synthetic-prism-parent"}
        status, body, _ = self.request("POST", "/prospects/umg-duplicate-prism/actions", fields)
        self.assertEqual(status, 200)
        self.assertIn("resolved_duplicate", body)
        self.assertIn("synthetic-prism-parent", body)
        self.assertIn("source classification possible_duplicate", body)
        status, queue_body, _ = self.request("GET", "/prospects?actor=noah&business_unit=unreal-media-group&queue=duplicate_reengagement")
        self.assertEqual(status, 200)
        self.assertIn("resolved_duplicate", queue_body)

    def test_registry_is_manual_only_and_offers_no_direct_worker_start(self) -> None:
        status, body, _ = self.request("GET", "/registry?actor=noah&business_unit=unreal-media-group")
        self.assertEqual(status, 200)
        self.assertIn("registered and enabled for manual synthetic execution", body)
        self.assertIn("manual human form only", body)
        self.assertNotIn("Start worker", body)
        status, detail, _ = self.request("GET", "/registry/brand-prospecting-agent?actor=noah&business_unit=unreal-media-group")
        self.assertEqual(status, 200)
        self.assertIn("unreal-media-brand-prospector", detail)
        self.assertIn("unreal-talent-campaign-prospector", detail)
        self.assertNotIn("Start worker", detail)


if __name__ == "__main__":
    unittest.main()

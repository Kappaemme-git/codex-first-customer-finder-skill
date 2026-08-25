from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "shared/prospecting-core/scripts"
sys.path.insert(0, str(CORE))

from classify_duplicate import classify_duplicate, validate_history  # noqa: E402
from common import ValidationError, load_json, score_talent, score_umg  # noqa: E402
from normalize_company_name import aliases_match, normalize_company_name, normalize_social_handle  # noqa: E402
from normalize_domain import normalize_domain  # noqa: E402
from render_report import render_html, render_markdown  # noqa: E402
from validate_campaign import validate_campaign  # noqa: E402
from validate_results import validate_result, validate_run_report  # noqa: E402


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.history = load_json(ROOT / "fixtures/prospecting/history/prospect-history.json", "history")
        validate_history(cls.history)
        cls.reengagement_campaign = load_json(ROOT / "fixtures/prospecting/campaigns/reengagement.json", "campaign")

    def test_domain_normalization(self) -> None:
        self.assertEqual(normalize_domain("HTTPS://WWW.Shop.Example.COM:443/path?q=1#x"), "example.com")
        self.assertEqual(normalize_domain("shop.example.co.uk/item"), "example.co.uk")
        self.assertEqual(normalize_domain("alpha.blogspot.com"), "alpha.blogspot.com")
        self.assertNotEqual(normalize_domain("alpha.blogspot.com"), normalize_domain("beta.blogspot.com"))

    def test_invalid_domain_and_url(self) -> None:
        with self.assertRaises(ValidationError):
            normalize_domain("localhost")
        report = load_json(ROOT / "fixtures/prospecting/expected/umg-sample-run.json")
        report["results"][0]["signals"][0]["source_url"] = "javascript:alert(1)"
        with self.assertRaises(ValidationError):
            validate_run_report(report)
        report = load_json(ROOT / "fixtures/prospecting/expected/umg-sample-run.json")
        report["results"][0]["signals"][0]["source_url"] = "https://example.com/x) [unsafe](https://evil.example"
        with self.assertRaises(ValidationError):
            validate_run_report(report)

    def test_company_and_social_normalization(self) -> None:
        self.assertEqual(normalize_company_name("The Ácme & Sons, LLC"), "the acme and sons")
        self.assertTrue(aliases_match("Existing Labs LLC", "Existing Labs"))
        self.assertEqual(normalize_social_handle("https://instagram.com/Example.Brand/"), "example.brand")

    def test_duplicate_fixture_cases(self) -> None:
        cases = load_json(ROOT / "fixtures/prospecting/candidates/duplicate-cases.json")
        campaign = copy.deepcopy(self.reengagement_campaign)
        for case in cases:
            with self.subTest(case=case["case"]):
                decision = classify_duplicate(case["candidate"], self.history, campaign, today=date(2026, 7, 16))
                self.assertEqual(decision["status"], case["expected"])

    def test_valid_new_trigger_reengages(self) -> None:
        candidate = load_json(ROOT / "fixtures/prospecting/candidates/reengagement.json")
        decision = classify_duplicate(candidate, self.history, self.reengagement_campaign, today=date(2026, 7, 16))
        self.assertEqual(decision["status"], "existing_new_trigger")
        self.assertTrue(decision["reengagement"])

    def test_invalid_or_future_trigger_does_not_reengage(self) -> None:
        for url, source_date in (("javascript:alert(1)", "2026-07-15"), ("https://existing.example/future", "2099-01-01")):
            with self.subTest(url=url, source_date=source_date):
                candidate = load_json(ROOT / "fixtures/prospecting/candidates/reengagement.json")
                candidate["new_trigger"].update({"source_url": url, "source_date": source_date})
                decision = classify_duplicate(candidate, self.history, self.reengagement_campaign, today=date(2026, 7, 16))
                self.assertEqual(decision["status"], "existing_no_new_trigger")

    def test_agency_brand_overlap(self) -> None:
        candidate = {"company_name": "Synthetic Agency", "domain": "agency.example", "company_type": "agency"}
        decision = classify_duplicate(candidate, self.history, self.reengagement_campaign)
        self.assertEqual(decision["status"], "agency_brand_overlap")
        self.assertEqual(decision["matched_prospect_id"], "p-agency-brand")

    def test_history_rejects_ambiguous_domain_and_social_identity(self) -> None:
        history = copy.deepcopy(self.history)
        duplicate_domain = copy.deepcopy(history["prospects"][0])
        duplicate_domain.update({
            "id": "p-duplicate-domain",
            "canonical_company_name": "Different Synthetic Company",
            "canonical_domain": "different.example",
            "domains": ["existing.example"],
            "alternate_names": [],
            "social_handles": {},
        })
        history["prospects"].append(duplicate_domain)
        with self.assertRaisesRegex(ValidationError, "assigned to multiple prospects"):
            validate_history(history)

        history = copy.deepcopy(self.history)
        duplicate_handle = copy.deepcopy(history["prospects"][0])
        duplicate_handle.update({
            "id": "p-duplicate-handle",
            "canonical_company_name": "Different Social Company",
            "canonical_domain": "different-social.example",
            "domains": [],
            "alternate_names": [],
            "social_handles": {"instagram": "@existinglabs"},
        })
        history["prospects"].append(duplicate_handle)
        with self.assertRaisesRegex(ValidationError, "social identity"):
            validate_history(history)

    def test_account_protections_override_distinct_subbrand(self) -> None:
        history = copy.deepcopy(self.history)
        record = history["prospects"][0]
        record["client_status"] = "active"
        record["subbrands"] = ["Protected Child"]
        decision = classify_duplicate(
            {"company_name": "Protected Child", "domain": "protected-child.example", "company_type": "brand", "independent_subbrand": True},
            history,
            self.reengagement_campaign,
        )
        self.assertEqual(decision["status"], "existing_client")

    def test_null_parent_company_does_not_break_matching(self) -> None:
        candidate = {"company_name": "Synthetic New", "domain": "new.example", "company_type": "brand", "parent_company": None}
        self.assertEqual(classify_duplicate(candidate, self.history, self.reengagement_campaign)["status"], "new_prospect")

    def test_exact_domain_has_priority_over_relationship_match(self) -> None:
        candidate = {"company_name": "Synthetic Subbrand", "domain": "existing.example", "company_type": "brand", "parent_company": "Synthetic Holdings"}
        decision = classify_duplicate(candidate, self.history, self.reengagement_campaign)
        self.assertEqual(decision["matched_prospect_id"], "p-existing")

    def test_campaign_cooldown_applies_without_explicit_cooldown_until(self) -> None:
        history = copy.deepcopy(self.history)
        record = history["prospects"][0]
        record["previous_discovery_dates"] = ["2026-07-15"]
        record["cooldown_until"] = None
        candidate = load_json(ROOT / "fixtures/prospecting/candidates/reengagement.json")
        decision = classify_duplicate(candidate, history, self.reengagement_campaign, today=date(2026, 7, 16))
        self.assertEqual(decision["status"], "existing_no_new_trigger")
        self.assertIn("cooldown", decision["reason"].lower())

    def test_no_new_trigger_and_disabled_reengagement(self) -> None:
        campaign = copy.deepcopy(self.reengagement_campaign)
        campaign["reengagement_enabled"] = False
        candidate = load_json(ROOT / "fixtures/prospecting/candidates/reengagement.json")
        self.assertEqual(classify_duplicate(candidate, self.history, campaign)["status"], "existing_no_new_trigger")

    def test_fixture_cooldown_override_is_not_available_to_normal_runs(self) -> None:
        history = copy.deepcopy(self.history)
        history["prospects"][0]["cooldown_until"] = "2099-01-01"
        candidate = load_json(ROOT / "fixtures/prospecting/candidates/reengagement.json")
        candidate["fixture_cooldown_override"] = True
        normal = classify_duplicate(candidate, history, self.reengagement_campaign, today=date(2026, 7, 16))
        self.assertEqual(normal["status"], "existing_no_new_trigger")
        controlled_test = classify_duplicate(
            candidate,
            history,
            self.reengagement_campaign,
            today=date(2026, 7, 16),
            allow_fixture_cooldown_override=True,
        )
        self.assertEqual(controlled_test["status"], "existing_new_trigger")

    def test_same_discovery_twice_is_not_new(self) -> None:
        candidate = {"company_name": "Synthetic Repeat", "domain": "repeat.example", "company_type": "brand"}
        first = classify_duplicate(candidate, self.history, self.reengagement_campaign)
        history = copy.deepcopy(self.history)
        record = copy.deepcopy(history["prospects"][0])
        record.update({"id": "p-repeat", "canonical_company_name": "Synthetic Repeat", "canonical_domain": "repeat.example", "domains": [], "alternate_names": [], "social_handles": {}})
        history["prospects"].append(record)
        second = classify_duplicate(candidate, history, self.reengagement_campaign)
        self.assertEqual(first["status"], "new_prospect")
        self.assertEqual(second["status"], "existing_no_new_trigger")

    def test_missing_history_fails_closed(self) -> None:
        with self.assertRaises(ValidationError):
            load_json(ROOT / "fixtures/prospecting/history/missing.json", "history")
        report = load_json(ROOT / "fixtures/prospecting/expected/umg-sample-run.json")
        report["history_loaded"] = False
        with self.assertRaises(ValidationError):
            validate_run_report(report)
        history = copy.deepcopy(self.history)
        history["prospects"][0]["suppressed"] = "false"
        with self.assertRaisesRegex(ValidationError, "must be boolean"):
            validate_history(history)

    def test_all_campaign_examples_validate(self) -> None:
        for path in sorted((ROOT / "fixtures/prospecting/campaigns").glob("*.json")):
            with self.subTest(path=path.name):
                validate_campaign(load_json(path), base_dir=path.parent)
        validate_history(load_json(ROOT / "fixtures/prospecting/history/starter-prospect-history.json"))

    def test_open_and_multiple_verticals(self) -> None:
        open_campaign = load_json(ROOT / "fixtures/prospecting/campaigns/umg-open-discovery.json")
        self.assertEqual(validate_campaign(open_campaign, require_history_file=False)["verticals"], [])
        multi = load_json(ROOT / "fixtures/prospecting/campaigns/umg-fitness-activewear.json")
        self.assertEqual(len(validate_campaign(multi, require_history_file=False)["verticals"]), 2)

    def test_umg_opportunity_filter_is_evidence_linked_and_excludes_ugc(self) -> None:
        report = load_json(ROOT / "fixtures/prospecting/expected/umg-sample-run.json")
        report["campaign"]["opportunity_filter"] = {
            "include_any": ["product_photography", "product_video"],
            "exclude": ["ugc_ad"],
        }
        result = report["results"][0]
        result["opportunity_matches"] = [{
            "kind": "product_photography",
            "basis": "inferred_low_confidence",
            "evidence_urls": [result["signals"][0]["source_url"]],
            "reason": "The current product launch supports review for product photography.",
        }]
        validate_run_report(report)

        missing = copy.deepcopy(report)
        missing["results"][0]["opportunity_matches"] = []
        with self.assertRaisesRegex(ValidationError, "included opportunity"):
            validate_run_report(missing)

        excluded = copy.deepcopy(report)
        excluded["results"][0]["opportunity_matches"].append({
            "kind": "ugc_ad",
            "basis": "observed",
            "evidence_urls": [result["signals"][0]["source_url"]],
            "reason": "The source explicitly centers the opportunity on UGC advertising.",
        })
        with self.assertRaisesRegex(ValidationError, "excluded opportunity"):
            validate_run_report(excluded)

        excluded["results"][0]["rejection_decision"] = {
            "rejected": True,
            "reasons": ["The evidence matches the campaign UGC-ad exclusion."],
        }
        excluded["results"][0]["future_handoff"]["ready"] = False
        excluded["summary"]["rejections"] = 1
        excluded["summary"]["qualified_shortlist"] = 0
        validate_run_report(excluded)

        unlinked = copy.deepcopy(report)
        unlinked["results"][0]["opportunity_matches"][0]["evidence_urls"] = [
            "https://unlinked.example/evidence"
        ]
        with self.assertRaisesRegex(ValidationError, "signal evidence"):
            validate_run_report(unlinked)

        unknown_basis = copy.deepcopy(report)
        unknown_basis["results"][0]["opportunity_matches"][0]["basis"] = "unknown"
        with self.assertRaisesRegex(ValidationError, "basis"):
            validate_run_report(unknown_basis)

        invalid_match_type = copy.deepcopy(report)
        invalid_match_type["results"][0]["opportunity_matches"][0]["kind"] = []
        with self.assertRaisesRegex(ValidationError, "controlled vocabulary"):
            validate_run_report(invalid_match_type)

        invalid_campaign = copy.deepcopy(report["campaign"])
        invalid_campaign["opportunity_filter"]["include_any"] = ["generic_marketing"]
        with self.assertRaisesRegex(ValidationError, "controlled vocabulary"):
            validate_campaign(invalid_campaign, require_history_file=False)

        overlapping = copy.deepcopy(report["campaign"])
        overlapping["opportunity_filter"]["exclude"].append("product_video")
        with self.assertRaisesRegex(ValidationError, "include and exclude"):
            validate_campaign(overlapping, require_history_file=False)

        talent_campaign = load_json(ROOT / "fixtures/prospecting/campaigns/talent-open-discovery.json")
        talent_campaign["opportunity_filter"] = copy.deepcopy(report["campaign"]["opportunity_filter"])
        with self.assertRaisesRegex(ValidationError, "Unreal Media Group"):
            validate_campaign(talent_campaign, require_history_file=False)

    def test_invalid_campaign(self) -> None:
        campaign = load_json(ROOT / "fixtures/prospecting/campaigns/umg-open-discovery.json")
        campaign["deep_research_limit"] = campaign["target_prospect_count"] + 1
        with self.assertRaises(ValidationError):
            validate_campaign(campaign, require_history_file=False)
        campaign = load_json(ROOT / "fixtures/prospecting/campaigns/talent-open-discovery.json")
        campaign.update({
            "allow_named_talent_recommendations": True,
            "approved_roster_path": "missing-approved-roster.json",
            "discovery_scope": "filtered",
            "verticals": ["sports beverage"],
            "talent_categories": ["athlete"],
            "campaign_channels": ["digital"],
        })
        with self.assertRaisesRegex(ValidationError, "approved roster file does not exist"):
            validate_campaign(campaign, require_history_file=False, base_dir=ROOT)

    def test_score_calculation(self) -> None:
        self.assertEqual(score_umg({"creative_need":4,"visual_fit":5,"budget_likelihood":4,"marketing_activity":4,"timing":5,"reachability":3,"evidence_quality":5}), 86)
        self.assertEqual(score_talent({"campaign_talent_fit":5,"budget_likelihood":4,"current_trigger":5,"rights_readiness":4,"brand_roster_compatibility":3,"decision_path":4,"evidence_quality":5}), 87)

    def test_unauthorized_named_talent_rejected(self) -> None:
        report = load_json(ROOT / "fixtures/prospecting/expected/talent-sample-run.json")
        report["results"][0]["named_talent"] = "Synthetic Famous Person"
        with self.assertRaisesRegex(ValidationError, "Unauthorized named talent"):
            validate_result(report["results"][0], report["campaign"])

    def test_named_talent_requires_matching_controlled_roster(self) -> None:
        report = load_json(ROOT / "fixtures/prospecting/expected/talent-sample-run.json")
        with tempfile.TemporaryDirectory() as temporary:
            roster_path = Path(temporary) / "roster.json"
            roster_path.write_text(json.dumps({
                "version": 1,
                "authorized_for_named_recommendations": True,
                "generated_at": "2026-07-16T00:00:00Z",
                "talent": [{
                    "talent_id": "talent-synthetic-1", "display_name": "Synthetic Roster Talent", "talent_category": "athlete",
                    "approved_brand_categories": ["beverage"], "restricted_categories": [], "geographic_rights_availability": ["United States"],
                    "channel_rights": ["digital"], "duration_constraints": "Requires deal review", "exclusivity_conflicts": [],
                    "approval_status": "approved", "current_availability_status": "requires_confirmation",
                    "minimum_commercial_requirements": "Internal review", "notes": "Synthetic test only", "data_freshness": "2026-07-16"
                }]
            }), encoding="utf-8")
            report["campaign"].update({
                "allow_named_talent_recommendations": True,
                "approved_roster_path": str(roster_path),
                "discovery_scope": "filtered",
                "verticals": ["beverage"],
                "campaign_channels": ["digital"],
            })
            result = report["results"][0]
            result.update({"named_talent": "Synthetic Roster Talent", "talent_recommendation_type": "approved_roster", "approved_roster_authorization": True})
            validate_result(result, report["campaign"])
            result["named_talent"] = "Unlisted Person"
            with self.assertRaisesRegex(ValidationError, "not an approved"):
                validate_result(result, report["campaign"])

            result["named_talent"] = "Synthetic Roster Talent"
            roster = json.loads(roster_path.read_text(encoding="utf-8"))
            roster["talent"][0]["restricted_categories"] = ["beverage"]
            roster_path.write_text(json.dumps(roster), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "restricted-category"):
                validate_result(result, report["campaign"])

    def test_result_freshness_threshold_and_summary_invariants(self) -> None:
        report = load_json(ROOT / "fixtures/prospecting/expected/umg-sample-run.json")
        report["results"][0]["signals"][0]["source_date"] = "2099-01-01"
        with self.assertRaisesRegex(ValidationError, "after discovery"):
            validate_run_report(report)
        report = load_json(ROOT / "fixtures/prospecting/expected/umg-sample-run.json")
        report["campaign"]["minimum_qualification_score"] = 90
        with self.assertRaisesRegex(ValidationError, "Below-threshold"):
            validate_run_report(report)
        report = load_json(ROOT / "fixtures/prospecting/expected/umg-sample-run.json")
        report["summary"]["new_unique_prospects"] = 999
        with self.assertRaisesRegex(ValidationError, "new_unique_prospects"):
            validate_run_report(report)
        report = load_json(ROOT / "fixtures/prospecting/expected/umg-sample-run.json")
        report["results"] = []
        with self.assertRaisesRegex(ValidationError, "Every raw candidate"):
            validate_run_report(report)

    def test_noneligible_duplicate_cannot_qualify_or_be_handoff_ready(self) -> None:
        report = load_json(ROOT / "fixtures/prospecting/expected/umg-sample-run.json")
        result = report["results"][0]
        result["duplicate_decision"] = {
            "status": "suppressed",
            "reason": "Synthetic suppression.",
            "matched_prospect_id": "p-suppressed",
            "matched_prospect_ids": ["p-suppressed"],
            "reengagement": False,
        }
        report["summary"] = {
            "raw_candidate_count": 1,
            "new_unique_prospects": 0,
            "duplicates": 1,
            "reengagement_prospects": 0,
            "rejections": 0,
            "qualified_shortlist": 0,
        }
        with self.assertRaisesRegex(ValidationError, "must be rejected"):
            validate_run_report(report)

        result["rejection_decision"] = {"rejected": True, "reasons": ["Suppressed record."]}
        report["summary"]["rejections"] = 1
        with self.assertRaisesRegex(ValidationError, "cannot be handoff-ready"):
            validate_run_report(report)
        result["future_handoff"]["ready"] = False
        validate_run_report(report)

    def test_event_lineage_and_test_only_fields_are_enforced(self) -> None:
        report = load_json(ROOT / "fixtures/prospecting/expected/umg-sample-run.json")
        report["results"][0]["discovery_event"]["campaign_name"] = "Wrong campaign"
        with self.assertRaisesRegex(ValidationError, "campaign_name"):
            validate_run_report(report)
        report = load_json(ROOT / "fixtures/prospecting/expected/umg-sample-run.json")
        report["raw_candidates"][0]["fixture_cooldown_override"] = True
        with self.assertRaisesRegex(ValidationError, "test-only"):
            validate_run_report(report)

    def test_private_contact_data_is_rejected(self) -> None:
        report = load_json(ROOT / "fixtures/prospecting/expected/umg-sample-run.json")
        report["results"][0]["recommended_next_action"] = "Email private.person@example.com"
        with self.assertRaisesRegex(ValidationError, "Email-shaped"):
            validate_run_report(report)
        report = load_json(ROOT / "fixtures/prospecting/expected/umg-sample-run.json")
        report["results"][0]["recommended_next_action"] = "Call +1 (212) 555-0100"
        with self.assertRaisesRegex(ValidationError, "Phone-shaped"):
            validate_run_report(report)

    def test_reports_escape_untrusted_text(self) -> None:
        report = load_json(ROOT / "fixtures/prospecting/expected/umg-sample-run.json")
        html = render_html(report)
        markdown = render_markdown(report)
        self.assertIn("&lt;test&gt;", html)
        self.assertNotIn("<test>", html)
        self.assertIn(r"\<test\>", markdown)
        self.assertIn("product_photography", html)
        self.assertIn(r"product\_photography", markdown)
        self.assertIn("Phase 6", html)
        talent_html = render_html(load_json(ROOT / "fixtures/prospecting/expected/talent-sample-run.json"))
        self.assertIn("Search assumptions", talent_html)
        self.assertIn("requires_internal_rights_check", talent_html)
        self.assertIn("Brand-safety flags", talent_html)
        self.assertIn("Buyer path", talent_html)

    def test_schema_files_and_sample_reports(self) -> None:
        for path in sorted((ROOT / "shared/prospecting-core/schemas").glob("*.json")):
            with self.subTest(path=path.name):
                schema = load_json(path, "schema")
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertIn("title", schema)
        run_schema = load_json(ROOT / "shared/prospecting-core/schemas/run-report.schema.json")
        self.assertEqual(run_schema["properties"]["campaign"]["$ref"], "campaign-config.schema.json")
        self.assertEqual(run_schema["properties"]["results"]["items"]["$ref"], "prospect-result.schema.json")
        for name in ("umg-sample-run.json", "talent-sample-run.json"):
            validate_run_report(load_json(ROOT / "fixtures/prospecting/expected" / name))


class InstallerAndOriginalRegressionTests(unittest.TestCase):
    def run_node(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["node", *args], cwd=ROOT, text=True, capture_output=True, check=False)

    def test_original_installer_and_renderer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skills = Path(temporary) / "skills"
            result = self.run_node("scripts/install.js", "--skills-dir", str(skills))
            self.assertEqual(result.returncode, 0, result.stderr)
            installed = skills / "first-customer-finder"
            self.assertTrue((installed / "SKILL.md").is_file())
            source = Path(temporary) / "original.json"
            output = Path(temporary) / "original.html"
            source.write_text(json.dumps({"title":"Original regression","product":"Synthetic","product_url":"https://example.com","target_customer":"Synthetic teams","search_scope":"Synthetic","generated_at":"2026-07-16","verdict":"Fixture","prospects":[],"patterns":[],"outreach_plan":{},"limits":[]}), encoding="utf-8")
            render = subprocess.run([sys.executable, str(installed / "scripts/generate_report.py"), str(source), str(output)], text=True, capture_output=True, check=False)
            self.assertEqual(render.returncode, 0, render.stderr)
            self.assertIn("Original regression", output.read_text(encoding="utf-8"))

    def test_unreal_installer_selections_and_wrappers(self) -> None:
        expected = {
            "original": {"first-customer-finder"},
            "umg": {"unreal-media-brand-prospector", "unreal-prospecting-core"},
            "talent": {"unreal-talent-campaign-prospector", "unreal-prospecting-core"},
            "unreal": {"unreal-media-brand-prospector", "unreal-talent-campaign-prospector", "unreal-prospecting-core"},
            "all": {"first-customer-finder", "unreal-media-brand-prospector", "unreal-talent-campaign-prospector", "unreal-prospecting-core"},
        }
        for selection, names in expected.items():
            with self.subTest(selection=selection), tempfile.TemporaryDirectory() as temporary:
                skills = Path(temporary) / "skills"
                result = self.run_node("scripts/install-unreal.js", "--skill", selection, "--skills-dir", str(skills))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual({path.name for path in skills.iterdir()}, names)
                if selection in {"umg", "unreal", "all"}:
                    output = Path(temporary) / "umg.html"
                    rendered = subprocess.run([sys.executable, str(skills / "unreal-media-brand-prospector/scripts/generate_report.py"), str(ROOT / "fixtures/prospecting/expected/umg-sample-run.json"), str(output)], text=True, capture_output=True, check=False)
                    self.assertEqual(rendered.returncode, 0, rendered.stderr)
                    self.assertTrue(output.is_file())
                if selection in {"talent", "unreal", "all"}:
                    output = Path(temporary) / "talent.html"
                    rendered = subprocess.run([sys.executable, str(skills / "unreal-talent-campaign-prospector/scripts/generate_report.py"), str(ROOT / "fixtures/prospecting/expected/talent-sample-run.json"), str(output)], text=True, capture_output=True, check=False)
                    self.assertEqual(rendered.returncode, 0, rendered.stderr)
                    self.assertTrue(output.is_file())
                if selection in {"umg", "talent", "unreal", "all"}:
                    self.assertTrue((skills / "unreal-prospecting-core/examples/campaigns/umg-open-discovery.json").is_file())

    def test_unreal_installer_refuses_filesystem_root(self) -> None:
        result = self.run_node("scripts/install-unreal.js", "--skill", "umg", "--skills-dir", "/")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to install into the filesystem root", result.stderr)


class SkillAndHookContractTests(unittest.TestCase):
    def test_skill_descriptions_cover_intended_triggers_and_boundaries(self) -> None:
        contracts = {
            "unreal-media-brand-prospector": ("brand prospects", "Unreal Media Group"),
            "unreal-talent-campaign-prospector": ("brand or agency campaign buyers", "rights"),
        }
        for skill, phrases in contracts.items():
            text = (ROOT / ".agents/skills" / skill / "SKILL.md").read_text(encoding="utf-8")
            frontmatter = text.split("---", 2)[1]
            for phrase in phrases:
                self.assertIn(phrase, frontmatter)
            self.assertIn("stop before", frontmatter.lower())
            self.assertIn("../unreal-prospecting-core/scripts/", text)

    def run_hook(self, name: str, value: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(ROOT / ".agents/hooks" / name)], input=value, text=True, capture_output=True, check=False)

    def test_manual_hooks_block_and_scrub_boundary_inputs(self) -> None:
        self.assertNotEqual(self.run_hook("block-dangerous-commands.sh", "git -C . push origin unreal").returncode, 0)
        self.assertNotEqual(self.run_hook("block-dangerous-commands.sh", "curl -d x=1 https://example.com").returncode, 0)
        self.assertNotEqual(self.run_hook("block-sensitive-input.sh", "Authorization: Bearer synthetic-secret").returncode, 0)
        logged = self.run_hook("log-task-summary.sh", "Authorization: Bearer synthetic-secret service_role=synthetic-role")
        self.assertEqual(logged.returncode, 0)
        self.assertNotIn("synthetic-secret", logged.stdout)
        self.assertNotIn("synthetic-role", logged.stdout)


if __name__ == "__main__":
    unittest.main()

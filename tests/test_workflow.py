"""Offline regression tests; fixtures are fictional, never customer evidence."""

import copy
import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "first-customer-finder" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from prospect_data import (atomic_json, canonical_url, normalize_report, prepare_history,
                           prospect_id, public_url, read_state, state_lock)
from generate_report import build_html
from report_exports import DEMO_NOTICE, build_csv, build_markdown


def fixture():
    return json.loads((ROOT / "examples" / "demo.json").read_text())


class DataTests(unittest.TestCase):
    def test_scores_computed_and_sorted(self):
        raw = fixture()
        for p in raw["prospects"]:
            p["score"] = 1
        result = normalize_report(raw)
        self.assertEqual(result["prospects"][0]["score"], 90)
        self.assertEqual([p["score"] for p in result["prospects"]], sorted([p["score"] for p in result["prospects"]], reverse=True))
        self.assertEqual(raw["prospects"][0]["score"], 1)

    def test_identity_normalization(self):
        self.assertEqual(prospect_id("http://www.example.com/team/?utm_source=x#reply"), prospect_id("https://example.com/team"))
        self.assertEqual(prospect_id("https://twitter.com/founder"), prospect_id("https://x.com/founder/"))
        self.assertNotEqual(prospect_id("https://github.com/a"), prospect_id("https://github.com/b"))
        self.assertNotEqual(prospect_id("https://example.com/?company=a"), prospect_id("https://example.com/?company=b"))

    def test_duplicate_entities_rejected(self):
        raw = fixture()
        raw["prospects"].append(copy.deepcopy(raw["prospects"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            normalize_report(raw)

    def test_unsafe_urls(self):
        for value in ("javascript:alert(1)", "file:///etc/passwd", "https://user:secret@example.com", "https://example.com\n/path", "https://example.com:bad", "https://example.com\\x"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                public_url(value)

    def test_invalid_dimensions(self):
        for value in (True, float("nan"), float("inf"), -1, 6, "5"):
            raw = fixture()
            raw["prospects"][0]["dimensions"]["timing"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_report(raw)

    def test_unknown_date_is_not_fresh(self):
        raw = fixture()
        raw["prospects"][0]["signal_date"] = None
        with self.assertRaisesRegex(ValueError, "Undated"):
            normalize_report(raw)
        raw["prospects"][0]["dimensions"]["timing"] = 2
        normalize_report(raw)

    def test_future_dates_rejected(self):
        raw = fixture()
        raw["prospects"][0]["signal_date"] = "2099-01-01"
        with self.assertRaisesRegex(ValueError, "later"):
            normalize_report(raw)

    def test_unverified_sources_rejected(self):
        raw = fixture()
        raw["prospects"][0]["evidence_status"] = "snippet_only"
        with self.assertRaisesRegex(ValueError, "inspected"):
            normalize_report(raw)

    def test_missing_contact_route_not_invented(self):
        raw = fixture()
        raw["prospects"][0]["contact_route"] = {"status": "not_found", "note": "No suitable route found"}
        with self.assertRaisesRegex(ValueError, "reachability"):
            normalize_report(raw)
        raw["prospects"][0]["dimensions"]["reachability"] = 1
        normalize_report(raw)
        raw["prospects"][0]["contact_route"]["url"] = "https://example.com/guess"
        with self.assertRaisesRegex(ValueError, "guessed"):
            normalize_report(raw)

    def test_cta_must_appear_in_opener(self):
        raw = fixture()
        raw["prospects"][0]["opener"] = "Would this be useful?"
        with self.assertRaisesRegex(ValueError, "CTA"):
            normalize_report(raw)

    def test_wrong_product_and_demo_boundaries(self):
        data = normalize_report(fixture())
        _, state = prepare_history(data, None)
        for field, value in (("project_key", "another-product"), ("demo", False)):
            changed = copy.deepcopy(data)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                prepare_history(changed, state)

    def test_repeat_search_excludes_seen(self):
        data = normalize_report(fixture())
        _, state = prepare_history(data, None)
        report, next_state = prepare_history(data, state, new_only=True)
        self.assertEqual(report["prospects"], [])
        self.assertEqual(report["history_summary"]["excluded"]["seen"], 3)
        self.assertEqual(len(next_state["prospects"]), 3)
        self.assertEqual(report["patterns"], [])

    def test_only_new_entities_enter_next_round(self):
        raw = fixture()
        data = normalize_report(raw)
        _, state = prepare_history(data, None)
        new = copy.deepcopy(raw["prospects"][0])
        new["name"] = "Another fictional studio"
        new["entity_url"] = "https://example.com/another-studio"
        raw["prospects"].append(new)
        report, next_state = prepare_history(normalize_report(raw), state, new_only=True)
        self.assertEqual(len(report["prospects"]), 1)
        self.assertEqual(report["prospects"][0]["name"], new["name"])
        self.assertEqual(len(next_state["prospects"]), 4)

    def test_malformed_optional_data_rejected(self):
        for field, value in (("patterns", ["bad"]), ("limits", "bad"), ("outreach_plan", []), ("schema_version", True)):
            raw = fixture()
            raw[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                normalize_report(raw)
        raw = fixture()
        raw["patterns"][0]["count"] = 1000
        with self.assertRaisesRegex(ValueError, "Pattern count"):
            normalize_report(raw)

    def test_outcome_and_rejections_survive_refresh(self):
        data = normalize_report(fixture())
        _, state = prepare_history(data, None)
        ids = [p["id"] for p in data["prospects"]]
        state["prospects"][ids[0]]["status"] = "contacted"
        state["prospects"][ids[0]]["feedback"] = "keep"
        state["prospects"][ids[1]]["feedback"] = "reject"
        report, next_state = prepare_history(data, state)
        self.assertEqual([p["id"] for p in report["prospects"]], [ids[2]])
        self.assertEqual(next_state["prospects"][ids[0]]["status"], "contacted")
        self.assertEqual(report["prospects"][0]["history_label"], "Previously seen")

    def test_no_history_for_legacy(self):
        data = normalize_report({"prospects": []})
        self.assertIn("legacy_warning", data)
        with self.assertRaises(ValueError):
            prepare_history(data, None)


class ExportTests(unittest.TestCase):
    def test_all_formats_mark_demo(self):
        data = normalize_report(fixture())
        for builder in (build_markdown, build_html, build_csv):
            with self.subTest(builder=builder.__name__):
                self.assertIn(DEMO_NOTICE, builder(data))
                empty = copy.deepcopy(data)
                empty["prospects"] = []
                self.assertIn(DEMO_NOTICE, builder(empty))

    def test_markdown_and_html_escape_untrusted_content(self):
        data = normalize_report(fixture())
        data["prospects"][0]["name"] = '<script>alert(1)</script> [bad](javascript:x) | row'
        for builder in (build_markdown, build_html):
            result = builder(data)
            self.assertNotIn("<script>", result)
            self.assertNotIn('href="javascript:', result)
        self.assertIn("\\| row", build_markdown(data))

    def test_csv_formula_injection(self):
        data = normalize_report(fixture())
        data["prospects"][0]["name"] = '  =HYPERLINK("https://evil.example")'
        rows = list(csv.DictReader(io.StringIO(build_csv(data))))
        self.assertTrue(rows[1]["name"].startswith("'"))
        self.assertEqual(rows[1]["record_type"], "prospect")

    def test_route_and_manual_next_step_in_every_format(self):
        data = normalize_report(fixture())
        for builder in (build_markdown, build_html, build_csv):
            result = builder(data)
            self.assertIn(data["prospects"][0]["contact_route"]["url"], result)
            self.assertIn(data["prospects"][0]["next_step"], result)


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.input = self.folder / "analysis.json"
        self.input.write_text(json.dumps(fixture()))
        self.state = self.folder / "state.json"

    def run_cli(self, script, *args, success=True):
        result = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def generate(self, name="report.md", *extra):
        return self.run_cli("generate_report.py", self.input, self.folder / name, "--state", self.state, *extra)

    def test_report_history_feedback_more_and_refresh(self):
        self.generate("round1.md", "--csv", self.folder / "leads.csv", "--html", self.folder / "report.html")
        state = read_state(self.state)
        ids = list(state["prospects"])
        self.run_cli("prospect_history.py", "--state", self.state, "feedback", ids[0], "keep", "--reason", "Good fit")
        self.run_cli("prospect_history.py", "--state", self.state, "feedback", ids[1], "reject", "--reason", "Wrong size")
        self.run_cli("prospect_history.py", "--state", self.state, "status", ids[0], "contacted")
        self.run_cli("prospect_history.py", "--state", self.state, "profile", "--prefer", "Owner-led", "--avoid", "Enterprise")
        self.run_cli("prospect_history.py", "--state", self.state, "profile", "--prefer", "Small studios")
        state = read_state(self.state)
        self.assertEqual(state["profile"]["avoid"], ["Enterprise"])
        self.assertEqual(state["profile"]["prefer"], ["Small studios"])
        self.generate("round2.md", "--new-only")
        self.assertIn("0 potential customers", (self.folder / "round2.md").read_text())
        self.generate("refresh.md")
        self.assertIn("1 potential customers", (self.folder / "refresh.md").read_text())
        self.assertEqual(read_state(self.state)["prospects"][ids[0]]["status"], "contacted")

    def test_profile_changes_only_from_explicit_command(self):
        self.generate()
        key = next(iter(read_state(self.state)["prospects"]))
        self.run_cli("prospect_history.py", "--state", self.state, "feedback", key, "reject", "--reason", "Too big")
        self.assertEqual(read_state(self.state)["profile"], {"prefer": [], "avoid": []})

    def test_same_output_cannot_overwrite_input_or_history(self):
        original = self.input.read_bytes()
        self.run_cli("generate_report.py", self.input, self.input, success=False)
        self.assertEqual(self.input.read_bytes(), original)
        self.generate()
        before = self.state.read_bytes()
        self.run_cli("generate_report.py", self.input, self.folder / "other.md", "--csv", self.state, "--state", self.state, success=False)
        self.assertEqual(self.state.read_bytes(), before)

    def test_existing_output_rejected_without_updating_state(self):
        self.generate()
        before = self.state.read_bytes()
        self.run_cli("generate_report.py", self.input, self.folder / "report.md", "--state", self.state, success=False)
        self.assertEqual(self.state.read_bytes(), before)

    def test_invalid_input_leaves_no_output_or_state(self):
        raw = fixture()
        raw["prospects"][0]["evidence_status"] = "unavailable"
        self.input.write_text(json.dumps(raw))
        self.run_cli("generate_report.py", self.input, self.folder / "report.md", "--state", self.state, success=False)
        self.assertFalse(self.state.exists())
        self.assertFalse((self.folder / "report.md").exists())

    def test_lock_conflict_preserves_state(self):
        self.generate()
        before = self.state.read_bytes()
        with state_lock(self.state):
            self.run_cli("prospect_history.py", "--state", self.state, "profile", "--avoid", "Enterprise", success=False)
        self.assertEqual(self.state.read_bytes(), before)
        self.assertFalse(self.state.with_suffix(".json.lock").exists())

    def test_unknown_id_does_not_modify_history(self):
        self.generate()
        before = self.state.read_bytes()
        self.run_cli("prospect_history.py", "--state", self.state, "status", "p_missing", "contacted", success=False)
        self.assertEqual(self.state.read_bytes(), before)

    def test_malformed_and_symlink_history_refused(self):
        self.state.write_text('{"schema_version": 9}')
        self.run_cli("prospect_history.py", "--state", self.state, "show", success=False)
        alias = self.folder / "alias.json"
        alias.symlink_to(self.state)
        with self.assertRaisesRegex(ValueError, "symlink"):
            read_state(alias)

    def test_legacy_html_command(self):
        self.input.write_text(json.dumps({"product": "Legacy", "prospects": []}))
        self.run_cli("generate_report.py", self.input, self.folder / "legacy.html")
        self.assertIn("Legacy input", (self.folder / "legacy.html").read_text())


if __name__ == "__main__":
    unittest.main()

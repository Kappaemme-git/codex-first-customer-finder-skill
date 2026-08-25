#!/usr/bin/env python3
"""Validate prospect results and run-report safety invariants."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from common import ValidationError, load_json, parse_date, parse_datetime, require_http_url, require_object, score_talent, score_umg
from normalize_domain import normalize_domain
from validate_campaign import OPPORTUNITY_KINDS, load_approved_roster, validate_campaign

ALLOWED_DUPLICATE_STATUSES = {
    "new_prospect", "existing_no_new_trigger", "existing_new_trigger", "existing_active_outreach",
    "existing_client", "existing_partner", "suppressed", "possible_duplicate_needs_review",
    "distinct_subbrand", "parent_company_relationship", "agency_brand_overlap",
}
ELIGIBLE_SHORTLIST_STATUSES = {"new_prospect", "existing_new_trigger", "distinct_subbrand"}
EVIDENCE_BASES = {"observed", "inferred_high_confidence", "inferred_low_confidence", "unknown", "requires_internal_rights_check"}
OPPORTUNITY_BASES = {"observed", "inferred_high_confidence", "inferred_low_confidence"}
EXPECTED_SKILLS = {
    "unreal-media-group": "unreal-media-brand-prospector",
    "unreal-talent": "unreal-talent-campaign-prospector",
}
EMAIL_PATTERN = re.compile(r"(?i)(?<![\w.+-])[\w.+-]+@[a-z0-9.-]+\.[a-z]{2,}(?![\w.-])")
PHONE_PATTERN = re.compile(r"(?<!\w)\+?\d(?:[ .()-]*\d){9,}(?!\w)")


def _reject_private_contact_data(value: Any, path: str = "report") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in {"email", "email_address", "phone", "phone_number", "mobile", "private_contact", "personal_contact"}:
                raise ValidationError(f"Private contact field is prohibited at {path}.{key}.")
            _reject_private_contact_data(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_private_contact_data(child, f"{path}[{index}]")
    elif isinstance(value, str) and EMAIL_PATTERN.search(value):
        raise ValidationError(f"Email-shaped contact data is prohibited at {path}.")
    elif isinstance(value, str) and PHONE_PATTERN.search(value):
        raise ValidationError(f"Phone-shaped contact data is prohibited at {path}.")


def _category_overlaps(left: list[str], right: list[str]) -> bool:
    for first in left:
        a = first.strip().casefold()
        for second in right:
            b = second.strip().casefold()
            if a == b or a in b or b in a:
                return True
    return False


def _validate_opportunity_matches(result: dict[str, Any], campaign: dict[str, Any], signal_urls: set[str]) -> set[str]:
    opportunity_filter = campaign.get("opportunity_filter")
    matches = result.get("opportunity_matches")
    if opportunity_filter is None:
        if matches is not None:
            raise ValidationError("opportunity_matches requires a campaign opportunity_filter.")
        return set()
    if result.get("business_unit") != "unreal-media-group":
        raise ValidationError("opportunity_matches is available only for Unreal Media Group results.")
    if not isinstance(matches, list):
        raise ValidationError("Results for a filtered opportunity campaign require opportunity_matches.")

    kinds: set[str] = set()
    required = {"kind", "basis", "evidence_urls", "reason"}
    for index, raw_match in enumerate(matches):
        match = require_object(raw_match, f"opportunity match {index}")
        missing = sorted(required - set(match))
        unknown = sorted(set(match) - required)
        if missing:
            raise ValidationError(f"Opportunity match {index} is missing: {', '.join(missing)}.")
        if unknown:
            raise ValidationError(f"Opportunity match {index} contains unsupported fields: {', '.join(unknown)}.")
        if not isinstance(match["kind"], str) or match["kind"] not in OPPORTUNITY_KINDS:
            raise ValidationError("Opportunity match kind is outside the controlled vocabulary.")
        if not isinstance(match["basis"], str) or match["basis"] not in OPPORTUNITY_BASES:
            raise ValidationError("Opportunity match basis is invalid.")
        if not isinstance(match["reason"], str) or not match["reason"].strip():
            raise ValidationError("Opportunity match reason must be a non-empty string.")
        evidence_urls = match["evidence_urls"]
        if not isinstance(evidence_urls, list) or not evidence_urls:
            raise ValidationError("Opportunity match evidence_urls must be a non-empty array.")
        validated_urls = [require_http_url(url) for url in evidence_urls]
        if len(validated_urls) != len(set(validated_urls)):
            raise ValidationError("Opportunity match evidence_urls must be unique.")
        if not set(validated_urls).issubset(signal_urls):
            raise ValidationError("Every opportunity match must cite preserved signal evidence.")
        kinds.add(match["kind"])
    return kinds


def validate_result(result: dict[str, Any], campaign: dict[str, Any], *, base_dir: Path | None = None) -> dict[str, Any]:
    required = {
        "company_name", "company_type", "business_unit", "identity", "discovery_event", "signals",
        "score_snapshot", "duplicate_decision", "rejection_decision", "reason_for_qualification",
        "important_uncertainty", "recommended_next_action", "future_handoff",
    }
    missing = sorted(required - set(result))
    if missing:
        raise ValidationError(f"Result is missing fields: {', '.join(missing)}.")
    if not isinstance(result["company_name"], str) or not result["company_name"].strip() or result["company_type"] not in {"brand", "agency"}:
        raise ValidationError("Result requires a non-empty company_name and brand or agency company_type.")
    if result["business_unit"] != campaign.get("business_unit"):
        raise ValidationError("Result business_unit does not match the campaign.")
    identity = require_object(result["identity"], "identity")
    if not identity.get("canonical_domain") or not identity.get("canonical_company_name"):
        raise ValidationError("Result identity requires canonical domain and company name.")
    normalize_domain(identity["canonical_domain"])

    event = require_object(result["discovery_event"], "discovery_event")
    discovered_at = parse_datetime(event.get("discovered_at"), "discovered_at")
    discovered_date = discovered_at.date()
    if event.get("campaign_name") != campaign.get("campaign_name"):
        raise ValidationError("discovery_event campaign_name must match the campaign.")
    source_urls = event.get("source_urls", [])
    if not isinstance(source_urls, list) or not source_urls:
        raise ValidationError("discovery_event source_urls must be a non-empty array.")
    validated_event_urls = {require_http_url(source) for source in source_urls}

    signals = result["signals"]
    if not isinstance(signals, list) or not signals:
        raise ValidationError("Every result requires at least one current signal.")
    official = False
    fresh_signal = False
    signal_urls: set[str] = set()
    for signal in signals:
        signal = require_object(signal, "signal")
        signal_url = require_http_url(signal.get("source_url"))
        signal_urls.add(signal_url)
        if signal.get("basis") not in EVIDENCE_BASES:
            raise ValidationError("Signal basis is invalid.")
        source_date = parse_date(signal.get("source_date"), "signal source_date")
        if source_date > discovered_date:
            raise ValidationError("Signal source_date cannot be after discovery.")
        fresh_signal = fresh_signal or (discovered_date - source_date).days <= campaign.get("maximum_evidence_age_days", 0)
        official = official or signal.get("official_source") is True
    if not signal_urls.issubset(validated_event_urls):
        raise ValidationError("Every signal source_url must be preserved in discovery_event source_urls.")
    opportunity_kinds = _validate_opportunity_matches(result, campaign, signal_urls)

    rejection = require_object(result["rejection_decision"], "rejection_decision")
    if not isinstance(rejection.get("rejected"), bool) or not isinstance(rejection.get("reasons"), list):
        raise ValidationError("rejection_decision requires boolean rejected and an array of reasons.")
    if not official and not rejection["rejected"]:
        raise ValidationError("Qualified results require an official company or agency source.")

    duplicate = require_object(result["duplicate_decision"], "duplicate_decision")
    status = duplicate.get("status")
    if status not in ALLOWED_DUPLICATE_STATUSES:
        raise ValidationError("Duplicate status is invalid.")
    matched_id = duplicate.get("matched_prospect_id")
    matched_ids = duplicate.get("matched_prospect_ids", [])
    if matched_ids is not None and (not isinstance(matched_ids, list) or any(not isinstance(value, str) or not value for value in matched_ids)):
        raise ValidationError("duplicate_decision matched_prospect_ids must be an array of non-empty strings.")
    if status == "new_prospect":
        if matched_id is not None or matched_ids:
            raise ValidationError("New prospects cannot include matched historical prospect IDs.")
    elif not isinstance(matched_id, str) or not matched_id:
        raise ValidationError("Existing or related results require matched_prospect_id.")
    expected_reengagement = status == "existing_new_trigger"
    if duplicate.get("reengagement") is not expected_reengagement:
        raise ValidationError("Duplicate reengagement flag must match existing_new_trigger status.")
    if expected_reengagement and campaign.get("reengagement_enabled") is not True:
        raise ValidationError("existing_new_trigger is invalid when campaign re-engagement is disabled.")

    score = require_object(result["score_snapshot"], "score_snapshot")
    dimensions = require_object(score.get("dimensions"), "score dimensions")
    expected = score_umg(dimensions) if result["business_unit"] == "unreal-media-group" else score_talent(dimensions)
    if abs(float(score.get("total", -1)) - expected) > 0.01:
        raise ValidationError(f"Score total {score.get('total')} does not match weighted dimensions {expected}.")
    if not rejection["rejected"] and expected < campaign.get("minimum_qualification_score", 101):
        raise ValidationError("Below-threshold results must be rejected.")
    if not rejection["rejected"] and not fresh_signal:
        raise ValidationError("Qualified results require a current signal within the campaign evidence-age limit.")
    if rejection["rejected"] and not rejection["reasons"]:
        raise ValidationError("Rejected results require at least one rejection reason.")
    if not rejection["rejected"] and rejection["reasons"]:
        raise ValidationError("Non-rejected results cannot include rejection reasons.")
    opportunity_filter = campaign.get("opportunity_filter")
    if opportunity_filter and not rejection["rejected"]:
        if not opportunity_kinds.intersection(opportunity_filter["include_any"]):
            raise ValidationError("Qualified results require at least one included opportunity match.")
        excluded = opportunity_kinds.intersection(opportunity_filter["exclude"])
        if excluded:
            raise ValidationError(f"Qualified results contain an excluded opportunity match: {sorted(excluded)}.")
    if status not in ELIGIBLE_SHORTLIST_STATUSES and not rejection["rejected"]:
        raise ValidationError(f"Duplicate status {status} is not eligible for qualification and must be rejected.")
    if not str(result["reason_for_qualification"]).strip() or not str(result["important_uncertainty"]).strip() or not str(result["recommended_next_action"]).strip():
        raise ValidationError("Qualification reason, uncertainty, and next action must be explicit.")

    handoff = require_object(result["future_handoff"], "future_handoff")
    if not isinstance(handoff.get("ready"), bool):
        raise ValidationError("Future creative handoff ready must be boolean.")
    if handoff.get("human_approval_required_before_generation") is not True:
        raise ValidationError("Future creative handoff must require human approval before generation.")
    if rejection["rejected"] or status not in ELIGIBLE_SHORTLIST_STATUSES:
        if handoff["ready"] is not False:
            raise ValidationError("Rejected, duplicate, suppressed, client, partner, or relationship-only results cannot be handoff-ready.")

    if result["business_unit"] == "unreal-talent":
        if not result.get("rights_territory"):
            raise ValidationError("Unreal Talent results require rights_territory.")
        named = result.get("named_talent")
        if result.get("rights_status") not in {"requires_internal_rights_check", "unknown", "preliminary_review_required"}:
            raise ValidationError("Talent rights_status must preserve an internal rights-review requirement.")
        if not isinstance(result.get("brand_safety_flags"), list):
            raise ValidationError("Talent brand_safety_flags must be an array.")
        if result.get("recommended_buyer_path") not in {"brand_direct", "agency_led", "brand_via_agency", "unknown_requires_review"}:
            raise ValidationError("Talent recommended_buyer_path is invalid or missing.")
        if named:
            if not (
                campaign.get("allow_named_talent_recommendations")
                and result.get("approved_roster_authorization") is True
                and result.get("talent_recommendation_type") == "approved_roster"
            ):
                raise ValidationError("Unauthorized named talent output is prohibited.")
            roster = load_approved_roster(campaign, base_dir)
            matches = [entry for entry in roster["talent"] if entry["display_name"].casefold() == str(named).casefold()]
            if len(matches) != 1 or matches[0]["approval_status"] != "approved" or matches[0]["current_availability_status"] not in {"requires_confirmation", "available_for_review"}:
                raise ValidationError("Named talent is not an approved, reviewable roster match.")
            entry = matches[0]
            if not set(result["rights_territory"]).issubset(set(entry["geographic_rights_availability"])):
                raise ValidationError("Named talent roster entry does not cover the result rights territory.")
            if campaign.get("talent_categories") and entry["talent_category"].casefold() not in {value.casefold() for value in campaign["talent_categories"]}:
                raise ValidationError("Named talent category does not match the campaign talent category.")
            verticals = campaign.get("verticals", [])
            if not verticals:
                raise ValidationError("Named talent requires explicit campaign verticals for category review.")
            if _category_overlaps(verticals, entry["restricted_categories"]):
                raise ValidationError("Named talent has a restricted-category conflict with the campaign.")
            if entry["approved_brand_categories"] and not _category_overlaps(verticals, entry["approved_brand_categories"]):
                raise ValidationError("Named talent is not approved for the campaign brand category.")
            channels = campaign.get("campaign_channels", [])
            if not channels or not {value.casefold() for value in channels}.issubset({value.casefold() for value in entry["channel_rights"]}):
                raise ValidationError("Named talent roster entry does not cover the campaign channels.")
            if entry["exclusivity_conflicts"]:
                raise ValidationError("Named talent has unresolved exclusivity conflicts and cannot be recommended automatically.")
            roster_freshness = parse_date(entry["data_freshness"], "named talent data_freshness")
            if roster_freshness > discovered_date:
                raise ValidationError("Named talent roster freshness cannot be after discovery.")
            if (discovered_date - roster_freshness).days > campaign.get("maximum_evidence_age_days", 0):
                raise ValidationError("Named talent roster data is older than the campaign evidence-age limit.")
        if not named and result.get("talent_recommendation_type") not in {"none", "archetype_only"}:
            raise ValidationError("Without an authorized named talent, recommendation type must be none or archetype_only.")
    return result


def validate_run_report(report: dict[str, Any], *, base_dir: Path | None = None) -> dict[str, Any]:
    required = {"run_metadata", "campaign", "history_loaded", "search_assumptions", "raw_candidates", "results", "summary", "limitations", "validation_errors", "future_creative_handoff_readiness"}
    missing = sorted(required - set(report))
    if missing:
        raise ValidationError(f"Run report is missing fields: {', '.join(missing)}.")
    if report["history_loaded"] is not True:
        raise ValidationError("History was not loaded; run fails closed and cannot claim new prospects.")
    metadata = require_object(report["run_metadata"], "run_metadata")
    metadata_required = {"run_id", "started_at", "completed_at", "skill", "phase"}
    if metadata_required - set(metadata) or metadata.get("phase") != 1:
        raise ValidationError("run_metadata requires run_id, timestamps, skill, and phase 1.")
    started = parse_datetime(metadata["started_at"], "run started_at")
    completed = parse_datetime(metadata["completed_at"], "run completed_at")
    if completed < started:
        raise ValidationError("run completed_at cannot be before started_at.")
    if not all(isinstance(metadata[key], str) and metadata[key].strip() for key in ("run_id", "skill")):
        raise ValidationError("run_metadata run_id and skill must be non-empty strings.")
    campaign = require_object(report["campaign"], "campaign")
    validate_campaign(campaign, require_history_file=False, base_dir=base_dir)
    expected_skill = EXPECTED_SKILLS[campaign["business_unit"]]
    if metadata["skill"] != expected_skill:
        raise ValidationError(f"run_metadata skill must be {expected_skill} for this business unit.")
    for key in ("search_assumptions", "raw_candidates", "results", "limitations", "validation_errors"):
        if not isinstance(report[key], list):
            raise ValidationError(f"Run report field {key} must be an array.")
    for key in ("search_assumptions", "limitations", "validation_errors"):
        if any(not isinstance(value, str) or not value.strip() for value in report[key]):
            raise ValidationError(f"Run report field {key} must contain only non-empty strings.")
    for index, candidate in enumerate(report["raw_candidates"]):
        candidate = require_object(candidate, f"raw candidate {index}")
        if "fixture_cooldown_override" in candidate:
            raise ValidationError("fixture_cooldown_override is test-only and prohibited in run reports.")
        if not isinstance(candidate.get("company_name"), str) or not candidate["company_name"].strip():
            raise ValidationError(f"Raw candidate {index} requires company_name.")
        normalize_domain(candidate.get("domain"))
    for result in report["results"]:
        validate_result(require_object(result, "result"), campaign, base_dir=base_dir)
    _reject_private_contact_data(report)
    summary = require_object(report["summary"], "summary")
    expected_raw = len(report["raw_candidates"])
    if summary.get("raw_candidate_count") != expected_raw:
        raise ValidationError("Summary raw_candidate_count does not match raw_candidates.")
    if len(report["results"]) != expected_raw:
        raise ValidationError("Every raw candidate requires a preserved result decision.")
    new_statuses = {"new_prospect", "distinct_subbrand"}
    calculated = {
        "new_unique_prospects": sum(result["duplicate_decision"]["status"] in new_statuses for result in report["results"]),
        "duplicates": sum(result["duplicate_decision"]["status"] not in new_statuses for result in report["results"]),
        "reengagement_prospects": sum(result["duplicate_decision"]["status"] == "existing_new_trigger" for result in report["results"]),
        "rejections": sum(result["rejection_decision"]["rejected"] for result in report["results"]),
        "qualified_shortlist": sum(
            not result["rejection_decision"]["rejected"]
            and result["duplicate_decision"]["status"] in ELIGIBLE_SHORTLIST_STATUSES
            for result in report["results"]
        ),
    }
    for key, expected in calculated.items():
        if summary.get(key) != expected:
            raise ValidationError(f"Summary {key} must be {expected} from preserved result decisions.")
    if not isinstance(report["future_creative_handoff_readiness"], str) or not report["future_creative_handoff_readiness"].strip():
        raise ValidationError("future_creative_handoff_readiness must be a non-empty string.")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        validate_run_report(require_object(load_json(args.report, "run report"), "run report"), base_dir=args.report.parent)
    except ValidationError as exc:
        raise SystemExit(f"Validation error: {exc}") from exc
    print(f"Valid run report: {args.report}")


if __name__ == "__main__":
    main()

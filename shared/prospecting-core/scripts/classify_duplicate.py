#!/usr/bin/env python3
"""Classify a candidate against durable local prospect history."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from common import ValidationError, load_json, parse_date, parse_datetime, require_http_url, require_object
from normalize_company_name import normalize_company_name, normalize_social_handle
from normalize_domain import normalize_domain


def validate_history(history: dict[str, Any]) -> dict[str, Any]:
    if history.get("version") != 1 or not isinstance(history.get("prospects"), list):
        raise ValidationError("Prospect history must have version 1 and a prospects array.")
    parse_datetime(history.get("generated_at"), "history generated_at")
    required = {
        "id", "canonical_company_name", "canonical_domain", "domains", "alternate_names",
        "social_handles", "previous_discovery_dates", "previous_campaign_appearances",
        "previous_scores", "previous_decisions", "outreach_status", "client_status",
        "partner_status", "suppressed", "prior_signals", "prior_rejection_reasons",
    }
    seen_ids: set[str] = set()
    domain_owners: dict[str, str] = {}
    handle_owners: dict[tuple[str, str], str] = {}
    for index, record in enumerate(history["prospects"]):
        if not isinstance(record, dict):
            raise ValidationError(f"History prospect {index} must be an object.")
        missing = sorted(required - set(record))
        if missing:
            raise ValidationError(f"History prospect {index} is missing: {', '.join(missing)}.")
        prospect_id = record["id"]
        if not isinstance(prospect_id, str) or not prospect_id.strip() or prospect_id in seen_ids:
            raise ValidationError(f"History prospect {index} id must be a unique non-empty string.")
        seen_ids.add(prospect_id)
        normalize_company_name(record["canonical_company_name"])
        for key in (
            "domains", "alternate_names", "previous_discovery_dates", "previous_campaign_appearances",
            "previous_scores", "previous_decisions", "prior_signals", "prior_rejection_reasons",
        ):
            if not isinstance(record[key], list):
                raise ValidationError(f"History prospect {index} field {key} must be an array.")
        if not isinstance(record["suppressed"], bool):
            raise ValidationError(f"History prospect {index} field suppressed must be boolean.")
        for key in ("outreach_status", "client_status", "partner_status"):
            if not isinstance(record[key], str):
                raise ValidationError(f"History prospect {index} field {key} must be a string.")
        if not isinstance(record["social_handles"], dict):
            raise ValidationError(f"History prospect {index} social_handles must be an object.")

        for domain_value in [record["canonical_domain"], *record["domains"]]:
            domain = normalize_domain(domain_value)
            owner = domain_owners.get(domain)
            if owner and owner != prospect_id:
                raise ValidationError(
                    f"History domain {domain} is assigned to multiple prospects ({owner}, {prospect_id}); identity is ambiguous."
                )
            domain_owners[domain] = prospect_id

        for platform, value in record["social_handles"].items():
            if not isinstance(platform, str) or not platform.strip():
                raise ValidationError(f"History prospect {index} social platform must be a non-empty string.")
            key = (platform.strip().casefold(), normalize_social_handle(value))
            owner = handle_owners.get(key)
            if owner and owner != prospect_id:
                raise ValidationError(
                    f"History social identity {key[0]}:{key[1]} is assigned to multiple prospects ({owner}, {prospect_id})."
                )
            handle_owners[key] = prospect_id

        for discovered_at in record["previous_discovery_dates"]:
            parse_date(discovered_at, f"history prospect {index} discovery date")
        if record.get("cooldown_until"):
            parse_date(record["cooldown_until"], f"history prospect {index} cooldown_until")
        for signal in record["prior_signals"]:
            signal = require_object(signal, f"history prospect {index} prior signal")
            require_http_url(signal.get("source_url"), f"history prospect {index} prior signal URL")
            parse_date(signal.get("source_date"), f"history prospect {index} prior signal date")
    return history


def _candidate_identity(candidate: dict[str, Any]) -> tuple[str, str, set[tuple[str, str]]]:
    name = normalize_company_name(candidate.get("company_name", ""))
    domain = normalize_domain(candidate.get("domain") or candidate.get("canonical_domain") or "")
    handles: set[tuple[str, str]] = set()
    for platform, value in (candidate.get("social_handles") or {}).items():
        handles.add((str(platform).strip().casefold(), normalize_social_handle(value)))
    return name, domain, handles


def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        by_id[record["id"]] = record
    return list(by_id.values())


def _match_records(candidate: dict[str, Any], history: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    name, domain, handles = _candidate_identity(candidate)
    records = history["prospects"]

    exact_domain = [
        record for record in records
        if domain in {normalize_domain(value) for value in [record["canonical_domain"], *record.get("domains", [])]}
    ]
    if exact_domain:
        return _dedupe_records(exact_domain), "exact_domain"

    aliases = [
        record for record in records
        if name in {normalize_company_name(value) for value in [record["canonical_company_name"], *record.get("alternate_names", [])]}
    ]
    if aliases:
        return _dedupe_records(aliases), "alias"

    social = []
    if handles:
        for record in records:
            record_handles = {
                (str(platform).strip().casefold(), normalize_social_handle(value))
                for platform, value in record.get("social_handles", {}).items()
            }
            if handles & record_handles:
                social.append(record)
    if social:
        return _dedupe_records(social), "social_handle"

    parent_company = candidate.get("parent_company")
    if parent_company:
        normalized_parent = normalize_company_name(parent_company)
        parents = [record for record in records if normalized_parent == normalize_company_name(record["canonical_company_name"])]
        if parents:
            return _dedupe_records(parents), "parent_company"

    subbrands = []
    for record in records:
        related_names = record.get("subsidiaries", []) + record.get("subbrands", [])
        if name in {normalize_company_name(value) for value in related_names}:
            subbrands.append(record)
    if subbrands:
        return _dedupe_records(subbrands), "known_subbrand"

    if candidate.get("company_type") == "agency":
        agencies = []
        for record in records:
            record_agencies = {normalize_company_name(value) for value in record.get("agency_relationships", [])}
            if name in record_agencies:
                agencies.append(record)
        if agencies:
            return _dedupe_records(agencies), "agency_relationship"

    possible = []
    candidate_tokens = set(name.split())
    for record in records:
        record_names = {normalize_company_name(value) for value in [record["canonical_company_name"], *record.get("alternate_names", [])]}
        for existing in record_names:
            existing_tokens = set(existing.split())
            union = candidate_tokens | existing_tokens
            similarity = len(candidate_tokens & existing_tokens) / len(union) if union else 0
            if similarity >= 0.75:
                possible.append(record)
                break
    return (_dedupe_records(possible), "possible_name") if possible else ([], None)


def _decision(status: str, reason: str, records: list[dict[str, Any]], *, reengagement: bool = False) -> dict[str, Any]:
    ids = [record["id"] for record in records]
    return {
        "status": status,
        "reason": reason,
        "matched_prospect_id": ids[0] if ids else None,
        "matched_prospect_ids": ids,
        "reengagement": reengagement,
    }


def classify_duplicate(
    candidate: dict[str, Any],
    history: dict[str, Any],
    campaign: dict[str, Any],
    *,
    today: date | None = None,
    allow_fixture_cooldown_override: bool = False,
) -> dict[str, Any]:
    validate_history(history)
    records, match_type = _match_records(candidate, history)
    if not records:
        return _decision("new_prospect", "No canonical identity or relationship matched history.", [])
    if len(records) > 1:
        return _decision(
            "possible_duplicate_needs_review",
            f"Candidate matched multiple historical records through {match_type}; identity requires human resolution.",
            records,
        )

    record = records[0]
    if match_type == "possible_name":
        return _decision(
            "possible_duplicate_needs_review",
            "Company names partially overlap but identity is not conclusive.",
            records,
        )

    # Account protections take priority over relationship/subbrand treatment.
    if record.get("suppressed"):
        return _decision("suppressed", record.get("suppression_reason") or "Existing record is suppressed.", records)
    if record.get("client_status") == "active":
        return _decision("existing_client", "Matched account is an active client.", records)
    if record.get("partner_status") == "active":
        return _decision("existing_partner", "Matched account is an active partner.", records)
    if record.get("outreach_status") in {"active", "contacted", "meeting", "proposal"}:
        return _decision("existing_active_outreach", "Matched account has active outreach or sales activity.", records)

    if match_type == "parent_company":
        return _decision("parent_company_relationship", "Candidate identifies an existing company as its parent.", records)
    if match_type == "known_subbrand" and candidate.get("independent_subbrand") is True:
        return _decision("distinct_subbrand", "Known subbrand has an independent identity and campaign opportunity.", records)
    if match_type == "agency_relationship":
        return _decision("agency_brand_overlap", "Candidate agency overlaps an existing brand opportunity.", records)

    new_trigger = candidate.get("new_trigger")
    if not campaign.get("reengagement_enabled") or not isinstance(new_trigger, dict):
        return _decision("existing_no_new_trigger", "Existing identity has no eligible new trigger.", records)
    trigger_url = new_trigger.get("source_url")
    trigger_date = new_trigger.get("source_date")
    if not trigger_url or not trigger_date or not new_trigger.get("reason"):
        return _decision("existing_no_new_trigger", "Re-engagement trigger lacks a dated source and recorded reason.", records)
    try:
        trigger_url = require_http_url(trigger_url, "new trigger source_url")
    except ValidationError:
        return _decision("existing_no_new_trigger", "Re-engagement trigger URL is invalid.", records)
    current_date = today or date.today()
    evidence_date = parse_date(trigger_date, "new trigger source_date")
    if evidence_date > current_date:
        return _decision("existing_no_new_trigger", "New trigger is future-dated.", records)
    if (current_date - evidence_date).days > campaign.get("maximum_evidence_age_days", 3650):
        return _decision("existing_no_new_trigger", "New trigger is older than the campaign evidence limit.", records)

    override = allow_fixture_cooldown_override and candidate.get("fixture_cooldown_override") is True
    cooldown_until = record.get("cooldown_until")
    if cooldown_until and parse_date(cooldown_until, "cooldown_until") > current_date and not override:
        return _decision("existing_no_new_trigger", "Cooldown has not expired.", records)
    prior_discovery_dates = record.get("previous_discovery_dates", [])
    if prior_discovery_dates and not override:
        latest_discovery = max(parse_date(value, "previous_discovery_date") for value in prior_discovery_dates)
        if (current_date - latest_discovery).days < campaign.get("cooldown_days", 0):
            return _decision("existing_no_new_trigger", "Campaign cooldown has not expired since the prior discovery.", records)
    prior_urls = {signal.get("source_url") for signal in record.get("prior_signals", []) if isinstance(signal, dict)}
    if trigger_url in prior_urls:
        return _decision("existing_no_new_trigger", "Trigger source was already recorded.", records)
    return _decision("existing_new_trigger", str(new_trigger["reason"]), records, reengagement=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("history", type=Path)
    parser.add_argument("campaign", type=Path)
    args = parser.parse_args()
    try:
        candidate = require_object(load_json(args.candidate, "candidate"), "candidate")
        history = require_object(load_json(args.history, "history"), "history")
        campaign = require_object(load_json(args.campaign, "campaign"), "campaign")
        decision = classify_duplicate(candidate, history, campaign)
    except ValidationError as exc:
        raise SystemExit(f"Validation error: {exc}") from exc
    print(json.dumps(decision, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

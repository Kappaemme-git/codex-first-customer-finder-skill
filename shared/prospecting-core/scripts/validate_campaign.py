#!/usr/bin/env python3
"""Validate a local Unreal prospecting campaign configuration."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import ValidationError, load_json, parse_date, parse_datetime, require_object

BUSINESS_UNITS = {"unreal-media-group", "unreal-talent"}
OUTPUT_FORMATS = {"json", "markdown", "html"}
OPPORTUNITY_KINDS = {"product_photography", "product_video", "ugc_ad"}
ALLOWED_FIELDS = {
    "business_unit", "campaign_name", "discovery_scope", "verticals", "geography", "buyer_types",
    "talent_categories", "rights_territory", "campaign_channels", "target_prospect_count", "deep_research_limit",
    "minimum_qualification_score", "required_signals", "preferred_signals", "excluded_categories",
    "include_companies", "exclude_companies", "reengagement_enabled", "cooldown_days",
    "maximum_evidence_age_days", "output_formats", "prospect_history_path", "approved_roster_path",
    "allow_named_talent_recommendations",
    "opportunity_filter",
}


def load_approved_roster(config: dict[str, Any], base_dir: Path | None = None) -> dict[str, Any]:
    roster_value = config.get("approved_roster_path")
    if not isinstance(roster_value, str) or not roster_value.strip():
        raise ValidationError("Named talent requires an approved_roster_path.")
    roster_path = Path(roster_value)
    if not roster_path.is_absolute() and base_dir:
        roster_path = base_dir / roster_path
    roster = require_object(load_json(roster_path, "approved roster"), "approved roster")
    if roster.get("version") != 1 or roster.get("authorized_for_named_recommendations") is not True:
        raise ValidationError("Approved roster must be version 1 and explicitly authorize named recommendations.")
    parse_datetime(roster.get("generated_at"), "approved roster generated_at")
    talent = roster.get("talent")
    if not isinstance(talent, list):
        raise ValidationError("Approved roster talent must be an array.")
    required = {
        "talent_id", "display_name", "talent_category", "approved_brand_categories",
        "restricted_categories", "geographic_rights_availability", "channel_rights",
        "duration_constraints", "exclusivity_conflicts", "approval_status",
        "current_availability_status", "minimum_commercial_requirements", "notes", "data_freshness",
    }
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for index, entry in enumerate(talent):
        entry = require_object(entry, f"approved roster talent {index}")
        missing = sorted(required - set(entry))
        if missing:
            raise ValidationError(f"Approved roster talent {index} is missing: {', '.join(missing)}.")
        talent_id = entry["talent_id"]
        display_name = entry["display_name"]
        if not isinstance(talent_id, str) or not talent_id.strip() or talent_id in seen_ids:
            raise ValidationError(f"Approved roster talent {index} talent_id must be unique and non-empty.")
        if not isinstance(display_name, str) or not display_name.strip() or display_name.casefold() in seen_names:
            raise ValidationError(f"Approved roster talent {index} display_name must be unique and non-empty.")
        seen_ids.add(talent_id)
        seen_names.add(display_name.casefold())
        if not isinstance(entry["talent_category"], str) or not entry["talent_category"].strip():
            raise ValidationError(f"Approved roster talent {index} talent_category must be non-empty.")
        for key in (
            "approved_brand_categories", "restricted_categories", "geographic_rights_availability",
            "channel_rights", "exclusivity_conflicts",
        ):
            if not isinstance(entry[key], list) or any(not isinstance(item, str) or not item.strip() for item in entry[key]):
                raise ValidationError(f"Approved roster talent {index} field {key} must be an array of non-empty strings.")
        for key in ("duration_constraints", "minimum_commercial_requirements", "notes"):
            if not isinstance(entry[key], str):
                raise ValidationError(f"Approved roster talent {index} field {key} must be a string.")
        parse_date(entry["data_freshness"], f"approved roster talent {index} data_freshness")
    return roster


def _string_list(config: dict[str, Any], key: str) -> list[str]:
    value = config.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValidationError(f"{key} must be an array of non-empty strings.")
    return value


def _validate_opportunity_filter(config: dict[str, Any]) -> None:
    value = config.get("opportunity_filter")
    if value is None:
        return
    if config.get("business_unit") != "unreal-media-group":
        raise ValidationError("opportunity_filter is available only for Unreal Media Group campaigns.")
    opportunity_filter = require_object(value, "opportunity_filter")
    required = {"include_any", "exclude"}
    missing = sorted(required - set(opportunity_filter))
    unknown = sorted(set(opportunity_filter) - required)
    if missing:
        raise ValidationError(f"opportunity_filter is missing: {', '.join(missing)}.")
    if unknown:
        raise ValidationError(f"opportunity_filter contains unsupported fields: {', '.join(unknown)}.")
    for key in ("include_any", "exclude"):
        values = opportunity_filter[key]
        if not isinstance(values, list) or any(not isinstance(item, str) or not item.strip() for item in values):
            raise ValidationError(f"opportunity_filter {key} must be an array of non-empty strings.")
        if len(values) != len(set(values)):
            raise ValidationError(f"opportunity_filter {key} values must be unique.")
        if any(item not in OPPORTUNITY_KINDS for item in values):
            raise ValidationError("opportunity_filter uses a value outside the controlled vocabulary.")
    if not opportunity_filter["include_any"]:
        raise ValidationError("opportunity_filter include_any must contain at least one value.")
    overlap = set(opportunity_filter["include_any"]) & set(opportunity_filter["exclude"])
    if overlap:
        raise ValidationError(f"opportunity_filter cannot include and exclude the same value: {sorted(overlap)}.")


def validate_campaign(config: dict[str, Any], *, require_history_file: bool = True, base_dir: Path | None = None) -> dict[str, Any]:
    required = {
        "business_unit", "campaign_name", "discovery_scope", "target_prospect_count",
        "deep_research_limit", "minimum_qualification_score", "reengagement_enabled",
        "cooldown_days", "maximum_evidence_age_days", "output_formats", "prospect_history_path",
    }
    missing = sorted(required - set(config))
    if missing:
        raise ValidationError(f"Campaign is missing required fields: {', '.join(missing)}.")
    unknown = sorted(set(config) - ALLOWED_FIELDS)
    if unknown:
        raise ValidationError(f"Campaign contains unsupported fields: {', '.join(unknown)}.")
    if config["business_unit"] not in BUSINESS_UNITS:
        raise ValidationError("business_unit must be unreal-media-group or unreal-talent.")
    if not isinstance(config["campaign_name"], str) or not config["campaign_name"].strip():
        raise ValidationError("campaign_name must be a non-empty string.")
    if config["discovery_scope"] not in {"open", "filtered"}:
        raise ValidationError("discovery_scope must be open or filtered.")
    if "geography" in config:
        geography = require_object(config["geography"], "geography")
        unknown_geography = sorted(set(geography) - {"countries", "regions", "cities", "languages"})
        if unknown_geography:
            raise ValidationError(f"geography contains unsupported fields: {', '.join(unknown_geography)}.")
        for key, values in geography.items():
            if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValidationError(f"geography {key} must be an array of non-empty strings.")
    verticals = _string_list(config, "verticals")
    if config["discovery_scope"] == "filtered" and not verticals:
        raise ValidationError("filtered discovery requires at least one vertical.")
    for key in (
        "required_signals", "preferred_signals", "excluded_categories", "include_companies",
        "exclude_companies", "talent_categories", "campaign_channels",
    ):
        _string_list(config, key)
    buyer_types = _string_list(config, "buyer_types")
    if any(value not in {"brand", "agency"} for value in buyer_types):
        raise ValidationError("buyer_types may contain only brand or agency.")
    if config["business_unit"] == "unreal-talent":
        if not buyer_types:
            raise ValidationError("Unreal Talent campaigns require buyer_types.")
        if not _string_list(config, "rights_territory"):
            raise ValidationError("Unreal Talent campaigns require likely rights_territory.")
    _validate_opportunity_filter(config)
    for key, minimum, maximum in (
        ("target_prospect_count", 1, 100), ("deep_research_limit", 0, 100),
        ("cooldown_days", 0, 3650), ("maximum_evidence_age_days", 1, 3650),
    ):
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValidationError(f"{key} must be an integer from {minimum} to {maximum}.")
    if config["deep_research_limit"] > config["target_prospect_count"]:
        raise ValidationError("deep_research_limit cannot exceed target_prospect_count.")
    minimum_score = config["minimum_qualification_score"]
    if isinstance(minimum_score, bool) or not isinstance(minimum_score, (int, float)) or not 0 <= minimum_score <= 100:
        raise ValidationError("minimum_qualification_score must be from 0 to 100.")
    if not isinstance(config["reengagement_enabled"], bool):
        raise ValidationError("reengagement_enabled must be boolean.")
    formats = _string_list(config, "output_formats")
    if not formats or len(formats) != len(set(formats)) or any(value not in OUTPUT_FORMATS for value in formats):
        raise ValidationError("output_formats must contain unique json, markdown, or html values.")
    overlap = {item.lower() for item in _string_list(config, "include_companies")} & {item.lower() for item in _string_list(config, "exclude_companies")}
    if overlap:
        raise ValidationError(f"Companies cannot be both included and excluded: {sorted(overlap)}.")
    history_value = config["prospect_history_path"]
    if not isinstance(history_value, str) or not history_value.strip():
        raise ValidationError("prospect_history_path must be a non-empty string.")
    if require_history_file:
        history_path = Path(history_value)
        if not history_path.is_absolute() and base_dir:
            history_path = base_dir / history_path
        if not history_path.is_file():
            raise ValidationError(f"Prospect history cannot be loaded: {history_path}.")

    allow_named = config.get("allow_named_talent_recommendations", False)
    if not isinstance(allow_named, bool):
        raise ValidationError("allow_named_talent_recommendations must be boolean.")
    roster_path = config.get("approved_roster_path")
    if roster_path is not None and not isinstance(roster_path, str):
        raise ValidationError("approved_roster_path must be a string or null.")
    if allow_named:
        if config["business_unit"] != "unreal-talent":
            raise ValidationError("Named talent is available only for Unreal Talent campaigns.")
        if not verticals:
            raise ValidationError("Named-talent review requires at least one explicit campaign vertical.")
        if not _string_list(config, "talent_categories"):
            raise ValidationError("Named-talent review requires an explicit talent category.")
        if not _string_list(config, "campaign_channels"):
            raise ValidationError("Named-talent review requires explicit campaign_channels.")
        load_approved_roster(config, base_dir)
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--skip-history-file-check", action="store_true")
    args = parser.parse_args()
    try:
        data = require_object(load_json(args.campaign, "campaign"), "campaign")
        validate_campaign(data, require_history_file=not args.skip_history_file_check, base_dir=args.campaign.parent)
    except ValidationError as exc:
        raise SystemExit(f"Validation error: {exc}") from exc
    print(f"Valid campaign: {args.campaign}")


if __name__ == "__main__":
    main()

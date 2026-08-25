#!/usr/bin/env python3
"""Shared standard-library helpers for local Phase 1 prospecting."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

UMG_WEIGHTS = {
    "creative_need": 20,
    "visual_fit": 20,
    "budget_likelihood": 15,
    "marketing_activity": 15,
    "timing": 15,
    "reachability": 10,
    "evidence_quality": 5,
}

TALENT_WEIGHTS = {
    "campaign_talent_fit": 20,
    "budget_likelihood": 20,
    "current_trigger": 20,
    "rights_readiness": 15,
    "brand_roster_compatibility": 10,
    "decision_path": 10,
    "evidence_quality": 5,
}


class ValidationError(ValueError):
    """Raised when local prospecting input violates a Phase 1 contract."""


def load_json(path: str | Path, label: str = "JSON") -> Any:
    target = Path(path)
    if not target.is_file():
        raise ValidationError(f"{label} file does not exist: {target}")
    try:
        with target.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Cannot load {label} from {target}: {exc}") from exc


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be a JSON object.")
    return value


def require_http_url(value: Any, label: str = "source URL") -> str:
    raw = str(value or "").strip()
    if any(character.isspace() or ord(character) < 32 for character in raw) or any(character in raw for character in '<>"\'\\'):
        raise ValidationError(f"{label} contains unsafe characters.")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValidationError(f"{label} must be a credential-free HTTP(S) URL.")
    return raw


def parse_date(value: Any, label: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationError(f"{label} must be an ISO date (YYYY-MM-DD).") from exc


def parse_datetime(value: Any, label: str) -> datetime:
    raw = str(value)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{label} must be an ISO date-time.") from exc


def weighted_score(dimensions: dict[str, Any], weights: dict[str, int]) -> float:
    missing = sorted(set(weights) - set(dimensions))
    extra = sorted(set(dimensions) - set(weights))
    if missing or extra:
        raise ValidationError(f"Score dimensions mismatch; missing={missing}, extra={extra}.")
    total = 0.0
    for name, weight in weights.items():
        value = dimensions[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 5:
            raise ValidationError(f"Score dimension {name} must be a number from 0 to 5.")
        total += float(value) / 5 * weight
    return round(total, 2)


def score_umg(dimensions: dict[str, Any]) -> float:
    return weighted_score(dimensions, UMG_WEIGHTS)


def score_talent(dimensions: dict[str, Any]) -> float:
    return weighted_score(dimensions, TALENT_WEIGHTS)

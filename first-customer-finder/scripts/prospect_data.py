"""Validation and local state. Standard library only; never performs network I/O."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


WEIGHTS = {"pain_strength": 25, "product_fit": 25, "timing": 20,
           "reachability": 15, "evidence_quality": 15}
STATUSES = ("new", "contacted", "replied", "not_interested", "customer")
FEEDBACK = ("keep", "maybe", "reject")


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def public_url(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected an absolute public HTTP(S) URL")
    raw = value.strip()
    if any(c.isspace() or ord(c) < 32 for c in raw) or "\\" in raw:
        raise ValueError("URL contains whitespace, control characters, or backslashes")
    try:
        parsed = urlsplit(raw)
        _ = parsed.port
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Expected an absolute public HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Credential-bearing URLs are not allowed")
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid public URL: {exc}") from exc
    return raw


def canonical_url(value):
    parsed = urlsplit(public_url(value))
    host = parsed.hostname.lower()
    if host.startswith("www."):
        host = host[4:]
    if host in {"twitter.com", "mobile.twitter.com", "mobile.x.com"}:
        host = "x.com"
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    port = parsed.port
    if port and not ((parsed.scheme == "https" and port == 443) or
                     (parsed.scheme == "http" and port == 80)):
        host += f":{port}"
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    # Hostnames are insensitive; arbitrary paths/query values need not be.
    return urlunsplit(("https", host, parsed.path.rstrip("/"), urlencode(sorted(query)), ""))


def prospect_id(entity_url):
    return "p_" + hashlib.sha256(canonical_url(entity_url).encode()).hexdigest()[:14]


def text_field(obj, key):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be nonempty text")
    return value.strip()


def iso_date(value, field, ceiling=None):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must be YYYY-MM-DD")
    if ceiling and parsed > ceiling:
        raise ValueError(f"{field} cannot be later than {ceiling}")
    return parsed


def normalize_report(raw):
    if not isinstance(raw, dict):
        raise ValueError("Input JSON must contain an object")
    data = copy.deepcopy(raw)
    if type(data.get("schema_version", 1)) is not int or data.get("schema_version", 1) not in {1, 2}:
        raise ValueError("Unsupported report schema_version")
    if not isinstance(data.get("prospects", []), list):
        raise ValueError("prospects must be an array")
    if not all(isinstance(p, dict) for p in data.get("prospects", [])):
        raise ValueError("Each prospect must be an object")
    if data.get("schema_version", 1) == 1:
        data["legacy_warning"] = "Legacy input: contact routes and source verification were not validated."
        return data
    for field in ("patterns", "limits"):
        if not isinstance(data.get(field, []), list):
            raise ValueError(f"{field} must be an array")
    if not all(isinstance(item, str) for item in data.get("limits", [])):
        raise ValueError("limits entries must be text")
    for pattern in data.get("patterns", []):
        if not isinstance(pattern, dict):
            raise ValueError("Each pattern must be an object")
        for field in ("title", "insight"):
            text_field(pattern, field)
        count = pattern.get("count")
        if type(count) is not int or not 1 <= count <= len(data.get("prospects", [])):
            raise ValueError("Pattern count must refer to included prospects")
    if not isinstance(data.get("outreach_plan", {}), dict):
        raise ValueError("outreach_plan must be an object")
    if not all(isinstance(v, str) for v in data.get("outreach_plan", {}).values()):
        raise ValueError("outreach_plan values must be text")
    for field in ("project_key", "product", "target_customer", "search_scope", "verdict"):
        text_field(data, field)
    if not isinstance(data.get("demo", False), bool):
        raise ValueError("demo must be a boolean")
    generated = iso_date(data.get("generated_at"), "generated_at", date.today())
    known = set()
    for index, p in enumerate(data.get("prospects", []), 1):
        try:
            for field in ("name", "pain_signal", "evidence", "why_fit", "why_now",
                          "source_title", "source_type", "target_role", "next_step",
                          "cta", "opener", "caution", "suggested_channel"):
                text_field(p, field)
            for field in ("entity_url", "source_url"):
                p[field] = public_url(p.get(field))
            identity = prospect_id(p["entity_url"])
            if identity in known:
                raise ValueError("Duplicate entity; consolidate its signals into one prospect")
            known.add(identity)
            p["id"] = identity
            if p.get("evidence_status") != "verified":
                raise ValueError("Only inspected original sources belong in the primary shortlist")
            if p.get("stage") not in {"High intent", "Problem aware", "Trigger present"}:
                raise ValueError("stage must be High intent, Problem aware, or Trigger present")
            if p.get("role_basis") not in {"observed", "inferred"}:
                raise ValueError("role_basis must be observed or inferred")
            checked = iso_date(p.get("checked_at"), "checked_at", generated)
            if p.get("signal_date") is not None:
                iso_date(p["signal_date"], "signal_date", checked)
            dimensions = p.get("dimensions", {})
            if not isinstance(dimensions, dict):
                raise ValueError("dimensions must be an object")
            for key in WEIGHTS:
                value = dimensions.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 5:
                    raise ValueError(f"{key} must be a finite number from 0 to 5")
            if p.get("signal_date") is None and dimensions["timing"] > 2:
                raise ValueError("Undated evidence requires timing <= 2")
            route = p.get("contact_route")
            if not isinstance(route, dict) or route.get("status") not in {"verified", "not_found"}:
                raise ValueError("contact_route.status must be verified or not_found")
            text_field(route, "note")
            if route["status"] == "verified":
                for key in ("url", "source_url"):
                    route[key] = public_url(route.get(key))
                text_field(route, "label")
                iso_date(route.get("checked_at"), "contact_route.checked_at", generated)
            else:
                if route.get("url") or route.get("source_url"):
                    raise ValueError("not_found route cannot contain a guessed URL")
                if dimensions["reachability"] > 1:
                    raise ValueError("No verified route requires reachability <= 1")
            if p["cta"].strip() not in p["opener"]:
                raise ValueError("opener must include its concrete CTA verbatim")
            p["score"] = round(sum(dimensions[k] / 5 * w for k, w in WEIGHTS.items()))
            if p["score"] < 50:
                raise ValueError("Score below 50: move this candidate outside the primary shortlist")
            if not isinstance(p.get("additional_sources", []), list):
                raise ValueError("additional_sources must be an array")
            for source in p.get("additional_sources", []):
                if not isinstance(source, dict):
                    raise ValueError("Each additional source must be an object")
                public_url(source["url"])
                text_field(source, "note")
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"Prospect {index}: {exc}") from exc
    data["prospects"] = sorted(data.get("prospects", []), key=lambda p: (-p["score"], p["name"]))
    return data


def read_state(path):
    if path.is_symlink():
        raise ValueError("State must be a regular local file, not a symlink")
    with path.open(encoding="utf-8") as handle:
        state = json.load(handle)
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise ValueError("Unsupported or malformed history")
    text_field(state, "project_key")
    if not isinstance(state.get("demo", False), bool):
        raise ValueError("Malformed history demo flag")
    if not isinstance(state.get("prospects"), dict):
        raise ValueError("Malformed prospect history")
    profile = state.get("profile")
    if not isinstance(profile, dict) or any(not isinstance(profile.get(k), list) or
        not all(isinstance(x, str) for x in profile[k]) for k in ("prefer", "avoid")):
        raise ValueError("Malformed search profile")
    for key, record in state["prospects"].items():
        if not isinstance(record, dict) or record.get("id") != key or record.get("status") not in STATUSES:
            raise ValueError("Malformed history record")
        if record.get("feedback") not in (None, *FEEDBACK):
            raise ValueError("Malformed history feedback")
        if not isinstance(record.get("latest"), dict) or prospect_id(record["latest"].get("entity_url")) != key:
            raise ValueError("History identity mismatch")
    return state


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("Refusing to replace a symlink")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def state_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError(f"History is locked by another run: {lock}. No state changed.") from exc
    try:
        os.close(fd)
        yield
    finally:
        lock.unlink()


def prepare_history(data, state, new_only=False):
    """Return filtered report and next state, without writing either one."""
    if data.get("schema_version") != 2:
        raise ValueError("Saved history requires report schema_version 2")
    if state is None:
        state = {"schema_version": 1, "project_key": data["project_key"],
                 "demo": data.get("demo", False), "profile": {"prefer": [], "avoid": []}, "prospects": {}}
    if state["project_key"] != data["project_key"]:
        raise ValueError("Product mismatch: use a separate state file for this project_key")
    if state.get("demo", False) != data.get("demo", False):
        raise ValueError("Demo and real research cannot share history")
    state, result = copy.deepcopy(state), copy.deepcopy(data)
    result["prospects"] = []
    excluded = {"seen": 0, "rejected": 0, "contacted": 0}
    now = timestamp()
    for p in data.get("prospects", []):
        record = state["prospects"].get(p["id"])
        reason = None
        if record and record.get("feedback") == "reject":
            reason = "rejected"
        elif record and record["status"] != "new":
            reason = "contacted"
        elif record and new_only:
            reason = "seen"
        if reason:
            excluded[reason] += 1
            continue
        p = copy.deepcopy(p)
        p["history_label"] = "Previously seen" if record else "New discovery"
        p["status"] = record["status"] if record else "new"
        p["feedback"] = record.get("feedback") if record else None
        next_record = copy.deepcopy(record) if record else {
            "id": p["id"], "first_seen": now, "status": "new", "feedback": None}
        next_record.update({"last_seen": now, "latest": p})
        state["prospects"][p["id"]] = next_record
        result["prospects"].append(p)
    result["history_summary"] = {"excluded": excluded, "new_only": new_only,
                                  "profile": copy.deepcopy(state["profile"])}
    if any(excluded.values()):
        # Input-level conclusions may refer to removed entities. Avoid presenting them as current.
        result["verdict"] = f"{len(result['prospects'])} eligible prospects remain after history filtering. Review the included evidence before outreach."
        result["patterns"] = []
        result["outreach_plan"] = {
            "angle": "Validate only the included prospects.",
            "first_step": "Review their evidence and suitable contact routes; send nothing automatically.",
            "follow_up": "Choose a next step after a real response.",
            "success": "Observe whether the stated problem is still relevant; no response is guaranteed."}
        result.setdefault("limits", []).append("History filtering removed candidates; prior pattern counts and the original outreach plan were omitted to avoid stale conclusions.")
    state["updated_at"] = now
    return result, state

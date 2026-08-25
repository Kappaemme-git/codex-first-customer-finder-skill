"""Deterministic domain model and fixture repository for Phase 3."""

from __future__ import annotations

import copy
import functools
import hashlib
import json
import sys
import threading
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CORE_SCRIPTS = REPOSITORY_ROOT / "shared" / "prospecting-core" / "scripts"
if str(CORE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(CORE_SCRIPTS))

from common import ValidationError  # noqa: E402
from validate_campaign import validate_campaign  # noqa: E402
from classify_duplicate import classify_duplicate, validate_history  # noqa: E402

BUSINESS_UNITS = {"unreal-media-group", "unreal-talent"}
ACTOR_SCOPE = {
    "noah": BUSINESS_UNITS,
    "rob": {"unreal-media-group"},
    "dan": {"unreal-talent"},
}
MAX_TEXT = 500
MAX_NOTE = 2_000
MAX_LIST = 20

# One governed state domain per contract decision kind. Approval and rejection are mutually
# exclusive values of a single decision stream, so a later decision of either kind supersedes the
# current leaf instead of opening a parallel history. Notes are commentary and own no state domain.
STATE_DOMAINS = {
    "approve_deeper_research": "decision",
    "reject": "decision",
    "resolve_identity": "resolve_identity",
    "suppress": "suppress",
    "assign": "assign",
}


def state_domain(kind: str) -> str | None:
    """Return the governed state domain an action belongs to, or None for ungoverned commentary."""
    return STATE_DOMAINS.get(kind)


class MissionControlError(Exception):
    """A safe application error with an HTTP-compatible status."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class Repository(Protocol):
    """Replaceable persistence boundary for the future governed adapter."""

    def campaigns(self, actor: str) -> list[dict[str, Any]]: ...

    def get_campaign(self, actor: str, family_id: str, version: int) -> dict[str, Any]: ...

    def add_campaign(self, actor: str, config: dict[str, Any], family_id: str | None = None) -> dict[str, Any]: ...

    def ensure_campaign_version(self, actor: str, family_id: str, version: int, configuration: dict[str, Any], configuration_hash: str, created_at: str) -> dict[str, Any]: ...

    def runs(self, actor: str) -> list[dict[str, Any]]: ...

    def get_run(self, actor: str, run_id: str) -> dict[str, Any]: ...

    def prepare_run(
        self, actor: str, family_id: str, version: int, idempotency_key: str,
        *, history: dict[str, Any] | None = None, prospect_cap: int | None = None,
    ) -> dict[str, Any]: ...

    def validate_prepared_run(
        self,
        actor: str,
        prepared: dict[str, Any],
        *,
        fixture_run: dict[str, Any] | None = None,
        results: list[dict[str, Any]] | None = None,
    ) -> None: ...

    def commit_prepared_run(self, actor: str, prepared: dict[str, Any]) -> dict[str, Any]: ...

    def start_run(self, actor: str, family_id: str, version: int, idempotency_key: str) -> dict[str, Any]: ...

    def prospects(self, actor: str, business_unit: str) -> list[dict[str, Any]]: ...

    def get_prospect(self, actor: str, business_unit: str, prospect_id: str) -> dict[str, Any]: ...

    def act(self, actor: str, business_unit: str, prospect_id: str, action: str, values: dict[str, str]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class CampaignVersion:
    family_id: str
    version: int
    business_unit: str
    creator_actor: str
    created_at: str
    configuration: dict[str, Any]
    configuration_hash: str


@dataclass(frozen=True)
class ManualRun:
    run_id: str
    campaign_family_id: str
    campaign_version: int
    business_unit: str
    initiating_actor: str
    input_schema_version: int
    configuration_hash: str
    skill_name: str
    skill_version: str
    fixture_source_ids: tuple[str, ...]
    output_ids: tuple[str, ...]
    started_at: str
    completed_at: str
    status: str
    estimated_cost_usd: int
    errors: tuple[str, ...]
    stop_reason: str
    idempotency_key: str
    idempotency_fingerprint: str
    fixture_adapter: bool = True


@dataclass(frozen=True)
class ReviewEvent:
    event_id: str
    prospect_id: str
    business_unit: str
    kind: str
    actor: str
    effective_at: str
    recorded_at: str
    value: dict[str, Any]
    supersedes_id: str | None = None


def event_order(event: ReviewEvent) -> tuple[str, str, str]:
    """Deterministic current-state order: effective time, recorded time, then stable event ID."""
    return (event.effective_at, event.recorded_at, event.event_id)


def projection_order(event: dict[str, Any]) -> tuple[str, str, str]:
    """The same ordering tuple applied to a serialized event."""
    return (event["effective_at"], event["recorded_at"], event["event_id"])


def _synchronized(method):
    """Serialize access to the process-local fixture state.

    The Phase 4 loopback server handles requests on bounded threads so a human
    can cancel a running attempt; the reentrant lock keeps this repository's
    in-memory collections consistent under that limited concurrency.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


@dataclass
class FixtureRepository:
    """Process-local adapter. State intentionally disappears on restart."""

    clock: Callable[[], datetime]
    next_id: Callable[[str], str]
    fixture_path: Path
    campaign_versions: list[CampaignVersion] = field(default_factory=list)
    run_records: list[ManualRun] = field(default_factory=list)
    prospect_history: list[dict[str, Any]] = field(default_factory=list)
    prospect_records: dict[str, dict[str, Any]] = field(default_factory=dict)
    review_events: list[ReviewEvent] = field(default_factory=list)
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    idempotency: dict[str, tuple[str, str]] = field(default_factory=dict)
    fail_next_audit: bool = False

    def __post_init__(self) -> None:
        fixture = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        self.sources = tuple(fixture["sources"])
        self.fixture_candidates = tuple(fixture["prospects"])
        self._lock = threading.RLock()

    def _now(self) -> str:
        return self.clock().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _authorize(self, actor: str, business_unit: str) -> None:
        if actor not in ACTOR_SCOPE:
            raise MissionControlError(403, "Actor is not allowed in this local review surface.")
        if business_unit not in ACTOR_SCOPE[actor]:
            raise MissionControlError(403, "Business-unit access denied.")

    def _audit(self, *, actor: str, action: str, business_unit: str, record_id: str) -> None:
        if self.fail_next_audit:
            self.fail_next_audit = False
            raise MissionControlError(500, "The governed action could not be recorded.")
        self.audit_events.append({
            "audit_id": self.next_id("audit"),
            "actor": actor,
            "action": action,
            "business_unit": business_unit,
            "record_id": record_id,
            "recorded_at": self._now(),
        })

    @_synchronized
    def campaigns(self, actor: str) -> list[dict[str, Any]]:
        allowed = ACTOR_SCOPE.get(actor, set())
        return [asdict(item) for item in self.campaign_versions if item.business_unit in allowed]

    @_synchronized
    def get_campaign(self, actor: str, family_id: str, version: int) -> dict[str, Any]:
        for item in self.campaign_versions:
            if item.family_id == family_id and item.version == version:
                self._authorize(actor, item.business_unit)
                return asdict(item)
        raise MissionControlError(404, "Campaign version not found.")

    @_synchronized
    def add_campaign(self, actor: str, config: dict[str, Any], family_id: str | None = None) -> dict[str, Any]:
        self._authorize(actor, config.get("business_unit", ""))
        try:
            validate_campaign(config, base_dir=REPOSITORY_ROOT)
        except ValidationError as exc:
            raise MissionControlError(400, str(exc)) from exc
        if family_id:
            family = [item for item in self.campaign_versions if item.family_id == family_id]
            if not family:
                raise MissionControlError(404, "Campaign family not found.")
            if any(item.business_unit != config["business_unit"] for item in family):
                raise MissionControlError(403, "A campaign family cannot change business unit.")
            version = max(item.version for item in family) + 1
        else:
            family_id = self.next_id("campaign")
            version = 1
        serialized = json.dumps(config, sort_keys=True, separators=(",", ":"))
        item = CampaignVersion(
            family_id=family_id,
            version=version,
            business_unit=config["business_unit"],
            creator_actor=actor,
            created_at=self._now(),
            configuration=copy.deepcopy(config),
            configuration_hash=hashlib.sha256(serialized.encode()).hexdigest(),
        )
        before = len(self.audit_events)
        self._audit(actor=actor, action="campaign_version_created", business_unit=item.business_unit, record_id=family_id)
        try:
            self.campaign_versions.append(item)
        except Exception:
            del self.audit_events[before:]
            raise
        return asdict(item)

    @_synchronized
    def ensure_campaign_version(
        self,
        actor: str,
        family_id: str,
        version: int,
        configuration: dict[str, Any],
        configuration_hash: str,
        created_at: str,
    ) -> dict[str, Any]:
        """Rehydrate an immutable campaign version from durable Phase 4 state.

        A fresh process has empty in-memory campaign collections; a durable
        worker retry replays its persisted validated snapshot through this
        boundary. Identity, business unit, and configuration hash must match
        exactly, and the frozen Phase 1 validator re-runs before anything is
        registered. No client-supplied data reaches this path.
        """
        self._authorize(actor, configuration.get("business_unit", ""))
        serialized = json.dumps(configuration, sort_keys=True, separators=(",", ":"))
        if hashlib.sha256(serialized.encode()).hexdigest() != configuration_hash:
            raise MissionControlError(409, "The durable configuration snapshot failed its integrity check.")
        for item in self.campaign_versions:
            if item.family_id == family_id and item.version == version:
                if item.configuration_hash != configuration_hash or item.business_unit != configuration["business_unit"]:
                    raise MissionControlError(409, "The durable campaign identity conflicts with this process's campaign state.")
                return asdict(item)
        try:
            validate_campaign(configuration, base_dir=REPOSITORY_ROOT)
        except ValidationError as exc:
            raise MissionControlError(400, str(exc)) from exc
        item = CampaignVersion(
            family_id=family_id,
            version=version,
            business_unit=configuration["business_unit"],
            creator_actor=actor,
            created_at=created_at,
            configuration=copy.deepcopy(configuration),
            configuration_hash=configuration_hash,
        )
        before = len(self.audit_events)
        self._audit(actor=actor, action="campaign_version_rehydrated", business_unit=item.business_unit, record_id=family_id)
        try:
            self.campaign_versions.append(item)
        except Exception:
            del self.audit_events[before:]
            raise
        return asdict(item)

    @_synchronized
    def runs(self, actor: str) -> list[dict[str, Any]]:
        allowed = ACTOR_SCOPE.get(actor, set())
        return [asdict(item) for item in self.run_records if item.business_unit in allowed]

    @_synchronized
    def get_run(self, actor: str, run_id: str) -> dict[str, Any]:
        for item in self.run_records:
            if item.run_id == run_id:
                self._authorize(actor, item.business_unit)
                return asdict(item)
        raise MissionControlError(404, "Run not found.")

    @staticmethod
    def _normalized(value: str) -> str:
        return "".join(character for character in value.casefold() if character.isalnum())

    def _select_candidates(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = [copy.deepcopy(item) for item in self.fixture_candidates if item["business_unit"] == config["business_unit"]]
        if config["discovery_scope"] == "filtered":
            wanted = {self._normalized(value) for value in config["verticals"]}
            candidates = [item for item in candidates if wanted & {self._normalized(value) for value in item["verticals"]}]
        return sorted(candidates, key=lambda item: (-item["score"], item["prospect_id"]))

    def _evidence_rejection(self, candidate: dict[str, Any], config: dict[str, Any]) -> str:
        evidence = candidate.get("evidence", [])
        if not evidence:
            return "missing_evidence"
        observed: list[date] = []
        for entry in evidence:
            try:
                observed.append(date.fromisoformat(entry["observed_at"]))
            except (KeyError, TypeError, ValueError):
                return "invalid_evidence_date"
        age = (self.clock().astimezone(timezone.utc).date() - max(observed)).days
        return "stale_evidence" if age > config["maximum_evidence_age_days"] else ""

    def _cooldown_active(self, candidate: dict[str, Any]) -> bool:
        value = candidate.get("cooldown_until")
        if not value:
            return False
        try:
            until = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return True
        return self.clock().astimezone(timezone.utc) < until.astimezone(timezone.utc)

    def _queue(
        self, candidate: dict[str, Any], config: dict[str, Any],
        history: dict[str, Any] | None = None,
    ) -> tuple[str, str, str | None]:
        if history is not None:
            decision = classify_duplicate(
                {
                    "company_name": candidate["account_name"],
                    "domain": candidate["domain"],
                    "company_type": "agency" if candidate.get("relationship") == "agency" else "brand",
                },
                history,
                config,
                today=self.clock().astimezone(timezone.utc).date(),
            )
            status = decision["status"]
            if status != "new_prospect":
                if status in {
                    "existing_new_trigger", "possible_duplicate_needs_review", "distinct_subbrand",
                    "parent_company_relationship", "agency_brand_overlap",
                }:
                    return "duplicate_reengagement", status, status
                return "rejections", status, status
        if candidate.get("duplicate_state") in {"possible_duplicate", "exact_duplicate", "reengagement"}:
            if candidate["duplicate_state"] == "reengagement" and not config["reengagement_enabled"]:
                return "duplicate_reengagement", "reengagement_disabled", candidate["duplicate_state"]
            return "duplicate_reengagement", candidate["duplicate_state"], candidate["duplicate_state"]
        rejection = candidate.get("rejection_reason")
        if candidate.get("relationship") in {"client", "partner", "active_outreach"}:
            rejection = f"existing_{candidate['relationship']}"
        elif candidate.get("suppressed"):
            rejection = "suppressed"
        elif self._cooldown_active(candidate):
            rejection = "active_cooldown"
        elif evidence_rejection := self._evidence_rejection(candidate, config):
            rejection = evidence_rejection
        elif candidate["score"] < config["minimum_qualification_score"]:
            rejection = "below_threshold"
        elif candidate.get("named_talent"):
            rejection = "unauthorized_named_talent"
        elif candidate.get("rights_state") == "conflict":
            rejection = "rights_conflict"
        elif candidate.get("brand_safety_state") == "conflict":
            rejection = "brand_safety_conflict"
        return ("rejections", rejection, None) if rejection else ("new", "", None)

    @_synchronized
    def prepare_run(
        self, actor: str, family_id: str, version: int, idempotency_key: str,
        *, history: dict[str, Any] | None = None, prospect_cap: int | None = None,
    ) -> dict[str, Any]:
        """Compute a fixture run without exposing it in process-local state."""
        campaign = self.get_campaign(actor, family_id, version)
        self._authorize(actor, campaign["business_unit"])
        if history is not None:
            validate_history(history)
        if prospect_cap is not None and (type(prospect_cap) is not int or not 1 <= prospect_cap <= 15):
            raise MissionControlError(400, "The shadow prospect cap is outside its reviewed bounds.")
        if not idempotency_key or len(idempotency_key) > 100 or any(not (character.isalnum() or character in "_-") for character in idempotency_key):
            raise MissionControlError(400, "A bounded alphanumeric idempotency key is required.")
        fingerprint = hashlib.sha256(json.dumps({
            "family_id": family_id,
            "version": version,
            "actor": actor,
            "business_unit": campaign["business_unit"],
            "configuration_hash": campaign["configuration_hash"],
        }, sort_keys=True).encode()).hexdigest()
        existing = self.idempotency.get(idempotency_key)
        if existing:
            if existing[0] != fingerprint:
                raise MissionControlError(409, "Idempotency key was already used with different input.")
            return {"existing_run": self.get_run(actor, existing[1])}

        candidates = self._select_candidates(campaign["configuration"])
        started_at = self._now()
        run_id = self.next_id("run")
        projections: list[dict[str, Any]] = []
        errors: list[str] = []
        eligible_count = 0
        for candidate in candidates:
            queue, rejection, duplicate_classification = self._queue(
                candidate, campaign["configuration"], history
            )
            if queue == "new":
                effective_cap = min(
                    campaign["configuration"]["target_prospect_count"],
                    prospect_cap if prospect_cap is not None else campaign["configuration"]["target_prospect_count"],
                )
                if eligible_count >= effective_cap:
                    queue, rejection = "rejections", "target_cap"
                else:
                    eligible_count += 1
            record = copy.deepcopy(candidate)
            record.update({
                "run_id": run_id,
                "campaign_family_id": family_id,
                "campaign_version": version,
                "queue": queue,
                "effective_rejection": rejection,
                "proposal_actor": actor if queue == "new" else None,
                "current_decision": "pending" if queue == "new" else rejection or candidate.get("duplicate_state"),
                "effective_cooldown": self._cooldown_active(candidate),
            })
            if history is not None:
                record["duplicate_classification"] = duplicate_classification
            projections.append(record)
            if candidate.get("source_error"):
                errors.append(candidate["source_error"][:MAX_TEXT])
        if not candidates:
            status, stop_reason = "no_results", "No synthetic fixtures matched the selected filters."
        elif all(item["queue"] == "rejections" for item in projections):
            status, stop_reason = "blocked_by_protection", "All matched fixtures were blocked by protection rules."
        elif any(item.get("fixture_validation_error") for item in projections):
            status, stop_reason = "failed_validation", "A synthetic fixture failed bounded validation."
        else:
            status = "completed"
            stop_reason = "Fixture evaluation completed with partial source errors." if errors else "Fixture evaluation completed."
        run = ManualRun(
            run_id=run_id,
            campaign_family_id=family_id,
            campaign_version=version,
            business_unit=campaign["business_unit"],
            initiating_actor=actor,
            input_schema_version=1,
            configuration_hash=campaign["configuration_hash"],
            skill_name="unreal-media-brand-prospector" if campaign["business_unit"] == "unreal-media-group" else "unreal-talent-campaign-prospector",
            skill_version="1.0.0-phase1-frozen",
            fixture_source_ids=tuple(self.sources),
            output_ids=tuple(item["prospect_id"] for item in projections),
            started_at=started_at,
            completed_at=self._now(),
            status=status,
            estimated_cost_usd=0,
            errors=tuple(errors[:10]),
            stop_reason=stop_reason,
            idempotency_key=idempotency_key,
            idempotency_fingerprint=fingerprint,
        )
        if self.fail_next_audit:
            self.fail_next_audit = False
            raise MissionControlError(500, "The governed action could not be recorded.")
        audit = {
            "audit_id": self.next_id("audit"),
            "actor": actor,
            "action": "manual_fixture_run",
            "business_unit": run.business_unit,
            "record_id": run_id,
            "recorded_at": self._now(),
        }
        return {
            "run": run,
            "fixture_run": asdict(run),
            "projections": projections,
            "results": [
                self._project_prospect(
                    item,
                    self.events_for(actor, run.business_unit, item["prospect_id"]),
                )
                for item in projections
            ],
            "audit": audit,
        }

    @_synchronized
    def validate_prepared_run(
        self,
        actor: str,
        prepared: dict[str, Any],
        *,
        fixture_run: dict[str, Any] | None = None,
        results: list[dict[str, Any]] | None = None,
    ) -> None:
        """Validate the concrete prepared shape without mutating local state."""

        def invalid() -> None:
            raise MissionControlError(500, "Prepared fixture result has an unexpected shape.")

        def validate_results(
            values: Any, output_ids: tuple[str, ...], business_unit: str
        ) -> None:
            if type(values) is not list or any(type(item) is not dict for item in values):
                invalid()
            if tuple(item.get("prospect_id") for item in values) != output_ids:
                invalid()
            if any(item.get("business_unit") != business_unit for item in values):
                invalid()
            try:
                json.dumps(values, sort_keys=True, separators=(",", ":"))
            except (TypeError, ValueError, RecursionError):
                invalid()

        if type(prepared) is not dict or (fixture_run is None) != (results is None):
            invalid()
        if "existing_run" in prepared:
            if set(prepared) != {"existing_run"} or type(prepared["existing_run"]) is not dict:
                invalid()
            existing_run = prepared["existing_run"]
            required = {
                "run_id", "business_unit", "fixture_source_ids", "output_ids", "status",
                "estimated_cost_usd", "errors", "stop_reason", "idempotency_key",
                "idempotency_fingerprint",
            }
            if not required.issubset(existing_run):
                invalid()
            if (
                not isinstance(existing_run["run_id"], str)
                or not isinstance(existing_run["business_unit"], str)
                or type(existing_run["fixture_source_ids"]) not in {list, tuple}
                or type(existing_run["output_ids"]) not in {list, tuple}
                or type(existing_run["errors"]) not in {list, tuple}
                or any(not isinstance(value, str) for value in existing_run["fixture_source_ids"])
                or any(not isinstance(value, str) for value in existing_run["output_ids"])
                or any(not isinstance(value, str) for value in existing_run["errors"])
                or not isinstance(existing_run["status"], str)
                or type(existing_run["estimated_cost_usd"]) is not int
                or not isinstance(existing_run["stop_reason"], str)
                or not isinstance(existing_run["idempotency_key"], str)
                or not isinstance(existing_run["idempotency_fingerprint"], str)
            ):
                invalid()
            self._authorize(actor, existing_run["business_unit"])
            try:
                json.dumps(existing_run, sort_keys=True, separators=(",", ":"))
            except (TypeError, ValueError, RecursionError):
                invalid()
            stored_run = next(
                (item for item in self.run_records if item.run_id == existing_run["run_id"]),
                None,
            )
            if (
                stored_run is None
                or asdict(stored_run) != existing_run
                or self.idempotency.get(existing_run["idempotency_key"])
                != (existing_run["idempotency_fingerprint"], existing_run["run_id"])
            ):
                invalid()
            if fixture_run is not None:
                if type(fixture_run) is not dict or fixture_run != existing_run:
                    invalid()
                validate_results(
                    results,
                    tuple(existing_run["output_ids"]),
                    existing_run["business_unit"],
                )
            return

        required = {"run", "fixture_run", "projections", "results", "audit"}
        if not required.issubset(prepared) or not isinstance(prepared["run"], ManualRun):
            invalid()
        run = prepared["run"]
        if (
            not isinstance(run.run_id, str)
            or not isinstance(run.business_unit, str)
            or not isinstance(run.idempotency_key, str)
            or not isinstance(run.idempotency_fingerprint, str)
            or any(not isinstance(value, str) for value in run.output_ids)
        ):
            invalid()
        self._authorize(actor, run.business_unit)
        serialized_run = asdict(run)
        projections = prepared["projections"]
        prepared_results = prepared["results"]
        audit = prepared["audit"]
        if (
            type(prepared["fixture_run"]) is not dict
            or prepared["fixture_run"] != serialized_run
            or type(projections) is not list
            or any(type(item) is not dict for item in projections)
            or type(audit) is not dict
        ):
            invalid()
        if tuple(item.get("prospect_id") for item in projections) != run.output_ids:
            invalid()
        if any(
            item.get("business_unit") != run.business_unit
            or item.get("run_id") != run.run_id
            or item.get("campaign_family_id") != run.campaign_family_id
            or item.get("campaign_version") != run.campaign_version
            for item in projections
        ):
            invalid()
        required_audit = {"audit_id", "actor", "action", "business_unit", "record_id", "recorded_at"}
        if (
            set(audit) != required_audit
            or any(not isinstance(audit[key], str) for key in required_audit)
            or audit["actor"] != actor
            or audit["action"] != "manual_fixture_run"
            or audit["business_unit"] != run.business_unit
            or audit["record_id"] != run.run_id
        ):
            invalid()
        validate_results(prepared_results, run.output_ids, run.business_unit)
        try:
            json.dumps(
                [serialized_run, projections, audit],
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError, RecursionError):
            invalid()
        if fixture_run is not None and (
            type(fixture_run) is not dict
            or fixture_run != prepared["fixture_run"]
            or results != prepared_results
        ):
            invalid()

    @_synchronized
    def commit_prepared_run(self, actor: str, prepared: dict[str, Any]) -> dict[str, Any]:
        """Project a fully prepared run after its durable success commits."""
        self.validate_prepared_run(actor, prepared)
        existing_run = prepared.get("existing_run")
        if existing_run is not None:
            self._authorize(actor, existing_run["business_unit"])
            return copy.deepcopy(existing_run)
        run = prepared["run"]
        self._authorize(actor, run.business_unit)
        existing = self.idempotency.get(run.idempotency_key)
        if existing:
            if existing[0] != run.idempotency_fingerprint:
                raise MissionControlError(409, "Idempotency key was already used with different input.")
            return self.get_run(actor, existing[1])
        before_audit = len(self.audit_events)
        before_runs = len(self.run_records)
        before_history = len(self.prospect_history)
        records_before = copy.deepcopy(self.prospect_records)
        idempotency_before = dict(self.idempotency)
        try:
            self.audit_events.append(copy.deepcopy(prepared["audit"]))
            self.run_records.append(run)
            for projection in prepared["projections"]:
                key = f"{run.business_unit}:{projection['prospect_id']}"
                preserved = copy.deepcopy(projection)
                self.prospect_history.append(preserved)
                self.prospect_records[key] = copy.deepcopy(preserved)
            self.idempotency[run.idempotency_key] = (
                run.idempotency_fingerprint,
                run.run_id,
            )
        except Exception:
            del self.audit_events[before_audit:]
            del self.run_records[before_runs:]
            del self.prospect_history[before_history:]
            self.prospect_records = records_before
            self.idempotency = idempotency_before
            raise
        return asdict(run)

    @_synchronized
    def start_run(self, actor: str, family_id: str, version: int, idempotency_key: str) -> dict[str, Any]:
        prepared = self.prepare_run(actor, family_id, version, idempotency_key)
        return self.commit_prepared_run(actor, prepared)

    @staticmethod
    def _project_prospect(item: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
        result = copy.deepcopy(item)
        result["review_history"] = events
        current: dict[str, dict[str, Any]] = {}
        for event in events:
            domain = state_domain(event["kind"])
            if domain is None:
                continue
            previous = current.get(domain)
            if previous is None or projection_order(event) > projection_order(previous):
                current[domain] = event
        result["current_review"] = current
        result["effective_suppressed"] = bool(result.get("suppressed")) or "suppress" in current
        result["effective_assignment"] = current.get("assign", {}).get("value", {}).get("assignee")
        result["notes"] = [event["value"]["text"] for event in events if event["kind"] == "note"]
        identity = current.get("resolve_identity")
        result["effective_matched_identity_id"] = identity["value"]["matched_identity_id"] if identity else None
        result["effective_duplicate_state"] = "resolved_duplicate" if identity else result.get("duplicate_state")
        decision = current.get("decision")
        if decision:
            result["current_decision"] = "approved_for_deeper_research" if decision["kind"] == "approve_deeper_research" else "rejected"
        return result

    @_synchronized
    def prospects(self, actor: str, business_unit: str) -> list[dict[str, Any]]:
        self._authorize(actor, business_unit)
        items = [
            self.get_prospect(actor, business_unit, item["prospect_id"])
            for item in self.prospect_records.values() if item["business_unit"] == business_unit
        ]
        return sorted(items, key=lambda item: (item["queue"], item["prospect_id"]))

    @_synchronized
    def get_prospect(self, actor: str, business_unit: str, prospect_id: str) -> dict[str, Any]:
        self._authorize(actor, business_unit)
        item = self.prospect_records.get(f"{business_unit}:{prospect_id}")
        if not item:
            raise MissionControlError(404, "Prospect not found in this business unit.")
        return self._project_prospect(item, self.events_for(actor, business_unit, prospect_id))

    @_synchronized
    def events_for(self, actor: str, business_unit: str, prospect_id: str) -> list[dict[str, Any]]:
        self._authorize(actor, business_unit)
        return [asdict(item) for item in sorted(
            (event for event in self.review_events if event.business_unit == business_unit and event.prospect_id == prospect_id),
            key=event_order,
        )]

    def _append_event(self, actor: str, business_unit: str, prospect_id: str, kind: str, value: dict[str, Any], supersedes_id: str | None = None) -> dict[str, Any]:
        self.get_prospect(actor, business_unit, prospect_id)
        domain = state_domain(kind)
        if domain is None:
            if supersedes_id:
                raise MissionControlError(409, "This action supersedes no governed state domain.")
        else:
            stream = [
                event for event in self.review_events
                if event.prospect_id == prospect_id and event.business_unit == business_unit and state_domain(event.kind) == domain
            ]
            if stream and supersedes_id != max(stream, key=event_order).event_id:
                raise MissionControlError(409, "A correction must supersede the current event explicitly.")
            if supersedes_id and not any(event.event_id == supersedes_id for event in stream):
                raise MissionControlError(409, "The superseded event is not part of this prospect state domain.")
        now = self._now()
        event = ReviewEvent(
            event_id=self.next_id("event"), prospect_id=prospect_id, business_unit=business_unit,
            kind=kind, actor=actor, effective_at=now, recorded_at=now,
            value=copy.deepcopy(value), supersedes_id=supersedes_id,
        )
        audit_len = len(self.audit_events)
        self._audit(actor=actor, action=kind, business_unit=business_unit, record_id=prospect_id)
        try:
            self.review_events.append(event)
        except Exception:
            del self.audit_events[audit_len:]
            raise
        return asdict(event)

    @_synchronized
    def act(self, actor: str, business_unit: str, prospect_id: str, action: str, values: dict[str, str]) -> dict[str, Any]:
        self._authorize(actor, business_unit)
        prospect = self.get_prospect(actor, business_unit, prospect_id)
        supersedes_id = values.get("supersedes_id") or None
        if action == "resolve_identity":
            target = values.get("matched_identity_id", "")
            if prospect.get("duplicate_state") != "possible_duplicate" or target not in prospect.get("matched_identity_ids", []):
                raise MissionControlError(409, "Identity resolution requires an exact listed synthetic match.")
            return self._append_event(actor, business_unit, prospect_id, action, {"matched_identity_id": target}, supersedes_id)
        if action == "suppress":
            reason = bounded_text(values.get("reason", ""), "suppression reason", MAX_TEXT)
            return self._append_event(actor, business_unit, prospect_id, action, {"reason": reason}, supersedes_id)
        if action == "approve_deeper_research":
            self._ensure_eligible(actor, prospect, supersedes_id)
            if actor == prospect.get("proposal_actor"):
                raise MissionControlError(403, "The proposing actor cannot approve their own request.")
            return self._append_event(actor, business_unit, prospect_id, action, {"decision": "approved"}, supersedes_id)
        if action == "reject":
            reason = bounded_text(values.get("reason", ""), "rejection reason", MAX_TEXT)
            return self._append_event(actor, business_unit, prospect_id, action, {"decision": "rejected", "reason": reason}, supersedes_id)
        if action == "assign":
            assignee = values.get("assignee", "")
            if assignee not in ACTOR_SCOPE or business_unit not in ACTOR_SCOPE[assignee]:
                raise MissionControlError(400, "Assignee is not allowed for this business unit.")
            return self._append_event(actor, business_unit, prospect_id, action, {"assignee": assignee}, supersedes_id)
        if action == "note":
            return self._append_event(actor, business_unit, prospect_id, action, {"text": bounded_text(values.get("text", ""), "note", MAX_NOTE)})
        raise MissionControlError(400, "Unknown governed action.")

    def _ensure_eligible(self, actor: str, prospect: dict[str, Any], supersedes_id: str | None = None) -> None:
        latest = self.get_prospect(actor, prospect["business_unit"], prospect["prospect_id"])
        if latest["effective_suppressed"]:
            raise MissionControlError(409, "Suppressed prospects cannot be approved.")
        decision = latest["current_review"].get("decision")
        if decision and decision["kind"] == "reject" and supersedes_id != decision["event_id"]:
            raise MissionControlError(409, "Rejected prospects cannot be approved without a superseding governed decision.")
        if prospect.get("named_talent"):
            raise MissionControlError(409, "Unauthorized named talent is blocked.")
        if prospect.get("rights_state") == "conflict" or prospect.get("brand_safety_state") == "conflict":
            raise MissionControlError(409, "Unresolved rights or brand-safety conflict blocks approval.")
        if latest["effective_duplicate_state"] == "resolved_duplicate":
            raise MissionControlError(409, f"Resolved duplicate of synthetic identity {latest['effective_matched_identity_id']} blocks new-prospect approval.")
        if latest["effective_duplicate_state"] != "new":
            raise MissionControlError(409, "Identity or re-engagement review must be resolved before approval.")
        if prospect.get("relationship") in {"client", "partner", "active_outreach"}:
            raise MissionControlError(409, "Existing relationship or active outreach blocks approval.")
        if prospect.get("effective_cooldown"):
            raise MissionControlError(409, "Active cooldown blocks approval.")
        if prospect.get("effective_rejection"):
            raise MissionControlError(409, f"Protection rule blocks approval: {prospect['effective_rejection']}.")
        if prospect["queue"] != "new":
            raise MissionControlError(409, "This prospect is not eligible for deeper research.")


def bounded_text(value: str, label: str, maximum: int = MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise MissionControlError(400, f"{label} must be text.")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > maximum or any(ord(character) < 32 and character not in "\n\t" for character in cleaned):
        raise MissionControlError(400, f"{label} must contain 1 to {maximum} safe characters.")
    return cleaned


def split_values(value: str, *, maximum: int = MAX_LIST) -> list[str]:
    items = [item.strip() for item in value.split(",") if item.strip()]
    if len(items) > maximum or any(len(item) > 100 or any(ord(character) < 32 for character in item) for item in items):
        raise MissionControlError(400, "Too many or overly long list values.")
    return items


def safe_evidence_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username and not parsed.password


class CounterIds:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self, prefix: str) -> str:
        self.value += 1
        return f"{prefix}-{self.value:04d}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MissionControl:
    """Application service consumed by HTML routes and future adapters."""

    def __init__(self, repository: Repository | None = None):
        self.repository = repository or FixtureRepository(
            clock=utc_now,
            next_id=CounterIds(),
            fixture_path=REPOSITORY_ROOT / "fixtures" / "prospecting" / "phase3" / "prospects.json",
        )

    def campaign_config(self, form: dict[str, str]) -> dict[str, Any]:
        business_unit = form.get("business_unit", "")
        scope = form.get("discovery_scope", "")
        verticals = split_values(form.get("verticals", ""))
        def number(name: str, conversion: Callable[[str], Any]) -> Any:
            try:
                return conversion(form.get(name, ""))
            except ValueError as exc:
                raise MissionControlError(400, f"{name} must be a valid number.") from exc

        target = number("target_prospect_count", int)
        score = number("minimum_qualification_score", float)
        cooldown = number("cooldown_days", int)
        freshness = number("maximum_evidence_age_days", int)
        talent_categories = split_values(form.get("talent_categories", ""))
        geography = split_values(form.get("geography", ""))
        rights = split_values(form.get("rights_territory", ""))
        config: dict[str, Any] = {
            "business_unit": business_unit,
            "campaign_name": bounded_text(form.get("campaign_name", ""), "campaign name", 120),
            "discovery_scope": scope,
            "verticals": verticals,
            "geography": {"countries": geography} if geography else {},
            "buyer_types": ["brand", "agency"] if business_unit == "unreal-talent" else ["brand"],
            "talent_categories": talent_categories,
            "rights_territory": rights,
            "campaign_channels": [],
            "target_prospect_count": target,
            "deep_research_limit": min(target, 10),
            "minimum_qualification_score": score,
            "required_signals": ["current synthetic fixture evidence"],
            "preferred_signals": [],
            "excluded_categories": [],
            "include_companies": [],
            "exclude_companies": [],
            "reengagement_enabled": form.get("reengagement_enabled") == "on",
            "cooldown_days": cooldown,
            "maximum_evidence_age_days": freshness,
            "output_formats": ["json", "html"],
            "prospect_history_path": "fixtures/prospecting/history/prospect-history.json",
            "approved_roster_path": None,
            "allow_named_talent_recommendations": False,
        }
        try:
            validate_campaign(config, base_dir=REPOSITORY_ROOT)
        except ValidationError as exc:
            raise MissionControlError(400, str(exc)) from exc
        return config

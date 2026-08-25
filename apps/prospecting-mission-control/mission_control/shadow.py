"""Phase 5 repository-local weekly scheduler in synthetic shadow mode.

The loop has one fixed UTC-weekly cadence, one bounded evaluation at a time,
and delegates execution to the existing RegisteredAgentService. It contains no
network client, external database, generic cron parser, outreach, or invocation
of the Phase 6 operational finder.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .agent import RegisteredAgentService, SCHEDULE_MANAGER
from .application import ACTOR_SCOPE, REPOSITORY_ROOT, MissionControlError
from .store import MAX_SNAPSHOT_BYTES, SqliteStore, canonical_json, shadow_result_metrics

# application.py has already added the frozen shared core to sys.path.
from classify_duplicate import validate_history  # noqa: E402
from common import ValidationError  # noqa: E402

MAX_ROTATION = 12
MAX_PROSPECT_CAP = 15
DEFAULT_HISTORY_SEED = (
    REPOSITORY_ROOT / "fixtures" / "prospecting" / "phase5" / "history-seeds.json"
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise MissionControlError(500, "The injected scheduler clock must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def weekly_due_at_or_after(now: datetime, weekday: int, hour: int, minute: int) -> datetime:
    """Return the first exact UTC weekly boundary at or after ``now``."""
    now = _utc(now)
    if type(weekday) is not int or not 0 <= weekday <= 6:
        raise MissionControlError(400, "Weekday must be an integer from 0 through 6.")
    if type(hour) is not int or not 0 <= hour <= 23:
        raise MissionControlError(400, "UTC hour must be an integer from 0 through 23.")
    if type(minute) is not int or not 0 <= minute <= 59:
        raise MissionControlError(400, "UTC minute must be an integer from 0 through 59.")
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    candidate += timedelta(days=(weekday - candidate.weekday()) % 7)
    if candidate < now:
        candidate += timedelta(days=7)
    return candidate


def _canonical_hash(value: Any, *, label: str) -> tuple[str, str]:
    serialized = canonical_json(value, limit=MAX_SNAPSHOT_BYTES, label=label)
    return serialized, hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class ShadowLoopService:
    """Governed schedule configuration, claims, history, and shadow execution."""

    def __init__(
        self,
        store: SqliteStore,
        agent: RegisteredAgentService,
        *,
        clock: Callable[[], datetime],
        history_seed_path: Path = DEFAULT_HISTORY_SEED,
    ):
        self.store = store
        self.agent = agent
        self.clock = clock
        self.history_seed_path = Path(history_seed_path)
        self._evaluation_lock = threading.Lock()
        self._pending_settlements: dict[str, dict[str, Any]] = {}
        self._pending_outputs: dict[str, str] = {}
        self.recovered_occurrence_ids = self.store.recover_shadow_occurrences(now=_iso(self._now()))

    def _now(self) -> datetime:
        return _utc(self.clock())

    @staticmethod
    def _authorize_read(actor: str, business_unit: str) -> None:
        if actor not in ACTOR_SCOPE or business_unit not in ACTOR_SCOPE[actor]:
            raise MissionControlError(403, "Business-unit access denied.")

    @staticmethod
    def _authorize_manage(actor: str) -> None:
        if actor != SCHEDULE_MANAGER:
            raise MissionControlError(403, "Noah must configure or control the local shadow schedule.")

    def create_schedule(
        self,
        *,
        actor: str,
        business_unit: str,
        name: str,
        campaign_refs: list[tuple[str, int]],
        weekday: int,
        utc_hour: int,
        utc_minute: int,
        prospect_cap: int,
        open_discovery_every: int = 0,
    ) -> dict[str, Any]:
        self._authorize_manage(actor)
        self._authorize_read(actor, business_unit)
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
            raise MissionControlError(400, "A bounded shadow schedule name is required.")
        weekly_due_at_or_after(self._now(), weekday, utc_hour, utc_minute)
        if type(prospect_cap) is not int or not 1 <= prospect_cap <= MAX_PROSPECT_CAP:
            raise MissionControlError(400, "The shadow prospect cap must be from 1 through 15.")
        if type(open_discovery_every) is not int or not 0 <= open_discovery_every <= 52:
            raise MissionControlError(400, "Open-discovery cadence must be from 0 through 52 weeks.")
        if not campaign_refs or len(campaign_refs) > MAX_ROTATION or len(set(campaign_refs)) != len(campaign_refs):
            raise MissionControlError(400, "The campaign rotation must contain 1 through 12 unique versions.")
        campaigns = []
        for family_id, version in campaign_refs:
            campaign = self.agent.repository.get_campaign(actor, family_id, version)
            if campaign["business_unit"] != business_unit:
                raise MissionControlError(403, "Business-unit access denied.")
            campaigns.append(campaign)
        if open_discovery_every and not any(
            item["configuration"]["discovery_scope"] == "open" for item in campaigns
        ):
            raise MissionControlError(400, "Configured open-discovery weeks require an open campaign version.")
        config = {
            "business_unit": business_unit,
            "name": name.strip(),
            "weekday": weekday,
            "utc_hour": utc_hour,
            "utc_minute": utc_minute,
            "prospect_cap": prospect_cap,
            "cost_cap_usd": 0,
            "open_discovery_every": open_discovery_every,
            "rotation": [
                {
                    "family_id": item["family_id"],
                    "version": item["version"],
                    "configuration_hash": item["configuration_hash"],
                }
                for item in campaigns
            ],
        }
        _, config_hash = _canonical_hash(config, label="Schedule configuration")
        return self.store.create_shadow_schedule(
            {
                **config,
                "created_by": actor,
                "campaigns": campaigns,
                "configuration_hash": config_hash,
            },
            now=_iso(self._now()),
        )

    def schedules(self, actor: str, business_unit: str) -> list[dict[str, Any]]:
        self._authorize_read(actor, business_unit)
        return self.store.list_shadow_schedules({business_unit})

    def get_schedule(self, actor: str, schedule_id: str) -> dict[str, Any]:
        item = self.store.get_shadow_schedule(schedule_id)
        if item is None or actor not in ACTOR_SCOPE or item["business_unit"] not in ACTOR_SCOPE[actor]:
            raise MissionControlError(404, "Shadow schedule not found.")
        return item

    def schedule_detail(self, actor: str, schedule_id: str) -> dict[str, Any]:
        item = self.get_schedule(actor, schedule_id)
        item["occurrences"] = [
            row for row in self.store.list_shadow_occurrences({item["business_unit"]})
            if row["schedule_id"] == schedule_id
        ]
        item["audits"] = self.store.shadow_schedule_audits(schedule_id)
        return item

    def _transition(
        self, actor: str, schedule_id: str, row_version: int,
        *, expected: tuple[str, ...], state: str,
    ) -> dict[str, Any]:
        self._authorize_manage(actor)
        schedule = self.get_schedule(actor, schedule_id)
        if schedule["row_version"] != row_version:
            raise MissionControlError(409, "The shadow schedule changed; reload before retrying.")
        due = None
        if state == "enabled":
            due = _iso(weekly_due_at_or_after(
                self._now(), schedule["weekday"], schedule["utc_hour"], schedule["utc_minute"]
            ))
        elif state == "paused":
            due = schedule["next_due_at"]
        updated = self.store.transition_shadow_schedule(
            schedule_id, expected_version=row_version, expected_states=expected,
            new_state=state, next_due_at=due, actor=actor, now=_iso(self._now()),
        )
        if updated is None:
            raise MissionControlError(409, "The shadow schedule transition lost an atomic race safely.")
        return updated

    def enable(self, actor: str, schedule_id: str, row_version: int) -> dict[str, Any]:
        return self._transition(actor, schedule_id, row_version, expected=("disabled",), state="enabled")

    def pause(self, actor: str, schedule_id: str, row_version: int) -> dict[str, Any]:
        return self._transition(actor, schedule_id, row_version, expected=("enabled",), state="paused")

    def resume(self, actor: str, schedule_id: str, row_version: int) -> dict[str, Any]:
        return self._transition(actor, schedule_id, row_version, expected=("paused",), state="enabled")

    def disable(self, actor: str, schedule_id: str, row_version: int) -> dict[str, Any]:
        return self._transition(
            actor, schedule_id, row_version, expected=("enabled", "paused"), state="disabled"
        )

    def occurrences(self, actor: str, business_unit: str) -> list[dict[str, Any]]:
        self._authorize_read(actor, business_unit)
        return self.store.list_shadow_occurrences({business_unit})

    def alerts(self, actor: str, business_unit: str) -> list[dict[str, Any]]:
        self._authorize_read(actor, business_unit)
        return self.store.list_shadow_alerts({business_unit})

    def _finish(self, occurrence_id: str, **fields: Any) -> dict[str, Any]:
        try:
            settled = self.store.finish_shadow_occurrence(occurrence_id, **fields)
        except MissionControlError:
            self._pending_settlements[occurrence_id] = fields
            try:
                settled = self.store.finish_shadow_occurrence(occurrence_id, **fields)
            except MissionControlError:
                raise
        self._pending_settlements.pop(occurrence_id, None)
        return settled

    def _finish_successful_run(
        self, actor: str, occurrence_id: str, run_id: str,
    ) -> dict[str, Any]:
        self._pending_outputs[occurrence_id] = run_id
        try:
            output = self.store.get_output(run_id)
            if output is None:
                raise MissionControlError(500, "The successful shadow run has no durable output.")
            result_count, duplicates, rate = shadow_result_metrics(output["result_snapshot"])
        except MissionControlError as exc:
            if not (
                exc.message.startswith("Stored result snapshot")
                or exc.message == "The successful shadow run has no durable output."
            ):
                raise
            settled = self._finish(
                occurrence_id, state="failed", failure_class="shadow_output_invalid",
                stop_reason="The shadow output failed its integrity check.",
                result_count=None, duplicate_count=None, duplicate_rate=None,
                actor=actor, now=_iso(self._now()),
            )
        else:
            settled = self._finish(
                occurrence_id, state="completed", failure_class=None,
                stop_reason=output["stop_reason"], result_count=result_count,
                duplicate_count=duplicates, duplicate_rate=rate,
                actor=actor, now=_iso(self._now()),
            )
        self._pending_outputs.pop(occurrence_id, None)
        return settled

    def claim_due(self, actor: str = SCHEDULE_MANAGER, schedule_id: str | None = None) -> dict[str, Any] | None:
        self._authorize_manage(actor)
        now = self._now()
        schedule = self.get_schedule(actor, schedule_id) if schedule_id else self.store.due_shadow_schedule(_iso(now))
        if not schedule or schedule["state"] != "enabled" or not schedule["next_due_at"]:
            return None
        scheduled_for = datetime.fromisoformat(schedule["next_due_at"].replace("Z", "+00:00"))
        if scheduled_for > now:
            return None
        future = scheduled_for + timedelta(days=7)
        if future <= now:
            skipped = ((now - future).days // 7) + 1
            future += timedelta(days=7 * skipped)
        identity = f"{schedule['schedule_id']}|{schedule['current_version']}|{_iso(scheduled_for)}"
        key = "shadow_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:48]
        return self.store.claim_shadow_occurrence(
            schedule["schedule_id"], expected_row_version=schedule["row_version"],
            scheduled_for=_iso(scheduled_for), next_due_at=_iso(future), idempotency_key=key,
            actor=actor, now=_iso(now),
        )

    def _load_history(self, business_unit: str) -> dict[str, Any]:
        try:
            raw = self.history_seed_path.read_bytes()
            if len(raw) > MAX_SNAPSHOT_BYTES:
                raise ValidationError("History seed exceeds the local safety limit.")
            document = json.loads(raw.decode("utf-8"))
            history = copy_history = json.loads(json.dumps(document[business_unit]))
            validate_history(history)
        except OSError as exc:
            raise MissionControlError(409, "history_unavailable") from exc
        except (KeyError, TypeError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            raise MissionControlError(409, "history_invalid") from exc

        by_domain: dict[str, dict[str, Any]] = {
            item["canonical_domain"].casefold(): item for item in copy_history["prospects"]
        }
        try:
            for output in self.store.successful_outputs_for_business_unit(business_unit):
                completed_date = output["created_at"][:10]
                campaign_ref = f"{output['campaign_family_id']}@{output['campaign_version']}"
                for result in output["result_snapshot"]:
                    if result.get("business_unit") != business_unit:
                        raise ValidationError("Durable result business unit is inconsistent.")
                    domain = result.get("domain")
                    identity = result.get("global_identity_id") or result.get("prospect_id")
                    if not isinstance(domain, str) or not isinstance(identity, str):
                        raise ValidationError("Durable result identity is incomplete.")
                    record = by_domain.get(domain.casefold())
                    if record is not None and record["id"] != identity:
                        raise ValidationError("Durable identity history is ambiguous.")
                    evidence = result.get("evidence") or []
                    signals = [
                        {"source_url": item["url"], "source_date": item["observed_at"]}
                        for item in evidence
                    ]
                    if record is None:
                        cooldown = result.get("cooldown_until")
                        record = {
                            "id": identity,
                            "canonical_company_name": result.get("account_name", identity),
                            "canonical_domain": domain,
                            "domains": [domain],
                            "alternate_names": [],
                            "social_handles": {},
                            "previous_discovery_dates": [],
                            "previous_campaign_appearances": [],
                            "previous_scores": [],
                            "previous_decisions": [],
                            "outreach_status": "active" if result.get("relationship") == "active_outreach" else "",
                            "client_status": "active" if result.get("relationship") == "client" else "",
                            "partner_status": "active" if result.get("relationship") == "partner" else "",
                            "suppressed": bool(result.get("suppressed")),
                            "suppression_reason": "Synthetic fixture suppression." if result.get("suppressed") else None,
                            "cooldown_until": cooldown[:10] if isinstance(cooldown, str) else None,
                            "prior_signals": [],
                            "prior_rejection_reasons": [],
                        }
                        by_domain[domain.casefold()] = record
                        copy_history["prospects"].append(record)
                    for key, value in (
                        ("previous_discovery_dates", completed_date),
                        ("previous_campaign_appearances", campaign_ref),
                        ("previous_scores", result.get("score")),
                        ("previous_decisions", result.get("current_decision")),
                    ):
                        if value is not None and value not in record[key]:
                            record[key].append(value)
                    for signal in signals:
                        if signal not in record["prior_signals"]:
                            record["prior_signals"].append(signal)
                    reason = result.get("effective_rejection")
                    if reason and reason not in record["prior_rejection_reasons"]:
                        record["prior_rejection_reasons"].append(reason)
            copy_history["generated_at"] = _iso(self._now())
            validate_history(copy_history)
        except (MissionControlError, ValidationError, KeyError, TypeError, ValueError) as exc:
            raise MissionControlError(409, "history_invalid") from exc
        return copy_history

    def execute_claimed(self, actor: str, occurrence: dict[str, Any]) -> dict[str, Any]:
        self._authorize_manage(actor)
        if occurrence["state"] != "claimed":
            return occurrence
        run_succeeded = False
        try:
            schedule = self.get_schedule(actor, occurrence["schedule_id"])
            campaign = next(
                item for item in schedule["campaigns"]
                if item["campaign_family_id"] == occurrence["campaign_family_id"]
                and item["campaign_version"] == occurrence["campaign_version"]
            )
            history = self._load_history(occurrence["business_unit"])
            serialized, history_hash = _canonical_hash(history, label="History snapshot")
            self.store.set_shadow_history(
                occurrence["occurrence_id"], history=json.loads(serialized), history_hash=history_hash
            )
            self.agent.repository.ensure_campaign_version(
                actor, campaign["campaign_family_id"], campaign["campaign_version"],
                campaign["configuration"], campaign["configuration_hash"], schedule["created_at"],
            )
            run, _created = self.agent.create_shadow_run(
                actor, campaign["campaign_family_id"], campaign["campaign_version"],
                occurrence["idempotency_key"],
                occurrence_id=occurrence["occurrence_id"],
            )
            if run["state"] == "queued":
                run = self.agent.execute_run(actor, run["run_id"])
            if run["state"] != "succeeded":
                return self._finish(
                    occurrence["occurrence_id"], state="failed",
                    failure_class=run.get("failure_class") or "worker_failure",
                    stop_reason=run.get("remediation") or "The registered worker failed safely.",
                    result_count=None, duplicate_count=None, duplicate_rate=None,
                    actor=actor, now=_iso(self._now()),
                )
            run_succeeded = True
            return self._finish_successful_run(actor, occurrence["occurrence_id"], run["run_id"])
        except (KeyError, StopIteration, TypeError, ValueError):
            return self._finish(
                occurrence["occurrence_id"], state="failed",
                failure_class="shadow_execution_failed",
                stop_reason="The local shadow occurrence failed safely.",
                result_count=None, duplicate_count=None, duplicate_rate=None,
                actor=actor, now=_iso(self._now()),
            )
        except MissionControlError as exc:
            if run_succeeded:
                raise
            failure_class = exc.message if exc.message in {"history_unavailable", "history_invalid"} else "shadow_execution_failed"
            message = {
                "history_unavailable": "Required synthetic history was unavailable; no worker attempt started.",
                "history_invalid": "Required synthetic history was invalid or inconsistent; no worker attempt started.",
            }.get(failure_class, "The local shadow occurrence failed safely.")
            return self._finish(
                occurrence["occurrence_id"], state="blocked" if failure_class.startswith("history_") else "failed",
                failure_class=failure_class, stop_reason=message,
                result_count=None, duplicate_count=None, duplicate_rate=None,
                actor=actor, now=_iso(self._now()),
            )

    def evaluate_due(self, actor: str = SCHEDULE_MANAGER) -> list[dict[str, Any]]:
        """Evaluate at most one due occurrence; duplicate ticks return no work."""
        if not self._evaluation_lock.acquire(blocking=False):
            return []
        try:
            if self._pending_settlements:
                occurrence_id = next(iter(self._pending_settlements))
                settled = self._finish(occurrence_id, **self._pending_settlements[occurrence_id])
                self._pending_outputs.pop(occurrence_id, None)
                return [settled]
            if self._pending_outputs:
                occurrence_id = next(iter(self._pending_outputs))
                return [self._finish_successful_run(
                    actor, occurrence_id, self._pending_outputs[occurrence_id]
                )]
            occurrence = self.claim_due(actor)
            if occurrence is None:
                return []
            if occurrence["state"] != "claimed":
                return [occurrence]
            return [self.execute_claimed(actor, occurrence)]
        finally:
            self._evaluation_lock.release()


class ShadowScheduler(threading.Thread):
    """One bounded, joinable wake loop for the repository-local Phase 5 service."""

    def __init__(self, service: ShadowLoopService, *, actor: str = SCHEDULE_MANAGER, wait_seconds: int = 60):
        super().__init__(name="prospecting-shadow-scheduler", daemon=False)
        self.service = service
        self.actor = actor
        self.wait_seconds = max(1, min(wait_seconds, 300))
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()

    def wake(self) -> None:
        self._wake_event.set()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.service.evaluate_due(self.actor)
            except MissionControlError:
                # Governed occurrence failures are persisted by the service;
                # the scheduler never emits payloads or tracebacks.
                pass
            self._wake_event.wait(self.wait_seconds)
            self._wake_event.clear()

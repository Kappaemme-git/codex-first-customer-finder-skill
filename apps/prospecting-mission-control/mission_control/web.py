"""Loopback HTTP surface for the synthetic Phase 3 review application."""

from __future__ import annotations

import argparse
import hmac
import html
import json
import re
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlencode, urlsplit

from pathlib import Path

from .application import ACTOR_SCOPE, BUSINESS_UNITS, MissionControl, MissionControlError, safe_evidence_url, state_domain, utc_now
from .agent import AGENT_ID, RegisteredAgentService, default_state_path
from .shadow import SCHEDULE_MANAGER, ShadowLoopService, ShadowScheduler
from .store import SqliteStore

MAX_BODY = 32_768
MAX_FIELDS = 40
IDENTIFIER = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")


def e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def page(title: str, body: str, *, actor: str, business_unit: str, status: str = "") -> str:
    query = urlencode({"actor": actor, "business_unit": business_unit})
    status_html = f'<p class="status" role="status" aria-live="polite">{e(status)}</p>' if status else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} · Prospecting Mission Control</title>
<style>
:root{{--ink:#17202a;--muted:#566573;--paper:#fbfcfc;--panel:#fff;--line:#ccd1d1;--accent:#174a7e;--warn:#7d3c00}}
*{{box-sizing:border-box}} body{{margin:0;font:16px/1.5 system-ui,sans-serif;color:var(--ink);background:var(--paper)}}
header,main,footer{{max-width:1120px;margin:auto;padding:1rem}} header{{border-bottom:1px solid var(--line)}}
nav{{display:flex;flex-wrap:wrap;gap:.8rem}} a{{color:var(--accent)}} a:focus,button:focus,input:focus,select:focus,textarea:focus{{outline:3px solid #f5b041;outline-offset:2px}}
.notice,.status,.error{{padding:.75rem;border:1px solid var(--line);background:var(--panel)}} .error{{border-color:#b03a2e}} .status{{border-color:#1e8449}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem}} .card{{padding:1rem;border:1px solid var(--line);background:var(--panel)}}
label{{display:block;font-weight:650;margin-top:.7rem}} input,select,textarea{{width:100%;max-width:42rem;padding:.55rem;border:1px solid #7b7d7d;background:white}} input[type=checkbox]{{width:auto}}
button{{margin-top:1rem;padding:.65rem 1rem;border:0;background:var(--accent);color:white;font-weight:700;cursor:pointer}} button[disabled]{{opacity:.55;cursor:not-allowed}}
table{{width:100%;border-collapse:collapse;background:var(--panel)}} th,td{{padding:.55rem;text-align:left;border:1px solid var(--line);vertical-align:top}} pre{{white-space:pre-wrap;overflow-wrap:anywhere}} dd,code,td{{overflow-wrap:anywhere}}
.tag{{display:inline-block;padding:.1rem .4rem;border:1px solid var(--line);margin:.1rem}} .warning{{color:var(--warn);font-weight:700}}
@media(max-width:640px){{table,thead,tbody,tr,th,td{{display:block}} thead{{position:absolute;left:-9999px}} td{{border-top:0}} nav{{flex-direction:column}}}}
</style></head><body>
<header><p><strong>Prospecting Manual Mission Control</strong></p>
<p class="notice"><strong>Synthetic local review surface.</strong> Campaign and governed prospect-review state resets on restart; registered worker runs and Phase 5 shadow schedules are durable in a local, gitignored SQLite file. The worker executes local synthetic fixtures only. Actor selection simulates policy; it is not production authentication. No external research, creative, likeness, or outbound capability exists.</p>
<nav aria-label="Primary"><a href="/campaigns?{query}">Campaigns</a><a href="/runs?{query}">Run history</a><a href="/worker-runs?{query}">Worker runs</a><a href="/review-tasks?{query}">Review tasks</a><a href="/prospects?{query}&amp;queue=new">Prospect queues</a><a href="/registry?{query}">Agent registry</a><a href="/shadow-schedules?{query}">Shadow schedules</a></nav>
<form method="get" action="/campaigns"><label for="scope_actor">Fixture review actor (not authentication)</label><select id="scope_actor" name="actor">{''.join(f'<option value="{e(name)}"{" selected" if name == actor else ""}>{e(name)}</option>' for name in ACTOR_SCOPE)}</select><label for="scope_unit">Business-unit scope</label><select id="scope_unit" name="business_unit">{''.join(f'<option value="{e(unit)}"{" selected" if unit == business_unit else ""}>{e(unit)}</option>' for unit in sorted(BUSINESS_UNITS))}</select><button type="submit">Change local review scope</button></form>
<p>Review actor: <strong>{e(actor)}</strong> · Business unit: <strong>{e(business_unit)}</strong></p></header>
<main id="main"><h1>{e(title)}</h1>{status_html}{body}</main>
<footer><small>Local synthetic registered worker · fixture-only shadow execution · durable local state · zero cost cap · no credentials, external network client, creative, likeness, approval, or outreach.</small></footer></body></html>"""


class WebApplication:
    def __init__(
        self,
        mission_control: MissionControl | None = None,
        csrf_token: str | None = None,
        agent_service: RegisteredAgentService | None = None,
        state_path: Path | None = None,
        shadow_service: ShadowLoopService | None = None,
    ):
        self.control = mission_control or MissionControl()
        self.csrf_token = csrf_token or secrets.token_urlsafe(32)
        self.agent = agent_service or RegisteredAgentService(
            self.control.repository,
            SqliteStore(state_path or default_state_path()),
            clock=getattr(self.control.repository, "clock", utc_now),
        )
        self.shadow = shadow_service or ShadowLoopService(
            self.agent.store,
            self.agent,
            clock=getattr(self.control.repository, "clock", utc_now),
        )

    @staticmethod
    def context(query: dict[str, list[str]]) -> tuple[str, str]:
        actor = query.get("actor", ["noah"])[0]
        business_unit = query.get("business_unit", ["unreal-media-group"])[0]
        if actor not in ACTOR_SCOPE:
            raise MissionControlError(403, "Unknown local review actor.")
        if business_unit not in BUSINESS_UNITS:
            raise MissionControlError(400, "Unknown business unit.")
        if business_unit not in ACTOR_SCOPE[actor]:
            raise MissionControlError(403, "Business-unit access denied.")
        return actor, business_unit

    def hidden(self, actor: str, business_unit: str) -> str:
        return f'<input type="hidden" name="csrf_token" value="{e(self.csrf_token)}"><input type="hidden" name="actor" value="{e(actor)}"><input type="hidden" name="business_unit" value="{e(business_unit)}">'

    def get(self, path: str, query: dict[str, list[str]]) -> tuple[int, str]:
        actor, business_unit = self.context(query)
        parts = [part for part in path.split("/") if part]
        if path in {"/", "/campaigns"}:
            return 200, self.campaigns(actor, business_unit)
        if path == "/campaigns/new":
            return 200, self.campaign_form(actor, business_unit)
        if len(parts) == 3 and parts[0] == "campaigns" and IDENTIFIER.fullmatch(parts[1]) and parts[2].isdigit():
            return 200, self.campaign_detail(actor, business_unit, parts[1], int(parts[2]))
        if path == "/runs":
            return 200, self.runs(actor, business_unit)
        if len(parts) == 2 and parts[0] == "runs" and IDENTIFIER.fullmatch(parts[1]):
            return 200, self.run_detail(actor, business_unit, parts[1])
        if path == "/prospects":
            queue = query.get("queue", ["new"])[0]
            if queue not in {"new", "duplicate_reengagement", "rejections"}:
                raise MissionControlError(400, "Unknown prospect queue.")
            return 200, self.prospects(actor, business_unit, queue)
        if len(parts) == 2 and parts[0] == "prospects" and IDENTIFIER.fullmatch(parts[1]):
            return 200, self.prospect_detail(actor, business_unit, parts[1])
        if path == "/registry":
            return 200, self.registry(actor, business_unit)
        if len(parts) == 2 and parts[0] == "registry" and IDENTIFIER.fullmatch(parts[1]):
            return 200, self.registry_detail(actor, business_unit, parts[1])
        if path == "/worker-runs":
            return 200, self.worker_runs(actor, business_unit)
        if len(parts) == 2 and parts[0] == "worker-runs" and IDENTIFIER.fullmatch(parts[1]):
            return 200, self.worker_run_detail(actor, business_unit, parts[1])
        if path == "/review-tasks":
            return 200, self.review_tasks(actor, business_unit)
        if len(parts) == 2 and parts[0] == "review-tasks" and IDENTIFIER.fullmatch(parts[1]):
            return 200, self.review_task_detail(actor, business_unit, parts[1])
        if path == "/shadow-schedules":
            return 200, self.shadow_schedules(actor, business_unit)
        if path == "/shadow-schedules/new":
            return 200, self.shadow_schedule_form(actor, business_unit)
        if len(parts) == 2 and parts[0] == "shadow-schedules" and IDENTIFIER.fullmatch(parts[1]):
            return 200, self.shadow_schedule_detail(actor, business_unit, parts[1])
        raise MissionControlError(404, "Page not found.")

    def post(self, path: str, form: dict[str, str]) -> tuple[int, str]:
        if not hmac.compare_digest(form.get("csrf_token", ""), self.csrf_token):
            raise MissionControlError(403, "CSRF validation failed.")
        actor = form.get("actor", "")
        business_unit = form.get("business_unit", "")
        self.context({"actor": [actor], "business_unit": [business_unit]})
        parts = [part for part in path.split("/") if part]
        if path == "/campaigns":
            try:
                config = self.control.campaign_config(form)
            except MissionControlError as exc:
                return exc.status, self.campaign_form(
                    actor, business_unit, config=form, family_id=form.get("family_id", ""), error=exc.message
                )
            item = self.control.repository.add_campaign(actor, config, form.get("family_id") or None)
            return 201, self.campaign_detail(actor, business_unit, item["family_id"], item["version"], "Immutable campaign version created.")
        if len(parts) == 4 and parts[0] == "campaigns" and IDENTIFIER.fullmatch(parts[1]) and parts[2].isdigit() and parts[3] == "run":
            campaign = self.control.repository.get_campaign(actor, parts[1], int(parts[2]))
            if campaign["business_unit"] != business_unit:
                raise MissionControlError(403, "Business-unit access denied.")
            run, created = self.agent.create_manual_run(actor, parts[1], int(parts[2]), form.get("idempotency_key", ""))
            if run["state"] == "queued":
                run = self.agent.execute_run(actor, run["run_id"])
            message = (
                "Registered-agent manual run executed."
                if created
                else "Idempotent replay: the existing logical run was returned without duplicate execution."
            )
            return 200, self.worker_run_detail(actor, business_unit, run["run_id"], message)
        if len(parts) == 3 and parts[0] == "worker-runs" and IDENTIFIER.fullmatch(parts[1]) and parts[2] in {"cancel", "retry"}:
            run = self.agent.get_run(actor, parts[1])
            if run["business_unit"] != business_unit:
                raise MissionControlError(403, "Business-unit access denied.")
            if parts[2] == "cancel":
                self.agent.cancel_run(actor, parts[1])
                message = "Cancellation recorded for the worker run."
            else:
                self.agent.retry_run(actor, parts[1])
                message = "Manual retry attempt executed under the same logical run."
            return 200, self.worker_run_detail(actor, business_unit, parts[1], message)
        if len(parts) == 3 and parts[0] == "prospects" and IDENTIFIER.fullmatch(parts[1]) and parts[2] == "actions":
            self.control.repository.act(actor, business_unit, parts[1], form.get("action", ""), form)
            return 200, self.prospect_detail(actor, business_unit, parts[1], "Append-only governed event recorded.")
        if path == "/shadow-schedules":
            refs = []
            for raw in form.get("campaign_refs", "").split(","):
                raw = raw.strip()
                if not raw:
                    continue
                family_id, separator, version = raw.partition(":")
                if not separator or not IDENTIFIER.fullmatch(family_id) or not version.isdigit():
                    raise MissionControlError(400, "Campaign versions must use family_id:version format.")
                refs.append((family_id, int(version)))
            schedule = self.shadow.create_schedule(
                actor=actor,
                business_unit=business_unit,
                name=form.get("name", ""),
                campaign_refs=refs,
                weekday=int(form.get("weekday", "")),
                utc_hour=int(form.get("utc_hour", "")),
                utc_minute=int(form.get("utc_minute", "")),
                prospect_cap=int(form.get("prospect_cap", "")),
                open_discovery_every=int(form.get("open_discovery_every", "0")),
            )
            return 201, self.shadow_schedule_detail(
                actor, business_unit, schedule["schedule_id"],
                "Synthetic local shadow schedule created disabled by default.",
            )
        if len(parts) == 3 and parts[0] == "shadow-schedules" and IDENTIFIER.fullmatch(parts[1]) and parts[2] in {"enable", "pause", "resume", "disable"}:
            schedule = self.shadow.get_schedule(actor, parts[1])
            if schedule["business_unit"] != business_unit:
                raise MissionControlError(403, "Business-unit access denied.")
            try:
                row_version = int(form.get("row_version", ""))
            except ValueError as exc:
                raise MissionControlError(400, "A valid schedule row version is required.") from exc
            transition = getattr(self.shadow, parts[2])
            transition(actor, parts[1], row_version)
            return 200, self.shadow_schedule_detail(
                actor, business_unit, parts[1], f"Shadow schedule {parts[2]} action recorded atomically.",
            )
        raise MissionControlError(404, "Action not found.")

    def campaigns(self, actor: str, business_unit: str) -> str:
        items = [item for item in self.control.repository.campaigns(actor) if item["business_unit"] == business_unit]
        query = urlencode({"actor": actor, "business_unit": business_unit})
        rows = "".join(f'<tr><td>{e(item["configuration"]["campaign_name"])}</td><td>{item["version"]}</td><td>{e(item["configuration"]["discovery_scope"])}</td><td><a href="/campaigns/{e(item["family_id"])}/{item["version"]}?{query}">Open</a></td></tr>' for item in items)
        body = f'<p><a href="/campaigns/new?{query}">Create a campaign</a></p>'
        body += '<p class="notice">No campaigns exist for this business unit. Create one to start a manual fixture run.</p>' if not rows else f'<table><thead><tr><th>Campaign</th><th>Version</th><th>Scope</th><th>View</th></tr></thead><tbody>{rows}</tbody></table>'
        return page("Campaigns", body, actor=actor, business_unit=business_unit)

    def campaign_form(self, actor: str, business_unit: str, *, config: dict[str, Any] | None = None, family_id: str = "", error: str = "") -> str:
        config = config or {}
        selected = lambda value, current: " selected" if value == current else ""
        def list_text(key: str) -> str:
            value = config.get(key, [])
            return value if isinstance(value, str) else ", ".join(value)

        geography_value = config.get("geography", "")
        if isinstance(geography_value, dict):
            geography_value = ", ".join(geography_value.get("countries", []))
        lowered_error = error.casefold()
        field_aliases = {
            "campaign_name": ("campaign_name", "campaign name"),
            "discovery_scope": ("discovery_scope", "discovery scope"),
            "verticals": ("vertical", "filtered discovery"),
            "target_prospect_count": ("target_prospect_count", "target prospect"),
            "minimum_qualification_score": ("minimum_qualification_score", "minimum qualification"),
            "cooldown_days": ("cooldown_days", "cooldown"),
            "maximum_evidence_age_days": ("maximum_evidence_age_days", "evidence age"),
            "rights_territory": ("rights_territory", "rights territory"),
        }
        error_field = next((key for key, aliases in field_aliases.items() if error and any(alias in lowered_error for alias in aliases)), "campaign_name" if error else "")
        def invalid(key: str) -> str:
            return f' aria-invalid="true" aria-describedby="{key}_error"' if error_field == key else ""

        def field_error(key: str) -> str:
            return f'<p id="{key}_error" class="error">{e(error)}</p>' if error_field == key else ""

        described_by = "campaign-help campaign-errors" if error else "campaign-help"
        error_summary = f'<p id="campaign-errors" class="error" role="alert">Campaign validation failed. {e(error)}</p>' if error else ""
        body = f"""<form method="post" action="/campaigns" aria-describedby="{described_by}">
{self.hidden(actor, business_unit)}<input type="hidden" name="family_id" value="{e(family_id)}">
<p id="campaign-help">Every submission creates an immutable version and is validated by the frozen Phase 1 validator.</p>{error_summary}
<label for="campaign_name">Campaign name</label><input id="campaign_name" name="campaign_name" maxlength="120" required value="{e(config.get('campaign_name',''))}"{invalid('campaign_name')}>{field_error('campaign_name')}
<label for="business_unit_display">Business unit</label><input id="business_unit_display" value="{e(business_unit)}" disabled>
<label for="discovery_scope">Discovery scope</label><select id="discovery_scope" name="discovery_scope"{invalid('discovery_scope')}><option value="open"{selected('open',config.get('discovery_scope','open'))}>Open discovery</option><option value="filtered"{selected('filtered',config.get('discovery_scope'))}>Filtered / vertical</option></select>{field_error('discovery_scope')}
<label for="verticals">Verticals (comma separated; required for filtered)</label><input id="verticals" name="verticals" maxlength="500" value="{e(list_text('verticals'))}"{invalid('verticals')}>{field_error('verticals')}
<label for="target_prospect_count">Target prospect count</label><input id="target_prospect_count" name="target_prospect_count" type="number" min="1" max="100" required value="{e(config.get('target_prospect_count',20))}"{invalid('target_prospect_count')}>{field_error('target_prospect_count')}
<label for="minimum_qualification_score">Minimum qualification score</label><input id="minimum_qualification_score" name="minimum_qualification_score" type="number" min="0" max="100" step="0.1" required value="{e(config.get('minimum_qualification_score',72 if business_unit=='unreal-media-group' else 78))}"{invalid('minimum_qualification_score')}>{field_error('minimum_qualification_score')}
<label><input name="reengagement_enabled" type="checkbox"{' checked' if config.get('reengagement_enabled') in {True, 'on'} else ''}> Include governed re-engagement review</label>
<label for="cooldown_days">Cooldown days</label><input id="cooldown_days" name="cooldown_days" type="number" min="0" max="3650" required value="{e(config.get('cooldown_days',120 if business_unit=='unreal-media-group' else 180))}"{invalid('cooldown_days')}>{field_error('cooldown_days')}
<label for="maximum_evidence_age_days">Maximum evidence age (days)</label><input id="maximum_evidence_age_days" name="maximum_evidence_age_days" type="number" min="1" max="3650" required value="{e(config.get('maximum_evidence_age_days',180))}"{invalid('maximum_evidence_age_days')}>{field_error('maximum_evidence_age_days')}
<label for="geography">Countries (comma separated)</label><input id="geography" name="geography" maxlength="500" value="{e(geography_value)}">
<label for="rights_territory">Talent rights territory (required for Talent)</label><input id="rights_territory" name="rights_territory" maxlength="500" value="{e(list_text('rights_territory'))}"{invalid('rights_territory')}>{field_error('rights_territory')}
<label for="talent_categories">Talent categories / archetypes (never named talent)</label><input id="talent_categories" name="talent_categories" maxlength="500" value="{e(list_text('talent_categories'))}">
<button type="submit">Create immutable campaign version</button></form>"""
        return page("New campaign" if not family_id else "New campaign version", body, actor=actor, business_unit=business_unit)

    def campaign_detail(self, actor: str, business_unit: str, family_id: str, version: int, status: str = "") -> str:
        item = self.control.repository.get_campaign(actor, family_id, version)
        if item["business_unit"] != business_unit:
            raise MissionControlError(403, "Business-unit access denied.")
        config = item["configuration"]
        key = f"{family_id}-v{version}-{item['configuration_hash'][:12]}"
        body = f"""<dl><dt>Family</dt><dd>{e(family_id)}</dd><dt>Version</dt><dd>{version}</dd><dt>Configuration hash</dt><dd><code>{e(item['configuration_hash'])}</code></dd><dt>Scope</dt><dd>{e(config['discovery_scope'])}</dd><dt>Verticals</dt><dd>{e(', '.join(config['verticals']) or 'Open discovery')}</dd></dl>
<details><summary>Full validated Phase 1 configuration</summary><pre>{e(json.dumps(config,indent=2,sort_keys=True))}</pre></details>
<form method="post" action="/campaigns/{e(family_id)}/{version}/run">{self.hidden(actor,business_unit)}<label for="idempotency_key">Idempotency key</label><input id="idempotency_key" name="idempotency_key" maxlength="100" required value="{e(key)}"><button type="submit">Start fixture dry run</button></form>
<h2>Create a new immutable version</h2>{self.campaign_form(actor,business_unit,config=config,family_id=family_id).split('<main id="main"><h1>New campaign version</h1>',1)[-1].split('</main>',1)[0]}"""
        return page(config["campaign_name"], body, actor=actor, business_unit=business_unit, status=status)

    def runs(self, actor: str, business_unit: str) -> str:
        items = [item for item in self.control.repository.runs(actor) if item["business_unit"] == business_unit]
        query = urlencode({"actor": actor, "business_unit": business_unit})
        rows = "".join(f'<tr><td><a href="/runs/{e(item["run_id"])}?{query}">{e(item["run_id"])}</a></td><td>{e(item["status"])}</td><td>{len(item["output_ids"])}</td><td>${item["estimated_cost_usd"]}</td><td>{e(item["stop_reason"])}</td></tr>' for item in items)
        body = '<p class="notice">No manual runs have been recorded.</p>' if not rows else f'<table><thead><tr><th>Run</th><th>Status</th><th>Outputs</th><th>Cost</th><th>Stop reason</th></tr></thead><tbody>{rows}</tbody></table>'
        return page("Run history", body, actor=actor, business_unit=business_unit)

    def run_detail(self, actor: str, business_unit: str, run_id: str, status: str = "") -> str:
        run = self.control.repository.get_run(actor, run_id)
        if run["business_unit"] != business_unit:
            raise MissionControlError(403, "Business-unit access denied.")
        fields = ["run_id","campaign_family_id","campaign_version","business_unit","initiating_actor","input_schema_version","configuration_hash","skill_name","skill_version","fixture_source_ids","output_ids","started_at","completed_at","status","estimated_cost_usd","errors","stop_reason","idempotency_key","fixture_adapter"]
        body = '<dl>' + ''.join(f'<dt>{e(key.replace("_"," ").title())}</dt><dd>{e(run[key])}</dd>' for key in fields) + '</dl>'
        query = urlencode({"actor": actor, "business_unit": business_unit})
        body += f'<p><a href="/prospects?{query}&amp;queue=new">Review run outputs in prospect queues</a></p>'
        return page(f"Run {run_id}", body, actor=actor, business_unit=business_unit, status=status)

    def prospects(self, actor: str, business_unit: str, queue: str) -> str:
        items = [item for item in self.control.repository.prospects(actor,business_unit) if item["queue"] == queue]
        query_base = {"actor": actor, "business_unit": business_unit}
        nav = ' · '.join(f'<a href="/prospects?{urlencode(query_base)}&amp;queue={name}">{label}</a>' for name,label in [("new","New"),("duplicate_reengagement","Duplicates & re-engagement"),("rejections","Rejections")])
        rows = "".join(f'<tr><td><a href="/prospects/{e(item["prospect_id"])}?{urlencode(query_base)}">{e(item["account_name"])}</a></td><td>{item["score"]}</td><td>{e(item["effective_duplicate_state"])}</td><td>{e(item["effective_rejection"] or "eligible review")}</td></tr>' for item in items)
        body = f'<p>{nav}</p>' + ('<p class="notice">This queue is empty.</p>' if not rows else f'<table><thead><tr><th>Account</th><th>Score</th><th>Identity state</th><th>Disposition</th></tr></thead><tbody>{rows}</tbody></table>')
        return page(f"Prospect queue: {queue.replace('_',' ')}", body, actor=actor, business_unit=business_unit)

    def prospect_detail(self, actor: str, business_unit: str, prospect_id: str, status: str = "") -> str:
        item = self.control.repository.get_prospect(actor,business_unit,prospect_id)
        evidence = "".join(f'<li><span class="tag">{e(entry["freshness"])}</span> {e(entry["source"])} · {e(entry["observed_at"])} · {e(entry["basis"])} · ' + (f'<a href="{e(entry["url"])}" rel="noreferrer">credential-free source</a>' if safe_evidence_url(entry["url"]) else '<span class="warning">unsafe URL omitted</span>') + '</li>' for entry in item["evidence"])
        history = "".join(f'<tr><td>{e(event["event_id"])}</td><td>{e(event["kind"])}</td><td>{e(event["actor"])}</td><td>{e(event["effective_at"])}</td><td>{e(event["supersedes_id"] or "")}</td><td>{e(json.dumps(event["value"],sort_keys=True))}</td></tr>' for event in item["review_history"])
        match_options = ''.join(f'<option value="{e(match)}">{e(match)}</option>' for match in item.get("matched_identity_ids",[]))
        hidden = self.hidden(actor,business_unit)
        supersedes = lambda kind: f'<input type="hidden" name="supersedes_id" value="{e(item["current_review"].get(state_domain(kind), {}).get("event_id", ""))}">'  # noqa: E731
        body = f"""<dl><dt>Global synthetic identity</dt><dd>{e(item['global_identity_id'])}</dd><dt>Account</dt><dd>{e(item['account_name'])} · {e(item['domain'])}</dd><dt>Business unit</dt><dd>{e(item['business_unit'])}</dd><dt>Relationship</dt><dd>{e(item['relationship'])}</dd><dt>Score</dt><dd>{item['score']} · {e(json.dumps(item['score_dimensions'],sort_keys=True))}</dd><dt>Queue</dt><dd>{e(item['queue'])}</dd><dt>Identity classification</dt><dd>{e(item['effective_duplicate_state'])} · source classification {e(item['duplicate_state'])} · matches {e(item.get('matched_identity_ids',[]))}</dd><dt>Identity resolution</dt><dd>{e(item['effective_matched_identity_id'] or 'unresolved')}</dd><dt>Rejection</dt><dd>{e(item['effective_rejection'] or 'none')}</dd><dt>Uncertainty</dt><dd>{e(item['uncertainty'])}</dd><dt>Suppression</dt><dd>{e(item['suppressed'])}</dd><dt>Cooldown</dt><dd>{e(item['cooldown_until'] or 'none')}</dd><dt>Rights</dt><dd>{e(item['rights_state'])}</dd><dt>Brand safety</dt><dd>{e(item['brand_safety_state'])}</dd><dt>Talent archetype</dt><dd>{e(item.get('talent_archetype','not applicable'))}</dd></dl>
<h2>Evidence</h2><ul>{evidence or '<li class="warning">Missing evidence</li>'}</ul>
<h2>Governed review actions</h2><p>Repeating a governed action appends a correction that explicitly supersedes its current event. History is never deleted.</p><div class="grid">
<form class="card" method="post" action="/prospects/{e(prospect_id)}/actions">{hidden}{supersedes('resolve_identity')}<input type="hidden" name="action" value="resolve_identity"><label for="matched_identity_id">Exact synthetic identity match</label><select id="matched_identity_id" name="matched_identity_id">{match_options}</select><button type="submit"{' disabled' if not match_options else ''}>Record identity resolution</button></form>
<form class="card" method="post" action="/prospects/{e(prospect_id)}/actions">{hidden}{supersedes('suppress')}<input type="hidden" name="action" value="suppress"><label for="suppress_reason">Suppression reason</label><input id="suppress_reason" name="reason" maxlength="500" required><button type="submit">Append suppression</button></form>
<form class="card" method="post" action="/prospects/{e(prospect_id)}/actions">{hidden}{supersedes('approve_deeper_research')}<input type="hidden" name="action" value="approve_deeper_research"><p>Approval requires an eligible record and a reviewer different from the proposing actor.</p><button type="submit">Approve for deeper research</button></form>
<form class="card" method="post" action="/prospects/{e(prospect_id)}/actions">{hidden}{supersedes('reject')}<input type="hidden" name="action" value="reject"><label for="reject_reason">Rejection reason</label><input id="reject_reason" name="reason" maxlength="500" required><button type="submit">Append rejection</button></form>
<form class="card" method="post" action="/prospects/{e(prospect_id)}/actions">{hidden}{supersedes('assign')}<input type="hidden" name="action" value="assign"><label for="assignee">Assign fixture reviewer</label><select id="assignee" name="assignee">{''.join(f'<option value="{e(name)}">{e(name)}</option>' for name in ACTOR_SCOPE if business_unit in ACTOR_SCOPE[name])}</select><button type="submit">Append assignment</button></form>
<form class="card" method="post" action="/prospects/{e(prospect_id)}/actions">{hidden}<input type="hidden" name="action" value="note"><label for="note_text">Review note</label><textarea id="note_text" name="text" maxlength="2000" required></textarea><button type="submit">Append note</button></form></div>
<h2>Current governed projection</h2><p>Decision: <strong>{e(item['current_decision'])}</strong> · Effective suppression: <strong>{e(item['effective_suppressed'])}</strong> · Assignment: <strong>{e(item['effective_assignment'] or 'unassigned')}</strong></p>
<h2>Append-only review history</h2>{'<p class="notice">No human review events yet.</p>' if not history else f'<table><thead><tr><th>ID</th><th>Kind</th><th>Actor</th><th>Effective</th><th>Supersedes</th><th>Value</th></tr></thead><tbody>{history}</tbody></table>'}"""
        return page(item["account_name"],body,actor=actor,business_unit=business_unit,status=status)

    def registry(self, actor: str, business_unit: str) -> str:
        registration = self.agent.registration()
        query = urlencode({"actor": actor, "business_unit": business_unit})
        body = f"""<p class="notice">One local agent is registered for manual synthetic execution. Phase 5 may submit one bounded occurrence from an explicitly enabled local weekly schedule. The worker itself has no credentials, scheduler, generic recurring loop, external network, creative, likeness, approval, or outreach capability.</p>
<table><thead><tr><th>Agent</th><th>Version</th><th>Registration state</th><th>Trigger</th><th>Detail</th></tr></thead><tbody>
<tr><td>{e(registration['agent_id'])}</td><td>{e(registration['agent_contract_version'])}</td><td>{e(registration['registration_state'])}</td><td>{e(registration['trigger'])}</td><td><a href="/registry/{e(registration['agent_id'])}?{query}">Capabilities</a></td></tr>
</tbody></table>"""
        return page("Agent registry", body, actor=actor, business_unit=business_unit)

    def registry_detail(self, actor: str, business_unit: str, agent_id: str) -> str:
        if agent_id != AGENT_ID:
            raise MissionControlError(404, "Registered agent not found.")
        registration = self.agent.registration()
        bindings = "".join(
            f'<tr><td>{e(unit)}</td><td>{e(binding["skill_id"])}</td><td>{e(binding["skill_version"])}</td><td><code>{e(binding["skill_integrity_sha256"][:16])}…</code></td></tr>'
            for unit, binding in registration["skill_bindings"].items()
        )
        fields = [
            "agent_id", "agent_contract_version", "worker_runtime_version", "registration_state",
            "input_schema", "output_schema", "trigger", "scheduled_shadow_trigger", "max_concurrency", "timeout_seconds",
            "cost_cap_usd", "max_attempts", "cancellation", "durable_store_adapter",
            "credentials", "scheduler", "recurring_loop", "network", "creative", "likeness", "outreach",
        ]
        body = f"""<p class="notice">Manual, fixture-only, locally registered worker. Business-unit skill routing is server-owned; a client can never select a skill, executable, or version.</p>
<dl>{''.join(f'<dt>{e(key.replace("_", " ").title())}</dt><dd>{e(registration[key])}</dd>' for key in fields)}</dl>
<h2>Server-owned business-unit skill bindings</h2>
<table><thead><tr><th>Business unit</th><th>Skill</th><th>Exact version</th><th>Integrity manifest</th></tr></thead><tbody>{bindings}</tbody></table>
<p>Direct runs start only from a campaign detail page through the manual human form. A separately governed, explicitly enabled Phase 5 schedule may submit one weekly shadow occurrence through the same bounded service.</p>"""
        return page(f"Registered agent {agent_id}", body, actor=actor, business_unit=business_unit)

    def worker_runs(self, actor: str, business_unit: str) -> str:
        items = self.agent.list_runs(actor, business_unit)
        query = urlencode({"actor": actor, "business_unit": business_unit})
        rows = "".join(
            f'<tr><td><a href="/worker-runs/{e(item["run_id"])}?{query}">{e(item["run_id"])}</a></td>'
            f'<td>{e(self._run_state_label(item))}</td><td>{item["attempt_count"]}/{item["max_attempts"]}</td>'
            f'<td>${item["cost_cap_usd"]}</td><td>{e(item["failure_class"] or "none")}</td></tr>'
            for item in items
        )
        body = (
            '<p class="notice">No registered-agent runs exist for this business unit. Start one from a campaign detail page.</p>'
            if not rows
            else f'<table><thead><tr><th>Logical run</th><th>State</th><th>Attempts</th><th>Cost cap</th><th>Failure class</th></tr></thead><tbody>{rows}</tbody></table>'
        )
        return page("Worker runs", body, actor=actor, business_unit=business_unit)

    @staticmethod
    def _durable_results_section(output: dict[str, Any] | None) -> str:
        """Read-only, business-unit-scoped review projection rendered from the
        durable validated result snapshot. It stays inspectable after a process
        restart, unlike the Phase 3 process-local queues."""
        if output is None:
            return ""

        def disposition(item: dict[str, Any]) -> Any:
            if item.get("effective_suppressed") is True:
                return "suppressed"
            decision = item.get("current_decision")
            if decision in {"rejected", "approved_for_deeper_research"}:
                return decision
            return item.get("effective_rejection") or decision or "eligible review"

        rows = "".join(
            f'<tr><td>{e(item.get("prospect_id", ""))}</td><td>{e(item.get("account_name", ""))}</td>'
            f'<td>{e(item.get("domain", ""))}</td><td>{e(item.get("score", ""))}</td>'
            f'<td>{e(item.get("queue", ""))}</td><td>{e(disposition(item))}</td>'
            f'<td>{e(item.get("uncertainty", ""))}</td></tr>'
            for item in output["result_snapshot"]
            if isinstance(item, dict)
        )
        table = (
            '<p class="notice">This run recorded a visible empty result set.</p>'
            if not rows
            else f'<table><thead><tr><th>Result</th><th>Account</th><th>Domain</th><th>Score</th><th>Queue</th><th>Disposition</th><th>Uncertainty</th></tr></thead><tbody>{rows}</tbody></table>'
        )
        return f"""<h2>Durable validated result snapshot</h2>
<p class="notice">Read-only durable review data; it remains inspectable after an application restart. Governed review actions (identity resolution, suppression, deeper-research approval, rejection, assignment, notes) operate on the process-local Phase 3 prospect queue populated by the server process that executed the run; after a restart those actions are unavailable for this run's results, and this snapshot remains the review record.</p>
{table}"""

    @staticmethod
    def _run_state_label(run: dict[str, Any]) -> str:
        if run["state"] == "succeeded" and run.get("review_task_id"):
            return "succeeded · review pending"
        if run["state"] in {"failed_retryable", "timed_out"} and run["attempt_count"] >= run["max_attempts"]:
            return f'{run["state"]} · retry budget exhausted'
        return run["state"]

    def worker_run_detail(self, actor: str, business_unit: str, run_id: str, status: str = "") -> str:
        run = self.agent.run_detail(actor, run_id)
        if run["business_unit"] != business_unit:
            raise MissionControlError(403, "Business-unit access denied.")
        query = urlencode({"actor": actor, "business_unit": business_unit})
        fields = [
            "run_id", "agent_id", "agent_version", "campaign_family_id", "campaign_version",
            "business_unit", "initiating_actor", "skill_id", "skill_version", "skill_integrity",
            "configuration_hash", "idempotency_key", "state", "attempt_count", "max_attempts",
            "retry_budget_remaining", "timeout_seconds", "cost_cap_usd", "actual_cost_usd",
            "cancel_requested", "created_at", "started_at", "completed_at", "failure_class",
            "retryable", "remediation",
        ]
        body = f'<p><span class="tag">{e(self._run_state_label(run))}</span></p><dl>' + "".join(
            f'<dt>{e(key.replace("_", " ").title())}</dt><dd>{e(run[key] if run[key] is not None else "none")}</dd>'
            for key in fields
        ) + "</dl>"
        attempts = "".join(
            f'<tr><td>{item["attempt_number"]}</td><td>{e(item["started_at"])}</td><td>{e(item["completed_at"] or "in progress")}</td>'
            f'<td>{e(item["terminal_state"] or "running")}</td><td>{e(item["outcome"] or "pending")}</td>'
            f'<td>{e(item["worker_version"])}</td><td>{e(item["estimated_cost_usd"] if item["estimated_cost_usd"] is not None else "none")}</td></tr>'
            for item in run["attempts"]
        )
        body += "<h2>Append-only attempt history</h2>" + (
            '<p class="notice">No attempt has started.</p>'
            if not attempts
            else f'<table><thead><tr><th>#</th><th>Started</th><th>Completed</th><th>Terminal state</th><th>Outcome</th><th>Worker version</th><th>Cost</th></tr></thead><tbody>{attempts}</tbody></table>'
        )
        output = run["output"]
        if output:
            body += f"""<h2>Output manifest</h2><dl>
<dt>Output Id</dt><dd>{e(output['output_id'])}</dd>
<dt>Output Schema</dt><dd>{e(output['output_schema'])}</dd>
<dt>Content Hash</dt><dd><code>{e(output['content_hash'])}</code></dd>
<dt>Byte Length</dt><dd>{output['byte_length']}</dd>
<dt>Fixture Source Ids</dt><dd>{e(', '.join(output['fixture_source_ids']))}</dd>
<dt>Result Ids</dt><dd>{e(', '.join(output['result_ids']) or 'none (visible empty result)')}</dd>
<dt>Estimated Cost Usd</dt><dd>{output['estimated_cost_usd']}</dd>
<dt>Errors</dt><dd>{e('; '.join(output['errors']) or 'none')}</dd>
<dt>Stop Reason</dt><dd>{e(output['stop_reason'])}</dd>
</dl>{self._durable_results_section(output)}<p><a href="/prospects?{query}&amp;queue=new">Open the process-local prospect queues (populated only by runs executed in this server process)</a></p>"""
        if run["review_task"]:
            body += f'<h2>Human review task</h2><p><a href="/review-tasks/{e(run["review_task"]["task_id"])}?{query}">{e(run["review_task"]["task_id"])}</a> · state: {e(run["review_task"]["state"])} · the worker cannot approve or complete it.</p>'
        hidden = self.hidden(actor, business_unit)
        if run["cancel_allowed"]:
            body += f'<form method="post" action="/worker-runs/{e(run_id)}/cancel">{hidden}<button type="submit">Cancel this run</button></form>'
        if run["retry_allowed"]:
            body += f'<form method="post" action="/worker-runs/{e(run_id)}/retry">{hidden}<button type="submit">Retry manually (attempt {run["attempt_count"] + 1} of {run["max_attempts"]})</button></form>'
        elif run["state"] in {"failed_retryable", "timed_out"}:
            if run["retry_block_reason"] == "scheduled_run":
                body += '<p class="warning">Scheduled shadow runs are not manually retryable; the linked occurrence owns final settlement.</p>'
            else:
                body += '<p class="warning">The retry budget is exhausted; no further attempts are allowed.</p>'
        audits = "".join(
            f'<tr><td>{e(item["audit_id"])}</td><td>{e(item["event_type"])}</td><td>{e(item["actor"])}</td><td>{e(item["safe_status"])}</td><td>{e(item["recorded_at"])}</td></tr>'
            for item in run["audit_events"]
        )
        body += "<h2>Bounded audit history</h2>" + (
            '<p class="notice">No audit events.</p>'
            if not audits
            else f'<table><thead><tr><th>ID</th><th>Event</th><th>Actor</th><th>Safe status</th><th>Recorded</th></tr></thead><tbody>{audits}</tbody></table>'
        )
        return page(f"Worker run {run_id}", body, actor=actor, business_unit=business_unit, status=status)

    def review_tasks(self, actor: str, business_unit: str) -> str:
        items = self.agent.review_tasks(actor, business_unit)
        query = urlencode({"actor": actor, "business_unit": business_unit})
        rows = "".join(
            f'<tr><td><a href="/review-tasks/{e(item["task_id"])}?{query}">{e(item["task_id"])}</a></td>'
            f'<td>{e(item["run_id"])}</td><td>{e(item["state"])}</td><td>{e(item["created_at"])}</td></tr>'
            for item in items
        )
        body = (
            '<p class="notice">No human review tasks exist for this business unit.</p>'
            if not rows
            else f'<table><thead><tr><th>Task</th><th>Logical run</th><th>State</th><th>Created</th></tr></thead><tbody>{rows}</tbody></table>'
        )
        return page("Human review tasks", body, actor=actor, business_unit=business_unit)

    def review_task_detail(self, actor: str, business_unit: str, task_id: str) -> str:
        task = self.agent.get_review_task(actor, task_id)
        if task["business_unit"] != business_unit:
            raise MissionControlError(403, "Business-unit access denied.")
        output = self.agent.run_detail(actor, task["run_id"])["output"]
        query = urlencode({"actor": actor, "business_unit": business_unit})
        body = f"""<dl>
<dt>Task Id</dt><dd>{e(task['task_id'])}</dd>
<dt>Logical Run</dt><dd><a href="/worker-runs/{e(task['run_id'])}?{query}">{e(task['run_id'])}</a></dd>
<dt>Output Reference</dt><dd>{e(task['output_id'])}</dd>
<dt>Business Unit</dt><dd>{e(task['business_unit'])}</dd>
<dt>State</dt><dd>{e(task['state'])}</dd>
<dt>Allowed Human Reviewers</dt><dd>{e(', '.join(task['allowed_reviewers']))}</dd>
<dt>Created</dt><dd>{e(task['created_at'])}</dd>
</dl>
<p class="notice">The worker created this task and cannot approve, complete, or impersonate the human reviewer. No automatic approval or standing permission exists.</p>
{self._durable_results_section(output)}
<p><a href="/prospects?{query}&amp;queue=new">Open the process-local prospect queues (populated only by runs executed in this server process)</a></p>"""
        return page(f"Review task {task_id}", body, actor=actor, business_unit=business_unit)

    def shadow_schedules(self, actor: str, business_unit: str) -> str:
        items = self.shadow.schedules(actor, business_unit)
        query = urlencode({"actor": actor, "business_unit": business_unit})
        rows = "".join(
            f'<tr><td>{e(item["name"])}</td><td>{e(item["state"])}</td>'
            f'<td>{e(item["next_due_at"] or "Not enabled")}</td><td>{e(item["health"])}</td>'
            f'<td>{e("Not available" if item.get("duplicate_rate") is None else item["duplicate_rate"])}</td>'
            f'<td><a href="/shadow-schedules/{e(item["schedule_id"])}?{query}">Inspect</a></td></tr>'
            for item in items
        )
        body = f"""<p class="notice">Phase 5 schedules are disabled by default and remain local, synthetic,
fixture-only, weekly UTC, zero-cost, and shadow-only. Creating a schedule never enables it.</p>"""
        if actor == SCHEDULE_MANAGER:
            body += f'<p><a href="/shadow-schedules/new?{query}">Configure a disabled shadow schedule</a></p>'
        else:
            body += '<p class="notice">This is read-only schedule state. Only Noah may configure or control a shadow schedule.</p>'
        body += (
            '<p class="notice">No shadow schedules exist for this business unit.</p>'
            if not rows
            else '<table><thead><tr><th>Schedule</th><th>State</th><th>Next UTC due</th><th>Health</th><th>Duplicate rate</th><th>View</th></tr></thead>'
                 f'<tbody>{rows}</tbody></table>'
        )
        alerts = self.shadow.alerts(actor, business_unit)
        if alerts:
            alert_rows = "".join(
                f'<tr><td>{e(item["created_at"])}</td><td>{e(item["failure_class"])}</td><td>{e(item["safe_message"])}</td></tr>'
                for item in alerts
            )
            body += f'<h2>Local alerts</h2><table><thead><tr><th>Time</th><th>Class</th><th>Safe message</th></tr></thead><tbody>{alert_rows}</tbody></table>'
        else:
            body += '<h2>Local alerts</h2><p class="notice">No local shadow-loop alerts exist.</p>'
        return page("Shadow schedules", body, actor=actor, business_unit=business_unit)

    def shadow_schedule_form(self, actor: str, business_unit: str) -> str:
        self.shadow.schedules(actor, business_unit)
        if actor != SCHEDULE_MANAGER:
            return page(
                "Shadow schedule access",
                '<p class="notice">This is read-only schedule state. Only Noah may configure or control a shadow schedule.</p>',
                actor=actor,
                business_unit=business_unit,
            )
        campaigns = [
            item for item in self.control.repository.campaigns(actor)
            if item["business_unit"] == business_unit
        ]
        choices = ", ".join(f'{item["family_id"]}:{item["version"]}' for item in campaigns)
        body = f"""<p class="notice">Configuration is immutable and disabled by default. Use approved campaign
versions from this business unit. The cadence is one bounded weekly UTC boundary, not generic cron.</p>
<form method="post" action="/shadow-schedules">
{self.hidden(actor, business_unit)}
<label for="schedule_name">Schedule name</label><input id="schedule_name" name="name" maxlength="120" required>
<label for="campaign_refs">Campaign rotation (comma-separated family_id:version)</label>
<input id="campaign_refs" name="campaign_refs" maxlength="1200" required aria-describedby="campaign_choices">
<p id="campaign_choices">Available immutable versions: {e(choices or 'None. Create a campaign first.')}</p>
<label for="weekday">UTC weekday (Monday 0 through Sunday 6)</label><input id="weekday" name="weekday" type="number" min="0" max="6" required value="0">
<label for="utc_hour">UTC hour</label><input id="utc_hour" name="utc_hour" type="number" min="0" max="23" required value="9">
<label for="utc_minute">UTC minute</label><input id="utc_minute" name="utc_minute" type="number" min="0" max="59" required value="0">
<label for="prospect_cap">Prospect cap</label><input id="prospect_cap" name="prospect_cap" type="number" min="1" max="15" required value="5">
<label for="open_discovery_every">Open-discovery week interval (0 disables)</label><input id="open_discovery_every" name="open_discovery_every" type="number" min="0" max="52" required value="0">
<button type="submit">Create disabled shadow schedule</button></form>"""
        return page("Configure shadow schedule", body, actor=actor, business_unit=business_unit)

    def shadow_schedule_detail(
        self, actor: str, business_unit: str, schedule_id: str, status: str = ""
    ) -> str:
        item = self.shadow.schedule_detail(actor, schedule_id)
        if item["business_unit"] != business_unit:
            raise MissionControlError(403, "Business-unit access denied.")
        query = urlencode({"actor": actor, "business_unit": business_unit})
        if actor == SCHEDULE_MANAGER:
            allowed = {
                "disabled": ("enable",),
                "enabled": ("pause", "disable"),
                "paused": ("resume", "disable"),
            }[item["state"]]
            controls = "".join(
                f'<form method="post" action="/shadow-schedules/{e(schedule_id)}/{action}">{self.hidden(actor, business_unit)}'
                f'<input type="hidden" name="row_version" value="{item["row_version"]}"><button type="submit">{e(action.title())} schedule</button></form>'
                for action in allowed
            )
        else:
            controls = '<p class="notice">This is read-only schedule state. Only Noah may control a shadow schedule.</p>'
        campaign_rows = "".join(
            f'<tr><td>{row["position"]}</td><td>{e(row["campaign_family_id"])}</td><td>{row["campaign_version"]}</td><td>{e(row["discovery_scope"])}</td></tr>'
            for row in item["campaigns"]
        )
        occurrence_rows = "".join(
            f'<tr><td>{e(row["scheduled_for"])}</td><td>{e(row["state"])}</td><td>{e(row["worker_run_id"] or "None")}</td><td>{e(row["stop_reason"] or "None")}</td><td>{e("Not available" if row["duplicate_rate"] is None else row["duplicate_rate"])}</td></tr>'
            for row in item["occurrences"]
        )
        body = f"""<p class="notice">Synthetic local shadow schedule. It can discover fixture candidates only;
every successful output remains pending human review. It cannot approve, enrich, generate, contact, or send.</p>
<dl><dt>Schedule</dt><dd>{e(item['name'])}</dd><dt>Business unit</dt><dd>{e(item['business_unit'])}</dd>
<dt>State</dt><dd>{e(item['state'])}</dd><dt>UTC cadence</dt><dd>weekday {item['weekday']} at {item['utc_hour']:02d}:{item['utc_minute']:02d} UTC</dd>
<dt>Next due</dt><dd>{e(item['next_due_at'] or 'Not enabled')}</dd><dt>Health</dt><dd>{e(item['health'])}</dd>
<dt>Last stop reason</dt><dd>{e(item['last_stop_reason'] or 'None')}</dd><dt>Prospect cap</dt><dd>{item['prospect_cap']}</dd>
<dt>Cost cap</dt><dd>$0 exactly</dd><dt>Duplicate rate</dt><dd>{e('Not available' if item.get('duplicate_rate') is None else item['duplicate_rate'])}</dd></dl>
<h2>Controls</h2>{controls}
<p class="notice">Pause or disable prevents an unclaimed occurrence. An occurrence whose claim already committed finishes under its immutable snapshot and remains shadow-only.</p>
<h2>Immutable campaign rotation</h2><table><thead><tr><th>Position</th><th>Family</th><th>Version</th><th>Scope</th></tr></thead><tbody>{campaign_rows}</tbody></table>
<h2>Occurrences</h2>"""
        body += (
            f'<table><thead><tr><th>Scheduled UTC</th><th>State</th><th>Run</th><th>Stop reason</th><th>Duplicate rate</th></tr></thead><tbody>{occurrence_rows}</tbody></table>'
            if occurrence_rows else '<p class="notice">No occurrence has been claimed.</p>'
        )
        body += f'<p><a href="/shadow-schedules?{query}">Back to shadow schedules and local alerts</a></p>'
        return page(f"Shadow schedule {schedule_id}", body, actor=actor, business_unit=business_unit, status=status)


def make_handler(app: WebApplication) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "ProspectingMissionControl/3"
        sys_version = ""

        def _validate_envelope(self) -> None:
            if len(self.path) > 4_096:
                raise MissionControlError(400, "Request target exceeds the local safety limit.")
            host = self.headers.get("Host", "").split(":", 1)[0].casefold()
            if host not in {"127.0.0.1", "localhost"}:
                raise MissionControlError(403, "Only a loopback Host is accepted.")

        def _send(self, status: int, body: str) -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; img-src 'none'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(data)

        def _error(
            self,
            exc: MissionControlError,
            context: tuple[str, str] | None = None,
        ) -> None:
            actor, unit = context or ("noah", "unreal-media-group")
            if context is None:
                try:
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True, max_num_fields=MAX_FIELDS)
                    actor, unit = app.context(query)
                except Exception:
                    pass
            self._send(exc.status, page(HTTPStatus(exc.status).phrase, f'<p class="error" role="alert">{e(exc.message)}</p>', actor=actor, business_unit=unit))

        def do_GET(self) -> None:
            try:
                self._validate_envelope()
                parsed = urlsplit(self.path)
                query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=MAX_FIELDS)
                status, body = app.get(parsed.path, query)
                self._send(status, body)
            except MissionControlError as exc:
                self._error(exc)
            except (ValueError, UnicodeError):
                self._error(MissionControlError(400, "Malformed request."))
            except Exception:
                self._error(MissionControlError(500, "The local review request failed safely."))

        def do_POST(self) -> None:
            error_context: tuple[str, str] | None = None
            try:
                self._validate_envelope()
                if self.headers.get_content_type() != "application/x-www-form-urlencoded":
                    raise MissionControlError(400, "Mutating forms require application/x-www-form-urlencoded content.")
                raw_length = self.headers.get("Content-Length")
                if raw_length is None:
                    raise MissionControlError(400, "Content-Length is required.")
                length = int(raw_length)
                if length < 0 or length > MAX_BODY:
                    raise MissionControlError(400, "Request body exceeds the local safety limit.")
                body = self.rfile.read(length).decode("utf-8", errors="strict")
                parsed_form = parse_qs(body, keep_blank_values=True, max_num_fields=MAX_FIELDS, strict_parsing=True)
                if any(len(values) != 1 for values in parsed_form.values()):
                    raise MissionControlError(400, "Repeated form fields are not allowed.")
                form = {key: values[0] for key, values in parsed_form.items()}
                try:
                    error_context = app.context({
                        "actor": [form.get("actor", "")],
                        "business_unit": [form.get("business_unit", "")],
                    })
                except MissionControlError:
                    pass
                status, output = app.post(urlsplit(self.path).path, form)
                self._send(status, output)
            except (ValueError, UnicodeError):
                self._error(MissionControlError(400, "Malformed form submission."), error_context)
            except MissionControlError as exc:
                self._error(exc, error_context)
            except Exception:
                self._error(
                    MissionControlError(500, "The governed action failed without a partial result."),
                    error_context,
                )

        def do_PUT(self) -> None: self._error(MissionControlError(405, "HTTP method not allowed."))
        def do_DELETE(self) -> None: self._error(MissionControlError(405, "HTTP method not allowed."))
        def do_PATCH(self) -> None: self._error(MissionControlError(405, "HTTP method not allowed."))
        def do_HEAD(self) -> None: self._error(MissionControlError(405, "HTTP method not allowed."))
        def do_OPTIONS(self) -> None: self._error(MissionControlError(405, "HTTP method not allowed."))

        def log_message(self, format: str, *args: Any) -> None:
            # Deliberately omit paths, query values, form bodies, and fixture content.
            print(f"mission-control status={args[1] if len(args) > 1 else 'unknown'}")

    return Handler


class LoopbackServer(ThreadingHTTPServer):
    """Loopback-only server with one bounded thread per request.

    Threads exist so a human can inspect or cancel a running bounded attempt;
    daemon_threads stays False so server_close joins every request thread.
    The separately owned Phase 5 weekly scheduler is also non-daemon and is
    explicitly stopped and joined by run_server.
    """

    daemon_threads = False


def build_server(app: WebApplication | None = None, port: int = 8765) -> HTTPServer:
    return LoopbackServer(("127.0.0.1", port), make_handler(app or WebApplication()))


def run_server() -> None:
    parser = argparse.ArgumentParser(description="Run synthetic Prospecting Mission Control on loopback only.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--state-path",
        type=Path,
        default=None,
        help="Operator-selected local SQLite state file for durable worker runs"
        " (default: the gitignored apps/prospecting-mission-control/local_state directory).",
    )
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise SystemExit("Port must be from 1024 to 65535.")
    app = WebApplication(state_path=args.state_path)
    server = build_server(app, port=args.port)
    scheduler = ShadowScheduler(app.shadow)
    scheduler.start()
    print(f"Synthetic Prospecting Mission Control: http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.stop()
        scheduler.join(timeout=5)
        server.server_close()
        if scheduler.is_alive():
            raise RuntimeError("The local shadow scheduler did not stop cleanly.")


if __name__ == "__main__":
    run_server()

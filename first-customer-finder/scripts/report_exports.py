"""Native Markdown and spreadsheet-safe CSV exports."""

import csv
import io
import re
from urllib.parse import quote

from prospect_data import public_url


DEMO_NOTICE = "FICTIONAL DEMO — invented prospects and evidence. Not live customer research."


def md(value):
    text = str(value if value is not None else "")
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"([\\`*_{}\[\]()|#!])", r"\\\1", text)
    return " ".join(text.splitlines())


def link(label, url):
    try:
        safe = public_url(url)
    except ValueError:
        return md(label) + " (no verified link)"
    return f"[{md(label)}]({quote(safe, safe=':/?=&%#@+;,~.-_')})"


def build_markdown(data):
    prospects = data.get("prospects", [])
    lines = [f"# {md(data.get('title', 'First Customer Finder'))}", ""]
    if data.get("demo"):
        lines += [f"> **{DEMO_NOTICE}**", ""]
    if data.get("legacy_warning"):
        lines += [f"> {md(data['legacy_warning'])}", ""]
    lines += [f"{md(data.get('product'))} · {md(data.get('generated_at'))}", "",
              f"**{len(prospects)} potential customers · No outreach sent**", "",
              md(data.get("verdict")), "", "## Search brief", "",
              f"- **Target:** {md(data.get('target_customer'))}",
              f"- **Scope:** {md(data.get('search_scope'))}",
              "- Scores prioritize research; they are not purchase probabilities.", ""]
    history = data.get("history_summary")
    if history:
        excluded = history["excluded"]
        lines += ["## This round", "",
                  f"Previously seen excluded: {excluded['seen']} · Rejected: {excluded['rejected']} · Already contacted/outcome recorded: {excluded['contacted']}", ""]
        for kind in ("prefer", "avoid"):
            if history["profile"][kind]:
                lines += [f"**{kind.title()}:** {md('; '.join(history['profile'][kind]))}", ""]
    if prospects:
        top = prospects[0]
        lines += ["## Start here", "", f"**{md(top.get('name'))} — {top.get('score', 0)}/100**", "",
                  md(top.get("why_now")), "", f"**Next step:** {md(top.get('next_step', 'Verify the source and contact route.'))}", "",
                  "## Shortlist", "", "| Rank | Prospect | Score | Target role | Contact route |",
                  "| --- | --- | ---: | --- | --- |"]
        for i, p in enumerate(prospects, 1):
            route = p.get("contact_route", {})
            route_label = link(route.get("label", "Open route"), route.get("url")) if route.get("status") == "verified" else "No verified route"
            lines.append(f"| P{i} | {md(p.get('name'))} | {p.get('score', 0)} | {md(p.get('target_role', 'Not verified'))} | {route_label} |")
        lines.append("")
    else:
        lines += ["## No eligible prospects this round", "", "No placeholders were added. Review the limits before changing the search scope.", ""]
    for i, p in enumerate(prospects, 1):
        route = p.get("contact_route", {})
        lines += [f"## P{i} · {md(p.get('name'))}", "",
                  f"**{p.get('score', 0)}/100 · {md(p.get('stage'))} · {md(p.get('history_label', 'History not used'))}**", "",
                  f"Stable ID: `{p.get('id', 'legacy')}`", "",
                  f"**Public signal:** {md(p.get('pain_signal'))}", "",
                  f"**Observed evidence:** {md(p.get('evidence'))}", "",
                  f"**Source:** {link(p.get('source_title', 'Original source'), p.get('source_url'))} · Published: {md(p.get('signal_date') or 'Unknown')} · Checked: {md(p.get('checked_at') or 'Not recorded')}", "",
                  f"**Why it fits:** {md(p.get('why_fit'))}", "",
                  f"**Why now:** {md(p.get('why_now'))}", "",
                  f"**Who:** {md(p.get('target_role', 'Not verified'))} ({md(p.get('role_basis', 'not recorded'))})", ""]
        if route.get("status") == "verified":
            lines += [f"**Where:** {link(route.get('label', 'Contact route'), route.get('url'))}", "",
                      f"Route evidence: {link('Supporting public page', route.get('source_url'))} · Checked: {md(route.get('checked_at'))}", ""]
        else:
            lines += ["**Where:** No suitable public contact route verified.", ""]
        lines += [md(route.get("note")), "", f"**Next step:** {md(p.get('next_step'))}", "",
                  f"**CTA:** {md(p.get('cta'))}", "", "### Draft — not sent", "",
                  f"> {md(p.get('opener'))}", "",
                  f"**Check before contacting:** {md(p.get('caution'))}", ""]
        if p.get("dimensions"):
            lines += ["Score breakdown: " + " · ".join(f"{md(k.replace('_', ' '))} {v}/5" for k, v in p["dimensions"].items()), ""]
        for source in p.get("additional_sources", []):
            lines += [f"- {link(source.get('note', 'Supporting evidence'), source.get('url'))}"]
        lines.append("")
    if data.get("patterns"):
        lines += ["## Recurring patterns", ""]
        for pattern in data["patterns"]:
            lines += [f"- **{md(pattern.get('title'))}** ({md(pattern.get('count'))}): {md(pattern.get('insight'))}"]
        lines.append("")
    plan = data.get("outreach_plan", {})
    if plan:
        lines += ["## Seven-day manual plan", ""]
        for key, label in (("angle", "Approach"), ("first_step", "First step"), ("follow_up", "Follow-up"), ("success", "Validation target, not a forecast")):
            lines += [f"- **{label}:** {md(plan.get(key))}"]
        lines.append("")
    lines += ["## Limits", "", "- These are potential customers inferred from public signals, not confirmed buyers.",
              "- A public contact route is not consent to receive promotion."]
    lines += [f"- {md(value)}" for value in data.get("limits", [])]
    lines += ["", "## Refine the next round", "", 'Reply with the ranks from this report, for example: “P1 fits; P2 does not because …”. State any general preference explicitly.', "",
              "History and status changes stay local. Feedback does not train a model or send messages.", ""]
    return "\n".join(lines)


CSV_FIELDS = ["record_type", "demo", "id", "name", "entity_url", "score", "stage", "target_role", "role_basis",
              "pain_signal", "source_url", "signal_date", "checked_at", "contact_status", "contact_url",
              "contact_source_url", "contact_note", "next_step", "cta", "opener", "caution", "status", "feedback"]


def csv_cell(value):
    value = str(value if value is not None else "")
    # Spreadsheet applications may execute formulas even in quoted CSV fields.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def build_csv(data):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS)
    writer.writeheader()
    if data.get("demo"):
        writer.writerow({"record_type": "notice", "demo": "true", "name": DEMO_NOTICE})
    for p in data.get("prospects", []):
        row = {key: p.get(key, "") for key in CSV_FIELDS}
        route = p.get("contact_route", {})
        row.update(record_type="prospect", demo=str(data.get("demo", False)).lower(),
                   contact_status=route.get("status", "not_verified"), contact_url=route.get("url", ""),
                   contact_source_url=route.get("source_url", ""), contact_note=route.get("note", ""))
        writer.writerow({key: csv_cell(value) for key, value in row.items()})
    return buffer.getvalue()

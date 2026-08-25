#!/usr/bin/env python3
"""Render validated Phase 1 run reports to escaped Markdown or HTML."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path
from typing import Any

from common import ValidationError, load_json, require_http_url, require_object
from validate_results import validate_run_report


def md(value: Any) -> str:
    return re.sub(r"([\\`*_[\]<>|])", r"\\\1", str(value if value is not None else "")).replace("\n", " ")


def _counts(report: dict[str, Any]) -> list[tuple[str, Any]]:
    summary = report["summary"]
    return [
        ("Raw candidates", summary["raw_candidate_count"]),
        ("New unique prospects", summary["new_unique_prospects"]),
        ("Duplicates", summary["duplicates"]),
        ("Re-engagement prospects", summary["reengagement_prospects"]),
        ("Rejections", summary["rejections"]),
        ("Qualified shortlist", summary["qualified_shortlist"]),
    ]


def render_markdown(report: dict[str, Any], *, base_dir: Path | None = None) -> str:
    validate_run_report(report, base_dir=base_dir)
    campaign = report["campaign"]
    lines = [f"# {md(campaign['campaign_name'])}", "", "Phase 6 operational finder report. No creative was generated and no outreach was sent.", "", "## Campaign scope", ""]
    lines.extend([f"- Business unit: {md(campaign['business_unit'])}", f"- Discovery: {md(campaign['discovery_scope'])}", f"- Verticals: {md(', '.join(campaign.get('verticals', [])) or 'open discovery')}"])
    if campaign.get("opportunity_filter"):
        opportunity_filter = campaign["opportunity_filter"]
        lines.extend([f"- Opportunity include-any: {md(', '.join(opportunity_filter['include_any']))}", f"- Opportunity exclusions: {md(', '.join(opportunity_filter['exclude']) or 'none')}"])
    if campaign["business_unit"] == "unreal-talent":
        lines.extend([f"- Buyer types: {md(', '.join(campaign['buyer_types']))}", f"- Talent categories: {md(', '.join(campaign.get('talent_categories', [])) or 'open')}", f"- Rights territory: {md(', '.join(campaign['rights_territory']))}"])
    lines.extend(["", "## Search assumptions", ""] + [f"- {md(value)}" for value in report["search_assumptions"]])
    lines.extend(["", "## Run summary", ""] + [f"- {label}: {value}" for label, value in _counts(report)])
    lines.extend(["", "## Qualified and reviewed results", ""])
    for result in report["results"]:
        decision = result["duplicate_decision"]
        lines.extend([f"### {md(result['company_name'])}", "", f"- Identity: `{md(result['identity']['canonical_domain'])}`", f"- Decision: `{md(decision['status'])}`", f"- Score: {result['score_snapshot']['total']}/100", f"- Qualification: {md(result['reason_for_qualification'])}", f"- Uncertainty: {md(result['important_uncertainty'])}", f"- Next action: {md(result['recommended_next_action'])}", "", "Score breakdown:", ""])
        if result["business_unit"] == "unreal-talent":
            lines.extend([f"- Buyer path: {md(result['recommended_buyer_path'])}", f"- Talent mode: {md(result['talent_recommendation_type'])}", f"- Talent archetype: {md(result.get('talent_archetype') or 'none')}", f"- Named talent: {md(result.get('named_talent') or 'none')}", f"- Rights territory: {md(', '.join(result['rights_territory']))}", f"- Rights status: {md(result['rights_status'])}", f"- Brand-safety flags: {md(', '.join(result['brand_safety_flags']) or 'none')}", ""])
        lines.extend([f"- {md(key)}: {value}/5" for key, value in result["score_snapshot"]["dimensions"].items()])
        lines.extend(["", "Evidence:", ""])
        for signal in result["signals"]:
            url = require_http_url(signal["source_url"]).replace("(", "%28").replace(")", "%29")
            lines.append(f"- [{md(signal['summary'])}]({url}) — `{md(signal['basis'])}`; date: {md(signal.get('source_date') or 'unavailable')}")
        if result.get("opportunity_matches"):
            lines.extend(["", "Opportunity matches:", ""])
            for match in result["opportunity_matches"]:
                lines.append(f"- `{md(match['kind'])}` — `{md(match['basis'])}`; {md(match['reason'])}")
        if result["rejection_decision"]["reasons"]:
            lines.extend(["", "Rejection reasons:", ""] + [f"- {md(reason)}" for reason in result["rejection_decision"]["reasons"]])
        lines.append("")
    lines.extend(["## Limitations", ""] + [f"- {md(value)}" for value in report["limitations"]])
    lines.extend(["", "## Validation errors", ""] + ([f"- {md(value)}" for value in report["validation_errors"]] or ["- None"] ))
    lines.extend(["", "## Future creative-handoff readiness", "", md(report["future_creative_handoff_readiness"]), ""])
    return "\n".join(lines)


def render_html(report: dict[str, Any], *, base_dir: Path | None = None) -> str:
    validate_run_report(report, base_dir=base_dir)
    campaign = report["campaign"]
    esc = lambda value: html.escape(str(value if value is not None else ""), quote=True)
    count_cards = "".join(f"<div><dt>{esc(label)}</dt><dd>{esc(value)}</dd></div>" for label, value in _counts(report))
    result_cards = []
    for result in report["results"]:
        signals = "".join(f'<li><a href="{esc(require_http_url(signal["source_url"]))}" target="_blank" rel="noreferrer noopener">{esc(signal["summary"])}</a><span>{esc(signal["basis"])} · {esc(signal.get("source_date") or "date unavailable")}</span></li>' for signal in result["signals"])
        dimensions = "".join(f"<li>{esc(key)}: {esc(value)}/5</li>" for key, value in result["score_snapshot"]["dimensions"].items())
        rejection = "".join(f"<li>{esc(reason)}</li>" for reason in result["rejection_decision"]["reasons"])
        opportunities = "".join(f'<li><b>{esc(match["kind"])}</b><span>{esc(match["basis"])} · {esc(match["reason"])}</span></li>' for match in result.get("opportunity_matches", []))
        talent = ""
        if result["business_unit"] == "unreal-talent":
            talent = f'<p><b>Buyer path:</b> {esc(result["recommended_buyer_path"])}</p><p><b>Talent mode:</b> {esc(result["talent_recommendation_type"])} · {esc(result.get("talent_archetype") or result.get("named_talent") or "none")}</p><p><b>Rights:</b> {esc(", ".join(result["rights_territory"]))} · {esc(result["rights_status"])}</p><p><b>Brand-safety flags:</b> {esc(", ".join(result["brand_safety_flags"]) or "none")}</p>'
        result_cards.append(f'<article><header><div><p class="eyebrow">{esc(result["duplicate_decision"]["status"])}</p><h2>{esc(result["company_name"])}</h2><code>{esc(result["identity"]["canonical_domain"])}</code></div><strong>{esc(result["score_snapshot"]["total"])}/100</strong></header><p>{esc(result["reason_for_qualification"])}</p><p><b>Uncertainty:</b> {esc(result["important_uncertainty"])}</p><p><b>Next:</b> {esc(result["recommended_next_action"])}</p>{talent}<details><summary>Evidence, score, and rejection audit</summary><ul>{signals}</ul>{f"<h3>Opportunity matches</h3><ul>{opportunities}</ul>" if opportunities else ""}<ul>{dimensions}</ul><ul>{rejection or "<li>No rejection reasons</li>"}</ul></details></article>')
    limitations = "".join(f"<li>{esc(value)}</li>" for value in report["limitations"])
    errors = "".join(f"<li>{esc(value)}</li>" for value in report["validation_errors"]) or "<li>None</li>"
    scope = f'{esc(campaign["discovery_scope"])} discovery; verticals: {esc(", ".join(campaign.get("verticals", [])) or "open")}'
    if campaign["business_unit"] == "unreal-talent":
        scope += f'; buyers: {esc(", ".join(campaign["buyer_types"]))}; rights: {esc(", ".join(campaign["rights_territory"]))}'
    elif campaign.get("opportunity_filter"):
        opportunity_filter = campaign["opportunity_filter"]
        scope += f'; opportunity include-any: {esc(", ".join(opportunity_filter["include_any"]))}; exclusions: {esc(", ".join(opportunity_filter["exclude"]) or "none")}'
    assumptions = "".join(f"<li>{esc(value)}</li>" for value in report["search_assumptions"])
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(campaign["campaign_name"])}</title><style>:root{{--bg:#0b0c10;--panel:#151820;--ink:#f6f2e9;--muted:#aab2bf;--accent:#c9ff62}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,sans-serif}}main{{width:min(1080px,calc(100% - 32px));margin:auto;padding:48px 0}}h1{{font-size:clamp(2.4rem,7vw,5rem);line-height:.95}}.lede,.eyebrow,dt,span{{color:var(--muted)}}dl{{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#333}}dl div,article,section{{background:var(--panel);padding:20px}}dd{{font-size:2rem;margin:4px 0}}article{{margin:16px 0;border:1px solid #333;border-radius:14px}}article header{{display:flex;justify-content:space-between;gap:20px}}article header>strong{{color:var(--accent);font-size:1.7rem}}a{{color:var(--accent);word-break:break-all}}span{{display:block;font-size:.85rem}}summary{{cursor:pointer;color:var(--accent)}}@media(max-width:700px){{dl{{grid-template-columns:1fr 1fr}}}}@media print{{body{{background:white;color:black}}article,section,dl div{{background:white}}}}</style></head><body><main><p class="eyebrow">Phase 6 · operational finder</p><h1>{esc(campaign["campaign_name"])}</h1><p class="lede">No creative was generated and no outreach was sent.</p><section><h2>Campaign scope</h2><p>{scope}</p><h2>Search assumptions</h2><ul>{assumptions}</ul></section><dl>{count_cards}</dl>{''.join(result_cards)}<section><h2>Limitations</h2><ul>{limitations}</ul><h2>Validation errors</h2><ul>{errors}</ul><h2>Future handoff readiness</h2><p>{esc(report["future_creative_handoff_readiness"])}</p></section></main></body></html>'''


def render(report: dict[str, Any], output: Path, *, base_dir: Path | None = None) -> None:
    suffix = output.suffix.lower()
    if suffix in {".md", ".markdown"}:
        content = render_markdown(report, base_dir=base_dir)
    elif suffix in {".html", ".htm"}:
        content = render_html(report, base_dir=base_dir)
    else:
        raise ValidationError("Output extension must be .md or .html.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        report = require_object(load_json(args.input, "run report"), "run report")
        render(report, args.output, base_dir=args.input.parent)
    except ValidationError as exc:
        raise SystemExit(f"Validation error: {exc}") from exc
    print(f"Created report: {args.output.resolve()}")


if __name__ == "__main__":
    main()

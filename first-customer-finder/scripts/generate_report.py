#!/usr/bin/env python3
"""Generate native Markdown, CSV, optional standalone HTML, and local history."""

from __future__ import annotations

import argparse
import html
import json
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from prospect_data import atomic_json, normalize_report, prepare_history, public_url, read_state, state_lock
from report_exports import DEMO_NOTICE, build_csv, build_markdown


DIMENSIONS = {
    "pain_strength": "Pain strength",
    "product_fit": "Product fit",
    "timing": "Timing",
    "reachability": "Reachability",
    "evidence_quality": "Evidence quality",
}


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def clamp(value: Any, maximum: int = 100) -> int:
    try:
        number = round(float(value))
    except (TypeError, ValueError, OverflowError):
        number = 0
    return max(0, min(maximum, number))


def items(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def safe_url(value: Any) -> str:
    try:
        return esc(public_url(value))
    except ValueError:
        return "#"


def stage_class(stage: Any) -> str:
    value = str(stage or "").lower()
    if "high" in value:
        return "hot"
    if "problem" in value or "trigger" in value:
        return "warm"
    return "cool"


def render_dimensions(data: dict[str, Any]) -> str:
    rows = []
    for key, label in DIMENSIONS.items():
        score = clamp(data.get(key, 0), 5)
        rows.append(
            f'<div class="metric"><span>{esc(label)}</span><div class="track"><i style="width:{score * 20}%"></i></div><b>{score}/5</b></div>'
        )
    return "".join(rows)


def render_prospect(prospect: dict[str, Any], index: int) -> str:
    score = clamp(prospect.get("score"))
    source = safe_url(prospect.get("source_url"))
    route = prospect.get("contact_route", {})
    route_html = (f'<a href="{safe_url(route.get("url"))}" target="_blank" rel="noreferrer">{esc(route.get("label", "Open contact route"))} ↗</a>'
                  if route.get("status") == "verified" else "No suitable public route verified")
    route_proof = (f'<a href="{safe_url(route.get("source_url"))}" target="_blank" rel="noreferrer">Route evidence ↗</a> · {esc(route.get("checked_at"))}'
                   if route.get("status") == "verified" else "")
    return f"""
    <article class="prospect reveal">
      <header class="prospect-head">
        <div class="rank">{index:02d}</div>
        <div class="identity">
          <span class="eyebrow">{esc(prospect.get('type', 'Public prospect'))}</span>
          <h3>{esc(prospect.get('name', f'Prospect {index}'))}</h3>
          <span class="stage {stage_class(prospect.get('stage'))}">{esc(prospect.get('stage', 'Potential fit'))}</span>
        </div>
        <div class="score" style="--score:{score}" aria-label="Fit score {score} out of 100"><strong>{score}</strong><small>/100</small></div>
      </header>
      <div class="signal"><span>Public signal</span><p>{esc(prospect.get('pain_signal', ''))}</p></div>
      <div class="prospect-grid">
        <div><span>Why it fits</span><p>{esc(prospect.get('why_fit', ''))}</p></div>
        <div><span>Why now</span><p>{esc(prospect.get('why_now', ''))}</p></div>
        <div><span>Who · {esc(prospect.get('role_basis', 'Not verified'))}</span><p>{esc(prospect.get('target_role', 'Not recorded'))}</p></div>
        <div><span>Contact route</span><p>{route_html}</p><p>{esc(route.get('note', ''))}</p><p>{route_proof}</p></div>
        <div><span>Next step</span><p>{esc(prospect.get('next_step', 'Verify source and route.'))}</p></div>
        <div><span>CTA</span><p>{esc(prospect.get('cta', 'Not recorded'))}</p></div>
        <div><span>Caution</span><p>{esc(prospect.get('caution', 'Confirm current relevance before outreach.'))}</p></div>
      </div>
      <blockquote><span>Draft — not sent</span>{esc(prospect.get('opener', ''))}</blockquote>
      <p class="chip">P{index} · {esc(prospect.get('id', 'legacy'))} · {esc(prospect.get('history_label', 'History not used'))}</p>
      <details>
        <summary>Evidence and score breakdown</summary>
        <div class="evidence"><div><span>Evidence</span><p>{esc(prospect.get('evidence', ''))}</p></div><div><span>Source</span><p>{esc(prospect.get('source_type', 'Public source'))} · Published: {esc(prospect.get('signal_date') or 'Unknown')} · Checked: {esc(prospect.get('checked_at', 'Not recorded'))}</p><a href="{source}" target="_blank" rel="noreferrer">{esc(prospect.get('source_title', 'Open original source'))} ↗</a></div></div>
        {''.join(f'<p><a href="{safe_url(s.get("url"))}" target="_blank" rel="noreferrer">{esc(s.get("note", "Supporting source"))} ↗</a></p>' for s in prospect.get('additional_sources', []))}
        <div class="metrics">{render_dimensions(prospect.get('dimensions') if isinstance(prospect.get('dimensions'), dict) else {})}</div>
      </details>
    </article>"""


def render_pattern(pattern: dict[str, Any], index: int) -> str:
    return f"""
    <article class="pattern reveal"><span class="pattern-num">{index:02d}</span><div><h3>{esc(pattern.get('title', 'Repeated signal'))}</h3><p>{esc(pattern.get('insight', ''))}</p></div><strong>{clamp(pattern.get('count'), 999)}×</strong></article>"""


def build_html(data: dict[str, Any]) -> str:
    prospects = sorted([x for x in items(data.get("prospects")) if isinstance(x, dict)], key=lambda p: -clamp(p.get('score')))
    patterns = [x for x in items(data.get("patterns")) if isinstance(x, dict)]
    scores = [clamp(x.get("score")) for x in prospects]
    high_intent = sum(1 for x in prospects if "high" in str(x.get("stage", "")).lower())
    average = round(sum(scores) / len(scores)) if scores else 0
    top = max(prospects, key=lambda x: clamp(x.get("score")), default={})
    plan = data.get("outreach_plan") if isinstance(data.get("outreach_plan"), dict) else {}
    limits = "".join(f"<li>{esc(x)}</li>" for x in items(data.get("limits")))
    prospect_html = "".join(render_prospect(x, i) for i, x in enumerate(prospects, 1))
    pattern_html = "".join(render_pattern(x, i) for i, x in enumerate(patterns, 1))
    product_url = safe_url(data.get("product_url"))
    notices = []
    if data.get('demo'):
        notices.append(DEMO_NOTICE)
    if data.get('legacy_warning'):
        notices.append(data['legacy_warning'])
    if data.get('history_summary'):
        history = data['history_summary']
        notices.append('History exclusions: ' + ', '.join(f'{k}: {v}' for k, v in history['excluded'].items()))
        notices.append('Search profile — ' + '; '.join(f'{k}: {", ".join(v) or "none"}' for k, v in history['profile'].items()))
    notice_html = ''.join(f'<p class="signal"><strong>{esc(n)}</strong></p>' for n in notices)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>{esc(data.get('title', 'First Customer Finder'))}</title>
  <style>
    :root{{--bg:#090b0f;--panel:#12161d;--panel2:#191f28;--ink:#f5f2ea;--muted:#9ca6b5;--line:#2b3340;--acid:#d9ff63;--blue:#69b7ff;--orange:#ff8f5a;--cyan:#5ee8d0;--radius:18px;--shadow:0 24px 80px rgba(0,0,0,.38)}}
    *{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.55}}body:before{{content:"";position:fixed;inset:0;pointer-events:none;opacity:.3;background:repeating-linear-gradient(135deg,rgba(255,255,255,.018) 0 1px,transparent 1px 12px);mask-image:linear-gradient(#000,transparent 82%)}}a{{color:inherit}}.skip{{position:absolute;left:-9999px}}.skip:focus{{left:16px;top:16px;z-index:9;background:var(--acid);color:#111;padding:10px}}
    .shell{{width:min(1180px,calc(100% - 40px));margin:auto;position:relative}}.top{{display:flex;justify-content:space-between;align-items:center;padding:22px 0;border-bottom:1px solid var(--line)}}.brand{{font-weight:850;display:flex;align-items:center;gap:10px}}.brand i{{width:12px;height:12px;border-radius:50%;background:var(--acid);box-shadow:0 0 22px var(--acid)}}.meta{{display:flex;gap:8px;align-items:center}}.chip,.stage{{border:1px solid var(--line);border-radius:999px;padding:7px 10px;color:var(--muted);font:750 11px ui-monospace,monospace;text-transform:uppercase;letter-spacing:.07em}}button{{background:var(--ink);color:#111;border:0;border-radius:999px;padding:9px 14px;font:800 13px inherit;cursor:pointer}}button:focus-visible,summary:focus-visible,a:focus-visible{{outline:3px solid var(--blue);outline-offset:3px}}
    .hero{{display:grid;grid-template-columns:1.45fr .55fr;gap:36px;align-items:end;padding:72px 0 42px}}.eyebrow{{color:var(--acid);font:750 11px ui-monospace,monospace;text-transform:uppercase;letter-spacing:.11em}}h1{{font-size:clamp(48px,7vw,92px);line-height:.92;letter-spacing:-.065em;margin:13px 0 24px}}.verdict{{font-size:clamp(18px,2.1vw,25px);color:#dce1e9;max-width:820px;margin:0}}.hero-card{{background:var(--acid);color:#10120d;padding:26px;border-radius:var(--radius);box-shadow:var(--shadow);transform:rotate(1deg)}}.hero-card span{{font:800 11px ui-monospace,monospace;text-transform:uppercase;letter-spacing:.08em}}.hero-card strong{{display:block;font-size:64px;line-height:1;letter-spacing:-.08em;margin:15px 0 6px}}.hero-card p{{margin:0;font-weight:700;font-size:13px}}
    .stats{{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;margin-bottom:28px}}.stats>div{{padding:18px;background:var(--panel)}}.stats>div+div{{border-left:1px solid var(--line)}}.stats span,.prospect-grid span,.signal span,.evidence span,blockquote span{{display:block;color:var(--muted);font:700 10px ui-monospace,monospace;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px}}.stats strong{{font-size:17px}}
    .best{{display:grid;grid-template-columns:180px 1fr auto;gap:24px;align-items:center;padding:25px;background:var(--orange);color:#1b0f09;border-radius:var(--radius);box-shadow:var(--shadow);margin:0 0 72px}}.best-label{{font:800 11px ui-monospace,monospace;text-transform:uppercase;letter-spacing:.1em}}.best h2{{font-size:clamp(28px,4vw,46px);letter-spacing:-.045em;line-height:1;margin:0 0 8px}}.best p{{margin:0}}.best strong{{font-size:44px}}
    .section-head{{display:flex;justify-content:space-between;align-items:end;gap:24px;padding-bottom:18px;border-bottom:1px solid var(--line);margin-bottom:18px}}.section-head h2{{font-size:clamp(34px,5vw,62px);line-height:.98;letter-spacing:-.055em;margin:0}}.section-head p{{color:var(--muted);max-width:470px;margin:0}}
    .prospects{{display:grid;gap:16px;margin-bottom:76px}}.prospect{{background:linear-gradient(135deg,var(--panel),#0f1319);border:1px solid var(--line);border-radius:var(--radius);padding:25px;box-shadow:0 12px 38px rgba(0,0,0,.18)}}.prospect-head{{display:grid;grid-template-columns:54px 1fr 92px;gap:17px;align-items:start}}.rank{{font:850 24px ui-monospace,monospace;color:var(--acid);padding-top:8px}}.identity h3{{font-size:29px;letter-spacing:-.04em;margin:6px 0 10px}}.stage{{display:inline-block}}.stage.hot{{color:var(--orange);border-color:rgba(255,143,90,.5)}}.stage.warm{{color:var(--cyan);border-color:rgba(94,232,208,.45)}}.score{{--score:0;width:88px;height:88px;border-radius:50%;display:grid;place-content:center;text-align:center;background:radial-gradient(circle,var(--panel) 58%,transparent 60%),conic-gradient(var(--acid) calc(var(--score)*1%),var(--line) 0)}}.score strong{{font-size:26px;line-height:1}}.score small{{color:var(--muted)}}
    .signal{{margin:21px 0 12px;padding:16px;background:var(--panel2);border-left:4px solid var(--acid)}}.signal p{{font-size:17px;margin:0}}.prospect-grid{{display:grid;grid-template-columns:1fr 1fr;gap:9px}}.prospect-grid>div,.evidence>div{{border:1px solid var(--line);border-radius:12px;padding:15px;background:rgba(255,255,255,.018)}}.prospect-grid p,.evidence p{{margin:0}}blockquote{{margin:12px 0 0;padding:16px;border:1px dashed rgba(217,255,99,.55);border-radius:12px;color:#eaf6c6}}details{{margin-top:10px}}summary{{cursor:pointer;color:var(--acid);font-weight:800;padding:10px 0}}.evidence{{display:grid;grid-template-columns:1fr 1fr;gap:9px}}.evidence a{{display:inline-block;color:var(--blue);margin-top:8px;word-break:break-word}}.metrics{{display:grid;gap:8px;margin-top:14px}}.metric{{display:grid;grid-template-columns:145px 1fr 40px;gap:12px;align-items:center;font-size:13px}}.track{{height:8px;background:var(--line);border-radius:8px;overflow:hidden}}.track i{{display:block;height:100%;background:linear-gradient(90deg,var(--blue),var(--acid))}}
    .patterns{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-bottom:76px}}.pattern{{display:grid;grid-template-columns:42px 1fr auto;gap:15px;align-items:start;padding:20px;border:1px solid var(--line);border-radius:14px;background:var(--panel)}}.pattern-num{{color:var(--acid);font:800 13px ui-monospace,monospace}}.pattern h3{{margin:0 0 5px}}.pattern p{{margin:0;color:var(--muted)}}.pattern>strong{{font-size:30px;color:var(--acid)}}
    .plan{{display:grid;grid-template-columns:.8fr 1.2fr;gap:28px;background:var(--acid);color:#111;padding:29px;border-radius:var(--radius);margin-bottom:30px}}.plan h2{{font-size:38px;line-height:1;letter-spacing:-.045em;margin:10px 0}}.plan-grid{{display:grid;grid-template-columns:1fr 1fr;gap:9px}}.plan-grid>div{{border:1px solid rgba(0,0,0,.24);border-radius:11px;padding:13px}}.plan-grid span{{display:block;font:750 10px ui-monospace,monospace;text-transform:uppercase;letter-spacing:.07em;margin-bottom:5px}}.plan-grid p{{margin:0}}.limits{{border:1px solid var(--line);border-radius:var(--radius);padding:24px;color:var(--muted);margin-bottom:60px}}.limits h2{{color:var(--ink);margin-top:0}}footer{{display:flex;justify-content:space-between;gap:20px;border-top:1px solid var(--line);padding:22px 0 40px;color:var(--muted);font-size:12px}}.reveal{{animation:rise .4s ease both}}@keyframes rise{{from{{opacity:0;transform:translateY(12px)}}}}
    @media(max-width:820px){{.shell{{width:min(100% - 24px,1180px)}}.hero,.plan{{grid-template-columns:1fr}}.hero{{padding-top:44px}}.hero-card{{transform:none}}.stats{{grid-template-columns:1fr 1fr}}.stats>div+div{{border-left:0;border-top:1px solid var(--line)}}.best{{grid-template-columns:1fr}}.prospect-head{{grid-template-columns:38px 1fr}}.score{{grid-column:1/-1}}.prospect-grid,.evidence,.patterns,.plan-grid{{grid-template-columns:1fr}}.meta .chip{{display:none}}}}
    @media(prefers-reduced-motion:reduce){{*{{animation:none!important;transition:none!important;scroll-behavior:auto!important}}}}@media print{{body{{background:#fff;color:#111}}body:before,.top button{{display:none}}.shell{{width:100%}}.prospect,.pattern,.limits{{background:#fff;color:#111;break-inside:avoid}}.prospect-grid span,.signal span,.evidence span,blockquote span{{color:#444}}}}
  </style>
</head>
<body>
  <a class="skip" href="#main">Skip to report</a>
  <div class="shell">
    <header class="top"><div class="brand"><i></i> First Customer Finder</div><div class="meta"><span class="chip">Public signals only</span><button type="button" onclick="window.print()">Print / Save PDF</button></div></header>
    <main id="main">
      {notice_html}
      <section class="hero"><div><span class="eyebrow">Early-customer report · {esc(data.get('generated_at', ''))}</span><h1>{esc(data.get('title', 'First Customer Finder'))}</h1><p class="verdict">{esc(data.get('verdict', 'No verdict supplied.'))}</p></div><aside class="hero-card"><span>Qualified prospects</span><strong>{len(prospects)}</strong><p>Potential customers based on public signals.</p></aside></section>
      <section class="stats"><div><span>Product</span><strong><a href="{product_url}" target="_blank" rel="noreferrer">{esc(data.get('product', 'Not specified'))}</a></strong></div><div><span>Target customer</span><strong>{esc(data.get('target_customer', 'Not specified'))}</strong></div><div><span>High intent</span><strong>{high_intent}</strong></div><div><span>Average fit score</span><strong>{average}/100</strong></div></section>
      <section class="best"><div class="best-label">Highest-confidence prospect</div><div><h2>{esc(top.get('name', 'No qualified prospect'))}</h2><p>{esc(top.get('why_now', top.get('pain_signal', '')))}</p></div><strong>{clamp(top.get('score'))}</strong></section>
      <section><header class="section-head"><h2>People with a reason<br>to care now.</h2><p>Every primary prospect is tied to a public pain, demand, or timing signal. Open the evidence before considering outreach.</p></header><div class="prospects">{prospect_html or '<p>No qualified prospects supplied.</p>'}</div></section>
      <section><header class="section-head"><h2>Signals that repeat.</h2><p>Patterns across prospects reveal the strongest positioning, workflow, and outreach angles.</p></header><div class="patterns">{pattern_html or '<p>No repeated patterns supplied.</p>'}</div></section>
      <section class="plan"><div><span class="eyebrow" style="color:#111">Seven-day manual plan</span><h2>{esc(plan.get('angle', 'Validate the pain before pitching the product.'))}</h2></div><div class="plan-grid"><div><span>First step</span><p>{esc(plan.get('first_step', ''))}</p></div><div><span>Follow-up</span><p>{esc(plan.get('follow_up', ''))}</p></div><div><span>Success signal</span><p>{esc(plan.get('success', ''))}</p></div><div><span>Research scope</span><p>{esc(data.get('search_scope', 'Not specified'))}</p></div></div></section>
      <section class="limits"><h2>Use this shortlist responsibly</h2><ul>{limits or '<li>These are potential customers inferred from public signals, not confirmed buyers.</li>'}</ul></section>
    </main>
    <footer><span>Generated by $first-customer-finder</span><span>Outreach is never sent automatically.</span></footer>
  </div>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Path to report JSON")
    parser.add_argument("output", type=Path, help="Path to output .md or .html (legacy command supported)")
    parser.add_argument("--csv", type=Path, help="Optional spreadsheet-safe CSV output")
    parser.add_argument("--html", type=Path, help="Optional standalone HTML alongside Markdown")
    parser.add_argument("--state", type=Path, help="Explicit product-local history path")
    parser.add_argument("--new-only", action="store_true", help="Exclude every previously seen entity; requires --state")
    args = parser.parse_args()

    try:
        if args.output.suffix.lower() not in {".md", ".html"}:
            raise ValueError("Output must have .md or .html extension")
        if args.new_only and not args.state:
            raise ValueError("--new-only requires --state")
        outputs = [p for p in (args.output, args.csv, args.html) if p]
        reserved = [args.input] + ([args.state, args.state.with_name(args.state.name + '.lock')] if args.state else [])
        all_paths = [p.resolve() for p in outputs + reserved]
        if len(all_paths) != len(set(all_paths)):
            raise ValueError("Input, outputs, state, and lock paths must be distinct")
        for path in outputs:
            if path.exists() or path.is_symlink():
                raise ValueError(f"Output already exists; choose a fresh run path: {path}")
        with args.input.open(encoding="utf-8") as handle:
            data = normalize_report(json.load(handle))
        with state_lock(args.state) if args.state else nullcontext():
            state = None
            if args.state:
                current = read_state(args.state) if args.state.exists() or args.state.is_symlink() else None
                data, state = prepare_history(data, current, args.new_only)
            rendered = {args.output: build_html(data) if args.output.suffix.lower() == '.html' else build_markdown(data)}
            if args.csv:
                rendered[args.csv] = build_csv(data)
            if args.html:
                rendered[args.html] = build_html(data)
            for path, content in rendered.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('x', encoding='utf-8', newline='') as handle:
                    handle.write(content)
            if args.state:
                atomic_json(args.state, state)
        for path in rendered:
            print(f"Created: {path.resolve()}")
        print(f"Included {len(data.get('prospects', []))} prospects. No outreach sent.")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()

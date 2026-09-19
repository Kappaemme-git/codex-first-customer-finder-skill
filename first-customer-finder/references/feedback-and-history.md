# Feedback and local history

Read this for saved history, repeat searches, and feedback. No network service, account, background job, or CRM is involved.

## Scope and storage

Use `outputs/first-customer-finder/<product-slug>/state.json` inside the user's chosen workspace. Put each report and its analysis JSON under a fresh run subfolder, such as `2026-09-19-01/`. Do not save research in the installed skill, its distribution repo, or a shared global database. Offer an ephemeral run when the user does not want history: omit `--state` and keep analysis JSON temporary. Explain that old reports contain their own snapshots even if history is later removed.

Set `project_key` to a stable, explicit product identifier (normally its canonical product URL; otherwise a user-recognizable slug). Reuse it on subsequent runs. The helper rejects a different product key in an existing state file. Never silently merge or switch histories. Two products from one company still need separate keys/folders.

Stable prospect IDs derive from `entity_url`: a public official company homepage or the specific public professional/project profile, never the shared host alone. Strip tracking and fragments, normalize www/trailing slashes, and treat twitter.com/x.com as aliases. Different legitimate paths remain different. Do not merge entities by name or guess that two profiles are the same person. Resolve identity manually when evidence establishes a match.

State retains the latest concise prospect snapshot, source/contact URLs, first/last seen times, user feedback/outcome, and explicit preferred/avoided search criteria. No entire scraped threads, private contact lists, tracking pixels, or secrets. Do not commit, upload, or publish it. Users can remove this exact product folder themselves to remove its reports and history; never delete it without a separate explicit request.

## Commands

Paths below are examples; resolve `scripts/` from this skill, and use absolute paths in actual tool calls.

Inspect the saved project before researching:

```bash
python3 scripts/prospect_history.py --state /workspace/outputs/first-customer-finder/example/state.json show
```

After the user selects an ID from the report, save only their stated judgment:

```bash
python3 scripts/prospect_history.py --state /workspace/outputs/first-customer-finder/example/state.json feedback p_0123456789abcd keep --reason "Relevant owner-led business"
python3 scripts/prospect_history.py --state /workspace/outputs/first-customer-finder/example/state.json feedback p_abcdef01234567 reject --reason "This company is too large"
```

The stable `p_...` ID appears alongside the convenient report rank P1/P2. Resolve ranks from the specific report being discussed; never reuse a rank across reports without checking its ID.

Only after an explicit general preference, update the search profile:

```bash
python3 scripts/prospect_history.py --state /workspace/outputs/first-customer-finder/example/state.json profile --prefer "Owner-led small teams" --avoid "Enterprise procurement"
```

Each supplied flag replaces that entire list; omitted flags preserve their existing list. Multiple flags are allowed. Read the current profile first and retain preferences the user did not change. Use `--clear-prefer` / `--clear-avoid` only when the user requests clearing that list. Reasons on individual feedback records are not automatically generalized.

Only after a user-reported outcome:

```bash
python3 scripts/prospect_history.py --state /workspace/outputs/first-customer-finder/example/state.json status p_0123456789abcd contacted
```

Allowed outcomes: `new`, `contacted`, `replied`, `not_interested`, `customer`. All but `new` are excluded from new outreach shortlists; rejecting an entity also excludes it. An explicit `keep` changes feedback but does not reset contact status. Correct a wrongly entered status only at the user's direction.

## More versus refresh

- **More/new:** inspect history, search with current criteria, then generate with `--state ... --new-only`. Previously seen records cannot reappear as new. Any omitted records are counted in the report.
- **Refresh existing:** reopen evidence and contact routes, write a new analysis, generate with `--state ...` without `--new-only`. Keep/maybe/new records can return as previously seen. Contacted/rejected records stay excluded.
- **Review contacted prospects:** inspect `show` or the older reports; do not reset their status just to force them into a prospect shortlist.
- **No additional matches:** produce an honest empty shortlist with the research limits. Do not relabel old prospects as new, broaden the ICP silently, or retry indefinitely.

State updates use an exclusive file lock and atomic replacement. If another run has the file locked, stop that update and report the conflict. Never delete another run's lock to force access.

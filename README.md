# First Customer Finder

**Find people with a public reason to care about your product — and know your next manual step.**

Give Codex your product URL, repository, or a short description. This skill researches accessible public demand signals, qualifies potential customers, verifies suitable public contact routes, and creates a report you can open directly in Codex.

Tell it which prospects fit. The next search uses your explicit feedback and local history.

> These are potential customers based on public evidence, not confirmed buyers. The skill never sends outreach automatically.

## What's new in v2

- **Concrete outreach:** target role, observed/inferred label, verified public route or an honest missing-route warning, realistic next step, and a specific CTA.
- **Feedback-driven searches:** keep, maybe, or reject candidates; refine the target profile with explicit preferences.
- **Product-local history:** stable prospect IDs, duplicate exclusion, previously seen labels, and manually recorded contact outcomes.
- **Native Markdown + CSV:** evidence and next steps in Codex, with a spreadsheet-friendly export. Standalone HTML is still available.
- **Stronger checks:** weighted scores are computed, missing dates/routes reduce their relevant dimensions, and malformed or incomplete qualified records are rejected.
- **Recoverable upgrades:** the installer preserves your previous skill folder outside the active skills directory.

“Learning” means saved search preferences, not model training. Public route verification means Codex inspected the page, not that the recipient consented to promotion.

## Install or update

```bash
npx --yes codex-first-customer-finder-skill@latest
```

Installs into `$CODEX_HOME/skills/first-customer-finder` or `~/.codex/skills/first-customer-finder`. Restart Codex after an update so it loads the new instructions. Re-running the command installs the version currently published on npm; source changes are not available there until a release is published.

Custom directory:

```bash
npx --yes codex-first-customer-finder-skill@latest --skills-dir /path/to/skills
```

**Requirements:** Node.js for the installer, Python 3.9+ for the local helpers, and a Codex environment with web search or browser access for live research. No third-party Python dependencies, data-broker subscription, or skill-specific API key is required. Codex usage and external platform access remain subject to your own account and tools.

## Try it

Start with a product:

```text
Use $first-customer-finder to find 5 potential customers for [PRODUCT URL].
```

Then refine the results:

```text
P1 and P3 fit. Focus on owner-led small businesses, avoid enterprise teams, and find 5 more.
```

Record a real outcome:

```text
I contacted P1. Remember that and exclude it from the next search.
```

Ranks such as P1 belong to the report you are discussing. The saved history uses stable IDs, so ranks cannot silently point to a different prospect in another report.

Other useful requests:

```text
Use $first-customer-finder in design-partners mode for [PRODUCT URL].
```

```text
Use $first-customer-finder to find developers publicly asking for an alternative to [TOOL], for my product [URL].
```

```text
Refresh the existing shortlist, recheck the sources, and include the HTML report.
```

## How a search works

1. **Understand the product.** Identify the outcome, buyer, use case, geography, alternatives, and disqualifiers. Ask a concise question only when a material ambiguity remains.
2. **Read the current project history.** Apply explicit preferences and avoid excluded candidates. A different product gets a separate history.
3. **Research public signals.** Discover and open original sources: requests for tools, manual workarounds, unresolved pain, switching intent, and relevant business events.
4. **Qualify and challenge.** Attribute the evidence correctly, check for resolved problems or poor fit, calculate the score, and consolidate duplicate entities.
5. **Make the next step concrete.** Identify the relevant function, verify a suitable official/public route when possible, and draft a short message with an actionable CTA.
6. **Deliver and refine.** Save a Markdown report, CSV, and local history. On request, use your feedback for the next search or refresh.

Search may use accessible public X posts, GitHub issues, forums, product reviews, company pages, and search engines. It does not promise access to every platform, bypass login walls, or qualify candidates from snippets alone. Blocked sources are reported as coverage gaps.

## What you receive

| Output | Purpose |
| --- | --- |
| `report.md` | Native Codex report with ranked candidates, source links/dates, roles, contact routes, drafts, and cautions |
| `prospects.csv` | Spreadsheet-safe snapshot of the included shortlist and its next steps |
| `report.html` (optional) | Responsive standalone visual report |
| `state.json` | Product-scoped local history, explicit preferences, feedback, and reported outcomes |
| `analysis.json` | The run's structured evidence, retained in the workspace unless using an ephemeral workflow |

Example workspace layout:

```text
outputs/first-customer-finder/my-product/
├── state.json
├── run-01/
│   ├── analysis.json
│   ├── report.md
│   └── prospects.csv
└── run-02/
    ├── analysis.json
    ├── report.md
    └── prospects.csv
```

History is kept in the chosen workspace, not uploaded, synced, or stored inside the installed skill. Ask for a run without saved history to omit it. Existing report files remain independent snapshots. Keep the research folder out of version control; remove that exact product folder yourself when you no longer want the stored data.

CSV edits are not automatically imported. Tell Codex which outcomes to record.

## Feedback and repeat searches

- **Keep / maybe / reject:** save your assessment and reason for a specific prospect.
- **Prefer / avoid:** save explicit general criteria. Rejecting one company does not automatically reject its entire industry.
- **Find more:** exclude all previously seen entities, as well as rejected or already-contacted records.
- **Refresh:** revisit eligible existing prospects and inspect their current evidence. Preserve feedback and contact status.
- **Contact outcomes:** `new`, `contacted`, `replied`, `not_interested`, or `customer`; entered only from your report, never inferred from a generated draft.

No background monitoring is started. No follow-up is sent. An empty shortlist is a valid result when there are no additional qualified matches.

## Qualification

| Dimension | Weight |
| --- | ---: |
| Pain strength | 25% |
| Product fit | 25% |
| Timing | 20% |
| Public reachability | 15% |
| Evidence quality | 15% |

Each dimension runs from 0 to 5. The helper calculates the weighted total. Scores are research priorities, **not conversion probabilities**. Numerical scores cannot override missing, contradictory, or misattributed evidence.

Every primary prospect needs an inspected original source. Unknown signal dates cap timing at 2/5; no suitable verified contact route caps reachability at 1/5. The report distinguishes publication date from the date the source was checked.

## Modes

- `quick`: up to 5 prospects
- `standard`: up to 10, default
- `deep`: up to 20 plus repeated-pattern analysis
- `design-partners`: feedback-oriented early adopters
- `b2b`: companies, business triggers, and buyer functions
- `community`: explicit requests and public discussion signals

Requested counts are limits, not quotas. The skill should return fewer candidates when evidence is weak.

## Privacy and limits

- Public, intentionally shared professional/business information only.
- No private email discovery, phone enrichment, data brokers, sensitive-trait targeting, or private-group access.
- No messages, form submissions, follows, comments, or CRM changes from a prospect-search request.
- A found route is not permission to advertise; platform/community rules still matter.
- A local preference profile is not autonomous learning or proof of demand.
- The scripts validate structure and consistency; they cannot prove a public statement true or replace judgment about outreach suitability.

## Run the fictional demo

This offline fixture tests the report and history workflow. **Every prospect, statement, and route is fictional.** It is not a live research benchmark.

```bash
git clone https://github.com/Kappaemme-git/codex-first-customer-finder-skill.git
cd codex-first-customer-finder-skill
python3 first-customer-finder/scripts/generate_report.py examples/demo.json outputs/demo/run-01/report.md --csv outputs/demo/run-01/prospects.csv --html outputs/demo/run-01/report.html --state outputs/demo/state.json
```

Try a repeat run: it should not invent new prospects or repackage old ones as new.

```bash
python3 first-customer-finder/scripts/generate_report.py examples/demo.json outputs/demo/run-02/report.md --state outputs/demo/state.json --new-only
```

Demo history cannot be mixed with real research. The fixture is not shipped in the npm install.

## Local development and tests

Install a source checkout for testing before publishing:

```bash
node scripts/install.js
npm test
npm pack --dry-run
```

Tests cover score calculation, stable identities, product isolation, feedback, outcome retention, repeated-search exclusions, missing routes, unsafe links, CSV formula escaping, legacy HTML, demo labels, history locking, output protection, and recoverable installation.

The package version is `0.2.0`; “v2” describes the second workflow generation.

## Community input

The outreach improvements address [issue #2](https://github.com/Kappaemme-git/codex-first-customer-finder-skill/issues/2) and incorporate the direction proposed in [PR #3](https://github.com/Kappaemme-git/codex-first-customer-finder-skill/pull/3) and [PR #5](https://github.com/Kappaemme-git/codex-first-customer-finder-skill/pull/5). Those proposals motivated concrete contact routes and manual CTAs; this update also adds local feedback/history and native exports.

## License

MIT

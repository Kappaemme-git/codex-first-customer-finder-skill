# Unreal Prospecting Skills

The `unreal` branch is ready to install as a local Codex skill. Its completed Phase 6 product is the practical finder/researcher workflow:

1. find public-business candidates,
2. load history and remove prior, suppressed, client, partner, active-outreach, and ambiguous identities,
3. optionally filter for product-photography or product-video opportunities while excluding UGC-ad work,
4. qualify and deeply research the remaining businesses,
5. validate the evidence and scoring,
6. produce local JSON, Markdown, and HTML reports.

It does not generate creative, send outreach, collect private contact data, write to a CRM, invoke downstream agents, or edit Unreal OS. The retired dossier/live-proof/projector/graph machinery is not part of this release.

## Install from GitHub

Runtime requirements: Git, Node.js, Python 3, and Codex. No package installation or third-party Python runtime dependency is required.

```bash
git clone --branch unreal https://github.com/Unreal-Media-Group/codex-first-customer-finder-skill.git unreal-prospecting-skills
cd unreal-prospecting-skills
node scripts/install-unreal.js --skill umg
```

The installer copies `unreal-media-brand-prospector` and the shared deterministic core into the active Codex skills directory. Restart Codex after installation.

Other supported selections are:

```bash
node scripts/install-unreal.js --skill original
node scripts/install-unreal.js --skill talent
node scripts/install-unreal.js --skill unreal
node scripts/install-unreal.js --skill all
```

Use `--skills-dir PATH` for an isolated install. The upstream `scripts/install.js` flow remains unchanged.

## Prepare the first run

Create a writable local campaign folder so real prospect history never enters Git:

```bash
mkdir -p "$HOME/unreal-prospecting-data/campaigns" "$HOME/unreal-prospecting-data/history" "$HOME/unreal-prospecting-data/reports"
cp "$HOME/.codex/skills/unreal-prospecting-core/examples/campaigns/umg-product-visuals-no-ugc.json" "$HOME/unreal-prospecting-data/campaigns/"
cp "$HOME/.codex/skills/unreal-prospecting-core/examples/history/starter-prospect-history.json" "$HOME/unreal-prospecting-data/history/"
python3 "$HOME/.codex/skills/unreal-prospecting-core/scripts/validate_campaign.py" "$HOME/unreal-prospecting-data/campaigns/umg-product-visuals-no-ugc.json"
```

The included campaign searches broadly for evidence-backed product-photography or product-video opportunities and excludes evidence of UGC-ad work. Edit its geography, verticals, limits, and signal preferences if needed; keep the controlled `opportunity_filter` values unchanged unless you intentionally want a different supported filter.

## Run in Codex

After restarting Codex, paste this prompt:

```text
Use $unreal-media-brand-prospector.

Run the campaign at:
~/unreal-prospecting-data/campaigns/umg-product-visuals-no-ugc.json

Load and update its referenced prospect history before qualification. Find public-business candidates, classify every identity against history, apply the product-photography/product-video include-any filter and UGC-ad exclusion only after deduplication, deeply research every eligible shortlisted business, and preserve dated source evidence with observation/inference labels.

Write the validated run JSON plus Markdown and HTML reports under:
~/unreal-prospecting-data/reports/

Do not collect private contact data, generate creative, draft or send outreach, write externally, or invoke downstream agents. Return fewer candidates if the evidence is insufficient.
```

The skill uses public web research when you explicitly run it. Deterministic validators and report rendering run locally; result quality still depends on accessible public evidence.

## Verify the checkout

The release suite also runs Codex's official skill validator, whose development-only dependency is listed in `requirements-dev.txt`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
PROSPECTING_PYTHON=.venv/bin/python bash tests/prospecting/run_all.sh
```

The suite validates campaigns, history, deduplication, opportunity filtering, reports, installers, Phase 3–5 synthetic local controls, and both Codex skills.

## Optional local Mission Control

Phases 3–5 remain available as a synthetic, loopback-only review and shadow-scheduling harness. They are not required to run the Phase 6 finder and do not perform live research.

```bash
python3 apps/prospecting-mission-control/run_server.py --port 8765
```

Open `http://127.0.0.1:8765`, then stop the server with `Ctrl-C`. See the Phase 3–5 documents for their fixture-only boundaries.

## Documentation

- [Phase 6 operational finder](docs/PHASE_6_OPERATIONAL_FINDER.md)
- [Campaign and report usage](docs/PHASE_1_USAGE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Phase 3 Manual Mission Control](docs/PHASE_3_MISSION_CONTROL.md)
- [Phase 4 Registered Agent](docs/PHASE_4_REGISTERED_AGENT.md)
- [Phase 5 Shadow Loop](docs/PHASE_5_SHADOW_LOOP.md)
- [Safe upstream synchronization](docs/UPSTREAM_SYNC.md)
- [Program roadmap](docs/specs/UNREAL_PROSPECTING_SKILLS_PROGRAM_ROADMAP.md)

The root `README.md` keeps the upstream documentation and adds a single `unreal`-branch pointer to this guide. `package.json`, the original skill directory, and the original installer remain aligned with upstream. Unreal-specific installation is documented here because this fork has not been published as a separate npm package.

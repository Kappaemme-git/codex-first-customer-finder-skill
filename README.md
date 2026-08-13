# Codex First Customer Finder Skill

A Codex skill that turns a startup URL or product idea into a qualified shortlist of potential first customers using recent public pain, demand, and timing signals.

It defines the ideal customer profile, researches public sources, links the evidence behind every prospect, ranks fit and timing, drafts a source-based opener, and creates a polished HTML report. It never sends outreach automatically.

## What It Does

- Analyzes a startup URL, repository, or product description
- Defines the primary and adjacent ideal customer profiles
- Finds explicit demand, pain, workaround, switching, and timing signals
- Qualifies prospects with an evidence-based score
- Links every primary prospect to the original public source
- Drafts respectful, source-based outreach openers
- Creates a responsive standalone HTML report
- Keeps all outreach manual by default
- Avoids private contact enrichment and sensitive personal data

## Installation

```bash
npx --yes codex-first-customer-finder-skill@latest
```

This installs the skill into:

```text
~/.codex/skills/first-customer-finder
```

Restart Codex after installation.

## Usage

Find the first ten potential customers:

```text
Use $first-customer-finder to find ten evidence-backed potential first customers for https://example.com and create the final HTML report.
```

Find design partners:

```text
Use $first-customer-finder in design-partners mode for this startup: [URL]. Prioritize people publicly describing the problem and likely to give product feedback.
```

B2B research:

```text
Use $first-customer-finder in b2b mode for [URL]. Find public business triggers, qualify the relevant companies, and draft one opener per prospect without sending anything.
```

## Output

The report includes:

1. Early-customer verdict
2. Primary ICP and disqualifiers
3. Highest-confidence prospect
4. Evidence-backed prospect shortlist
5. Fit and timing scores
6. Source links and signal dates
7. Personalized outreach openers
8. Repeated pain patterns
9. Seven-day manual outreach plan
10. Research limitations

Prospects are hypotheses based on public signals, not confirmed customers or guaranteed buyers.

## Modes

- `quick`: up to five strong prospects
- `standard`: up to ten prospects across several source types
- `deep`: up to twenty prospects and repeated-pattern analysis
- `design-partners`: feedback-oriented early adopters
- `b2b`: companies and public business triggers
- `community`: explicit requests and public discussion signals

## Manual Installation

```bash
git clone https://github.com/Kappaemme-git/codex-first-customer-finder-skill.git
mkdir -p ~/.codex/skills
cp -R codex-first-customer-finder-skill/first-customer-finder ~/.codex/skills/first-customer-finder
```

Restart Codex after installation.

## License

MIT

## Sponsor

[![CoreClaw — Find high-intent leads from local data](assets/coreclaw-google-maps-lead-finder.png)](https://www.coreclaw.com/coreclaw/google-maps-lead-finder?utm_source=github&utm_medium=referral&utm_campaign=leads&utm_term=&utm_id=leads)

### CoreClaw: 100+ Platform Scraping + Lead Enrichment

Turn public data into actionable, high-intent sales leads—and find your first
paying customers faster.

- No coding required—extract structured data effortlessly
- Flexible exports, including JSON, CSV, Excel, and more
- Pay only for successful results, with no wasted budget on failures

[Start your free CoreClaw trial](https://www.coreclaw.com/coreclaw/google-maps-lead-finder?utm_source=github&utm_medium=referral&utm_campaign=leads&utm_term=&utm_id=leads)

*CoreClaw is a paid sponsor of this project.*

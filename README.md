# Shopify Audit & Outreach Agent (Autonomous Lead Discovery Edition)

An AI agent, built on the [Coasty](https://coasty.ai) computer-use API, that
**autonomously finds new small Shopify stores on its own**, audits each one
for genuine, fixable problems, ranks them by opportunity, and drafts
personalized outreach — with a human approval gate before anything is marked
ready to send. It remembers every store it has ever processed, so it never
wastes a run re-contacting the same lead twice.

## The Problem

Freelance Shopify optimizers (speed, conversion, checkout fixes) typically
spend real time manually hunting for leads, then cold-pitch stores with
generic messages: *"Hi, want to hire me?"* This is slow, doesn't scale, and
has a low response rate because it isn't backed by anything specific.

This agent removes both bottlenecks: it finds NEW small stores on its own
each run, actually visits each one, finds real evidence-backed issues, and
drafts outreach that says *"I noticed X, Y, Z on your store"* instead of a
generic pitch — with zero repeated leads across runs.

## How It Works (Workflow)

The pipeline runs in six phases, all orchestrated by one Python script:

0. **Discover** — A Coasty agent searches online on its own to find a target
   number of real, small, active, independent Shopify stores — explicitly
   avoiding large established brands and anything already recorded in
   `seen_stores.json` from a previous run. If discovery finds fewer stores
   than the target (a quiet day, rate limits, etc.), a manual fallback list
   automatically fills the gap so a run never comes up empty.
1. **Audit** — For each store, a Coasty agent visits the live site and
   checks: page load speed, image optimization, checkout friction (add to
   cart → view cart), mobile-layout issues, broken links, and trust signals
   (shipping info, return policy, reviews). It self-scores an "Opportunity
   Score" (1–10) based on how many real, fixable problems it found.
2. **Verify** — A second, independent Coasty agent pass re-checks the single
   most significant issue from phase 1, using a different method (e.g.
   reloading and re-timing, or checking a different product page), so
   findings aren't reported on a single fluke pass.
3. **Rank** — All stores are sorted by Opportunity Score, so the freelancer
   knows exactly who to contact first.
4. **Draft outreach** — For the top 3 ranked stores, a personalized outreach
   message is generated, referencing the specific issues found on that exact
   store.
5. **Human approval gate** — Before any message is written to the final
   report, a human is asked to approve or skip it. Nothing is auto-sent.

Output is saved as a durable `audit_report.md` file — a ranked report with
findings, verification notes, and approved outreach messages, ready to
actually use. `seen_stores.json` is updated so tomorrow's run automatically
discovers fresh, never-before-seen leads.

## Why This Is a Real Business Workflow

This isn't a single lookup or a "research and summarize" task. It's a closed
loop with persistent memory: autonomous lead discovery → multi-phase
execution across two independent agent passes → a ranked, durable business
deliverable (a report a freelancer could open and act on immediately) → a
human-in-the-loop gate before any outward action → memory that prevents
wasted, repeated outreach. It solves an actual freelance sales problem end
to end, not a hypothetical one.

## Setup

Requirements: Python 3, `requests` library, a Coasty API key.

```bash
pip install requests
export COASTY_API_KEY="sk-coasty-live-your-key-here"
```

Optionally adjust `DAILY_TARGET` near the top of `shopify_audit_agent.py` to
change how many new stores are discovered and processed per run. The
`FALLBACK_STORE_URLS` list can also be edited — it's only used if autonomous
discovery can't find enough new stores on its own.

## Running It

```bash
python3 shopify_audit_agent.py
```

The script will:
- Autonomously discover new, never-before-seen small Shopify stores
- Print live status updates as each store is audited and verified
- Show ranked results in the terminal
- Prompt you to approve or skip each drafted outreach message (type `y` or `n`)
- Save everything to `audit_report.md` when finished
- Update `seen_stores.json` so the next run finds entirely fresh leads

## Evidence From a Real Run

*(Run ID, step count, and cost to be added here after the demo run — see
`audit_report.md` in this repo for full output.)*

## Customization

- Add or remove checks in the `audit_store()` task prompt to fit different
  platforms (not just Shopify) or different priorities
- Change `top_candidates = all_results[:3]` to draft outreach for more or
  fewer stores
- Swap `draft_outreach_message()` for a Coasty-powered draft instead of the
  current template-based version, if you want the AI to write the pitch too

## License

MIT — free to use, adapt, and build on.

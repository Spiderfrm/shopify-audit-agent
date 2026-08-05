"""
Shopify Audit & Outreach Agent (Autonomous Lead Discovery Edition)
--------------------------------------------------------------------
A closed-loop AI workflow built on the Coasty computer-use API.

WHAT THIS DOES (in plain terms):
0. AUTONOMOUSLY DISCOVERS new small Shopify stores on its own each run --
   you don't have to manually hunt for URLs. It remembers every store
   it has already processed (in seen_stores.json) so it never repeats
   the same lead twice across runs.
1. For each discovered (or fallback) store, sends an AI agent to actually
   visit the site and check for real, common problems (page speed, image
   size, checkout friction, mobile experience, broken links, trust
   signals)
2. Sends a SECOND agent pass to independently re-verify the most important
   finding for each store (cross-verification, not just one pass)
3. Scores and ranks every store by "opportunity" -- how many real,
   fixable problems it has
4. Drafts a personalized outreach message for the top-ranked stores,
   referencing the SPECIFIC issues found on THAT store
5. Requires human approval before any message is marked "ready to send"
6. Saves everything as a durable, readable report file (audit_report.md)
   and updates seen_stores.json so tomorrow's run finds fresh leads

WHY THIS IS A REAL BUSINESS WORKFLOW (not a toy demo):
This solves an actual freelance problem: instead of manually hunting for
leads AND cold-pitching with generic messages, this finds NEW real stores
on its own, evidence-backs the pitch, and never wastes a day re-contacting
someone already reached out to.

SAFETY NET: if autonomous discovery can't find enough new stores in a
run (rate limits, a quiet day, etc.), the script automatically falls
back to a manual backup list (FALLBACK_STORE_URLS below) so a run never
comes up empty.

HOW TO RUN THIS:
1. pip install requests
2. Get your live API key from https://coasty.ai/developers/keys
3. Set it as an environment variable:
       export COASTY_API_KEY="sk-coasty-live-..."
4. (Optional) adjust DAILY_TARGET below for how many new stores per run
5. Run:
       python3 shopify_audit_agent.py
6. Follow the prompts for the human-approval step
7. Check audit_report.md when it finishes -- run it again tomorrow and
   it will automatically find fresh, never-before-seen stores
"""

import os
import sys
import time
import json
import re
import requests

BASE = "https://coasty.ai/v1"
API_KEY = os.environ.get("COASTY_API_KEY")

if not API_KEY:
    print("ERROR: Set COASTY_API_KEY as an environment variable first.")
    print('Example: export COASTY_API_KEY="sk-coasty-live-..."')
    sys.exit(1)

HEADERS = {"X-API-Key": API_KEY}

# ---- How many NEW stores to find and process per run ----
DAILY_TARGET = 5

# ---- Where we remember stores we've already contacted ----
SEEN_STORES_FILE = "seen_stores.json"

# ---- Safety net: used only if autonomous discovery comes up short ----
FALLBACK_STORE_URLS = [
    "https://aguaprimo.myshopify.com",
    "https://dontaedemarcusllc.com",
    "https://ellisstores.com",
    "http://mrehig-ye.myshopify.com",
    "https://reliable-networks-2.myshopify.com",
]

TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "timed_out"}


def run_coasty_task(task_description: str, idempotency_key: str, max_steps: int = 40):
    """
    Sends one task to Coasty's /v1/tasks endpoint and polls until it
    finishes. Returns the final run data (dict).
    """
    response = requests.post(
        f"{BASE}/tasks",
        headers={**HEADERS, "Idempotency-Key": idempotency_key},
        json={"task": task_description, "max_steps": max_steps},
        timeout=30,
    )
    run = response.json()
    run_id = run.get("id")

    if not run_id:
        print(f"  ERROR starting task: {run}")
        return {"status": "failed", "result": None}

    print(f"  Started run {run_id}...")

    while True:
        status_resp = requests.get(f"{BASE}/runs/{run_id}", headers=HEADERS, timeout=30)
        status_data = status_resp.json()
        status = status_data.get("status")
        steps = status_data.get("steps_completed", 0)
        print(f"    status: {status} | steps: {steps}")

        if status in TERMINAL_STATUSES:
            return status_data

        time.sleep(3)


def load_seen_stores() -> set:
    """
    Loads the set of store URLs we've already discovered/contacted in
    previous runs, so we never repeat a lead. Returns an empty set if
    this is the first run (file doesn't exist yet).
    """
    if not os.path.exists(SEEN_STORES_FILE):
        return set()
    try:
        with open(SEEN_STORES_FILE, "r") as f:
            data = json.load(f)
            return set(data.get("seen_urls", []))
    except (json.JSONDecodeError, IOError):
        return set()


def save_seen_stores(seen_urls: set):
    """
    Persists the growing list of already-contacted stores to disk so
    tomorrow's run knows to skip them.
    """
    with open(SEEN_STORES_FILE, "w") as f:
        json.dump({"seen_urls": sorted(list(seen_urls))}, f, indent=2)


def discover_new_stores(seen_urls: set, target_count: int) -> list:
    """
    PHASE 0: Autonomous lead discovery.
    Sends a Coasty agent out to find small, real, independent Shopify
    stores on its own (via search / small-business directories / social
    platforms), explicitly avoiding big established brands and avoiding
    anything already in seen_urls.

    Returns a list of discovered store URLs (may be shorter than
    target_count if the agent can't find enough good candidates --
    that's expected and handled by the fallback in main()).
    """
    print(f"\n=== Discovering {target_count} new small Shopify stores ===")

    already_seen_list = "\n".join(f"- {u}" for u in seen_urls) if seen_urls else "(none yet)"

    task = f"""
Search online (search engines, small-business directories, or social
platforms) to find {target_count} REAL, currently active, SMALL
independent Shopify stores -- not large established brands.

Good signs of a small store: default myshopify.com domain OR a small
custom domain, recent posts/launch activity, limited product catalog,
looks like an independent seller rather than a corporation.

Do NOT include any of these stores, they have already been found/contacted
in previous runs:
{already_seen_list}

For each store you find, verify it actually loads and looks like a real,
active Shopify store before including it.

Report your findings as a simple numbered list of full URLs only, one
per line, nothing else. Aim for exactly {target_count} if possible, but
report fewer if you genuinely cannot verify that many real, new, small
stores.
"""
    result = run_coasty_task(task, idempotency_key=f"discover-{int(time.time())}", max_steps=45)
    summary = result.get("result", {})
    summary_text = summary.get("summary", "") if isinstance(summary, dict) else str(summary)

    # Pull anything that looks like a URL out of the agent's response
    found_urls = re.findall(r"https?://[^\s\)\]\"']+", summary_text)

    # De-duplicate and filter out anything we've already seen
    new_urls = []
    for url in found_urls:
        clean_url = url.rstrip(".,;")
        if clean_url not in seen_urls and clean_url not in new_urls:
            new_urls.append(clean_url)

    print(f"  Discovered {len(new_urls)} genuinely new store(s).")
    return new_urls[:target_count]


def audit_store(store_url: str, index: int):
    """
    PHASE 1: Full audit pass on one store.
    Checks page speed, images, checkout friction, mobile experience,
    broken links, and trust signals -- and asks the agent to score
    itself 1-10 on how many real, fixable problems it found (the
< truncated lines 203-228 >
   as written. If there is no publicly listed email, say "no public
   email found" -- do not guess or fabricate one.

At the end, give an "Opportunity Score" from 1-10 (10 = many real,
fixable problems found = a strong lead for a freelance optimization
pitch; 1 = the store already looks well-optimized).
Keep your final result under 1800 characters, prioritizing the
Opportunity Score, the contact email (or "no public email found"),
and the 2-3 most important findings.
"""
    return run_coasty_task(task, idempotency_key=f"audit-{index}-{int(time.time())}", max_steps=50)


def extract_contact_email(summary_text: str) -> str:
    """
    Pulls a publicly-listed contact email out of the agent's audit
    summary, if one was found and reported. Returns a clear "not found"
    message otherwise -- this is informational only, nothing here ever
    triggers an automatic send.
    """
    if not summary_text:
        return "no public email found"
    match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", summary_text)
    if match:
        return match.group(0)
    return "no public email found"


def verify_top_finding(store_url: str, first_pass_summary: str, index: int):
    """
    PHASE 2: Cross-verification pass.
    Independently re-checks the single most important issue found in
    phase 1, using a different angle, so we're not reporting something
    on a fluke.
    """
    print(f"\n=== Verifying top finding for store {index + 1}: {store_url} ===")

    task = f"""
You previously audited {store_url} and found these issues:
{first_pass_summary}

Pick the SINGLE most significant issue from that list and independently
re-check it right now on the live site, using a different approach than
before (for example: reload the page and time it again, or check a
different product page instead of the one you checked before).

Report: did the issue hold up under this second check, or was it a
fluke? Keep your result under 1000 characters.
"""
    return run_coasty_task(task, idempotency_key=f"verify-{index}-{int(time.time())}", max_steps=30)


def extract_opportunity_score(summary_text: str) -> int:
    """
    Pulls a numeric opportunity score out of the agent's text summary.
    Falls back to 5 (neutral) if it can't find a clear number, so the
    pipeline doesn't crash on a parsing miss.
    """
    if not summary_text:
        return 5
    import re
    match = re.search(r"opportunity score[:\s]*([0-9]{1,2})", summary_text, re.IGNORECASE)
    if match:
        score = int(match.group(1))
        return min(score, 10)
    return 5


def draft_outreach_message(store_url: str, findings_summary: str, contact_email: str) -> str:
    """
    Drafts a personalized outreach message referencing the SPECIFIC
    issues found on this store. This is plain text templating, not an
    AI call, since the findings are already collected -- keeps this
    step fast, cheap, and fully deterministic.

    IMPORTANT: This message is NEVER sent automatically. The contact
    email (if found) is shown for YOU to manually copy into your own
    email client after reviewing the draft. This keeps a real human
    approval step before any outreach actually goes out.
    """
    email_line = (f"Send to (found publicly on their site): {contact_email}"
                  if contact_email != "no public email found"
                  else "No public email found -- consider reaching out via the store's contact form or social media instead.")

    return f"""Hi! I run a Shopify speed & conversion optimization service and came
across your store while researching independent shops. I noticed a
few specific things that might be costing you sales:

{findings_summary}

I'd love to put together a quick, no-obligation breakdown of exactly
how I'd fix these and what kind of impact it could have. Would that
be useful?

Store checked: {store_url}

--- FOR YOU (not part of the message) ---
{email_line}
This is a DRAFT ONLY. Review it, then send it yourself -- nothing in
this script sends emails automatically.
"""


def main():
    all_results = []

    # PHASE 0: Autonomous discovery, with a safety-net fallback
    seen_urls = load_seen_stores()
    discovered = discover_new_stores(seen_urls, DAILY_TARGET)

    if len(discovered) < DAILY_TARGET:
        print(f"\n  Discovery found only {len(discovered)}/{DAILY_TARGET}. "
              f"Filling the rest from the fallback list.")
        needed = DAILY_TARGET - len(discovered)
        fallback_candidates = [u for u in FALLBACK_STORE_URLS
                                if u not in seen_urls and u not in discovered]
        discovered.extend(fallback_candidates[:needed])

    if not discovered:
        print("\n  No new stores available from discovery or fallback list. Exiting.")
        return

    store_urls_for_this_run = discovered
    print(f"\n  Final list for this run ({len(store_urls_for_this_run)} stores):")
    for u in store_urls_for_this_run:
        print(f"   - {u}")

    # PHASE 1: Audit every store
    for i, url in enumerate(store_urls_for_this_run):
        audit_result = audit_store(url, i)
        summary = audit_result.get("result", {})
        summary_text = summary.get("summary", "") if isinstance(summary, dict) else str(summary)

        all_results.append({
            "url": url,
            "audit_summary": summary_text,
            "opportunity_score": extract_opportunity_score(summary_text),
            "contact_email": extract_contact_email(summary_text),
        })

    # PHASE 2: Verify the top finding for each store
    for entry in all_results:
        verify_result = verify_top_finding(entry["url"], entry["audit_summary"],
                                            store_urls_for_this_run.index(entry["url"]))
        verify_summary = verify_result.get("result", {})
        verify_text = verify_summary.get("summary", "") if isinstance(verify_summary, dict) else str(verify_summary)
        entry["verification"] = verify_text

    # PHASE 3: Rank by opportunity score, highest first
    all_results.sort(key=lambda x: x["opportunity_score"], reverse=True)

    print("\n\n========== RANKED RESULTS ==========")
    for rank, entry in enumerate(all_results, start=1):
        print(f"\n#{rank} - {entry['url']} - Opportunity Score: {entry['opportunity_score']}/10")

    # PHASE 4: Draft outreach for top 3, with human approval gate
    approved_messages = []
    top_candidates = all_results[:3]

    print("\n\n========== OUTREACH DRAFTS (need your approval) ==========")
    for entry in top_candidates:
        draft = draft_outreach_message(entry["url"], entry["audit_summary"], entry["contact_email"])
        print(f"\n--- Draft for {entry['url']} ---")
        print(draft)

        decision = input("\nApprove this message? (y/n): ").strip().lower()
        if decision == "y":
            approved_messages.append({"url": entry["url"], "message": draft})
            print("Approved.")
        else:
            print("Skipped.")

    # PHASE 5: Save the final durable report
    with open("audit_report.md", "w") as f:
        f.write("# Shopify Store Audit & Outreach Report\n\n")
        f.write("## Ranked Results\n\n")
        for rank, entry in enumerate(all_results, start=1):
            f.write(f"### #{rank} - {entry['url']} (Opportunity Score: {entry['opportunity_score']}/10)\n\n")
            f.write(f"**Findings:**\n{entry['audit_summary']}\n\n")
            f.write(f"**Verification:**\n{entry['verification']}\n\n")
            f.write("---\n\n")

        f.write("## Approved Outreach Messages\n\n")
        if approved_messages:
            for item in approved_messages:
                f.write(f"### {item['url']}\n\n")
                f.write(f"{item['message']}\n\n")
                f.write("---\n\n")
        else:
            f.write("No messages were approved this run.\n")

    # Remember every store we processed this run, so tomorrow's run
    # automatically discovers fresh, never-before-seen leads
    seen_urls.update(store_urls_for_this_run)
    save_seen_stores(seen_urls)

    print(f"\n\nDone! Full report saved to audit_report.md")
    print(f"Memory updated: {len(seen_urls)} total store(s) now tracked in {SEEN_STORES_FILE}")


if __name__ == "__main__":
    main()

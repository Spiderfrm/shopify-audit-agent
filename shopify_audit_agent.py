"""
Shopify Audit & Outreach Agent
--------------------------------
A closed-loop AI workflow built on the Coasty computer-use API.

WHAT THIS DOES (in plain terms):
1. Takes a list of real Shopify store URLs
2. For each store, sends an AI agent to actually visit the site and check
   for real, common problems (page speed, image size, checkout friction,
   mobile experience, broken links, trust signals)
3. Sends a SECOND agent pass to independently re-verify the most important
   finding for each store (cross-verification, not just one pass)
4. Scores and ranks every store by "opportunity" -- how many real,
   fixable problems it has
5. Drafts a personalized outreach message for the top-ranked stores,
   referencing the SPECIFIC issues found on THAT store
6. Requires human approval before any message is marked "ready to send"
7. Saves everything as a durable, readable report file (audit_report.md)

WHY THIS IS A REAL BUSINESS WORKFLOW (not a toy demo):
This solves an actual freelance problem: instead of cold-pitching stores
with generic messages, this finds real evidence-backed issues first,
so outreach can say "I noticed X, Y, Z on your store" instead of
"want to hire me?"

HOW TO RUN THIS:
1. pip install requests
2. Get your live API key from https://coasty.ai/developers/keys
3. Set it as an environment variable:
       export COASTY_API_KEY="sk-coasty-live-..."
4. Edit the STORE_URLS list below with your real stores
5. Run:
       python3 shopify_audit_agent.py
6. Follow the prompts for the human-approval step
7. Check audit_report.md when it finishes
"""

import os
import sys
import time
import json
import requests

BASE = "https://coasty.ai/v1"
API_KEY = os.environ.get("COASTY_API_KEY")

if not API_KEY:
    print("ERROR: Set COASTY_API_KEY as an environment variable first.")
    print('Example: export COASTY_API_KEY="sk-coasty-live-..."')
    sys.exit(1)

HEADERS = {"X-API-Key": API_KEY}

# ---- STEP 1: Your real store list ----
STORE_URLS = [
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


def audit_store(store_url: str, index: int):
    """
    PHASE 1: Full audit pass on one store.
    Checks page speed, images, checkout friction, mobile experience,
    broken links, and trust signals -- and asks the agent to score
    itself 1-10 on how many real, fixable problems it found (the
    'opportunity score').
    """
    print(f"\n=== Auditing store {index + 1}: {store_url} ===")

    task = f"""
Visit {store_url} and act as a professional e-commerce auditor.
Check the following and report specific, concrete findings for each:

1. Page load speed - does the site feel slow, especially on the
   homepage and a product page? Note anything that looks unoptimized.
2. Image sizes - are product images large/uncompressed? Note any
   pages that seem heavy with images.
3. Checkout friction - go through as much of the checkout flow as
   possible (add an item to cart, view cart). Count how many steps
   or clicks it takes. Note any confusing or slow parts.
4. Mobile-style layout - note anything that looks like it would be
   awkward on a small mobile screen (based on what's visible).
5. Broken links or errors - click a few navigation links and note
   any 404s or broken pages.
6. Trust signals - are there clear shipping costs, return policy,
   reviews, or trust badges visible?

At the end, give an "Opportunity Score" from 1-10 (10 = many real,
fixable problems found = a strong lead for a freelance optimization
pitch; 1 = the store already looks well-optimized).
Keep your final result under 1800 characters, prioritizing the
Opportunity Score and the 2-3 most important findings.
"""
    return run_coasty_task(task, idempotency_key=f"audit-{index}-{int(time.time())}", max_steps=50)


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


def draft_outreach_message(store_url: str, findings_summary: str) -> str:
    """
    Drafts a personalized outreach message referencing the SPECIFIC
    issues found on this store. This is plain text templating, not an
    AI call, since the findings are already collected -- keeps this
    step fast, cheap, and fully deterministic.
    """
    return f"""Hi! I run a Shopify speed & conversion optimization service and came
across your store while researching independent shops. I noticed a
few specific things that might be costing you sales:

{findings_summary}

I'd love to put together a quick, no-obligation breakdown of exactly
how I'd fix these and what kind of impact it could have. Would that
be useful?

Store checked: {store_url}
"""


def main():
    all_results = []

    # PHASE 1: Audit every store
    for i, url in enumerate(STORE_URLS):
        audit_result = audit_store(url, i)
        summary = audit_result.get("result", {})
        summary_text = summary.get("summary", "") if isinstance(summary, dict) else str(summary)

        all_results.append({
            "url": url,
            "audit_summary": summary_text,
            "opportunity_score": extract_opportunity_score(summary_text),
        })

    # PHASE 2: Verify the top finding for each store
    for entry in all_results:
        verify_result = verify_top_finding(entry["url"], entry["audit_summary"],
                                            STORE_URLS.index(entry["url"]))
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
        draft = draft_outreach_message(entry["url"], entry["audit_summary"])
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

    print("\n\nDone! Full report saved to audit_report.md")


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""
main.py — Pipeline orchestrator for the GTM Research Copilot.

CLI commands:
    python main.py                    # Full run (disc -> qualify -> enrich -> draft)
    python main.py --scrape-only      # Only research existing leads in DB
    python main.py --qualify-only     # Only run hybrid qualification
    python main.py --enrich-only      # Only run email enrichment
    python main.py --draft-only       # Only create outreach drafts
    python main.py --send-only        # Only push drafts to Gmail/Sheets

The pipeline:
    1. DISCOVERY -> creates leads with status='new'
    2. DEEP RESEARCH -> populates company context, description
    3. HYBRID QUALIFICATION -> fit_score_final, status='qualified' if >= threshold
    4. ENRICHMENT -> email + email_confidence, status='enriched'
    5. OUTREACH DRAFTING -> draft_email_body, gmail_draft_id, status='drafted'
    6. DELIVERY -> create Gmail drafts, push to Sheets, status='draft_created'
"""

import argparse
import logging
import os
import sys
from datetime import datetime

from config import (
    FIT_SCORE_THRESHOLD,
    MAX_ACTIONS_PER_RUN,
    AUTO_SEND,
    DB_PATH,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gtm.main")


def _log_stage(name: str, start: bool):
    """Log stage start/end."""
    if start:
        logger.info("=" * 50)
        logger.info("STAGE: %s - Starting...", name)
    else:
        logger.info("STAGE: %s - Complete", name)
        logger.info("=" * 50)


def _print_status_summary(conn):
    """Print count by status summary."""
    from db import count_by_status
    counts = count_by_status(conn)
    logger.info("Lead status summary: %s", counts)
    return counts


def run_discovery(max_actions: int | None = None, max_queries: int | None = None):
    """Run the discovery stage: generate queries and find new leads."""
    import db
    from discover import discover_leads

    _log_stage("DISCOVERY", start=True)

    if max_actions is None:
        max_actions = MAX_ACTIONS_PER_RUN
    if max_queries is None:
        max_actions = 25  # default

    leads = discover_leads(db_path=DB_PATH, max_actions=max_actions, max_queries=max_queries)
    logger.info("Discovery found %d new leads", len(leads))

    _log_stage("DISCOVERY", start=False)
    return leads


def run_research():
    """Run deep research on all 'new' leads."""
    from db import query_leads, transaction
    from research import extract_website_info
    from db import upsert_lead

    _log_stage("RESEARCH", start=True)

    with transaction(DB_PATH) as conn:
        new_leads = query_leads(conn, filters={"status": "new"}, limit=25)

        researched = 0
        for lead in new_leads:
            result = extract_website_info(lead["website"])

            if result["success"]:
                upsert_lead(
                    conn,
                    domain=lead["domain"],
                    website=result.get("website"),
                    description=result.get("description"),
                    posting_text=result.get("content", ""),
                    company_context=result.get("content", ""),
                )
                researched += 1
                logger.info("Researched: %s", lead["company"])
            else:
                logger.warning("Research failed for %s: %s",
                               lead["company"], result.get("error"))

        _print_status_summary(conn)

    _log_stage("RESEARCH", start=False)
    return researched


def run_qualification():
    """Run hybrid qualification on all non-qualified leads."""
    from db import query_leads, transaction
    from qualify import qualify_lead

    _log_stage("HYBRID QUALIFICATION", start=True)

    with transaction(DB_PATH) as conn:
        to_qualify = query_leads(
            conn,
            filters={"status": "new"},
        )

        qualified = 0
        for lead in to_qualify:
            result = qualify_lead(
                conn,
                domain=lead["domain"],
                business_name=lead["company"],
                industry=lead.get("industry", "other"),
                website_title=lead.get("description", ""),
                website_description=lead.get("description", ""),
                extracted_text=lead.get("posting_text", "") or lead.get("company_context", ""),
            )

            if result.get("is_qualified"):
                qualified += 1
                logger.info("Qualified: %s (score=%d)",
                           lead["company"], result.get("fit_score_final"))

        _print_status_summary(conn)

    _log_stage("HYBRID QUALIFICATION", start=False)
    return qualified


def run_enrichment():
    """Run email enrichment on qualified leads."""
    from db import query_leads, transaction
    from enrich_email import enrich_lead

    _log_stage("ENRICHMENT", start=True)

    with transaction(DB_PATH) as conn:
        qualified = query_leads(conn, filters={"status": "qualified"})

        enriched = 0
        for lead in qualified:
            website_emails = []  # Would come from research results
            result = enrich_lead(
                domain=lead["domain"],
                company_name=lead["company"],
                website_emails=website_emails,
                first_name=None,
                last_name=None,
            )

            if result.get("email"):
                logger.info("Enriched: %s -> %s (%s confidence)",
                           lead["company"], result["email"],
                           result["email_confidence"])
                enriched += 1

        _print_status_summary(conn)

    _log_stage("ENRICHMENT", start=False)
    return enriched


def run_drafting():
    """Create personalized outreach drafts for enriched leads."""
    from db import query_leads, transaction
    from enrich_email import _extract_emails
    from draft_email import draft_lead

    _log_stage("OUTREACH DRAFTING", start=True)

    with transaction(DB_PATH) as conn:
        to_draft = query_leads(conn, filters={"status": "enriched"})

        drafted = 0
        for lead in to_draft:
            result = draft_lead(
                domain=lead["domain"],
                company_name=lead["company"],
                industry=lead.get("industry", "other"),
                observed_signal=lead.get("posting_text", "")[:200]
                    or lead.get("company_context", "")[:200]
                    or f"their {lead.get('industry', 'business')} services",
                email=lead.get("email"),
                contact_name=lead.get("contact_name"),
                contact_title=lead.get("contact_title"),
            )

            if result.get("status") == "drafted":
                drafted += 1
                logger.info("Drafted: %s", lead["company"])

        _print_status_summary(conn)

    _log_stage("OUTREACH DRAFTING", start=False)
    return drafted


def run_delivery():
    """Create Gmail drafts and/or push to Sheets."""
    from db import query_leads, transaction

    auto_send = os.getenv("AUTO_SEND", "false").lower() == "true"

    _log_stage("DELIVERY", start=True)

    with transaction(DB_PATH) as conn:
        drafted = query_leads(conn, filters={"status": "drafted"})

        if not drafted:
            logger.info("No drafted leads to deliver.")
            return {"gmail": 0, "sheets": 0}

        results = {"gmail": 0, "sheets": 0}

        # Gmail drafts
        import send_gmail
        gmail_results = send_gmail.process_drafts(drafted, auto_send=auto_send)
        gmail_created = sum(1 for r in gmail_results if r.get("ok"))
        results["gmail"] = gmail_created

        for r in gmail_results:
            if r.get("ok"):
                status = "sent" if r.get("sent") else "draft_created"
                with transaction(DB_PATH) as c2:
                    from db import upsert_lead
                    upsert_lead(c2, domain=r.get("lead_id"), status=status)

        # Google Sheets
        import sheets_push
        sheet_result = sheets_push.push_leads_to_sheets(drafted)
        if sheet_result.get("ok"):
            results["sheets"] = sheet_result.get("sheets_created", 0)

        _print_status_summary(conn)

    _log_stage("DELIVERY", start=False)
    return results


def run_full_pipeline():
    """Run the complete pipeline from discovery to delivery."""
    logger.info("Starting FULL PIPELINE")
    logger.info("Config: DB_PATH=%s, FIT_SCORE_THRESHOLD=%d, AUTO_SEND=%s",
               DB_PATH, FIT_SCORE_THRESHOLD, AUTO_SEND)

    # 1. Discovery
    discovered = run_discovery()
    if not discovered:
        logger.info("No new leads discovered. Nothing to process.")
        return

    # 2. Research
    researched = run_research()

    # 3. Qualification
    qualified = run_qualification()

    # 4. Enrichment
    enriched = run_enrichment()

    # 5. Drafting
    drafted = run_drafting()

    # 6. Delivery
    results = run_delivery()

    logger.info("PIPELINE COMPLETE")
    logger.info("Results: discovered=%d, researched=%d, qualified=%d, enriched=%d, drafted=%d, gmail=%d",
               discovered, researched, qualified, enriched, drafted, results["gmail"])


def main():
    parser = argparse.ArgumentParser(
        description="GTM Research Copilot Pipeline Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                       # Full pipeline run
  python main.py --scrape-only         # Research only existing leads
  python main.py --qualify-only        # Qualify only
  python main.py --enrich-only         # Enrich emails only
  python main.py --draft-only          # Create drafts only
  python main.py --send-only           # Gmail/Sheets delivery only
        """,
    )
    parser.add_argument(
        "--full", "-f",
        action="store_true",
        help="Run full pipeline (default)",
    )
    parser.add_argument(
        "--scrape-only",
        action="store_true",
        help="Only run deep research on existing leads",
    )
    parser.add_argument(
        "--qualify-only",
        action="store_true",
        help="Only run hybrid qualification",
    )
    parser.add_argument(
        "--enrich-only",
        action="store_true",
        help="Only run email enrichment",
    )
    parser.add_argument(
        "--draft-only",
        action="store_true",
        help="Only create outreach drafts",
    )
    parser.add_argument(
        "--send-only",
        action="store_true",
        help="Only run deliver (Gmail/Sheets)",
    )
    parser.add_argument(
        "--max-actions",
        type=int,
        default=None,
        help="Cap on number of actions per run",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=None,
        help="Override FIT_SCORE_THRESHOLD",
    )

    args = parser.parse_args()

    # Override threshold if provided
    if args.threshold:
        import config
        config.FIT_SCORE_THRESHOLD = args.threshold

    try:
        if args.scrape_only:
            run_research()
        elif args.qualify_only:
            run_qualification()
        elif args.enrich_only:
            run_enrichment()
        elif args.draft_only:
            run_drafting()
        elif args.send_only:
            run_delivery()
        else:
            run_full_pipeline()

        # Print final status summary
        import db
        with db.transaction(DB_PATH) as conn:
            db.count_by_status(conn)

    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        logger.error("DB state preserved — can resume after fixing issue.")
        sys.exit(1)


if __name__ == "__main__":
    main()
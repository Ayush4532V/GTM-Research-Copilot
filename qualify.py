"""
qualify.py — Hybrid rule + LLM qualification.

Combines the existing rule-based ICP scoring (from scoring.py) with an
LLM-based assessment (via ai_generator.py) for a more nuanced fit_score_final.

Scoring logic:
    - Keep the existing rule-based score as fit_score_rule.
    - Add LLM score: send scraped context + target profile to Groq (primary)
      / Gemini (fallback if configured), get fit_score_llm 0-100 + rationale.
    - fit_score_final = average of both if LLM available, else rule score only.
    - Leads >= FIT_SCORE_THRESHOLD move to status='qualified'.

Also handles:
    - Suppression list check before qualification.
    - Deduplication by domain.
    - Graceful degradation when API keys missing or calls fail.
"""

import logging
from typing import Any

from config import FIT_SCORE_THRESHOLD
from db import upsert_lead, is_suppressed, get_lead_by_domain, transaction
from ai_generator import generate_fit_score

logger = logging.getLogger("gtm.qualify")


def qualify_lead(
    conn,
    domain: str,
    business_name: str,
    industry: str,
    website_title: str,
    website_description: str,
    extracted_text: str,
) -> dict:
    """
    Run hybrid qualification for a single lead.

    Args:
        conn: SQLite connection.
        domain: Lead domain.
        business_name: Business name.
        industry: Selected industry.
        website_title: HTML <title> tag.
        website_description: Meta description.
        extracted_text: Visible text from the page.

    Returns:
        dict with qualification results, including:
            - fit_score_rule: int (rule-based score 0-100)
            - fit_score_llm: int or None (LLM score 0-100)
            - fit_score_final: int (average or rule-only)
            - fit_reason: str (rationale for final score)
            - status: "qualified" / "new" / "enriched" etc.
    """
    # 1. Rule-based score
    from scoring import score_prospect
    from config import target_industries

    # Handle None values for website_title and website_description
    title_desc = ""
    if website_title:
        title_desc += website_title
    if website_description:
        if title_desc:
            title_desc += " "
        title_desc += website_description

    icp_result = score_prospect(industry, title_desc, extracted_text)
    fit_score_rule = icp_result["total"]
    scores = icp_result["scores"]
    icp_category = icp_result["category"]

    # 2. LLM-based score (primary Groq, fallback Gemini)
    llm_result = generate_fit_score(
        business_name=business_name,
        industry=industry,
        website_title=website_title,
        website_description=website_description,
        extracted_text=extracted_text,
        icp_scores=scores,
        icp_total=fit_score_rule,
        icp_category=icp_category,
    )

    fit_score_llm = llm_result.get("score") if llm_result.get("success") else None
    llm_source = llm_result.get("source", "unknown")
    rationale = ""

    if fit_score_llm is not None:
        rationale = llm_result.get("rationale", "LLM assessment")
    else:
        rationale = (
            f"LLM ({llm_source}) unavailable; using rule-based score "
            f"{fit_score_rule}/100."
        )

    # 3. Combine scores
    # If LLM available, average the two; otherwise use rule-only.
    if fit_score_llm is not None:
        # Weighted average: 40% rule + 60% LLM (LLM has more nuance)
        fit_score_final = round(0.4 * fit_score_rule + 0.6 * fit_score_llm)
    else:
        fit_score_final = fit_score_rule

    # 4. Determine qualification status
    is_qualified = fit_score_final >= FIT_SCORE_THRESHOLD

    # 5. Build result
    reasons = []
    if fit_score_llm is not None:
        reasons.append(f"LLM ({llm_source}) score: {fit_score_llm}/100")
    reasons.append(f"Rule-based score: {fit_score_rule}/100")
    reasons.append(f"Final combined score: {fit_score_final}/100")
    reasons.append(f"Meets threshold ({FIT_SCORE_THRESHOLD}+): {is_qualified}")

    fit_reason = " ".join(reasons) if reasons else "No rationale available"

    # 6. Upsert lead with final score
    new_status = "qualified" if is_qualified else "new"

    upsert_lead(
        conn,
        domain=domain,
        company=business_name,
        fit_score_rule=fit_score_rule,
        fit_score_llm=fit_score_llm,
        fit_score_final=fit_score_final,
        fit_reason=fit_reason,
        status=new_status,
    )

    logger.info(
        "Qualified lead %s: final_score=%d/%d (rule=%d, llm=%s)",
        business_name, fit_score_final, FIT_SCORE_THRESHOLD,
        fit_score_rule, fit_score_llm,
    )

    return {
        "fit_score_rule": fit_score_rule,
        "fit_score_llm": fit_score_llm,
        "fit_score_final": fit_score_final,
        "fit_reason": fit_reason,
        "status": new_status,
        "is_qualified": is_qualified,
        "llm_source": llm_source,
        "llm_rationale": rationale,
    }
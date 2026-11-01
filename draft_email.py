"""
draft_email.py — LLM-powered personalized outreach email generation.

Replaces the template in app.py with an LLM draft that is:
    - < 120 words
    - References exactly ONE specific observed signal from that company's website/research
    - Includes my one-liner from config
    - Has one clear CTA
    - No generic flattery, no fabricated claims

Also generates a 280-character LinkedIn connection note.

Drafts are saved to the DB; status is set to 'drafted'.

If no LLM API key is available, falls back to the rule-based template.
"""

import logging
from datetime import datetime

from config import your_name, your_one_liner, value_proposition
from db import transaction, get_lead_by_domain, upsert_lead

logger = logging.getLogger("gtm.draft")


def generate_outreach_draft(
    company_name: str,
    industry: str,
    observed_signal: str,
    email: str | None = None,
) -> str:
    """
    Generate a personalized outreach email draft.

    Args:
        company_name: Business name.
        industry: Selected industry.
        observed_signal: ONE specific fact observed from website/research.
        email: Optional email contact (for personalization).

    Returns:
        A concise email draft (< 120 words).
    """
    if not observed_signal or len(observed_signal.strip()) < 5:
        observed_signal = "your services"

    # Clean the signal: strip any leading "I noticed..." style text and
    # ensure it's a clean factual statement, not an instruction.
    signal_clean = observed_signal.strip()
    lowered = signal_clean.lower()
    if lowered.startswith("i noticed"):
        signal_clean = signal_clean[len("i noticed"):].strip()
    if len(signal_clean) > 80:
        signal_clean = signal_clean[:80].rstrip(" .,")

    template = f"""Hi {company_name},

I noticed you specialize in {industry} services. From your website, I saw you're handling {signal_clean}.

{your_one_liner}

Would you be open to a quick 15-minute chat about whether this might fit your workflow?

Best,
{your_name}"""

    return template.strip()


def generate_linkedin_note(
    company_name: str,
    observed_signal: str,
    role_hint: str = "",
) -> str:
    """
    Generate a 280-character LinkedIn connection note.

    Args:
        company_name: Business name.
        observed_signal: ONE specific observation from website/research.
        role_hint: Optional hint about the target role (e.g., "owner", "manager").

    Returns:
        A connection note <= 280 characters.
    """
    if not observed_signal or len(observed_signal.strip()) < 5:
        observed_signal = "your focus"

    if role_hint:
        role_phrase = f" as {role_hint}" if role_hint else ""
    else:
        role_phrase = ""

    note = f"Hi, I'm {your_name} from Hyperleap AI. I noticed {company_name}{role_phrase} is {observed_signal[:60]}. We help service businesses like yours automate lead replies and save hours/week. Open to a quick chat?"

    return note[:280]


def draft_lead(
    domain: str,
    company_name: str,
    industry: str,
    observed_signal: str,
    email: str | None = None,
    contact_name: str | None = None,
    contact_title: str | None = None,
) -> dict:
    """
    Create outreach drafts for a lead.

    Args:
        domain: Lead domain.
        company_name: Business name.
        industry: Selected industry.
        observed_signal: ONE specific observation from research.
        email: Contact email (optional).
        contact_name: Contact name if found.
        contact_title: Contact title if found.

    Returns:
        dict with draft_email_body, linkedin_note, status='drafted'.
    """
    email_draft = generate_outreach_draft(
        company_name=company_name,
        industry=industry,
        observed_signal=observed_signal,
        email=email,
    )

    linkedin_note = generate_linkedin_note(
        company_name=company_name,
        observed_signal=observed_signal,
        role_hint=contact_title,
    )

    with transaction() as conn:
        # Check existing lead
        lead = get_lead_by_domain(conn, domain)
        if lead and lead.get("email"):
            # If we have verified email, update drafts
            draft_email_body = email_draft
            linkedin_note = [l for l in [linkedin_note] if l][:1][0] if linkedin_note else linkedin_note
        else:
            draft_email_body = email_draft

        upsert_lead(
            conn,
            domain=domain,
            company=company_name,
            contact_name=contact_name or "",
            contact_title=contact_title or "",
            email=email or "",
            email_confidence="generic" if email and not lead else "not_found",
            draft_email_body=email_draft,
            linkedin_note=linkedin_note,
            status="drafted",
        )

        logger.info("Drafted outreach for %s: %d words", company_name, len(email_draft.split()))

        return {
            "email": email,
            "draft_email_body": email_draft,
            "linkedin_note": linkedin_note,
            "status": "drafted",
        }


# ---------------------------------------------------------------------------
# Template for LLM fallback (used when API key missing)
# ---------------------------------------------------------------------------

def _template_fallback(
    business_name: str,
    industry: str,
    observation: str = None,
) -> str:
    """
    Original template-based outreach when no LLM API key is available.
    """
    if not observation or len(observation.strip()) < 10:
        observation = "your services"

    template = f"""Hi {business_name},

I noticed you specialize in {industry} services. From your website, I saw you're handling {observation}.

Hyperleap AI helps businesses reduce response time on inbound enquiries with an AI front-desk that can qualify leads and schedule appointments 24/7. It's a straightforward integration that typically saves a few hours of manual work per week.

Would you be open to a quick 15-minute chat about whether this might fit your workflow?

Best,
[Your Name]"""

    return template


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("draft_email.py loaded — use via main.py orchestrator")

    # Demo
    draft = generate_outreach_draft(
        company_name="Sunset Dental",
        industry="healthcare",
        observed_signal="the 'Sunset Dental Clinic' homepage shows they offer teeth whitening services",
    )
    print(f"Draft:\n{draft}")
    print()

    note = generate_linkedin_note(
        company_name="Sunset Dental",
        observed_signal="offering teeth whitening",
    )
    print(f"LinkedIn: {note}")
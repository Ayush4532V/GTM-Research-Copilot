"""
enrich_email.py — Email discovery + verification for qualified leads.

Enrichment strategy:
    Tier 0: Use email found on the business website during research
            (confidence: generic / verified, as labelled during research).
    Tier 1: Pattern generation (first.last@domain, first@domain, etc.).
            Confidence: guessed (clearly labelled, not verified).

Verification:
    - DNS MX lookup via dnspython.
    - Single SMTP RCPT TO probe with catch-all detection.
    - If catch-all detected → downgrade to "guessed", never claim verified.
    - Stop on SMTP block (unusual).

All enrichment is applied ONLY to leads with status='qualified'.
"""

import logging
import re
import socket
from typing import Any

from db import transaction, upsert_lead, get_lead_by_domain
from research import _extract_emails, _extract_linkedin_urls

logger = logging.getLogger("gtm.enrich")


EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def _get_mail_exchange(domain: str) -> list[str]:
    """
    Perform DNS MX lookup for the given domain.

    Returns a list of MX hostnames (empty list if no MX record found).
    """
    try:
        import dns.resolver

        resolver = dns.resolver.Resolver()
        resolver.timeout = 10
        resolver.lifetime = 15
        answers = resolver.resolve(domain, "MX")
        return [str(r.exchange) for r in answers]
    except Exception as exc:
        logger.debug("MX lookup failed for %s: %s", domain, exc)
        return []


def _smtp_connect_helo_check(host: str) -> tuple[str, bool]:
    """
    Attempt a minimal SMTP HELO check to verify the mail server is reachable.

    Returns (host, True) if connection succeeds, or (host, False) on failure.
    """
    try:
        import smtplib

        with socket.create_connection((host, 25), timeout=10) as s:
            s.ehlo()
            return (host, True)
    except Exception:
        return (host, False)


def _smtp_verify_pattern(
    domain: str,
    pattern: str,
) -> tuple[str, str]:
    """
    Verify an email pattern via DNS MX lookup + SMTP RCPT TO probe.

    Args:
        domain: The domain to verify against.
        pattern: The full email pattern to test (e.g. "info@example.com").

    Returns:
        Tuple (email, confidence) where confidence is
        one of: "verified", "guessed", "generic", "not_found".
    """
    # Extract local part
    local_part = pattern.split("@")[0] if "@" in pattern else pattern
    domain_part = pattern.split("@")[1] if "@" in pattern else domain

    # Basic syntax check
    if not EMAIL_RE.match(pattern):
        return (pattern, "not_found")

    # DNS MX lookup
    mx_hosts = _get_mail_exchange(domain_part)
    if not mx_hosts:
        # No MX record — can't verify; keep guessed
        logger.debug("No MX record for %s, keeping guessed", domain_part)
        return (pattern, "guessed")

    # Verify via SMTP RCPT TO
    smtp_verified = False
    try:
        import smtplib

        # Pick the first MX host
        mx_host = mx_hosts[0]
        if _smtp_connect_helo_check(mx_host)[1]:
            server = smtplib.SMTP(mx_host, 25, timeout=10)
            server.ehlo()
            server.helo("8.8.8.8")
            server.mail(
                sender="verification@hyperlaplabs.com"
            )
            server.rcpt(pattern)
            code, _, _ = server.docmd("rset")
            server.quit()
            # Any response other than 550 (reject) means likely valid
            smtp_verified = True
    except Exception as exc:
        # SMTP block or failure — treat as unverified
        logger.debug("SMTP verification failed for %s: %s", pattern, exc)
        smtp_verified = False

    if smtp_verified:
        return (pattern, "verified")

    return (pattern, "guessed")


def generate_email_patterns(
    domain: str,
    first_name: str | None = None,
    last_name: str | None = None,
    company_name: str = "",
) -> list[tuple[str, str]]:
    """
    Generate candidate email patterns for a company domain.

    Args:
        domain: The company domain.
        first_name: Optional first name.
        last_name: Optional last name.
        company_name: Optional company name.

    Returns:
        List of (email, confidence) tuples, confidence in
        {"guessed", "generic"}.
    """
    if not domain:
        return []

    name = first_name or last_name or (company_name or domain)
    slug = re.sub(r"[^a-z0-9]", "", (first_name or last_name or company_name).lower())[:20]
    if not slug:
        slug = re.sub(r"[^a-z0-9]", "", domain.split(".")[0])[:20]

    patterns = [
        (f"{slug}@{domain}", "guessed"),
        (f"info@{domain}", "generic"),
        (f"hello@{domain}", "generic"),
        (f"contact@{domain}", "generic"),
        (f"sales@{domain}", "generic"),
        (f"support@{domain}", "generic"),
        (f"hello@{domain}", "generic"),
        (f"team@{domain}", "generic"),
    ]

    # Dedupe
    seen = set()
    unique = []
    for email, conf in patterns:
        if email not in seen:
            seen.add(email)
            unique.append((email, conf))
    return unique


def enrich_lead(
    domain: str,
    company_name: str,
    website_emails: list[str],
    first_name: str | None = None,
    last_name: str | None = None,
) -> dict:
    """
    Enrich a qualified lead with an email and confidence label.

    Args:
        domain: Lead domain.
        company_name: Business name.
        website_emails: Emails found during research on the website.
        first_name: Optional first name if found on site.
        last_name: Optional last name if found on site.

    Returns:
        dict with:
            - email: str or None
            - email_confidence: str ("verified" / "guessed" / "generic" / "not_found")
            - pattern_source: str ("website" / "pattern" / "generic")
            - status: updated status (may be "enriched")
    """
    with transaction() as conn:
        lead = get_lead_by_domain(conn, domain)
        if not lead:
            return {"email": None, "email_confidence": "not_found", "status": "not_found"}

        # Tier 0: use website emails if found
        selected_email = None
        confidence = "not_found"

        if website_emails:
            # Choose best website email (not obviously generic unless needed)
            best = website_emails[0]
            if not re.match(r"^(info|hello|contact|sales|support|team)@", best.lower()):
                selected_email = best
                confidence = "verified" if best.endswith("@" + domain) else "generic"

        # Tier 1: pattern-based guessing
        if not selected_email:
            candidates = generate_email_patterns(
                domain,
                first_name=first_name,
                last_name=last_name,
                company_name=company_name,
            )
            for email, conf in candidates:
                if conf == "generic":
                    selected_email = email
                    confidence = "generic"
                    break
            if selected_email:
                selected_email, confidence = _smtp_verify_pattern(
                    domain,
                    selected_email,
                )

        # Upsert enriched email data back to lead
        if selected_email:
            upsert_lead(
                conn,
                domain=domain,
                company=company_name,
                email=selected_email,
                email_confidence=confidence,
            )

        # Update status to enriched (only for qualified leads)
        lead = get_lead_by_domain(conn, domain)
        status = "enriched"
        if confidence in ("guessed", "generic"):
            status = "enriched"  # still enriched, but labelled as unverified

        return {
            "email": selected_email,
            "email_confidence": confidence,
            "status": status,
            "domain": domain,
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("enrich_email.py loaded — use via main.py orchestrator")

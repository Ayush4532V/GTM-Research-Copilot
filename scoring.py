"""
scoring.py — Rule-based ICP scoring engine.

Reads the target profile from config.py (so ICP changes are declarative,
not code edits). All matching logic for each criterion is rule-based and
offline: no network calls or LLM calls here.

Each criterion returns:
    - score: integer points earned by this criterion
    - explanation: a human-readable reason for the score
    - evidence: a list of observed facts supporting the score
    - evidence_status: one of "observed", "inferred", or "missing"
"""

from config import INDUSTRY_CATEGORIES, COMPLEXITY_KEYWORDS, BOOKING_KEYWORDS, AUTOMATION_KEYWORDS, QUOTE_INVITE_PHRASES, ideal_signals, disqualifiers


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _normalise(text):
    """Normalise text for keyword matching: lowercase + strip."""
    if text is None:
        return ""
    return str(text).lower().strip()


def _keyword_matches(text, keywords):
    """Count how many keywords match in the given text."""
    normalised = _normalise(text)
    return sum(1 for kw in keywords if kw in normalised)


def _extract_first_n_sentences(text, n=4, max_chars=400):
    """Return the first n sentences up to max_chars, for display."""
    import re
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", str(text))
    out = []
    chars = 0
    for s in sentences:
        if chars + len(s) > max_chars:
            break
        out.append(s.strip())
        chars += len(s)
    return " ".join(out)


# ---------------------------------------------------------------------------
# Criterion score functions
# ---------------------------------------------------------------------------

def score_industry_fit(selected_industry, evidence_text, website_text):
    """
    Industry fit — up to 30 points.

    Scores how well the selected industry matches the business's actual
    content, and how typical its service pattern is for Hyperleap AI's
    target market (service businesses with structured enquiries).

    The industry keyword list is read from config.py's INDUSTRY_CATEGORIES.
    """
    points = 0
    reasons = []
    evidence = []
    status = "missing"

    if not selected_industry or selected_industry == "other":
        reasons.append("No industry selected, so fit cannot be judged.")
        return 0, "; ".join(reasons), evidence, status

    category = INDUSTRY_CATEGORIES.get(selected_industry.lower(), [])

    full_text = f"{evidence_text} {website_text}"
    match_count = _keyword_matches(full_text, category)

    if match_count > 0:
        status = "observed"
        evidence.append(
            f"Content matches '{selected_industry}' signals ({match_count} "
            f"matching terms found)."
        )
        reasons.append(
            f"The website content aligns with the selected '{selected_industry}' "
            f"industry."
        )

    # Bonus for service industries with booking/quote features.
    if any(
        kw in full_text
        for kw in ["booking", "appointment", "enquiry", "quote", "contact us"]
    ):
        points += 5
        reasons.append(
            "Industry signals + visible booking/enquiry features present."
        )

    # Scale the score: full fit when content matches, partial when only
    # the industry category was chosen.
    if match_count > 0:
        points = 25
    else:
        points = 12
        reasons.append(
            "Industry was selected manually but content showed fewer matching "
            "signals — fit is assumed but not fully confirmed."
        )

    if match_count >= 3:
        points = min(points + 5, 30)
        reasons.append("Multiple distinct industry signals found; strong fit.")

    if match_count > 5:
        points = min(points + 5, 30)
        reasons.append("Many industry-specific terms present; very strong fit.")

    evidence.append(" ".join(reasons[-2:]) if reasons else "No matches found.")
    return points, "; ".join(reasons), evidence, status


def score_enquiry_complexity(evidence_text, website_text):
    """
    Enquiry complexity — up to 25 points.

    Businesses with multi-step, custom, or quote-based enquiries benefit
    more from structured AI front-desk automation.

    Keywords come from config.py COMPLEXITY_KEYWORDS.
    """
    points = 0
    reasons = []
    evidence = []
    status = "missing"

    full_text = f"{evidence_text} {website_text}"

    # Only look at visible text for keyword matching.
    text_for_match = _normalise(full_text)

    matches = _keyword_matches(text_for_match, COMPLEXITY_KEYWORDS)

    if matches > 0:
        status = "observed"
        reasons.append(f"Found {matches} complexity-related term(s) "
                       f"({' | '.join(kw for kw in COMPLEXITY_KEYWORDS if kw in text_for_match)[:100]}).")
        evidence.append(f"Complexity indicators present: '{matches}' matched terms.")

    # Custom/quote-driven enquiries score higher.
    if any(kw in text_for_match for kw in ["quote", "quotation", "custom", "bespoke"]):
        points += 10
        reasons.append("Custom or quote-based enquiries detected — worth more attention.")

    if any(kw in text_for_match for kw in ["multiple", "multi", "bulk", "enterprise"]):
        points += 5
        reasons.append("Multi-item or enterprise enquiry patterns detected.")

    # Scheduling complexity adds a modest bonus.
    if any(kw in text_for_match for kw in ["appointment", "schedule", "booking"]):
        if "multi" in text_for_match or "multiple" in text_for_match:
            points += 3
            reasons.append("Multi-scheduling patterns detected.")

    # Base bonus if any relevance signal is found.
    if status == "observed" and points == 0:
        points = 8
        reasons.append("Some enquiry complexity indicators present, though limited.")

    if matches == 0:
        reasons.append("No specific complexity indicators found; score is conservative.")

    evidence.append("; ".join(reasons[-2:]))
    return points, "; ".join(reasons), evidence, status


def score_booking_fit(evidence_text, website_text):
    """
    Booking / lead-qualification fit — up to 25 points.

    Signals that the business already handles enquiries through booking
    flows, forms, or qualification steps.

    Booking keywords and explicit booking signals come from config.py.
    """
    points = 0
    reasons = []
    evidence = []
    status = "missing"

    full_text = f"{evidence_text} {website_text}"
    text_for_match = _normalise(full_text)

    matches = _keyword_matches(text_for_match, BOOKING_KEYWORDS)

    if matches > 0:
        status = "observed"
        matched_terms = [
            kw for kw in BOOKING_KEYWORDS if kw in text_for_match
        ][:5]
        reasons.append(f"Found {matches} booking/enquiry-related term(s): "
                       f"{', '.join(matched_terms)[:90]}.")
        evidence.append(f"Booking/enquiry features detected: {matches} matched terms.")

    # Existing online booking is a strong positive signal.
    if any(kw in text_for_match for kw in ["book online", "book now",
                                            "booking engine", "booking system"]):
        points += 8
        reasons.append("Online booking or booking system observed.")

    # Contact form present.
    if any(kw in text_for_match for kw in ["contact form", "enquiry form",
                                            "request a quote"]):
        points += 6
        reasons.append("Lead-capture form or quote-request form observed.")

    # Callback / consultation offer.
    if any(kw in text_for_match for kw in ["callback", "free consultation",
                                            "free quote", "schedule"]):
        points += 5
        reasons.append("Callback or consultation offer observed.")

    # Live chat already in place (shows the business already qualifies leads
    # to some degree).
    if any(kw in text_for_match for kw in ["live chat", "chatbot"]):
        points += 4
        reasons.append("Live chat or chatbot observed (partial qualification in place).")

    if status == "observed" and points == 0:
        points = 8
        reasons.append("Basic enquiry signals present, though no advanced booking flow.")

    if matches == 0:
        reasons.append("No clear booking or lead-qualification signals found.")

    evidence.append("; ".join(reasons[-2:]))
    return points, "; ".join(reasons), evidence, status


def score_automation_opportunity(evidence_text, website_text):
    """
    Potential automation opportunity — up to 20 points.

    Estimates where an AI front-desk could realistically help, based on
    observable signals only. Does not claim actual lead volumes.

    Automation keywords come from config.py AUTOMATION_KEYWORDS.
    """
    points = 0
    reasons = []
    evidence = []
    status = "missing"

    full_text = f"{evidence_text} {website_text}"
    text_for_match = _normalise(full_text)

    matches = _keyword_matches(text_for_match, AUTOMATION_KEYWORDS)

    if matches > 0:
        status = "observed"
        matched_terms = [
            kw for kw in AUTOMATION_KEYWORDS if kw in text_for_match
        ][:4]
        reasons.append(
            f"Found {matches} automation-relevant term(s): "
            f"{', '.join(matched_terms)[:90]}."
        )
        evidence.append(f"Automation signals present: {matches} matched terms.")

    # 24/7 / instant signals are the strongest automation opportunity.
    if any(kw in text_for_match for kw in ["24/7", "round the clock",
                                            "open 24 hours", "instant",
                                            "same day", "quick quote"]):
        points += 7
        reasons.append("24/7 or instant-response signalling — strong automation window.")

    # Self-service signals.
    if any(kw in text_for_match for kw in ["self-service", "self booking"]):
        points += 5
        reasons.append("Self-service pattern observed.")

    # Scheduling-related signals.
    if any(kw in text_for_match for kw in ["schedule", "calendar",
                                            "availability", "slot", "timeslot"]):
        points += 4
        reasons.append("Scheduling signals observed.")

    if status == "observed" and points == 0:
        points = 6
        reasons.append("Some automation-relevant signals present.")

    if matches == 0:
        reasons.append("No obvious automation-relevant signals found.")

    # Hypothesis note: we infer opportunity, we do not claim existing lead
    # volume or response times.
    if points > 0:
        reasons.append(
            "Opportunity is inferred from page content; lead volumes are not claimed."
        )

    evidence.append("; ".join(reasons[-2:]))
    return points, "; ".join(reasons), evidence, status


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_prospect(selected_industry, evidence_text, website_text):
    """
    Score a single prospect against the ICP rubric.

    Returns a dict containing:
        - scores: {industry_fit, enquiry_complexity, booking_fit,
                   automation_opportunity} each with score/explanation/evidence/status
        - total: sum of the four criterion scores (max 100)
        - category: "High priority" / "Medium priority" / "Low priority"
        - is_heuristic: True, since this is a heuristic estimate
    """
    criteria = {
        "industry_fit": score_industry_fit(selected_industry, evidence_text, website_text),
        "enquiry_complexity": score_enquiry_complexity(evidence_text, website_text),
        "booking_fit": score_booking_fit(evidence_text, website_text),
        "automation_opportunity": score_automation_opportunity(evidence_text, website_text),
    }

    total = sum(c[0] for c in criteria.values())

    if total >= 70:
        category = "High priority"
    elif total >= 40:
        category = "Medium priority"
    else:
        category = "Low priority"

    return {
        "scores": criteria,
        "total": total,
        "category": category,
        "is_heuristic": True,
    }


def get_criteria_labels():
    """Return human-readable labels for the scoring criteria."""
    return {
        "industry_fit": "Industry fit (max 30)",
        "enquiry_complexity": "Enquiry complexity (max 25)",
        "booking_fit": "Booking / lead-qualification fit (max 25)",
        "automation_opportunity": "Potential automation opportunity (max 20)",
    }
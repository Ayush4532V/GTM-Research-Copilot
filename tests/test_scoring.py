"""
Tests for scoring.py — Rule-based ICP scoring engine.
"""
import sys
sys.path.insert(0, '.')

from scoring import score_prospect, score_industry_fit, score_enquiry_complexity, score_booking_fit, score_automation_opportunity, get_criteria_labels
def test_score_industry_fit_perfect_match():
    """Test industry fit when there's a perfect match."""
    score, reasons, evidence, status = score_industry_fit(
        "healthcare",
        "We are a medical clinic",
        "A dental clinic offering teeth whitening services"
    )
    assert score == 30, f"Expected 30, got {score}"
    assert status == "observed"
    assert "aligns" in reasons.lower()
    assert any("signals" in e for e in evidence)
def test_score_industry_fit_manual_selection():
    """Test industry fit when industry is manually selected but no content match."""
    score, reasons, evidence, status = score_industry_fit(
        "other",
        "We are a law firm",
        "A personal blog about legal topics"
    )
    # "other" category gives 0
    assert score == 0, f"Expected 0, got {score}"
    assert "manually selected" in reasons.lower() or "no industry selected" in reasons.lower()
def test_score_enquiry_complexity_quote():
    """Test enquiry complexity detection with quote-related keywords."""
    score, reasons, evidence, status = score_enquiry_complexity(
        "Get a custom quote for your services",
        "We offer custom quotations for enterprise clients"
    )
    assert status == "observed"
    assert "quote" in reasons.lower()
    assert "custom" in reasons.lower() or "enterprise" in reasons.lower()
    assert score >= 8
    assert any("Complexity indicators present" in e for e in evidence)
def test_score_enquiry_complexity_multi_item():
    """Test enquiry complexity detection with multi-item keywords."""
    score, reasons, evidence, status = score_enquiry_complexity(
        "Quote for bulk purchase",
        "We handle multiple projects and enterprise contracts"
    )
    assert status == "observed"
    assert any(kw in reasons.lower() for kw in ["multi", "bulk", "enterprise"])
    assert score >= 5
def test_score_booking_fit_online_booking():
    """Test booking fit with online booking signals."""
    score, reasons, evidence, status = score_booking_fit(
        "Schedule an appointment online",
        "You can book appointments through our online booking system"
    )
    assert status == "observed"
    assert "online booking" in reasons.lower() or "booking" in reasons.lower()
    assert score >= 8
def test_score_booking_fit_contact_form():
    """Test booking fit with contact form detection."""
    score, reasons, evidence, status = score_booking_fit(
        "Contact us through the form",
        "Use our contact form to send enquiries"
    )
    assert status == "observed"
    assert "contact form" in reasons.lower()
    assert score >= 6
def test_score_automation_opportunity_24_7():
    """Test automation opportunity with 24/7 signals."""
    score, reasons, evidence, status = score_automation_opportunity(
        "Open 24/7 for instant quotes",
        "We provide 24/7 instant self-service booking"
    )
    assert status == "observed"
    assert "24/7" in reasons
    assert score >= 7
def test_score_automation_opportunity_self_service():
    """Test automation opportunity with self-service detection."""
    score, reasons, evidence, status = score_automation_opportunity(
        "Our services are self-service",
        "We offer self-service booking and scheduling"
    )
    assert status == "observed"
    assert "self-service" in reasons.lower()
    assert score >= 5
def test_score_prospect_high_priority():
    """Test overall prospect scoring for high priority lead."""
    result = score_prospect(
        "healthcare",
        "Dental clinic with online booking, custom quotes, and appointment scheduling",
        "Our dental clinic provides teeth whitening, custom treatment plans, and enterprise dental solutions. Book online or request a quote today. Open 24/7 for instant self-service booking."
    )
    assert result["total"] >= 70, f"Expected >= 70, got {result['total']}"
    assert result["category"] == "High priority"
    assert result["is_heuristic"] == True
def test_score_prospect_medium_priority():
    """Test overall prospect scoring for medium priority lead."""
    result = score_prospect(
        "fitness",
        "We provide fitness services",
        "Gym with online booking and appointment scheduling. Get a custom quote for personal training."
    )
    assert result["total"] >= 40, f"Expected >= 40, got {result['total']}"
    assert result["category"] in ["Medium priority", "High priority"]
    assert result["is_heuristic"] == True
def test_score_prospect_no_match():
    """Test overall prospect scoring with no strong matches."""
    result = score_prospect(
        "real_estate",
        "We are an agency",
        "A simple business website"
    )
    assert result["total"] < 40
    assert result["category"] in ["Low priority", "Medium priority"]
    assert result["is_heuristic"] == True
def test_criteria_labels():
    """Test that get_criteria_labels returns proper labels."""
    labels = get_criteria_labels()
    assert "industry_fit" in labels
    assert "enquiry_complexity" in labels
    assert "booking_fit" in labels
    assert "automation_opportunity" in labels
    assert "Industry fit" in labels["industry_fit"]
    assert "Enquiry complexity" in labels["enquiry_complexity"]
    assert "Booking" in labels["booking_fit"]
    assert "automation" in labels["automation_opportunity"].lower()
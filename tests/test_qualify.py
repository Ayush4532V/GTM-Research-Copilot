"""
Tests for qualify.py — Hybrid rule + LLM qualification.
"""
import sys
sys.path.insert(0, '.')

import tempfile
import os
from unittest.mock import patch, MagicMock
from qualify import qualify_lead
from db import get_conn, upsert_lead, get_lead_by_domain
def setup_temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    return path
class TestQualifyLead:
    """Tests for the qualify_lead function."""

    def test_qualify_lead_qualified(self):
        """Test that a high-scoring lead becomes qualified."""
        db_path = setup_temp_db()
        try:
            # First insert the lead
            conn = get_conn(db_path)
            upsert_lead(
                conn,
                domain="qualified.com",
                company="Qualified Company",
                industry="healthcare",
                description="Medical services providing",
                posting_text="Dental clinic with booking features"
            )
            conn.close()

            # Mock the LLM call
            with patch('qualify.generate_fit_score') as mock_llm:
                mock_llm.return_value = {
                    "score": 85,
                    "rationale": "Strong healthcare vertical with booking signals",
                    "source": "groq",
                    "success": True
                }

                # Now qualify with a strong rule score
                conn = get_conn(db_path)
                result = qualify_lead(
                    conn=conn,
                    domain="qualified.com",
                    business_name="Qualified Company",
                    industry="healthcare",
                    website_title="Dental clinic with custom quotes and online booking",
                    website_description="Medical services with appointment scheduling and contact form",
                    extracted_text="We offer custom quotes for enterprise clients. Book appointments online through our booking system. Get a free consultation and request a callback."
                )
                conn.close()

            assert result["is_qualified"] == True
            assert result["status"] == "qualified"
            assert result["fit_score_rule"] > 0
            assert result["fit_score_llm"] == 85
            assert result["fit_score_final"] > 0
            assert result["fit_reason"] is not None
        finally:
            os.unlink(db_path)

    def test_qualify_lead_not_qualified(self):
        """Test that a low-scoring lead stays as new."""
        db_path = setup_temp_db()
        try:
            conn = get_conn(db_path)
            upsert_lead(
                conn,
                domain="notqualified.com",
                company="Not Qualified Company",
                industry="other",
                description="Minimal info",
                posting_text=""
            )
            conn.close()

            with patch('qualify.generate_fit_score') as mock_llm:
                mock_llm.return_value = {
                    "score": 30,
                    "rationale": "Low fit",
                    "source": "groq",
                    "success": True
                }

                conn = get_conn(db_path)
                result = qualify_lead(
                    conn=conn,
                    domain="notqualified.com",
                    business_name="Not Qualified Company",
                    industry="other",
                    website_title="Not Qualified",
                    website_description="Minimal info",
                    extracted_text=""
                )
                conn.close()

            assert result["is_qualified"] == False
            assert result["status"] == "new"
        finally:
            os.unlink(db_path)

    def test_qualify_lead_fallback_to_rule_only(self):
        """Test that qualification falls back to rule-only when LLM fails."""
        db_path = setup_temp_db()
        try:
            conn = get_conn(db_path)
            upsert_lead(
                conn,
                domain="fallback.com",
                company="Fallback Company",
                industry="healthcare",
                description="Medical services",
                posting_text="Healthcare provider with booking"
            )
            conn.close()

            with patch('qualify.generate_fit_score') as mock_llm:
                # LLM returns failure
                mock_llm.return_value = {
                    "score": None,
                    "rationale": "",
                    "source": "groq",
                    "success": False
                }

                conn = get_conn(db_path)
                result = qualify_lead(
                    conn=conn,
                    domain="fallback.com",
                    business_name="Fallback Company",
                    industry="healthcare",
                    website_title="Fallback Company",
                    website_description="Medical services",
                    extracted_text="Healthcare provider with booking features"
                )
                conn.close()

            # Should still be qualified based on rule score alone
            assert result["fit_score_rule"] > 0
            assert result["fit_score_llm"] is None
            assert result["fit_score_final"] == result["fit_score_rule"]
            assert "rule-based" in result["fit_reason"].lower()
        finally:
            os.unlink(db_path)

    def test_qualify_lead_weighted_average(self):
        """Test that the weighted average formula is applied correctly."""
        db_path = setup_temp_db()
        try:
            conn = get_conn(db_path)
            upsert_lead(
                conn,
                domain="weighted.com",
                company="Weighted Company",
                industry="tech",
                description="Technology services",
                posting_text="Software with custom features"
            )
            conn.close()

            with patch('qualify.generate_fit_score') as mock_llm:
                mock_llm.return_value = {
                    "score": 90,
                    "rationale": "High",
                    "source": "gemini",
                    "success": True
                }

                conn = get_conn(db_path)
                result = qualify_lead(
                    conn=conn,
                    domain="weighted.com",
                    business_name="Weighted Company",
                    industry="tech",
                    website_title="Weighted Company",
                    website_description="Technology services",
                    extracted_text="Custom software development"
                )
                conn.close()

            # Verify the 40/60 weighted average formula
            rule_score = result["fit_score_rule"]
            llm_score = result["fit_score_llm"]
            expected_final = round(0.4 * rule_score + 0.6 * llm_score)
            assert result["fit_score_final"] == expected_final
            assert "LLM" in result["fit_reason"]
            assert "gemini" in result["fit_reason"].lower()
        finally:
            os.unlink(db_path)

    def test_qualify_lead_updates_db_status(self):
        """Test that qualify_lead updates the database status."""
        db_path = setup_temp_db()
        try:
            conn = get_conn(db_path)
            upsert_lead(
                conn,
                domain="dbupdate.com",
                company="DB Update Company",
                industry="fitness",
                description="Fitness services",
                posting_text="Gym with booking"
            )
            conn.close()

            with patch('qualify.generate_fit_score') as mock_llm:
                mock_llm.return_value = {
                    "score": 80,
                    "rationale": "Good fit",
                    "source": "groq",
                    "success": True
                }

                conn = get_conn(db_path)
                qualify_lead(
                    conn=conn,
                    domain="dbupdate.com",
                    business_name="DB Update Company",
                    industry="fitness",
                    website_title="Fitness Gym with custom quotes and online booking",
                    website_description="Gym services with appointment scheduling and contact form",
                    extracted_text="We offer custom quotes for enterprise clients. Book appointments online through our booking system. Get a free consultation and request a callback."
                )

                # Check DB was updated
                lead = get_lead_by_domain(conn, "dbupdate.com")
                conn.close()

            assert lead["status"] == "qualified"
            assert lead["fit_score_final"] >= 70
            assert lead["fit_score_rule"] > 0
            assert lead["fit_score_llm"] is not None
            assert lead["fit_reason"] is not None
        finally:
            os.unlink(db_path)
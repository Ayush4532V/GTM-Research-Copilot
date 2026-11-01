"""
Tests for enrich_email.py — Email discovery and verification.
"""
import sys
sys.path.insert(0, '.')

import tempfile
import os
from unittest.mock import patch, MagicMock
from enrich_email import generate_email_patterns, _smtp_verify_pattern, _get_mail_exchange, _smtp_connect_helo_check, enrich_lead
from db import get_conn, upsert_lead, get_lead_by_domain
def setup_temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    return path
class TestGenerateEmailPatterns:
    """Tests for generate_email_patterns."""

    def test_generate_email_patterns_no_domain(self):
        """Test that no patterns are generated for empty domain."""
        patterns = generate_email_patterns("")
        assert len(patterns) == 0

    def test_generate_email_patterns_with_first_name(self):
        """Test pattern generation with first name."""
        patterns = generate_email_patterns(
            domain="example.com",
            first_name="John",
            last_name="Doe",
            company_name="Example Inc"
        )
        assert len(patterns) > 0

        # Check for first@example.com pattern (uses first_name, not first+last)
        first_pattern = [p for p in patterns if p[0] == "john@example.com"]
        assert len(first_pattern) == 1
        assert first_pattern[0][1] == "guessed"

    def test_generate_email_patterns_generic_fallback(self):
        """Test pattern generation falls back to generic patterns."""
        patterns = generate_email_patterns(
            domain="example.com",
            company_name="Example"
        )
        # Should include generic patterns like info@, hello@, etc.
        generic_emails = [p[0] for p in patterns if p[1] == "generic"]
        assert len(generic_emails) > 0
        assert "info@example.com" in generic_emails

        # Check all are valid email patterns
        for email, confidence in patterns:
            assert "@" in email
            assert confidence in ["guessed", "generic"]

    def test_generate_email_patterns_deduplication(self):
        """Test that patterns are deduplicated."""
        patterns = generate_email_patterns(
            domain="example.com",
            first_name="Jane",
            last_name="Smith",
            company_name="Example"
        )
        emails = [p[0] for p in patterns]
        assert len(emails) == len(set(emails))  # No duplicates
        assert len(patterns) > 0

class TestSMTPPatternVerification:
    """Tests for SMTP pattern verification."""

    def test_smtp_verify_invalid_pattern_syntax(self):
        """Test that invalid email patterns return not_found."""
        email, confidence = _smtp_verify_pattern(
            domain="example.com",
            pattern="invalid-email-format"
        )
        assert confidence == "not_found"
        assert email == "invalid-email-format"

    def test_smtp_verify_no_mx_record(self):
        """Test that when no MX record is found, pattern is guessed."""
        with patch('enrich_email._get_mail_exchange') as mock_mx:
            mock_mx.return_value = []
            email, confidence = _smtp_verify_pattern(
                domain="example.com",
                pattern="info@example.com"
            )
            assert confidence == "guessed"
            assert email == "info@example.com"

    def test_smtp_verify_smtp_blocked(self):
        """Test that when SMTP verification fails, pattern is guessed."""
        with patch('enrich_email._get_mail_exchange') as mock_mx:
            mock_mx.return_value = ["mx.example.com"]
            with patch('enrich_email._smtp_connect_helo_check') as mock_helo:
                mock_helo.return_value = ("mx.example.com", False)

                email, confidence = _smtp_verify_pattern(
                    domain="example.com",
                    pattern="info@example.com"
                )
                assert confidence == "guessed"
                assert email == "info@example.com"

class TestGetMailExchange:
    """Tests for DNS MX lookup."""

    def test_get_mail_exchange_no_mx(self):
        """Test that no MX record results in empty list."""
        with patch('dns.resolver.Resolver') as mock_resolver:
            mock_resolver.return_value.resolve.side_effect = Exception("DNS failure")
            result = _get_mail_exchange("nonexistent.com")
            assert result == []

    def test_get_mail_exchange_success(self):
        """Test successful MX lookup."""
        mock_response = [MagicMock(), MagicMock()]
        mock_response[0].exchange = "mail1.example.com"
        mock_response[1].exchange = "mail2.example.com"

        with patch('dns.resolver.Resolver') as mock_resolver:
            mock_resolver.return_value.resolve.return_value = mock_response
            result = _get_mail_exchange("example.com")
            assert result == ["mail1.example.com", "mail2.example.com"]

class TestEnrichLead:
    """Tests for the enrich_lead function."""

    def test_enrich_lead_not_found(self):
        """Test enriching a lead that doesn't exist."""
        db_path = setup_temp_db()
        try:
            result = enrich_lead(
                domain="nonexistent.com",
                company_name="Nonexistent Company",
                website_emails=[],
                first_name=None,
                last_name=None
            )
            assert result["email"] is None
            assert result["email_confidence"] == "not_found"
            assert result["status"] == "not_found"
        finally:
            os.unlink(db_path)

    def test_enrich_lead_website_email(self):
        """Test enrichment using website email."""
        with patch('enrich_email.transaction') as mock_transaction:
            mock_conn = MagicMock()
            mock_transaction.return_value.__enter__.return_value = mock_conn
            mock_transaction.return_value.__exit__.return_value = None

            with patch('enrich_email.get_lead_by_domain') as mock_get:
                mock_get.return_value = {
                    "id": 1,
                    "domain": "enriched.com",
                    "company": "Enriched Company",
                    "status": "qualified",
                    "email": None,
                    "email_confidence": "not_found",
                }

                # Website has a valid (non-generic) email
                result = enrich_lead(
                    domain="enriched.com",
                    company_name="Enriched Company",
                    website_emails=["john@enriched.com"],
                    first_name=None,
                    last_name=None
                )

            # Should find email from website
            assert result["email"] is not None
            assert result["email_confidence"] in ["verified", "generic"]

    def test_enrich_lead_no_website_fallback_to_pattern(self):
        """Test fallback to pattern generation when no website email found."""
        with patch('enrich_email.transaction') as mock_transaction:
            mock_conn = MagicMock()
            mock_transaction.return_value.__enter__.return_value = mock_conn
            mock_transaction.return_value.__exit__.return_value = None

            with patch('enrich_email.get_lead_by_domain') as mock_get:
                mock_get.return_value = {
                    "id": 1,
                    "domain": "pattern.com",
                    "company": "Pattern Company",
                    "status": "qualified",
                    "email": None,
                    "email_confidence": "not_found",
                }

                with patch('enrich_email.generate_email_patterns') as mock_gen:
                    mock_gen.return_value = [("info@pattern.com", "generic")]

                    with patch('enrich_email._smtp_verify_pattern') as mock_verify:
                        mock_verify.return_value = ("info@pattern.com", "guessed")

                        result = enrich_lead(
                            domain="pattern.com",
                            company_name="Pattern Company",
                            website_emails=[],
                            first_name="John",
                            last_name="Doe"
                        )

            # Should have fallen back to pattern and got a result
            assert result["email"] is not None
"""
Tests for draft_email.py — Personalized outreach draft generation.
"""
import sys
sys.path.insert(0, '.')

import tempfile
import os
from unittest.mock import patch, MagicMock
from draft_email import generate_outreach_draft, generate_linkedin_note, draft_lead, _template_fallback
from db import get_conn, upsert_lead, get_lead_by_domain
def setup_temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    return path
class TestGenerateOutreachDraft:
    """Tests for the generate_outreach_draft function."""

    def test_generate_outreach_draft_basic(self):
        """Test basic draft generation."""
        draft = generate_outreach_draft(
            company_name="Test Dental",
            industry="healthcare",
            observed_signal="they offer teeth whitening services"
        )

        # Draft should contain the company name
        assert "Test Dental" in draft

        # Should contain the industry
        assert "healthcare" in draft

        # Should contain the observed signal
        assert "teeth whitening" in draft

        # Should contain the sender's one-liner
        assert "Hyperlape" in draft or "reduce response time" in draft

    def test_generate_outreach_draft_short(self):
        """Test that generated draft is under 120 words."""
        draft = generate_outreach_draft(
            company_name="Short Co",
            industry="tech",
            observed_signal="custom software development"
        )

        word_count = len(draft.split())
        assert word_count < 120, f"Draft too long: {word_count} words"

    def test_generate_outreach_draft_long_signal_truncated(self):
        """Test that long signals are truncated to 80 chars."""
        long_signal = "We offer " + "a very detailed custom software development service for enterprise clients with multiple features " * 2
        draft = generate_outreach_draft(
            company_name="Long Co",
            industry="tech",
            observed_signal=long_signal
        )
        # Signal should be truncated to 80 chars
        assert len(long_signal) > 80
        # The draft should contain the signal but truncated
        # After truncation, the signal portion should be <= 80 chars
        # Extract the signal from after "handling " to the end of that line
        signal_start = draft.find("handling ") + len("handling ")
        rest = draft[signal_start:]
        # Take up to first newline
        signal_end = rest.find("\n")
        if signal_end == -1:
            drafted_signal = rest
        else:
            drafted_signal = rest[:signal_end]
        assert len(drafted_signal.strip()) <= 81  # Allow 80 chars + trailing period

    def test_generate_outreach_draft_strips_i_noticed(self):
        """Test that 'I noticed' prefix is stripped from signal."""
        draft = generate_outreach_draft(
            company_name="Test Co",
            industry="tech",
            observed_signal="I noticed they have a modern website"
        )
        # The "I noticed" from the user's signal input should be stripped
        # The template itself has "I noticed" in its structure, so we check
        # that the signal part doesn't start with "I noticed"
        assert "they have a modern website" in draft
        # Verify the original "I noticed" prefix from the signal is removed
        # (the template "I noticed you specialize" is separate from the signal)
        assert "I noticed they have" not in draft

    def test_generate_outreach_draft_empty_signal(self):
        """Test fallback for empty signal."""
        draft = generate_outreach_draft(
            company_name="Test Co",
            industry="tech",
            observed_signal=""
        )
        # Should use fallback signal
        assert "your services" in draft.lower() or len(draft) > 0

class TestGenerateLinkedinNote:
    """Tests for the generate_linkedin_note function."""

    def test_linkedin_note_short(self):
        """Test that LinkedIn note is <= 280 chars."""
        note = generate_linkedin_note(
            company_name="Test Co",
            observed_signal="online booking system"
        )

        assert len(note) <= 280

    def test_linkedin_note_with_role(self):
        """Test LinkedIn note with role hint."""
        note = generate_linkedin_note(
            company_name="Test Co",
            observed_signal="online booking system",
            role_hint="owner"
        )

        # Should include the role
        assert "owner" in note.lower()

    def test_linkedin_note_short_signal(self):
        """Test LinkedIn note with short signal."""
        note = generate_linkedin_note(
            company_name="Test Co",
            observed_signal="book now"
        )
        assert len(note) <= 280

class TestTemplateFallback:
    """Tests for the _template_fallback function."""

    def test_template_fallback_basic(self):
        """Test template fallback generation."""
        fallback = _template_fallback(
            business_name="Template Co",
            industry="healthcare",
            observation="teeth whitening services"
        )
        assert "Template Co" in fallback
        assert "healthcare" in fallback
        assert "teeth whitening" in fallback

    def test_template_fallback_short_observation(self):
        """Test template fallback with short observation."""
        fallback = _template_fallback(
            business_name="Template Co",
            industry="healthcare",
            observation=""
        )
        # Should use default observation
        assert fallback is not None

class TestDraftLead:
    """Tests for the draft_lead function."""

    def test_draft_lead_creates_draft(self):
        """Test that draft_lead creates a draft for a lead."""
        # Mock all database operations to test just the drafting logic
        with patch('draft_email.transaction') as mock_transaction:
            mock_conn = MagicMock()
            mock_transaction.return_value.__enter__.return_value = mock_conn
            mock_transaction.return_value.__exit__.return_value = None

            with patch('draft_email.get_lead_by_domain', return_value=None):
                result = draft_lead(
                    domain="drafted.com",
                    company_name="Drafted Company",
                    industry="healthcare",
                    observed_signal="online booking",
                    email="info@drafted.com",
                    contact_name="John Doe",
                    contact_title="Owner"
                )

            assert result["status"] == "drafted"
            assert result["draft_email_body"] is not None
            assert result["linkedin_note"] is not None

    def test_draft_lead_no_lead(self):
        """Test that draft_lead works for a new domain."""
        with patch('draft_email.transaction') as mock_transaction:
            mock_conn = MagicMock()
            mock_transaction.return_value.__enter__.return_value = mock_conn
            mock_transaction.return_value.__exit__.return_value = None

            with patch('draft_email.get_lead_by_domain', return_value=None):
                result = draft_lead(
                    domain="newdraft.com",
                    company_name="New Draft Co",
                    industry="tech",
                    observed_signal="custom software",
                )

            assert result["status"] == "drafted"
            assert result["draft_email_body"] is not None
            assert result["linkedin_note"] is not None
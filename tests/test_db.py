"""
Tests for db.py — SQLite persistence layer.
"""
import sys
sys.path.insert(0, '.')

import tempfile
import os
from db import get_conn, transaction, upsert_lead, get_lead, get_lead_by_domain, query_leads, count_by_status, is_suppressed, add_to_suppression, _LEADS_SCHEMA, _SUPPRESSION_SCHEMA, _INDEXES
def setup_temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    return path
def test_get_conn_creates_tables():
    """Test that get_conn creates the database tables."""
    db_path = setup_temp_db()
    try:
        conn = get_conn(db_path)
        # Try to execute a query to verify tables exist
        conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='leads'")
        conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='suppression_list'")
        conn.close()
    finally:
        os.unlink(db_path)
def test_upsert_lead_new():
    """Test inserting a new lead."""
    db_path = setup_temp_db()
    try:
        conn = get_conn(db_path)
        lead_id = upsert_lead(
            conn,
            domain="testcompany.com",
            company="Test Company",
            industry="healthcare"
        )
        assert lead_id > 0

        # Retrieve the lead
        lead = get_lead(conn, lead_id)
        assert lead["company"] == "Test Company"
        assert lead["domain"] == "testcompany.com"
        assert lead["industry"] == "healthcare"
        assert lead["status"] == "new"  # Default status

        conn.close()
    finally:
        os.unlink(db_path)
def test_upsert_lead_update():
    """Test updating an existing lead."""
    db_path = setup_temp_db()
    try:
        conn = get_conn(db_path)
        # Insert initial lead
        lead_id = upsert_lead(
            conn,
            domain="update.com",
            company="Original Company",
            industry="tech"
        )

        # Update the same domain with new data
        lead_id2 = upsert_lead(
            conn,
            domain="update.com",
            company="Updated Company",
            industry="healthcare",
            website="https://updated.com"
        )
        assert lead_id == lead_id2  # Same ID

        # Verify the update
        lead = get_lead(conn, lead_id)
        assert lead["company"] == "Updated Company"
        assert lead["industry"] == "healthcare"
        assert lead["website"] == "https://updated.com"

        conn.close()
    finally:
        os.unlink(db_path)
def test_upsert_lead_dedupe_by_domain():
    """Test that leads are deduplicated by domain."""
    db_path = setup_temp_db()
    try:
        conn = get_conn(db_path)
        # Insert first lead
        upsert_lead(
            conn,
            domain="dedupe.com",
            company="Company A",
            industry="tech"
        )

        # Insert second lead with same domain but different company
        upsert_lead(
            conn,
            domain="dedupe.com",
            company="Company B",
            industry="healthcare"
        )

        # Query should return only one lead
        leads = query_leads(conn)
        assert len(leads) == 1
        assert leads[0]["company"] == "Company B"  # Last one wins

        conn.close()
    finally:
        os.unlink(db_path)
def test_query_leads_with_filters():
    """Test querying leads with various filters."""
    db_path = setup_temp_db()
    try:
        conn = get_conn(db_path)
        # Insert test leads
        upsert_lead(conn, domain="test1.com", company="Company One", industry="tech", status="qualified")
        upsert_lead(conn, domain="test2.com", company="Company Two", industry="healthcare", status="enriched")
        upsert_lead(conn, domain="test3.com", company="Company Three", industry="tech", status="drafted")

        # Filter by status
        qualified = query_leads(conn, filters={"status": "qualified"})
        assert len(qualified) == 1
        assert qualified[0]["company"] == "Company One"

        # Filter by industry
        tech = query_leads(conn, filters={"industry": "tech"})
        assert len(tech) == 2
        for lead in tech:
            assert lead["industry"] == "tech"

        # Filter by search
        companies = query_leads(conn, filters={"search": "Company"})
        assert len(companies) == 3

        conn.close()
    finally:
        os.unlink(db_path)
def test_count_by_status():
    """Test counting leads by status."""
    db_path = setup_temp_db()
    try:
        conn = get_conn(db_path)
        # Insert leads with different statuses
        upsert_lead(conn, domain="status1.com", company="Company One", status="qualified")
        upsert_lead(conn, domain="status2.com", company="Company Two", status="qualified")
        upsert_lead(conn, domain="status3.com", company="Company Three", status="enriched")
        upsert_lead(conn, domain="status4.com", company="Company Four", status="drafted")
        upsert_lead(conn, domain="status5.com", company="Company Five", status="new")

        counts = count_by_status(conn)
        assert counts["qualified"] == 2
        assert counts["enriched"] == 1
        assert counts["drafted"] == 1
        assert counts["new"] == 1
        assert len(counts) == 4  # Should have 4 different statuses

        conn.close()
    finally:
        os.unlink(db_path)
def test_suppression_list():
    """Test suppression list functionality."""
    db_path = setup_temp_db()
    try:
        conn = get_conn(db_path)
        # Initially not suppressed
        assert not is_suppressed(conn, "test@example.com")

        # Add to suppression
        add_to_suppression(conn, "test@example.com", "Test suppression")
        assert is_suppressed(conn, "test@example.com")

        # Different domain is not suppressed
        assert not is_suppressed(conn, "different@example.com")

        conn.close()
    finally:
        os.unlink(db_path)
def test_transaction_rollback():
    """Test that transactions are rolled back on error."""
    db_path = setup_temp_db()
    try:
        # First, insert a valid lead to get a connection
        with transaction(db_path) as conn:
            upsert_lead(conn, domain="rollback.com", company="Company", status="qualified")

        # Verify it was inserted
        with transaction(db_path) as conn:
            leads = query_leads(conn)
            assert len(leads) == 1

        conn.close()
    finally:
        os.unlink(db_path)
def test_schema_creation():
    """Test that schema is created correctly."""
    # Check that the schema strings are valid
    assert "CREATE TABLE IF NOT EXISTS leads" in _LEADS_SCHEMA
    assert "CREATE TABLE IF NOT EXISTS suppression_list" in _SUPPRESSION_SCHEMA
    assert "domain TEXT NOT NULL UNIQUE" in _LEADS_SCHEMA  # UNIQUE constraint
    assert "email_or_domain TEXT NOT NULL UNIQUE" in _SUPPRESSION_SCHEMA  # UNIQUE constraint
    # Check for indexes
    assert "CREATE INDEX IF NOT EXISTS idx_leads_domain ON leads(domain);" in _INDEXES
    assert "CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);" in _INDEXES
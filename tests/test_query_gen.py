"""
Tests for query_gen.py — Search query generation from target profile.
"""
import sys
sys.path.insert(0, '.')

from query_gen import generate_queries, _region_suffix, _industry_dorks, _business_directory_queries, _google_maps_queries, _generic_directory_queries
def test_region_suffix_empty():
    """Test region suffix when target_regions is empty."""
    from config import target_regions
    target_regions.clear()  # Clear for test
    try:
        result = _region_suffix(target_regions)
        assert result == ""
    finally:
        # Restore original value
        from config import target_regions as original
        target_regions.extend(original)
def test_region_suffix_with_regions():
    """Test region suffix with actual regions."""
    from config import target_regions
    original_regions = target_regions.copy()
    target_regions.clear()
    target_regions.extend(["us", "uk", "ca"])

    try:
        result = _region_suffix(target_regions)
        assert result == "us uk ca"
    finally:
        target_regions.clear()
        target_regions.extend(original_regions)
def test_industry_dorks():
    """Test industry dork generation."""
    industry = "healthcare"
    dorks = _industry_dorks(industry)
    assert len(dorks) == 3
    assert 'site:linkedin.com/company "healthcare"' in dorks
    assert 'site:linkedin.com/in "healthcare"' in dorks
    assert 'site:x.com "healthcare"' in dorks
def test_business_directory_queries_with_region():
    """Test business directory queries with region."""
    industry = "dentist"
    region = "London"
    queries = _business_directory_queries(industry, region)
    assert len(queries) == 4
    assert '"dentist" directory London' in queries
    assert 'best dentist near London' in queries
    assert 'top dentist in London' in queries
    assert 'dentist business listing London' in queries
def test_business_directory_queries_no_region():
    """Test business directory queries without region."""
    industry = "dentist"
    region = ""
    queries = _business_directory_queries(industry, region)
    assert len(queries) == 4
    assert '"dentist" business directory' in queries
    assert 'best dentist companies' in queries
    assert 'top dentist businesses' in queries
    assert 'dentist business listing' in queries
def test_google_maps_queries_with_region():
    """Test Google Maps queries with region."""
    industry = "restaurants"
    region = "NYC"
    queries = _google_maps_queries(industry, region)
    assert len(queries) == 2
    assert 'restaurants near NYC' in queries
    assert 'restaurants in NYC google maps' in queries
def test_google_maps_queries_no_region():
    """Test Google Maps queries without region."""
    industry = "restaurants"
    region = ""
    queries = _google_maps_queries(industry, region)
    assert len(queries) == 2
    assert 'restaurants near me' in queries
    assert 'restaurants google maps' in queries
def test_generic_directory_queries():
    """Test generic directory queries."""
    queries = _generic_directory_queries()
    # Should have 12 directories × 4 terms = 48 queries
    assert len(queries) == 48
    # Check some specific ones
    assert 'site:crunchbase.com "dentist"' in queries
    assert 'site:g2.com "legal firm"' in queries
    assert 'site:clutch.co "plumbing"' in queries
def test_generate_queries_default():
    """Test generate_queries with default parameters."""
    queries = generate_queries()
    assert len(queries) > 0
    assert len(queries) <= 25  # Should be capped at max_queries

    # Check for deduplication
    assert len(queries) == len(set(queries))

    # Check that we have some expected query types
    has_linkedin = any("linkedin" in q.lower() for q in queries)
    has_google_maps = any("google maps" in q.lower() for q in queries)
    has_directory = any("directory" in q.lower() for q in queries)

    assert has_linkedin or has_google_maps or has_directory
def test_generate_queries_with_industries():
    """Test generate_queries with specific industries."""
    industries = ["healthcare", "legal"]
    queries = generate_queries(industries=industries, max_queries=50)

    # Should include queries from both industries
    healthcare_queries = [q for q in queries if "healthcare" in q.lower()]
    legal_queries = [q for q in queries if "legal" in q.lower()]

    assert len(healthcare_queries) > 0
    assert len(legal_queries) > 0

    # Should not have "other" industry queries
    other_queries = [q for q in queries if '"other"' in q]
    assert len(other_queries) == 0
def test_generate_queries_max_queries_limit():
    """Test that max_queries parameter works."""
    # Request more than available
    queries = generate_queries(max_queries=10)
    assert len(queries) <= 10

    # Request fewer
    queries2 = generate_queries(max_queries=5)
    assert len(queries2) <= 5

def test_query_types():
    """Test that all expected query types are generated."""
    queries = generate_queries(max_queries=100)  # Get lots to see variety

    # Check for various query patterns
    industry_dorks = [q for q in queries if q.startswith("site:linkedin.com")]
    assert len(industry_dorks) > 0

    maps_queries = [q for q in queries if "google maps" in q.lower()]
    assert len(maps_queries) > 0

    directory_queries = [q for q in queries if "directory" in q.lower()]
    assert len(directory_queries) > 0

    generic_queries = [q for q in queries if q.startswith("site:") and not q.startswith("site:linkedin")]
    assert len(generic_queries) > 0
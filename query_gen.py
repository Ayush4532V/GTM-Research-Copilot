"""
query_gen.py — Generate search queries from the target profile.

Takes the declarative profile in config.py and produces a list of
Google-style search queries and site-dorks for lead discovery.

Query types:
- Business directory searches (e.g. "dentist in London")
- Industry-specific directory searches (e.g. "legal firms directory UK")
- Google Maps-style queries (e.g. "best restaurants near me")
- LinkedIn / X dorks (e.g. "site:linkedin.com/in dentist London")
- Site-specific searches for known directories
"""

from config import target_industries, target_regions


def _region_suffix(regions):
    """Build a region suffix string from the target_regions list."""
    if not regions:
        return ""
    return " ".join(regions)


def _industry_dorks(industry):
    """Generate site-dork queries for a specific industry."""
    dorks = []
    # LinkedIn company pages
    dorks.append(f'site:linkedin.com/company "{industry}"')
    # LinkedIn personal profiles (note: this is public search only, no scraping)
    dorks.append(f'site:linkedin.com/in "{industry}"')
    # X/Twitter public bios
    dorks.append(f'site:x.com "{industry}"')
    return dorks


def _business_directory_queries(industry, region_suffix):
    """Generate business-directory style queries for an industry."""
    queries = []
    if region_suffix:
        queries.append(f'"{industry}" directory {region_suffix}')
        queries.append(f'best {industry} near {region_suffix}')
        queries.append(f'top {industry} in {region_suffix}')
        queries.append(f'{industry} business listing {region_suffix}')
    else:
        queries.append(f'"{industry}" business directory')
        queries.append(f'best {industry} companies')
        queries.append(f'top {industry} businesses')
        queries.append(f'{industry} business listing')
    return queries


def _google_maps_queries(industry, region_suffix):
    """Generate Google Maps-style queries."""
    queries = []
    if region_suffix:
        queries.append(f'{industry} near {region_suffix}')
        queries.append(f'{industry} in {region_suffix} google maps')
    else:
        queries.append(f'{industry} near me')
        queries.append(f'{industry} google maps')
    return queries


def _generic_directory_queries():
    """Generate queries against known business directories."""
    directories = [
        "crunchbase.com",
        "g2.com",
        "clutch.co",
        "yelp.com",
        "tripadvisor.com",
        "thomsonreuters.com",
        "bloomberg.com",
        "zoominfo.com",
        "dunandbradstreet.com",
        "craft.co",
        "owler.com",
        "companywallstreet.com",
    ]
    queries = []
    for d in directories:
        queries.append(f'site:{d} "dentist"')
        queries.append(f'site:{d} "legal firm"')
        queries.append(f'site:{d} "plumbing"')
        queries.append(f'site:{d} "accounting"')
    return queries


def generate_queries(
    industries: list[str] | None = None,
    max_queries: int = 25,
) -> list[str]:
    """
    Generate a list of search queries from the target profile.

    Args:
        industries: Optional list of industry names. Defaults to all keys
                    in target_industries (excluding "other").
        max_queries: Maximum number of queries to return.

    Returns:
        A list of search query strings, deduplicated and capped.
    """
    if industries is None:
        industries = [k for k in target_industries.keys() if k != "other"]

    region_suffix = _region_suffix(target_regions)
    all_queries = []

    for industry in industries:
        all_queries.extend(_industry_dorks(industry))
        all_queries.extend(_business_directory_queries(industry, region_suffix))
        all_queries.extend(_google_maps_queries(industry, region_suffix))

    # Add generic directory queries (these are broad, so we only add a few).
    all_queries.extend(_generic_directory_queries())

    # Deduplicate while preserving order.
    seen = set()
    unique = []
    for q in all_queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)

    # Cap to max_queries.
    if max_queries > 0 and len(unique) > max_queries:
        unique = unique[:max_queries]

    return unique


if __name__ == "__main__":
    queries = generate_queries(max_queries=25)
    print(f"Generated {len(queries)} queries:")
    for i, q in enumerate(queries, 1):
        print(f"  {i:2d}. {q}")
"""
research.py — Deep website extraction with multi-page crawl and JS fallback.

This module extracts public information from business websites using a
two-tier approach:

Tier 1 (fast): Requests + BeautifulSoup — fetches homepage and follows
discovered links to /about, /services, /contact, /careers, etc.

Tier 2 (fallback): Playwright headless Chromium — used only when Tier 1
returns empty/minimal content, indicating JS-rendered pages.

Both tiers extract: title, meta description, full visible text, public
emails, phone numbers, social/LinkedIn links, booking/contact-form signals.

All network calls include retry with exponential backoff + jitter.
Graceful timeout/error handling per page. SQLite caching so re-runs don't
re-scrape.
"""

import logging
import os
import random
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("gtm.research")


# ---------------------------------------------------------------------------
# Retry helper (exponential backoff + jitter)
# ---------------------------------------------------------------------------

def _retry_with_backoff(func, max_retries=3, base_delay=1.0, *args, **kwargs):
    """
    Call func with exponential backoff + jitter.

    On each failure, waits base_delay * (2 ** attempt) + random jitter
    before retrying. Raises the last exception after max_retries.
    """
    last_exc = None
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    "Attempt %d failed (%s), retrying in %.1fs",
                    attempt + 1, type(exc).__name__, delay,
                )
                time.sleep(delay)
    raise last_exc


# ---------------------------------------------------------------------------
# URL / link helpers
# ---------------------------------------------------------------------------

def _normalize_url(url: str) -> str:
    """Ensure URL has a scheme and strip trailing slash."""
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    # Remove trailing slash except for root
    if url.endswith("/") and url.count("/") > 2:
        url = url.rstrip("/")
    return url


def _same_domain(url1: str, url2: str) -> bool:
    """Check if two URLs belong to the same registered domain."""
    try:
        d1 = urlparse(url1).netloc.lower().lstrip("www.")
        d2 = urlparse(url2).netloc.lower().lstrip("www.")
        return d1 == d2
    except Exception:
        return False


def _is_internal_link(base_url: str, href: str) -> bool:
    """Check if href is an internal link on the same site."""
    if not href:
        return False
    if href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return False
    # Relative paths
    if href.startswith("/"):
        return True
    # Absolute URLs on same domain
    if href.startswith("http"):
        return _same_domain(base_url, href)
    return False


def _resolve_url(base_url: str, href: str) -> str:
    """Resolve a relative or absolute href against the base URL."""
    return urljoin(base_url, href)


# Priority path patterns for deep crawl
PRIORITY_PATHS = [
    "/about", "/about-us", "/aboutus", "/our-story", "/company",
    "/services", "/service", "/what-we-do", "/solutions", "/offerings",
    "/contact", "/contact-us", "/contactus", "/get-in-touch", "/enquiry",
    "/careers", "/jobs", "/join-us", "/work-with-us", "/team",
    "/book", "/booking", "/appointment", "/schedule", "/reserve",
    "/quote", "/get-a-quote", "/request-quote", "/pricing",
]


def _discover_priority_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """
    Extract internal links matching priority path patterns from a page.

    Returns a list of unique, resolved absolute URLs.
    """
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not _is_internal_link(base_url, href):
            continue
        resolved = _resolve_url(base_url, href)
        # Check if path matches any priority pattern
        path = urlparse(resolved).path.lower()
        if any(p in path for p in PRIORITY_PATHS):
            links.add(resolved)
    return list(links)


# ---------------------------------------------------------------------------
# Content extraction
# ---------------------------------------------------------------------------

@dataclass
class PageContent:
    """Structured content extracted from a single page."""
    url: str
    title: str
    description: str
    content: str
    emails: list[str]
    phones: list[str]
    linkedin_urls: list[str]
    social_urls: list[str]
    booking_signals: list[str]
    contact_form_signals: list[str]
    success: bool
    error: str | None = None


EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}"
)


def _extract_emails(text: str) -> list[str]:
    """Extract unique email addresses from text."""
    found = EMAIL_RE.findall(text)
    # Filter out common false positives
    filtered = [e for e in found if not e.endswith((".png", ".jpg", ".gif", ".svg", ".css", ".js"))]
    return list(dict.fromkeys(filtered))


def _extract_phones(text: str) -> list[str]:
    """Extract unique phone numbers from text."""
    found = PHONE_RE.findall(text)
    return list(dict.fromkeys(found))


def _extract_linkedin_urls(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Extract LinkedIn profile/company URLs from page links."""
    urls = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if "linkedin.com" in href:
            urls.add(href)
    return list(urls)


def _extract_social_urls(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Extract social media URLs from page links."""
    urls = set()
    social_domains = ["facebook.com", "twitter.com", "x.com", "instagram.com",
                      "youtube.com", "tiktok.com"]
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if any(d in href for d in social_domains):
            urls.add(href)
    return list(urls)


def _extract_booking_signals(soup: BeautifulSoup, text: str) -> list[str]:
    """Extract booking/contact-form related signals from page."""
    signals = []
    text_lower = text.lower()

    # Keywords in visible text
    for kw in ["book online", "book now", "booking", "appointment", "schedule",
               "reserve", "enquiry", "contact form", "request a quote",
               "callback", "free consultation", "live chat", "chatbot"]:
        if kw in text_lower:
            signals.append(kw)

    # Check for actual forms
    for form in soup.find_all("form"):
        form_text = form.get_text(" ", strip=True).lower()
        if any(kw in form_text for kw in ["contact", "enquiry", "quote",
                                           "book", "appointment", "schedule",
                                           "callback", "consultation"]):
            signals.append("contact_form_detected")
            break

    return list(dict.fromkeys(signals))


def _extract_content_from_html(html: str, base_url: str) -> PageContent:
    """Parse HTML and extract structured content."""
    soup = BeautifulSoup(html, "html.parser")

    # Title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Meta description
    desc_tag = soup.find("meta", attrs={"name": "description"})
    if not desc_tag:
        desc_tag = soup.find("meta", attrs={"property": "og:description"})
    description = desc_tag.get("content", "") if desc_tag else ""

    # Remove non-content elements
    for elem in soup(["script", "style", "noscript", "header", "footer",
                      "nav", "svg", "img", "form", "aside"]):
        elem.decompose()

    # Get main content or fallback to body
    main = soup.find("main")
    if main:
        text_content = main.get_text(separator=" ", strip=True)
    else:
        text_content = soup.get_text(separator=" ", strip=True)

    text_content = re.sub(r"\s+", " ", text_content)

    # Extract signals
    emails = _extract_emails(text_content)
    phones = _extract_phones(text_content)
    linkedin = _extract_linkedin_urls(soup, base_url)
    social = _extract_social_urls(soup, base_url)
    booking = _extract_booking_signals(soup, text_content)

    return PageContent(
        url=base_url,
        title=title,
        description=description,
        content=text_content[:15000],  # Cap at 15k chars per page
        emails=emails,
        phones=phones,
        linkedin_urls=linkedin,
        social_urls=social,
        booking_signals=booking,
        contact_form_signals=[s for s in booking if "form" in s or "contact" in s],
        success=True,
    )


# ---------------------------------------------------------------------------
# Tier 1: Requests + BeautifulSoup
# ---------------------------------------------------------------------------

def _fetch_with_requests(url: str, timeout: int = 15) -> str | None:
    """
    Fetch page content using requests + BeautifulSoup.

    Returns HTML string on success, None on failure.
    """
    def _do_fetch():
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.text

    try:
        return _retry_with_backoff(_do_fetch, max_retries=2, base_delay=1.0)
    except requests.exceptions.Timeout:
        logger.warning("Timeout fetching %s", url)
        return None
    except requests.exceptions.HTTPError as e:
        logger.warning("HTTP error %s for %s", e.response.status_code, url)
        return None
    except requests.exceptions.RequestException as e:
        logger.warning("Request error for %s: %s", url, type(e).__name__)
        return None


def _extract_with_requests(base_url: str, max_pages: int = 6) -> list[PageContent]:
    """
    Crawl homepage and discovered priority pages using requests+BS4.

    Returns list of PageContent objects (one per successfully fetched page).
    """
    results = []
    visited = set()
    to_visit = [base_url]

    while to_visit and len(results) < max_pages:
        url = to_visit.pop(0)
        normalized = _normalize_url(url)
        if normalized in visited:
            continue
        visited.add(normalized)

        html = _fetch_with_requests(normalized)
        if html is None:
            continue

        page = _extract_content_from_html(html, normalized)
        results.append(page)

        # Discover new links from this page
        soup = BeautifulSoup(html, "html.parser")
        for link in _discover_priority_links(soup, normalized):
            if _normalize_url(link) not in visited:
                to_visit.append(link)

    return results


# ---------------------------------------------------------------------------
# Tier 2: Playwright fallback (for JS-rendered pages)
# ---------------------------------------------------------------------------

def _extract_with_playwright(base_url: str, max_pages: int = 4) -> list[PageContent]:
    """
    Crawl using Playwright headless Chromium.

    Only used when requests returns empty/minimal content.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright not installed; install with: pip install playwright && playwright install chromium")
        return []

    results = []
    visited = set()
    to_visit = [base_url]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()

            while to_visit and len(results) < max_pages:
                url = to_visit.pop(0)
                normalized = _normalize_url(url)
                if normalized in visited:
                    continue
                visited.add(normalized)

                try:
                    page.goto(normalized, wait_until="domcontentloaded", timeout=30000)
                    # Wait for network to be idle (optional, helps with SPAs)
                    try:
                        page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass

                    html = page.content()
                    if not html or len(html) < 500:
                        continue

                    content = _extract_content_from_html(html, normalized)
                    results.append(content)

                    # Discover links from rendered DOM
                    links = page.eval_on_selector_all(
                        "a[href]",
                        "elements => elements.map(e => e.href)"
                    )
                    for link in links:
                        if _is_internal_link(base_url, link):
                            resolved = _resolve_url(base_url, link)
                            path = urlparse(resolved).path.lower()
                            if any(p in path for p in PRIORITY_PATHS):
                                if _normalize_url(resolved) not in visited:
                                    to_visit.append(resolved)

                except Exception as e:
                    logger.warning("Playwright failed for %s: %s", normalized, e)

            browser.close()
    except Exception as e:
        logger.error("Playwright setup failed: %s", e)

    return results


# ---------------------------------------------------------------------------
# Cache (simple file-based)
# ---------------------------------------------------------------------------

CACHE_DIR = os.path.join(os.path.dirname(__file__), ".research_cache")


def _cache_key(url: str) -> str:
    """Generate a filesystem-safe cache key from a URL."""
    # Use domain + path hash
    parsed = urlparse(_normalize_url(url))
    domain = parsed.netloc.lower().lstrip("www.")
    path_hash = str(hash(parsed.path))[-8:]
    return f"{domain}_{path_hash}.json"


def _load_from_cache(url: str) -> list[PageContent] | None:
    """Load cached research results for a base URL."""
    import json
    key = _cache_key(url)
    path = os.path.join(CACHE_DIR, key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return [PageContent(**item) for item in data]
    except Exception:
        return None


def _save_to_cache(url: str, pages: list[PageContent]) -> None:
    """Save research results to cache."""
    import json
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = _cache_key(url)
    path = os.path.join(CACHE_DIR, key)
    try:
        with open(path, "w") as f:
            json.dump([p.__dict__ for p in pages], f)
    except Exception as e:
        logger.warning("Failed to write cache: %s", e)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_website_info(url: str) -> dict:
    """
    Extract public information from a website.

    Tier 1: Requests + BeautifulSoup (multi-page crawl).
    Tier 2: Playwright headless Chromium (fallback if Tier 1 yields minimal content).

    Returns dict with keys:
        - title: Page title (str)
        - description: Meta description (str)
        - content: Extracted visible text, concatenated from all pages (str)
        - emails: list of found email addresses
        - phones: list of found phone numbers
        - linkedin_urls: list of LinkedIn URLs
        - social_urls: list of social media URLs
        - booking_signals: list of booking/contact-form signals
        - success: Whether extraction succeeded (bool)
        - error: Error message if failed (str or None)
        - pages_crawled: Number of pages successfully crawled
    """
    result = {
        "title": "",
        "description": "",
        "content": "",
        "emails": [],
        "phones": [],
        "linkedin_urls": [],
        "social_urls": [],
        "booking_signals": [],
        "success": False,
        "error": None,
        "pages_crawled": 0,
    }

    if not url:
        result["error"] = "No URL provided."
        return result

    base_url = _normalize_url(url)

    # Check cache first
    cached = _load_from_cache(base_url)
    if cached:
        logger.info("Using cached results for %s (%d pages)", base_url, len(cached))
        return _merge_pages(cached)

    # Tier 1: Requests + BS4
    logger.info("Tier 1: Fetching with requests+BS4: %s", base_url)
    pages = _extract_with_requests(base_url, max_pages=6)

    # Check if Tier 1 got meaningful content
    total_chars = sum(len(p.content) for p in pages if p.success)
    if total_chars < 500:
        logger.info("Tier 1 yielded minimal content (%d chars), trying Playwright...", total_chars)
        pw_pages = _extract_with_playwright(base_url, max_pages=4)
        if pw_pages:
            pw_chars = sum(len(p.content) for p in pw_pages)
            logger.info("Playwright extracted %d chars from %d pages", pw_chars, len(pw_pages))
            pages = pw_pages

    if not pages:
        result["error"] = "Could not extract content from website (all tiers failed)."
        return result

    # Merge all pages
    merged = _merge_pages(pages)
    merged["pages_crawled"] = len(pages)

    # Save to cache
    _save_to_cache(base_url, pages)

    return merged


def _merge_pages(pages: list[PageContent]) -> dict:
    """Merge multiple PageContent objects into a single result dict."""
    # Use the first (homepage) page for title/description
    first = pages[0] if pages else None

    # Combine all content
    all_content = []
    all_emails = set()
    all_phones = set()
    all_linkedin = set()
    all_social = set()
    all_booking = set()

    for p in pages:
        if p.content:
            all_content.append(f"[{p.url}] {p.content}")
        all_emails.update(p.emails)
        all_phones.update(p.phones)
        all_linkedin.update(p.linkedin_urls)
        all_social.update(p.social_urls)
        all_booking.update(p.booking_signals)

    if first:
        return {
            "title": first.title,
            "description": first.description,
            "content": "\n\n".join(all_content)[:20000],  # Cap combined content
            "emails": list(all_emails),
            "phones": list(all_phones),
            "linkedin_urls": list(all_linkedin),
            "social_urls": list(all_social),
            "booking_signals": list(all_booking),
            "success": True,
            "error": None,
        }
    else:
        return {
            "title": "",
            "description": "",
            "content": "",
            "emails": [],
            "phones": [],
            "linkedin_urls": [],
            "social_urls": [],
            "booking_signals": [],
            "success": False,
            "error": "No pages extracted",
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Quick test
    result = extract_website_info("https://example.com")
    print(f"Success: {result['success']}")
    print(f"Title: {result['title']}")
    print(f"Content length: {len(result['content'])}")
    print(f"Emails: {result['emails']}")
    print(f"Pages crawled: {result['pages_crawled']}")
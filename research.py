"""
research.py — Website extraction utilities.

This module contains functions for extracting publicly accessible information
from business websites using Requests and BeautifulSoup.
"""

import re
import requests
from bs4 import BeautifulSoup


def extract_website_info(url: str) -> dict:
    """
    Extract public information from a website using Requests and BeautifulSoup.

    Args:
        url: The website URL to extract information from.

    Returns:
        A dictionary with keys:
            - title: Page title (str)
            - description: Meta description (str)
            - content: Extracted visible text (str)
            - success: Whether extraction succeeded (bool)
            - error: Error message if failed (str or None)
    """
    result = {
        "title": "",
        "description": "",
        "content": "",
        "success": False,
        "error": None,
    }

    if not url:
        result["error"] = "No URL provided."
        return result

    # Normalize URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Extract the page title.
        title_tag = soup.find("title")
        result["title"] = title_tag.get_text(strip=True) if title_tag else ""

        # Extract the meta description.
        desc_tag = soup.find("meta", attrs={"name": "description"})
        if not desc_tag:
            desc_tag = soup.find("meta", attrs={"property": "og:description"})
        result["description"] = (
            desc_tag["content"] if desc_tag and desc_tag.get("content") else ""
        )

        # Extract visible text content.
        for elem in soup(["script", "style", "noscript", "header", "footer",
                          "nav", "svg", "img", "form"]):
            elem.decompose()

        main = soup.find("main")
        if main:
            text_content = main.get_text(separator=" ", strip=True)
        else:
            text_content = soup.get_text(separator=" ", strip=True)

        text_content = re.sub(r"\s+", " ", text_content)
        max_chars = 3000
        if len(text_content) > max_chars:
            text_content = text_content[:max_chars] + "..."

        result["content"] = text_content
        result["success"] = True

    except requests.exceptions.Timeout:
        result["error"] = "Website request timed out. The site may be slow or unreachable."
    except requests.exceptions.HTTPError as e:
        result["error"] = f"HTTP error {e.response.status_code}: could not access the page."
    except requests.exceptions.RequestException as e:
        # Keep the diagnostic useful without echoing the full URL (which could
        # contain private query parameters).
        detail = type(e).__name__
        cause = e.__cause__
        if cause:
            detail += f" ({type(cause).__name__})"
        result["error"] = f"Network error: could not reach the website ({detail})."
    except Exception as e:
        result["error"] = f"Extraction error: {str(e)[:100]}"

    return result

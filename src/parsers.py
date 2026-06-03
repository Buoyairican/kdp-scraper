"""
parsers.py — BeautifulSoup parsers for Amazon pages.

Centralised here so selector changes are one-file fixes.
Every function takes raw HTML and returns clean Python data.
Returns None / empty where data is unavailable — never fakes values.
"""

from __future__ import annotations
import re
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from src.logger import log


# ------------------------------------------------------------------ #
# Utility                                                             #
# ------------------------------------------------------------------ #

def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _clean_int(text: str) -> Optional[int]:
    """'1,234' or '1234 ratings' → 1234, or None."""
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


# ------------------------------------------------------------------ #
# CAPTCHA / block detection                                           #
# ------------------------------------------------------------------ #

BLOCK_SIGNALS = [
    "Type the characters you see in this image",
    "Enter the characters you see below",
    "Sorry, we just need to make sure you",
    "Robot Check",
    "api.crhc.amazon.com",
]


def is_blocked(html: str) -> bool:
    """True if Amazon returned a CAPTCHA or bot-check page."""
    for signal in BLOCK_SIGNALS:
        if signal in html:
            return True
    return False


# ------------------------------------------------------------------ #
# SERP page parser                                                    #
# ------------------------------------------------------------------ #

def parse_serp(html: str) -> list[dict]:
    """
    Parse Amazon search results page.

    Returns a list of dicts:
      { asin, title, review_count, is_sponsored }

    Sponsored results are flagged but NOT filtered here —
    Stage 3 does that filtering.
    """
    if is_blocked(html):
        log.warning("SERP parse: Amazon block/CAPTCHA detected.")
        return []

    soup = _soup(html)
    results = []

    for item in soup.select('[data-component-type="s-search-result"]'):
        asin = item.get("data-asin", "").strip()
        if not asin:
            continue

        # Title — current layout: h2 > span (no wrapping <a>)
        title_el = (
            item.select_one("h2 span")
            or item.select_one("h2 a span")
            or item.select_one("h2.a-size-mini a span, h2 a span.a-text-normal")
        )
        title = title_el.get_text(strip=True) if title_el else ""

        # Review count — current layout: a[href*=customerReviews] > span
        review_count: Optional[int] = None
        rev_link = item.select_one('a[href*="customerReviews"] span')
        if rev_link:
            review_count = _clean_int(rev_link.get_text())
        # Fallback: aria-label like "920 ratings"
        if review_count is None:
            ratings_el = item.select_one('span[aria-label$="ratings"]')
            if ratings_el:
                review_count = _clean_int(ratings_el.get("aria-label", ""))
        # Fallback: old layout with stars aria-label
        if review_count is None:
            stars_el = item.select_one('[aria-label*="stars"]')
            if stars_el:
                sib = stars_el.find_next_sibling()
                if sib:
                    review_count = _clean_int(sib.get_text())

        # Sponsored?
        sponsored_label = item.select_one(
            'span.puis-sponsored-label-text,'
            'span[aria-label="Sponsored"],'
            '.s-sponsored-label-info-icon'
        )
        is_sponsored = sponsored_label is not None

        results.append({
            "asin":         asin,
            "title":        title,
            "review_count": review_count,
            "is_sponsored": is_sponsored,
        })

    return results


# ------------------------------------------------------------------ #
# Product page parser                                                 #
# ------------------------------------------------------------------ #

def parse_product_page(html: str, asin: str) -> dict:
    """
    Extracts BSR, review count, publication date from a product page.

    Returns dict:
      { asin, title, review_count, bsr_books, bsr_sub, pub_date, format }
    All missing fields are None.
    """
    if is_blocked(html):
        log.warning(f"Product page {asin}: Amazon block/CAPTCHA detected.")
        return {"asin": asin, "error": "blocked"}

    soup = _soup(html)
    data = {"asin": asin}

    # ---- Title ----
    title_el = soup.select_one("#productTitle, #ebooksProductTitle")
    data["title"] = title_el.get_text(strip=True) if title_el else ""

    # ---- Review count ----
    rev_el = soup.select_one(
        "#acrCustomerReviewText,"
        "span#acrCustomerReviewLink span"
    )
    if rev_el:
        data["review_count"] = _clean_int(rev_el.get_text())
    else:
        # fallback: look for "X ratings" text
        rat_el = soup.find(string=re.compile(r"\d[\d,]* ratings"))
        data["review_count"] = _clean_int(rat_el) if rat_el else None

    # ---- BSR ----
    data["bsr_books"] = None
    data["bsr_sub"]   = None
    bsr_text = ""

    # Method 1: detail bullets (most common for paperback)
    for el in soup.select("#detailBulletsWrapper_feature_div li, #detailBullets_feature_div li"):
        text = el.get_text(" ", strip=True)
        if "Best Sellers Rank" in text:
            bsr_text = text
            break

    # Method 2: product details table (common for Kindle)
    if not bsr_text:
        for row in soup.select(
            "#productDetails_detailBullets_sections1 tr,"
            "#productDetails_db_sections tr,"
            "table.prodDetTable tr"
        ):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2 and "Best Sellers Rank" in cells[0].get_text():
                bsr_text = cells[1].get_text(" ", strip=True)
                break

    if bsr_text:
        # Extract the root "in Books" rank (first occurrence)
        m_books = re.search(r"#([\d,]+)\s+in\s+Books\b", bsr_text)
        if m_books:
            data["bsr_books"] = _clean_int(m_books.group(1))

        # Extract subcategory rank (second number, after "in Books")
        # Pattern: #X in <Subcategory Name> (Books)
        sub_matches = re.findall(r"#([\d,]+)\s+in\s+([^(#\n]+)", bsr_text)
        for rank_str, cat_name in sub_matches:
            if "books" not in cat_name.lower():  # skip the root
                rank_int = _clean_int(rank_str)
                if rank_int and (data["bsr_sub"] is None or rank_int < data["bsr_sub"]):
                    data["bsr_sub"] = rank_int

    # ---- Publication date ----
    data["pub_date"] = None
    pub_patterns = [
        # "Publication date : January 15, 2024"
        re.compile(r"Publication\s+date\s*[:\–-]\s*([\w]+ \d{1,2},\s*\d{4})", re.I),
        # "Publisher ‏ : ‎ Some Press (January 15, 2024)"
        re.compile(r"\((\w+ \d{1,2},\s*\d{4})\)"),
    ]
    full_text = soup.get_text(" ")
    for pat in pub_patterns:
        m = pat.search(full_text)
        if m:
            raw_date = m.group(1).strip()
            try:
                parsed = datetime.strptime(raw_date, "%B %d, %Y")
                data["pub_date"] = parsed.date().isoformat()
                break
            except ValueError:
                try:
                    parsed = datetime.strptime(raw_date, "%d %B %Y")
                    data["pub_date"] = parsed.date().isoformat()
                    break
                except ValueError:
                    continue

    # ---- Format ----
    # Heuristic: Kindle page URL or "Kindle Edition" text
    kindle_el = soup.find('span', class_='a-size-medium', string=re.compile(r'Kindle'))
    if not kindle_el:
        kindle_el = soup.find('a', href=re.compile(r'/Kindle-eBooks/'))
    data["format"] = "kindle" if kindle_el else "paperback"

    return data


# ------------------------------------------------------------------ #
# Category page parser                                                #
# ------------------------------------------------------------------ #

def parse_category_top_results(html: str) -> list[dict]:
    """
    Same structure as SERP but used for category browse pages.
    Returns top results with ASIN + review_count.
    """
    return parse_serp(html)

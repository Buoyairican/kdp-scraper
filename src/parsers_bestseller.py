"""
parsers_bestseller.py — Parser for Amazon Best Sellers list pages.

URL pattern: /best-sellers-books-Amazon/zgbs/books/{NODE_ID}?pg=N

Each page shows 50 books with: rank, title, author, star rating,
review count, price, and ASIN (in the product link).
"""

from __future__ import annotations
import re
from typing import Optional

from bs4 import BeautifulSoup

from src.logger import log


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _clean_int(text: str) -> Optional[int]:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def parse_bestseller_list(html: str, page_offset: int = 0) -> list[dict]:
    """
    Parse an Amazon Best Sellers list page.

    Returns list of dicts:
      { rank, asin, title, review_count, star_rating, author }

    page_offset: added to position-based rank (0 for page 1, 50 for page 2).
    """
    soup = _soup(html)
    results = []

    # Amazon bestseller list items — primary: ordered list structure
    lists = soup.find_all("ol", class_="zg-ordered-list")
    items = [item for ol in lists for item in ol.find_all("li", recursive=False)]

    if not items:
        items = soup.select('[id^="gridItemRoot"]')
    if not items:
        items = soup.select(".zg-grid-general-faceout")
    if not items:
        items = soup.select('[data-asin]')

    log.info(f"Bestseller parser: found {len(items)} items")

    for idx, item in enumerate(items):
        rank = page_offset + idx + 1

        # Try to get explicit rank number from the page
        rank_el = item.select_one(".zg-bdg-text, span.zg-badge-text")
        if rank_el:
            rank_num = _clean_int(rank_el.get_text())
            if rank_num:
                rank = rank_num

        # ASIN from link
        asin = ""
        link = item.select_one('a[href*="/dp/"]')
        if link:
            href = link.get("href", "")
            m = re.search(r"/dp/([A-Z0-9]{10})", href)
            if m:
                asin = m.group(1)

        if not asin:
            asin = item.get("data-asin", "")

        # Title
        title = ""
        title_el = item.select_one(
            "a.a-link-normal span div,"
            " a.a-link-normal .p13n-sc-truncate,"
            " ._cDEzb_p13n-sc-css-line-clamp-1_1Fn1y,"
            " .zg-text-center-align .p13n-sc-truncated,"
            " a[href*='/dp/'] span"
        )
        if title_el:
            title = title_el.get_text(strip=True)
        if not title:
            # Fallback: first link with /dp/ that has text
            if link:
                title = link.get_text(strip=True)

        # Review count
        review_count = None
        rev_el = item.select_one(
            "span.a-size-small,"
            " .a-icon-row a.a-size-small,"
            " a[href*='customerReviews']"
        )
        if rev_el:
            review_count = _clean_int(rev_el.get_text())

        # Star rating
        star_rating = None
        star_el = item.select_one('[class*="a-icon-star"]')
        if star_el:
            aria = star_el.get("aria-label", "") or star_el.get_text()
            m = re.search(r"([\d.]+)", aria)
            if m:
                try:
                    star_rating = float(m.group(1))
                except ValueError:
                    pass

        # Author
        author = ""
        author_el = item.select_one(".a-row.a-size-small .a-link-normal + span, .a-size-small.a-color-base")
        if author_el:
            author = author_el.get_text(strip=True)

        if asin or title:
            results.append({
                "rank": rank,
                "asin": asin,
                "title": title,
                "review_count": review_count,
                "star_rating": star_rating,
                "author": author,
            })

    if not results:
        log.warning("Bestseller parser: no items found. Page structure may have changed.")

    return results

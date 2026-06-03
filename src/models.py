"""
models.py — Data classes and classification logic.
All thresholds read from config, not hardcoded here.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
import config


@dataclass
class Book:
    asin: str
    title: str
    author: str = ""
    bsr_books: Optional[int] = None   # BSR in the Books root category
    bsr_sub: Optional[int] = None     # BSR in the subcategory (informational)
    review_count: Optional[int] = None
    pub_date: Optional[str] = None    # ISO format YYYY-MM-DD
    format: str = "paperback"         # paperback | kindle
    scrape_date: str = field(default_factory=lambda: datetime.utcnow().date().isoformat())
    classification: str = "UNKNOWN"   # set by classify()

    def classify(self) -> str:
        """
        Applies classification rules from kdp-scraper.md.
        UNKNOWN if essential data is missing.
        """
        if self.review_count is None or self.bsr_books is None:
            self.classification = "UNKNOWN"
            return self.classification

        # AUTHORITY wins over everything when review count is high
        if self.review_count >= config.REVIEWS_AUTHORITY_MIN:
            self.classification = "AUTHORITY"
            return self.classification

        # DEAD checks
        if self.bsr_books > config.BSR_DEAD_HARD:
            self.classification = "DEAD"
            return self.classification
        if self.bsr_books > config.BSR_DEAD_SOFT and self.review_count > config.REVIEWS_DEAD_SOFT:
            self.classification = "DEAD"
            return self.classification
        if self.pub_date and self.pub_date < config.PUB_DATE_DEAD_MAX:
            self.classification = "DEAD"
            return self.classification

        # WINNING
        bsr_threshold = (
            config.BSR_WINNING_KINDLE
            if self.format == "kindle"
            else config.BSR_WINNING_PAPERBACK
        )
        if (
            self.bsr_books <= bsr_threshold
            and self.review_count < config.REVIEWS_WINNING_MAX
            and (self.pub_date is None or self.pub_date >= config.PUB_DATE_WINNING_MIN)
        ):
            self.classification = "WINNING"
            return self.classification

        self.classification = "INCONCLUSIVE"
        return self.classification

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class KeywordResult:
    keyword: str
    winning_count: int = 0
    authority_count: int = 0
    dead_count: int = 0
    inconclusive_count: int = 0
    unknown_count: int = 0
    avg_bsr_top3: Optional[float] = None
    books: list = field(default_factory=list)   # list of Book dicts
    verdict: str = "SKIP"

    def score(self) -> str:
        """Applies GO / WATCH / SKIP verdict."""
        if (
            self.winning_count >= config.GO_WINNING
            and self.authority_count <= config.GO_MAX_AUTHORITY
        ):
            self.verdict = "GO"
        elif self.winning_count >= config.WATCH_WINNING:
            self.verdict = "WATCH"
        else:
            self.verdict = "SKIP"
        return self.verdict

    def to_csv_row(self) -> dict:
        return {
            "keyword":           self.keyword,
            "winning_count":     self.winning_count,
            "authority_count":   self.authority_count,
            "dead_count":        self.dead_count,
            "inconclusive_count":self.inconclusive_count,
            "unknown_count":     self.unknown_count,
            "avg_bsr_top3":      round(self.avg_bsr_top3) if self.avg_bsr_top3 else "",
            "verdict":           self.verdict,
        }


# Seed nonfiction categories — node ID + human label.
# These are the stable Amazon browse nodes for non-fiction.
# Stage 1 validates which ones show buying signal.
NONFICTION_SEED_CATEGORIES = [
    {"node": "283155",  "label": "Books (root)"},
    {"node": "10",      "label": "Health, Fitness & Dieting"},
    {"node": "17",      "label": "Self-Help"},
    {"node": "491300",  "label": "Business & Money"},
    {"node": "9",       "label": "History"},
    {"node": "14",      "label": "Parenting & Relationships"},
    {"node": "22",      "label": "Religion & Spirituality"},
    {"node": "23",      "label": "Science & Math"},
    {"node": "26",      "label": "Sports & Outdoors"},
    {"node": "6",       "label": "Cookbooks, Food & Wine"},
    {"node": "1642",    "label": "Politics & Social Sciences"},
    {"node": "2702",    "label": "Education & Teaching"},
    {"node": "173507",  "label": "Medical Books"},
    {"node": "4218",    "label": "Law"},
    {"node": "4",       "label": "Children's Books"},
    {"node": "21",      "label": "Test Preparation"},
    {"node": "2581",    "label": "Crafts, Hobbies & Home"},
    {"node": "75",      "label": "Travel"},
    {"node": "3510",    "label": "Engineering & Transportation"},
    {"node": "1000",    "label": "Arts & Photography"},
    {"node": "2",       "label": "Biographies & Memoirs"},
    {"node": "6656742011", "label": "Teen & Young Adult"},
    {"node": "173514",  "label": "Christian Books & Bibles"},
    {"node": "11232",   "label": "Comics & Graphic Novels"},
    {"node": "4736",    "label": "Gay & Lesbian"},
    {"node": "549",     "label": "Computers & Technology"},
    {"node": "130",     "label": "Reference"},
    {"node": "15306",   "label": "Professional & Technical"},
    {"node": "4356",    "label": "Psychology & Counseling"},
    {"node": "53",      "label": "Business Communication"},
]

# ============================================================
# KDP Research Pipeline — Configuration
# ============================================================
# To swap scraping providers: change SCRAPER_PROVIDER in .env.
# Valid values: "scrapingant" | "scraperapi" | "oxylabs" | "scrapingbee"
# ============================================================

import os

from dotenv import load_dotenv


load_dotenv()

SCRAPER_PROVIDER = os.getenv("SCRAPER_PROVIDER", "scrapingbee")

# --- API credentials ---
SCRAPINGANT_API_KEY = os.getenv("SCRAPINGANT_API_KEY", "")
SCRAPERAPI_API_KEY = os.getenv("SCRAPERAPI_API_KEY", "")
OXYLABS_USERNAME = os.getenv("OXYLABS_USERNAME", "")
OXYLABS_PASSWORD = os.getenv("OXYLABS_PASSWORD", "")
SCRAPINGBEE_API_KEY = os.getenv("SCRAPINGBEE_API_KEY", "")

# --- Credit safety threshold ---
# Script exits cleanly when remaining credits fall below this number.
CREDIT_RESERVE = 20

# --- Request behaviour ---
JS_RENDER           = True       # use headless browser to bypass anti-bot (costs more credits)
REQUEST_TIMEOUT     = 120       # seconds per call (higher for JS render)
RETRY_ATTEMPTS      = 3
RETRY_BACKOFF_BASE  = 2         # exponential: 2^attempt seconds
DELAY_BETWEEN_CALLS = 1.5       # seconds — keeps request cadence human-like

# --- Skip list — overly broad nodes that always produce SKIP ---
SKIP_NODES = ["2745"]  # Entrepreneurship

# --- Stage 1 — Category Discovery ---
# Minimum top-results to pull per category check
S1_RESULTS_PER_CATEGORY = 5
# How many categories must survive Stage 1 before proceeding
S1_MIN_SURVIVING = 3

# --- Stage 2 — Alphabet Soup ---
# Max keyword candidates to carry forward into Stage 3
S2_MAX_CANDIDATES = 200

# --- Stage 3 — SERP Filter ---
# Number of organic (non-sponsored) results to read per keyword
S3_ORGANIC_RESULTS = 5
# Max authority books on page 1 before keyword is dropped
S3_MAX_AUTHORITY_ON_PAGE1 = 2
# Minimum winning books on page 1 required to pass SERP filter
S3_MIN_WINNING_ON_PAGE1   = 1

# --- Stage 4 — BSR Confirmation ---
# Top-N books per keyword to pull full product page for
S4_BOOKS_PER_KEYWORD = 3

# --- Classification thresholds (from kdp-scraper.md) ---
BSR_WINNING_PAPERBACK  = 300_000
BSR_WINNING_KINDLE     = 70_000
REVIEWS_WINNING_MAX    = 100
REVIEWS_AUTHORITY_MIN  = 300
BSR_DEAD_HARD          = 500_000
BSR_DEAD_SOFT          = 150_000
REVIEWS_DEAD_SOFT      = 30
PUB_DATE_WINNING_MIN   = "2024-01-01"
PUB_DATE_DEAD_MAX      = "2022-01-01"

# --- Scoring thresholds for GO / WATCH / SKIP ---
# GO:   winning_count >= GO_WINNING  AND authority_count <= GO_MAX_AUTHORITY
# WATCH: winning_count >= WATCH_WINNING
# SKIP: everything else
GO_WINNING        = 3
GO_MAX_AUTHORITY  = 3
WATCH_WINNING     = 1

# --- Output ---
OUTPUT_CSV = "output/results.csv"
STATE_FILE = "state/pipeline_state.json"
LOG_FILE   = "state/run_log.txt"

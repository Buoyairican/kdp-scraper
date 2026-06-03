# Required Skills from Existing GitHub Repositories

## Core Tech Stack (Use these repos as reference)

### 1. Playwright Amazon Scraping
- **Rahulmodi3/amazon-web-scraping-playwright-python**  
  https://github.com/Rahulmodi3/amazon-web-scraping-playwright-python  
  → Excellent for scraping Amazon Best Sellers & product data with Playwright.

- **HasData/playwright-scraping**  
  https://github.com/HasData/playwright-scraping  
  → Contains `scrape_products_amazon.py` – direct Amazon search/product scraping examples.

- **scraper-bank/Amazon.com-Scrapers**  
  https://github.com/scraper-bank/Amazon.com-Scrapers  
  → Production-ready scrapers for **Search Results (SERP)** and **Product Pages** using Playwright + Scrapy.

### 2. Search Results + Review Count Scraping
- **scrapehero-code/amazon-scraper**  
  https://github.com/scrapehero-code/amazon-scraper  
  → Search results scraper (`searchresults.py`) – perfect for Stage 3 (top organic results, review counts).

- **luminati-io/amazon-products-search-scraper**  
  https://github.com/luminati-io/amazon-products-search-scraper  
  → Dedicated Amazon Search Results scraper (handles sponsored filtering).

### 3. Product Page + BSR Scraping
- **oxylabs/how-to-scrape-amazon-product-data**  
  https://github.com/oxylabs/how-to-scrape-amazon-product-data  
  → Strong examples for extracting BSR, publication date, ratings from product pages.

### 4. Amazon Autocomplete (Alphabet Soup - Stage 2)
- **michaellopez7032-pixel/amazon-search-autocomplete-api**  
  https://github.com/michaellopez7032-pixel/amazon-search-autocomplete-api  
  → Amazon search autocomplete scraper.

### 5. State Management & Resumable Scrapers
- Look for patterns in Scrapy projects with `JOBDIR` (built-in resume).  
- General resumable examples: Search "scrapy resume" or use JSON/TinyDB state in the Playwright repos above.

## Additional Recommended Skills to Implement

- **Playwright + playwright-stealth** (or patches) for anti-detection.
- **BeautifulSoup4** or **Selectolax** for parsing review counts and BSR.
- **JSON / TinyDB** for state saving after every stage/keyword.
- **tenacity** for retries + exponential backoff.
- **loguru** for logging.
- **Pandas** for CSV output.
- Rotating proxies + random delays/human-like behavior.

## API Swap Capability
Study Oxylabs and ScraperAPI examples in their GitHub repos (they show easy payload switching between sources).

**Instruction to Claude**:  
Study the above repositories (especially Rahulmodi3, HasData, scraper-bank, and scrapehero-code) and build the 5-stage scraper using their proven patterns for Playwright Amazon SERP + Product scraping, while adding full JSON state management for resumability.
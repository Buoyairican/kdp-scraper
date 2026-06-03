Topics: amazon-kdp · kdp-research · web-scraping · publisher-rocket-alternative · kindle-publishing · niche-research · passive-income

# KDP Niche Research Pipeline

Free KDP niche research pipeline for finding low competition book niches on Amazon. Use it as an open-source Publisher Rocket alternative / KDP Spy alternative when you want a scriptable Amazon bestseller scraper that turns seed titles into GO/WATCH/SKIP publishing signals.

This KDP keyword research tool starts from a book title you've spotted, finds its category nodes, scans the top 100 books in each node, filters obvious low-content spam, and outputs verdicts with winning and authority counts for content planning.

![Demo](demo.gif)

Sample output:

| Category | Verdict | Winning books | Authority books | Signal |
|----------|---------|---------------|-----------------|--------|
| Assisted Living Facility Guides | GO | 5 | 2 | Demand with weak competition |
| Senior Care Business | WATCH | 3 | 6 | Good demand, stronger incumbents |
| Entrepreneurship | SKIP | 0 | 18 | Too broad or too competitive |

GitHub repo description: Free KDP niche research tool and Amazon bestseller scraper for low-competition book niches.

---

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:
1. Set `SCRAPER_PROVIDER` to `"scrapingbee"` (or `"scrapingant"`, `"scraperapi"`, `"oxylabs"`)
2. Set the corresponding API key or provider credentials
3. Adjust thresholds in `config.py` if needed

---

## Usage

```bash
# New analysis with a seed title
python main.py --title "How To Start An Assisted Living Facility"

# Resume from last checkpoint
python main.py --resume

# Check progress
python main.py --status

# Wipe state and start fresh
python main.py --reset
```

### Parallel Sessions

Run multiple analyses simultaneously using `--session`:

```bash
# Each session gets its own state file and output folder
python main.py --title "Assisted Living Facility Guide" --session assisted_living
python main.py --title "Candle Making Business" --session candle_making

# Resume a specific session
python main.py --resume --session assisted_living

# Check status of a session
python main.py --status --session candle_making
```

Sessions are stored in `state/{session_name}.json` with output in `output/{session_name}/`.

---

## Pipeline Stages

| Stage | What it does | API calls |
|-------|-------------|-----------|
| 1 | Search seed title on Amazon, find ASIN, extract BSR category nodes | 2 (js=False) |
| 2 | Fetch bestseller lists (top 100 per node), classify books, compute verdict | 2 per node (js=True) |
| 3 | Extract keyword seeds from winning titles, run alphabet soup expansion | 0 (free autocomplete API) |

**Estimated credit cost:** ~100-200 credits per full run (8 ScrapingBee calls total).

---

## Classification

Books on the bestseller list are classified by rank + review count:

| Class | Rule |
|-------|------|
| WINNING | rank <= 50 AND reviews < 75 |
| AUTHORITY | reviews >= 500 |
| LOW-CONTENT | title contains journal/log/planner/workbook/etc. (excluded) |
| INCONCLUSIVE | everything else |

### Verdicts (per category node)

| Verdict | Rule |
|---------|------|
| **GO** | winning >= 3 AND authority <= 3 |
| **WATCH (high-win)** | winning >= 8 but authority > 3 |
| **WATCH** | winning >= 1 |
| **SKIP** | no winning books found |

---

## Output

`output/results_YYYYMMDD_HHMMSS.csv` (or `output/{session}/results_...csv`)

Three sections:
1. **Node Verdicts** - node_id, category, verdict, winning/authority counts
2. **Winning Books** - category, rank, title, review_count, ASIN
3. **Keyword Variations** - alphabet soup expansions from top bigram/trigram seeds

Use the CSV as a starting point for KDP niche research: compare the winning counts, authority counts, and keyword variations before committing to a book outline.

---

## Low-Content Filter

Books with these keywords in the title are automatically excluded from classification:

> journal, log, workbook, planner, notebook, tracker, diary, organizer, checklist, logbook, record book, activity book, coloring, puzzle, word search, sudoku, lined pages, dot grid

This prevents low-content/KDP spam books from inflating winning counts or polluting keyword seeds.

---

## Resume Behaviour

State is saved to `state/pipeline_state.json` after every API call.
If interrupted (crash, credits exhausted, CAPTCHA, Ctrl+C), re-run with `--resume` to pick up exactly where it stopped.

---

## Credit Exhaustion

When credits fall to `CREDIT_RESERVE` (default: 20), the script saves state and exits cleanly. Re-run after topping up.

---

## CAPTCHA Handling

If Amazon returns a CAPTCHA, the script logs it and stops. State is saved. Resume after a few minutes or switch providers.

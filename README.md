# Chennai Early-Career Job Tracker

A local, configuration-driven tracker for **fresher and early-career jobs in Chennai**, with a dedicated ranking layer for software development roles.

## What changed

- **Wider source coverage:** Freshersworld (general + software-specific), LinkedIn, Indeed, Naukri, Internshala, Foundit, and Shine search pages are configured.
- **Software-first ranking:** titles are classified into Software development, Data & AI, QA & testing, IT support, or Other early career and receive a transparent fit score.
- **Better filtering:** Chennai location and experience are checked, senior/mid-career signals are excluded, and prefilted fresher portals are supported.
- **More resilient extraction:** CSS selectors are tried in order, then standard `JobPosting` JSON-LD is used as a fallback.
- **Honest source health:** robots.txt blocks, HTTP errors, and pages with changed markup appear in the dashboard instead of being silently counted as zero.
- **Improved dashboard:** software focus, all early-career, and new-today views; search; sorting; role-mix bars; source coverage; and responsive job cards.

> Job portals can block automated requests or change their HTML. The tracker reports those conditions; it does not bypass them. Always open the original posting and verify its freshness before applying.

## Run it

```bash
pip install -r requirements.txt
python enhanced_scraper.py
# Optional: rerun every 30 minutes
python enhanced_scraper.py --realtime --interval 30
```

Then open `dashboard.html`. The scraper writes:

- `jobs_db.json` — persistent deduplicated job history
- `dashboard_data.js` — browser-readable dashboard payload
- `scraper.log` — source and run diagnostics

## Configuration

Edit `config.json` to enable/disable sources, change search pages, adjust the 1-year experience ceiling, or tune request delays. A source should only be enabled where the page is public and its terms permit personal, polite access.

Useful settings:

- `location_filter`: currently `Chennai`
- `max_experience_years`: currently `1`
- `retry_attempts`: transient request retries
- `source_delay_seconds`: delay between portals

## Current live run

The verified rebuild on 28 September 2026 crawled **40 current listing cards**, followed their detail URLs, retained **10 verified jobs**, and placed **30 records in Needs verification**. Legacy records from earlier scraper versions were removed. The trusted feed never includes an unverified or generic employer name.

## Deploy on Render

The repository includes [`render.yaml`](render.yaml) and `render-build.sh` for a Render Blueprint static-site deploy.

- Render uses the free static-site plan.
- Each deploy installs the Python dependencies, runs one scraper cycle, and publishes only `dashboard.html` and `dashboard_data.js` from `dist/`.
- Scraper source code, configuration, logs, and the job database are not exposed by the deployed site.
- The dashboard is a static snapshot; to refresh it, trigger a new deploy or run the scraper locally and push the generated data. Each deploy also crawls job-detail pages and rebuilds the verified/review split.

In Render, choose **New → Blueprint**, select `SyedAshraf49/Tracker`, and apply the Blueprint. Render will read the committed `render.yaml` automatically.

If you create a **Web Service** manually instead of using the Blueprint, use this start command so Render serves the published dashboard rather than the repository directory:

```bash
python3 -m http.server $PORT --bind 0.0.0.0 --directory dist
```

The root `index.html` is also included as a safe fallback for services that are still pointed at the repository root.

## Verified collection

The scraper now uses source-specific listing adapters, follows each job-detail URL, reads `JobPosting` JSON-LD and detail-page metadata, normalizes titles, separates recruiter names, and writes `verification_status` values of `verified` or `needs_verification`. Only verified records appear in the main dashboard feed. Saved HTML fixtures in `tests/fixtures/` protect the Freshersworld and Internshala parsers from selector regressions; run `python3 -m unittest discover -s tests -v`.

## Dashboard UI

The dashboard is intentionally dark and compact. Each listing shows only the requested essentials: **company**, **role**, an **initial JD snapshot**, **date posted** when supplied by the source, the original **link**, and **where it was scraped from**. Fit percentages are not displayed.

### Source policy

Some large portals reject automated access in the Render build environment with robots rules or HTTP 403/404 responses. Those sources remain documented in `config.json` with their selectors, but are disabled by default so deploys stay fast and reliable. The scraper now treats permanent 401/403/404/410 responses as terminal and only retries transient failures such as timeouts, 429, and 5xx responses. Re-enable a source only after confirming its current terms and public page behavior.

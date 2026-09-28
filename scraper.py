#!/usr/bin/env python3
"""
Fresher Job Scraper
--------------------
Reads sources from config.json, scrapes each one, filters for fresher/entry-level
roles, and tracks which postings are NEW since the last run.

Run this once a day (manually, or via cron / Windows Task Scheduler - see README).

Outputs:
  - jobs_db.json         : full running history of every job ever seen
  - dashboard_data.js    : data file the dashboard.html reads (auto-generated, don't edit)
"""

import json
import hashlib
import time
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urljoin
from urllib import robotparser

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
DB_PATH = BASE_DIR / "jobs_db.json"
DASHBOARD_DATA_PATH = BASE_DIR / "dashboard_data.js"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36"
}
REQUEST_DELAY_SECONDS = 2  # be polite between requests


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_db():
    if DB_PATH.exists():
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_db(db):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def make_job_id(company, title, link):
    raw = f"{company}|{title}|{link}".lower().strip()
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def robots_allows(url):
    """Best-effort robots.txt check. If it can't be checked, default to allow
    but you should still manually confirm scraping is acceptable for that site."""
    try:
        parts = url.split("/")
        base = f"{parts[0]}//{parts[2]}"
        rp = robotparser.RobotFileParser()
        rp.set_url(urljoin(base, "/robots.txt"))
        rp.read()
        return rp.can_fetch(HEADERS["User-Agent"], url)
    except Exception:
        return True  # couldn't determine - proceed cautiously, log a warning


def matches_fresher_keywords(text, keywords):
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def extract_text(el):
    return el.get_text(strip=True) if el else ""


def scrape_source(source, fresher_keywords):
    """Returns a list of dicts: {company, title, link, location}"""
    url = source["url"]
    print(f"  -> Fetching {url}")

    if not robots_allows(url):
        print(f"  !! robots.txt disallows scraping this URL. Skipping: {url}")
        return []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  !! Request failed for {url}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    cards = soup.select(source["job_card_selector"])
    print(f"  -> Found {len(cards)} raw job cards")

    results = []
    for card in cards:
        title_el = card.select_one(source["title_selector"])
        title = extract_text(title_el)
        if not title:
            continue

        if source["type"] == "aggregator":
            company_el = card.select_one(source.get("company_selector", ""))
            company = extract_text(company_el) or "Unknown"
        else:
            company = source.get("company_name", "Unknown")

        link_el = card.select_one(source["link_selector"])
        link = ""
        if link_el and link_el.has_attr(source.get("link_attr", "href")):
            link = link_el[source.get("link_attr", "href")]
            link = urljoin(source.get("link_base", url), link)

        location = ""
        if source.get("location_selector"):
            loc_el = card.select_one(source["location_selector"])
            location = extract_text(loc_el)

        # Filter for fresher roles unless the source URL is already pre-filtered
        if not source.get("already_filtered_for_freshers", False):
            if not matches_fresher_keywords(title, fresher_keywords):
                continue

        results.append({
            "company": company,
            "title": title,
            "link": link,
            "location": location,
            "source": source["name"],
        })

    return results


def main():
    config = load_config()
    db = load_db()
    today = date.today().isoformat()

    enabled_sources = [s for s in config["sources"] if s.get("enabled", False)]
    if not enabled_sources:
        print("No sources are enabled in config.json.")
        print("Open config.json, copy the TEMPLATE block, fill in real selectors,")
        print("and set \"enabled\": true. See README.md for how to find selectors.")
        sys.exit(0)

    new_today = []

    for source in enabled_sources:
        print(f"\nScraping: {source['name']}")
        jobs = scrape_source(source, config["fresher_keywords"])

        for job in jobs:
            job_id = make_job_id(job["company"], job["title"], job["link"])
            if job_id not in db:
                job["first_seen"] = today
                db[job_id] = job
                new_today.append(job)
            # else: already seen before, skip (no duplicate spam in dashboard)

        time.sleep(REQUEST_DELAY_SECONDS)

    save_db(db)

    # Write data file for the dashboard (plain JS so dashboard.html works
    # by double-click, no local server needed)
    all_jobs = list(db.values())
    all_jobs.sort(key=lambda j: j.get("first_seen", ""), reverse=True)

    payload = {
        "generated_at": today,
        "all_jobs": all_jobs,
        "today_count": len(new_today),
    }
    with open(DASHBOARD_DATA_PATH, "w", encoding="utf-8") as f:
        f.write("const JOBS_DATA = ")
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write(";\n")

    print(f"\nDone. {len(new_today)} new fresher role(s) found today.")
    print(f"Total roles tracked: {len(all_jobs)}")
    print(f"Open dashboard.html in your browser to view them.")


if __name__ == "__main__":
    main()

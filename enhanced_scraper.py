#!/usr/bin/env python3
"""
Enhanced Fresher Job Scraper - Real-Time Edition
-------------------------------------------------
Scrapes fresher jobs from multiple career websites in Chennai with real-time updates.

Features:
  - Multi-source scraping (10+ job portals)
  - Real-time continuous monitoring
  - Selenium support for dynamic websites
  - Better Chennai location filtering
  - Enhanced fresher job detection
  - Duplicate detection
  - Auto-retry on failures

Usage:
  python enhanced_scraper.py              # Run once
  python enhanced_scraper.py --realtime   # Run continuously with scheduled updates
  python enhanced_scraper.py --interval 30 # Run every 30 minutes
"""

import json
import hashlib
import time
import sys
import argparse
import logging
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urljoin
from urllib import robotparser
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup
import schedule

# Selenium imports (optional, will gracefully degrade)
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("Warning: Selenium not available. Sites requiring JavaScript will be skipped.")
    print("Install with: pip install selenium webdriver-manager")

# Setup
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
DB_PATH = BASE_DIR / "jobs_db.json"
DASHBOARD_DATA_PATH = BASE_DIR / "dashboard_data.js"
LOG_PATH = BASE_DIR / "scraper.log"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


class JobScraper:
    def __init__(self, config_path: Path = CONFIG_PATH):
        self.config = self.load_config(config_path)
        self.db = self.load_db()
        self.driver = None
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        
    def load_config(self, path: Path) -> dict:
        """Load configuration from JSON file"""
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def load_db(self) -> dict:
        """Load existing job database"""
        if DB_PATH.exists():
            with open(DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    
    def save_db(self):
        """Save job database to file"""
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump(self.db, f, indent=2, ensure_ascii=False)
    
    def get_selenium_driver(self):
        """Initialize Selenium WebDriver (lazy loading)"""
        if not SELENIUM_AVAILABLE:
            return None
            
        if self.driver is None:
            try:
                chrome_options = Options()
                if self.config.get("scraper_settings", {}).get("headless_browser", True):
                    chrome_options.add_argument("--headless")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-blink-features=AutomationControlled")
                chrome_options.add_argument(f"user-agent={HEADERS['User-Agent']}")
                
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("Selenium WebDriver initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Selenium: {e}")
                return None
        return self.driver
    
    def close_driver(self):
        """Close Selenium WebDriver"""
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
            except Exception as e:
                logger.error(f"Error closing driver: {e}")
    
    def make_job_id(self, company: str, title: str, link: str) -> str:
        """Generate unique job ID"""
        raw = f"{company}|{title}|{link}".lower().strip()
        return hashlib.md5(raw.encode("utf-8")).hexdigest()
    
    def matches_keywords(self, text: str, keywords: List[str]) -> bool:
        """Check if text matches any keyword"""
        if not text:
            return False
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in keywords)
    
    def extract_text(self, element) -> str:
        """Safely extract text from BeautifulSoup element"""
        return element.get_text(strip=True) if element else ""
    
    def is_chennai_location(self, location: str) -> bool:
        """Check if location is Chennai"""
        if not location:
            return False
        location_keywords = self.config.get("location_keywords", ["chennai"])
        return self.matches_keywords(location, location_keywords)
    
    def is_fresher_job(self, title: str, experience: str = "") -> bool:
        """Determine if job is for freshers"""
        fresher_keywords = self.config.get("fresher_keywords", [])
        combined_text = f"{title} {experience}"
        return self.matches_keywords(combined_text, fresher_keywords)
    
    def robots_allows(self, url: str) -> bool:
        """Check if robots.txt allows scraping"""
        try:
            parts = url.split("/")
            base = f"{parts[0]}//{parts[2]}"
            rp = robotparser.RobotFileParser()
            rp.set_url(urljoin(base, "/robots.txt"))
            rp.read()
            return rp.can_fetch(HEADERS["User-Agent"], url)
        except Exception:
            return True  # Default to allow if check fails
    
    def fetch_with_requests(self, url: str, timeout: int = 20) -> Optional[BeautifulSoup]:
        """Fetch page using requests library"""
        try:
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except requests.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            return None
    
    def fetch_with_selenium(self, url: str, wait_selector: str = None, timeout: int = 20) -> Optional[BeautifulSoup]:
        """Fetch page using Selenium for dynamic content"""
        driver = self.get_selenium_driver()
        if not driver:
            logger.warning(f"Selenium not available for {url}")
            return None
        
        try:
            driver.get(url)
            if wait_selector:
                WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector))
                )
            else:
                time.sleep(3)  # Wait for dynamic content
            
            return BeautifulSoup(driver.page_source, "lxml")
        except Exception as e:
            logger.error(f"Selenium fetch failed for {url}: {e}")
            return None
    
    def scrape_source(self, source: dict) -> List[dict]:
        """Scrape jobs from a single source"""
        url = source["url"]
        source_name = source["name"]
        logger.info(f"Scraping: {source_name}")
        logger.info(f"  URL: {url}")
        
        # Check robots.txt
        if not self.robots_allows(url):
            logger.warning(f"  Robots.txt disallows scraping: {url}")
            return []
        
        # Fetch page
        if source.get("requires_selenium", False):
            soup = self.fetch_with_selenium(url, source.get("job_card_selector"))
        else:
            soup = self.fetch_with_requests(url)
        
        if not soup:
            logger.error(f"  Failed to fetch page content")
            return []
        
        # Extract job cards
        job_card_selector = source["job_card_selector"]
        cards = soup.select(job_card_selector)
        logger.info(f"  Found {len(cards)} job cards with selector: {job_card_selector}")
        
        if len(cards) == 0:
            # Try alternative selectors if available
            selectors = job_card_selector.split(", ")
            for alt_selector in selectors:
                cards = soup.select(alt_selector.strip())
                if len(cards) > 0:
                    logger.info(f"  Alternative selector worked: {alt_selector} - found {len(cards)} cards")
                    break
        
        if len(cards) == 0:
            logger.warning(f"  No job cards found. Page structure may have changed.")
            logger.debug(f"  Page preview: {soup.get_text()[:500]}")
            return []
        
        results = []
        for idx, card in enumerate(cards):
            try:
                # Extract title with multiple selector attempts
                title = ""
                title_selectors = source["title_selector"].split(", ")
                for ts in title_selectors:
                    title_el = card.select_one(ts.strip())
                    if title_el:
                        title = self.extract_text(title_el)
                        if title:
                            break
                
                if not title:
                    logger.debug(f"  Card {idx+1}: No title found")
                    continue
                
                # Extract company
                company = ""
                if source["type"] == "aggregator":
                    company_selectors = source.get("company_selector", "").split(", ")
                    for cs in company_selectors:
                        if cs:
                            company_el = card.select_one(cs.strip())
                            if company_el:
                                company = self.extract_text(company_el)
                                if company:
                                    break
                    if not company:
                        company = "Unknown"
                else:
                    company = source.get("company_name", "Unknown")
                
                # Extract link
                link = ""
                link_selectors = source["link_selector"].split(", ")
                for ls in link_selectors:
                    link_el = card.select_one(ls.strip())
                    if link_el and link_el.has_attr(source.get("link_attr", "href")):
                        link = link_el[source.get("link_attr", "href")]
                        if link:
                            link = urljoin(source.get("link_base", url), link)
                            break
                
                # Extract location
                location = ""
                if source.get("location_selector"):
                    loc_selectors = source.get("location_selector", "").split(", ")
                    for loc_s in loc_selectors:
                        if loc_s:
                            loc_el = card.select_one(loc_s.strip())
                            if loc_el:
                                location = self.extract_text(loc_el)
                                if location:
                                    break
                
                # Extract experience (if available)
                experience = ""
                if source.get("experience_selector"):
                    exp_selectors = source.get("experience_selector", "").split(", ")
                    for exp_s in exp_selectors:
                        if exp_s:
                            exp_el = card.select_one(exp_s.strip())
                            if exp_el:
                                experience = self.extract_text(exp_el)
                                if experience:
                                    break
                
                # Filter for Chennai (if location filtering is enabled)
                settings = self.config.get("scraper_settings", {})
                if settings.get("location_filter", "").lower() == "chennai":
                    if location and not self.is_chennai_location(location):
                        logger.debug(f"  Card {idx+1}: Filtered out (not Chennai): {location}")
                        continue
                
                # Filter for fresher jobs (unless already pre-filtered)
                if not source.get("already_filtered_for_freshers", False):
                    if not self.is_fresher_job(title, experience):
                        logger.debug(f"  Card {idx+1}: Filtered out (not fresher): {title}")
                        continue
                
                job_data = {
                    "company": company,
                    "title": title,
                    "link": link,
                    "location": location or "Chennai",
                    "experience": experience,
                    "source": source_name,
                }
                results.append(job_data)
                logger.debug(f"  OK Job {len(results)}: {title} at {company}")
                
            except Exception as e:
                logger.debug(f"  Error parsing job card {idx+1}: {e}")
                continue
        
        logger.info(f"  -> Extracted {len(results)} valid Chennai fresher jobs from {source_name}")
        return results
    
    def run_scraping_cycle(self) -> Dict[str, int]:
        """Run one complete scraping cycle"""
        logger.info("="*60)
        logger.info("Starting scraping cycle")
        logger.info("="*60)
        
        today = date.today().isoformat()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        enabled_sources = [s for s in self.config["sources"] if s.get("enabled", False)]
        if not enabled_sources:
            logger.warning("No sources enabled in config.json")
            return {"new": 0, "total": len(self.db)}
        
        new_jobs = []
        retry_attempts = self.config.get("scraper_settings", {}).get("retry_attempts", 3)
        request_delay = self.config.get("scraper_settings", {}).get("request_timeout", 2)
        
        for source in enabled_sources:
            # Retry logic
            jobs = []
            for attempt in range(retry_attempts):
                try:
                    jobs = self.scrape_source(source)
                    break
                except Exception as e:
                    logger.error(f"Attempt {attempt+1} failed for {source['name']}: {e}")
                    if attempt < retry_attempts - 1:
                        time.sleep(request_delay * (attempt + 1))
            
            # Process jobs
            for job in jobs:
                job_id = self.make_job_id(job["company"], job["title"], job["link"])
                if job_id not in self.db:
                    job["first_seen"] = today
                    job["first_seen_time"] = timestamp
                    self.db[job_id] = job
                    new_jobs.append(job)
                    logger.info(f"  NEW JOB: {job['title']} at {job['company']}")
                else:
                    # Update last_seen
                    self.db[job_id]["last_seen"] = today
            
            # Be polite - delay between sources
            time.sleep(request_delay)
        
        # Save database
        self.save_db()
        
        # Generate dashboard data
        self.generate_dashboard_data(new_jobs, today, timestamp)
        
        stats = {
            "new": len(new_jobs),
            "total": len(self.db),
            "sources_scraped": len(enabled_sources)
        }
        
        logger.info("="*60)
        logger.info(f"Scraping cycle complete!")
        logger.info(f"  New jobs found: {stats['new']}")
        logger.info(f"  Total jobs tracked: {stats['total']}")
        logger.info(f"  Sources scraped: {stats['sources_scraped']}")
        logger.info("="*60)
        
        return stats
    
    def generate_dashboard_data(self, new_jobs: List[dict], today: str, timestamp: str):
        """Generate dashboard data file"""
        all_jobs = list(self.db.values())
        all_jobs.sort(key=lambda j: j.get("first_seen_time", j.get("first_seen", "")), reverse=True)
        
        payload = {
            "generated_at": today,
            "generated_timestamp": timestamp,
            "all_jobs": all_jobs,
            "today_count": len([j for j in all_jobs if j.get("first_seen") == today]),
            "new_this_cycle": len(new_jobs),
            "total_jobs": len(all_jobs),
        }
        
        with open(DASHBOARD_DATA_PATH, "w", encoding="utf-8") as f:
            f.write("const JOBS_DATA = ")
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write(";\n")
    
    def cleanup(self):
        """Cleanup resources"""
        self.close_driver()
        self.session.close()


def run_once():
    """Run scraper once"""
    scraper = JobScraper()
    try:
        stats = scraper.run_scraping_cycle()
        print(f"\n✓ Scraping complete!")
        print(f"  • New jobs: {stats['new']}")
        print(f"  • Total jobs: {stats['total']}")
        print(f"  • Open dashboard.html to view results")
    finally:
        scraper.cleanup()


def run_realtime(interval_minutes: int = 30):
    """Run scraper continuously at intervals"""
    scraper = JobScraper()
    
    print(f"🔄 Real-time mode activated!")
    print(f"  • Scraping every {interval_minutes} minutes")
    print(f"  • Press Ctrl+C to stop")
    print(f"  • Logs: {LOG_PATH}")
    print()
    
    def job():
        try:
            scraper.run_scraping_cycle()
        except Exception as e:
            logger.error(f"Error in scheduled job: {e}")
    
    # Run immediately on start
    job()
    
    # Schedule periodic runs
    schedule.every(interval_minutes).minutes.do(job)
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    except KeyboardInterrupt:
        print("\n\n⏹ Stopping real-time scraper...")
    finally:
        scraper.cleanup()
        print("✓ Cleanup complete. Goodbye!")


def main():
    parser = argparse.ArgumentParser(
        description="Enhanced Job Scraper for Chennai Fresher Jobs"
    )
    parser.add_argument(
        "--realtime",
        action="store_true",
        help="Run continuously with scheduled updates"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Interval in minutes for real-time mode (default: 30)"
    )
    
    args = parser.parse_args()
    
    if args.realtime:
        run_realtime(args.interval)
    else:
        run_once()


if __name__ == "__main__":
    main()

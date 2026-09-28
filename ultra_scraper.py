#!/usr/bin/env python3
"""
ULTRA SCRAPER - Get ALL Chennai Fresher Jobs from EVERY Website
----------------------------------------------------------------
This aggressive scraper tries multiple methods to get jobs from all sources:
- Direct HTTP requests
- Selenium for dynamic sites
- Multiple selector fallbacks
- Aggressive retry logic
"""

import json
import hashlib
import time
import sys
import logging
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urljoin
from typing import List, Dict

import requests
from bs4 import BeautifulSoup

# Selenium imports
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
    print("⚠️  Selenium not installed. Some sites will be skipped.")
    print("   Install with: pip install selenium webdriver-manager\n")

# Setup
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
DB_PATH = BASE_DIR / "jobs_db.json"
DASHBOARD_DATA_PATH = BASE_DIR / "dashboard_data.js"
LOG_PATH = BASE_DIR / "ultra_scraper.log"

# Logging
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
}

# Comprehensive job source list
JOB_SOURCES = [
    {
        "name": "Freshersworld - Chennai",
        "url": "https://www.freshersworld.com/jobs/jobsearch/chennai-jobs",
        "use_selenium": False,
        "job_card_selector": "div.job-container",
        "title_selector": "span.wrap-title, span.seo_title",
        "company_selector": "h3.latest-jobs-company, div.latest-jobs-company, span.company",
        "link_attr": "job_display_url",
        "link_on": "card",
        "extract_company_from_title": True,  # Company is in the title
    },
    {
        "name": "Naukri - Chennai Freshers",
        "url": "https://www.naukri.com/fresher-jobs-in-chennai",
        "use_selenium": True,
        "job_card_selector": "article.jobTuple, div.jobTuple",
        "title_selector": "a.title, div.title",
        "company_selector": "a.subTitle, div.subTitle, span.companyInfo",
        "link_selector": "a.title",
    },
    {
        "name": "Indeed India - Chennai",
        "url": "https://in.indeed.com/jobs?q=fresher+OR+%22entry+level%22&l=Chennai%2C+Tamil+Nadu",
        "use_selenium": True,
        "job_card_selector": "div.job_seen_beacon, td.resultContent",
        "title_selector": "h2.jobTitle span, h2.jobTitle",
        "company_selector": "span.companyName, div.company_location span",
        "link_selector": "h2.jobTitle a, a.jcs-JobTitle",
    },
    {
        "name": "Monster India - Chennai",
        "url": "https://www.monsterindia.com/search/fresher-jobs-in-chennai",
        "use_selenium": True,
        "job_card_selector": "div.card-body, article.job-tile",
        "title_selector": "h2 a, a.job-tittle",
        "company_selector": "span.company-name, div.company",
        "link_selector": "h2 a",
    },
    {
        "name": "TimesJobs - Chennai Entry Level",
        "url": "https://www.timesjobs.com/candidate/job-search.html?searchType=personalizedSearch&from=submit&txtKeywords=fresher&txtLocation=chennai",
        "use_selenium": False,
        "job_card_selector": "li.job-bx, li.clearfix",
        "title_selector": "h2 a, h3 a",
        "company_selector": "h3.joblist-comp-name, span.comp-name",
        "link_selector": "h2 a",
    },
    {
        "name": "Shine - Chennai",
        "url": "https://www.shine.com/job-search/fresher-jobs-in-chennai",
        "use_selenium": True,
        "job_card_selector": "li.jCard, div.jobCard_root",
        "title_selector": "a.jobTitle, h2 a",
        "company_selector": "div.recruiterName, span.company",
        "link_selector": "a.jobTitle, h2 a",
    },
    {
        "name": "Internshala - Chennai",
        "url": "https://internshala.com/jobs/fresher-jobs-in-chennai/",
        "use_selenium": True,
        "job_card_selector": "div.individual_internship, div.internship_meta",
        "title_selector": "div.job-internship-name, h3.heading_4_5",
        "company_selector": "p.company-name, div.company_name",
        "link_selector": "div.heading_4_5 a, a.view_detail_button",
    },
    {
        "name": "LinkedIn - Chennai Entry Level",
        "url": "https://www.linkedin.com/jobs/search/?keywords=fresher%20OR%20entry%20level&location=Chennai",
        "use_selenium": True,
        "job_card_selector": "div.job-search-card, li.jobs-search-results__list-item",
        "title_selector": "h3.base-search-card__title, a.job-card-list__title",
        "company_selector": "h4.base-search-card__subtitle, div.job-card-container__company-name",
        "link_selector": "a.base-card__full-link, a.job-card-list__title",
    },
    {
        "name": "Foundit - Chennai",
        "url": "https://www.foundit.in/srp/fresher-jobs-in-chennai",
        "use_selenium": True,
        "job_card_selector": "div.jobTuple, article.job-card",
        "title_selector": "a.job-title, h2 a",
        "company_selector": "span.companyName",
        "link_selector": "a.job-title",
    },
    {
        "name": "IIMJobs - Chennai",
        "url": "https://www.iimjobs.com/j/fresher-chennai-1.html",
        "use_selenium": False,
        "job_card_selector": "div.job-details, article.job",
        "title_selector": "h2 a, div.title a",
        "company_selector": "div.company, span.company-name",
        "link_selector": "h2 a",
    },
    {
        "name": "Hirist - Chennai IT",
        "url": "https://www.hirist.tech/jobs/fresher-jobs-chennai",
        "use_selenium": False,
        "job_card_selector": "div.job-listing, div.job-card",
        "title_selector": "h2 a, div.title a",
        "company_selector": "div.company",
        "link_selector": "h2 a",
    },
    {
        "name": "Cutshort - Chennai Tech",
        "url": "https://cutshort.io/jobs/fresher-jobs-in-chennai",
        "use_selenium": True,
        "job_card_selector": "div.opportunity-card, div.job-card",
        "title_selector": "h3 a, div.title a",
        "company_selector": "div.company-name",
        "link_selector": "h3 a",
    },
    {
        "name": "Instahyre - Chennai",
        "url": "https://www.instahyre.com/search-jobs/?location=Chennai&experience=0-1",
        "use_selenium": True,
        "job_card_selector": "div.opportunity-card",
        "title_selector": "h3 a, div.job-title",
        "company_selector": "div.company-name",
        "link_selector": "h3 a",
    },
    {
        "name": "Apna - Chennai",
        "url": "https://apna.co/jobs/chennai",
        "use_selenium": True,
        "job_card_selector": "div.job-card, article.listing",
        "title_selector": "h3, div.job-title",
        "company_selector": "p.company, div.company-name",
        "link_selector": "a",
    },
]


class UltraScraper:
    def __init__(self):
        self.db = self.load_db()
        self.driver = None
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        
    def load_db(self):
        if DB_PATH.exists():
            with open(DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    
    def save_db(self):
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump(self.db, f, indent=2, ensure_ascii=False)
    
    def get_selenium_driver(self):
        if not SELENIUM_AVAILABLE:
            return None
            
        if self.driver is None:
            try:
                chrome_options = Options()
                chrome_options.add_argument("--headless=new")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-blink-features=AutomationControlled")
                chrome_options.add_argument(f"user-agent={HEADERS['User-Agent']}")
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("-> Selenium WebDriver initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Selenium: {e}")
                return None
        return self.driver
    
    def close_driver(self):
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
            except:
                pass
    
    def make_job_id(self, company: str, title: str, link: str) -> str:
        raw = f"{company}|{title}|{link}".lower().strip()
        return hashlib.md5(raw.encode("utf-8")).hexdigest()
    
    def extract_text(self, element) -> str:
        return element.get_text(strip=True) if element else ""
    
    def fetch_with_requests(self, url: str, timeout: int = 20):
        try:
            resp = self.session.get(url, timeout=timeout, verify=False)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except Exception as e:
            logger.debug(f"Request failed: {e}")
            return None
    
    def fetch_with_selenium(self, url: str, wait_selector: str = None, timeout: int = 20):
        driver = self.get_selenium_driver()
        if not driver:
            return None
        
        try:
            driver.get(url)
            if wait_selector:
                WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector))
                )
            else:
                time.sleep(5)  # Wait for dynamic content
            
            return BeautifulSoup(driver.page_source, "lxml")
        except Exception as e:
            logger.debug(f"Selenium fetch failed: {e}")
            return None
    
    def scrape_source(self, source: dict) -> List[dict]:
        name = source["name"]
        url = source["url"]
        logger.info(f"\n{'='*60}")
        logger.info(f"Scraping: {name}")
        logger.info(f"URL: {url}")
        
        # Try with requests first (faster)
        soup = self.fetch_with_requests(url)
        
        # If failed and selenium is available/needed, try selenium
        if not soup and source.get("use_selenium", False):
            logger.info(f"-> Trying with Selenium...")
            soup = self.fetch_with_selenium(url, source.get("job_card_selector"))
        
        if not soup:
            logger.warning(f"-> Failed to fetch page")
            return []
        
        # Extract job cards
        job_card_selector = source["job_card_selector"]
        selectors = [s.strip() for s in job_card_selector.split(",")]
        
        cards = []
        for selector in selectors:
            cards = soup.select(selector)
            if cards:
                logger.info(f"-> Found {len(cards)} job cards with: {selector}")
                break
        
        if not cards:
            logger.warning(f"-> No job cards found")
            return []
        
        results = []
        for idx, card in enumerate(cards[:50]):  # Limit to first 50 jobs per source
            try:
                # Extract title
                title = ""
                title_selectors = [s.strip() for s in source["title_selector"].split(",")]
                for ts in title_selectors:
                    el = card.select_one(ts)
                    if el:
                        title = self.extract_text(el)
                        if title:
                            break
                
                if not title:
                    continue
                
                # Extract company
                company = "Unknown"
                company_selectors = [s.strip() for s in source.get("company_selector", "").split(",")]
                for cs in company_selectors:
                    if cs:
                        el = card.select_one(cs)
                        if el:
                            company = self.extract_text(el)
                            if company:
                                break
                
                # Try to extract company from title if specified
                if company == "Unknown" and source.get("extract_company_from_title"):
                    # Freshersworld pattern: "Job Title ... in COMPANY NAME at Location"
                    import re
                    match = re.search(r'\sin\s+([A-Z][^at]+?)\s+at\s+', title)
                    if match:
                        company = match.group(1).strip()
                
                # Extract link
                link = ""
                link_attr = source.get("link_attr", "href")
                link_on = source.get("link_on", "link")
                
                if link_on == "card":
                    # Link attribute is on the card itself
                    link = card.get(link_attr, "")
                else:
                    # Link is on a child element
                    link_selector = source.get("link_selector", source["title_selector"])
                    link_selectors = [s.strip() for s in link_selector.split(",")]
                    for ls in link_selectors:
                        el = card.select_one(ls)
                        if el and el.has_attr(link_attr):
                            link = el[link_attr]
                            break
                
                # Make absolute URL
                if link and not link.startswith("http"):
                    link = urljoin(url, link)
                
                if not link:
                    link = url  # Fallback to source URL
                
                job_data = {
                    "company": company,
                    "title": title,
                    "link": link,
                    "location": "Chennai",
                    "experience": "Fresher",
                    "source": name,
                }
                results.append(job_data)
                
            except Exception as e:
                logger.debug(f"Error parsing card {idx}: {e}")
                continue
        
        logger.info(f"-> Extracted {len(results)} jobs from {name}")
        return results
    
    def run(self):
        logger.info("\n" + "="*70)
        logger.info("ULTRA SCRAPER - Getting ALL Chennai Fresher Jobs")
        logger.info("="*70 + "\n")
        
        today = date.today().isoformat()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        all_new_jobs = []
        source_count = 0
        
        for source in JOB_SOURCES:
            # Skip if selenium needed but not available
            if source.get("use_selenium") and not SELENIUM_AVAILABLE:
                logger.warning(f"\nSkipping {source['name']} - requires Selenium")
                continue
            
            source_count += 1
            
            # Try up to 2 times
            jobs = []
            for attempt in range(2):
                try:
                    jobs = self.scrape_source(source)
                    if jobs:
                        break
                    if attempt == 0:
                        logger.info(f"-> Retrying...")
                        time.sleep(2)
                except Exception as e:
                    logger.error(f"Error on attempt {attempt+1}: {e}")
            
            # Add to database
            for job in jobs:
                job_id = self.make_job_id(job["company"], job["title"], job["link"])
                if job_id not in self.db:
                    job["first_seen"] = today
                    job["first_seen_time"] = timestamp
                    self.db[job_id] = job
                    all_new_jobs.append(job)
                    logger.info(f"   NEW: {job['title'][:50]} at {job['company'][:30]}")
            
            # Be polite
            time.sleep(2)
        
        # Save database
        self.save_db()
        
        # Generate dashboard
        all_jobs = list(self.db.values())
        all_jobs.sort(key=lambda j: j.get("first_seen_time", j.get("first_seen", "")), reverse=True)
        
        payload = {
            "generated_at": today,
            "generated_timestamp": timestamp,
            "all_jobs": all_jobs,
            "today_count": len([j for j in all_jobs if j.get("first_seen") == today]),
            "new_this_cycle": len(all_new_jobs),
            "total_jobs": len(all_jobs),
        }
        
        with open(DASHBOARD_DATA_PATH, "w", encoding="utf-8") as f:
            f.write("const JOBS_DATA = ")
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write(";\n")
        
        # Summary
        logger.info("\n" + "="*70)
        logger.info("SCRAPING COMPLETE!")
        logger.info("="*70)
        logger.info(f"Sources attempted: {source_count}")
        logger.info(f"New jobs found: {len(all_new_jobs)}")
        logger.info(f"Total jobs in database: {len(all_jobs)}")
        logger.info(f"\nOpen dashboard.html to view all {len(all_jobs)} Chennai fresher jobs!")
        logger.info("="*70 + "\n")
        
        return {
            "new": len(all_new_jobs),
            "total": len(all_jobs),
            "sources": source_count
        }


def main():
    import warnings
    warnings.filterwarnings("ignore")
    
    scraper = UltraScraper()
    try:
        scraper.run()
    finally:
        scraper.close_driver()
    
    print("\n" + "="*70)
    print("SUCCESS! Check dashboard.html to see all Chennai fresher jobs")
    print("="*70)


if __name__ == "__main__":
    main()

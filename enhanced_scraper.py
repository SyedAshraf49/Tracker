#!/usr/bin/env python3
"""Chennai early-career job tracker.

Configuration-driven and polite: it tries normal HTML first, falls back to
JSON-LD JobPosting data, checks robots.txt, retries transient failures, and
keeps source health in dashboard_data.js instead of silently hiding failures.
"""
from __future__ import annotations
import argparse, hashlib, json, logging, re, sys, time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib import robotparser
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
try:
    import schedule
except ImportError:
    schedule = None

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH, DB_PATH = BASE_DIR / 'config.json', BASE_DIR / 'jobs_db.json'
DASHBOARD_DATA_PATH, LOG_PATH = BASE_DIR / 'dashboard_data.js', BASE_DIR / 'scraper.log'
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler(LOG_PATH, encoding='utf-8'), logging.StreamHandler(sys.stdout)])
logger = logging.getLogger('job-tracker')
HEADERS = {'User-Agent': 'ChennaiEarlyCareerTracker/2.0 (+personal research)', 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'Accept-Language': 'en-IN,en;q=0.8'}
SOFTWARE_TERMS = {'software','developer','development','engineering','engineer','programmer','frontend','front end','backend','back end','full stack','full-stack','web developer','mobile developer','android','ios','qa','quality assurance','automation tester','test engineer','devops','cloud engineer','data engineer','data analyst','machine learning','ai engineer','python','java developer','react','node.js','application support'}
EXCLUDE_TERMS = {'senior','lead','manager','director','principal','architect','7+ years','8+ years','10+ years','12+ years','15+ years'}
EARLY_TERMS = {'fresher','freshers','entry level','entry-level','graduate trainee','campus hire','trainee','associate engineer','0-1 year','0-1 years','0-2 years','junior','new grad','graduate engineer','recent graduate','walk-in','walkin','no experience','intern','internship','apprentice','early career'}

def load_json(path: Path, fallback: Any) -> Any:
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError): return fallback

def clean(value: Any) -> str: return re.sub(r'\s+', ' ', str(value or '')).strip()
def terms_found(text: str, terms: set[str]) -> list[str]:
    lower = clean(text).lower(); return sorted({term for term in terms if term in lower})

def classify_job(title: str, description: str = '') -> tuple[str, int, list[str]]:
    text = f'{title} {description}'; low = text.lower()
    software_hits, early_hits, exclude_hits = terms_found(text, SOFTWARE_TERMS), terms_found(text, EARLY_TERMS), terms_found(text, EXCLUDE_TERMS)
    score = min(100, len(software_hits) * 18 + len(early_hits) * 12)
    if exclude_hits: score = max(0, score - 35)
    if any(term in low for term in ('software developer','software engineer','full stack','frontend developer','backend developer')): score = min(100, score + 22)
    if score >= 45: category = 'Software development'
    elif any(term in low for term in ('data','analyst','machine learning','ai')): category = 'Data & AI'
    elif any(term in low for term in ('qa','test','quality')): category = 'QA & testing'
    elif any(term in low for term in ('support','technical support','application support')): category = 'IT support'
    else: category = 'Other early career'
    return category, score, sorted(set(software_hits + early_hits))

def job_id(job: dict) -> str:
    link = clean(job.get('link')); identity = link if link.startswith('http') else f"{clean(job.get('company')).lower()}|{clean(job.get('title')).lower()}"
    return hashlib.sha256(identity.encode()).hexdigest()[:24]

def robots_allows(url: str) -> bool:
    try:
        parsed = urlparse(url); rp = robotparser.RobotFileParser(f'{parsed.scheme}://{parsed.netloc}/robots.txt'); rp.read()
        return rp.can_fetch(HEADERS['User-Agent'], url)
    except Exception as exc:
        logger.warning('Could not check robots.txt for %s: %s', url, exc); return True

def first_text(card: Any, selectors: str) -> str:
    for selector in (s.strip() for s in (selectors or '').split(',')):
        if selector:
            element = card.select_one(selector)
            value = clean(element.get_text(' ', strip=True)) if element else ''
            if value: return value
    return ''

def first_link(card: Any, source: dict, page_url: str) -> str:
    attr = source.get('link_attr', 'href')
    if source.get('link_on') == 'card': raw = card.get(attr, '')
    else:
        raw = ''
        for selector in (s.strip() for s in source.get('link_selector', source.get('title_selector', '')).split(',')):
            element = card.select_one(selector)
            if element and element.get(attr): raw = element.get(attr); break
    return urljoin(source.get('link_base') or page_url, clean(raw)) if raw else page_url

def jsonld_jobs(soup: BeautifulSoup, source: dict) -> list[dict]:
    found = []
    for script in soup.select('script[type="application/ld+json"]'):
        try: payload = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError): continue
        records = payload if isinstance(payload, list) else (payload.get('@graph', [payload]) if isinstance(payload, dict) else [])
        for record in records:
            if not isinstance(record, dict) or record.get('@type') not in ('JobPosting', ['JobPosting']): continue
            location = record.get('jobLocation', {}); location = location[0] if isinstance(location, list) and location else location
            address = location.get('address', {}) if isinstance(location, dict) else {}
            loc = clean(' '.join(str(address.get(k, '')) for k in ('addressLocality','addressRegion','addressCountry'))) if isinstance(address, dict) else clean(location)
            found.append({'company': clean((record.get('hiringOrganization') or {}).get('name', 'Unknown')), 'title': clean(record.get('title')), 'link': clean(record.get('url')) or source['url'], 'location': loc, 'experience': clean(record.get('experienceRequirements')), 'description': BeautifulSoup(clean(record.get('description')), 'lxml').get_text(' ', strip=True)[:600], 'source': source['name']})
    return found

def source_is_prefiltered(job: dict, config: dict) -> bool:
    return any(s.get('name') == job.get('source') and s.get('already_filtered_for_freshers') for s in config.get('sources', []))

class JobScraper:
    def __init__(self, config_path: Path = CONFIG_PATH):
        self.config = load_json(config_path, {}); self.db = load_json(DB_PATH, {}); self.source_health = []
        self.session = requests.Session(); self.session.headers.update(HEADERS)
        self.last_fetch_retryable = True
    def fetch(self, url: str):
        timeout = int(self.config.get('scraper_settings', {}).get('request_timeout', 20))
        self.last_fetch_retryable = True
        try:
            response = self.session.get(url, timeout=timeout); response.raise_for_status(); return BeautifulSoup(response.text, 'lxml'), 'ok'
        except requests.RequestException as exc:
            status = getattr(getattr(exc, 'response', None), 'status_code', None)
            # 401/403/404/410 are terminal for this URL. Retrying them only
            # slows Render builds and creates noisy logs; 429 and 5xx remain retryable.
            if status in {401, 403, 404, 410}:
                self.last_fetch_retryable = False
            return None, clean(exc)
    def scrape_source(self, source: dict) -> list[dict]:
        url = source['url']
        if not robots_allows(url): self.source_health.append({'name': source['name'], 'status': 'blocked by robots.txt', 'jobs': 0}); return []
        soup, error = self.fetch(url)
        if not soup:
            self.source_health.append({'name': source['name'], 'status': 'request failed', 'jobs': 0, 'detail': error[:120]}); logger.warning('%s: %s', source['name'], error); return []
        cards, working_selector = [], ''
        for selector in (s.strip() for s in source.get('job_card_selector','').split(',') if s.strip()):
            cards = soup.select(selector)
            if cards: working_selector = selector; break
        results = []
        for card in cards[:int(source.get('max_jobs', 100))]:
            title = first_text(card, source.get('title_selector',''))
            if not title: continue
            company = first_text(card, source.get('company_selector','')) or 'Unknown'
            if company == 'Unknown' and source.get('extract_company_from_title'):
                match = re.search(r'\bin\s+(.+?)\s+at\s+', title, re.I)
                if match: company = clean(match.group(1))
            location, experience = first_text(card, source.get('location_selector','')), first_text(card, source.get('experience_selector',''))
            description = first_text(card, source.get('description_selector',''))
            if source.get('already_filtered_for_freshers'): experience = experience or 'Fresher / entry level'
            results.append({'company': company, 'title': title, 'link': first_link(card, source, url), 'location': location or 'Chennai', 'experience': experience or 'Early career', 'description': description, 'source': source['name']})
        if not results: results = jsonld_jobs(soup, source)
        status = 'working' if results or cards else 'reachable, no cards matched'
        self.source_health.append({'name': source['name'], 'status': status, 'jobs': len(results), 'selector': working_selector}); logger.info('%s: %d jobs (%s)', source['name'], len(results), status)
        return results
    def qualifies(self, job: dict) -> bool:
        settings = self.config.get('scraper_settings', {}); text = f"{job.get('title','')} {job.get('experience','')} {job.get('description','')}".lower(); location = clean(job.get('location','Chennai')).lower(); target = clean(settings.get('location_filter','Chennai')).lower()
        if target and target not in location and target not in text: return False
        category, score, matched = classify_job(job.get('title',''), job.get('description','')); years = re.findall(r'(\d+)\s*\+?\s*year', text)
        if years and min(map(int, years)) > int(settings.get('max_experience_years', 1)): return False
        if not source_is_prefiltered(job, self.config) and not (terms_found(text, EARLY_TERMS) or score >= 35): return False
        job.update({'category': category, 'software_score': score, 'matched_terms': matched, 'is_software_role': score >= 45}); return True
    def run_cycle(self) -> dict:
        today, timestamp = date.today().isoformat(), datetime.now().strftime('%Y-%m-%d %H:%M:%S'); settings = self.config.get('scraper_settings', {}); enabled = [s for s in self.config.get('sources', []) if s.get('enabled', False)]; new_jobs = 0
        for source in enabled:
            jobs = []
            for attempt in range(int(settings.get('retry_attempts', 2))):
                jobs = self.scrape_source(source)
                if jobs or not self.last_fetch_retryable or attempt == int(settings.get('retry_attempts', 2)) - 1: break
                time.sleep(1.5 * (attempt + 1))
            for job in jobs:
                if not self.qualifies(job): continue
                key = job_id(job)
                if key in self.db: self.db[key].update({'last_seen': today, 'category': job['category'], 'software_score': job['software_score'], 'is_software_role': job['is_software_role'], 'matched_terms': job['matched_terms']})
                else: job.update({'first_seen': today, 'first_seen_time': timestamp, 'last_seen': today}); self.db[key] = job; new_jobs += 1
            time.sleep(float(settings.get('source_delay_seconds', 1.5)))
        self.write_outputs(today, timestamp, new_jobs, len(enabled)); return {'new': new_jobs, 'total': len(self.db), 'sources_scraped': len(enabled), 'source_health': self.source_health}
    def write_outputs(self, today: str, timestamp: str, new_jobs: int, source_count: int) -> None:
        target = clean(self.config.get('scraper_settings', {}).get('location_filter', 'Chennai')).lower()
        self.db = {key: job for key, job in self.db.items() if not target or target in clean(job.get('location', '')).lower()}
        jobs = list(self.db.values())
        for job in jobs:
            if 'software_score' not in job:
                category, score, matched = classify_job(job.get('title',''), job.get('description','')); job.update({'category': category, 'software_score': score, 'matched_terms': matched, 'is_software_role': score >= 45})
        jobs.sort(key=lambda item: (item.get('software_score', 0), item.get('first_seen_time', '')), reverse=True); category_counts, source_counts = {}, {}
        for job in jobs:
            category_counts[job.get('category','Other early career')] = category_counts.get(job.get('category','Other early career'), 0) + 1; source_counts[job.get('source','Unknown')] = source_counts.get(job.get('source','Unknown'), 0) + 1
        DB_PATH.write_text(json.dumps(self.db, indent=2, ensure_ascii=False), encoding='utf-8')
        latest_health = {}
        for health in self.source_health:
            latest_health[health['name']] = health
        payload = {'generated_at': today, 'generated_timestamp': timestamp, 'all_jobs': jobs, 'today_count': sum(j.get('first_seen') == today for j in jobs), 'new_this_cycle': new_jobs, 'total_jobs': len(jobs), 'software_jobs': sum(bool(j.get('is_software_role')) for j in jobs), 'category_counts': category_counts, 'source_counts': source_counts, 'source_health': list(latest_health.values()), 'sources_configured': source_count}
        DASHBOARD_DATA_PATH.write_text('const JOBS_DATA = ' + json.dumps(payload, indent=2, ensure_ascii=False) + ';\n', encoding='utf-8')
    def close(self): self.session.close()

def run_once():
    scraper = JobScraper()
    try:
        stats = scraper.run_cycle(); print(f"\nDone. {stats['new']} new qualifying jobs; {stats['total']} total tracked.")
    finally: scraper.close()

def main():
    parser = argparse.ArgumentParser(description='Track Chennai fresher and early-career jobs'); parser.add_argument('--realtime', action='store_true'); parser.add_argument('--interval', type=int, default=30); args = parser.parse_args()
    if not args.realtime: run_once(); return
    if schedule is None: raise SystemExit('Install schedule with: pip install -r requirements.txt')
    scraper = JobScraper()
    try:
        def cycle():
            try: scraper.run_cycle()
            except Exception: logger.exception('Scraping cycle failed')
        cycle(); schedule.every(max(5, args.interval)).minutes.do(cycle); logger.info('Realtime mode active; interval=%d minutes', max(5,args.interval))
        while True: schedule.run_pending(); time.sleep(30)
    except KeyboardInterrupt: logger.info('Realtime mode stopped')
    finally: scraper.close()
if __name__ == '__main__': main()

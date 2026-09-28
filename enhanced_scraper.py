#!/usr/bin/env python3
"""Verified Chennai early-career job collector.

Pipeline: source listing -> normalized URL -> job-detail page -> structured
metadata -> verification decision. Only verified records reach all_jobs in the
published dashboard payload; records that need a human check stay visible in a
separate review queue.
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
SCHEMA_VERSION = 3
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler(LOG_PATH, encoding='utf-8'), logging.StreamHandler(sys.stdout)])
logger = logging.getLogger('verified-job-tracker')
HEADERS = {'User-Agent': 'ChennaiEarlyCareerTracker/3.0 (+personal research)', 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'Accept-Language': 'en-IN,en;q=0.8'}
GENERIC_COMPANY_TERMS = ('unknown', 'company not listed', 'leading mnc', 'client of', 'a client', 'freshersworld', 'freshers world', 'teamlease', 'confidential', 'undisclosed', 'not specified', 'placement service', 'placement agency', 'consultancy', 'recruitment', 'manpower', 'staffing', 'hr solutions')
SOFTWARE_TERMS = {'software','developer','development','engineering','engineer','programmer','frontend','front end','backend','back end','full stack','full-stack','web developer','mobile developer','android','ios','qa','quality assurance','automation tester','test engineer','devops','cloud engineer','data engineer','data analyst','machine learning','ai engineer','python','java developer','react','node.js','application support'}
EARLY_TERMS = {'fresher','freshers','entry level','entry-level','graduate trainee','campus hire','trainee','associate engineer','0-1 year','0-1 years','0-2 years','junior','new grad','graduate engineer','recent graduate','walk-in','walkin','no experience','intern','internship','apprentice','early career'}
EXCLUDE_TERMS = {'senior','lead','manager','director','principal','architect','7+ years','8+ years','10+ years','12+ years','15+ years'}


def load_json(path: Path, fallback: Any) -> Any:
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError): return fallback

def clean(value: Any) -> str: return re.sub(r'\s+', ' ', str(value or '')).strip()
def terms_found(text: str, terms: set[str]) -> list[str]:
    low = clean(text).lower(); return sorted({term for term in terms if term in low})

def normalize_title(title: str) -> str:
    value = clean(title)
    value = re.sub(r'\s+(?:jobs?\s+)?opening\s+in\s+.+?\s+at\s+.+$', '', value, flags=re.I)
    value = re.sub(r'\s+(?:jobs?\s+opening|job\s+vacanc(?:y|ies)).*$', '', value, flags=re.I)
    value = re.sub(r'(?:\s*[-|]\s*)?(?:chennai|chennai-others|tamil nadu)\s*(?:less)?$', '', value, flags=re.I)
    return clean(value).strip(' -|') or clean(title)

def normalize_company(value: str) -> str | None:
    company = clean(value).strip(' -|:')
    if not company or any(term in company.lower() for term in GENERIC_COMPANY_TERMS): return None
    company = re.sub(r'\s+(?:pvt|private)\.?\s*(?:ltd|limited)\.?$', lambda m: ' ' + m.group(0).strip(), company, flags=re.I)
    return company[:180]

def extract_recruiter(text: str) -> str | None:
    match = re.search(r"(?i)(?:recruiter|posted\s+by|agency|consultant)\s*[:\-]\s*([A-Za-z0-9 &.,()'\-]{2,100})", clean(text))
    return clean(match.group(1)).strip(' .,-') if match else None

def classify_job(title: str, description: str = '') -> tuple[str, int, list[str]]:
    text = f'{title} {description}'; low = text.lower(); software, early, excluded = terms_found(text, SOFTWARE_TERMS), terms_found(text, EARLY_TERMS), terms_found(text, EXCLUDE_TERMS)
    score = min(100, len(software) * 18 + len(early) * 12)
    if excluded: score = max(0, score - 35)
    if any(x in low for x in ('software developer','software engineer','full stack','frontend developer','backend developer')): score = min(100, score + 22)
    if score >= 45: category = 'Software development'
    elif any(x in low for x in ('data','analyst','machine learning','ai')): category = 'Data & AI'
    elif any(x in low for x in ('qa','test','quality')): category = 'QA & testing'
    elif any(x in low for x in ('support','technical support','application support')): category = 'IT support'
    else: category = 'Other early career'
    return category, score, sorted(set(software + early))

def job_id(job: dict) -> str:
    identity = clean(job.get('link')) or f"{clean(job.get('company')).lower()}|{clean(job.get('title')).lower()}"
    return hashlib.sha256(identity.encode()).hexdigest()[:24]

def first_text(card: Any, selectors: str) -> str:
    for selector in (s.strip() for s in (selectors or '').split(',')):
        if selector:
            el = card.select_one(selector); value = clean(el.get_text(' ', strip=True)) if el else ''
            if value: return value
    return ''

def first_link(card: Any, source: dict, page_url: str) -> str:
    attr = source.get('link_attr', 'href')
    if source.get('link_on') == 'card': raw = card.get(attr, '')
    else:
        raw = ''
        for selector in (s.strip() for s in source.get('link_selector', source.get('title_selector', '')).split(',')):
            el = card.select_one(selector)
            if el and el.get(attr): raw = el.get(attr); break
    return urljoin(source.get('link_base') or page_url, clean(raw)) if raw else ''

def jsonld_records(soup: BeautifulSoup) -> list[dict]:
    records = []
    for script in soup.select('script[type="application/ld+json"]'):
        try: payload = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError): continue
        items = payload if isinstance(payload, list) else payload.get('@graph', [payload]) if isinstance(payload, dict) else []
        records.extend(item for item in items if isinstance(item, dict))
    return records

def jobposting_record(soup: BeautifulSoup) -> dict | None:
    for record in jsonld_records(soup):
        types = record.get('@type', [])
        if record.get('@type') == 'JobPosting' or 'JobPosting' in (types if isinstance(types, list) else [types]): return record
    return None

def jsonld_org_name(record: dict | None) -> str:
    org = (record or {}).get('hiringOrganization', {})
    return clean(org.get('name') if isinstance(org, dict) else org)

def jsonld_company(record: dict | None) -> str | None:
    return normalize_company(jsonld_org_name(record))

def parse_listing_soup(soup: BeautifulSoup, source: dict, page_url: str) -> list[dict]:
    adapter = source.get('adapter', 'generic'); selectors = source.get('job_card_selector', '')
    cards, working = [], ''
    for selector in (s.strip() for s in selectors.split(',') if s.strip()):
        cards = soup.select(selector)
        if cards: working = selector; break
    results = []
    for card in cards[:int(source.get('max_jobs', 100))]:
        raw_title = first_text(card, source.get('title_selector', ''))
        if not raw_title: continue
        title = normalize_title(raw_title)
        company = normalize_company(first_text(card, source.get('company_selector', '')))
        if not company and adapter == 'freshersworld':
            match = re.search(r'\bin\s+(.+?)\s+at\s+', raw_title, re.I)
            company = normalize_company(match.group(1)) if match else None
        location = first_text(card, source.get('location_selector', '')) or 'Chennai'
        link = first_link(card, source, page_url)
        recruiter = extract_recruiter(card.get_text(' ', strip=True))
        results.append({'title': title, 'raw_title': raw_title, 'company': company, 'recruiter': recruiter, 'link': link, 'location': location, 'source': source['name'], 'adapter': adapter})
    return results

def parse_detail_soup(soup: BeautifulSoup, listing: dict, source: dict) -> dict:
    record = jobposting_record(soup); org_name = jsonld_org_name(record); company = jsonld_company(record)
    if not company:
        for selector in ('[itemprop="hiringOrganization"] [itemprop="name"]','[itemprop="hiringOrganization"]','meta[property="og:site_name"]','meta[name="author"]'):
            el = soup.select_one(selector)
            value = el.get('content','') if el and el.name == 'meta' else el.get_text(' ', strip=True) if el else ''
            company = normalize_company(value)
            if company: break
    title = clean(record.get('title')) if record else ''
    title = normalize_title(title or first_text(soup, 'h1, [itemprop="title"], meta[property="og:title"]')) or listing['title']
    if record and isinstance(record.get('description'), str): description = BeautifulSoup(record['description'], 'lxml').get_text(' ', strip=True)
    else: description = first_text(soup, '[itemprop="description"], .job-description, .job-details, main, article')
    description = clean(description)[:1200]
    location = listing.get('location','Chennai')
    if record:
        loc = record.get('jobLocation', {})
        if isinstance(loc, list): loc = loc[0] if loc else {}
        address = loc.get('address', {}) if isinstance(loc, dict) else {}
        if isinstance(address, dict): location = clean(' '.join(str(address.get(k,'')) for k in ('addressLocality','addressRegion')))
    raw_text = soup.get_text(' ', strip=True)
    recruiter = listing.get('recruiter') or (org_name if org_name and not company else None) or extract_recruiter(raw_text)
    date_posted = clean(record.get('datePosted')) if record else ''
    if not date_posted:
        for prop in ('datePosted','datePublished'):
            el = soup.select_one(f'[itemprop="{prop}"], meta[property="article:{prop}"]')
            if el: date_posted = clean(el.get('content','') or el.get_text(' ', strip=True)); break
    return {**listing, 'company': company, 'title': title, 'location': location or listing.get('location','Chennai'), 'recruiter': recruiter, 'description': description, 'initial_jd': description or 'Initial job description was not captured; open the original listing for details.', 'date_posted': date_posted or 'Not provided', 'company_verified': bool(company), 'verification_method': 'detail_jsonld' if jsonld_company(record) else 'detail_metadata' if company else None}

def robots_allows(url: str, cache: dict) -> bool:
    host = urlparse(url).netloc
    if host in cache: return cache[host]
    try:
        parsed = urlparse(url); rp = robotparser.RobotFileParser(f'{parsed.scheme}://{parsed.netloc}/robots.txt'); rp.read(); cache[host] = rp.can_fetch(HEADERS['User-Agent'], url)
    except Exception as exc:
        logger.warning('robots check failed for %s: %s', host, exc); cache[host] = True
    return cache[host]

class JobScraper:
    def __init__(self, config_path: Path = CONFIG_PATH):
        self.config = load_json(config_path, {}); existing = load_json(DB_PATH, {})
        # Old records have no verification schema and are intentionally purged.
        self.db = {key: value for key, value in existing.items() if value.get('schema_version') == SCHEMA_VERSION and value.get('verification_status') in ('verified','needs_verification')}
        self.source_health, self.robots_cache = [], {}; self.session = requests.Session(); self.session.headers.update(HEADERS)
    def fetch(self, url: str):
        try:
            response = self.session.get(url, timeout=int(self.config.get('scraper_settings',{}).get('request_timeout',20))); response.raise_for_status(); return BeautifulSoup(response.text, 'lxml'), None
        except requests.RequestException as exc: return None, clean(exc)
    def verify_listing(self, listing: dict, source: dict) -> dict:
        if not listing.get('link') or listing['link'] == source['url']: return {**listing, 'verification_status':'needs_verification', 'verification_reason':'No job-detail URL'}
        if not robots_allows(listing['link'], self.robots_cache): return {**listing, 'verification_status':'needs_verification', 'verification_reason':'Detail page blocked by robots.txt'}
        soup, error = self.fetch(listing['link'])
        if not soup: return {**listing, 'verification_status':'needs_verification', 'verification_reason':f'Detail page unavailable: {error[:120]}'}
        job = parse_detail_soup(soup, listing, source)
        target = clean(self.config.get('scraper_settings',{}).get('location_filter','Chennai')).lower()
        if not job.get('company_verified'): job.update({'verification_status':'needs_verification','verification_reason':'Hiring company could not be verified'}); return job
        if target and target not in clean(job.get('location','')).lower(): job.update({'verification_status':'needs_verification','verification_reason':'Detail page location is not Chennai'}); return job
        text = f"{job.get('title','')} {job.get('description','')} {job.get('experience','')}".lower(); category, score, matched = classify_job(job.get('title',''), job.get('description',''))
        if not source.get('already_filtered_for_freshers') and not terms_found(text, EARLY_TERMS): job.update({'verification_status':'needs_verification','verification_reason':'Early-career signal not confirmed'}); return job
        job.update({'category':category,'software_score':score,'matched_terms':matched,'is_software_role':score >= 45,'verification_status':'verified','verification_reason':'Detail page and hiring company verified','schema_version':SCHEMA_VERSION}); return job
    def run_cycle(self) -> dict:
        today, timestamp = date.today().isoformat(), datetime.now().strftime('%Y-%m-%d %H:%M:%S'); settings = self.config.get('scraper_settings',{}); enabled = [s for s in self.config.get('sources',[]) if s.get('enabled')]; new, verified_count, review_count = 0, 0, 0
        for source in enabled:
            if not robots_allows(source['url'], self.robots_cache): self.source_health.append({'name':source['name'],'status':'blocked by robots.txt','listed':0,'verified':0}); continue
            soup, error = self.fetch(source['url'])
            if not soup: logger.warning('%s: %s', source['name'], error); self.source_health.append({'name':source['name'],'status':'request failed','listed':0,'verified':0}); continue
            listings = parse_listing_soup(soup, source, source['url']); verified_here = 0
            for listing in listings:
                result = self.verify_listing(listing, source)
                result.update({'first_seen': today, 'first_seen_time': timestamp, 'last_seen': today})
                key = job_id(result)
                if key in self.db: result['first_seen'] = self.db[key].get('first_seen', today); result['first_seen_time'] = self.db[key].get('first_seen_time', timestamp)
                else: new += 1
                self.db[key] = result
                if result.get('verification_status') == 'verified': verified_count += 1; verified_here += 1
                else: review_count += 1
                time.sleep(float(settings.get('detail_delay_seconds',0.35)))
            self.source_health.append({'name':source['name'],'status':'working','listed':len(listings),'verified':verified_here,'review':len(listings)-verified_here}); logger.info('%s: %d listings, %d verified', source['name'], len(listings), verified_here)
            time.sleep(float(settings.get('source_delay_seconds',1.5)))
        self.write_outputs(today,timestamp,new,len(enabled)); return {'new':new,'total':len(self.db),'verified':verified_count,'review':review_count}
    def write_outputs(self, today: str, timestamp: str, new_jobs: int, source_count: int):
        jobs = list(self.db.values())
        for job in jobs:
            if not job.get('schema_version'): job['schema_version'] = SCHEMA_VERSION
            if not job.get('verification_status'): job['verification_status'] = 'needs_verification'
            if not job.get('initial_jd'): job['initial_jd'] = clean(job.get('description')) or 'Initial job description was not captured; open the original listing for details.'
            if not job.get('date_posted'): job['date_posted'] = 'Not provided'
        self.db = {job_id(job): job for job in jobs}; jobs = list(self.db.values()); verified = [j for j in jobs if j.get('verification_status') == 'verified']; review = [j for j in jobs if j.get('verification_status') != 'verified']
        verified.sort(key=lambda j: (j.get('first_seen_time','')), reverse=True); review.sort(key=lambda j: j.get('first_seen_time',''), reverse=True)
        DB_PATH.write_text(json.dumps(self.db, indent=2, ensure_ascii=False), encoding='utf-8')
        payload = {'schema_version':SCHEMA_VERSION,'generated_at':today,'generated_timestamp':timestamp,'all_jobs':verified,'needs_verification':review,'today_count':sum(j.get('first_seen')==today for j in verified),'review_count':len(review),'new_this_cycle':new_jobs,'total_jobs':len(verified),'software_jobs':sum(bool(j.get('is_software_role')) for j in verified),'source_health':self.source_health,'sources_configured':source_count}
        DASHBOARD_DATA_PATH.write_text('const JOBS_DATA = '+json.dumps(payload,indent=2,ensure_ascii=False)+';\n', encoding='utf-8')
    def close(self): self.session.close()

def run_once():
    scraper = JobScraper()
    try: print(scraper.run_cycle())
    finally: scraper.close()

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--realtime',action='store_true'); parser.add_argument('--interval',type=int,default=30); args=parser.parse_args()
    if not args.realtime: run_once(); return
    if schedule is None: raise SystemExit('Install schedule with: pip install -r requirements.txt')
    scraper=JobScraper()
    try:
        schedule.every(max(5,args.interval)).minutes.do(scraper.run_cycle); scraper.run_cycle()
        while True: schedule.run_pending(); time.sleep(30)
    except KeyboardInterrupt: pass
    finally: scraper.close()
if __name__ == '__main__': main()

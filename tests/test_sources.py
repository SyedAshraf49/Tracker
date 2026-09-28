import json
import unittest
from pathlib import Path
from bs4 import BeautifulSoup
from enhanced_scraper import normalize_company, normalize_title, parse_detail_soup, parse_listing_soup

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures'

class SourceFixtureTests(unittest.TestCase):
    def read(self, name): return BeautifulSoup((FIXTURES / name).read_text(), 'lxml')
    def test_freshersworld_listing_adapter(self):
        source={'name':'Freshersworld','adapter':'freshersworld','job_card_selector':'div.job-container','title_selector':'span.wrap-title','company_selector':'h3.latest-jobs-company','location_selector':'a.bold_font','link_on':'card','link_attr':'job_display_url'}
        jobs=parse_listing_soup(self.read('freshersworld_listing.html'),source,'https://example.test/list')
        self.assertEqual(jobs[0]['company'],'Acme Tech Private Limited'); self.assertEqual(jobs[0]['title'],'Software Engineer'); self.assertIn('/jobs/software-engineer',jobs[0]['link'])
    def test_freshersworld_detail_jsonld(self):
        listing={'title':'Software Engineer','company':None,'link':'https://example.test/job','location':'Chennai','source':'Freshersworld'}
        job=parse_detail_soup(self.read('freshersworld_detail.html'),listing,{})
        self.assertEqual(job['company'],'Acme Tech Private Limited'); self.assertEqual(job['date_posted'],'2026-09-25'); self.assertEqual(job['verification_method'],'detail_jsonld')
    def test_internshala_adapter_and_metadata(self):
        source={'name':'Internshala','adapter':'internshala','job_card_selector':'div.individual_internship','title_selector':'div.job-internship-name','company_selector':'p.company-name','location_selector':'div.location_link','link_selector':'a.view_detail_button'}
        listing=parse_listing_soup(self.read('internshala_listing.html'),source,'https://example.test/list')[0]
        job=parse_detail_soup(self.read('internshala_detail.html'),listing,source)
        self.assertEqual(listing['company'],'Blue River Labs'); self.assertEqual(job['date_posted'],'2026-09-24')
    def test_unverified_company_is_rejected(self):
        self.assertIsNone(normalize_company('A client of freshersworld'))
        self.assertEqual(normalize_title('Full-Stack Developer Jobs Opening in A client of freshers world at Chennai-Others, ChennaiLess'),'Full-Stack Developer')

if __name__ == '__main__': unittest.main()

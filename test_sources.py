#!/usr/bin/env python3
"""
Quick test script to verify which job sources are working
"""

import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def test_source(source):
    """Test if a source's selectors are working"""
    if not source.get("enabled", False):
        return "DISABLED", 0
    
    if source.get("requires_selenium", False):
        return "NEEDS_SELENIUM", 0
    
    name = source["name"]
    url = source["url"]
    
    try:
        print(f"\nTesting: {name}")
        print(f"  URL: {url}")
        
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "lxml")
        
        # Try all job card selectors
        selectors = source["job_card_selector"].split(", ")
        total_cards = 0
        working_selector = None
        
        for selector in selectors:
            cards = soup.select(selector.strip())
            if len(cards) > 0:
                total_cards = len(cards)
                working_selector = selector.strip()
                break
        
        if total_cards > 0:
            print(f"  ✓ WORKING - Found {total_cards} cards with: {working_selector}")
            
            # Test first card
            card = soup.select(working_selector)[0]
            
            # Test title
            title_selectors = source["title_selector"].split(", ")
            title_found = False
            for ts in title_selectors:
                title_el = card.select_one(ts.strip())
                if title_el and title_el.get_text(strip=True):
                    print(f"    Title: {title_el.get_text(strip=True)[:50]}")
                    title_found = True
                    break
            
            if not title_found:
                print(f"    ⚠ Title selector not working")
            
            # Test company
            if source["type"] == "aggregator":
                company_selectors = source.get("company_selector", "").split(", ")
                company_found = False
                for cs in company_selectors:
                    if cs:
                        company_el = card.select_one(cs.strip())
                        if company_el and company_el.get_text(strip=True):
                            print(f"    Company: {company_el.get_text(strip=True)[:50]}")
                            company_found = True
                            break
                
                if not company_found:
                    print(f"    ⚠ Company selector not working")
            
            return "WORKING", total_cards
        else:
            print(f"  ✗ NO CARDS FOUND")
            print(f"    Tried selectors: {source['job_card_selector']}")
            # print(f"    Page preview: {soup.get_text()[:200]}")
            return "NO_CARDS", 0
            
    except requests.RequestException as e:
        print(f"  ✗ REQUEST FAILED: {e}")
        return "REQUEST_FAILED", 0
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return "ERROR", 0

def main():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    print("="*70)
    print("Testing Job Sources for Chennai Fresher Jobs")
    print("="*70)
    
    results = {
        "WORKING": [],
        "NEEDS_SELENIUM": [],
        "NO_CARDS": [],
        "DISABLED": [],
        "REQUEST_FAILED": [],
        "ERROR": []
    }
    
    total_jobs = 0
    
    for source in config["sources"]:
        status, count = test_source(source)
        results[status].append(source["name"])
        total_jobs += count
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    print(f"\n✓ WORKING ({len(results['WORKING'])} sources, {total_jobs} total jobs):")
    for name in results['WORKING']:
        print(f"  • {name}")
    
    if results['NEEDS_SELENIUM']:
        print(f"\n⚡ NEEDS SELENIUM ({len(results['NEEDS_SELENIUM'])} sources):")
        for name in results['NEEDS_SELENIUM']:
            print(f"  • {name}")
    
    if results['NO_CARDS']:
        print(f"\n⚠ NO CARDS FOUND ({len(results['NO_CARDS'])} sources - selectors may need updating):")
        for name in results['NO_CARDS']:
            print(f"  • {name}")
    
    if results['REQUEST_FAILED']:
        print(f"\n✗ REQUEST FAILED ({len(results['REQUEST_FAILED'])} sources):")
        for name in results['REQUEST_FAILED']:
            print(f"  • {name}")
    
    if results['DISABLED']:
        print(f"\n○ DISABLED ({len(results['DISABLED'])} sources):")
        for name in results['DISABLED']:
            print(f"  • {name}")
    
    print("\n" + "="*70)
    print(f"Total working sources: {len(results['WORKING'])}")
    print(f"Total jobs found: {total_jobs}")
    print("="*70)
    
    print("\nNow run: python enhanced_scraper.py")

if __name__ == "__main__":
    main()

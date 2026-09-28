import requests
from bs4 import BeautifulSoup

url = "https://www.freshersworld.com/jobs/jobsearch/chennai-jobs"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

resp = requests.get(url, headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, "lxml")

cards = soup.select("div.job-container")
print(f"Found {len(cards)} cards\n")

if len(cards) > 0:
    card = cards[0]
    print("First card HTML structure:")
    print(card.prettify()[:1000])
    print("\n" + "="*60)
    
    # Try different title selectors
    selectors = [
        "h3.latest-jobs-title a",
        "div.job-tittle a",
        "h2 a",
        "h3 a",
        "a.latest-jobs-title",
        "div.latest-jobs-title"
    ]
    
    print("\nTrying title selectors:")
    for sel in selectors:
        el = card.select_one(sel)
        if el:
            print(f"  {sel}: {el.get_text(strip=True)[:50]}")
        else:
            print(f"  {sel}: NOT FOUND")
    
    print("\nAll links in card:")
    for link in card.find_all('a')[:3]:
        print(f"  {link.get('class')}: {link.get_text(strip=True)[:50]}")

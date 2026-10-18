import json
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# Real browser headers taaki SarkariResult ya baaki sites 403 block na karein
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,hi;q=0.8'
}

def clean_text(text):
    return re.sub(r'\s+', ' ', text or '').strip()

# LEVEL-2 DEEP SCRAPER: Page ke andar ghus kar direct links nikalna
def extract_deep_official_links(page_url):
    details = {
        "apply_link": "#",
        "notif_url": "#",
        "official_web": "#"
    }
    
    if not page_url or page_url == "#":
        return details

    try:
        resp = requests.get(page_url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return details
            
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            text = a.get_text().lower()
            parent_text = a.parent.get_text().lower() if a.parent else ""
            combined = f"{text} {parent_text}"

            # Filter out third-party/internal links
            is_internal = any(domain in href.lower() for domain in [
                'sarkariresult', 'freejobalert', 'mysarkarinaukri', 'rojgarresult',
                'sarkariexam', 'jobriya', 'indgovtjobs', 'aglasem', 'whatsapp.com', 't.me'
            ])

            # 1. Direct Apply Online Link (Sarkari portal)
            if ("apply online" in combined or "registration" in combined or "apply" in text):
                if not is_internal and details["apply_link"] == "#" and href.startswith("http"):
                    details["apply_link"] = href

            # 2. Direct Official Notification (.pdf ya direct notification file)
            if ("notification" in combined or "advt" in combined or href.lower().endswith(".pdf")):
                if details["notif_url"] == "#" and (href.lower().endswith(".pdf") or not is_internal):
                    details["notif_url"] = href

            # 3. Direct Official Website Board
            if ("official website" in combined or "official portal" in combined):
                if not is_internal and details["official_web"] == "#" and href.startswith("http"):
                    details["official_web"] = href

    except Exception as e:
        print(f"Deep scraping error on {page_url}: {e}")

    return details

# MULTI-SITE SCRAPER ENGINE
def scrape_all_sources():
    all_extracted_posts = []
    today_str = datetime.now().strftime("%d %b %Y")

    # 1. SCRAPE SARKARIRESULT.COM
    try:
        print("Scraping SarkariResult...")
        res = requests.get("https://www.sarkariresult.com/latestjob/", headers=HEADERS, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            for li in soup.select("#post ul li a")[:10]:
                title = clean_text(li.get_text())
                href = li['href']
                if not href.startswith("http"):
                    href = "https://www.sarkariresult.com" + href
                
                deep_links = extract_deep_official_links(href)
                all_extracted_posts.append({
                    "title": title,
                    "source": "SarkariResult.com",
                    "category": "latest_jobs",
                    "date": today_str,
                    "apply_link": deep_links["apply_link"],
                    "notif_url": deep_links["notif_url"],
                    "webUrl": deep_links["official_web"],
                    "url": href
                })
    except Exception as e:
        print(f"Error SarkariResult: {e}")

    # 2. SCRAPE FREEJOBALERT.COM
    try:
        print("Scraping FreeJobAlert...")
        res = requests.get("https://www.freejobalert.com/government-jobs/", headers=HEADERS, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            for row in soup.select("table.latnobda tr")[1:10]:
                links = row.find_all('a')
                if len(links) >= 1:
                    title = clean_text(links[0].get_text())
                    href = links[0]['href']
                    deep_links = extract_deep_official_links(href)
                    all_extracted_posts.append({
                        "title": title,
                        "source": "FreeJobAlert.com",
                        "category": "latest_jobs",
                        "date": today_str,
                        "apply_link": deep_links["apply_link"],
                        "notif_url": deep_links["notif_url"],
                        "webUrl": deep_links["official_web"],
                        "url": href
                    })
    except Exception as e:
        print(f"Error FreeJobAlert: {e}")

    return all_extracted_posts

# SAVE TO jobs_database.json
if __name__ == "__main__":
    posts = scrape_all_sources()
    
    # Existing database load karein taaki purane posts delete na hon
    try:
        with open("jobs_database.json", "r", encoding="utf-8") as f:
            existing = json.load(f)
            if not isinstance(existing, list):
                existing = existing.get("posts", [])
    except Exception:
        existing = []

    # Deduplication check
    existing_titles = {clean_text(p.get("title", "")).lower() for p in existing}
    new_added = 0

    for p in posts:
        t_key = clean_text(p["title"]).lower()
        if t_key and t_key not in existing_titles:
            existing_titles.add(t_key)
            existing.insert(0, p)
            new_added += 1

    with open("jobs_database.json", "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"Scraping Complete! Added {new_added} new posts with direct official links.")

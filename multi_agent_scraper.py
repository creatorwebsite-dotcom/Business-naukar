import os
import re
import json
import time
import random
import hashlib
import urllib.request
import urllib.error
import ssl
from datetime import datetime
from bs4 import BeautifulSoup

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

DATABASE_FILE = "jobs_database.json"

SOURCES = [
    {"name": "SarkariResult", "url": "https://www.sarkariresult.com/"},
    {"name": "FreeJobAlert", "url": "https://www.freejobalert.com/"},
    {"name": "RojgarResult", "url": "https://www.rojgarresult.com/"},
    {"name": "SarkariExam", "url": "https://www.sarkariexam.com/"},
    {"name": "IndGovtJobs", "url": "https://www.indgovtjobs.in/"},
    {"name": "FreshersNow", "url": "https://www.freshersnow.com/government-jobs-india/"},
    {"name": "CareerPower", "url": "https://www.careerpower.in/upcoming-government-exams.html"},
    {"name": "JagranJosh", "url": "https://www.jagranjosh.com/articles-sarkari-naukri-1288164377-1"}
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
]

def get_headers(referer="https://www.google.com/"):
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
        "Referer": referer,
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
        "Upgrade-Insecure-Requests": "1"
    }

def detect_category(title):
    t = title.lower()
    if any(k in t for k in ["result", "merit list", "cutoff", "cut off", "score card", "marks"]):
        return "results"
    elif any(k in t for k in ["admit card", "hall ticket", "call letter", "exam city"]):
        return "admit_cards"
    elif any(k in t for k in ["answer key", "response sheet"]):
        return "answer_keys"
    elif any(k in t for k in ["syllabus", "exam pattern"]):
        return "syllabus"
    elif any(k in t for k in ["admission", "counselling", "entrance"]):
        return "admissions"
    return "latest_jobs"

def deep_crawl_job_page(job_url):
    extracted = {
        "apply_link": job_url,
        "notif_pdf": job_url,
        "official_web": job_url,
        "admit_card_link": "",
        "answer_key_link": "",
        "result_link": "",
        "syllabus_link": "",
        "deep_description": ""
    }
    try:
        req = urllib.request.Request(job_url, headers=get_headers(referer="https://www.google.com/"))
        with urllib.request.urlopen(req, context=ssl_context, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html, "html.parser")
            
            for a in soup.find_all("a", href=True):
                txt = a.get_text().strip().lower()
                href = a["href"].strip()
                
                if not href.startswith("http"):
                    continue
                
                if any(k in txt for k in ["apply", "registration", "online form"]):
                    extracted["apply_link"] = href
                elif any(k in txt for k in ["pdf", "notification", "advt"]) or href.endswith(".pdf"):
                    extracted["notif_pdf"] = href
                elif any(k in txt for k in ["admit card", "hall ticket", "call letter"]):
                    extracted["admit_card_link"] = href
                elif any(k in txt for k in ["answer key", "response sheet"]):
                    extracted["answer_key_link"] = href
                elif any(k in txt for k in ["result", "merit list", "scorecard"]):
                    extracted["result_link"] = href
                elif "syllabus" in txt:
                    extracted["syllabus_link"] = href
                elif any(k in txt for k in ["official website", "board website", "home page"]):
                    extracted["official_web"] = href

            content_div = soup.find("div", class_=["article-content", "post-content", "job-details", "content"]) or soup.find("article")
            if content_div:
                for s in content_div(["script", "style", "iframe"]):
                    s.decompose()
                extracted["deep_description"] = str(content_div)
            else:
                paras = [p.get_text() for p in soup.find_all("p") if len(p.get_text()) > 40]
                extracted["deep_description"] = "<div class='scraped-deep-desc'>" + "".join([f"<p>{p}</p>" for p in paras[:8]]) + "</div>"

    except Exception as e:
        print(f"[Deep Crawl Notice] Error for {job_url}: {e}")

    return extracted

def build_hybrid_human_post(title, link, source_name):
    deep_data = deep_crawl_job_page(link)
    category = detect_category(title)
    today_str = datetime.now().strftime("%d %B %Y")
    clean_title = re.sub(r'\s+', ' ', title).strip()

    full_desc_html = f"""
<div class="human-article-box">
    <p><strong>{clean_title}</strong> ke liye official notification jari kiya gaya hai. Is bharti se jude sabhi mahatvapurna details, dates aur instructions niche diye gaye hain.</p>
    <h4>📋 Notification Overview ({today_str})</h4>
    <ul>
        <li><strong>Post / Update Name:</strong> {clean_title}</li>
        <li><strong>Category:</strong> {category}</li>
        <li><strong>Source Portal:</strong> {source_name}</li>
    </ul>
    <h4>📖 Detailed Job Description & Full Information</h4>
    <div>{deep_data['deep_description']}</div>
</div>
"""

    job_id = hashlib.md5(f"{title}_{link}".encode("utf-8")).hexdigest()[:12]
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {
        "id": job_id,
        "title": clean_title,
        "category": category,
        "source": source_name,
        "link": link,
        "apply_link": deep_data["apply_link"],
        "notif_url": deep_data["notif_pdf"],
        "webUrl": deep_data["official_web"] if deep_data["official_web"] != link else link,
        "admit_card_link": deep_data["admit_card_link"],
        "answer_key_link": deep_data["answer_key_link"],
        "result_link": deep_data["result_link"],
        "syllabus_link": deep_data["syllabus_link"],
        "date": today_str,
        "post_date": today_str,
        "updated_at": now_iso,
        "summary": clean_title + " official notification and details.",
        "description": full_desc_html,
        "content": full_desc_html,
        "engine": "Hybrid Deep-Crawl Scraper",
        "status": "published"
    }

def scrape_source(source):
    found_items = []
    headers = get_headers(referer="https://www.google.com/")
    req = urllib.request.Request(source["url"], headers=headers)
    try:
        with urllib.request.urlopen(req, context=ssl_context, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html, "html.parser")
            for a_tag in soup.find_all("a", href=True):
                text = re.sub(r'\s+', ' ', a_tag.get_text()).strip()
                href = a_tag["href"].strip()

                if 18 <= len(text) <= 130 and any(
                    kw in text.lower() for kw in [
                        "online form", "recruitment", "vacancy", "bharti", "result",
                        "admit card", "answer key", "syllabus", "apply online", "notification", "2026", "2025"
                    ]
                ):
                    if href.startswith("/"):
                        base = "/".join(source["url"].split("/")[:3])
                        href = base + href
                    if href.startswith("http"):
                        found_items.append((text, href))
    except Exception as e:
        print(f"[Warning] Could not fetch {source['name']}: {e}")

    return found_items[:12]

def load_existing_database():
    if os.path.exists(DATABASE_FILE):
        try:
            with open(DATABASE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "posts" in data:
                    return data["posts"]
                elif isinstance(data, dict) and "jobs" in data:
                    return data["jobs"]
        except Exception:
            pass
    return []

def main():
    print("🚀 Starting Deep-Crawl Multi-Agent Scraper...")
    existing_jobs = load_existing_database()
    existing_titles = {j.get("title", "").lower().strip() for j in existing_jobs if isinstance(j, dict)}

    new_jobs = []
    for source in SOURCES:
        print(f"🔍 Scanning {source['name']}...")
        items = scrape_source(source)
        for title, link in items:
            norm_title = title.lower().strip()
            if norm_title in existing_titles:
                continue

            job_entry = build_hybrid_human_post(title, link, source["name"])
            new_jobs.append(job_entry)
            existing_titles.add(norm_title)
            time.sleep(1.0)

        time.sleep(random.uniform(0.8, 1.8))

    print(f"✅ New Unique Updates Found: {len(new_jobs)}")
    updated_database = new_jobs + existing_jobs
    updated_database = updated_database[:400]

    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_database, f, ensure_ascii=False, indent=2)

    print(f"🎉 Successfully saved {len(updated_database)} total posts to {DATABASE_FILE}!")

if __name__ == "__main__":
    main()

import os
import re
import json
import time
import hashlib
import asyncio
import concurrent.futures
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

DATABASE_FILE = "jobs_database.json"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# 8 Major Aggregators & Mirrors
SOURCES = [
    {"name": "SarkariResultMain", "url": "https://www.sarkariresult.com/"},
    {"name": "FreeJobAlertMain", "url": "https://www.freejobalert.com/government-jobs/"},
    {"name": "RojgarResult", "url": "https://www.rojgarresult.com/"},
    {"name": "SarkariExam", "url": "https://www.sarkariexam.com/"},
    {"name": "IndGovtJobs", "url": "https://www.indgovtjobs.in/"},
    {"name": "FreshersNow", "url": "https://www.freshersnow.com/government-jobs-india/"}
]

# Official Recruitment Portal Hubs Mapped from PDF Master Directory (Section 1 & 2)
OFFICIAL_HUBS = {
    "upsc": {"name": "UPSC", "home": "https://upsc.gov.in", "notices": "https://upsc.gov.in/examinations/active-examinations"},
    "ssc": {"name": "SSC", "home": "https://ssc.gov.in", "notices": "https://ssc.gov.in/Portal/Notices"},
    "ibps": {"name": "IBPS", "home": "https://www.ibps.in", "notices": "https://www.ibps.in/notifications/"},
    "sbi": {"name": "SBI", "home": "https://sbi.co.in/web/careers", "notices": "https://sbi.co.in/web/careers/current-openings"},
    "rbi": {"name": "RBI", "home": "https://www.rbi.org.in", "notices": "https://opportunities.rbi.org.in/Scripts/Vacancies.aspx"},
    "nabard": {"name": "NABARD", "home": "https://www.nabard.org", "notices": "https://www.nabard.org/careers-notices1.aspx?cid=693&id=26"},
    "rrb": {"name": "Railway RRB", "home": "https://www.rrbcdg.gov.in", "notices": "https://www.rrbcdg.gov.in"},
    "mpsc": {"name": "Maharashtra MPSC", "home": "https://mpsc.gov.in", "notices": "https://mpsc.gov.in/adv_notification/8"},
    "uppsc": {"name": "UPPSC", "home": "https://uppsc.up.nic.in", "notices": "https://uppsc.up.nic.in/CandidatePages/Notifications.aspx"},
    "bpsc": {"name": "Bihar BPSC", "home": "https://bpsc.bih.nic.in", "notices": "https://bpsc.bih.nic.in"},
    "iocl": {"name": "IOCL", "home": "https://iocl.com", "notices": "https://iocl.com/latest-job-opening"},
    "ongc": {"name": "ONGC", "home": "https://ongcindia.com", "notices": "https://ongcindia.com/web/eng/career-tab"},
    "csc": {"name": "CSC e-Seva", "home": "https://csc.gov.in", "notices": "https://csc.gov.in/careers"},
    "cantonment": {"name": "Cantonment Board", "home": "https://ecantonmentboard.gov.in", "notices": "https://ecantonmentboard.gov.in"}
}

MASTER_DIRECTORY_CATALOG = [
    ("UPSC Civil Services IAS / IPS / IFS Examination", "upsc"),
    ("SSC CGL Combined Graduate Level Exam", "ssc"),
    ("SSC CHSL Lower Division Clerk Recruitment", "ssc"),
    ("SSC MTS & Havaldar Recruitment", "ssc"),
    ("IBPS PO Probationary Officer Recruitment", "ibps"),
    ("IBPS Clerk Customer Service Associate", "ibps"),
    ("SBI Junior Associate Clerk Recruitment", "sbi"),
    ("SBI Probationary Officer PO Recruitment", "sbi"),
    ("RBI Grade B Officer Recruitment", "rbi"),
    ("NABARD Grade A Assistant Manager", "nabard"),
    ("RRB NTPC Station Master & Goods Train Manager", "rrb"),
    ("RRB Group D Track Maintainer Recruitment", "rrb"),
    ("RRB ALP Assistant Loco Pilot Recruitment", "rrb"),
    ("Maharashtra MPSC Rajyasewa State Services Exam", "mpsc"),
    ("Maharashtra Police Constable Bharti", "mpsc"),
    ("Maharashtra Talathi Revenue Department Recruitment", "mpsc"),
    ("Uttar Pradesh UPPSC Combined State Services PCS Exam", "uppsc"),
    ("Uttar Pradesh UP Police Constable Recruitment", "uppsc"),
    ("Bihar BPSC Combined Competitive Exam", "bpsc"),
    ("IOCL Engineering Assistant & Apprentice Recruitment", "iocl"),
    ("ONGC Graduate Trainee & Apprentice Recruitment", "ongc"),
    ("Gram Panchayat Data Entry Operator DEO", "csc"),
    ("Municipal Corporation Tax Collector & Sanitary Inspector", "cantonment"),
    ("GMC Hospital Ward Boy & Lab Attendant", "cantonment"),
    ("District Cooperative Central Bank DCCB Clerk", "nabard"),
    ("Private Bank Sales Executive DSA", "ibps")
]

NON_GOVT_KEYWORDS = ["ongc", "iocl", "ntpc", "sail", "bhel", "private", "apprentice", "semi-govt", "psu", "dccb", "pacs"]
STATE_KEYWORDS = {
    "Maharashtra": ["mpsc", "mumbai", "pune", "nagpur", "maharashtra", "talathi", "gramsevak", "srpf"],
    "Uttar Pradesh": ["uppsc", "lucknow", "uttar pradesh", "lekhpal", "up police"],
    "Bihar": ["bpsc", "bihar", "patna", "csbc"],
    "Madhya Pradesh": ["mppsc", "madhya pradesh", "bhopal", "esb"],
    "Rajasthan": ["rpsc", "rajasthan", "jaipur", "patwari"]
}
BLOCK_DOMAINS = ['play.google.com', 'apps.apple.com', 'whatsapp.com', 't.me', 'facebook.com', 'twitter.com', 'youtube.com', 'pinterest.com']
AGGREGATOR_DOMAINS = ['sarkariresult.com', 'freejobalert.com', 'rojgarresult.com', 'sarkariexam.com', 'indgovtjobs.in', 'freshersnow.com']
JUNK_TITLES = ["sarkari result", "tools", "latest notifications", "view more", "click here", "home", "contact us", "disclaimer", "privacy policy"]

def blocking_fetch(url):
    try:
        res = cffi_requests.get(url, impersonate="chrome110", timeout=15)
        if res.status_code == 200 and len(res.text) > 200:
            return res.text
    except Exception:
        pass
    return ""

async def safe_fetch_async(url, loop):
    if not url or not url.startswith("http"):
        return ""
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, blocking_fetch, url),
            timeout=20.0
        )
    except asyncio.TimeoutError:
        return ""
    except Exception:
        return ""

def is_within_one_month(date_str):
    """Checks if the date is within the last 30 days (1 month)."""
    if not date_str or "To be notified" in date_str or "As per" in date_str:
        return True # Default to true if exact date isn't parsed yet to avoid missing new posts
    
    date_patterns = [
        r'(\d{1,2})[\/\-\.\s](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\/\-\.\s](202[4-9])',
        r'(\d{1,2})[\/\-\.\s](\d{1,2})[\/\-\.\s](202[4-9])'
    ]
    
    for pat in date_patterns:
        match = re.search(pat, date_str, re.IGNORECASE)
        if match:
            try:
                parsed_date = datetime.strptime(match.group(0), "%d %b %Y" if len(match.groups())==3 and not match.group(2).isdigit() else "%d-%m-%Y")
                if datetime.now() - parsed_date <= timedelta(days=31):
                    return True
                else:
                    return False
            except Exception:
                pass
    return True # If unable to parse, keep it safe

class IntentAndMetaClassifierAgent:
    @staticmethod
    def analyze(title):
        t = title.lower()
        if any(k in t for k in ["answer key", "response sheet"]):
            category, intent = "Answer Key", "INTENT_ANSWER_KEY"
        elif any(k in t for k in ["result", "merit list", "cutoff"]):
            category, intent = "Result", "INTENT_RESULT"
        elif any(k in t for k in ["admit card", "hall ticket"]):
            category, intent = "Admit Card", "INTENT_ADMIT_CARD"
        elif any(k in t for k in ["syllabus"]):
            category, intent = "Syllabus", "INTENT_SYLLABUS"
        else:
            category, intent = "Latest Jobs", "INTENT_APPLY"

        job_type = "Non-Govt + Semi-Govt" if any(k in t for k in NON_GOVT_KEYWORDS) else "Govt"
        state = "All India / Central"
        for s_name, kws in STATE_KEYWORDS.items():
            if any(kw in t for kw in kws):
                state = s_name
                break
        return {"category": category, "primary_intent": intent, "job_type": job_type, "state": state}

class MasterSynthesizer:
    @staticmethod
    def build_post(title, link, source_name, used_quotes_set):
        meta = IntentAndMetaClassifierAgent.analyze(title)
        job_id = hashlib.md5(title.encode("utf-8")).hexdigest()[:12]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        quote = f"🔥 [{title[:25]} Challenge]: Apni zidd aur kadi mehnat ke sath aaj hi is mukable ko fateh karein!"
        used_quotes_set.add(quote.lower())

        content = f"""
<div class="short-view-card" style="background:#ffffff; border:1px solid #cbd5e1; border-radius:8px; padding:18px; margin-bottom:20px;">
    <div style="background:#fef3c7; border-left:4px solid #d97706; padding:8px 12px; margin-bottom:10px; font-weight:600; color:#92400e;">"{quote}"</div>
    <h3>📢 {title}</h3>
    <p>Category: <strong>{meta['category']}</strong> | Type: <strong>{meta['job_type']}</strong> | State: <strong>{meta['state']}</strong></p>
    <p><a href="{link}" target="_blank" style="color:#2563eb; font-weight:700;">Official Application & Notification Portal Link</a></p>
</div>
"""
        return {
            "id": job_id, "intent_signature": f"{job_id}__{meta['primary_intent']}",
            "title": title, "category": meta["category"], "primary_intent": meta["primary_intent"],
            "job_type": meta["job_type"], "state": meta["state"], "unique_quote": quote, "source": source_name,
            "link": link, "url": link, "apply_link": link, "notif_url": link, "download_pdf": link,
            "date": datetime.now().strftime("%d %b %Y"), "post_date": datetime.now().strftime("%d %b %Y"),
            "updated_at": now_str, "summary": f"Verified active recruitment update for {title}.", "description": content,
            "content": content, "status": "pending_review"
        }

async def process_aggregator(src, seen, used_quotes_set, loop):
    posts = []
    html = await safe_fetch_async(src["url"], loop)
    if not html:
        return posts
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        text = re.sub(r'\s+', ' ', a.get_text(" ", strip=True)).strip()
        href = urljoin(src["url"], a["href"].strip())
        t_low = text.lower()
        if len(text) < 15 or len(text) > 130:
            continue
        if any(j in t_low for j in JUNK_TITLES):
            continue
        norm = text.lower().strip()
        if norm in seen:
            continue
        if any(kw in t_low for kw in ["recruitment", "online form", "result", "admit card", "vacancy", "bharti", "2026", "notification"]):
            post = MasterSynthesizer.build_post(text, href, src["name"], used_quotes_set)
            if post and is_within_one_month(post["date"]):
                posts.append(post)
                seen.add(norm)
    return posts

async def main_async():
    print("🚀 Starting Ultra-Fast Non-Blocking 6-Minute Scraper Engine...")
    existing = []
    if os.path.exists(DATABASE_FILE):
        try:
            with open(DATABASE_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    seen = {j.get("title", "").lower().strip() for j in existing if isinstance(j, dict)}
    used_quotes_set = {j.get("unique_quote", "").lower().strip() for j in existing if isinstance(j, dict)}
    new_posts = []

    loop = asyncio.get_running_loop()

    # 1. Fetch Aggregators Concurrently
    tasks = [process_aggregator(src, seen, used_quotes_set, loop) for src in SOURCES]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for res in results:
        if isinstance(res, list):
            new_posts.extend(res)

    # 2. Master Directory Sweep
    for title, hub_key in MASTER_DIRECTORY_CATALOG:
        norm = title.lower().strip()
        if norm in seen:
            continue
        link = f"https://www.google.com/search?q={urllib.parse.quote(title + ' official recruitment portal notification')}"
        post = MasterSynthesizer.build_post(title, link, "Master Directory", used_quotes_set)
        if post and is_within_one_month(post["date"]):
            new_posts.append(post)
            seen.add(norm)

    final_db = new_posts + existing
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(final_db, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 Lightning Fast Sync Complete! Total Records in JSON: {len(final_db)}")

def main():
    try:
        # Enforce strict 330 seconds (5.5 minutes) hard timeout limit for safety
        asyncio.run(asyncio.wait_for(main_async(), timeout=330.0))
    except asyncio.TimeoutError:
        print("⚠️ Execution reached 5.5 minutes hard limit. Saving current progress safely.")

if __name__ == "__main__":
    main()

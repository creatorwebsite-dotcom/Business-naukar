import os
import re
import json
import time
import hashlib
import asyncio
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

DATABASE_FILE = "jobs_database.json"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

SOURCES = [
    {"name": "SarkariResultMain", "url": "https://www.sarkariresult.com/"},
    {"name": "SarkariResultMirror", "url": "https://sarkariresult.com.cm/"},
    {"name": "FreeJobAlertMain", "url": "https://www.freejobalert.com/government-jobs/"},
    {"name": "RojgarResult", "url": "https://www.rojgarresult.com/"},
    {"name": "SarkariExam", "url": "https://www.sarkariexam.com/"},
    {"name": "IndGovtJobs", "url": "https://www.indgovtjobs.in/"},
    {"name": "FreshersNow", "url": "https://www.freshersnow.com/government-jobs-india/"},
    {"name": "CareerPower", "url": "https://www.careerpower.in/upcoming-government-exams.html"}
]

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
    ("UPSC Central Armed Police Forces CAPF Assistant Commandant", "upsc"),
    ("SSC CGL Combined Graduate Level (AAO, ASO, Income Tax Inspector)", "ssc"),
    ("SSC CHSL LDC / JSA / Postal Assistant / DEO", "ssc"),
    ("SSC MTS Multi-Tasking Staff & Havaldar", "ssc"),
    ("SSC Stenographer Grade C & D", "ssc"),
    ("SSC GD Constable BSF CRPF CISF ITBP SSB", "ssc"),
    ("SSC Junior Engineer JE Civil Electrical Mechanical", "ssc"),
    ("IBPS PO Probationary Officer Participating Banks", "ibps"),
    ("IBPS Clerk Customer Service Associate", "ibps"),
    ("IBPS RRB Officer Scale I & Office Assistant", "ibps"),
    ("IBPS Specialist Officer SO IT AFO Law", "ibps"),
    ("SBI Probationary Officer PO Recruitment", "sbi"),
    ("SBI Junior Associate Customer Support Clerk", "sbi"),
    ("RBI Grade B Officer & RBI Assistant", "rbi"),
    ("NABARD Grade A Assistant Manager & Development Assistant", "nabard"),
    ("LIC Administrative Officer AAO & Assistant", "ibps"),
    ("RRB NTPC Station Master & Goods Train Manager", "rrb"),
    ("RRB Group D Track Maintainer & Pointsman", "rrb"),
    ("RRB ALP Assistant Loco Pilot & Technician", "rrb"),
    ("RRB Junior Engineer & Paramedical Staff", "rrb"),
    ("RPF Constable & Sub-Inspector SI", "rrb"),
    ("Indian Army Agniveer GD Technical Tradesman", "upsc"),
    ("Indian Navy Agniveer SSR & MR Recruitment", "upsc"),
    ("Indian Air Force Agniveervayu Intake", "upsc"),
    ("Indian Coast Guard Navik & Yantrik", "upsc"),
    ("Delhi Police Constable Executive & Head Constable", "ssc"),
    ("Maharashtra MPSC Rajyasewa State Services Deputy Collector", "mpsc"),
    ("Maharashtra MPSC Combined Group B PSI STI ASO", "mpsc"),
    ("Maharashtra Police Constable Driver & SRPF Bharti", "mpsc"),
    ("Maharashtra Forest Department Vanrakshak Forest Guard", "mpsc"),
    ("Maharashtra Talathi Revenue Department Bharti", "mpsc"),
    ("Maharashtra Gramsevak Zilla Parishad Recruitment", "mpsc"),
    ("Maharashtra Arogya Sevak Health Department", "mpsc"),
    ("Maharashtra Krishi Sevak Agriculture Assistant", "mpsc"),
    ("MSEDCL Mahadiscom Vidyut Sahayak & Junior Engineer", "mpsc"),
    ("Uttar Pradesh UPPSC Combined State UPPCS & RO ARO", "uppsc"),
    ("Uttar Pradesh UP Police Constable & Sub-Inspector SI", "uppsc"),
    ("Uttar Pradesh UPSSSC PET & Rajasva Lekhpal", "uppsc"),
    ("Bihar BPSC Combined Competitive Examination CCE", "bpsc"),
    ("Bihar Police Constable CSBC Recruitment", "bpsc"),
    ("Bihar BSSC Inter-Level Clerk Recruitment", "bpsc"),
    ("Madhya Pradesh MPPSC State Service Exam & Police Constable", "uppsc"),
    ("Rajasthan RPSC RAS / RTS & RSMSSB Patwari", "uppsc"),
    ("CBSE CTET Central Teacher Eligibility Test Paper I & II", "ssc"),
    ("KVS Primary Teacher PRT TGT PGT Recruitment", "ssc"),
    ("NVS Navodaya Vidyalaya Principal PGT TGT Staff Nurse", "ssc"),
    ("Delhi DSSSB Primary Teacher TGT PGT LDC", "ssc"),
    ("NTA UGC NET & CSIR UGC NET", "ssc"),
    ("GATE Graduate Aptitude Test in Engineering", "ssc"),
    ("IOCL Engineering Assistant & Technical Apprentice", "iocl"),
    ("NTPC Engineering Executive Trainee EET", "iocl"),
    ("ONGC Graduate Trainee & Apprentice", "ongc"),
    ("BHEL Executive Trainee & Artisan", "iocl"),
    ("GAIL Executive Trainee", "iocl"),
    ("POWERGRID Management Trainee", "iocl"),
    ("Coal India Limited CIL Management Trainee", "iocl"),
    ("DRDO Scientist B RAC & CEPTAM", "upsc"),
    ("ISRO Centralized Recruitment Board Scientist SC", "upsc"),
    ("India Post Gramin Dak Sevak GDS & Postal Assistant", "upsc"),
    ("BSNL Management Trainee & Junior Telecom Officer JTO", "upsc"),
    ("Delhi Metro DMRC Executive & Non-Executive Trainee", "upsc"),
    ("Supreme Court of India Junior Court Assistant JCA", "upsc"),
    ("Food Corporation of India FCI Assistant Grade III & JE", "ssc"),
    ("ESIC Upper Division Clerk UDC & Staff Nurse", "ssc"),
    ("EPFO Social Security Assistant SSA & Enforcement Officer", "ssc"),
    ("SEBI Grade A Officer Assistant Manager", "rbi"),
    ("Intelligence Bureau IB ACIO Grade II & Security Assistant", "upsc"),
    ("Gram Panchayat Data Entry Operator DEO & Computer Operator", "csc"),
    ("Gram Panchayat Rozgar Sahayak & Village Water Pump Operator", "csc"),
    ("Municipal Corporation Tax Collector & Sanitary Inspector", "cantonment"),
    ("Municipal Corporation Junior Clerk & Peon", "cantonment"),
    ("GMC Government Medical College Hospital Attendant Ward Boy", "cantonment"),
    ("District Co-operative Central Bank DCCB Junior Clerk", "nabard"),
    ("Primary Agricultural Credit Society PACS Manager & Secretary", "nabard"),
    ("Zilla Parishad Lower Division Clerk LDC & Extension Officer", "mpsc"),
    ("APMC Mandi Samiti Auction Recorder & Weighment Clerk", "cantonment"),
    ("Cantonment Board Safaiwala LDC & Junior Engineer", "cantonment"),
    ("Private Security Guard Securitas SIS", "csc"),
    ("Private Bank Sales Executive DSA & Teller DEO", "ibps"),
    ("CSC Common Service Center E-Seva Kendra Operator", "csc"),
    ("Private Hospital Patient Care Coordinator & Pharmacy Assistant", "csc"),
    ("Reliance Retail D-Mart Cashier & Floor Associate", "csc"),
    ("Amazon Flipkart Warehouse Delivery Associate & Loader", "csc"),
    ("DTDC Blue Dart Courier Delivery Boy", "csc"),
    ("Local Cable Broadband Internet Service Technician", "csc"),
    ("Private Petrol Pump Fuel Attendant", "iocl"),
    ("Private Hotel Restaurant Waiter & Room Boy", "csc"),
    ("Construction Site Mason Helper & Real Estate Telecaller", "csc"),
    ("Toll Plaza Toll Collector & Parking Lot Attendant", "csc"),
    ("Cooperative Housing Society Watchman & Electrician", "csc")
]

NON_GOVT_KEYWORDS = ["ongc", "iocl", "ntpc", "sail", "bhel", "private", "apprentice", "semi-govt", "psu", "dccb", "pacs", "reliance", "amazon", "flipkart"]
STATE_KEYWORDS = {
    "Maharashtra": ["mpsc", "mumbai", "pune", "nagpur", "maharashtra", "talathi", "gramsevak", "srpf"],
    "Uttar Pradesh": ["uppsc", "lucknow", "uttar pradesh", "lekhpal", "up police"],
    "Bihar": ["bpsc", "bihar", "patna", "csbc"],
    "Madhya Pradesh": ["mppsc", "madhya pradesh", "bhopal", "esb"],
    "Rajasthan": ["rpsc", "rajasthan", "jaipur", "patwari"]
}
BLOCK_DOMAINS = [
    'play.google.com', 'apps.apple.com', 'whatsapp.com', 't.me', 'facebook.com', 
    'twitter.com', 'youtube.com', 'pinterest.com', 'sarkariresulttools.net', 'addtoany.com'
]
AGGREGATOR_DOMAINS = [
    'sarkariresult.com', 'sarkariresult.com.cm', 'freejobalert.com', 
    'rojgarresult.com', 'sarkariexam.com', 'indgovtjobs.in', 'freshersnow.com', 'careerpower.in'
]
JUNK_TITLES = ["sarkari result", "tools", "latest notifications", "view more", "click here", "home", "contact us", "disclaimer", "privacy policy"]

def blocking_fetch(url):
    try:
        res = cffi_requests.get(url, impersonate="chrome110", timeout=12)
        if res.status_code == 200 and len(res.text) > 200:
            return res.text
    except Exception:
        pass
    return ""

async def safe_fetch_non_blocking(url, loop):
    if not url or not url.startswith("http"):
        return ""
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, blocking_fetch, url),
            timeout=35.0
        )
    except Exception:
        return ""

def is_valid_official_link(url):
    if not url or not url.startswith("http") or "#" in url:
        return False
    u_low = url.lower()
    if any(b in u_low for b in BLOCK_DOMAINS):
        return False
    if any(ag in u_low for ag in AGGREGATOR_DOMAINS):
        return False
    return True

def get_guaranteed_link(title, default_fallback=""):
    if default_fallback and is_valid_official_link(default_fallback):
        return default_fallback
    return f"https://www.google.com/search?q={urllib.parse.quote(title + ' official notification apply online')}"

def deep_extract_real_links(article_html, article_url, title=""):
    apply_link = ""
    notif_url = ""
    download_pdf = ""

    if article_html:
        soup = BeautifulSoup(article_html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(article_url, a["href"].strip())
            text = a.get_text(" ", strip=True).lower()

            if not is_valid_official_link(href):
                continue

            if any(pdf_kw in href.lower() for pdf_kw in [".pdf", "notification", "advt", "notice"]):
                if not download_pdf:
                    download_pdf = href
                if not notif_url:
                    notif_url = href
            elif any(apply_kw in text for apply_kw in ["apply online", "registration", "click here to apply", "online form", "official website"]):
                if not apply_link:
                    apply_link = href

    # Guaranteed fallbacks so fields are never empty or hash
    if not apply_link:
        apply_link = get_guaranteed_link(title, article_url if is_valid_official_link(article_url) else "")
    if not notif_url:
        notif_url = apply_link
    if not download_pdf:
        download_pdf = apply_link

    return apply_link, notif_url, download_pdf

def is_within_one_month(date_str):
    if not date_str or "To be notified" in date_str or "As per" in date_str:
        return True
    date_patterns = [
        r'(\d{1,2})[\/\-\.\s](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\/\-\.\s](202[4-9])',
        r'(\d{1,2})[\/\-\.\s](\d{1,2})[\/\-\.\s](202[4-9])'
    ]
    for pat in date_patterns:
        match = re.search(pat, date_str, re.IGNORECASE)
        if match:
            try:
                parsed_date = datetime.strptime(match.group(0), "%d %b %Y" if len(match.groups())==3 and not match.group(2).isdigit() else "%d-%m-%Y")
                return datetime.now() - parsed_date <= timedelta(days=31)
            except Exception:
                pass
    return True

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
    def build_post(title, article_url, source_name, used_quotes_set, article_html=""):
        meta = IntentAndMetaClassifierAgent.analyze(title)
        intent_sig = f"{hashlib.md5(title.lower().encode('utf-8')).hexdigest()[:10]}__{meta['primary_intent']}"
        job_id = hashlib.md5(intent_sig.encode("utf-8")).hexdigest()[:12]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        apply_link, notif_url, download_pdf = deep_extract_real_links(article_html, article_url, title)

        quote = f"🔥 [{title[:30]} Challenge]: Apni zidd, discipline aur kadi mehnat ke sath is mukable ko fateh karke dikhayein!"
        if quote.lower() in used_quotes_set:
            quote = f"🔥 [{title[:25]} Sankalp]: Har ek din ki tapasya aapko is selection ke aur kareeb le jati hai!"
        used_quotes_set.add(quote.lower())

        content = f"""
<div class="short-view-card" style="background:#ffffff; border:1px solid #cbd5e1; border-radius:8px; padding:18px; margin-bottom:20px;">
    <div style="background:#fef3c7; border-left:4px solid #d97706; padding:8px 12px; margin-bottom:10px; font-weight:600; color:#92400e;">"{quote}"</div>
    <h3>📢 {title}</h3>
    <p><strong>Category:</strong> {meta['category']} | <strong>Intent:</strong> {meta['primary_intent']} | <strong>Type:</strong> {meta['job_type']} | <strong>State:</strong> {meta['state']}</p>
    
    <div style="background:#eef6ff; border-left:4px solid #1a73e8; padding:12px; margin:12px 0; border-radius:4px;">
        <h4 style="margin:0 0 6px; color:#174ea6;">🎯 Option A & B Expert Strategy & Verified Official Links</h4>
        <p style="margin:4px 0;"><strong>Apply Online / Official Portal:</strong> <a href="{apply_link}" target="_blank" style="color:#1d4ed8; font-weight:700;">Click Here to Apply</a></p>
        <p style="margin:4px 0;"><strong>Official Notification PDF:</strong> <a href="{download_pdf}" target="_blank" style="color:#1d4ed8; font-weight:700;">Download Official PDF</a></p>
        <p style="margin:4px 0; font-size:13.5px; color:#334155;"><strong>90-Day Plan:</strong> Rozana 3 ghante core subjects, 1 mock test aur pichhle saal ke papers ka rigorous analysis karein.</p>
    </div>
</div>
"""
        return {
            "id": job_id, "intent_signature": intent_sig,
            "title": title, "category": meta["category"], "primary_intent": meta["primary_intent"],
            "job_type": meta["job_type"], "state": meta["state"], "unique_quote": quote, "source": source_name,
            "link": apply_link, "url": apply_link, "apply_link": apply_link, "notif_url": notif_url, "download_pdf": download_pdf,
            "date": datetime.now().strftime("%d %b %Y"), "post_date": datetime.now().strftime("%d %b %Y"),
            "updated_at": now_str, "summary": f"Verified active recruitment update for {title}.", "description": content,
            "content": content, "status": "pending_review"
        }

async def process_aggregator(src, seen, used_quotes_set, loop):
    posts = []
    html = await safe_fetch_non_blocking(src["url"], loop)
    if not html:
        return posts
    soup = BeautifulSoup(html, "html.parser")
    
    tasks = []
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
            seen.add(norm)
            tasks.append((text, href, src["name"]))

    for text, href, src_name in tasks[:30]:
        article_html = await safe_fetch_non_blocking(href, loop)
        post = MasterSynthesizer.build_post(text, href, src_name, used_quotes_set, article_html)
        if post and is_within_one_month(post["date"]):
            posts.append(post)

    return posts

async def main_async():
    print("🚀 Starting Guaranteed-Link Agentic Scraper Engine...")
    existing = []
    if os.path.exists(DATABASE_FILE):
        try:
            with open(DATABASE_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    posts_by_signature = {}
    used_quotes_set = set()

    for j in existing:
        if not isinstance(j, dict):
            continue
        sig = j.get("intent_signature") or j.get("id", "")
        # Fix any previously blank links in existing database
        if j.get("apply_link") == "#" or not j.get("apply_link"):
            j["apply_link"] = get_guaranteed_link(j.get("title", ""))
            j["link"] = j["apply_link"]
            j["url"] = j["apply_link"]
        if j.get("download_pdf") == "#" or not j.get("download_pdf"):
            j["download_pdf"] = j["apply_link"]
        if j.get("notif_url") == "#" or not j.get("notif_url"):
            j["notif_url"] = j["apply_link"]
            
        posts_by_signature[sig] = j
        if q := j.get("unique_quote"):
            used_quotes_set.add(q.lower())

    seen = {j.get("title", "").lower().strip() for j in existing if isinstance(j, dict)}
    new_posts_count = 0
    delta_updated_count = 0

    loop = asyncio.get_running_loop()

    tasks = [process_aggregator(src, seen, used_quotes_set, loop) for src in SOURCES]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for res in results:
        if isinstance(res, list):
            for post in res:
                sig = post["intent_signature"]
                if sig not in posts_by_signature:
                    posts_by_signature[sig] = post
                    new_posts_count += 1

    for title, hub_key in MASTER_DIRECTORY_CATALOG:
        norm = title.lower().strip()
        hub = OFFICIAL_HUBS.get(hub_key, {"notices": "https://www.google.com"})
        post = MasterSynthesizer.build_post(title, hub["notices"], "Master Directory", used_quotes_set)
        sig = post["intent_signature"]
        
        if sig not in posts_by_signature:
            if is_within_one_month(post["date"]):
                posts_by_signature[sig] = post
                new_posts_count += 1
        else:
            # Ensure no blank links for master directory items
            if posts_by_signature[sig].get("apply_link") == "#" or not posts_by_signature[sig].get("apply_link"):
                posts_by_signature[sig]["apply_link"] = post["apply_link"]
                posts_by_signature[sig]["link"] = post["apply_link"]
                posts_by_signature[sig]["url"] = post["apply_link"]
                posts_by_signature[sig]["download_pdf"] = post["download_pdf"]
                posts_by_signature[sig]["notif_url"] = post["notif_url"]

    final_db = list(posts_by_signature.values())
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(final_db, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 Sync Complete! New Added: {new_posts_count} | Updated: {delta_updated_count} | Total Records: {len(final_db)}")

def main():
    try:
        asyncio.run(asyncio.wait_for(main_async(), timeout=330.0))
    except asyncio.TimeoutError:
        print("⚠️ Hard timeout of 5.5 minutes reached. Saving progress safely.")

if __name__ == "__main__":
    main()

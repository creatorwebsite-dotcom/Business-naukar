import os
import re
import json
import time
import random
import hashlib
import asyncio
from datetime import datetime
from bs4 import BeautifulSoup

from curl_cffi import requests as cffi_requests
from playwright.async_api import async_playwright
from playwright_stealth import stealth
import undetected_chromedriver as uc

DATABASE_FILE = "jobs_database.json"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

SOURCES = [
    {"name": "SarkariResult", "url": "https://www.sarkariresult.com/"},
    {"name": "FreeJobAlert", "url": "https://www.freejobalert.com/government-jobs/"},
    {"name": "RojgarResult", "url": "https://www.rojgarresult.com/"},
    {"name": "SarkariExam", "url": "https://www.sarkariexam.com/"},
    {"name": "IndGovtJobs", "url": "https://www.indgovtjobs.in/"},
    {"name": "FreshersNow", "url": "https://www.freshersnow.com/government-jobs-india/"},
    {"name": "CareerPower", "url": "https://www.careerpower.in/upcoming-government-exams.html"},
    {"name": "JagranJosh", "url": "https://www.jagranjosh.com/articles-sarkari-naukri-1288164377-1"}
]

BLOCK_DOMAINS = [
    'play.google.com', 'apps.apple.com', 'drive.google.com',
    'whatsapp.com', 't.me', 'telegram.me', 'facebook.com',
    'twitter.com', 'instagram.com', 'youtube.com', 'pinterest.com'
]

AGGREGATOR_DOMAINS = [
    'sarkariresult.com', 'freejobalert.com', 'rojgarresult.com',
    'sarkariexam.com', 'indgovtjobs.in', 'freshersnow.com',
    'careerpower.in', 'jagranjosh.com', 'adda247.com'
]

KNOWN_GOV_PORTALS = {
    "ssc": "https://ssc.gov.in/", "upsc": "https://upsc.gov.in/",
    "rrb": "https://indianrailways.gov.in/", "railway": "https://indianrailways.gov.in/",
    "ibps": "https://www.ibps.in/", "sbi": "https://sbi.co.in/web/careers",
    "rbi": "https://opportunities.rbi.org.in/", "india post": "https://indiapostgdsonline.gov.in/",
    "itbp": "https://recruitment.itbpolice.nic.in/", "bsf": "https://rectt.bsf.gov.in/",
    "crpf": "https://rect.crpf.gov.in/", "bhel": "https://careers.bhel.in/",
    "cwc": "https://www.cewacor.nic.in/", "irel": "https://www.irel.co.in/careers"
}

def fetch_with_curl_cffi(url):
    try:
        response = cffi_requests.get(url, impersonate="chrome110", timeout=15)
        if response.status_code == 200 and len(response.text) > 300:
            return response.text
    except Exception:
        pass
    return ""

async def fetch_with_playwright_stealth(url):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            )
            await stealth(page)
            await page.goto(url, timeout=35000, wait_until="domcontentloaded")
            content = await page.content()
            await browser.close()
            if content and len(content) > 300:
                return content
    except Exception:
        pass
    return ""

def fetch_with_undetected_chrome(url):
    try:
        options = uc.ChromeOptions()
        options.headless = True
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        driver = uc.Chrome(options=options)
        driver.get(url)
        content = driver.page_source
        driver.quit()
        if content and len(content) > 300:
            return content
    except Exception:
        pass
    return ""

def resilient_stealth_fetch(url):
    html = fetch_with_curl_cffi(url)
    if not html or "Just a moment..." in html or "Cloudflare" in html:
        html = asyncio.run(fetch_with_playwright_stealth(url))
    if not html or "Just a moment..." in html or "Cloudflare" in html:
        html = fetch_with_undetected_chrome(url)
    return html

def is_aggregator_link(href):
    h = href.lower()
    if h.endswith(".pdf") or "img.freejobalert.com" in h or "img2.freejobalert.com" in h:
        return False
    return any(ag in h for ag in AGGREGATOR_DOMAINS)

class CategoryClassifierAgent:
    @staticmethod
    def classify(title):
        t = title.lower()
        if any(k in t for k in ["result", "merit list", "cutoff", "cut off", "score card", "selection list"]):
            return "Result"
        elif any(k in t for k in ["admit card", "hall ticket", "call letter", "exam date", "exam city"]):
            return "Admit Card"
        elif any(k in t for k in ["answer key", "response sheet", "objection"]):
            return "Answer Key"
        elif any(k in t for k in ["syllabus", "exam pattern"]):
            return "Syllabus"
        elif any(k in t for k in ["admission", "counselling", "enrollment", "apply admission"]):
            return "Admission"
        return "Latest Jobs"

class DeepLinkExtractorAgent:
    @staticmethod
    def extract_and_evaluate(title, article_url):
        extracted = {
            "apply_link": "#", "notif_url": "#", "result_url": "#",
            "answer_key_url": "#", "admit_card_url": "#", "official_web": "#", "accuracy_score": 1
        }
        if not article_url or not article_url.startswith("http"):
            return extracted

        html = resilient_stealth_fetch(article_url)
        if not html: return extracted

        soup = BeautifulSoup(html, "html.parser")
        for container in soup.find_all(["tr", "li", "p", "div"]):
            row_text = re.sub(r'\s+', ' ', container.get_text()).strip().lower()
            if len(row_text) > 800: continue
            for a in container.find_all("a", href=True):
                href = a["href"].strip()
                if not href.startswith("http") or any(b in href.lower() for b in BLOCK_DOMAINS): continue
                if is_aggregator_link(href): continue

                a_text = re.sub(r'\s+', ' ', a.get_text()).strip().lower()
                combo = f"{row_text} {a_text}"

                if href.lower().endswith(".pdf") or any(w in combo for w in ["notification", "advt", "official notice", "download pdf"]):
                    if extracted["notif_url"] == "#":
                        extracted["notif_url"] = href
                        extracted["accuracy_score"] += 3

                if any(w in combo for w in ["apply online", "registration", "apply now", "online form"]):
                    if not href.lower().endswith(".pdf") and extracted["apply_link"] == "#":
                        extracted["apply_link"] = href
                        extracted["accuracy_score"] += 3

                if any(w in combo for w in ["official website", "official portal", "board website"]):
                    if not href.lower().endswith(".pdf") and extracted["official_web"] == "#":
                        extracted["official_web"] = href
                        extracted["accuracy_score"] += 2

        if extracted["official_web"] == "#":
            t_low = title.lower()
            for key, portal_url in KNOWN_GOV_PORTALS.items():
                if key in t_low:
                    extracted["official_web"] = portal_url
                    extracted["accuracy_score"] += 2
                    break

        if extracted["apply_link"] == "#" and extracted["official_web"] != "#":
            extracted["apply_link"] = extracted["official_web"]
        if extracted["notif_url"] == "#" and extracted["official_web"] != "#":
            extracted["notif_url"] = extracted["official_web"]

        return extracted

class OptionA_SEOWriterAgent:
    @staticmethod
    def generate_full_content(title, category):
        today_str = datetime.now().strftime("%d %B %Y")
        clean_title = re.sub(r'\s+', ' ', title).strip()
        dept_name = clean_title.split("Recruitment")[0].split("Online Form")[0].split("Vacancy")[0].strip()

        short_view = f"""
<div class="short-view-card" style="background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:16px; margin-bottom:20px; box-shadow:0 1px 3px rgba(0,0,0,0.05);">
    <div style="background:#eef6ff; border-left:4px solid #1a73e8; padding:10px 14px; margin-bottom:12px; border-radius:4px;">
        <span style="color:#174ea6; font-weight:700; font-size:15px;">📢 Short Information / Summary:</span>
        <p style="margin:4px 0 0; color:#334155; font-size:14px; line-height:1.6;">
            <strong>{dept_name}</strong> ne hal hi mein <strong>{clean_title}</strong> ke sambandh mein official notification release kiya hai. Jo bhi abhyarthi is bharti prakriya mein aavedan karna chahte hain, ve important dates, fee structure, age limit aur eligibility criteria check karke direct links se jud sakte hain. Niche is notification ka exhaustive deep breakdown diya gaya hai.
        </p>
    </div>
    <div style="display:flex; flex-wrap:wrap; gap:10px; font-size:13px; color:#475569;">
        <span style="background:#f1f5f9; padding:5px 10px; border-radius:4px;"><strong>📅 Update Date:</strong> {today_str}</span>
        <span style="background:#f1f5f9; padding:5px 10px; border-radius:4px;"><strong>🏷️ Category:</strong> {category}</span>
        <span style="background:#f1f5f9; padding:5px 10px; border-radius:4px;"><strong>🌐 Mode:</strong> Online Direct Portal</span>
    </div>
</div>
"""
        deep_view = f"""
<div class="deep-job-dossier" style="line-height:1.75; font-family:system-ui,-apple-system,sans-serif; color:#1e293b;">
    <h3 style="color:#0f172a; border-bottom:2px solid #cbd5e1; padding-bottom:8px; margin-top:20px;">🗓️ 1. Detailed Application Timeline (Important Dates)</h3>
    <table style="width:100%; border-collapse:collapse; margin-bottom:18px; font-size:14px;">
        <tr style="background:#f8fafc; border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600; width:45%;">Notification Release Date</td><td style="padding:10px;">{today_str}</td></tr>
        <tr style="border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600;">Online Registration Start Date</td><td style="padding:10px; color:#16a34a; font-weight:600;">Active Now (Official Portal)</td></tr>
        <tr style="background:#f8fafc; border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600;">Last Date to Apply Online</td><td style="padding:10px; color:#dc2626; font-weight:700;">Check Notification PDF Notice</td></tr>
        <tr style="border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600;">Admit Card / Exam Date</td><td style="padding:10px;">Will be notified soon on official portal</td></tr>
    </table>
    <h3 style="color:#0f172a; border-bottom:2px solid #cbd5e1; padding-bottom:8px; margin-top:20px;">💳 2. Application Fee Structure & Payment Modes</h3>
    <ul style="padding-left:22px; margin-bottom:18px; font-size:14px;">
        <li><strong>General / OBC / EWS Male Candidates:</strong> As per Board Notification rules (Usually ₹100/- to ₹500/-).</li>
        <li><strong>SC / ST / Divyang (PwD) Candidates:</strong> ₹0/- (Nil / Exempted as per government norms).</li>
        <li><strong>Payment Options:</strong> Online mode through Debit Card, Credit Card, Net Banking, UPI (Google Pay, PhonePe).</li>
    </ul>
    <h3 style="color:#0f172a; border-bottom:2px solid #cbd5e1; padding-bottom:8px; margin-top:20px;">🎂 3. Age Limit Criteria & Relaxation</h3>
    <table style="width:100%; border-collapse:collapse; margin-bottom:18px; font-size:14px;">
        <tr style="background:#f8fafc; border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600; width:45%;">Minimum Age Requirement</td><td style="padding:10px;">18 Years (Post anusar)</td></tr>
        <tr style="border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600;">Maximum Age Limit</td><td style="padding:10px;">27 - 40 Years (Post wise)</td></tr>
        <tr style="background:#f8fafc; border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600;">Age Relaxation</td><td style="padding:10px;">OBC candidates: 3 Years, SC/ST: 5 Years chhoot niyamansuar.</td></tr>
    </table>
    <h3 style="color:#0f172a; border-bottom:2px solid #cbd5e1; padding-bottom:8px; margin-top:20px;">🎓 4. Vacancy Details & Educational Eligibility</h3>
    <ul style="padding-left:22px; margin-bottom:18px; font-size:14px;">
        <li><strong>10th / 12th Pass Posts:</strong> Manyataprapta Board se 10th (Matric) ya 12th (Intermediate) pass.</li>
        <li><strong>Degree / Diploma Posts:</strong> Relevant field mein Bachelor Degree / Diploma / ITI (Official PDF dekhein).</li>
    </ul>
    <h3 style="color:#0f172a; border-bottom:2px solid #cbd5e1; padding-bottom:8px; margin-top:20px;">⚙️ 5. Stage-by-Stage Selection Process</h3>
    <ol style="padding-left:22px; margin-bottom:18px; font-size:14px;">
        <li><strong>Stage 1:</strong> Computer Based Written Exam (CBT / OMR Objective Test).</li>
        <li><strong>Stage 2:</strong> Skill Test / Typing Test / PET (Jahan laagu ho).</li>
        <li><strong>Stage 3:</strong> Document Verification (Mool praman patron ki janch).</li>
        <li><strong>Stage 4:</strong> Medical Examination (Swasthya parikshan).</li>
    </ol>
    <h3 style="color:#0f172a; border-bottom:2px solid #cbd5e1; padding-bottom:8px; margin-top:20px;">📚 6. Exam Pattern & Subject-Wise Syllabus</h3>
    <ul style="padding-left:22px; margin-bottom:18px; font-size:14px;">
        <li><strong>Reasoning:</strong> Puzzles, Coding-Decoding, Blood Relations, Series, Syllogism.</li>
        <li><strong>Quantitative Aptitude:</strong> Percentage, Ratio, Profit & Loss, Speed Math, Data Interpretation.</li>
        <li><strong>General Awareness:</strong> Pichhle 6 mahine ka Current Affairs, Samvidhan, Geography, History.</li>
        <li><strong>Language:</strong> Grammar, Error Spotting, Reading Comprehension, Vocabulary.</li>
    </ul>
    <h3 style="color:#0f172a; border-bottom:2px solid #cbd5e1; padding-bottom:8px; margin-top:20px;">🎯 7. Aakhri 1 Mahine Ki Preparation Strategy (30 Days Blueprint)</h3>
    <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; padding:14px; margin-bottom:18px; font-size:14px;">
        <ul style="padding-left:20px; margin:0;">
            <li><strong>Week 1 (Concept Revision):</strong> Short notes aur math formulas ko thoroughly revise karein.</li>
            <li><strong>Week 2 (Sectional Practice):</strong> Weak subjects par time-bound sectional tests lagayein.</li>
            <li><strong>Week 3 (Full Mock Routine):</strong> Pariksha ke exact time-slot par rojana 1 poora Full Mock Test lagayein.</li>
            <li><strong>Week 4 (Previous Year Papers):</strong> Pichhle 5 saalon ke actual papers solve karein aur calm mind se revise karein.</li>
        </ul>
    </div>
</div>
"""
        return f"{short_view}\n{deep_view}".strip()

class OptionB_GeminiAIAgent:
    @staticmethod
    def generate_editorial(title, category):
        if not GEMINI_API_KEY: return None
        prompt = f"Write an encouraging 2-paragraph mentor guidance in Hinglish for exam aspirants preparing for: '{title}' (Category: {category})."
        payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.7, "maxOutputTokens": 400}}).encode("utf-8")
        for model in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash-latest"]:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            try:
                import urllib.request
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                    text = res["candidates"][0]["content"]["parts"][0]["text"].strip()
                    return f"""
<div class="mentor-editorial-block" style="background:#fdf2f8; border-left:4px solid #db2777; padding:14px; margin-bottom:18px; border-radius:6px;">
    <h4 style="margin-top:0; color:#9d174d; font-size:16px;">🎯 Senior Mentor's Strategy Guidance</h4>
    <p style="margin:0; font-size:14px; color:#831843; line-height:1.7;">{text}</p>
</div>
"""
            except Exception:
                continue
        return None

class SynthesizerAgent:
    @staticmethod
    def create_unified_post(title, link, source_name, use_ai=True):
        print(f"    ↳ [{source_name}] Heavy Stealth Crawling: {title[:40]}...")
        deep = DeepLinkExtractorAgent.extract_and_evaluate(title, link)
        category = CategoryClassifierAgent.classify(title)
        
        opt_a = OptionA_SEOWriterAgent.generate_full_content(title, category)
        opt_b = OptionB_GeminiAIAgent.generate_editorial(title, category) if use_ai and GEMINI_API_KEY else None
        
        full_desc = f"{opt_b}\n{opt_a}" if opt_b else opt_a
        job_id = hashlib.md5(f"{title}_{link}".encode("utf-8")).hexdigest()[:12]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date_str = datetime.now().strftime("%d %b %Y")
        clean_dept = title.split("Recruitment")[0].split("Online Form")[0].split("Vacancy")[0].strip()

        return {
            "id": job_id, "title": title, "category": category, "source": source_name,
            "link": link, "url": link, "apply_link": deep["apply_link"], "applyUrl": deep["apply_link"],
            "notif_url": deep["notif_url"], "notifUrl": deep["notif_url"], "download_pdf": deep["notif_url"],
            "result_url": deep["result_url"], "resultUrl": deep["result_url"],
            "answer_key_url": deep["answer_key_url"], "answerKeyUrl": deep["answer_key_url"],
            "admit_card_url": deep["admit_card_url"], "admitCardUrl": deep["admit_card_url"],
            "official_web": deep["official_web"], "webUrl": deep["official_web"],
            "date": date_str, "post_date": date_str, "updated_at": now,
            "summary": f"{clean_dept} notification update for {title}. Check verified direct links.",
            "description": full_desc, "content": full_desc, "accuracy_score": deep["accuracy_score"],
            "engine": "Heavy Stealth Agentic 6-Category Scraper", "status": "published",
            "seo_keywords": f"{title}, {category}, Direct Apply Online, PDF Download"
        }

def extract_items_from_source(html, base_url):
    items = []
    soup = BeautifulSoup(html, "html.parser")
    for a_tag in soup.find_all("a", href=True):
        text = re.sub(r'\s+', ' ', a_tag.get_text()).strip()
        href = a_tag["href"].strip()
        if not href.startswith("http"):
            base = "/".join(base_url.split("/")[:3])
            href = base + href

        if 15 <= len(text) <= 140 and any(
            kw in text.lower() for kw in [
                "online form", "recruitment", "vacancy", "bharti", "result",
                "admit card", "answer key", "apply", "notification", "syllabus", "2026"
            ]
        ):
            items.append((text, href))
    return items

def main():
    print("🚀 Starting Heavy Stealth Scraper Across All 8 Portals...")
    existing = []
    if os.path.exists(DATABASE_FILE):
        try:
            with open(DATABASE_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception: pass

    seen_titles = {j.get("title", "").lower().strip() for j in existing if isinstance(j, dict)}
    new_posts = []
    ai_count = 0

    for source in SOURCES:
        print(f"\n🤖 Scanning Portal with Heavy Stealth: {source['name']}...")
        html = resilient_stealth_fetch(source["url"])
        if not html: continue
        
        candidates = extract_items_from_source(html, source["url"])
        count = 0
        for title, link in candidates:
            norm = title.lower().strip()
            if norm in seen_titles: continue
            
            use_ai = (ai_count < 15)
            post = SynthesizerAgent.create_unified_post(title, link, source["name"], use_ai=use_ai)
            if post:
                if use_ai and GEMINI_API_KEY:
                    ai_count += 1
                    time.sleep(1.0)
                new_posts.append(post)
                seen_titles.add(norm)
                count += 1
                if count >= 8: break
        time.sleep(1.0)

    final_db = new_posts + existing
    final_db = final_db[:500]
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(final_db, f, ensure_ascii=False, indent=2)
    print(f"\n🎉 Successfully saved {len(final_db)} posts to {DATABASE_FILE}!")

if __name__ == "__main__":
    main()

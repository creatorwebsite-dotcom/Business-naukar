import os
import re
import json
import time
import random
import hashlib
import asyncio
from datetime import datetime
from bs4 import BeautifulSoup

# Advanced Anti-Block Libraries
from curl_cffi import requests as cffi_requests
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

DATABASE_FILE = "jobs_database.json"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# ALL 8 MANDATORY RECRUITMENT PORTALS
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

# =====================================================================
# HYBRID NETWORK FETCH ENGINE (curl_cffi + Playwright Stealth)
# =====================================================================
def fetch_with_curl_cffi(url):
    """Fast static fetching using real Chrome TLS fingerprinting"""
    try:
        response = cffi_requests.get(url, impersonate="chrome110", timeout=15)
        if response.status_code == 200 and len(response.text) > 300:
            return response.text
    except Exception:
        pass
    return ""

async def fetch_with_playwright_stealth(url):
    """Heavy dynamic rendering & Cloudflare bypass using Playwright + Stealth"""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            )
            await stealth_async(page)
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            content = await page.content()
            await browser.close()
            if content and len(content) > 300:
                return content
    except Exception:
        pass
    return ""

def resilient_fetch(url):
    """Primary curl_cffi try, fallback to Playwright Stealth if blocked"""
    html = fetch_with_curl_cffi(url)
    if not html or "Just a moment..." in html or "Cloudflare" in html:
        print(f"      ↳ Static fetch blocked/empty. Switching to Playwright Stealth Engine for: {url}")
        html = asyncio.run(fetch_with_playwright_stealth(url))
    return html

def is_aggregator_link(href):
    h = href.lower()
    if h.endswith(".pdf") or "img.freejobalert.com" in h or "img2.freejobalert.com" in h:
        return False
    return any(ag in h for ag in AGGREGATOR_DOMAINS)

# =====================================================================
# AGENT 1: SMART CATEGORY CLASSIFIER
# =====================================================================
class CategoryClassifierAgent:
    @staticmethod
    def classify(title):
        t = title.lower()
        if any(k in t for k in ["result", "merit list", "cutoff", "score card"]):
            return "Result"
        elif any(k in t for k in ["admit card", "hall ticket", "call letter", "exam date"]):
            return "Admit Card"
        elif any(k in t for k in ["answer key", "response sheet", "objection"]):
            return "Answer Key"
        elif any(k in t for k in ["syllabus", "exam pattern"]):
            return "Syllabus"
        return "Latest Jobs"

# =====================================================================
# AGENT 2: DEEP OFFICIAL LINK & PDF EXTRACTOR AGENT
# =====================================================================
class DeepLinkExtractorAgent:
    @staticmethod
    def extract_and_evaluate(article_url):
        extracted = {
            "apply_link": "#",
            "notif_url": "#",
            "result_url": "#",
            "answer_key_url": "#",
            "admit_card_url": "#",
            "official_web": "#",
            "accuracy_score": 1
        }

        if not article_url or not article_url.startswith("http"):
            return extracted

        html = resilient_fetch(article_url)
        if not html:
            return extracted

        soup = BeautifulSoup(html, "html.parser")

        for container in soup.find_all(["tr", "li", "p", "div"]):
            row_text = re.sub(r'\s+', ' ', container.get_text()).strip().lower()
            if len(row_text) > 800:
                continue
            for a in container.find_all("a", href=True):
                href = a["href"].strip()
                if not href.startswith("http") or any(b in href.lower() for b in BLOCK_DOMAINS):
                    continue
                if is_aggregator_link(href):
                    continue

                a_text = re.sub(r'\s+', ' ', a.get_text()).strip().lower()
                combo = f"{row_text} {a_text}"

                if href.lower().endswith(".pdf") or any(w in combo for w in ["notification", "advt", "notice", "download pdf"]):
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

        if extracted["apply_link"] == "#" and extracted["official_web"] != "#":
            extracted["apply_link"] = extracted["official_web"]
        if extracted["notif_url"] == "#" and extracted["official_web"] != "#":
            extracted["notif_url"] = extracted["official_web"]

        return extracted

# =====================================================================
# AGENT 3: OPTION A - SHORT VIEW + EXHAUSTIVE DEEP DOSSIER
# =====================================================================
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

# =====================================================================
# AGENT 4: OPTION B - GEMINI AI COUNSELOR ENGINE
# =====================================================================
class OptionB_GeminiAIAgent:
    @staticmethod
    def generate_editorial(title, category):
        if not GEMINI_API_KEY:
            return None

        prompt = (
            f"You are an expert Indian competitive exam mentor. "
            f"Write an authentic, encouraging 2-paragraph editorial guidance piece in Hinglish "
            f"for candidates preparing for: '{title}' (Category: {category}). "
            f"Paragraph 1 should highlight career significance and reality. "
            f"Paragraph 2 should give practical study tips to avoid silly mistakes. "
            f"Do not use bullet points."
        )

        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 400}
        }).encode("utf-8")

        for model_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash-latest"]:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, context=ssl_context, timeout=12) as response:
                    res_data = json.loads(response.read().decode("utf-8"))
                    candidates = res_data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts and "text" in parts[0]:
                            editorial_text = parts[0]["text"].strip()
                            return f"""
<div class="mentor-editorial-block" style="background:#fdf2f8; border-left:4px solid #db2777; padding:14px; margin-bottom:18px; border-radius:6px;">
    <h4 style="margin-top:0; color:#9d174d; font-size:16px;">🎯 Senior Mentor's Strategy Guidance</h4>
    <p style="margin:0; font-size:14px; color:#831843; line-height:1.7;">{editorial_text}</p>
</div>
"""
            except Exception:
                continue
        return None

# =====================================================================
# AGENT 5: SYNTHESIZER
# =====================================================================
class SynthesizerAgent:
    @staticmethod
    def create_unified_post(title, link, source_name, use_ai=True):
        print(f"    ↳ [{source_name}] Deep Crawling Official Links: {title[:40]}...")
        deep = DeepLinkExtractorAgent.extract_and_evaluate(link)

        category = CategoryClassifierAgent.classify(title)
        option_a_html = OptionA_SEOWriterAgent.generate_full_content(title, category)
        option_b_html = None

        if use_ai and GEMINI_API_KEY:
            option_b_html = OptionB_GeminiAIAgent.generate_editorial(title, category)

        full_description = f"{option_b_html}\n{option_a_html}" if option_b_html else option_a_html

        job_id = hashlib.md5(f"{title}_{link}".encode("utf-8")).hexdigest()[:12]
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date_display = datetime.now().strftime("%d %b %Y")

        clean_dept = title.split("Recruitment")[0].split("Online Form")[0].split("Vacancy")[0].strip()
        short_summary_text = f"{clean_dept} has officially released the notification update for {title}. Check key dates, age limit, syllabus and verified direct links."

        return {
            "id": job_id,
            "title": title,
            "category": category,
            "source": source_name,
            "link": link,
            "url": link,
            "apply_link": deep["apply_link"],
            "applyUrl": deep["apply_link"],
            "notif_url": deep["notif_url"],
            "notifUrl": deep["notif_url"],
            "download_pdf": deep["notif_url"],
            "result_url": deep["result_url"],
            "resultUrl": deep["result_url"],
            "answer_key_url": deep["answer_key_url"],
            "answerKeyUrl": deep["answer_key_url"],
            "admit_card_url": deep["admit_card_url"],
            "admitCardUrl": deep["admit_card_url"],
            "official_web": deep["official_web"],
            "webUrl": deep["official_web"],
            "date": date_display,
            "post_date": date_display,
            "updated_at": now_iso,
            "summary": short_summary_text,
            "description": full_description,
            "content": full_description,
            "accuracy_score": deep["accuracy_score"],
            "engine": "Agentic Hybrid (Option B Gemini AI + Option A Short & Deep Dossier)",
            "status": "published",
            "seo_keywords": f"{title}, {category}, Sarkari Result, Direct Apply Online, PDF Download, Syllabus, 1 Month Strategy"
        }

# =====================================================================
# AGENT 6: SCANNER (ALL 8 PORTALS RESILIENT)
# =====================================================================
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
    print("🚀 Starting Hybrid Stealth Scraper Across ALL 8 Portals...")
    existing_database = []
    if os.path.exists(DATABASE_FILE):
        try:
            with open(DATABASE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    existing_database = data
        except Exception:
            existing_database = []

    existing_titles = {j.get("title", "").lower().strip() for j in existing_database if isinstance(j, dict)}

    new_posts = []
    ai_calls_count = 0
    MAX_AI_CALLS_PER_RUN = 16

    for source in SOURCES:
        print(f"\n🤖 [Scanner Agent] Scanning Portal: {source['name']}...")
        html = resilient_fetch(source["url"])
        candidates = extract_items_from_source(html, source["url"]) if html else []
        
        for title, link in candidates[:10]:
            norm_title = title.lower().strip()
            if norm_title in existing_titles:
                continue

            use_ai_now = (ai_calls_count < MAX_AI_CALLS_PER_RUN)
            post_entry = SynthesizerAgent.create_unified_post(title, link, source["name"], use_ai=use_ai_now)
            if post_entry:
                if use_ai_now and GEMINI_API_KEY:
                    ai_calls_count += 1
                    time.sleep(1.0)
                new_posts.append(post_entry)
                existing_titles.add(norm_title)

        time.sleep(1.0)

    print(f"\n✅ Total Verified Posts Harvested: {len(new_posts)}")
    final_database = new_posts + existing_database
    final_database = final_database[:500]

    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(final_database, f, ensure_ascii=False, indent=2)

    print(f"🎉 Successfully saved {len(final_database)} posts to {DATABASE_FILE}!")

if __name__ == "__main__":
    main()

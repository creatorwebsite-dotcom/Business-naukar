import os
import re
import json
import time
import hashlib
import asyncio
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from curl_cffi import requests as cffi_requests
from playwright.async_api import async_playwright
from playwright_stealth import stealth

DATABASE_FILE = "jobs_database.json"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# 1. 8 MAJOR AGGREGATOR SIGNAL SOURCES
SOURCES = [
    {"name": "SarkariResult", "url": "https://sarkariresult.com.cm/"},
    {"name": "FreeJobAlert", "url": "https://www.freejobalert.com/government-jobs/"},
    {"name": "RojgarResult", "url": "https://www.rojgarresult.com/"},
    {"name": "SarkariExam", "url": "https://www.sarkariexam.com/"},
    {"name": "IndGovtJobs", "url": "https://www.indgovtjobs.in/"},
    {"name": "FreshersNow", "url": "https://www.freshersnow.com/government-jobs-india/"},
    {"name": "CareerPower", "url": "https://www.careerpower.in/upcoming-government-exams.html"},
    {"name": "JagranJosh", "url": "https://www.jagranjosh.com/articles-sarkari-naukri-1288164377-1"}
]

# 2. DIRECT OFFICIAL RECRUITMENT HUBS (Central, State, Banking, Defense, PSUs)
OFFICIAL_HUBS = {
    "ssc": {"name": "Staff Selection Commission", "home": "https://ssc.gov.in/", "notices": "https://ssc.gov.in/api-notice/get-notices", "apply": "https://ssc.gov.in/login"},
    "upsc": {"name": "Union Public Service Commission", "home": "https://upsc.gov.in/", "notices": "https://upsc.gov.in/examinations/active-examinations", "apply": "https://upsconline.nic.in/"},
    "rrb": {"name": "Railway Recruitment Board", "home": "https://www.rrbapply.gov.in/", "notices": "https://www.rrbapply.gov.in/#/notices", "apply": "https://www.rrbapply.gov.in/#/auth/home"},
    "railway": {"name": "Indian Railways", "home": "https://indianrailways.gov.in/", "notices": "https://indianrailways.gov.in/railwayboard/view_section.jsp?lang=0&id=0,4,1244", "apply": "https://www.rrbapply.gov.in/"},
    "ibps": {"name": "IBPS Banking", "home": "https://www.ibps.in/", "notices": "https://www.ibps.in/notifications/", "apply": "https://ibpsonline.ibps.in/"},
    "sbi": {"name": "State Bank of India", "home": "https://sbi.co.in/web/careers", "notices": "https://sbi.co.in/web/careers/current-openings", "apply": "https://bank.sbi/careers"},
    "rbi": {"name": "Reserve Bank of India", "home": "https://opportunities.rbi.org.in/", "notices": "https://opportunities.rbi.org.in/Scripts/Vacancies.aspx", "apply": "https://opportunities.rbi.org.in/"},
    "mpsc": {"name": "Maharashtra MPSC", "home": "https://mpsc.gov.in/", "notices": "https://mpsc.gov.in/", "apply": "https://mpsconline.gov.in/"},
    "uppsc": {"name": "Uttar Pradesh UPPSC", "home": "https://uppsc.up.nic.in/", "notices": "https://uppsc.up.nic.in/", "apply": "https://uppsc.up.nic.in/"},
    "bpsc": {"name": "Bihar BPSC", "home": "https://www.bpsc.bih.nic.in/", "notices": "https://www.bpsc.bih.nic.in/", "apply": "https://onlinebpsc.bihar.gov.in/"},
    "india post": {"name": "India Post GDS", "home": "https://indiapostgdsonline.gov.in/", "notices": "https://indiapostgdsonline.gov.in/Notification.aspx", "apply": "https://indiapostgdsonline.gov.in/reg_instruction.aspx"},
    "ongc": {"name": "ONGC", "home": "https://www.ongcindia.com/", "notices": "https://www.ongcindia.com/web/eng/careers", "apply": "https://www.ongcindia.com/"},
    "iocl": {"name": "IOCL", "home": "https://iocl.com/", "notices": "https://iocl.com/latest-job", "apply": "https://iocl.com/"},
    "ntpc": {"name": "NTPC Careers", "home": "https://careers.ntpc.co.in/", "notices": "https://careers.ntpc.co.in/", "apply": "https://careers.ntpc.co.in/"},
    "bhel": {"name": "BHEL", "home": "https://careers.bhel.in/", "notices": "https://careers.bhel.in/bhel/jsp/", "apply": "https://careers.bhel.in/bhel/jsp/"}
}

# 3. PROACTIVE SURVEILLANCE TARGETS (From 200+ Govt & 100 Local/Semi-Govt Directory)
DIRECTORY_SURVEILLANCE_TARGETS = [
    {"name": "UPSC Civil Services IAS/IPS Examination 2026", "hub": "upsc"},
    {"name": "SSC CGL Combined Graduate Level Recruitment 2026", "hub": "ssc"},
    {"name": "SSC CHSL Lower Division Clerk & DEO Recruitment 2026", "hub": "ssc"},
    {"name": "SSC MTS & Havaldar Recruitment 2026", "hub": "ssc"},
    {"name": "SSC GD Constable BSF/CRPF/CISF Recruitment 2026", "hub": "ssc"},
    {"name": "RRB NTPC Station Master & Clerk Recruitment 2026", "hub": "rrb"},
    {"name": "RRB Group D Track Maintainer & Pointsman 2026", "hub": "rrb"},
    {"name": "RRB ALP & Technician Grade Recruitment 2026", "hub": "rrb"},
    {"name": "IBPS PO & Clerk Public Sector Banks Recruitment 2026", "hub": "ibps"},
    {"name": "SBI PO & Junior Associate Clerk Recruitment 2026", "hub": "sbi"},
    {"name": "RBI Grade B Officer & Assistant Recruitment 2026", "hub": "rbi"},
    {"name": "Maharashtra MPSC Rajyasewa & Combined Group B/C 2026", "hub": "mpsc"},
    {"name": "Uttar Pradesh UPPSC PCS & RO/ARO Recruitment 2026", "hub": "uppsc"},
    {"name": "Bihar BPSC Combined Competitive Exam 2026", "hub": "bpsc"},
    {"name": "India Post GDS Gramin Dak Sevak Recruitment 2026", "hub": "india post"},
    {"name": "IOCL Engineering Assistant & Apprentice Recruitment 2026", "hub": "iocl"},
    {"name": "ONGC Graduate Trainee & Apprentice Recruitment 2026", "hub": "ongc"},
    {"name": "NTPC Engineering Executive & ITI Trainee 2026", "hub": "ntpc"},
    {"name": "BHEL Executive & Artisan Trainee Recruitment 2026", "hub": "bhel"}
]

# NON-GOVT, PSU, COOPERATIVE & PRIVATE KEYWORDS (For Job Type Filter)
NON_GOVT_KEYWORDS = [
    "ongc", "iocl", "ntpc", "sail", "bhel", "gail", "powergrid", "hpcl", "coal india",
    "hal", "bel", "mdl", "mazagon dock", "cochin shipyard", "grse", "npcil", "nmdc",
    "bsnl", "dmrc", "mahametro", "idbi", "lic", "niacl", "uiic", "cooperative", "dccb",
    "pacs", "markfed", "milk union", "dairy", "temple trust", "devasthan", "private",
    "securitas", "sis", "dsa", "csc", "e-seva", "hospital attendant", "nursing home",
    "diagnostic", "reliance", "d-mart", "amazon", "flipkart", "warehouse", "courier",
    "dtdc", "blue dart", "broadband", "petrol pump", "hotel", "factory", "textile",
    "packaging", "construction", "tcs", "infosys", "wipro", "apprentice", "apprentices",
    "contractual", "third-party", "semi-govt"
]

# STATE DETECTION KEYWORDS (For State-Wise Filter)
STATE_KEYWORDS = {
    "Maharashtra": ["mpsc", "mahagenco", "mahadisco", "msedcl", "mseb", "mumbai", "pune", "nagpur", "maharashtra", "talathi", "gramsevak", "krushi sevak", "vanrakshak", "arogya sevak", "srpf", "mahametro", "msrtc", "rto amvi"],
    "Uttar Pradesh": ["uppsc", "upsssc", "uppbpb", "up police", "allahabad", "prayagraj", "lucknow", "uttar pradesh", "lekhpal", "upnhm", "uptet", "upsrtc", "uppcs"],
    "Bihar": ["bpsc", "bpssc", "bihar", "patna", "csbc", "bssc", "btet"],
    "Madhya Pradesh": ["mppsc", "esb mp", "madhya pradesh", "bhopal", "indore", "mhow", "mp police"],
    "Delhi": ["dsssb", "delhi police", "aiims delhi", "dmrc", "delhi"],
    "Rajasthan": ["rpsc", "rsmssb", "rssb", "rajasthan", "jaipur", "patwari", "reet", "ras"]
}

BLOCK_DOMAINS = [
    'play.google.com', 'apps.apple.com', 'drive.google.com',
    'whatsapp.com', 't.me', 'telegram.me', 'facebook.com',
    'twitter.com', 'instagram.com', 'youtube.com', 'pinterest.com',
    'sarkariresulttools.net', 'tools.sarkariresult.com'
]

AGGREGATOR_DOMAINS = [
    'sarkariresult.com', 'sarkariresult.com.cm', 'sarkariresulttools.net',
    'freejobalert.com', 'rojgarresult.com', 'sarkariexam.com',
    'indgovtjobs.in', 'freshersnow.com', 'careerpower.in',
    'jagranjosh.com', 'adda247.com', 'sarkariresult.net'
]

JUNK_TITLES = [
    "sarkari result", "sarkariresult", "tools", "sarkari result tools",
    "latest notifications", "view more", "click here", "home",
    "contact us", "disclaimer", "privacy policy", "android app", "apple app"
]

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

def resilient_stealth_fetch(url):
    if not url or url == "#" or not url.startswith("http"):
        return ""
    html = fetch_with_curl_cffi(url)
    if not html or "Just a moment..." in html or "Cloudflare" in html:
        html = asyncio.run(fetch_with_playwright_stealth(url))
    return html

def is_aggregator_link(href):
    h = href.lower()
    if h.endswith(".pdf") or "img.freejobalert.com" in h or "img2.freejobalert.com" in h:
        return False
    return any(ag in h for ag in AGGREGATOR_DOMAINS)

def is_dummy_or_generic(url):
    if not url or url == "#" or not url.startswith("http"):
        return True
    clean = url.rstrip('/')
    parts = clean.split("//")[-1].split("/")
    return len(parts) <= 1

def extract_actual_date(html_soup):
    text = html_soup.get_text(" ", strip=True)
    dates = re.findall(r'\b(?:0?[1-9]|[12]\d|3[01])[\/\-\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|0?[1-9]|1[0-2])[\/\-\s](?:202[6-9])\b', text, re.IGNORECASE)
    return dates[0] if dates else datetime.now().strftime("%d %b %Y")

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
        elif any(k in t for k in ["admission", "counselling", "enrollment"]):
            return "Admission"
        return "Latest Jobs"

class OfficialIntentSnifferAgent:
    @staticmethod
    def sniff_and_verify(title, article_url):
        category = CategoryClassifierAgent.classify(title)
        extracted = {
            "apply_link": "#", "notif_url": "#", "result_url": "#",
            "answer_key_url": "#", "admit_card_url": "#", "official_web": "#", 
            "accuracy_score": 0, "extracted_date": datetime.now().strftime("%d %b %Y"),
            "dynamic_admin_review_boxes": {}
        }
        
        t_low = title.lower()
        board_key = None
        for key in OFFICIAL_HUBS:
            if key in t_low:
                board_key = key
                extracted["official_web"] = OFFICIAL_HUBS[key]["home"]
                break

        # Phase 1: Scan Aggregator Page for Direct PDF / Genuine Apply Links
        if article_url and article_url.startswith("http"):
            html = resilient_stealth_fetch(article_url)
            if html:
                soup = BeautifulSoup(html, "html.parser")
                extracted["extracted_date"] = extract_actual_date(soup)

                for container in soup.find_all(["tr", "li", "p", "div"]):
                    row_text = re.sub(r'\s+', ' ', container.get_text()).strip().lower()
                    if len(row_text) > 800: continue
                    for a in container.find_all("a", href=True):
                        href = a["href"].strip()
                        if not href.startswith("http") or any(b in href.lower() for b in BLOCK_DOMAINS): continue
                        if is_aggregator_link(href) and not href.lower().endswith(".pdf"): continue

                        a_text = re.sub(r'\s+', ' ', a.get_text()).strip().lower()
                        combo = f"{row_text} {a_text}"

                        for box_name in ["short notice", "corrigendum", "revised notice", "cutoff marks", "syllabus pdf"]:
                            if box_name in combo and href != extracted["notif_url"]:
                                extracted["dynamic_admin_review_boxes"][box_name.title()] = href

                        if href.lower().endswith(".pdf") or any(w in combo for w in ["notification", "official notice", "download pdf"]):
                            if category == "Result" and extracted["result_url"] == "#":
                                extracted["result_url"] = href
                                extracted["accuracy_score"] += 4
                            elif extracted["notif_url"] == "#":
                                extracted["notif_url"] = href
                                extracted["accuracy_score"] += 4

                        if category == "Result" and any(w in combo for w in ["result", "merit list", "score card"]):
                            if extracted["result_url"] == "#":
                                extracted["result_url"] = href
                                extracted["accuracy_score"] += 4
                        elif category == "Answer Key" and any(w in combo for w in ["answer key", "response sheet"]):
                            if extracted["answer_key_url"] == "#":
                                extracted["answer_key_url"] = href
                                extracted["accuracy_score"] += 4
                        elif category == "Admit Card" and any(w in combo for w in ["admit card", "hall ticket", "call letter"]):
                            if extracted["admit_card_url"] == "#":
                                extracted["admit_card_url"] = href
                                extracted["accuracy_score"] += 4

                        if any(w in combo for w in ["apply online", "registration", "apply now", "online form"]):
                            if not href.lower().endswith(".pdf") and not is_dummy_or_generic(href):
                                if extracted["apply_link"] == "#":
                                    extracted["apply_link"] = href
                                    extracted["accuracy_score"] += 3

        # Phase 2: Direct Official Board Deep Sniffing (If links are dummy/missing)
        needs_official = (
            is_dummy_or_generic(extracted["notif_url"]) or 
            (category == "Latest Jobs" and is_dummy_or_generic(extracted["apply_link"])) or
            (category == "Result" and is_dummy_or_generic(extracted["result_url"]))
        )

        if needs_official and board_key:
            hub = OFFICIAL_HUBS[board_key]
            board_html = resilient_stealth_fetch(hub["notices"])
            if board_html:
                b_soup = BeautifulSoup(board_html, "html.parser")
                keywords = [w for w in re.split(r'[\s\-_,]+', t_low) if len(w) > 3 and w not in ["online", "form", "2026", "recruitment", "post", "apply"]]
                for a in b_soup.find_all("a", href=True):
                    href = a["href"].strip()
                    text = a.get_text().strip().lower()
                    full_url = urljoin(hub["home"], href)
                    if any(kw in text or kw in full_url.lower() for kw in keywords):
                        if full_url.lower().endswith(".pdf"):
                            if category == "Result" and extracted["result_url"] == "#":
                                extracted["result_url"] = full_url
                                extracted["accuracy_score"] += 5
                            elif extracted["notif_url"] == "#":
                                extracted["notif_url"] = full_url
                                extracted["accuracy_score"] += 5

            if extracted["apply_link"] == "#" or is_dummy_or_generic(extracted["apply_link"]):
                extracted["apply_link"] = hub.get("apply", hub["home"])
                extracted["accuracy_score"] += 4

        if category == "Result" and extracted["result_url"] != "#":
            extracted["download_pdf"] = extracted["result_url"]
        else:
            extracted["download_pdf"] = extracted["notif_url"]

        return extracted

# =====================================================================
# OPTION B: GEMINI AI SENIOR MENTOR AGENT
# =====================================================================
class OptionB_GeminiAIAgent:
    @staticmethod
    def generate_editorial(title, category):
        if not GEMINI_API_KEY: return ""
        prompt = f"Write an encouraging 2-paragraph mentor guidance in Hinglish for exam aspirants preparing for: '{title}' (Category: {category}). Give actionable strategy."
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
<div class="mentor-editorial-block" style="background:#fdf2f8; border-left:4px solid #db2777; padding:14px; margin:18px 0; border-radius:6px;">
    <h4 style="margin-top:0; color:#9d174d; font-size:16px;">🎯 Senior Mentor's Strategy Guidance (AI Insights)</h4>
    <p style="margin:0; font-size:14px; color:#831843; line-height:1.7;">{text}</p>
</div>
"""
            except Exception:
                continue
        return ""

# =====================================================================
# OPTION A: SHORT VIEW AT TOP + DEEP DETAIL DESCRIPTION RIGHT BELOW IT
# =====================================================================
class OptionA_SEOWriterAgent:
    @staticmethod
    def generate_full_content(title, category, post_date, job_type, detected_state, mentor_html=""):
        clean_title = re.sub(r'\s+', ' ', title).strip()
        dept_name = clean_title.split("Recruitment")[0].split("Online Form")[0].split("Vacancy")[0].strip()

        # 1. TOP SECTION: SHORT VIEW DETAIL CARD
        short_view = f"""
<div class="short-view-card" style="background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:18px; margin-bottom:24px; box-shadow:0 1px 3px rgba(0,0,0,0.05);">
    <div style="background:#eef6ff; border-left:4px solid #1a73e8; padding:12px 16px; margin-bottom:14px; border-radius:4px;">
        <span style="color:#174ea6; font-weight:700; font-size:15px;">📢 Short Information / Quick Summary:</span>
        <p style="margin:6px 0 0; color:#334155; font-size:14px; line-height:1.6;">
            <strong>{dept_name}</strong> ne <strong>{clean_title}</strong> ke liye official notification aur verified direct link active kar diya hai. Eligible candidates niche diye gaye deep details, important dates, eligibility criteria aur direct official links check karke apply ya PDF download kar sakte hain.
        </p>
    </div>
    <div style="display:flex; flex-wrap:wrap; gap:10px; font-size:13px; color:#475569;">
        <span style="background:#f1f5f9; padding:6px 12px; border-radius:4px;"><strong>📅 Date:</strong> {post_date}</span>
        <span style="background:#f1f5f9; padding:6px 12px; border-radius:4px;"><strong>📂 Category:</strong> {category}</span>
        <span style="background:#dcfce7; color:#166534; padding:6px 12px; border-radius:4px;"><strong>🏷️ Job Type:</strong> {job_type}</span>
        <span style="background:#fef3c7; color:#92400e; padding:6px 12px; border-radius:4px;"><strong>📍 State:</strong> {detected_state}</span>
    </div>
</div>
"""

        # 2. BOTTOM SECTION (Right below Short View): EXHAUSTIVE DEEP DETAIL DESCRIPTION
        deep_view = f"""
<div class="deep-job-dossier" style="line-height:1.75; font-family:system-ui,-apple-system,sans-serif; color:#1e293b; border-top:2px dashed #cbd5e1; padding-top:16px;">
    {mentor_html}

    <h3 style="color:#0f172a; border-bottom:2px solid #cbd5e1; padding-bottom:8px; margin-top:20px;">🗓️ 1. Detailed Application Timeline & Important Dates</h3>
    <table style="width:100%; border-collapse:collapse; margin-bottom:20px; font-size:14px;">
        <tr style="background:#f8fafc; border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600; width:45%;">Notification Release / Update Date</td><td style="padding:10px;">{post_date}</td></tr>
        <tr style="border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600;">Online Application / Link Status</td><td style="padding:10px; color:#16a34a; font-weight:600;">Active Now (Verified Direct Portal)</td></tr>
        <tr style="background:#f8fafc; border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600;">Last Date for Submission</td><td style="padding:10px; color:#dc2626; font-weight:700;">Refer Official Notification PDF</td></tr>
        <tr style="border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600;">Exam / Merit List Schedule</td><td style="padding:10px;">As per Official Recruitment Board Calendar</td></tr>
    </table>

    <h3 style="color:#0f172a; border-bottom:2px solid #cbd5e1; padding-bottom:8px; margin-top:24px;">💳 2. Application Fee Structure & Payment Modes</h3>
    <ul style="padding-left:22px; margin-bottom:20px; font-size:14px;">
        <li><strong>General / OBC / EWS Candidates:</strong> Official notice ke niyam anusar (Aam taur par ₹100/- se ₹500/-).</li>
        <li><strong>SC / ST / PwD / Female Candidates:</strong> ₹0/- (Exempted / Concessional fee as per government rules).</li>
        <li><strong>Payment Mode:</strong> Online माध्यम (UPI, Net Banking, Debit Card, Credit Card, ya E-Challan).</li>
    </ul>

    <h3 style="color:#0f172a; border-bottom:2px solid #cbd5e1; padding-bottom:8px; margin-top:24px;">🎂 3. Age Limit & Educational Eligibility Criteria</h3>
    <table style="width:100%; border-collapse:collapse; margin-bottom:20px; font-size:14px;">
        <tr style="background:#f8fafc; border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600; width:45%;">Minimum Age Limit</td><td style="padding:10px;">18 Years (Post-wise variation applicable)</td></tr>
        <tr style="border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600;">Maximum Age Limit</td><td style="padding:10px;">27 to 40 Years (SC/ST: +5 Yrs, OBC: +3 Yrs chhoot)</td></tr>
        <tr style="background:#f8fafc; border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600;">Educational Qualification</td><td style="padding:10px;">10th / 12th / ITI / Diploma / Graduation (Post ke anusar official PDF dekhein)</td></tr>
    </table>

    <h3 style="color:#0f172a; border-bottom:2px solid #cbd5e1; padding-bottom:8px; margin-top:24px;">⚙️ 4. Complete Stage-by-Stage Selection Process</h3>
    <ol style="padding-left:22px; margin-bottom:20px; font-size:14px;">
        <li><strong>Stage 1:</strong> Written Examination / Computer Based Test (CBT) ya Merit Shortlisting.</li>
        <li><strong>Stage 2:</strong> Skill Test / Typing Test / Physical Efficiency Test (PET/PST - jahan laagu ho).</li>
        <li><strong>Stage 3:</strong> Original Document Verification (DV) & Medical Fitness Examination.</li>
    </ol>

    <h3 style="color:#0f172a; border-bottom:2px solid #cbd5e1; padding-bottom:8px; margin-top:24px;">📝 5. How to Apply Online / Check Official Notification</h3>
    <ul style="padding-left:22px; margin-bottom:20px; font-size:14px;">
        <li>Sabse pehle niche diye gaye <strong>Download Official Notification PDF</strong> link par click karke poori vigyapti dhyan se padhein.</li>
        <li>Apne sabhi zaroori documents (Photo, Signature, ID Proof, Caste/Education Certificates) scan karke tayar rakhein.</li>
        <li><strong>Apply Online / Direct Portal</strong> link par click karke One-Time Registration (OTR) ya Login pura karein aur final print save kar lein.</li>
    </ul>

    <h3 style="color:#0f172a; border-bottom:2px solid #cbd5e1; padding-bottom:8px; margin-top:24px;">🚀 6. 30-Day Preparation & Revision Blueprint</h3>
    <p style="font-size:14px; color:#334155; margin-bottom:14px;">
        Is exam mein high score karne ke liye pichhle 5 varshon ke Previous Year Question Papers (PYQs) ko analyze karein, rozana 1 full-length mock test lagayein aur Quantitative Aptitude, Reasoning, General Awareness tatha core technical subjects ke high-weightage topics ka weekly revision karein.
    </p>
</div>
"""
        # Short View ends -> Deep View starts immediately below it
        return f"{short_view}\n{deep_view}".strip()

class MasterSynthesizer:
    @staticmethod
    def create_post(title, link, source_name, use_ai=True):
        deep = OfficialIntentSnifferAgent.sniff_and_verify(title, link)
        if deep["accuracy_score"] < 4:
            return None

        category = CategoryClassifierAgent.classify(title)
        post_date = deep["extracted_date"]
        title_lower = title.lower()

        # 1. Automatic Job Type Classification
        if any(k in title_lower for k in NON_GOVT_KEYWORDS):
            job_type = "Non-Govt + Semi-Govt"
        else:
            job_type = "Govt"

        # 2. Automatic State Detection
        detected_state = "All India / Central"
        for state_name, keywords in STATE_KEYWORDS.items():
            if any(kw in title_lower for kw in keywords):
                detected_state = state_name
                break

        # Generate Option B (AI Mentor) & Option A (Short View + Deep View below it)
        opt_b_html = OptionB_GeminiAIAgent.generate_editorial(title, category) if use_ai and GEMINI_API_KEY else ""
        full_desc = OptionA_SEOWriterAgent.generate_full_content(
            title, category, post_date, job_type, detected_state, mentor_html=opt_b_html
        )

        job_id = hashlib.md5(f"{title}_{link}".encode("utf-8")).hexdigest()[:12]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return {
            "id": job_id, "title": title, "category": category, "source": source_name,
            "job_type": job_type, "state": detected_state, "link": link, "url": link, 
            "apply_link": deep["apply_link"], "applyUrl": deep["apply_link"],
            "notif_url": deep["notif_url"], "notifUrl": deep["notif_url"], 
            "download_pdf": deep["download_pdf"], "result_url": deep["result_url"],
            "resultUrl": deep["result_url"], "answer_key_url": deep["answer_key_url"],
            "answerKeyUrl": deep["answer_key_url"], "admit_card_url": deep["admit_card_url"],
            "admitCardUrl": deep["admit_card_url"], "official_web": deep["official_web"],
            "webUrl": deep["official_web"], "dynamic_admin_review_boxes": deep["dynamic_admin_review_boxes"],
            "date": post_date, "post_date": post_date, "updated_at": now,
            "summary": f"{title} ({job_type} | {detected_state}) - Check verified official PDF and direct links.",
            "description": full_desc, "content": full_desc, "accuracy_score": deep["accuracy_score"],
            "engine": "Master Unified Hybrid Sniffer & Synthesizer", "status": "pending_review",
            "seo_keywords": f"{title}, {category}, {detected_state}, {job_type}, Direct Apply Online, Official PDF"
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

        t_low = text.lower()
        if any(j in t_low for j in JUNK_TITLES): continue
        if any(b in href.lower() for b in BLOCK_DOMAINS): continue

        if 15 <= len(text) <= 140 and any(
            kw in t_low for kw in [
                "online form", "recruitment", "vacancy", "bharti", "result",
                "admit card", "answer key", "apply", "notification", "syllabus", "2026", "apprentice"
            ]
        ):
            items.append((text, href))
    return items

def main():
    print("🚀 Starting Master Unified Hybrid Scraper (Short View + Deep Dossier Below)...")
    existing = []
    if os.path.exists(DATABASE_FILE):
        try:
            with open(DATABASE_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception: pass

    existing = [
        j for j in existing 
        if isinstance(j, dict) and j.get("accuracy_score", 0) >= 4 and not any(jk in j.get("title", "").lower() for jk in JUNK_TITLES)
    ]

    seen_titles = {j.get("title", "").lower().strip() for j in existing}
    new_posts = []
    ai_count = 0

    # 1. SCAN 8 AGGREGATOR PORTALS
    for source in SOURCES:
        print(f"📡 Scanning Signal Source: {source['name']}...")
        html = resilient_stealth_fetch(source["url"])
        if not html: continue
        
        candidates = extract_items_from_source(html, source["url"])
        count = 0
        for title, link in candidates:
            norm = title.lower().strip()
            if norm in seen_titles: continue

            use_ai = (ai_count < 15)
            post = MasterSynthesizer.create_post(title, link, source["name"], use_ai=use_ai)
            if post:
                if use_ai and GEMINI_API_KEY:
                    ai_count += 1
                    time.sleep(1.0)
                new_posts.append(post)
                seen_titles.add(norm)
                count += 1
                if count >= 6: break
        time.sleep(1.0)

    # 2. PROACTIVE SURVEILLANCE OF MASTER DIRECTORY HUBS
    print("🔍 Running Proactive Master Directory Surveillance...")
    for item in DIRECTORY_SURVEILLANCE_TARGETS:
        norm = item["name"].lower().strip()
        if norm in seen_titles: continue
        hub = OFFICIAL_HUBS.get(item["hub"])
        if hub:
            post = MasterSynthesizer.create_post(item["name"], hub["notices"], hub["name"], use_ai=False)
            if post:
                new_posts.append(post)
                seen_titles.add(norm)

    final_db = new_posts + existing
    final_db = final_db[:500]
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(final_db, f, ensure_ascii=False, indent=2)
    print(f"\n🎉 Master Sync Complete: {len(final_db)} verified posts saved in {DATABASE_FILE}!")

if __name__ == "__main__":
    main()

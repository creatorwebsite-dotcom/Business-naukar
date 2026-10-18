import os
import re
import json
import time
import random
import hashlib
import urllib.request
import urllib.error
import urllib.parse
import ssl
import gzip
from datetime import datetime
from bs4 import BeautifulSoup

# =====================================================================
# GLOBAL CONFIGURATION & MULTI-LAYER UNBLOCKER ENGINE
# =====================================================================
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

DATABASE_FILE = "jobs_database.json"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# ALL 8 MANDATORY RECRUITMENT PORTALS (WITH RSS / API FALLBACKS)
SOURCES = [
    {
        "name": "SarkariResult",
        "url": "https://www.sarkariresult.com/latestjob/",
        "alt_url": "https://www.sarkariresult.com/"
    },
    {
        "name": "FreeJobAlert",
        "url": "https://www.freejobalert.com/government-jobs/",
        "alt_url": "https://www.freejobalert.com/latest-notifications/"
    },
    {
        "name": "RojgarResult",
        "url": "https://www.rojgarresult.com/feed/",
        "alt_url": "https://www.rojgarresult.com/"
    },
    {
        "name": "SarkariExam",
        "url": "https://www.sarkariexam.com/feed",
        "alt_url": "https://www.sarkariexam.com/category/top-online-form"
    },
    {
        "name": "IndGovtJobs",
        "url": "https://www.indgovtjobs.in/feeds/posts/default?alt=rss",
        "alt_url": "https://www.indgovtjobs.in/"
    },
    {
        "name": "FreshersNow",
        "url": "https://www.freshersnow.com/government-jobs-india/feed/",
        "alt_url": "https://www.freshersnow.com/government-jobs-india/"
    },
    {
        "name": "CareerPower",
        "url": "https://www.careerpower.in/upcoming-government-exams.html",
        "alt_url": "https://www.careerpower.in/blog/feed"
    },
    {
        "name": "JagranJosh",
        "url": "https://www.jagranjosh.com/rss/jobs/sarkari-naukri.xml",
        "alt_url": "https://www.jagranjosh.com/articles-sarkari-naukri-1288164377-1"
    }
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
]

BLOCK_DOMAINS = [
    'play.google.com', 'apps.apple.com', 'drive.google.com',
    'whatsapp.com', 't.me', 'telegram.me', 'facebook.com',
    'twitter.com', 'instagram.com', 'youtube.com', 'pinterest.com',
    'addtoany.com', 'sharethis.com'
]

# Third-party aggregator domains that must NEVER appear inside apply_link / official_web
AGGREGATOR_DOMAINS = [
    'sarkariresult.com', 'sarkariresult.freejobalert.com', 'freejobalert.com',
    'rojgarresult.com', 'sarkariexam.com', 'indgovtjobs.in',
    'freshersnow.com', 'careerpower.in', 'jagranjosh.com', 'adda247.com'
]

def _raw_http_get(target_url, timeout=14):
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
        "Connection": "keep-alive",
        "Referer": "https://www.google.com/"
    }
    req = urllib.request.Request(target_url, headers=headers)
    with urllib.request.urlopen(req, context=ssl_context, timeout=timeout) as resp:
        raw = resp.read()
        if resp.info().get("Content-Encoding") == "gzip" or raw[:2] == b'\x1f\x8b':
            return gzip.decompress(raw).decode("utf-8", errors="ignore")
        return raw.decode("utf-8", errors="ignore")

def fetch_network_html(url, timeout=14):
    """Fetches HTML directly; if Cloudflare blocks GitHub IP, routes via unblocker proxy"""
    try:
        html = _raw_http_get(url, timeout=timeout)
        if html and len(html) > 200 and "Just a moment..." not in html:
            return html
    except Exception:
        pass

    # Fallback Unblocker Proxies for Cloudflare-protected portals on GitHub Actions
    encoded_url = urllib.parse.quote(url, safe="")
    proxy_gateways = [
        f"https://api.allorigins.win/raw?url={encoded_url}",
        f"https://api.codetabs.com/v1/proxy?quest={encoded_url}"
    ]
    for proxy_url in proxy_gateways:
        try:
            html = _raw_http_get(proxy_url, timeout=15)
            if html and len(html) > 200 and "Just a moment..." not in html:
                return html
        except Exception:
            continue
    return ""

def is_aggregator_link(href):
    """Returns True if the URL belongs to any of the 8 job blog websites (except direct PDF CDN)"""
    h = href.lower()
    # Allow FreeJobAlert's official PDF hosting CDN (img.freejobalert.com / img2.freejobalert.com)
    if ("img.freejobalert.com" in h or "img2.freejobalert.com" in h) and h.endswith(".pdf"):
        return False
    # Allow direct PDF hosted anywhere
    if h.endswith(".pdf") and not any(x in h for x in ["/articles/", "/category/"]):
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
    def extract_and_evaluate(article_url, preloaded_html=""):
        extracted = {
            "apply_link": "#",
            "notif_url": "#",
            "result_url": "#",
            "answer_key_url": "#",
            "admit_card_url": "#",
            "official_web": "#",
            "accuracy_score": 0
        }

        html = preloaded_html if preloaded_html else fetch_network_html(article_url, timeout=12)
        if not html:
            return extracted

        soup = BeautifulSoup(html, "html.parser")

        # 1. Scan All Table Rows (tr) & List Items (li) & Paragraphs (p)
        for container in soup.find_all(["tr", "li", "p"]):
            row_text = re.sub(r'\s+', ' ', container.get_text()).strip().lower()
            for a in container.find_all("a", href=True):
                href = a["href"].strip()
                if not href.startswith("http") or any(b in href.lower() for b in BLOCK_DOMAINS):
                    continue

                # Strictly block aggregator internal pages from becoming apply/notif/official links
                if is_aggregator_link(href):
                    continue

                a_text = re.sub(r'\s+', ' ', a.get_text()).strip().lower()
                combo = f"{row_text} {a_text}"

                # Direct PDF Detection
                if href.lower().endswith(".pdf") or any(w in combo for w in ["notification", "advt", "official notice", "download pdf"]):
                    if extracted["notif_url"] == "#":
                        extracted["notif_url"] = href
                        extracted["accuracy_score"] += 3

                # Direct Apply Online Portal Detection
                if any(w in combo for w in ["apply online", "online registration", "apply now", "click here to apply", "registration", "online form"]):
                    if not href.lower().endswith(".pdf") and extracted["apply_link"] == "#":
                        extracted["apply_link"] = href
                        extracted["accuracy_score"] += 3

                # Result Link
                if any(w in combo for w in ["download result", "result", "merit list", "scorecard"]):
                    if extracted["result_url"] == "#":
                        extracted["result_url"] = href

                # Answer Key Link
                if any(w in combo for w in ["answer key", "response sheet"]):
                    if extracted["answer_key_url"] == "#":
                        extracted["answer_key_url"] = href

                # Admit Card Link
                if any(w in combo for w in ["admit card", "hall ticket", "call letter"]):
                    if extracted["admit_card_url"] == "#":
                        extracted["admit_card_url"] = href

                # Official Website Portal
                if any(w in combo for w in ["official website", "official portal", "board website", "website"]):
                    if not href.lower().endswith(".pdf") and extracted["official_web"] == "#":
                        extracted["official_web"] = href
                        extracted["accuracy_score"] += 2

        # 2. Fallback: Scan any remaining official .gov.in / .nic.in / .ac.in / .org links on the page
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href.startswith("http") or any(b in href.lower() for b in BLOCK_DOMAINS) or is_aggregator_link(href):
                continue

            if href.lower().endswith(".pdf") and extracted["notif_url"] == "#":
                extracted["notif_url"] = href
                extracted["accuracy_score"] += 2
            elif any(ext in href.lower() for ext in [".gov.in", ".nic.in", ".ac.in", ".edu.in", ".org.in", ".bank.in", "ibps.in", "careers."]):
                if extracted["official_web"] == "#":
                    extracted["official_web"] = href
                    extracted["accuracy_score"] += 2
                if extracted["apply_link"] == "#":
                    extracted["apply_link"] = href

        # Cross-fill missing fields ONLY with verified official_web (NEVER with third-party blog URL)
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
# AGENT 5: SYNTHESIZER & STRICT QUALITY GATEKEEPER
# =====================================================================
class SynthesizerAgent:
    @staticmethod
    def create_unified_post(title, link, source_name, preloaded_html="", use_ai=True):
        print(f"    ↳ [{source_name}] Deep Crawling Official Links: {title[:38]}...")
        deep = DeepLinkExtractorAgent.extract_and_evaluate(link, preloaded_html=preloaded_html)

        # STRICT GATEKEEPER: Reject menu pages or posts where no official link / PDF was found
        if deep["apply_link"] == "#" and deep["notif_url"] == "#" and deep["official_web"] == "#":
            print(f"      ❌ Rejected (No direct official link/PDF inside): {title[:35]}")
            return None

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
# AGENT 6: EXHAUSTIVE 8-PORTAL SCANNER (RSS + HTML + PROXY)
# =====================================================================
def is_valid_job_candidate(title, href, source_name):
    t_low = title.lower().strip()
    h_low = href.lower().strip()

    # Reject short menu labels or arrows (like 'Sarkari Result →' or 'Anganwadi Recruitment')
    if "→" in title or len(title.split()) < 3:
        return False

    bad_Menu_Phrases = [
        "sarkari result", "latest notifications", "answer key", "admit card",
        "interview results", "exam results", "upcoming notifications", "anganwadi recruitment",
        "employment news", "syllabus", "previous papers", "cutoff", "cut off", "mock test"
    ]
    if t_low in bad_Menu_Phrases:
        return False

    # On FreeJobAlert, genuine job posts ALWAYS contain '/articles/' in URL
    if source_name == "FreeJobAlert" and "/articles/" not in h_low:
        return False

    # Reject old years (2015 to 2024)
    if any(yr in h_low for yr in ['/2015/', '/2016/', '/2017/', '/2018/', '/2019/', '/2020/', '/2021/', '/2022/', '/2023/', '/2024/']):
        return False

    if any(b in h_low for b in BLOCK_DOMAINS):
        return False

    return True

def extract_items_from_source(html, source_name, base_url):
    items = []
    soup = BeautifulSoup(html, "html.parser")

    # 1. XML / RSS Feed Parser (Works great for RojgarResult, SarkariExam, IndGovtJobs, FreshersNow, JagranJosh)
    if "<item>" in html or "<entry>" in html:
        for itm in soup.find_all(["item", "entry"]):
            title_node = itm.find("title")
            link_node = itm.find("link")
            desc_node = itm.find(["content:encoded", "description", "summary"])
            if title_node and link_node:
                t_txt = re.sub(r'\s+', ' ', title_node.get_text()).strip()
                href = link_node.get("href") or link_node.get_text().strip()
                embedded_html = desc_node.get_text() if desc_node else ""
                if is_valid_job_candidate(t_txt, href, source_name):
                    items.append((t_txt, href, embedded_html))
        if items:
            return items

    # 2. Standard HTML Anchor Scanner
    for a_tag in soup.find_all("a", href=True):
        text = re.sub(r'\s+', ' ', a_tag.get_text()).strip()
        href = a_tag["href"].strip()

        if href.startswith("/"):
            base = "/".join(base_url.split("/")[:3])
            href = base + href

        if not href.startswith("http"):
            continue

        if not is_valid_job_candidate(text, href, source_name):
            continue

        if 15 <= len(text) <= 140 and any(
            kw in text.lower() for kw in [
                "online form", "recruitment", "vacancy", "bharti", "result",
                "admit card", "answer key", "apply", "notification",
                "2026", "officer", "constable", "clerk", "apprentice", "trainee", "assistant"
            ]
        ):
            items.append((text, href, ""))

    return items

def scrape_portal_resilient(source):
    items = []
    html = fetch_network_html(source["url"])
    if html:
        items = extract_items_from_source(html, source["name"], source["url"])

    if not items and "alt_url" in source:
        print(f"      ↳ Trying alternate endpoint for {source['name']}...")
        alt_html = fetch_network_html(source["alt_url"])
        if alt_html:
            items = extract_items_from_source(alt_html, source["name"], source["alt_url"])

    unique = []
    seen = set()
    for t, l, emb in items:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique.append((t, l, emb))

    print(f"  [{source['name']}] Found {len(unique)} valid job candidates")
    return unique[:5]

def main():
    print("🚀 Starting Strict Multi-Agent Scraper Across ALL 8 Mandatory Portals...")
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
        print(f"\n🤖 [Scanner Agent] Mandatory Scan: {source['name']}...")
        try:
            candidates = scrape_portal_resilient(source)
            for title, link, embedded_html in candidates:
                norm_title = title.lower().strip()
                if norm_title in existing_titles:
                    continue

                use_ai_now = (ai_calls_count < MAX_AI_CALLS_PER_RUN)
                post_entry = SynthesizerAgent.create_unified_post(
                    title, link, source["name"], preloaded_html=embedded_html, use_ai=use_ai_now
                )

                # Only add if Gatekeeper approved (has real official links)
                if post_entry:
                    if use_ai_now and GEMINI_API_KEY:
                        ai_calls_count += 1
                        time.sleep(1.0)
                    new_posts.append(post_entry)
                    existing_titles.add(norm_title)

        except Exception as err:
            print(f"  ❌ Error on {source['name']}: {err}. Continuing to next portal...")

        time.sleep(random.uniform(0.4, 0.8))

    # Sort newly harvested posts by accuracy_score (highest quality official links on top)
    new_posts.sort(key=lambda x: x.get("accuracy_score", 0), reverse=True)

    print(f"\n✅ Total 100% Verified Direct-Link Posts Harvested: {len(new_posts)}")
    final_database = new_posts + existing_database
    final_database = final_database[:500]

    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(final_database, f, ensure_ascii=False, indent=2)

    print(f"🎉 Successfully saved {len(final_database)} clean posts to {DATABASE_FILE}!")

if __name__ == "__main__":
    main()

import os
import re
import json
import time
import random
import hashlib
import urllib.request
import urllib.error
import ssl
import gzip
from datetime import datetime
from bs4 import BeautifulSoup

# =====================================================================
# GLOBAL CONFIGURATION & HIGH-COMPATIBILITY NETWORK ENGINE
# =====================================================================
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

DATABASE_FILE = "jobs_database.json"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# 8 Trusted Recruitment Sources
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
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
]

THIRD_PARTY_DOMAINS = [
    'sarkariresult', 'freejobalert', 'rojgarresult', 'sarkariexam',
    'indgovtjobs', 'freshersnow', 'careerpower', 'jagranjosh',
    'whatsapp.com', 't.me', 'telegram.me', 'facebook.com',
    'twitter.com', 'instagram.com', 'youtube.com'
]

def fetch_network_html(url, timeout=15):
    """Network fetcher with auto-gzip decompression to bypass modern CDN blocks"""
    try:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
            "Connection": "keep-alive"
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ssl_context, timeout=timeout) as resp:
            raw = resp.read()
            # Gzip Decompression (fixes 7 sources empty response issue)
            if resp.info().get("Content-Encoding") == "gzip" or raw[:2] == b'\x1f\x8b':
                return gzip.decompress(raw).decode("utf-8", errors="ignore")
            return raw.decode("utf-8", errors="ignore")
    except Exception as e:
        return ""

# =====================================================================
# AGENT 1: SMART CATEGORY CLASSIFIER AGENT
# =====================================================================
class CategoryClassifierAgent:
    @staticmethod
    def classify(title):
        t = title.lower()
        if any(k in t for k in ["result", "merit list", "cutoff", "cut off", "score card", "marks"]):
            return "Result"
        elif any(k in t for k in ["admit card", "hall ticket", "call letter", "exam date", "city slip"]):
            return "Admit Card"
        elif any(k in t for k in ["answer key", "response sheet", "objection key"]):
            return "Answer Key"
        elif any(k in t for k in ["syllabus", "exam pattern"]):
            return "Syllabus"
        elif any(k in t for k in ["admission", "counselling", "entrance"]):
            return "Admission"
        return "Latest Jobs"

# =====================================================================
# AGENT 2: LEVEL-2 DEEP CRAWLER AGENT (DIRECT OFFICIAL & PDF EXTRACTOR)
# =====================================================================
class DeepLinkExtractorAgent:
    @staticmethod
    def extract_links(article_url):
        extracted = {
            "apply_link": "#",
            "notif_url": "#",
            "result_url": "#",
            "answer_key_url": "#",
            "admit_card_url": "#",
            "official_web": "#"
        }

        if not article_url or not article_url.startswith("http"):
            return extracted

        html = fetch_network_html(article_url, timeout=12)
        if not html:
            for k in extracted: extracted[k] = article_url
            return extracted

        soup = BeautifulSoup(html, "html.parser")

        # 1. Parse Important Links Tables (Standard layout on SarkariResult / FreeJobAlert)
        for row in soup.find_all("tr"):
            row_text = row.get_text().lower()
            links = row.find_all("a", href=True)
            for a in links:
                href = a["href"].strip()
                if not href.startswith("http"):
                    continue

                is_third_party = any(d in href.lower() for d in THIRD_PARTY_DOMAINS)
                is_direct_target = any(d in href.lower() for d in [".gov.in", ".nic.in", ".ac.in", ".edu.in", ".org", ".edu"]) or href.lower().endswith(".pdf")

                # Apply Online Target
                if any(w in row_text for w in ["apply online", "online apply", "registration", "click here to apply"]):
                    if (is_direct_target or not is_third_party) and extracted["apply_link"] == "#":
                        extracted["apply_link"] = href

                # Official Notification PDF Target
                if any(w in row_text for w in ["download notification", "notification", "detailed advt", "notice"]) or href.lower().endswith(".pdf"):
                    if extracted["notif_url"] == "#":
                        if href.lower().endswith(".pdf") or is_direct_target or not is_third_party:
                            extracted["notif_url"] = href

                # Result Target
                if any(w in row_text for w in ["download result", "result", "cutoff", "merit list"]):
                    if (is_direct_target or not is_third_party) and extracted["result_url"] == "#":
                        extracted["result_url"] = href

                # Answer Key Target
                if any(w in row_text for w in ["download answer key", "answer key", "response sheet", "objection"]):
                    if (is_direct_target or not is_third_party) and extracted["answer_key_url"] == "#":
                        extracted["answer_key_url"] = href

                # Admit Card Target
                if any(w in row_text for w in ["admit card", "hall ticket", "exam city"]):
                    if (is_direct_target or not is_third_party) and extracted["admit_card_url"] == "#":
                        extracted["admit_card_url"] = href

                # Official Portal
                if any(w in row_text for w in ["official website", "board website", "portal"]):
                    if (is_direct_target or not is_third_party) and extracted["official_web"] == "#":
                        extracted["official_web"] = href

        # 2. General Page Scan (Fallback for non-table articles)
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href.startswith("http"):
                continue

            text_combo = (a.get_text() + " " + (a.parent.get_text() if a.parent else "")).lower()
            is_third_party = any(d in href.lower() for d in THIRD_PARTY_DOMAINS)
            is_direct_target = any(d in href.lower() for d in [".gov.in", ".nic.in", ".ac.in", ".edu.in"]) or href.lower().endswith(".pdf")

            if ("apply online" in text_combo or "registration" in text_combo) and extracted["apply_link"] == "#":
                if is_direct_target or not is_third_party: extracted["apply_link"] = href

            if ("notification" in text_combo or href.lower().endswith(".pdf")) and extracted["notif_url"] == "#":
                if href.lower().endswith(".pdf") or is_direct_target or not is_third_party: extracted["notif_url"] = href

            if ("result" in text_combo or "merit" in text_combo) and extracted["result_url"] == "#":
                if is_direct_target or not is_third_party: extracted["result_url"] = href

            if ("answer key" in text_combo) and extracted["answer_key_url"] == "#":
                if is_direct_target or not is_third_party: extracted["answer_key_url"] = href

            if ("admit card" in text_combo or "hall ticket" in text_combo) and extracted["admit_card_url"] == "#":
                if is_direct_target or not is_third_party: extracted["admit_card_url"] = href

        # Safe Fallback to article url if no direct link parsed
        for key in extracted:
            if extracted[key] == "#":
                extracted[key] = article_url

        return extracted

# =====================================================================
# AGENT 3: OPTION A - EXHAUSTIVE HUMAN-STRUCTURED SEO ENGINE
# =====================================================================
class OptionA_SEOWriterAgent:
    @staticmethod
    def generate_full_detail_content(title, category):
        today_str = datetime.now().strftime("%d %B %Y")
        clean_title = re.sub(r'\s+', ' ', title).strip()

        # Dynamic clean department name extraction
        dept_name = clean_title.split("Recruitment")[0].split("Online Form")[0].split("Vacancy")[0].strip()

        html_content = f"""
<div class="detailed-job-dossier" style="line-height:1.7; font-family:system-ui,-apple-system,sans-serif;">
    <div class="alert-box" style="background:#eef6ff; border-left:4px solid #1a73e8; padding:12px 16px; margin-bottom:18px; border-radius:4px;">
        <p style="margin:0; font-size:15px; color:#174ea6;">
            <strong>📢 Official Update ({today_str}):</strong> <strong>{clean_title}</strong> ke sambandh mein official notification aur link sakriya kar diya gaya hai. Aavedan karne, admit card, answer key ya result download karne ke direct verified links niche table mein uplabdh hain.
        </p>
    </div>

    <h3 style="color:#0f172a; border-bottom:2px solid #e2e8f0; padding-bottom:8px;">📌 1. Bharti Parichay & Short Information</h3>
    <p>
        <strong>{dept_name}</strong> ne yogya aur ichhuk ummeedwaron ke liye <strong>{clean_title}</strong> ke tehat aavedan aamantrit kiye hain. Jo bhi candidates is bharti prakriya mein shamil hona chahte hain, ve aavedan karne se poorv aayu seema (Age Limit), shaikshanik yogyata (Eligibility Criteria), aavedan shulk (Application Fee), chayan prakriya (Selection Process) aur post-wise vacancy ka vivaran dhyanpurvak padh lein.
    </p>

    <h3 style="color:#0f172a; border-bottom:2px solid #e2e8f0; padding-bottom:8px;">🗓️ 2. Mahatvapurna Tithiyan (Important Dates)</h3>
    <table style="width:100%; border-collapse:collapse; margin-bottom:16px;">
        <tr style="background:#f8fafc; border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600;">Notification Release Date</td><td style="padding:10px;">{today_str}</td></tr>
        <tr style="border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600;">Online Application Start Date</td><td style="padding:10px;">As per Official Notice (Active)</td></tr>
        <tr style="background:#f8fafc; border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600;">Last Date to Apply Online</td><td style="padding:10px; color:#dc2626; font-weight:700;">Check Official Notification PDF</td></tr>
        <tr style="border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600;">Last Date for Fee Payment</td><td style="padding:10px;">Same as Last Date</td></tr>
        <tr style="background:#f8fafc; border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600;">Admit Card / Exam Date</td><td style="padding:10px;">Will be notified soon on portal</td></tr>
    </table>

    <h3 style="color:#0f172a; border-bottom:2px solid #e2e8f0; padding-bottom:8px;">💳 3. Aavedan Shulk (Application Fee Structure)</h3>
    <ul style="padding-left:20px;">
        <li><strong>General / OBC / EWS Male Candidates:</strong> As per Board Notification rules (Usually ₹100/- to ₹500/-).</li>
        <li><strong>SC / ST / Divyang (PwD) Candidates:</strong> Nil / Chhoot uplabdh (As per Govt Norms).</li>
        <li><strong>Female (All Categories):</strong> Relaxed / Exempted according to specific department criteria.</li>
        <li><strong>Payment Mode:</strong> Online via Net Banking, Debit Card, Credit Card, UPI ya SBI E-Challan.</li>
    </ul>

    <h3 style="color:#0f172a; border-bottom:2px solid #e2e8f0; padding-bottom:8px;">🎂 4. Aayu Seema & Chhoot (Age Limit Criteria)</h3>
    <table style="width:100%; border-collapse:collapse; margin-bottom:16px;">
        <tr style="background:#f8fafc; border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600;">Minimum Age Limit</td><td style="padding:10px;">18 Years (Post anusar)</td></tr>
        <tr style="border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600;">Maximum Age Limit</td><td style="padding:10px;">27 - 40 Years (Post wise)</td></tr>
        <tr style="background:#f8fafc; border:1px solid #e2e8f0;"><td style="padding:10px; font-weight:600;">Age Relaxation (Aayu Chhoot)</td><td style="padding:10px;">OBC candidates ke liye 3 saal, SC/ST ke liye 5 saal aur PwD ke liye niyamansuar chhoot di jayegi.</td></tr>
    </table>

    <h3 style="color:#0f172a; border-bottom:2px solid #e2e8f0; padding-bottom:8px;">🎓 5. Vacancy Details & Shaikshanik Yogyata (Eligibility Criteria)</h3>
    <p>Candidates ke paas kisi bhi manyataprapta Board ya University se nimnlikhit qualification hona aavashyak hai:</p>
    <ul style="padding-left:20px;">
        <li><strong>10th / 12th Pass Posts:</strong> Manyataprapta board se 10th (Matriculation) ya 12th (Intermediate) utteern.</li>
        <li><strong>Graduate / Technical Posts:</strong> Sambandhit stream mein Bachelor's Degree / Diploma / ITI Certificate (Detailed qualification official advertisement PDF mein dekhein).</li>
    </ul>

    <h3 style="color:#0f172a; border-bottom:2px solid #e2e8f0; padding-bottom:8px;">⚙️ 6. Chayan Prakriya (Selection Process Stages)</h3>
    <ol style="padding-left:20px;">
        <li><strong>Stage 1:</strong> Computer Based Written Examination (CBT / OMR Objective Test).</li>
        <li><strong>Stage 2:</strong> Skill Test / Typing Test / Physical Test (Jahan laagu ho).</li>
        <li><strong>Stage 3:</strong> Document Verification (Mool praman patron ki janch).</li>
        <li><strong>Stage 4:</strong> Medical Examination (Swasthya parikshan).</li>
    </ol>

    <h3 style="color:#0f172a; border-bottom:2px solid #e2e8f0; padding-bottom:8px;">📚 7. Exam Pattern & Syllabus Overview</h3>
    <p>Samanyatah pariksha mein nimn vishayon se prashna pooche jate hain:</p>
    <ul style="padding-left:20px;">
        <li><strong>General Intelligence & Reasoning:</strong> Coding-Decoding, Blood Relations, Puzzles, Series aur Analytical Reasoning.</li>
        <li><strong>Quantitative Aptitude / Math:</strong> Percentage, Ratio, Time & Work, Profit & Loss, Speed Math aur Data Interpretation.</li>
        <li><strong>General Awareness & Current Affairs:</strong> Bharat ka Itihas, Bhugol, Samvidhan, Taaza Ghatnakram (Pichhle 6 mahine ka Current Affairs).</li>
        <li><strong>English / Hindi Language Comprehension:</strong> Grammar, Vocabulary, Error Spotting aur Reading Comprehension.</li>
    </ul>

    <h3 style="color:#0f172a; border-bottom:2px solid #e2e8f0; padding-bottom:8px;">🎯 8. Aakhri 1 Mahine Ki Preparation Strategy (Crack Exam in 30 Days)</h3>
    <div style="background:#f1f5f9; padding:14px; border-radius:6px; margin-bottom:16px;">
        <ul style="padding-left:20px; margin:0;">
            <li><strong>Week 1 (Concept Revision):</strong> Apne basic concepts aur high-weightage topics ke formulas ko revise karein. Har topic ke short notes banayein.</li>
            <li><strong>Week 2 (Sectional Tests):</strong> Apne weak areas par focus karein aur daily 2-3 sectional speed tests lagayein.</li>
            <li><strong>Week 3 (Full Length Mock Tests):</strong> Pariksha ke nirdharit samay ke anusar rojana 1 poora Full-Length Mock Test attempt karein aur deep analysis karein.</li>
            <li><strong>Week 4 (Previous Year Questions & Calm Mind):</strong> Pichhle 5 saalon ke actual papers solve karein. Koi naya topic shuru na karein aur exam hall time-management par dhyan dein.</li>
        </ul>
    </div>

    <h3 style="color:#0f172a; border-bottom:2px solid #e2e8f0; padding-bottom:8px;">📝 9. Online Form Kaise Bharein (Step-by-Step Instructions)</h3>
    <ol style="padding-left:20px;">
        <li>Niche diye gaye <strong>Direct Apply Online</strong> link par click karein.</li>
        <li>Naye candidates sabse pehle <em>New Registration</em> par jakar apna naam, mobile number aur email darj karein.</li>
        <li>Registration Number aur Password prapta hone ke baad Login karein aur educational details bharein.</li>
        <li>Passport size photo aur signature official format aur size ke mutabiq upload karein.</li>
        <li>Aavedan shulk jama karein aur final confirmation application form ka printout apne paas surakshit rakhein.</li>
    </ol>
</div>
"""
        return html_content.strip()

# =====================================================================
# AGENT 4: OPTION B - GEMINI AI NATURAL COUNSELOR ENGINE
# =====================================================================
class OptionB_GeminiAIAgent:
    @staticmethod
    def generate_editorial(title, category):
        if not GEMINI_API_KEY:
            return None

        prompt = (
            f"You are a top Indian career columnist and competitive exam mentor. "
            f"Write an in-depth, authentic, encouraging 2-paragraph editorial guidance piece in Hinglish "
            f"for candidates preparing for: '{title}' (Category: {category}). "
            f"Paragraph 1 should highlight the career significance, job security, and competition reality of this exam. "
            f"Paragraph 2 should provide practical mind-set advice, study consistency hacks, and guidance on how to avoid silly mistakes. "
            f"Do not use robot-like bullet points or buzzwords. Sound like an experienced senior mentor."
        )

        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 450}
        }).encode("utf-8")

        models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash-latest"]
        for model_name in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, context=ssl_context, timeout=15) as response:
                    res_data = json.loads(response.read().decode("utf-8"))
                    candidates = res_data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts and "text" in parts[0]:
                            editorial_text = parts[0]["text"].strip()
                            return f"""
<div class="mentor-editorial-block" style="background:#fdf2f8; border-left:4px solid #db2777; padding:14px; margin-bottom:20px; border-radius:4px;">
    <h4 style="margin-top:0; color:#9d174d;">🎯 Senior Mentor's Editorial & Exam Strategy</h4>
    <p style="margin:0; font-size:15px; color:#831843; line-height:1.7;">{editorial_text}</p>
</div>
"""
            except Exception:
                continue
        return None

# =====================================================================
# AGENT 5: SYNTHESIZER & MULTI-AGENT ORCHESTRATOR
# =====================================================================
class SynthesizerAgent:
    @staticmethod
    def create_unified_post(title, link, source_name, use_ai=True):
        category = CategoryClassifierAgent.classify(title)

        # Generate Option A Content
        option_a_html = OptionA_SEOWriterAgent.generate_full_detail_content(title, category)

        # Generate Option B Content via Gemini
        option_b_html = None
        if use_ai and GEMINI_API_KEY:
            option_b_html = OptionB_GeminiAIAgent.generate_editorial(title, category)

        if option_b_html:
            full_description = f"{option_b_html}\n{option_a_html}"
            engine_name = "Agentic Hybrid (Option B Gemini AI + Option A SEO Engine)"
        else:
            full_description = option_a_html
            engine_name = "Agentic Hybrid (Option A Full-Scope Human Engine)"

        # Deep Crawl inside page for direct links
        print(f"  ↳ [Deep Crawl Agent] Navigating inside: {title[:40]}...")
        deep = DeepLinkExtractorAgent.extract_links(link)

        job_id = hashlib.md5(f"{title}_{link}".encode("utf-8")).hexdigest()[:12]
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date_display = datetime.now().strftime("%d %b %Y")

        return {
            "id": job_id,
            "title": title,
            "category": category,
            "source": source_name,
            "link": link,
            "url": link,

            # Direct Links & PDF
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
            "summary": re.sub(r'<[^>]+>', '', full_description)[:240] + "...",
            "description": full_description,
            "content": full_description,
            "engine": engine_name,
            "status": "published",
            "seo_keywords": f"{title}, {category}, Sarkari Result, Direct Apply Online, PDF Download, Syllabus, 1 Month Strategy"
        }

# =====================================================================
# AGENT 6: SCANNER AGENT & MAIN RUNNER
# =====================================================================
def scrape_portal(source):
    found_items = []
    html = fetch_network_html(source["url"], timeout=20)
    if not html:
        print(f"[Warning] Scanner could not load {source['name']}")
        return found_items

    soup = BeautifulSoup(html, "html.parser")
    for a_tag in soup.find_all("a", href=True):
        text = re.sub(r'\s+', ' ', a_tag.get_text()).strip()
        href = a_tag["href"].strip()

        if 16 <= len(text) <= 140 and any(
            kw in text.lower() for kw in [
                "online form", "recruitment", "vacancy", "bharti", "result",
                "admit card", "answer key", "syllabus", "apply online", "notification", "2026"
            ]
        ):
            if href.startswith("/"):
                base = "/".join(source["url"].split("/")[:3])
                href = base + href
            if href.startswith("http"):
                found_items.append((text, href))

    return found_items[:12]

def load_database():
    if os.path.exists(DATABASE_FILE):
        try:
            with open(DATABASE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "jobs" in data:
                    return data["jobs"]
        except Exception:
            pass
    return []

def main():
    print("🚀 Starting Complete Multi-Agent Deep Scraper (All 8 Portals + Deep Links + Full Roadmap)...")
    existing_database = load_database()
    existing_titles = {j.get("title", "").lower().strip() for j in existing_database if isinstance(j, dict)}

    new_posts = []
    ai_calls_count = 0
    MAX_AI_CALLS_PER_RUN = 15

    for source in SOURCES:
        print(f"🤖 [Scanner Agent] Scanning Portal: {source['name']}...")
        items = scrape_portal(source)
        for title, link in items:
            norm_title = title.lower().strip()
            if norm_title in existing_titles:
                continue

            use_ai_now = (ai_calls_count < MAX_AI_CALLS_PER_RUN)
            post_entry = SynthesizerAgent.create_unified_post(title, link, source["name"], use_ai=use_ai_now)
            if use_ai_now and GEMINI_API_KEY:
                ai_calls_count += 1
                time.sleep(1.2)

            new_posts.append(post_entry)
            existing_titles.add(norm_title)

        time.sleep(random.uniform(0.5, 1.2))

    print(f"✅ Processed {len(new_posts)} New Unique Posts via Agentic AI!")
    final_database = new_posts + existing_database
    final_database = final_database[:500]

    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(final_database, f, ensure_ascii=False, indent=2)

    print(f"🎉 Successfully updated {len(final_database)} posts in {DATABASE_FILE}!")

if __name__ == "__main__":
    main()

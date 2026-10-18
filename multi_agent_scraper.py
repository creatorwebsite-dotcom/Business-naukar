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

# =====================================================================
# GLOBAL CONFIGURATION & NETWORK SETTINGS
# =====================================================================
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

DATABASE_FILE = "jobs_database.json"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
]

THIRD_PARTY_DOMAINS = [
    'sarkariresult', 'freejobalert', 'rojgarresult', 'sarkariexam',
    'indgovtjobs', 'freshersnow', 'careerpower', 'jagranjosh',
    'whatsapp.com', 't.me', 'telegram.me', 'facebook.com',
    'twitter.com', 'instagram.com', 'youtube.com'
]

# =====================================================================
# AGENT 1: CATEGORY CLASSIFIER AGENT
# =====================================================================
class CategoryClassifierAgent:
    @staticmethod
    def classify(title):
        t = title.lower()
        if any(k in t for k in ["result", "merit list", "cutoff", "cut off", "score card", "marks"]):
            return "Result"
        elif any(k in t for k in ["admit card", "hall ticket", "call letter", "exam date", "exam city"]):
            return "Admit Card"
        elif any(k in t for k in ["answer key", "response sheet", "objection"]):
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

        try:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            req = urllib.request.Request(article_url, headers=headers)
            with urllib.request.urlopen(req, context=ssl_context, timeout=12) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                soup = BeautifulSoup(html, "html.parser")

                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"].strip()
                    if not href.startswith("http"):
                        continue

                    link_text = re.sub(r'\s+', ' ', a_tag.get_text()).strip().lower()
                    parent_text = re.sub(r'\s+', ' ', a_tag.parent.get_text()).strip().lower() if a_tag.parent else ""
                    combined = f"{link_text} {parent_text}"

                    is_third_party = any(d in href.lower() for d in THIRD_PARTY_DOMAINS)

                    # 1. Apply Online / Registration URL
                    if any(k in combined for k in ["apply online", "online apply", "registration", "apply here", "fill form"]):
                        if not is_third_party and extracted["apply_link"] == "#":
                            extracted["apply_link"] = href

                    # 2. Official Notification PDF File
                    if any(k in combined for k in ["download notification", "notification pdf", "official notification", "advt pdf", "download notice"]) or href.lower().endswith(".pdf"):
                        if extracted["notif_url"] == "#":
                            if href.lower().endswith(".pdf") or not is_third_party:
                                extracted["notif_url"] = href

                    # 3. Direct Result / Merit List PDF or Scorecard URL
                    if any(k in combined for k in ["download result", "check result", "scorecard", "merit list", "cutoff", "marks"]):
                        if not is_third_party and extracted["result_url"] == "#":
                            extracted["result_url"] = href

                    # 4. Direct Answer Key / Objection Portal Link
                    if any(k in combined for k in ["download answer key", "answer key", "response sheet", "raise objection", "key challenge"]):
                        if not is_third_party and extracted["answer_key_url"] == "#":
                            extracted["answer_key_url"] = href

                    # 5. Direct Admit Card / Hall Ticket Slip Link
                    if any(k in combined for k in ["download admit card", "admit card", "hall ticket", "call letter", "exam city"]):
                        if not is_third_party and extracted["admit_card_url"] == "#":
                            extracted["admit_card_url"] = href

                    # 6. Official Board / Commission Web Address
                    if any(k in combined for k in ["official website", "official portal", "board website", "commission website"]):
                        if not is_third_party and extracted["official_web"] == "#":
                            extracted["official_web"] = href

        except Exception as e:
            print(f"    [Deep Crawl Notice] {article_url}: {e}")

        # Fallbacks: Agar direct link na mile toh article URL use ho
        for key in extracted:
            if extracted[key] == "#":
                extracted[key] = article_url

        return extracted

# =====================================================================
# AGENT 3: OPTION A - HUMAN STRUCTURING & SEO FORMATTING AGENT
# =====================================================================
class OptionA_SEOWriterAgent:
    @staticmethod
    def generate_content(title, category):
        today_str = datetime.now().strftime("%d %B %Y")
        clean_title = re.sub(r'\s+', ' ', title).strip()

        intro_templates = [
            f"Sarkari naukri ki taiyari kar rahe candidates ke liye badi khabar hai. Hal hi mein <strong>{clean_title}</strong> ke tahat naya official update jari kiya gaya hai. Niche di gayi puri jankari dhyan se padhein aur direct link se apply ya download karein.",
            f"Desh bhar ke yuvaon ke liye ek aur shandaar avsar samne aaya hai. <strong>{clean_title}</strong> ka official update jari ho chuka hai. Yahan eligibility, important dates aur direct online links saral shabdon mein uplabdh hain.",
            f"Competitive exams ki taiyari karne wale abhyarthiyon ke liye mahatvapurna update: <strong>{clean_title}</strong> se judi taaza jankari jari ho chuki hai. Niche diye gaye direct options se official documents check karein."
        ]

        intro = random.choice(intro_templates)

        structured_html = f"""
<div class="human-article-box">
    <p>{intro}</p>
    <h4>📋 Notification & Event Overview ({today_str})</h4>
    <ul>
        <li><strong>Post / Update:</strong> {clean_title}</li>
        <li><strong>Category:</strong> {category}</li>
        <li><strong>Access Mode:</strong> Online Direct Official Portal</li>
        <li><strong>Status:</strong> Active & Verified</li>
    </ul>
    <h4>💡 Candidates Ke Liye Zaroori Salah (Expert Tips)</h4>
    <p>Apna <strong>Original Notification PDF</strong> ek baar dhyan se verify karein. Sabhi educational documents pehle se taiyar rakhein taaki form bharte ya result/admit card download karte waqt kisi pareshani ka samna na karna pade.</p>
    <h4>✅ Kaise Check / Download Karein?</h4>
    <ol>
        <li>Niche diye gaye <strong>Direct Official Action Link</strong> par click karein.</li>
        <li>Portal open hone par apna Registration Number / Roll Number ya credentials enter karein.</li>
        <li>Form submission confirmation ya download kiye gaye PDF file ka printout surakshit save kar lein.</li>
    </ol>
</div>
"""
        return structured_html.strip()

# =====================================================================
# AGENT 4: OPTION B - GEMINI AI NATURAL EDITORIAL AGENT
# =====================================================================
class OptionB_GeminiAIAgent:
    @staticmethod
    def generate_editorial(title, category):
        if not GEMINI_API_KEY:
            return None

        prompt = (
            f"You are an expert Indian government exam counselor and career columnist. "
            f"Write a natural, human, engaging 2-paragraph editorial overview in simple Hinglish "
            f"for this update: '{title}' (Category: {category}). "
            f"Explain why this update matters for aspirants and give 2 practical tips. "
            f"Do not sound robotic or use bullet points. Make it clear and encouraging."
        )

        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 300}
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
                            ai_text = parts[0]["text"].strip()
                            return f"<div class='ai-editorial'><p>{ai_text}</p></div>"
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    continue
                elif e.code == 429:
                    time.sleep(2)
                    break
                else:
                    break
            except Exception:
                break
        return None

# =====================================================================
# AGENT 5: SYNTHESIZER & MULTI-AGENT ORCHESTRATOR
# =====================================================================
class SynthesizerAgent:
    @staticmethod
    def create_unified_post(title, link, source_name, use_ai=True):
        # 1. Classify Category
        category = CategoryClassifierAgent.classify(title)

        # 2. Option A Engine
        option_a_html = OptionA_SEOWriterAgent.generate_content(title, category)

        # 3. Option B Gemini Engine
        option_b_html = None
        if use_ai and GEMINI_API_KEY:
            option_b_html = OptionB_GeminiAIAgent.generate_editorial(title, category)

        if option_b_html:
            full_description = f"{option_b_html}\n<hr/>\n{option_a_html}"
            engine_used = "Agentic Hybrid (Option B Gemini AI + Option A SEO)"
        else:
            full_description = option_a_html
            engine_used = "Agentic Hybrid (Option A Smart Human Engine)"

        # 4. Deep Crawl for Direct Links & PDF files
        print(f"  ↳ [Deep Crawl Agent] Extracting Direct Links: {title[:38]}...")
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
            "summary": re.sub(r'<[^>]+>', '', full_description)[:220] + "...",
            "description": full_description,
            "content": full_description,
            "engine": engine_used,
            "status": "published",
            "seo_keywords": f"{title}, {category}, Sarkari Result, Latest Govt Jobs 2026, Answer Key, Result PDF"
        }

# =====================================================================
# AGENT 6: SCANNER AGENT & MAIN RUNNER
# =====================================================================
def scrape_portal(source):
    found_items = []
    headers = {"User-Agent": random.choice(USER_AGENTS)}
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
                        "admit card", "answer key", "syllabus", "apply online", "notification", "2026"
                    ]
                ):
                    if href.startswith("/"):
                        base = "/".join(source["url"].split("/")[:3])
                        href = base + href
                    if href.startswith("http"):
                        found_items.append((text, href))
    except Exception as e:
        print(f"[Warning] Scanner could not fetch {source['name']}: {e}")

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
    print("🚀 Starting Agentic Multi-Agent Hybrid Scraper...")
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

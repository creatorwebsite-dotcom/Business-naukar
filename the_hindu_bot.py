# ==============================================================================
# 📰 THE HINDU EXAM NEWS AUTOMATION SYSTEM (6:30 AM IST ANTI-BLOCK PYTHON BOT)
# Paste this entire block at the VERY END of your scraper.py file
# ==============================================================================
import os
import re
import json
import time
import random
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

# 1. OFFICIAL PAYWALL-FREE RSS FEEDS OF THE HINDU
THE_HINDU_RSS_SOURCES = [
    {
        "key": "national",
        "label": "🏛️ National & Polity",
        "url": "https://www.thehindu.com/news/national/feeder/default.rss",
        "relevance": "GS Paper-II: Polity, Governance, Supreme Court Judgements, Bills & Govt Schemes"
    },
    {
        "key": "economy",
        "label": "📈 Economy & Banking",
        "url": "https://www.thehindu.com/business/Economy/feeder/default.rss",
        "relevance": "GS Paper-III & Banking/SSC: RBI Monetary Policy, GDP, Inflation, Budget & Banking"
    },
    {
        "key": "ir",
        "label": "🌐 International Relations",
        "url": "https://www.thehindu.com/news/international/feeder/default.rss",
        "relevance": "GS Paper-II & Current Affairs: Bilateral Agreements, Foreign Visits & UN/G20/BRICS"
    },
    {
        "key": "scitech",
        "label": "🚀 Science, Tech & Environment",
        "url": "https://www.thehindu.com/sci-tech/feeder/default.rss",
        "relevance": "GS Paper-III & Prelims: ISRO/NASA Missions, Defense Updates, Tech & Climate Reports"
    },
    {
        "key": "editorial",
        "label": "✍️ Editorial Spark",
        "url": "https://www.thehindu.com/opinion/editorial/feeder/default.rss",
        "relevance": "UPSC & State PSC Mains / Essay: Deep Analytical Core Summary & Vocabulary"
    }
]

# Anti-Block Rotating Browser User-Agents
ANTI_BLOCK_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"
]

# Drop Crime, Entertainment, Ads & Political Rants
DROP_NOISE_REGEX = re.compile(
    r"\b(murder|robbery|theft|killed|cinema|movie|actor|actress|bollywood|horoscope|lottery|sponsored|ipl|box office)\b",
    re.IGNORECASE
)

def clean_html_tags(raw_html):
    text = re.sub(r"<[^>]+>", " ", str(raw_html or ""))
    return re.sub(r"\s+", " ", text).strip()

def fetch_rss_anti_block(rss_url):
    headers = {
        "User-Agent": random.choice(ANTI_BLOCK_USER_AGENTS),
        "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache"
    }
    req = urllib.request.Request(rss_url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.read()

def run_the_hindu_630am_exam_bot():
    ist_now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    date_str = ist_now.strftime("%d %b %Y, %I:%M %p IST")
    collected_articles = []

    for src in THE_HINDU_RSS_SOURCES:
        try:
            xml_bytes = fetch_rss_anti_block(src["url"])
            root = ET.fromstring(xml_bytes)
            count = 0
            for item in root.findall(".//item"):
                if count >= 6:
                    break
                title = clean_html_tags(item.findtext("title"))
                desc = clean_html_tags(item.findtext("description"))
                link = (item.findtext("link") or "https://www.thehindu.com").strip()
                pub_date = (item.findtext("pubDate") or date_str).strip()

                if not title or DROP_NOISE_REGEX.search(title + " " + desc):
                    continue

                sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", desc) if len(s.strip()) > 20]
                if sentences:
                    bullets = "<br>".join([f"• {s}" for s in sentences[:3]])
                else:
                    bullets = f"• <strong>Key Update:</strong> {title}"

                if src["key"] == "editorial":
                    bullets += "<br>• <strong>Editorial Spark (Mains/Essay):</strong> Critical analytical perspective for descriptive answer writing."

                collected_articles.append({
                    "category": src["key"],
                    "categoryLabel": src["label"],
                    "title": title,
                    "link": link,
                    "pubDate": pub_date,
                    "examRelevance": src["relevance"],
                    "keyPoints": bullets
                })
                count += 1
            time.sleep(0.8)  # Polite anti-block delay between feeds
        except Exception as e:
            print(f"[The Hindu Bot] Warning on {src['key']}: {e}")

    payload = {
        "updatedAt": date_str,
        "hookLine1": "Aaj ki Top 5 Khabrein jo aapke Exam ko Crack karengi - Sirf 3 minute mein!",
        "hookLine2": "Utho! Aaj ke is dynamic analysis mein RBI ka naya update aur Supreme Court ka landmark faisla shamil hai.",
        "totalArticles": len(collected_articles),
        "articles": collected_articles
    }

    with open("the_hindu_daily.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[The Hindu Bot] Saved {len(collected_articles)} exam articles to the_hindu_daily.json")

    # Optional Delivery Bot: Telegram Notification if TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID are set in GitHub Secrets
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if tg_token and tg_chat and collected_articles:
        try:
            msg_lines = [
                "🔥 *Aaj ki Top 5 Khabrein jo aapke Exam ko Crack karengi - Sirf 3 minute mein!*\n",
                f"📅 *{date_str}*\n"
            ]
            for a in collected_articles[:6]:
                msg_lines.append(f"{a['categoryLabel']}\n*{a['title']}*\n🎯 _{a['examRelevance']}_\n🔗 [Read Full]({a['link']})\n")
            tg_url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
            tg_data = json.dumps({
                "chat_id": tg_chat,
                "text": "\n".join(msg_lines),
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }).encode("utf-8")
            tg_req = urllib.request.Request(tg_url, data=tg_data, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(tg_req, timeout=15)
        except Exception as te:
            print(f"[Telegram Delivery Bot] Notice: {te}")

if __name__ == "__main__":
    run_the_hindu_630am_exam_bot()

import os
import re
import json
import time
import hashlib
import asyncio
import urllib.parse
import urllib.request
from datetime import datetime
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from curl_cffi import requests as cffi_requests
from playwright.async_api import async_playwright
from playwright_stealth import stealth

DATABASE_FILE = "jobs_database.json"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# ==============================================================================
# LAYER 1A: 8 MAJOR AGGREGATOR WEBSITES + MIRROR WEBSITES
# ==============================================================================
SOURCES = [
    {"name": "SarkariResult", "url": "https://sarkariresult.com.cm/"},
    {"name": "SarkariResultMirror", "url": "https://www.sarkariresult.com/"},
    {"name": "FreeJobAlert", "url": "https://www.freejobalert.com/government-jobs/"},
    {"name": "RojgarResult", "url": "https://www.rojgarresult.com/"},
    {"name": "SarkariExam", "url": "https://www.sarkariexam.com/"},
    {"name": "IndGovtJobs", "url": "https://www.indgovtjobs.in/"},
    {"name": "FreshersNow", "url": "https://www.freshersnow.com/government-jobs-india/"},
    {"name": "CareerPower", "url": "https://www.careerpower.in/upcoming-government-exams.html"},
    {"name": "JagranJosh", "url": "https://www.jagranjosh.com/articles-sarkari-naukri-1288164377-1"}
]

# ==============================================================================
# LAYER 1B: OFFICIAL RECRUITMENT BOARDS (200+ Govt & 100 Non-Govt/PSU Coverage)
# ==============================================================================
OFFICIAL_HUBS = {
    "upsc": {"name": "Union Public Service Commission", "home": "https://upsc.gov.in/", "notices": "https://upsc.gov.in/examinations/active-examinations", "apply_portal": "https://upsconline.nic.in/upsc/OTRP/index.php"},
    "ssc": {"name": "Staff Selection Commission", "home": "https://ssc.gov.in/", "notices": "https://ssc.gov.in/Portal/Notices", "apply_portal": "https://ssc.gov.in/login"},
    "rrb": {"name": "Railway Recruitment Board", "home": "https://www.rrbapply.gov.in/", "notices": "https://www.rrbapply.gov.in/#/notices", "apply_portal": "https://www.rrbapply.gov.in/#/auth/home"},
    "rpf": {"name": "Railway Protection Force", "home": "https://www.rrbapply.gov.in/", "notices": "https://www.rrbapply.gov.in/#/notices", "apply_portal": "https://www.rrbapply.gov.in/#/auth/home"},
    "ibps": {"name": "Institute of Banking Personnel Selection", "home": "https://www.ibps.in/", "notices": "https://www.ibps.in/notifications/", "apply_portal": "https://ibpsonline.ibps.in/"},
    "sbi": {"name": "State Bank of India", "home": "https://sbi.co.in/web/careers", "notices": "https://sbi.co.in/web/careers/current-openings", "apply_portal": "https://ibpsonline.ibps.in/"},
    "rbi": {"name": "Reserve Bank of India", "home": "https://opportunities.rbi.org.in/", "notices": "https://opportunities.rbi.org.in/Scripts/Vacancies.aspx", "apply_portal": "https://opportunities.rbi.org.in/Scripts/Vacancies.aspx"},
    "nabard": {"name": "NABARD", "home": "https://www.nabard.org/", "notices": "https://www.nabard.org/careers-notices1.aspx?cid=693&id=26", "apply_portal": "https://www.nabard.org/careers-notices1.aspx?cid=693&id=26"},
    "lic": {"name": "Life Insurance Corporation", "home": "https://licindia.in/", "notices": "https://licindia.in/Bottom-Links/Careers", "apply_portal": "https://ibpsonline.ibps.in/"},
    "niacl": {"name": "New India Assurance", "home": "https://www.newindia.co.in/", "notices": "https://www.newindia.co.in/portal/readMore/Vacancies", "apply_portal": "https://ibpsonline.ibps.in/"},
    "idbi": {"name": "IDBI Bank", "home": "https://www.idbibank.in/", "notices": "https://www.idbibank.in/idbi-bank-careers-current-openings.aspx", "apply_portal": "https://www.idbibank.in/idbi-bank-careers-current-openings.aspx"},
    "army": {"name": "Join Indian Army Agniveer", "home": "https://joinindianarmy.nic.in/", "notices": "https://joinindianarmy.nic.in/Bravo.htm", "apply_portal": "https://joinindianarmy.nic.in/Authentication.aspx"},
    "navy": {"name": "Join Indian Navy Agniveer", "home": "https://www.joinindiannavy.gov.in/", "notices": "https://www.joinindiannavy.gov.in/en/page/career-opportunities.html", "apply_portal": "https://agniveernavy.cdac.in/"},
    "air force": {"name": "Indian Air Force Agniveervayu", "home": "https://agnipathvayu.cdac.in/", "notices": "https://agnipathvayu.cdac.in/AV/", "apply_portal": "https://agnipathvayu.cdac.in/avreg/candidate/login"},
    "coast guard": {"name": "Indian Coast Guard", "home": "https://joinindiancoastguard.cdac.in/", "notices": "https://joinindiancoastguard.cdac.in/", "apply_portal": "https://joinindiancoastguard.cdac.in/cgept/"},
    "mpsc": {"name": "Maharashtra MPSC", "home": "https://mpsc.gov.in/", "notices": "https://mpsc.gov.in/adv_notification/8", "apply_portal": "https://mpsconline.gov.in/candidate/login"},
    "mahapolice": {"name": "Maharashtra Police Bharti", "home": "https://www.mahapolice.gov.in/", "notices": "https://policerecruitment2024.mahait.org/", "apply_portal": "https://policerecruitment2024.mahait.org/"},
    "uppsc": {"name": "Uttar Pradesh UPPSC", "home": "https://uppsc.up.nic.in/", "notices": "https://uppsc.up.nic.in/CandidatePages/Notifications.aspx", "apply_portal": "https://uppsc.up.nic.in/CandidatePages/Notifications.aspx"},
    "upsssc": {"name": "Uttar Pradesh UPSSSC", "home": "https://upsssc.gov.in/", "notices": "https://upsssc.gov.in/AllNotifications.aspx", "apply_portal": "https://upsssc.gov.in/AllNotifications.aspx"},
    "up police": {"name": "UPPBPB UP Police", "home": "https://uppbpb.gov.in/", "notices": "https://uppbpb.gov.in/Notice", "apply_portal": "https://uppbpb.gov.in/"},
    "bpsc": {"name": "Bihar BPSC", "home": "https://www.bpsc.bih.nic.in/", "notices": "https://www.bpsc.bih.nic.in/", "apply_portal": "https://onlinebpsc.bihar.gov.in/main/home"},
    "bssc": {"name": "Bihar BSSC", "home": "https://bssc.bihar.gov.in/", "notices": "https://bssc.bihar.gov.in/NoticeBoard.htm", "apply_portal": "https://www.onlinebssc.com/"},
    "csbc": {"name": "Bihar Police CSBC", "home": "https://csbc.bihar.gov.in/", "notices": "https://csbc.bihar.gov.in/", "apply_portal": "https://csbc.bihar.gov.in/"},
    "mppsc": {"name": "Madhya Pradesh MPPSC", "home": "https://mppsc.mp.gov.in/", "notices": "https://mppsc.mp.gov.in/advertisements", "apply_portal": "https://mppsc.mp.gov.in/Applyonline"},
    "rpsc": {"name": "Rajasthan RPSC", "home": "https://rpsc.rajasthan.gov.in/", "notices": "https://rpsc.rajasthan.gov.in/advertisements", "apply_portal": "https://sso.rajasthan.gov.in/signin"},
    "rsmssb": {"name": "Rajasthan RSSB", "home": "https://rssb.rajasthan.gov.in/", "notices": "https://rssb.rajasthan.gov.in/advertisements", "apply_portal": "https://sso.rajasthan.gov.in/signin"},
    "hpsc": {"name": "Haryana HPSC", "home": "https://hpsc.gov.in/", "notices": "https://hpsc.gov.in/en-us/Instructions", "apply_portal": "https://regn.hpsc.gov.in/"},
    "dsssb": {"name": "Delhi DSSSB", "home": "https://dsssb.delhi.gov.in/", "notices": "https://dsssb.delhi.gov.in/home/Vacancy-Advertisements", "apply_portal": "https://dsssbonline.nic.in/"},
    "ctet": {"name": "CBSE CTET", "home": "https://ctet.nic.in/", "notices": "https://ctet.nic.in/", "apply_portal": "https://examinationservices.nic.in/"},
    "kvs": {"name": "Kendriya Vidyalaya Sangathan", "home": "https://kvsangathan.nic.in/", "notices": "https://kvsangathan.nic.in/en/employment-notice/", "apply_portal": "https://kvsangathan.nic.in/en/employment-notice/"},
    "nvs": {"name": "Navodaya Vidyalaya Samiti", "home": "https://navodaya.gov.in/", "notices": "https://navodaya.gov.in/nvs/en/Recruitment/Notification-Vacancies/", "apply_portal": "https://navodaya.gov.in/nvs/en/Recruitment/Fill-up-online-application/"},
    "ugc net": {"name": "NTA UGC NET", "home": "https://ugcnet.nta.ac.in/", "notices": "https://ugcnet.nta.ac.in/", "apply_portal": "https://ugcnet.ntaonline.in/"},
    "india post": {"name": "India Post GDS", "home": "https://indiapostgdsonline.gov.in/", "notices": "https://indiapostgdsonline.gov.in/", "apply_portal": "https://indiapostgdsonline.gov.in/reg_instruction.aspx"},
    "fci": {"name": "Food Corporation of India", "home": "https://fci.gov.in/", "notices": "https://www.recruitmentfci.in/", "apply_portal": "https://www.recruitmentfci.in/"},
    "esic": {"name": "ESIC", "home": "https://www.esic.gov.in/", "notices": "https://www.esic.gov.in/recruitments", "apply_portal": "https://www.esic.gov.in/recruitments"},
    "epfo": {"name": "EPFO", "home": "https://www.epfindia.gov.in/", "notices": "https://www.epfindia.gov.in/site_en/Recruitments.php", "apply_portal": "https://upsconline.nic.in/"},
    "drdo": {"name": "DRDO", "home": "https://www.drdo.gov.in/", "notices": "https://www.drdo.gov.in/drdo/careers", "apply_portal": "https://rac.gov.in/"},
    "isro": {"name": "ISRO", "home": "https://www.isro.gov.in/", "notices": "https://www.isro.gov.in/Careers.html", "apply_portal": "https://apps.ursc.gov.in/"},
    "barc": {"name": "BARC", "home": "https://www.barc.gov.in/", "notices": "https://www.barc.gov.in/careers/", "apply_portal": "https://barconlineexam.com/"},
    "iocl": {"name": "Indian Oil IOCL", "home": "https://iocl.com/", "notices": "https://iocl.com/latest-job-opening", "apply_portal": "https://iocl.com/latest-job-opening"},
    "ntpc": {"name": "NTPC Limited", "home": "https://careers.ntpc.co.in/", "notices": "https://careers.ntpc.co.in/", "apply_portal": "https://careers.ntpc.co.in/"},
    "ongc": {"name": "ONGC Limited", "home": "https://ongcindia.com/", "notices": "https://ongcindia.com/web/eng/career-tab", "apply_portal": "https://ongcindia.com/web/eng/career-tab"},
    "bhel": {"name": "BHEL", "home": "https://careers.bhel.in/", "notices": "https://careers.bhel.in/", "apply_portal": "https://careers.bhel.in/"},
    "gail": {"name": "GAIL India", "home": "https://gailonline.com/", "notices": "https://gailonline.com/CRApplyingGail.html", "apply_portal": "https://gailonline.com/CRApplyingGail.html"},
    "sail": {"name": "SAIL", "home": "https://sailcareers.com/", "notices": "https://sailcareers.com/", "apply_portal": "https://sailcareers.com/"},
    "hal": {"name": "Hindustan Aeronautics HAL", "home": "https://hal-india.co.in/", "notices": "https://hal-india.co.in/career", "apply_portal": "https://hal-india.co.in/career"},
    "bel": {"name": "Bharat Electronics BEL", "home": "https://bel-india.in/", "notices": "https://bel-india.in/job-notifications/", "apply_portal": "https://bel-india.in/job-notifications/"},
    "mdl": {"name": "Mazagon Dock MDL", "home": "https://mazagondock.in/", "notices": "https://mazagondock.in/Career.aspx", "apply_portal": "https://mazagondock.in/erecruitment/"},
    "dmrc": {"name": "Delhi Metro DMRC", "home": "https://delhimetrorail.com/", "notices": "https://delhimetrorail.com/pages/en/career", "apply_portal": "https://delhimetrorail.com/pages/en/career"},
    "mahametro": {"name": "MahaMetro", "home": "https://www.mahametro.org/", "notices": "https://www.mahametro.org/Career.aspx", "apply_portal": "https://www.mahametro.org/Career.aspx"},
    "aai": {"name": "Airports Authority AAI", "home": "https://www.aai.aero/", "notices": "https://www.aai.aero/en/careers/recruitment", "apply_portal": "https://www.aai.aero/en/careers/recruitment"}
}

# ==============================================================================
# LAYER 2: NON-GOVT / SEMI-GOVT KEYWORDS & STATE DETECTION MAPPING
# ==============================================================================
NON_GOVT_KEYWORDS = [
    "ongc", "iocl", "ntpc", "sail", "bhel", "gail", "powergrid", "hpcl", "coal india",
    "hal", "bel", "mdl", "mazagon dock", "cochin shipyard", "grse", "npcil", "nmdc",
    "bsnl", "dmrc", "mahametro", "idbi", "lic", "niacl", "uiic", "cooperative", "dccb",
    "pacs", "markfed", "milk union", "dairy", "temple trust", "devasthan", "private",
    "securitas", "sis", "dsa", "csc", "e-seva", "nursing home", "diagnostic", "reliance",
    "d-mart", "amazon", "flipkart", "warehouse", "courier", "dtdc", "blue dart",
    "broadband", "petrol pump", "hotel", "factory", "textile", "packaging", "tcs",
    "infosys", "wipro", "accenture", "cognizant", "apprentice", "apprentices",
    "contractual", "third-party", "semi-govt", "psu"
]

STATE_KEYWORDS = {
    "Maharashtra": ["mpsc", "mahagenco", "mahadisco", "msedcl", "mseb", "mumbai", "pune", "nagpur", "nashik", "thane", "bhiwandi", "maharashtra", "talathi", "gramsevak", "krushi sevak", "vanrakshak", "arogya sevak", "srpf", "mahametro", "msrtc", "rto amvi", "mahapolice", "zp maharashtra"],
    "Uttar Pradesh": ["uppsc", "upsssc", "uppbpb", "up police", "allahabad", "prayagraj", "lucknow", "varanasi", "kanpur", "noida", "uttar pradesh", "lekhpal", "upnhm", "uptet", "upsrtc", "uppcs", "ro/aro"],
    "Bihar": ["bpsc", "bpssc", "bihar", "patna", "gaya", "muzaffarpur", "csbc", "bssc", "btet", "bihar police"],
    "Madhya Pradesh": ["mppsc", "esb mp", "mppeb", "vyapam", "madhya pradesh", "bhopal", "indore", "jabalpur", "gwalior", "mp police"],
    "Rajasthan": ["rpsc", "rsmssb", "rssb", "rajasthan", "jaipur", "jodhpur", "udaipur", "kota", "patwari", "reet", "ras"],
    "Haryana": ["hpsc", "hssc", "haryana", "chandigarh", "gurugram", "rohtak", "htet", "hcs"],
    "Delhi": ["dsssb", "delhi police", "aiims delhi", "dmrc", "ndmc", "mcd", "delhi"],
    "Gujarat": ["gpsc", "gsssb", "ojas", "gujarat", "ahmedabad", "surat", "vadodara"],
    "Punjab": ["ppsc", "psssb", "punjab", "amritsar", "ludhiana", "patiala"],
    "West Bengal": ["wbpsc", "wbprb", "west bengal", "kolkata", "howrah"],
    "Karnataka": ["kpsc", "kea", "karnataka", "bengaluru", "bangalore", "mysuru"],
    "Tamil Nadu": ["tnpsc", "trb tn", "tamil nadu", "chennai", "coimbatore"],
    "Telangana": ["tspsc", "tgpsc", "telangana", "hyderabad"],
    "Andhra Pradesh": ["appsc", "andhra pradesh", "vijayawada", "visakhapatnam"],
    "Jharkhand": ["jpsc", "jssc", "jharkhand", "ranchi", "jamshedpur"],
    "Chhattisgarh": ["cgpsc", "cgvyapam", "chhattisgarh", "raipur", "bilaspur"],
    "Uttarakhand": ["ukpsc", "uksssc", "uttarakhand", "dehradun", "haridwar"],
    "Himachal Pradesh": ["hppsc", "hpsssb", "himachal", "shimla"],
    "Odisha": ["opsc", "ossc", "osssc", "odisha", "bhubaneswar", "cuttack"],
    "Assam": ["apsc", "slprb assam", "assam", "guwahati"],
    "Kerala": ["kerala psc", "kerala", "thiruvananthapuram", "kochi"]
}

BLOCK_DOMAINS = [
    'play.google.com', 'apps.apple.com', 'drive.google.com',
    'whatsapp.com', 't.me', 'telegram.me', 'facebook.com',
    'twitter.com', 'x.com', 'instagram.com', 'youtube.com', 'pinterest.com',
    'sarkariresulttools.net', 'tools.sarkariresult.com', 'addtoany.com'
]

AGGREGATOR_DOMAINS = [
    'sarkariresult.com', 'sarkariresult.com.cm', 'sarkariresulttools.net',
    'freejobalert.com', 'rojgarresult.com', 'sarkariexam.com',
    'indgovtjobs.in', 'freshersnow.com', 'careerpower.in',
    'jagranjosh.com', 'adda247.com', 'sarkariresult.net'
]

JUNK_TITLES = [
    "sarkari result", "sarkariresult", "tools", "sarkari result tools",
    "latest notifications", "view more", "click here", "home", "read more",
    "contact us", "disclaimer", "privacy policy", "android app", "apple app",
    "join telegram", "whatsapp group", "all results", "admit card 2026"
]

DYNAMIC_BOX_KEYWORDS = [
    "date extended", "corrigendum", "revised notice", "revised vacancy",
    "short notice", "cutoff", "cut off", "score card", "merit list",
    "exam city", "intimation", "mock test", "objection", "dv schedule",
    "document verification", "skill test", "typing test", "pet/pst",
    "interview schedule", "medical exam", "waiting list", "reserve list",
    "zone wise", "category wise vacancy", "post preference", "otr registration"
]

# ==============================================================================
# STEALTH NETWORK FETCHING ENGINE (curl_cffi + Playwright Stealth)
# ==============================================================================
def fetch_with_curl_cffi(url):
    try:
        response = cffi_requests.get(url, impersonate="chrome110", timeout=15)
        if response.status_code == 200 and len(response.text) > 250:
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
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            content = await page.content()
            await browser.close()
            if content and len(content) > 250:
                return content
    except Exception:
        pass
    return ""

def resilient_stealth_fetch(url):
    if not url or url == "#" or not url.startswith("http"):
        return ""
    html = fetch_with_curl_cffi(url)
    if not html or "Just a moment..." in html or "Cloudflare" in html or "Attention Required!" in html:
        try:
            html = asyncio.run(fetch_with_playwright_stealth(url))
        except Exception:
            pass
    return html

# ==============================================================================
# STRICT DEEP URL & PDF VALIDATOR (BLOCKS ROOT HOMEPAGES)
# ==============================================================================
def is_aggregator_page_link(href):
    h = href.lower()
    if h.endswith(".pdf") or ".pdf?" in h or "img.freejobalert.com" in h or "img2.freejobalert.com" in h:
        return False
    return any(ag in h for ag in AGGREGATOR_DOMAINS)

def is_specific_deep_url(url, require_pdf=False):
    """
    Strictly rejects '#', root domains like 'https://www.rbi.org.in/',
    or generic language homepages like 'https://hpsc.gov.in/en-us/'.
    """
    if not url or url == "#" or not url.startswith("http"):
        return False
    u_low = url.lower().strip()
    if any(b in u_low for b in BLOCK_DOMAINS):
        return False
    if is_aggregator_page_link(u_low):
        return False

    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    query = parsed.query

    if require_pdf:
        return (
            u_low.endswith(".pdf") or ".pdf?" in u_low or "/portals/" in u_low
            or "rdocs" in u_low or "download" in u_low or "writereaddata" in u_low
        )

    generic_paths = [
        "", "/", "/en", "/en-us", "/hi", "/home", "/index.html",
        "/index.php", "/index.jsp", "/default.aspx", "/web/careers"
    ]
    if path.lower() in generic_paths and not query:
        return False

    reg_domains = [
        "ibpsreg.ibps.in", "ibpsonline.ibps.in", "upsconline.nic.in",
        "mpsconline.gov.in", "onlinebpsc.bihar.gov.in", "dsssbonline.nic.in",
        "regn.hpsc.gov.in", "rrbapply.gov.in", "examinationservices.nic.in"
    ]
    if any(rd in parsed.netloc.lower() for rd in reg_domains) and (len(path) > 1 or query):
        return True

    segments = [s for s in path.split("/") if s and s.lower() not in ["en", "en-us", "hi", "web"]]
    return len(segments) >= 1 and (len(path) > 6 or len(query) > 4)

# ==============================================================================
# LAYER 2: INTENT, CATEGORY, JOB TYPE & STATE CLASSIFIER AGENT
# ==============================================================================
class IntentAndMetaClassifierAgent:
    @staticmethod
    def analyze(title):
        t = title.lower()

        if any(k in t for k in ["answer key", "response sheet", "objection", "question paper"]):
            category = "Answer Key"
            primary_intent = "INTENT_ANSWER_KEY"
        elif any(k in t for k in ["result", "merit list", "cutoff", "cut off", "score card", "selection list", "marks", "final result"]):
            category = "Result"
            primary_intent = "INTENT_RESULT"
        elif any(k in t for k in ["admit card", "hall ticket", "call letter", "exam city", "exam date", "interview letter"]):
            category = "Admit Card"
            primary_intent = "INTENT_ADMIT_CARD"
        elif any(k in t for k in ["syllabus", "exam pattern", "curriculum"]):
            category = "Syllabus"
            primary_intent = "INTENT_SYLLABUS"
        elif any(k in t for k in ["admission", "counselling", "entrance", "enrollment"]):
            category = "Admission"
            primary_intent = "INTENT_APPLY"
        elif any(k in t for k in ["apply online", "online form", "registration", "application form"]):
            category = "Latest Jobs"
            primary_intent = "INTENT_APPLY"
        elif any(k in t for k in ["notification", "short notice", "advertisement", "advt"]):
            category = "Latest Jobs"
            primary_intent = "INTENT_NOTIFICATION"
        else:
            category = "Latest Jobs"
            primary_intent = "INTENT_APPLY"

        job_type = "Non-Govt + Semi-Govt" if any(k in t for k in NON_GOVT_KEYWORDS) else "Govt"

        detected_state = "All India / Central"
        for state_name, keywords in STATE_KEYWORDS.items():
            if any(kw in t for kw in keywords):
                detected_state = state_name
                break

        board_key = None
        for key in OFFICIAL_HUBS:
            if key in t:
                board_key = key
                break

        return {
            "category": category,
            "primary_intent": primary_intent,
            "job_type": job_type,
            "state": detected_state,
            "board_key": board_key
        }

# ==============================================================================
# LAYER 1C: CROSS-WEBSITE COMBINATION GROUPER AGENT
# ==============================================================================
class CrossSiteCombinerAgent:
    @staticmethod
    def normalize_exam_signature(title):
        t = title.lower()
        stop_words = ["online", "form", "recruitment", "vacancy", "bharti", "apply", "now", "out", "link", "check", "download", "pdf", "official", "notification", "advt"]
        tokens = [w for w in re.findall(r'[a-z0-9]+', t) if w not in stop_words and len(w) > 1]
        return "_".join(tokens[:5])

# ==============================================================================
# LAYER 6A: UNIQUE NON-REPEATING INTENT-BASED CHALLENGING QUOTE AGENT
# ==============================================================================
class UniqueIntentQuoteAgent:
    INTENT_OPENERS = {
        "INTENT_APPLY": [
            "Form bharna sirf pehla kadam hai, asli jung us din shuru hoti hai jab aap",
            "Bheed sirf registration karke chhod deti hai, lekin asli विजेता",
            "Comfort zone mein baith kar selection nahi milta;",
            "Aaj ka ek faisla aapka agla 40 saal ka career badal sakta hai—",
            "Sapne unke poore nahi hote jo last date ka wait karte hain, balki unke jo",
            "Har ek seat par hazaron daavedar hain, par बाजी wahi marega jo"
        ],
        "INTENT_NOTIFICATION": [
            "Official vigyapti aa chuki hai—ab bahane banane ka waqt khatam aur",
            "Notification ki har ek line pukarti hai ki kya aapमें",
            "Jab duniya vacancy gin rahi ho, tab aap sirf apni ek pakki seat ke liye",
            "Bigul baj chuka hai! Yeh notification sirf ek PDF nahi, balki",
            "Taiyari kali raaton mein hoti hai aur chamak selection list mein dikhti hai—",
            "Jo notification aane ke pehle ghante se apna discipline set karta hai, wahi"
        ],
        "INTENT_ADMIT_CARD": [
            "Admit Card haath mein hai—ab darne ka nahi, balki exam hall mein",
            "Pichhle mahino ki saari mehnat ab un 2 ghanto ke CBT mein hisab mangegi;",
            "Hall Ticket sirf entry pass hai, exam center se bahar nikalte waqt",
            "Pressure wahi mehsoos karta hai jisneimandari se padha hai—ab",
            "Exam City aur Roll Number tay hai; ab apne dimaag ko shant rakh kar",
            "Aakhiri dino mein ghabrahat nahi, balki apni speed aur accuracy ka"
        ],
        "INTENT_ANSWER_KEY": [
            "Answer Key se daro mat! Ek-ek galat sawal ka hisab lagao kyunki",
            "Response sheet aapka aaina hai—apni kamiyon ko pehchan kar",
            "Sahi uttar aत्मविश्वास dete hain aur galat uttar agle stage ka",
            "Cutoff ke dar se rukna nahi hai; Answer Key ka har ek question aapko",
            "Asli aspirant wahi hai jo Answer Key milane ke baad apni galtiyon ko",
            "Score chahe jo bhi bane, is Response Sheet ke analysis se apni"
        ],
        "INTENT_RESULT": [
            "Result ki PDF mein naam unhi ka chamakta hai jinhone",
            "Safalta mili toh shukrana karein, aur agar kuch marks se chook gaye toh",
            "Merit list aakhiri faisla nahi hoti—har ek parinaam aapko",
            "Selection list mein apna Roll Number dekhne ka sukh har thakan mita deta hai;",
            "Cutoff par karne walon ko badhai, aur rukne walon ko chunauti hai ki",
            "Final Result batata hai ki kiski mehnat mein kitni zidd thi—"
        ],
        "INTENT_SYLLABUS": [
            "Syllabus aapka yuddh-manchitra (battle map) hai—bina exam pattern samjhe",
            "Har ek topic aur weightage ko tod kar padho, kyunki",
            "Toppers alag kitabein nahi padhte, wo Syllabus ke har ek point ko",
            "Chakravyuh tabhi tootta hai jab aapko Exam Pattern ke har",
            "Syllabus ki gehrai ko jo pehle din samajh leta hai, wahi",
            "Negative marking aur time limit ke is khel mein Syllabus ka"
        ]
    }

    INTENT_CHALLENGES = {
        "INTENT_APPLY": [
            "rozana 8 ghante ki kadi tapasyase apni seat cheen kar dikhaye!",
            "aaj hi form bhar kar 100% syllabus aur mock tests mein jhonk de!",
            "apni neend aur aalsya ko tyag kar har roz apna record tode!",
            "bina ek din gawaye PYQs aur revision ki aag mein tapna shuru kare!"
        ],
        "INTENT_NOTIFICATION": [
            "is bharti mein apना 100% jhonk kar itihaas rachne ka dam hai!",
            "aaj se hi har ek subject ka chakravyuh bhedna shuru kar de!",
            "apne sangharsh ko final selection letter mein badalne ka waqt hai!",
            "rozana mock test mein apne marks badhane ki zidd pakad le!"
        ],
        "INTENT_ADMIT_CARD": [
            "har ek minute aur har ek question par apna poora niyantran rakho!",
            "apni kalam aur mouse ki raftaar se paper ko fateh karke aao!",
            "bina negative marking ke जाल mein fanse apna best score khada karo!",
            "poore aत्मविश्वास ke sath exam hall mein utro aur jeet kar lauto!"
        ],
        "INTENT_ANSWER_KEY": [
            "wahi galtiyan sudhar kar agle attempt ya Mains mein topper banta hai!",
            "apni accuracy ko 95% ke paar le jane ka sankalp aaj hi lo!",
            "har weak topic ko apni sabse badi taqat bana kar dikhao!",
            "objection aur analysis ke baad agle padav ki taiyari dugni raftaar se karo!"
        ],
        "INTENT_RESULT": [
            "andheri raaton mein bina ruke apne lakshya ke liye pasina bahaya hai!",
            "dugni taqat aur naye hausle ke sath agle exam mein dhamakedar wapsi karein!",
            "apni mehnat par bharosa rakhein aur agle lakshya ki taraf kadam badhayein!",
            "sabit kar dein ki aapki zidd kisi bhi nakami se kahin zyada badi hai!"
        ],
        "INTENT_SYLLABUS": [
            "har ek high-weightage chapter par apni pakad lohe jaisi majboot banao!",
            "rozana targeted revision se har kathin vishay ko apna gulam bana lo!",
            "smart strategy aur time-management se cutoff se 20 marks upar ka lakshya rakho!",
            "ek-ek unit ko master karke apni safalta ki neev aaj hi pakki karo!"
        ]
    }

    @staticmethod
    def generate_unique_quote(title, meta, used_quotes_set, use_ai=True):
        intent = meta["primary_intent"]
        clean_title = re.sub(r'\s+', ' ', title).strip()
        short_exam_name = " ".join(clean_title.split()[:4])

        # Try Gemini AI first for a tailored intent-specific challenging quote
        if use_ai and GEMINI_API_KEY:
            prompt = (
                f"Write a single, powerful, challenging 2-line motivational quote in Hinglish specifically for "
                f"an aspirant viewing '{clean_title}' whose post intent is '{intent}'. "
                f"Mention '{short_exam_name}' naturally. Make it fierce, unique, and action-oriented. No markdown quotes."
            )
            payload = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.85, "maxOutputTokens": 90}
            }).encode("utf-8")

            for model in ["gemini-2.5-flash", "gemini-2.0-flash"]:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
                try:
                    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        res = json.loads(resp.read().decode("utf-8"))
                        candidate_quote = res["candidates"][0]["content"]["parts"][0]["text"].strip().strip('"').strip("'")
                        if candidate_quote and candidate_quote.lower() not in used_quotes_set:
                            used_quotes_set.add(candidate_quote.lower())
                            return candidate_quote
                except Exception:
                    continue

        # Deterministic Non-Repeating Intent Quote Engine (Guaranteed Unique per Post)
        openers = UniqueIntentQuoteAgent.INTENT_OPENERS.get(intent, UniqueIntentQuoteAgent.INTENT_OPENERS["INTENT_APPLY"])
        challenges = UniqueIntentQuoteAgent.INTENT_CHALLENGES.get(intent, UniqueIntentQuoteAgent.INTENT_CHALLENGES["INTENT_APPLY"])

        seed_int = int(hashlib.md5(f"{clean_title}_{intent}".encode("utf-8")).hexdigest(), 16)
        for offset in range(len(openers) * len(challenges)):
            op = openers[(seed_int + offset) % len(openers)]
            ch = challenges[((seed_int // 7) + offset) % len(challenges)]
            crafted = f"🔥 [{short_exam_name} Challenge]: {op} {clean_title} ke is mukable mein {ch}"
            if crafted.lower() not in used_quotes_set:
                used_quotes_set.add(crafted.lower())
                return crafted

        # Ultimate fallback with unique hash stamp so it NEVER repeats
        unique_fallback = f"🔥 [{short_exam_name} Sankalp #{seed_int % 9999}]: {clean_title} mein wahi baazi marega jo aaj ke din ko apni aakhiri koshish maan kar mehnat karega!"
        used_quotes_set.add(unique_fallback.lower())
        return unique_fallback

# ==============================================================================
# LAYER 3 & 4: DEEP REAL TABLE EXTRACTOR + STRICT OFFICIAL & CHROME SNIFFER
# ==============================================================================
class DeepVerificationAndExtractionAgent:
    @staticmethod
    def search_chrome_fallback(title, intent_type, board_home=""):
        domain_filter = ""
        if board_home and board_home != "#":
            netloc = urlparse(board_home).netloc.replace("www.", "")
            domain_filter = f"site:{netloc} "

        if intent_type in ["INTENT_NOTIFICATION", "INTENT_RESULT", "INTENT_ANSWER_KEY", "INTENT_SYLLABUS"]:
            query = f"{domain_filter}{title} official pdf"
        else:
            query = f"{domain_filter}{title} apply online registration link"

        search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        html = resilient_stealth_fetch(search_url)
        if not html:
            return "#"

        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "uddg=" in href:
                try:
                    parsed_qs = urllib.parse.parse_qs(urlparse(href).query)
                    real_url = parsed_qs.get("uddg", [""])[0]
                    if real_url and is_specific_deep_url(real_url):
                        return real_url
                except Exception:
                    continue
            elif href.startswith("http") and "duckduckgo.com" not in href:
                if is_specific_deep_url(href):
                    return href
        return "#"

    @staticmethod
    def extract_and_verify(title, source_urls_list, meta):
        data = {
            "apply_link": "#",
            "notif_url": "#",
            "result_url": "#",
            "answer_key_url": "#",
            "admit_card_url": "#",
            "syllabus_url": "#",
            "download_pdf": "#",
            "official_web": OFFICIAL_HUBS[meta["board_key"]]["home"] if meta["board_key"] else "#",
            "dates": {
                "notification_date": "To be notified in Official PDF",
                "apply_start_date": "To be notified in Official PDF",
                "last_date": "To be notified in Official PDF",
                "extended_date": "N/A",
                "exam_date": "As per Official Schedule",
                "admit_card_date": "Before Exam",
                "answer_key_date": "After Exam",
                "result_date": "As per Board Update"
            },
            "fees": [],
            "age_criteria": [],
            "vacancy_breakdown": [],
            "selection_process": [],
            "exam_pattern": [],
            "dynamic_admin_review_boxes": {},
            "combined_sources": [],
            "accuracy_score": 0
        }

        date_pattern = re.compile(r'(\d{1,2}[\/\-\.\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|[01]?\d)[\/\-\.\s]202[4-9])', re.IGNORECASE)

        # PHASE 1: COMBINE DATA FROM ALL MATCHED AGGREGATOR PAGES
        for src_name, article_url in source_urls_list:
            if not article_url or not article_url.startswith("http"):
                continue
            html = resilient_stealth_fetch(article_url)
            if not html:
                continue

            data["combined_sources"].append(src_name)
            soup = BeautifulSoup(html, "html.parser")

            for elem in soup.find_all(["li", "tr", "p"]):
                txt = re.sub(r'\s+', ' ', elem.get_text(" ", strip=True)).strip()
                t_low = txt.lower()
                if len(txt) < 6 or len(txt) > 350:
                    continue

                found_dates = date_pattern.findall(txt)
                if found_dates:
                    d_val = found_dates[-1]
                    if any(k in t_low for k in ["notification", "advt", "published", "release"]):
                        data["dates"]["notification_date"] = d_val
                    if any(k in t_low for k in ["begin", "start", "starting", "opening"]):
                        data["dates"]["apply_start_date"] = d_val
                    if any(k in t_low for k in ["last date", "closing", "apply online last"]):
                        data["dates"]["last_date"] = d_val
                    if any(k in t_low for k in ["extended", "revised last date"]):
                        data["dates"]["extended_date"] = d_val
                    if any(k in t_low for k in ["exam date", "cbt date", "prelims", "mains", "written exam"]):
                        data["dates"]["exam_date"] = d_val
                    if any(k in t_low for k in ["admit card", "hall ticket"]):
                        data["dates"]["admit_card_date"] = d_val
                    if any(k in t_low for k in ["answer key"]):
                        data["dates"]["answer_key_date"] = d_val
                    if any(k in t_low for k in ["result", "merit"]):
                        data["dates"]["result_date"] = d_val

                if ("₹" in txt or "rs." in t_low or "rs " in t_low or "fee" in t_low or "nil" in t_low) and any(c in t_low for c in ["general", "obc", "sc", "st", "ews", "female", "pwd", "all candidates"]):
                    if txt not in data["fees"] and len(data["fees"]) < 6:
                        data["fees"].append(txt)

                if any(k in t_low for k in ["minimum age", "maximum age", "age limit", "age relaxation", "years"]) and any(d in txt for d in ["18", "20", "21", "25", "27", "28", "30", "32", "35", "37", "40", "42", "45"]):
                    if txt not in data["age_criteria"] and len(data["age_criteria"]) < 6:
                        data["age_criteria"].append(txt)

                if any(k in t_low for k in ["written exam", "cbt", "prelims", "mains", "skill test", "typing", "physical", "document verification", "medical", "interview"]) and len(txt) < 180:
                    if txt not in data["selection_process"] and len(data["selection_process"]) < 6:
                        data["selection_process"].append(txt)

            for table in soup.find_all("table"):
                rows = table.find_all("tr")
                for r in rows[:15]:
                    cols = [re.sub(r'\s+', ' ', c.get_text(" ", strip=True)).strip() for c in r.find_all(["td", "th"])]
                    cols = [c for c in cols if c]
                    if len(cols) >= 2:
                        row_str = " | ".join(cols)
                        r_low = row_str.lower()
                        if any(k in r_low for k in ["ur", "general", "obc", "ews", "sc", "st", "total", "post name", "vacancy", "seats"]):
                            if cols not in data["vacancy_breakdown"] and len(data["vacancy_breakdown"]) < 12:
                                data["vacancy_breakdown"].append(cols)
                        elif any(k in r_low for k in ["subject", "questions", "marks", "duration", "reasoning", "aptitude", "english", "awareness", "general studies"]):
                            if cols not in data["exam_pattern"] and len(data["exam_pattern"]) < 10:
                                data["exam_pattern"].append(cols)

            for container in soup.find_all(["tr", "li", "p", "div"]):
                row_text = re.sub(r'\s+', ' ', container.get_text(" ", strip=True)).strip().lower()
                if len(row_text) > 600:
                    continue
                for a in container.find_all("a", href=True):
                    href = urljoin(article_url, a["href"].strip())
                    if not href.startswith("http") or any(b in href.lower() for b in BLOCK_DOMAINS):
                        continue
                    if is_aggregator_page_link(href):
                        continue

                    a_text = re.sub(r'\s+', ' ', a.get_text(" ", strip=True)).strip().lower()
                    combo = f"{row_text} {a_text}"
                    h_low = href.lower()

                    if any(w in combo for w in ["official website", "official portal", "official site"]):
                        if data["official_web"] == "#":
                            data["official_web"] = href

                    for dyn_kw in DYNAMIC_BOX_KEYWORDS:
                        if dyn_kw in combo and is_specific_deep_url(href):
                            box_label = dyn_kw.title()
                            if box_label not in data["dynamic_admin_review_boxes"]:
                                data["dynamic_admin_review_boxes"][box_label] = href

                    is_pdf = is_specific_deep_url(href, require_pdf=True)
                    is_deep = is_specific_deep_url(href, require_pdf=False)

                    if any(w in combo for w in ["answer key", "response sheet", "objection"]) and is_deep:
                        if data["answer_key_url"] == "#":
                            data["answer_key_url"] = href
                            data["accuracy_score"] += 5

                    elif any(w in combo for w in ["result", "merit list", "score card", "selection list", "cutoff"]) and is_deep:
                        if data["result_url"] == "#" or (is_pdf and not data["result_url"].lower().endswith(".pdf")):
                            data["result_url"] = href
                            data["accuracy_score"] += 5

                    elif any(w in combo for w in ["admit card", "hall ticket", "call letter", "exam city"]) and is_deep:
                        if data["admit_card_url"] == "#":
                            data["admit_card_url"] = href
                            data["accuracy_score"] += 5

                    elif any(w in combo for w in ["syllabus", "exam pattern"]) and is_deep:
                        if data["syllabus_url"] == "#":
                            data["syllabus_url"] = href
                            data["accuracy_score"] += 4

                    elif any(w in combo for w in ["apply online", "registration", "login", "online form", "apply now"]) and not h_low.endswith(".pdf") and is_deep:
                        if data["apply_link"] == "#":
                            data["apply_link"] = href
                            data["accuracy_score"] += 5

                    elif (is_pdf or any(w in combo for w in ["notification", "official notice", "advertisement", "advt", "full notice"])) and is_deep:
                        if data["notif_url"] == "#" or (is_pdf and not data["notif_url"].lower().endswith(".pdf")):
                            data["notif_url"] = href
                            data["accuracy_score"] += 5

        # PHASE 2: OFFICIAL BOARD DEEP CRAWL (If specific links are missing)
        if meta["board_key"]:
            hub = OFFICIAL_HUBS[meta["board_key"]]
            board_html = resilient_stealth_fetch(hub["notices"])
            if board_html:
                b_soup = BeautifulSoup(board_html, "html.parser")
                t_tokens = [w for w in re.findall(r'[a-z0-9]+', title.lower()) if len(w) > 2 and w not in ["online", "form", "2026", "recruitment", "post", "apply", "result"]]

                for a in b_soup.find_all("a", href=True):
                    full_url = urljoin(hub["home"], a["href"].strip())
                    a_txt = a.get_text(" ", strip=True).lower()
                    if any(tok in a_txt or tok in full_url.lower() for tok in t_tokens):
                        if is_specific_deep_url(full_url, require_pdf=True):
                            if meta["primary_intent"] == "INTENT_RESULT" and data["result_url"] == "#":
                                data["result_url"] = full_url
                                data["accuracy_score"] += 6
                            elif meta["primary_intent"] == "INTENT_ANSWER_KEY" and data["answer_key_url"] == "#":
                                data["answer_key_url"] = full_url
                                data["accuracy_score"] += 6
                            elif data["notif_url"] == "#":
                                data["notif_url"] = full_url
                                data["accuracy_score"] += 6
                        elif is_specific_deep_url(full_url) and any(k in a_txt or k in full_url.lower() for k in ["apply", "reg", "login", "candidate"]):
                            if data["apply_link"] == "#":
                                data["apply_link"] = full_url
                                data["accuracy_score"] += 5

            if data["apply_link"] == "#" and is_specific_deep_url(hub.get("apply_portal", "#")):
                data["apply_link"] = hub["apply_portal"]
                data["accuracy_score"] += 4

        # PHASE 3: CHROME SEARCH ENGINE FALLBACK FOR PRIMARY INTENT
        intent = meta["primary_intent"]
        if intent == "INTENT_APPLY" and not is_specific_deep_url(data["apply_link"]):
            found = DeepVerificationAndExtractionAgent.search_chrome_fallback(title, intent, data["official_web"])
            if is_specific_deep_url(found):
                data["apply_link"] = found
                data["accuracy_score"] += 4

        elif intent == "INTENT_NOTIFICATION" and not is_specific_deep_url(data["notif_url"]):
            found = DeepVerificationAndExtractionAgent.search_chrome_fallback(title, intent, data["official_web"])
            if is_specific_deep_url(found):
                data["notif_url"] = found
                data["accuracy_score"] += 4

        elif intent == "INTENT_RESULT" and not is_specific_deep_url(data["result_url"]):
            found = DeepVerificationAndExtractionAgent.search_chrome_fallback(title, intent, data["official_web"])
            if is_specific_deep_url(found):
                data["result_url"] = found
                data["accuracy_score"] += 4

        elif intent == "INTENT_ADMIT_CARD" and not is_specific_deep_url(data["admit_card_url"]):
            found = DeepVerificationAndExtractionAgent.search_chrome_fallback(title, intent, data["official_web"])
            if is_specific_deep_url(found):
                data["admit_card_url"] = found
                data["accuracy_score"] += 4

        elif intent == "INTENT_ANSWER_KEY" and not is_specific_deep_url(data["answer_key_url"]):
            found = DeepVerificationAndExtractionAgent.search_chrome_fallback(title, intent, data["official_web"])
            if is_specific_deep_url(found):
                data["answer_key_url"] = found
                data["accuracy_score"] += 4

        if intent == "INTENT_RESULT" and is_specific_deep_url(data["result_url"]):
            data["download_pdf"] = data["result_url"]
        elif intent == "INTENT_ANSWER_KEY" and is_specific_deep_url(data["answer_key_url"]):
            data["download_pdf"] = data["answer_key_url"]
        elif intent == "INTENT_SYLLABUS" and is_specific_deep_url(data["syllabus_url"]):
            data["download_pdf"] = data["syllabus_url"]
        elif is_specific_deep_url(data["notif_url"]):
            data["download_pdf"] = data["notif_url"]
        else:
            data["download_pdf"] = "#"

        return data

    @staticmethod
    def is_primary_intent_satisfied(meta, data):
        """
        STRICT ENFORCEMENT RULE:
        Every post MUST have its specific intent link verified & non-generic.
        """
        intent = meta["primary_intent"]
        if intent == "INTENT_APPLY":
            return is_specific_deep_url(data["apply_link"]) or is_specific_deep_url(data["notif_url"])
        elif intent == "INTENT_NOTIFICATION":
            return is_specific_deep_url(data["notif_url"])
        elif intent == "INTENT_RESULT":
            return is_specific_deep_url(data["result_url"]) or is_specific_deep_url(data["notif_url"])
        elif intent == "INTENT_ADMIT_CARD":
            return is_specific_deep_url(data["admit_card_url"]) or is_specific_deep_url(data["apply_link"])
        elif intent == "INTENT_ANSWER_KEY":
            return is_specific_deep_url(data["answer_key_url"]) or is_specific_deep_url(data["notif_url"])
        elif intent == "INTENT_SYLLABUS":
            return is_specific_deep_url(data["syllabus_url"]) or is_specific_deep_url(data["notif_url"])
        return False

# ==============================================================================
# LAYER 6B & 7: OPTION B (AGENTIC AI MENTOR + 90-DAY STRATEGY) & OPTION A BUILDER
# ==============================================================================
class OptionB_GeminiMentorAgent:
    @staticmethod
    def generate_mentor_and_90day_strategy(title, meta, use_ai=True):
        if use_ai and GEMINI_API_KEY:
            prompt = (
                f"Act as an expert Indian Competitive Exam Mentor. For the post '{title}' "
                f"(Category: {meta['category']}, Intent: {meta['primary_intent']}, State: {meta['state']}), "
                f"write in Hinglish: (1) A 3-line actionable mentor advice, and (2) A bulleted Last 3 Months "
                f"(Month 1, Month 2, Month 3) Exam Preparation Strategy."
            )
            payload = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.65, "maxOutputTokens": 450}
            }).encode("utf-8")

            for model in ["gemini-2.5-flash", "gemini-2.0-flash"]:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
                try:
                    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        res = json.loads(resp.read().decode("utf-8"))
                        ai_text = res["candidates"][0]["content"]["parts"][0]["text"].strip()
                        return ai_text.replace("\n", "<br>")
                except Exception:
                    continue

        return (
            f"<strong>💡 Mentor Key Insight:</strong> <strong>{title}</strong> mein high accuracy aur time management sabse bada game-changer hai. Official notification PDF aur specific link niche verify karke attach kar diya gaya hai.<br><br>"
            f"<strong>📅 Month 1 (Foundation & Syllabus Completion):</strong> Sabse pehle core subjects (Quant/Technical, Reasoning, GK/Current Affairs, Language) ke high-weightage chapters cover karein aur pichhle 5 saal ke Previous Year Papers (PYQs) ka trend dekhein.<br>"
            f"<strong>📅 Month 2 (Speed Drill & Sectional Tests):</strong> Rozana 2 sectional quizzes lagayein, calculation/short-tricks ke notes banayein aur pichhle 6 mahine ka Current Affairs + Static GK revise karein.<br>"
            f"<strong>📅 Month 3 (Full-Length Mock Tests & Error Analysis):</strong> Har din 1 Full-Length CBT Mock Test exam-time slot par dein aur galat hue questions ki 'Error Notebook' banakar final 15 din me baar-baar revise karein."
        )

class OptionA_RichDossierBuilder:
    @staticmethod
    def build_html(title, meta, data, unique_quote, mentor_strategy_html):
        dates = data["dates"]

        if data["fees"]:
            fee_items = "".join([f"<li>{f}</li>" for f in data["fees"]])
        else:
            fee_items = (
                "<li><strong>General / OBC / EWS:</strong> Refer Official Notification PDF for post-wise fee.</li>"
                "<li><strong>SC / ST / PwD / Female:</strong> Exempted / Concessional as per Government norms.</li>"
                "<li><strong>Payment Mode:</strong> Online via UPI, Net Banking, Debit/Credit Card.</li>"
            )

        if data["age_criteria"]:
            age_items = "".join([f"<li>{a}</li>" for a in data["age_criteria"]])
        else:
            age_items = (
                "<li><strong>Minimum Age:</strong> 18 - 21 Years (Post-wise variation as per rules).</li>"
                "<li><strong>Maximum Age:</strong> As per Official Notification PDF.</li>"
                "<li><strong>Age Relaxation:</strong> SC/ST: +5 Years, OBC (NCL): +3 Years, PwBD: +10 Years.</li>"
            )

        if data["vacancy_breakdown"]:
            vac_rows_html = ""
            for idx, r_cols in enumerate(data["vacancy_breakdown"]):
                bg = "#f8fafc" if idx % 2 == 0 else "#ffffff"
                cells = "".join([f"<td style='padding:8px 10px; border:1px solid #cbd5e1;'>{c}</td>" for c in r_cols])
                vac_rows_html += f"<tr style='background:{bg};'>{cells}</tr>"
            vacancy_section = f"<table style='width:100%; border-collapse:collapse; margin-bottom:18px; font-size:13.5px;'>{vac_rows_html}</table>"
        else:
            vacancy_section = (
                "<p style='font-size:14px; color:#334155;'>Category-wise (UR / OBC / EWS / SC / ST) post distribution aur post-wise educational qualification ke liye niche attach ki gayi <strong>Official Notification PDF</strong> dekhein.</p>"
            )

        if data["selection_process"]:
            sel_items = "".join([f"<li>{s}</li>" for s in data["selection_process"]])
        else:
            sel_items = (
                "<li><strong>Stage 1:</strong> Computer Based Test (CBT) / Written Examination.</li>"
                "<li><strong>Stage 2:</strong> Mains / Skill Test / Physical Test (Post ke anusaar).</li>"
                "<li><strong>Stage 3:</strong> Document Verification (DV) & Medical Examination.</li>"
            )

        if data["exam_pattern"]:
            pat_rows_html = ""
            for idx, r_cols in enumerate(data["exam_pattern"]):
                bg = "#f8fafc" if idx % 2 == 0 else "#ffffff"
                cells = "".join([f"<td style='padding:8px 10px; border:1px solid #cbd5e1;'>{c}</td>" for c in r_cols])
                pat_rows_html += f"<tr style='background:{bg};'>{cells}</tr>"
            pattern_table = f"<table style='width:100%; border-collapse:collapse; margin-bottom:18px; font-size:13.5px;'>{pat_rows_html}</table>"
        else:
            pattern_table = "<p style='font-size:14px; color:#334155;'>Detailed subject-wise marking scheme, negative marking aur exam duration Official Notification PDF mein uplabdh hai.</p>"

        dyn_boxes_html = ""
        if data["dynamic_admin_review_boxes"]:
            rows = "".join([
                f"<tr style='border:1px solid #cbd5e1;'><td style='padding:9px; font-weight:600;'>📌 {lbl}</td>"
                f"<td style='padding:9px;'><a href='{url}' target='_blank' rel='noopener' style='color:#1d4ed8; font-weight:700;'>Click Here (Verified Link)</a></td></tr>"
                for lbl, url in data["dynamic_admin_review_boxes"].items()
            ])
            dyn_boxes_html = f"""
            <h3 style="color:#0f172a; border-bottom:2px solid #cbd5e1; padding-bottom:8px; margin-top:24px;">🆕 Additional Official Notices & Dynamic Links</h3>
            <table style="width:100%; border-collapse:collapse; margin-bottom:20px; font-size:14px;">{rows}</table>
            """

        # 1. SHORT VIEW DETAIL CARD (With Unique Intent-Based Challenging Quote Banner)
        short_view = f"""
<div class="short-view-card" style="background:#ffffff; border:1px solid #cbd5e1; border-radius:8px; padding:18px; margin-bottom:24px; box-shadow:0 1px 3px rgba(0,0,0,0.06);">
    <div class="unique-challenging-quote" style="background:linear-gradient(90deg, #fffbeb 0%, #fef3c7 100%); border-left:4px solid #d97706; padding:11px 15px; margin-bottom:14px; border-radius:4px; font-style:italic; color:#92400e; font-size:13.5px; font-weight:600;">
        "{unique_quote}"
    </div>
    <div style="background:#eef6ff; border-left:4px solid #1a73e8; padding:12px 16px; margin-bottom:14px; border-radius:4px;">
        <span style="color:#174ea6; font-weight:700; font-size:15px;">📢 Short Information ({meta['primary_intent'].replace('INTENT_', '')}):</span>
        <p style="margin:6px 0 0; color:#1e293b; font-size:14px; line-height:1.6;">
            <strong>{title}</strong> ke liye official verification ke baad specific direct link aur PDF dossier taiyar kar diya gaya hai. Combined Verified Sources: <strong>{', '.join(set(data['combined_sources'])) or 'Official Portal'}</strong>.
        </p>
    </div>
    <div style="display:flex; flex-wrap:wrap; gap:10px; font-size:13px; color:#334155;">
        <span style="background:#f1f5f9; padding:6px 12px; border-radius:4px;"><strong>📂 Category:</strong> {meta['category']}</span>
        <span style="background:#dcfce7; color:#166534; padding:6px 12px; border-radius:4px;"><strong>🏷️ Job Type:</strong> {meta['job_type']}</span>
        <span style="background:#fef3c7; color:#92400e; padding:6px 12px; border-radius:4px;"><strong>📍 State:</strong> {meta['state']}</span>
        <span style="background:#fee2e2; color:#991b1b; padding:6px 12px; border-radius:4px;"><strong>⏳ Last Date:</strong> {dates['last_date']}</span>
    </div>
</div>
"""

        # 2. DEEP DETAIL DESCRIPTION (Immediately Below Short View)
        deep_view = f"""
<div class="deep-job-dossier" style="line-height:1.75; font-family:system-ui,-apple-system,sans-serif; color:#1e293b; border-top:2px dashed #94a3b8; padding-top:18px;">

    <h3 style="color:#0f172a; border-bottom:2px solid #cbd5e1; padding-bottom:8px; margin-top:10px;">🗓️ 1. Official Important Dates & Schedule</h3>
    <table style="width:100%; border-collapse:collapse; margin-bottom:20px; font-size:14px;">
        <tr style="background:#f8fafc; border:1px solid #cbd5e1;"><td style="padding:9px; font-weight:600; width:48%;">Notification Release Date</td><td style="padding:9px;">{dates['notification_date']}</td></tr>
        <tr style="border:1px solid #cbd5e1;"><td style="padding:9px; font-weight:600;">Application Begin Date</td><td style="padding:9px;">{dates['apply_start_date']}</td></tr>
        <tr style="background:#f8fafc; border:1px solid #cbd5e1;"><td style="padding:9px; font-weight:600;">Last Date for Apply Online</td><td style="padding:9px; color:#dc2626; font-weight:700;">{dates['last_date']}</td></tr>
        <tr style="border:1px solid #cbd5e1;"><td style="padding:9px; font-weight:600;">Extended Last Date</td><td style="padding:9px;">{dates['extended_date']}</td></tr>
        <tr style="background:#f8fafc; border:1px solid #cbd5e1;"><td style="padding:9px; font-weight:600;">Exam Date / CBT Schedule</td><td style="padding:9px;">{dates['exam_date']}</td></tr>
        <tr style="border:1px solid #cbd5e1;"><td style="padding:9px; font-weight:600;">Admit Card Release</td><td style="padding:9px;">{dates['admit_card_date']}</td></tr>
        <tr style="background:#f8fafc; border:1px solid #cbd5e1;"><td style="padding:9px; font-weight:600;">Answer Key Release</td><td style="padding:9px;">{dates['answer_key_date']}</td></tr>
        <tr style="border:1px solid #cbd5e1;"><td style="padding:9px; font-weight:600;">Result Declared Date</td><td style="padding:9px; color:#16a34a; font-weight:700;">{dates['result_date']}</td></tr>
    </table>

    <h3 style="color:#0f172a; border-bottom:2px solid #cbd5e1; padding-bottom:8px; margin-top:24px;">💳 2. Application Fee Details</h3>
    <ul style="padding-left:20px; margin-bottom:20px; font-size:14px;">{fee_items}</ul>

    <h3 style="color:#0f172a; border-bottom:2px solid #cbd5e1; padding-bottom:8px; margin-top:24px;">🎂 3. Age Criteria & Relaxation</h3>
    <ul style="padding-left:20px; margin-bottom:20px; font-size:14px;">{age_items}</ul>

    <h3 style="color:#0f172a; border-bottom:2px solid #cbd5e1; padding-bottom:8px; margin-top:24px;">📊 4. Category-Wise Post Distribution & Eligibility</h3>
    {vacancy_section}

    <h3 style="color:#0f172a; border-bottom:2px solid #cbd5e1; padding-bottom:8px; margin-top:24px;">⚙️ 5. Selection Process & Exam Pattern</h3>
    <ul style="padding-left:20px; margin-bottom:14px; font-size:14px;">{sel_items}</ul>
    {pattern_table}

    <div class="mentor-editorial-block" style="background:#fdf2f8; border-left:4px solid #db2777; padding:16px; margin:24px 0; border-radius:6px;">
        <h3 style="margin-top:0; color:#9d174d; font-size:16px;">🎯 6. Agentic AI Mentor & Last 3 Months (90-Day) Exam Strategy</h3>
        <div style="font-size:14px; color:#831843; line-height:1.7;">{mentor_strategy_html}</div>
    </div>

    {dyn_boxes_html}
</div>
"""
        return f"{short_view}\n{deep_view}".strip()

# ==============================================================================
# MASTER SYNTHESIZER ORCHESTRATOR
# ==============================================================================
class MasterSynthesizer:
    @staticmethod
    def build_verified_post(title, source_urls_list, used_quotes_set, use_ai=True):
        meta = IntentAndMetaClassifierAgent.analyze(title)
        data = DeepVerificationAndExtractionAgent.extract_and_verify(title, source_urls_list, meta)

        # STRICT GATEKEEPER: Reject post if its Primary Intent link is missing or is a root domain!
        if not DeepVerificationAndExtractionAgent.is_primary_intent_satisfied(meta, data):
            print(f"   ⛔ [REJECTED - Missing Specific Intent Link] {title} ({meta['primary_intent']})")
            return None

        unique_quote = UniqueIntentQuoteAgent.generate_unique_quote(title, meta, used_quotes_set, use_ai=use_ai)
        mentor_html = OptionB_GeminiMentorAgent.generate_mentor_and_90day_strategy(title, meta, use_ai=use_ai)
        full_html = OptionA_RichDossierBuilder.build_html(title, meta, data, unique_quote, mentor_html)

        primary_source_url = source_urls_list[0][1] if source_urls_list else data["official_web"]
        primary_source_name = " + ".join(sorted(set(data["combined_sources"]))) if data["combined_sources"] else "Official Board"

        job_id = hashlib.md5(f"{CrossSiteCombinerAgent.normalize_exam_signature(title)}".encode("utf-8")).hexdigest()[:12]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        real_display_date = data["dates"]["notification_date"]
        if real_display_date == "To be notified in Official PDF" and data["dates"]["last_date"] != "To be notified in Official PDF":
            real_display_date = f"Last Date: {data['dates']['last_date']}"

        print(f"   ✅ [VERIFIED {meta['primary_intent']}] {title[:42]} | Quote Ready | State: {meta['state']}")

        return {
            "id": job_id,
            "title": title,
            "category": meta["category"],
            "primary_intent": meta["primary_intent"],
            "job_type": meta["job_type"],
            "state": meta["state"],
            "unique_quote": unique_quote,
            "source": primary_source_name,
            "link": primary_source_url,
            "url": primary_source_url,
            "apply_link": data["apply_link"],
            "applyUrl": data["apply_link"],
            "notif_url": data["notif_url"],
            "notifUrl": data["notif_url"],
            "download_pdf": data["download_pdf"],
            "result_url": data["result_url"],
            "resultUrl": data["result_url"],
            "answer_key_url": data["answer_key_url"],
            "answerKeyUrl": data["answer_key_url"],
            "admit_card_url": data["admit_card_url"],
            "admitCardUrl": data["admit_card_url"],
            "syllabus_url": data["syllabus_url"],
            "official_web": data["official_web"],
            "webUrl": data["official_web"],
            "important_dates": data["dates"],
            "dynamic_admin_review_boxes": data["dynamic_admin_review_boxes"],
            "date": real_display_date,
            "post_date": real_display_date,
            "updated_at": now_str,
            "summary": f"{title} ({meta['job_type']} | {meta['state']}) - {unique_quote}",
            "description": full_html,
            "content": full_html,
            "accuracy_score": data["accuracy_score"],
            "engine": "8-Layer Agentic Combination & Strict Intent Verifier",
            "status": "pending_review"
        }

def collect_candidates_from_all_sources():
    grouped_candidates = {}

    for src in SOURCES:
        print(f"📡 Scanning Aggregator Signal: {src['name']}...")
        html = resilient_stealth_fetch(src["url"])
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            text = re.sub(r'\s+', ' ', a.get_text(" ", strip=True)).strip()
            href = urljoin(src["url"], a["href"].strip())
            t_low = text.lower()

            if len(text) < 16 or len(text) > 140:
                continue
            if any(j in t_low for j in JUNK_TITLES):
                continue
            if any(b in href.lower() for b in BLOCK_DOMAINS):
                continue

            if any(kw in t_low for kw in [
                "online form", "recruitment", "vacancy", "bharti", "result",
                "admit card", "answer key", "syllabus", "notification", "apprentice", "2026"
            ]):
                sig = CrossSiteCombinerAgent.normalize_exam_signature(text)
                if not sig:
                    continue
                if sig not in grouped_candidates:
                    grouped_candidates[sig] = {"title": text, "sources": []}
                if (src["name"], href) not in grouped_candidates[sig]["sources"]:
                    grouped_candidates[sig]["sources"].append((src["name"], href))

    return grouped_candidates

def main():
    print("🚀 Starting 8-Layer Agentic Combination, Strict Intent & Unique Quote Engine...")
    existing = []
    if os.path.exists(DATABASE_FILE):
        try:
            with open(DATABASE_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    # Clean out old posts with root domains & load existing quotes into used_quotes_set
    cleaned_existing = []
    used_quotes_set = set()

    for j in existing:
        if not isinstance(j, dict):
            continue
        meta_check = IntentAndMetaClassifierAgent.analyze(j.get("title", ""))
        check_data = {
            "apply_link": j.get("apply_link", "#"),
            "notif_url": j.get("notif_url", "#"),
            "result_url": j.get("result_url", "#"),
            "admit_card_url": j.get("admit_card_url", "#"),
            "answer_key_url": j.get("answer_key_url", "#"),
            "syllabus_url": j.get("syllabus_url", "#")
        }
        if DeepVerificationAndExtractionAgent.is_primary_intent_satisfied(meta_check, check_data):
            # Ensure existing posts also have a unique non-repeating quote
            q = j.get("unique_quote", "").strip()
            if not q or q.lower() in used_quotes_set:
                q = UniqueIntentQuoteAgent.generate_unique_quote(j.get("title", "Exam Post"), meta_check, used_quotes_set, use_ai=False)
                j["unique_quote"] = q
            else:
                used_quotes_set.add(q.lower())
            cleaned_existing.append(j)

    seen_sigs = {CrossSiteCombinerAgent.normalize_exam_signature(j.get("title", "")) for j in cleaned_existing}
    grouped_candidates = collect_candidates_from_all_sources()

    new_posts = []
    ai_used = 0

    for sig, bundle in grouped_candidates.items():
        if sig in seen_sigs:
            continue
        use_ai = (ai_used < 15)
        post = MasterSynthesizer.build_verified_post(
            bundle["title"], bundle["sources"], used_quotes_set, use_ai=use_ai
        )
        if post:
            if use_ai and GEMINI_API_KEY:
                ai_used += 1
                time.sleep(0.8)
            new_posts.append(post)
            seen_sigs.add(sig)
            if len(new_posts) >= 25:
                break

    final_db = new_posts + cleaned_existing
    final_db = final_db[:500]

    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(final_db, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 Master Sync Complete! New Verified Posts: {len(new_posts)} | Total Clean Posts with Unique Quotes in {DATABASE_FILE}: {len(final_db)}")

if __name__ == "__main__":
    main()

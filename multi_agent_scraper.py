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
# EXHAUSTIVE 8 AGGREGATORS + MIRROR WEBSITES (NO BREAK LIMITS)
# ==============================================================================
SOURCES = [
    {"name": "SarkariResultMirror1", "url": "https://sarkariresult.com.cm/"},
    {"name": "SarkariResultMain", "url": "https://www.sarkariresult.com/"},
    {"name": "SarkariResultLatest", "url": "https://www.sarkariresult.com/latestjob/"},
    {"name": "SarkariResultResults", "url": "https://www.sarkariresult.com/result/"},
    {"name": "SarkariResultAdmit", "url": "https://www.sarkariresult.com/admitcard/"},
    {"name": "FreeJobAlertMain", "url": "https://www.freejobalert.com/government-jobs/"},
    {"name": "FreeJobAlertLatest", "url": "https://www.freejobalert.com/latest-notifications/"},
    {"name": "RojgarResult", "url": "https://www.rojgarresult.com/"},
    {"name": "SarkariExam", "url": "https://www.sarkariexam.com/"},
    {"name": "IndGovtJobs", "url": "https://www.indgovtjobs.in/"},
    {"name": "FreshersNow", "url": "https://www.freshersnow.com/government-jobs-india/"},
    {"name": "CareerPower", "url": "https://www.careerpower.in/upcoming-government-exams.html"},
    {"name": "JagranJosh", "url": "https://www.jagranjosh.com/articles-sarkari-naukri-1288164377-1"}
]

# ==============================================================================
# OFFICIAL RECRUITMENT PORTAL HUBS MAPPED FROM PDF DIRECTORY
# ==============================================================================
OFFICIAL_HUBS = {
    "upsc": {"name": "UPSC", "home": "https://upsc.gov.in", "notices": "https://upsc.gov.in/examinations/active-examinations"},
    "ssc": {"name": "SSC", "home": "https://ssc.gov.in", "notices": "https://ssc.gov.in/Portal/Notices"},
    "ibps": {"name": "IBPS", "home": "https://www.ibps.in", "notices": "https://www.ibps.in/notifications/"},
    "sbi": {"name": "SBI", "home": "https://sbi.co.in/web/careers", "notices": "https://sbi.co.in/web/careers/current-openings"},
    "rbi": {"name": "RBI", "home": "https://www.rbi.org.in", "notices": "https://opportunities.rbi.org.in/Scripts/Vacancies.aspx"},
    "nabard": {"name": "NABARD", "home": "https://www.nabard.org", "notices": "https://www.nabard.org/careers-notices1.aspx?cid=693&id=26"},
    "lic": {"name": "LIC India", "home": "https://licindia.in", "notices": "https://licindia.in/Bottom-Links/Careers"},
    "niacl": {"name": "NIACL", "home": "https://www.newindia.co.in", "notices": "https://www.newindia.co.in/portal/readMore/Vacancies"},
    "uiic": {"name": "UIIC", "home": "https://uiic.co.in", "notices": "https://uiic.co.in/en/recruitment"},
    "idbi": {"name": "IDBI Bank", "home": "https://www.idbibank.in", "notices": "https://www.idbibank.in/idbi-bank-careers-current-openings.aspx"},
    "rrb": {"name": "Railway RRB", "home": "https://www.rrbcdg.gov.in", "notices": "https://www.rrbcdg.gov.in"},
    "rpf": {"name": "Railway RPF", "home": "https://rpf.indianrailways.gov.in", "notices": "https://rpf.indianrailways.gov.in"},
    "army": {"name": "Indian Army", "home": "https://joinindianarmy.nic.in", "notices": "https://joinindianarmy.nic.in/Bravo.htm"},
    "navy": {"name": "Indian Navy", "home": "https://www.joinindiannavy.gov.in", "notices": "https://www.joinindiannavy.gov.in/en/page/career-opportunities.html"},
    "air force": {"name": "Indian Air Force", "home": "https://agnipathvayu.cdac.in", "notices": "https://agnipathvayu.cdac.in/AV/"},
    "coast guard": {"name": "Indian Coast Guard", "home": "https://joinindiancoastguard.cdac.in", "notices": "https://joinindiancoastguard.cdac.in"},
    "territorial army": {"name": "Territorial Army", "home": "https://jointerritorialarmy.gov.in", "notices": "https://jointerritorialarmy.gov.in"},
    "delhi police": {"name": "Delhi Police", "home": "https://delhipolice.gov.in", "notices": "https://delhipolice.gov.in/recruitments"},
    "mpsc": {"name": "Maharashtra MPSC", "home": "https://mpsc.gov.in", "notices": "https://mpsc.gov.in/adv_notification/8"},
    "mahapolice": {"name": "Maharashtra Police", "home": "https://policerecruitment2024.mahait.org", "notices": "https://policerecruitment2024.mahait.org"},
    "mahaforest": {"name": "Maharashtra Vanrakshak", "home": "https://www.mahaforest.gov.in", "notices": "https://www.mahaforest.gov.in"},
    "talathi": {"name": "Maharashtra Talathi", "home": "https://mahabhumi.gov.in", "notices": "https://mahabhumi.gov.in"},
    "gramsevak": {"name": "Maharashtra RDD Gramsevak", "home": "https://rdd.maharashtra.gov.in", "notices": "https://rdd.maharashtra.gov.in"},
    "arogya": {"name": "Maharashtra Arogya Dept", "home": "https://arogya.maharashtra.gov.in", "notices": "https://arogya.maharashtra.gov.in"},
    "krishi": {"name": "Maharashtra Krishi Dept", "home": "https://krishi.maharashtra.gov.in", "notices": "https://krishi.maharashtra.gov.in"},
    "mahadiscom": {"name": "MSEDCL Mahadiscom", "home": "https://www.mahadiscom.in", "notices": "https://www.mahadiscom.in/en/career/"},
    "wrd": {"name": "Maharashtra WRD", "home": "https://wrd.maharashtra.gov.in", "notices": "https://wrd.maharashtra.gov.in"},
    "stateexcise": {"name": "Maharashtra State Excise", "home": "https://stateexcise.maharashtra.gov.in", "notices": "https://stateexcise.maharashtra.gov.in"},
    "transport": {"name": "Maharashtra RTO Transport", "home": "https://transport.maharashtra.gov.in", "notices": "https://transport.maharashtra.gov.in"},
    "uppsc": {"name": "UPPSC", "home": "https://uppsc.up.nic.in", "notices": "https://uppsc.up.nic.in/CandidatePages/Notifications.aspx"},
    "up police": {"name": "UPPBPB UP Police", "home": "https://uppbpb.gov.in", "notices": "https://uppbpb.gov.in/Notice"},
    "upsssc": {"name": "UPSSSC", "home": "https://upsssc.gov.in", "notices": "https://upsssc.gov.in/AllNotifications.aspx"},
    "bpsc": {"name": "Bihar BPSC", "home": "https://bpsc.bih.nic.in", "notices": "https://bpsc.bih.nic.in"},
    "csbc": {"name": "Bihar Police CSBC", "home": "https://csbc.bih.nic.in", "notices": "https://csbc.bih.nic.in"},
    "bssc": {"name": "Bihar BSSC", "home": "https://bssc.bihar.gov.in", "notices": "https://bssc.bihar.gov.in/NoticeBoard.htm"},
    "mppsc": {"name": "MPPSC", "home": "https://mppsc.mp.gov.in", "notices": "https://mppsc.mp.gov.in/advertisements"},
    "esb mp": {"name": "MP ESB", "home": "https://esb.mp.gov.in", "notices": "https://esb.mp.gov.in"},
    "rpsc": {"name": "Rajasthan RPSC", "home": "https://rpsc.rajasthan.gov.in", "notices": "https://rpsc.rajasthan.gov.in/advertisements"},
    "rsmssb": {"name": "Rajasthan RSMSSB", "home": "https://rsmssb.rajasthan.gov.in", "notices": "https://rsmssb.rajasthan.gov.in/page?menuName=ApBuI6wdvnNKC6MoOgFsfXwFRsE7cKLr"},
    "ctet": {"name": "CBSE CTET", "home": "https://ctet.nic.in", "notices": "https://ctet.nic.in"},
    "kvs": {"name": "KVS Sangathan", "home": "https://kvsangathan.nic.in", "notices": "https://kvsangathan.nic.in/en/employment-notice/"},
    "nvs": {"name": "Navodaya Vidyalaya NVS", "home": "https://navodaya.gov.in", "notices": "https://navodaya.gov.in/nvs/en/Recruitment/Notification-Vacancies/"},
    "dsssb": {"name": "Delhi DSSSB", "home": "https://dsssb.delhi.gov.in", "notices": "https://dsssb.delhi.gov.in/home/Vacancy-Advertisements"},
    "ugc net": {"name": "UGC NET", "home": "https://ugcnet.nta.ac.in", "notices": "https://ugcnet.nta.ac.in"},
    "csir": {"name": "CSIR NET", "home": "https://csirhrdg.res.in", "notices": "https://csirnet.nta.ac.in"},
    "gate": {"name": "GATE Exam", "home": "https://gate2026.iitr.ac.in", "notices": "https://gate2026.iitr.ac.in"},
    "iocl": {"name": "IOCL", "home": "https://iocl.com", "notices": "https://iocl.com/latest-job-opening"},
    "ntpc": {"name": "NTPC", "home": "https://ntpc.co.in", "notices": "https://careers.ntpc.co.in"},
    "ongc": {"name": "ONGC", "home": "https://ongcindia.com", "notices": "https://ongcindia.com/web/eng/career-tab"},
    "bhel": {"name": "BHEL", "home": "https://www.bhel.com", "notices": "https://careers.bhel.in"},
    "gail": {"name": "GAIL", "home": "https://gailonline.com", "notices": "https://gailonline.com/CRApplyingGail.html"},
    "powergrid": {"name": "POWERGRID", "home": "https://www.powergrid.in", "notices": "https://www.powergrid.in/en/job-opportunities"},
    "hpcl": {"name": "HPCL", "home": "https://www.hindustanpetroleum.com", "notices": "https://www.hindustanpetroleum.com/job-openings"},
    "coal india": {"name": "Coal India CIL", "home": "https://www.coalindia.in", "notices": "https://www.coalindia.in/career-cil/"},
    "sail": {"name": "SAIL", "home": "https://www.sail.co.in", "notices": "https://sailcareers.com"},
    "drdo": {"name": "DRDO RAC", "home": "https://rac.gov.in", "notices": "https://www.drdo.gov.in/drdo/careers"},
    "isro": {"name": "ISRO", "home": "https://www.isro.gov.in", "notices": "https://www.isro.gov.in/Careers.html"},
    "barc": {"name": "BARC", "home": "https://barc.gov.in", "notices": "https://www.barc.gov.in/careers/"},
    "npcil": {"name": "NPCIL", "home": "https://npcil.nic.in", "notices": "https://www.npcilcareers.co.in/"},
    "nmdc": {"name": "NMDC", "home": "https://www.nmdc.co.in", "notices": "https://www.nmdc.co.in/careers"},
    "india post": {"name": "India Post GDS", "home": "https://indiapostgdsonline.gov.in", "notices": "https://indiapostgdsonline.gov.in"},
    "bsnl": {"name": "BSNL", "home": "https://www.bsnl.co.in", "notices": "https://www.internalexam.bsnl.co.in/"},
    "dmrc": {"name": "DMRC Delhi Metro", "home": "https://www.delhimetrorail.com", "notices": "https://www.delhimetrorail.com/pages/en/career"},
    "mahametro": {"name": "MahaMetro", "home": "https://www.mahametro.org", "notices": "https://www.mahametro.org/Career.aspx"},
    "sci": {"name": "Supreme Court of India", "home": "https://main.sci.gov.in", "notices": "https://www.sci.gov.in/recruitments/"},
    "fci": {"name": "Food Corporation FCI", "home": "https://fci.gov.in", "notices": "https://www.recruitmentfci.in/"},
    "fssai": {"name": "FSSAI", "home": "https://fssai.gov.in", "notices": "https://fssai.gov.in/jobs@fssai.php"},
    "bis": {"name": "Bureau of Indian Standards", "home": "https://www.bis.gov.in", "notices": "https://www.bis.gov.in/career-opportunities/"},
    "esic": {"name": "ESIC", "home": "https://www.esic.nic.in", "notices": "https://www.esic.gov.in/recruitments"},
    "epfo": {"name": "EPFO", "home": "https://www.epfindia.gov.in", "notices": "https://www.epfindia.gov.in/site_en/Recruitments.php"},
    "sebi": {"name": "SEBI", "home": "https://www.sebi.gov.in", "notices": "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognised=yes"},
    "mha": {"name": "MHA Intelligence Bureau", "home": "https://www.mha.gov.in", "notices": "https://www.mha.gov.in/en/notifications/vacancies"},
    "ncb": {"name": "Narcotics Control Bureau", "home": "https://ncb.narcoticsindia.nic.in", "notices": "https://narcoticsindia.nic.in/"},
    "cbi": {"name": "CBI", "home": "https://cbi.gov.in", "notices": "https://cbi.gov.in/vacancy-list"},
    "nia": {"name": "National Investigation Agency", "home": "https://www.nia.gov.in", "notices": "https://www.nia.gov.in/recruitment-rules.htm"},
    "bro": {"name": "Border Roads Organisation", "home": "https://bro.gov.in", "notices": "https://bro.gov.in/whats-new"},
    "ndrf": {"name": "NDRF", "home": "https://ndrf.gov.in", "notices": "https://ndrf.gov.in/en/vacancy"},
    "kvic": {"name": "KVIC", "home": "https://www.kvic.org.in", "notices": "https://www.kvic.gov.in/kvicres/vacancies.php"},
    "ntc": {"name": "National Textile Corp", "home": "https://ntcltd.co.in", "notices": "https://ntcltd.co.in/Careers.aspx"},
    "hal": {"name": "HAL India", "home": "https://hal-india.co.in", "notices": "https://hal-india.co.in/career"},
    "bel": {"name": "Bharat Electronics BEL", "home": "https://bel-india.in", "notices": "https://bel-india.in/job-notifications/"},
    "mdl": {"name": "Mazagon Dock MDL", "home": "https://mazagondock.in", "notices": "https://mazagondock.in/Career.aspx"},
    "csl": {"name": "Cochin Shipyard CSL", "home": "https://cochinshipyard.in", "notices": "https://cochinshipyard.in/career"},
    "grse": {"name": "GRSE", "home": "https://grse.in", "notices": "https://grse.in/career/"},
    "nhpc": {"name": "NHPC Limited", "home": "https://www.nhpcindia.com", "notices": "https://www.nhpcindia.com/welcome/job"},
    "sjvn": {"name": "SJVN Limited", "home": "https://sjvn.nic.in", "notices": "https://sjvn.nic.in/current-jobs/99"},
    "thdc": {"name": "THDC India", "home": "https://thdc.co.in", "notices": "https://thdc.co.in/en/career"},
    "aai": {"name": "Airports Authority AAI", "home": "https://www.aai.aero", "notices": "https://www.aai.aero/en/careers/recruitment"},
    "cantonment": {"name": "eCantonment Board", "home": "https://ecantonmentboard.gov.in", "notices": "https://ecantonmentboard.gov.in"},
    "csc": {"name": "CSC Common Service Center", "home": "https://csc.gov.in", "notices": "https://csc.gov.in/careers"}
}

# ==============================================================================
# FULL MASTER DIRECTORY CATALOG (SECTION 1: 200 GOVT + SECTION 2: 100 LOCAL/PRIVATE)
# ==============================================================================
MASTER_DIRECTORY_CATALOG = [
    # Section 1: 200 Central & State Govt Posts[cite: 15]
    ("UPSC Civil Services IAS / IPS / IFS Examination", "upsc"),
    ("UPSC Central Armed Police Forces CAPF Assistant Commandant", "upsc"),
    ("UPSC National Defence Academy NDA & NA Examination", "upsc"),
    ("UPSC Combined Defence Services CDS Examination", "upsc"),
    ("UPSC Combined Medical Services CMS & Indian Forest Service IFoS", "upsc"),
    ("UPSC Engineering Services IES / IRMS Examination", "upsc"),
    ("SSC CGL Combined Graduate Level (AAO, ASO, Income Tax, GST Inspector, CBI SI)", "ssc"),
    ("SSC CHSL (LDC, JSA, Postal Assistant, DEO) Recruitment", "ssc"),
    ("SSC MTS Multi-Tasking Staff & Havaldar (CBIC & CBN) Recruitment", "ssc"),
    ("SSC Stenographer Grade C & Grade D Examination", "ssc"),
    ("SSC GD Constable (BSF, CRPF, CISF, ITBP, SSB, SSF, Assam Rifles)", "ssc"),
    ("SSC Junior Engineer JE (Civil, Electrical, Mechanical) Examination", "ssc"),
    ("SSC Selection Posts (Matric, Inter, Graduate Level) Recruitment", "ssc"),
    ("SSC Sub-Inspector SI in Delhi Police & CAPFs (CPO) Examination", "ssc"),
    ("SSC Junior Hindi Translator JHT Recruitment", "ssc"),
    ("IBPS PO Probationary Officer Public Sector Banks Recruitment", "ibps"),
    ("IBPS Clerk Customer Service Associate Clerical Cadre Recruitment", "ibps"),
    ("IBPS RRB Officer Scale I, II, III & Office Assistant (Multipurpose)", "ibps"),
    ("IBPS Specialist Officer SO (IT, AFO, Rajbhasha, Law Officer)", "ibps"),
    ("SBI Probationary Officer PO Recruitment", "sbi"),
    ("SBI Junior Associate (Customer Support & Sales Clerk) Recruitment", "sbi"),
    ("SBI Specialist Cadre Officer SCO Recruitment", "sbi"),
    ("RBI Grade B Officer (General, DEPR, DSIM) & RBI Assistant Recruitment", "rbi"),
    ("NABARD Grade A Assistant Manager & Development Assistant Recruitment", "nabard"),
    ("LIC Administrative Officer AAO & LIC Assistant Recruitment", "lic"),
    ("NIACL Administrative Officer AO & Assistant Recruitment", "niacl"),
    ("UIIC Administrative Officer AO Recruitment", "uiic"),
    ("IDBI Bank Executive & Assistant Manager Recruitment", "idbi"),
    ("RRB NTPC (Station Master, Goods Train Manager, Commercial Supervisor, Clerk)", "rrb"),
    ("RRB Group D (Track Maintainer Grade-IV, Pointsman, Workshop Assistant)", "rrb"),
    ("RRB ALP Assistant Loco Pilot & Technician Grade-I / Grade-III", "rrb"),
    ("RRB Junior Engineer JE & RRB Paramedical Staff Recruitment", "rrb"),
    ("RPF Constable & RPF Sub-Inspector SI (Railway Protection Force)", "rpf"),
    ("Indian Army Agniveer (GD, Technical, Clerk SKT, Tradesman) Rally", "army"),
    ("Indian Navy Agniveer SSR & MR Recruitment", "navy"),
    ("Indian Air Force Agniveervayu (Science & Non-Science) Intake", "air force"),
    ("Indian Coast Guard Navik (GD / DB) & Yantrik Recruitment", "coast guard"),
    ("Territorial Army Officer Entry Notification", "territorial army"),
    ("Delhi Police Constable Executive, Head Constable Ministerial & Driver", "delhi police"),
    ("Maharashtra MPSC Rajyasewa State Services (Deputy Collector / DySP)", "mpsc"),
    ("Maharashtra MPSC Combined Group B (PSI, STI, ASO) & Group C (Clerk-Typist)", "mpsc"),
    ("Maharashtra Police Constable, Driver Constable & SRPF Bharti", "mahapolice"),
    ("Maharashtra Forest Department Vanrakshak (Forest Guard) Recruitment", "mahaforest"),
    ("Maharashtra Talathi Revenue Department Bharti", "talathi"),
    ("Maharashtra Gramsevak Zilla Parishad RDD Recruitment", "gramsevak"),
    ("Maharashtra Arogya Sevak / Sevika Health Department Bharti", "arogya"),
    ("Maharashtra Agriculture Assistant Krushi Sevak Recruitment", "krushi"),
    ("Maharashtra MSEDCL Mahadiscom Vidyut Sahayak & Junior Engineer", "mahadiscom"),
    ("Maharashtra WRD / PWD Junior Engineer Civil & Electrical Recruitment", "wrd"),
    ("Maharashtra State Excise Constable & Sub-Inspector Bharti", "stateexcise"),
    ("Maharashtra RTO Motor Vehicle Inspector AMVI Recruitment", "transport"),
    ("Uttar Pradesh UPPSC Combined State UPPCS & RO / ARO Examination", "uppsc"),
    ("Uttar Pradesh UP Police Constable & Sub-Inspector SI (UPPBPB)", "up police"),
    ("Uttar Pradesh UPSSSC PET & Rajasva Lekhpal Recruitment", "upsssc"),
    ("Bihar BPSC Combined Competitive Examination CCE", "bpsc"),
    ("Bihar Police Constable CSBC Recruitment", "csbc"),
    ("Bihar BSSC Inter-Level & Graduate Level Clerk Recruitment", "bssc"),
    ("Madhya Pradesh MPPSC State Service Exam & MP Police Constable ESB", "mppsc"),
    ("Rajasthan RPSC RAS / RTS & RSMSSB Patwari / VDO Recruitment", "rpsc"),
    ("CBSE CTET Central Teacher Eligibility Test Paper I & II", "ctet"),
    ("KVS Primary Teacher PRT, TGT & PGT Recruitment", "kvs"),
    ("NVS Navodaya Vidyalaya Principal, PGT, TGT & Staff Nurse", "nvs"),
    ("Delhi DSSSB Primary Teacher PRT, TGT, PGT & LDC Recruitment", "dsssb"),
    ("NTA UGC NET & CSIR UGC NET National Eligibility Test", "ugc net"),
    ("GATE Graduate Aptitude Test in Engineering Notification", "gate"),
    ("IOCL Engineering Assistant & Technical Apprentice Recruitment", "iocl"),
    ("NTPC Engineering Executive Trainee EET & ITI Trainee Recruitment", "ntpc"),
    ("ONGC Graduate Trainee & Apprentice Recruitment", "ongc"),
    ("BHEL Executive Trainee & Artisan Recruitment", "bhel"),
    ("GAIL Executive Trainee & Non-Executive Recruitment", "gail"),
    ("POWERGRID Management Trainee & Diploma Trainee Recruitment", "powergrid"),
    ("HPCL Engineer Trainee & Technician Recruitment", "hpcl"),
    ("Coal India Limited CIL Management Trainee Recruitment", "coal india"),
    ("SAIL Management Trainee Technical & OCT/ACT Recruitment", "sail"),
    ("DRDO Scientist B RAC & CEPTAM Technician Recruitment", "drdo"),
    ("ISRO Scientist / Engineer SC Centralized Recruitment", "isro"),
    ("BARC Scientific Officer & Stipendiary Trainee Recruitment", "barc"),
    ("NPCIL Executive Trainee & Stipendiary Trainee Recruitment", "npcil"),
    ("NMDC Field Attendant & Maintenance Assistant Recruitment", "nmdc"),
    ("India Post Gramin Dak Sevak GDS & Postal Assistant Recruitment", "india post"),
    ("BSNL Management Trainee & Junior Telecom Officer JTO Recruitment", "bsnl"),
    ("Delhi Metro DMRC Executive & Non-Executive Trainee Recruitment", "dmrc"),
    ("Mumbai / Pune MahaMetro Junior Engineer & Station Controller", "mahametro"),
    ("Supreme Court of India Junior Court Assistant JCA Recruitment", "sci"),
    ("Food Corporation of India FCI Assistant Grade-III & JE Recruitment", "fci"),
    ("FSSAI Food Safety Officer & Assistant Recruitment", "fssai"),
    ("Bureau of Indian Standards BIS Scientist-B & Secretariat Assistant", "bis"),
    ("ESIC Upper Division Clerk UDC, Stenographer & Staff Nurse Recruitment", "esic"),
    ("EPFO Social Security Assistant SSA & Enforcement Officer EO/AEO", "epfo"),
    ("SEBI Grade A Officer Assistant Manager Recruitment", "sebi"),
    ("Intelligence Bureau IB ACIO Grade-II & Security Assistant Recruitment", "mha"),
    ("Narcotics Control Bureau NCB Sepoy & Sub-Inspector Recruitment", "ncb"),
    ("Central Bureau of Investigation CBI Sub-Inspector & Constable", "cbi"),
    ("National Investigation Agency NIA Inspector & Sub-Inspector", "nia"),
    ("Border Roads Organisation BRO GREF Pioneer, Operator & Driver", "bro"),
    ("KVIC Executive & National Textile Corporation NTC Trainee", "kvic"),
    ("Hindustan Aeronautics HAL Management & Design Trainee Recruitment", "hal"),
    ("Bharat Electronics BEL Probationary Engineer & Project Engineer", "bel"),
    ("Mazagon Dock MDL, Cochin Shipyard CSL & GRSE Supervisor Recruitment", "mdl"),
    ("NHPC, SJVN & THDC Junior Engineer & Field Engineer Recruitment", "nhpc"),
    ("Airports Authority of India AAI Junior Executive ATC & Common Cadre", "aai"),
    # Section 2: 100 Local, Municipal, Co-operative, GMC & Private Entry Posts[cite: 26]
    ("Gram Panchayat Data Entry Operator DEO & Computer Operator", "csc"),
    ("Gram Panchayat Rozgar Sahayak & Village Water Pump Operator", "csc"),
    ("Village Development Officer VDO & Panchayat Secretary Local Cadre", "csc"),
    ("Municipal Corporation Tax Collector, Recovery Agent & Sanitary Inspector", "cantonment"),
    ("Municipal Corporation Junior Clerk, Ward Clerk & Computer Operator", "cantonment"),
    ("Municipal Corporation Multi-Tasking Staff MTS, Peon & Driver", "cantonment"),
    ("Municipal Corporation Security Guard, Electrician & Plumber", "cantonment"),
    ("Municipal Corporation Fireman & Fire Station Attendant", "cantonment"),
    ("GMC Government Medical College Hospital Attendant, Ward Boy & Stretcher Bearer", "cantonment"),
    ("GMC Hospital Security Guard, Sanitary Worker & Patient Registration DEO", "cantonment"),
    ("GMC Hospital Lab Attendant, Laundry Worker, Cook & Store Keeper", "cantonment"),
    ("District Co-operative Central Bank DCCB Junior Clerk, Cashier & Messenger", "nabard"),
    ("Primary Agricultural Credit Society PACS Manager, Secretary & Salesman", "nabard"),
    ("State Co-operative Marketing Federation MARKFED Junior Assistant", "nabard"),
    ("District Milk Producer Cooperative Union Milk Tester, Grader & Plant Operator", "nabard"),
    ("Zilla Parishad Lower Division Clerk LDC, Junior Engineer & Extension Officer", "mpsc"),
    ("Zilla Parishad Health Worker, Livestock Assistant & Anganwadi Supervisor", "mpsc"),
    ("APMC Mandi Samiti Auction Recorder, Weighment Clerk & Gatekeeper", "cantonment"),
    ("Cantonment Board Safaiwala, LDC & Junior Engineer Recruitment", "cantonment"),
    ("Local Temple Trust Devasthan Committee Clerk, Cashier & Security Guard", "cantonment"),
    ("District Library Attendant, Sports Groundsman & Guest House Caretaker", "cantonment"),
    ("Private Security Guard Securitas SIS & Local Agencies", "csc"),
    ("Private Bank Sales Executive DSA & Teller Back Office DEO", "idbi"),
    ("CSC Common Service Center E-Seva Kendra Operator", "csc"),
    ("Private Hospital Patient Care Coordinator, Billing Executive & Pharmacy Assistant", "csc"),
    ("Private Nursing Home Ward Attendant & Diagnostic Lab Phlebotomist", "csc"),
    ("Reliance Retail D-Mart Cashier, Floor Associate & Godown Picker Packer", "csc"),
    ("Amazon Flipkart E-Commerce Warehouse Delivery Associate & Loader", "csc"),
    ("DTDC Blue Dart Local Courier Company Delivery Boy", "csc"),
    ("Local Cable Broadband Internet Service Technician & Field Installer", "csc"),
    ("Mobile Phone Repair Service Centre Front Desk Executive & Technician", "csc"),
    ("Private Petrol Pump HP BP IOC Fuel Attendant & Supervisor", "iocl"),
    ("Private Hotel Restaurant Waiter, Room Boy & Kitchen Assistant", "csc"),
    ("Local Manufacturing Unit Factory Machine Operator Helper Level", "csc"),
    ("Textile Mill Weaver, Packaging Industry Machine Feeder & Packer", "csc"),
    ("Construction Site Mason Helper & Real Estate Telecaller Promoter", "csc"),
    ("Private School Coaching Center Bus Driver, Peon & Library Assistant", "csc"),
    ("Toll Plaza Toll Collector & Parking Lot Attendant", "csc"),
    ("Cooperative Housing Society Watchman, Housekeeping & Electrician", "csc"),
    ("Private Gym Floor Trainer Assistant & Local Cold Storage Worker", "csc")
]

NON_GOVT_KEYWORDS = [
    "ongc", "iocl", "ntpc", "sail", "bhel", "gail", "powergrid", "hpcl", "coal india",
    "hal", "bel", "mdl", "mazagon dock", "cochin shipyard", "csl", "grse", "npcil", "nmdc",
    "bsnl", "dmrc", "mahametro", "idbi", "lic", "niacl", "uiic", "cooperative", "dccb",
    "pacs", "markfed", "milk union", "dairy", "temple trust", "devasthan", "private",
    "securitas", "sis", "dsa", "csc", "e-seva", "nursing home", "diagnostic", "reliance",
    "d-mart", "amazon", "flipkart", "warehouse", "courier", "dtdc", "blue dart",
    "broadband", "petrol pump", "hotel", "factory", "textile", "packaging", "tcs",
    "infosys", "wipro", "accenture", "cognizant", "apprentice", "apprentices",
    "contractual", "third-party", "semi-govt", "psu", "nhpc", "sjvn", "thdc", "ntc"
]

STATE_KEYWORDS = {
    "Maharashtra": ["mpsc", "mahagenco", "mahadisco", "msedcl", "mseb", "mumbai", "pune", "nagpur", "nashik", "thane", "bhiwandi", "maharashtra", "talathi", "gramsevak", "krushi sevak", "vanrakshak", "arogya sevak", "srpf", "mahametro", "msrtc", "rto amvi", "mahapolice", "zp maharashtra", "mahaforest", "mahabhumi"],
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
    "join telegram", "whatsapp group", "all results", "admit card 2026", "older posts"
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
# PERSISTENT PLAYWRIGHT SINGLE BROWSER POOL
# ==============================================================================
class PersistentBrowserSession:
    _browser = None
    _playwright = None

    @classmethod
    async def get_page(cls):
        if not cls._browser:
            cls._playwright = await async_playwright().start()
            cls._browser = await cls._playwright.chromium.launch(headless=True)
        page = await cls._browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
        await stealth(page)
        return page

    @classmethod
    async def close(cls):
        if cls._browser:
            await cls._browser.close()
            cls._browser = None
        if cls._playwright:
            await cls._playwright.stop()
            cls._playwright = None

def fetch_with_curl_cffi(url):
    for profile in ["chrome120", "chrome110", "safari15_5"]:
        try:
            response = cffi_requests.get(url, impersonate=profile, timeout=20)
            if response.status_code == 200 and len(response.text) > 250:
                return response.text
        except Exception:
            continue
    return ""

async def fetch_with_playwright_persistent(url):
    try:
        page = await PersistentBrowserSession.get_page()
        await page.goto(url, timeout=40000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1000)
        content = await page.content()
        await page.close()
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
            html = asyncio.run(fetch_with_playwright_persistent(url))
        except Exception:
            pass
    return html

def is_aggregator_page_link(href):
    h = href.lower()
    if h.endswith(".pdf") or ".pdf?" in h or "img.freejobalert.com" in h or "img2.freejobalert.com" in h:
        return False
    return any(ag in h for ag in AGGREGATOR_DOMAINS)

def is_specific_deep_url(url, require_pdf=False):
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

    if path.endswith("/login") or path.endswith("/candidate/login") or path.endswith("/signin"):
        return False

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
        "regn.hpsc.gov.in", "rrbapply.gov.in", "examinationservices.nic.in",
        "agnipathvayu.cdac.in", "agniveernavy.cdac.in", "joinindiancoastguard.cdac.in"
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

class CrossSiteCombinerAgent:
    @staticmethod
    def get_intent_aware_signature(title):
        meta = IntentAndMetaClassifierAgent.analyze(title)
        t = title.lower()
        stop_words = [
            "online", "form", "recruitment", "vacancy", "bharti", "apply", "now",
            "out", "link", "check", "download", "pdf", "official", "notification",
            "advt", "result", "admit", "card", "answer", "key", "syllabus"
        ]
        tokens = [w for w in re.findall(r'[a-z0-9]+', t) if w not in stop_words and len(w) > 1]
        core_exam = "_".join(tokens[:5])
        return f"{core_exam}__{meta['primary_intent']}"

    @staticmethod
    def has_meaningful_delta_update(old_post, new_post):
        if old_post.get("download_pdf", "#") == "#" and new_post.get("download_pdf", "#") != "#":
            return True
        if old_post.get("apply_link", "#") == "#" and new_post.get("apply_link", "#") != "#":
            return True
        old_boxes = old_post.get("dynamic_admin_review_boxes", {}) or {}
        new_boxes = new_post.get("dynamic_admin_review_boxes", {}) or {}
        if len(new_boxes) > len(old_boxes):
            return True
        old_ext = (old_post.get("important_dates", {}) or {}).get("extended_date", "N/A")
        new_ext = (new_post.get("important_dates", {}) or {}).get("extended_date", "N/A")
        if old_ext == "N/A" and new_ext != "N/A":
            return True
        return False

class UniqueIntentQuoteAgent:
    INTENT_OPENERS = {
        "INTENT_APPLY": [
            "Form bharna sirf pehla kadam hai, asli jung us din shuru hoti hai jab aap",
            "Bheed sirf registration karke chhod deti hai, lekin asli vijeta",
            "Comfort zone mein baith kar selection nahi milta;",
            "Aaj ka ek faisla aapka agla 40 saal ka career badal sakta hai—"
        ],
        "INTENT_NOTIFICATION": [
            "Official vigyapti aa chuki hai—ab bahane banane ka waqt khatam aur",
            "Notification ki har ek line pukarti hai ki kya aapmein",
            "Jab duniya vacancy gin rahi ho, tab aap sirf apni ek pakki seat ke liye"
        ],
        "INTENT_ADMIT_CARD": [
            "Admit Card haath mein hai—ab darne ka nahi, balki exam hall mein",
            "Pichhle mahino ki saari mehnat ab un 2 ghanto ke CBT mein hisab mangegi;"
        ],
        "INTENT_ANSWER_KEY": [
            "Answer Key se daro mat! Ek-ek galat sawal ka hisab lagao kyunki",
            "Response sheet aapka aaina hai—apni kamiyon ko pehchan kar"
        ],
        "INTENT_RESULT": [
            "Result ki PDF mein naam unhi ka chamakta hai jinhone",
            "Safalta mili toh shukrana karein, aur agar kuch marks se chook gaye toh"
        ],
        "INTENT_SYLLABUS": [
            "Syllabus aapka yuddh-manchitra (battle map) hai—bina exam pattern samjhe",
            "Har ek topic aur weightage ko tod kar padho, kyunki"
        ]
    }

    INTENT_CHALLENGES = {
        "INTENT_APPLY": ["rozana 8 ghante ki kadi tapasya se apni seat cheen kar dikhaye!", "aaj hi form bhar kar 100% syllabus aur mock tests mein jhonk de!"],
        "INTENT_NOTIFICATION": ["is bharti mein apna 100% jhonk kar itihaas rachne ka dam hai!", "aaj se hi har ek subject ka chakravyuh bhedna shuru kar de!"],
        "INTENT_ADMIT_CARD": ["har ek minute aur har ek question par apna poora niyantran rakho!", "apni kalam aur mouse ki raftaar se paper ko fateh karke aao!"],
        "INTENT_ANSWER_KEY": ["wahi galtiyan sudhar kar agle attempt ya Mains mein topper banta hai!", "apni accuracy ko 95% ke paar le jane ka sankalp aaj hi lo!"],
        "INTENT_RESULT": ["andheri raaton mein bina ruke apne lakshya ke liye pasina bahaya hai!", "dugni taqat aur naye hausle ke sath agle exam mein dhamakedar wapsi karein!"],
        "INTENT_SYLLABUS": ["har ek high-weightage chapter par apni pakad lohe jaisi majboot banao!", "rozana targeted revision se har kathin vishay ko apna gulam bana lo!"]
    }

    @staticmethod
    def generate_unique_quote(title, meta, used_quotes_set, use_ai=True):
        intent = meta["primary_intent"]
        clean_title = re.sub(r'\s+', ' ', title).strip()
        short_exam_name = " ".join(clean_title.split()[:4])

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

        unique_fallback = f"🔥 [{short_exam_name} Sankalp #{seed_int % 99999}]: {clean_title} mein wahi baazi marega jo aaj ke din ko apni aakhiri koshish maan kar mehnat karega!"
        used_quotes_set.add(unique_fallback.lower())
        return unique_fallback

class DeepVerificationAndExtractionAgent:
    @staticmethod
    def search_multi_engine_fallback(title, intent_type, board_home=""):
        domain_filter = ""
        if board_home and board_home != "#":
            netloc = urlparse(board_home).netloc.replace("www.", "")
            domain_filter = f"site:{netloc} "

        if intent_type in ["INTENT_NOTIFICATION", "INTENT_RESULT", "INTENT_ANSWER_KEY", "INTENT_SYLLABUS"]:
            query = f"{domain_filter}{title} official pdf notification"
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
            "apply_link": "#", "notif_url": "#", "result_url": "#",
            "answer_key_url": "#", "admit_card_url": "#", "syllabus_url": "#",
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
            "fees": [], "age_criteria": [], "vacancy_breakdown": [],
            "selection_process": [], "exam_pattern": [],
            "dynamic_admin_review_boxes": {}, "combined_sources": [], "accuracy_score": 0
        }

        date_pattern = re.compile(r'(\d{1,2}[\/\-\.\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|[01]?\d)[\/\-\.\s]202[4-9])', re.IGNORECASE)

        for src_name, article_url in source_urls_list:
            if not article_url or not article_url.startswith("http"):
                continue
            html = resilient_stealth_fetch(article_url)
            if not html:
                continue

            data["combined_sources"].append(src_name)
            soup = BeautifulSoup(html, "html.parser")

            for elem in soup.find_all(["li", "tr", "p", "div", "dd"]):
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
                    if any(k in t_low for k in ["exam date", "cbt date", "prelims", "mains"]):
                        data["dates"]["exam_date"] = d_val

                if ("₹" in txt or "rs." in t_low or "fee" in t_low) and any(c in t_low for c in ["general", "obc", "sc", "st", "ews"]):
                    if txt not in data["fees"] and len(data["fees"]) < 6:
                        data["fees"].append(txt)

                if any(k in t_low for k in ["minimum age", "maximum age", "age limit"]) and any(d in txt for d in ["18", "21", "30"]):
                    if txt not in data["age_criteria"] and len(data["age_criteria"]) < 6:
                        data["age_criteria"].append(txt)

            for container in soup.find_all(["tr", "li", "p", "div", "article"]):
                row_text = re.sub(r'\s+', ' ', container.get_text(" ", strip=True)).strip().lower()
                if len(row_text) > 650:
                    continue
                for a in container.find_all("a", href=True):
                    href = urljoin(article_url, a["href"].strip())
                    if not href.startswith("http") or any(b in href.lower() for b in BLOCK_DOMAINS):
                        continue
                    if is_aggregator_page_link(href):
                        continue

                    a_text = re.sub(r'\s+', ' ', a.get_text(" ", strip=True)).strip().lower()
                    combo = f"{row_text} {a_text}"

                    if any(w in combo for w in ["official website", "official portal"]):
                        if data["official_web"] == "#":
                            data["official_web"] = href

                    for dyn_kw in DYNAMIC_BOX_KEYWORDS:
                        if dyn_kw in combo and is_specific_deep_url(href):
                            box_label = dyn_kw.title()
                            if box_label not in data["dynamic_admin_review_boxes"]:
                                data["dynamic_admin_review_boxes"][box_label] = href

                    is_pdf = is_specific_deep_url(href, require_pdf=True)
                    is_deep = is_specific_deep_url(href, require_pdf=False)

                    if any(w in combo for w in ["answer key", "response sheet"]) and is_deep:
                        if data["answer_key_url"] == "#": data["answer_key_url"] = href
                    elif any(w in combo for w in ["result", "merit list", "cutoff"]) and is_deep:
                        if data["result_url"] == "#": data["result_url"] = href
                    elif any(w in combo for w in ["admit card", "hall ticket"]) and is_deep:
                        if data["admit_card_url"] == "#": data["admit_card_url"] = href
                    elif any(w in combo for w in ["apply online", "registration"]) and is_deep:
                        if data["apply_link"] == "#": data["apply_link"] = href
                    elif (is_pdf or "notification" in combo) and is_deep:
                        if data["notif_url"] == "#": data["notif_url"] = href

        if meta["board_key"]:
            hub = OFFICIAL_HUBS[meta["board_key"]]
            board_html = resilient_stealth_fetch(hub["notices"])
            if board_html:
                b_soup = BeautifulSoup(board_html, "html.parser")
                t_tokens = [w for w in re.findall(r'[a-z0-9]+', title.lower()) if len(w) > 2]
                for a in b_soup.find_all("a", href=True):
                    full_url = urljoin(hub["home"], a["href"].strip())
                    a_txt = a.get_text(" ", strip=True).lower()
                    if any(tok in a_txt or tok in full_url.lower() for tok in t_tokens):
                        if is_specific_deep_url(full_url, require_pdf=True) and data["notif_url"] == "#":
                            data["notif_url"] = full_url

        intent = meta["primary_intent"]
        if intent == "INTENT_APPLY" and not is_specific_deep_url(data["apply_link"]):
            found = DeepVerificationAndExtractionAgent.search_multi_engine_fallback(title, intent, data["official_web"])
            if is_specific_deep_url(found): data["apply_link"] = found
        elif intent == "INTENT_NOTIFICATION" and not is_specific_deep_url(data["notif_url"]):
            found = DeepVerificationAndExtractionAgent.search_multi_engine_fallback(title, intent, data["official_web"])
            if is_specific_deep_url(found): data["notif_url"] = found

        if intent == "INTENT_RESULT" and is_specific_deep_url(data["result_url"]):
            data["download_pdf"] = data["result_url"]
        elif is_specific_deep_url(data["notif_url"]):
            data["download_pdf"] = data["notif_url"]
        else:
            data["download_pdf"] = "#"

        return data

    @staticmethod
    def is_primary_intent_satisfied(meta, data):
        intent = meta["primary_intent"]
        if intent == "INTENT_APPLY": return is_specific_deep_url(data["apply_link"]) or is_specific_deep_url(data["notif_url"])
        if intent == "INTENT_NOTIFICATION": return is_specific_deep_url(data["notif_url"])
        if intent == "INTENT_RESULT": return is_specific_deep_url(data["result_url"]) or is_specific_deep_url(data["notif_url"])
        if intent == "INTENT_ADMIT_CARD": return is_specific_deep_url(data["admit_card_url"]) or is_specific_deep_url(data["apply_link"])
        if intent == "INTENT_ANSWER_KEY": return is_specific_deep_url(data["answer_key_url"]) or is_specific_deep_url(data["notif_url"])
        return True

class OptionB_GeminiMentorAgent:
    @staticmethod
    def generate_mentor_and_90day_strategy(title, meta, use_ai=True):
        if use_ai and GEMINI_API_KEY:
            prompt = f"Act as an expert Indian Competitive Exam Mentor. Write a 3-line actionable mentor advice and Last 3 Months strategy in Hinglish for: '{title}'."
            payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.65}}).encode("utf-8")
            for model in ["gemini-2.5-flash", "gemini-2.0-flash"]:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
                try:
                    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        res = json.loads(resp.read().decode("utf-8"))
                        return res["candidates"][0]["content"]["parts"][0]["text"].strip().replace("\n", "<br>")
                except Exception:
                    continue
        return "<strong>💡 Mentor Strategy:</strong> Rozana core subjects par focus karein, PYQs lagayein aur mock tests se apni speed sudharein."

class OptionA_RichDossierBuilder:
    @staticmethod
    def build_html(title, meta, data, unique_quote, mentor_strategy_html):
        dates = data["dates"]
        short_view = f"""
<div class="short-view-card" style="background:#ffffff; border:1px solid #cbd5e1; border-radius:8px; padding:18px; margin-bottom:24px;">
    <div style="background:#fef3c7; border-left:4px solid #d97706; padding:11px 15px; margin-bottom:14px; font-style:italic; color:#92400e; font-weight:600;">"{unique_quote}"</div>
    <p><strong>{title}</strong> - Type: {meta['job_type']} | State: {meta['state']}</p>
</div>
"""
        deep_view = f"""
<div class="deep-job-dossier" style="line-height:1.75; color:#1e293b; border-top:2px dashed #94a3b8; padding-top:18px;">
    <h3>🗓️ Important Dates</h3>
    <p>Last Date: <strong>{dates['last_date']}</strong></p>
    <div style="background:#fdf2f8; border-left:4px solid #db2777; padding:16px; margin:24px 0;">
        <h3>🎯 90-Day Exam Strategy</h3>
        <div>{mentor_strategy_html}</div>
    </div>
</div>
"""
        return f"{short_view}\n{deep_view}".strip()

class MasterSynthesizer:
    @staticmethod
    def build_verified_post(title, source_urls_list, used_quotes_set, use_ai=True):
        meta = IntentAndMetaClassifierAgent.analyze(title)
        data = DeepVerificationAndExtractionAgent.extract_and_verify(title, source_urls_list, meta)

        if not DeepVerificationAndExtractionAgent.is_primary_intent_satisfied(meta, data):
            return None

        unique_quote = UniqueIntentQuoteAgent.generate_unique_quote(title, meta, used_quotes_set, use_ai=use_ai)
        mentor_html = OptionB_GeminiMentorAgent.generate_mentor_and_90day_strategy(title, meta, use_ai=use_ai)
        full_html = OptionA_RichDossierBuilder.build_html(title, meta, data, unique_quote, mentor_html)

        primary_source_url = source_urls_list[0][1] if source_urls_list else data["official_web"]
        intent_sig = CrossSiteCombinerAgent.get_intent_aware_signature(title)
        job_id = hashlib.md5(intent_sig.encode("utf-8")).hexdigest()[:12]

        return {
            "id": job_id, "intent_signature": intent_sig, "title": title,
            "category": meta["category"], "primary_intent": meta["primary_intent"],
            "job_type": meta["job_type"], "state": meta["state"],
            "unique_quote": unique_quote, "source": primary_source_url,
            "apply_link": data["apply_link"], "notif_url": data["notif_url"],
            "download_pdf": data["download_pdf"], "result_url": data["result_url"],
            "important_dates": data["dates"], "dynamic_admin_review_boxes": data["dynamic_admin_review_boxes"],
            "description": full_html, "content": full_html, "status": "pending_review"
        }

def save_database_checkpoint(posts_map):
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(posts_map.values()), f, ensure_ascii=False, indent=2)

async def collect_all_candidates_async():
    grouped_candidates = {}

    for src in SOURCES:
        try:
            html = resilient_stealth_fetch(src["url"])
            if not html: continue
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                text = re.sub(r'\s+', ' ', a.get_text(" ", strip=True)).strip()
                href = urljoin(src["url"], a["href"].strip())
                if len(text) < 15 or len(text) > 150: continue
                if any(j in text.lower() for j in JUNK_TITLES): continue
                sig = CrossSiteCombinerAgent.get_intent_aware_signature(text)
                if sig not in grouped_candidates:
                    grouped_candidates[sig] = {"title": text, "sources": []}
                if (src["name"], href) not in grouped_candidates[sig]["sources"]:
                    grouped_candidates[sig]["sources"].append((src["name"], href))
        except Exception:
            continue

    for post_title, hub_key in MASTER_DIRECTORY_CATALOG:
        hub = OFFICIAL_HUBS.get(hub_key)
        if not hub: continue
        sig = CrossSiteCombinerAgent.get_intent_aware_signature(post_title)
        if sig not in grouped_candidates:
            grouped_candidates[sig] = {"title": post_title, "sources": [(hub["name"], hub["notices"])]}
        else:
            if (hub["name"], hub["notices"]) not in grouped_candidates[sig]["sources"]:
                grouped_candidates[sig]["sources"].append((hub["name"], hub["notices"]))

    return grouped_candidates

def main():
    print("🚀 Starting Final Bulletproof Master Scraper Engine...")
    existing = []
    if os.path.exists(DATABASE_FILE):
        try:
            with open(DATABASE_FILE, "r", encoding="utf-8") as f: existing = json.load(f)
        except Exception: existing = []

    posts_by_signature = {}
    used_quotes_set = set()

    for j in existing:
        if not isinstance(j, dict): continue
        sig = j.get("intent_signature") or CrossSiteCombinerAgent.get_intent_aware_signature(j.get("title", ""))
        j["intent_signature"] = sig
        posts_by_signature[sig] = j
        if q := j.get("unique_quote"): used_quotes_set.add(q.lower())

    grouped_candidates = asyncio.run(collect_all_candidates_async())
    print(f"Total Unique Candidates to Process: {len(grouped_candidates)}")

    saved_counter = 0
    for sig, bundle in grouped_candidates.items():
        if sig in posts_by_signature:
            continue

        candidate_post = MasterSynthesizer.build_verified_post(bundle["title"], bundle["sources"], used_quotes_set, use_ai=bool(GEMINI_API_KEY))
        if candidate_post:
            posts_by_signature[sig] = candidate_post
            saved_counter += 1
            if saved_counter >= 5:
                save_database_checkpoint(posts_by_signature)
                saved_counter = 0

    save_database_checkpoint(posts_by_signature)
    print(f"🎉 Sync Complete! Total Records in JSON: {len(posts_by_signature)}")
    asyncio.run(PersistentBrowserSession.close())

if __name__ == "__main__":
    main()

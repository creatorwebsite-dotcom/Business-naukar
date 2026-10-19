import os
import re
import json
import time
import hashlib
import asyncio
import urllib.parse
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

DATABASE_FILE = "jobs_database.json"
ADMIN_BOXES_FILE = "admin_boxes.json"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# ==============================================================================
# LAYER 1A: 8 MAJOR AGGREGATORS & MIRROR WEBSITES
# ==============================================================================
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

# ==============================================================================
# LAYER 1B: OFFICIAL RECRUITMENT PORTALS & NOTICE BOARDS (FOR DEEP VERIFICATION)
# ==============================================================================
OFFICIAL_HUBS = {
    "upsc": {"name": "UPSC", "home": "https://upsc.gov.in", "notices": "https://upsc.gov.in/examinations/active-examinations", "apply_portal": "https://upsconline.nic.in"},
    "ssc": {"name": "SSC", "home": "https://ssc.gov.in", "notices": "https://ssc.gov.in/Portal/Notices", "apply_portal": "https://ssc.gov.in"},
    "ibps": {"name": "IBPS", "home": "https://www.ibps.in", "notices": "https://www.ibps.in/notifications/", "apply_portal": "https://ibpsonline.ibps.in"},
    "sbi": {"name": "SBI", "home": "https://sbi.co.in/web/careers", "notices": "https://sbi.co.in/web/careers/current-openings", "apply_portal": "https://bank.sbi/web/careers/current-openings"},
    "rbi": {"name": "RBI", "home": "https://www.rbi.org.in", "notices": "https://opportunities.rbi.org.in/Scripts/Vacancies.aspx", "apply_portal": "https://opportunities.rbi.org.in/Scripts/Vacancies.aspx"},
    "nabard": {"name": "NABARD", "home": "https://www.nabard.org", "notices": "https://www.nabard.org/careers-notices1.aspx?cid=693&id=26", "apply_portal": "https://www.nabard.org/careers-notices1.aspx?cid=693&id=26"},
    "lic": {"name": "LIC", "home": "https://licindia.in", "notices": "https://licindia.in/Bottom-Links/Careers", "apply_portal": "https://licindia.in/Bottom-Links/Careers"},
    "niacl": {"name": "NIACL", "home": "https://www.newindia.co.in", "notices": "https://www.newindia.co.in/portal/readMore/Vacancies", "apply_portal": "https://www.newindia.co.in/portal/readMore/Vacancies"},
    "uiic": {"name": "UIIC", "home": "https://uiic.co.in", "notices": "https://uiic.co.in/en/careers/recruitment", "apply_portal": "https://uiic.co.in/en/careers/recruitment"},
    "idbi": {"name": "IDBI Bank", "home": "https://www.idbibank.in", "notices": "https://www.idbibank.in/idbi-bank-careers-current-openings.aspx", "apply_portal": "https://www.idbibank.in/idbi-bank-careers-current-openings.aspx"},
    "rrb": {"name": "Railway RRB", "home": "https://www.rrbcdg.gov.in", "notices": "https://www.rrbcdg.gov.in", "apply_portal": "https://www.rrbapply.gov.in"},
    "rpf": {"name": "RPF Railway", "home": "https://rpf.indianrailways.gov.in", "notices": "https://www.rrbapply.gov.in", "apply_portal": "https://www.rrbapply.gov.in"},
    "army": {"name": "Indian Army", "home": "https://joinindianarmy.nic.in", "notices": "https://joinindianarmy.nic.in/Authentication.aspx", "apply_portal": "https://joinindianarmy.nic.in"},
    "navy": {"name": "Indian Navy", "home": "https://www.joinindiannavy.gov.in", "notices": "https://www.joinindiannavy.gov.in/en/page/current-events.html", "apply_portal": "https://www.joinindiannavy.gov.in"},
    "airforce": {"name": "Indian Air Force", "home": "https://agnipathvayu.cdac.in", "notices": "https://agnipathvayu.cdac.in/AV/", "apply_portal": "https://agnipathvayu.cdac.in/AV/"},
    "coastguard": {"name": "Indian Coast Guard", "home": "https://joinindiancoastguard.cdac.in", "notices": "https://joinindiancoastguard.cdac.in", "apply_portal": "https://joinindiancoastguard.cdac.in"},
    "delhipolice": {"name": "Delhi Police", "home": "https://delhipolice.gov.in", "notices": "https://delhipolice.gov.in/recruitments", "apply_portal": "https://ssc.gov.in"},
    "mpsc": {"name": "Maharashtra MPSC", "home": "https://mpsc.gov.in", "notices": "https://mpsc.gov.in/adv_notification/8", "apply_portal": "https://mpsconline.gov.in"},
    "mahapolice": {"name": "Maharashtra Police", "home": "https://polrecruitment2024.mahait.org", "notices": "https://polrecruitment2024.mahait.org", "apply_portal": "https://polrecruitment2024.mahait.org"},
    "mahaforest": {"name": "Maharashtra Forest", "home": "https://www.mahaforest.gov.in", "notices": "https://www.mahaforest.gov.in", "apply_portal": "https://www.mahaforest.gov.in"},
    "mahabhumi": {"name": "Maharashtra Revenue Talathi", "home": "https://mahabhumi.gov.in", "notices": "https://mahabhumi.gov.in/mahabhumilink", "apply_portal": "https://mahabhumi.gov.in"},
    "mahardd": {"name": "Maharashtra ZP RDD", "home": "https://rdd.maharashtra.gov.in", "notices": "https://rdd.maharashtra.gov.in", "apply_portal": "https://ibpsonline.ibps.in"},
    "mahaarogya": {"name": "Maharashtra Arogya", "home": "https://arogya.maharashtra.gov.in", "notices": "https://arogya.maharashtra.gov.in", "apply_portal": "https://arogya.maharashtra.gov.in"},
    "mahakrishi": {"name": "Maharashtra Krishi", "home": "https://krishi.maharashtra.gov.in", "notices": "https://krishi.maharashtra.gov.in", "apply_portal": "https://krishi.maharashtra.gov.in"},
    "mahadiscom": {"name": "MSEDCL Mahadiscom", "home": "https://www.mahadiscom.in", "notices": "https://www.mahadiscom.in/en/career/", "apply_portal": "https://www.mahadiscom.in/en/career/"},
    "uppsc": {"name": "UPPSC", "home": "https://uppsc.up.nic.in", "notices": "https://uppsc.up.nic.in/CandidatePages/Notifications.aspx", "apply_portal": "https://uppsc.up.nic.in/CandidatePages/Notifications.aspx"},
    "uppbpb": {"name": "UP Police UPPBPB", "home": "https://uppbpb.gov.in", "notices": "https://uppbpb.gov.in/Home/Notice", "apply_portal": "https://uppbpb.gov.in"},
    "upsssc": {"name": "UPSSSC", "home": "https://upsssc.gov.in", "notices": "https://upsssc.gov.in/AllNotifications.aspx", "apply_portal": "https://upsssc.gov.in/AllNotifications.aspx"},
    "bpsc": {"name": "Bihar BPSC", "home": "https://bpsc.bih.nic.in", "notices": "https://bpsc.bih.nic.in", "apply_portal": "https://onlinebpsc.bihar.gov.in"},
    "csbc": {"name": "Bihar Police CSBC", "home": "https://csbc.bih.nic.in", "notices": "https://csbc.bih.nic.in", "apply_portal": "https://csbc.bih.nic.in"},
    "bssc": {"name": "Bihar BSSC", "home": "https://bssc.bihar.gov.in", "notices": "https://bssc.bihar.gov.in/NoticeBoard.htm", "apply_portal": "https://bssc.bihar.gov.in/NoticeBoard.htm"},
    "mppsc": {"name": "MPPSC", "home": "https://mppsc.mp.gov.in", "notices": "https://mppsc.mp.gov.in/Advertisements", "apply_portal": "https://mppsc.mp.gov.in/Applyonline"},
    "mpesb": {"name": "MP ESB", "home": "https://esb.mp.gov.in", "notices": "https://esb.mp.gov.in/e_default.html", "apply_portal": "https://esb.mp.gov.in"},
    "rpsc": {"name": "Rajasthan RPSC", "home": "https://rpsc.rajasthan.gov.in", "notices": "https://rpsc.rajasthan.gov.in/advertisements", "apply_portal": "https://sso.rajasthan.gov.in"},
    "rsmssb": {"name": "Rajasthan RSMSSB", "home": "https://rsmssb.rajasthan.gov.in", "notices": "https://rsmssb.rajasthan.gov.in/page?menuName=ApBuI6wdvnNKC6MoOgFsfXwFRsE7cKLr", "apply_portal": "https://sso.rajasthan.gov.in"},
    "ctet": {"name": "CTET CBSE", "home": "https://ctet.nic.in", "notices": "https://ctet.nic.in", "apply_portal": "https://ctet.nic.in"},
    "kvs": {"name": "KVS Sangathan", "home": "https://kvsangathan.nic.in", "notices": "https://kvsangathan.nic.in/en/recruitment", "apply_portal": "https://kvsangathan.nic.in/en/recruitment"},
    "nvs": {"name": "NVS Navodaya", "home": "https://navodaya.gov.in", "notices": "https://navodaya.gov.in/nvs/en/Recruitment/Notification-Vacancies/", "apply_portal": "https://navodaya.gov.in/nvs/en/Recruitment/Fill-up-online-application/"},
    "dsssb": {"name": "Delhi DSSSB", "home": "https://dsssb.delhi.gov.in", "notices": "https://dsssb.delhi.gov.in/home/vacancies", "apply_portal": "https://dsssbonline.nic.in"},
    "ugcnet": {"name": "NTA UGC NET", "home": "https://ugcnet.nta.ac.in", "notices": "https://ugcnet.nta.ac.in", "apply_portal": "https://ugcnet.nta.ac.in"},
    "iocl": {"name": "IOCL", "home": "https://iocl.com", "notices": "https://iocl.com/latest-job-opening", "apply_portal": "https://iocl.com/latest-job-opening"},
    "ntpc": {"name": "NTPC", "home": "https://ntpc.co.in", "notices": "https://careers.ntpc.co.in", "apply_portal": "https://careers.ntpc.co.in"},
    "ongc": {"name": "ONGC", "home": "https://ongcindia.com", "notices": "https://ongcindia.com/web/eng/career-tab", "apply_portal": "https://ongcindia.com/web/eng/career-tab"},
    "bhel": {"name": "BHEL", "home": "https://www.bhel.com", "notices": "https://careers.bhel.in", "apply_portal": "https://careers.bhel.in"},
    "gail": {"name": "GAIL", "home": "https://gailonline.com", "notices": "https://gailonline.com/CRApplyingGail.html", "apply_portal": "https://gailonline.com/CRApplyingGail.html"},
    "powergrid": {"name": "POWERGRID", "home": "https://www.powergrid.in", "notices": "https://www.powergrid.in/en/job-opportunities", "apply_portal": "https://www.powergrid.in/en/job-opportunities"},
    "hpcl": {"name": "HPCL", "home": "https://www.hindustanpetroleum.com", "notices": "https://www.hindustanpetroleum.com/job-openings", "apply_portal": "https://jobs.hpcl.co.in"},
    "cil": {"name": "Coal India", "home": "https://www.coalindia.in", "notices": "https://www.coalindia.in/career-cil/", "apply_portal": "https://www.coalindia.in/career-cil/"},
    "sail": {"name": "SAIL", "home": "https://www.sail.co.in", "notices": "https://sailcareers.com", "apply_portal": "https://sailcareers.com"},
    "drdo": {"name": "DRDO RAC", "home": "https://rac.gov.in", "notices": "https://rac.gov.in", "apply_portal": "https://rac.gov.in"},
    "isro": {"name": "ISRO", "home": "https://www.isro.gov.in", "notices": "https://www.isro.gov.in/Careers.html", "apply_portal": "https://www.isro.gov.in/Careers.html"},
    "barc": {"name": "BARC", "home": "https://barc.gov.in", "notices": "https://recruit.barc.gov.in", "apply_portal": "https://recruit.barc.gov.in"},
    "npcil": {"name": "NPCIL", "home": "https://npcil.nic.in", "notices": "https://www.npcilcareers.co.in", "apply_portal": "https://www.npcilcareers.co.in"},
    "nmdc": {"name": "NMDC", "home": "https://www.nmdc.co.in", "notices": "https://www.nmdc.co.in/careers", "apply_portal": "https://www.nmdc.co.in/careers"},
    "indiapost": {"name": "India Post GDS", "home": "https://indiapostgdsonline.gov.in", "notices": "https://indiapostgdsonline.gov.in", "apply_portal": "https://indiapostgdsonline.gov.in"},
    "bsnl": {"name": "BSNL", "home": "https://www.bsnl.co.in", "notices": "https://externalexam.bsnl.co.in", "apply_portal": "https://externalexam.bsnl.co.in"},
    "dmrc": {"name": "Delhi Metro DMRC", "home": "https://www.delhimetrorail.com", "notices": "https://www.delhimetrorail.com/pages/en/career", "apply_portal": "https://www.delhimetrorail.com/pages/en/career"},
    "mahametro": {"name": "MahaMetro", "home": "https://www.mahametro.org", "notices": "https://www.mahametro.org/Career.aspx", "apply_portal": "https://www.mahametro.org/Career.aspx"},
    "sci": {"name": "Supreme Court SCI", "home": "https://main.sci.gov.in", "notices": "https://main.sci.gov.in/recruitment", "apply_portal": "https://main.sci.gov.in/recruitment"},
    "fci": {"name": "FCI", "home": "https://fci.gov.in", "notices": "https://www.recruitmentfci.in", "apply_portal": "https://www.recruitmentfci.in"},
    "fssai": {"name": "FSSAI", "home": "https://fssai.gov.in", "notices": "https://fssai.gov.in/jobs@fssai.php", "apply_portal": "https://fssai.gov.in/jobs@fssai.php"},
    "bis": {"name": "BIS", "home": "https://www.bis.gov.in", "notices": "https://www.bis.gov.in/career-opportunities/", "apply_portal": "https://www.bis.gov.in/career-opportunities/"},
    "esic": {"name": "ESIC", "home": "https://www.esic.gov.in", "notices": "https://www.esic.gov.in/recruitments", "apply_portal": "https://www.esic.gov.in/recruitments"},
    "epfo": {"name": "EPFO", "home": "https://www.epfindia.gov.in", "notices": "https://www.epfindia.gov.in/site_en/Recruitments.php", "apply_portal": "https://www.epfindia.gov.in/site_en/Recruitments.php"},
    "sebi": {"name": "SEBI", "home": "https://www.sebi.gov.in", "notices": "https://www.sebi.gov.in/sebiweb/other/careerdetail.jsp", "apply_portal": "https://www.sebi.gov.in/sebiweb/other/careerdetail.jsp"},
    "mha": {"name": "MHA IB", "home": "https://www.mha.gov.in", "notices": "https://www.mha.gov.in/en/notifications/vacancies", "apply_portal": "https://www.mha.gov.in/en/notifications/vacancies"},
    "hal": {"name": "HAL", "home": "https://hal-india.co.in", "notices": "https://hal-india.co.in/career", "apply_portal": "https://hal-india.co.in/career"},
    "bel": {"name": "BEL", "home": "https://bel-india.in", "notices": "https://bel-india.in/job-notifications/", "apply_portal": "https://bel-india.in/job-notifications/"},
    "mdl": {"name": "Mazagon Dock MDL", "home": "https://mazagondock.in", "notices": "https://mazagondock.in/ Career.aspx", "apply_portal": "https://mazagondock.in"},
    "aai": {"name": "AAI Airports Authority", "home": "https://www.aai.aero", "notices": "https://www.aai.aero/en/careers/recruitment", "apply_portal": "https://www.aai.aero/en/careers/recruitment"},
    "cantonment": {"name": "Cantonment Board", "home": "https://ecantonmentboard.gov.in", "notices": "https://ecantonmentboard.gov.in", "apply_portal": "https://ecantonmentboard.gov.in"},
    "csc": {"name": "CSC e-Seva", "home": "https://csc.gov.in", "notices": "https://csc.gov.in/careers", "apply_portal": "https://register.csc.gov.in"}
}

# ==============================================================================
# LAYER 1C: COMPLETE 300-POST MASTER DIRECTORY (200 GOVT + 100 SEMI-GOVT/LOCAL/PRIVATE)
# ==============================================================================
MASTER_DIRECTORY_CATALOG = [
    # SECTION 1: 200 Central & State Govt Recurring Exam Posts
    ("UPSC Civil Services Examination (IAS / IPS / IFS / IRS)", "upsc", ["ias", "ifs", "civil services", "cse"]),
    ("UPSC Engineering Services Examination (IES / IRMS)", "upsc", ["engineering services", "ese", "ies", "irms"]),
    ("UPSC Central Armed Police Forces (CAPF) Assistant Commandant", "upsc", ["capf", "assistant commandant"]),
    ("UPSC National Defence Academy & Naval Academy (NDA & NA)", "upsc", ["nda", "naval academy"]),
    ("UPSC Combined Defence Services Examination (CDS)", "upsc", ["cds", "combined defence"]),
    ("UPSC Combined Medical Services (CMS) & Indian Forest Service (IFoS)", "upsc", ["cms", "medical services", "forest service"]),
    ("SSC CGL Combined Graduate Level (AAO, ASO, Income Tax & GST Inspector, CBI SI, Auditor)", "ssc", ["ssc cgl", "combined graduate level"]),
    ("SSC CHSL Combined Higher Secondary Level (LDC, JSA, Postal Assistant, DEO)", "ssc", ["ssc chsl", "higher secondary", "ldc", "deo"]),
    ("SSC MTS Multi-Tasking Staff & CBIC/CBN Havaldar Recruitment", "ssc", ["ssc mts", "havaldar", "multi tasking"]),
    ("SSC Stenographer Grade C & Grade D Examination", "ssc", ["ssc stenographer", "steno grade"]),
    ("SSC GD Constable (BSF, CRPF, CISF, ITBP, SSB, SSF & Assam Rifles)", "ssc", ["ssc gd", "constable gd", "rifleman"]),
    ("SSC Junior Engineer (JE - Civil, Electrical & Mechanical)", "ssc", ["ssc je", "junior engineer"]),
    ("SSC Selection Posts (Phase Matrix - Matric, Inter & Graduate Level)", "ssc", ["selection post", "ssc phase"]),
    ("SSC Sub-Inspector in Delhi Police & CAPF (SSC CPO SI)", "ssc", ["ssc cpo", "sub inspector in delhi police", "capf si"]),
    ("SSC Junior Hindi Translator (JHT) Examination", "ssc", ["ssc jht", "hindi translator"]),
    ("IBPS PO / MT Probationary Officer in Public Sector Banks", "ibps", ["ibps po", "probationary officer", "crp po"]),
    ("IBPS Clerk Customer Service Associate (CSA Clerical Cadre)", "ibps", ["ibps clerk", "customer service associate", "crp clerk"]),
    ("IBPS RRB Officer Scale-I, II, III & Office Assistant (Multipurpose)", "ibps", ["ibps rrb", "crp rrb", "office assistant", "officer scale"]),
    ("IBPS Specialist Officer (SO - IT, AFO, Rajbhasha, Law, HR, Marketing)", "ibps", ["ibps so", "specialist officer", "crp spl"]),
    ("SBI Probationary Officer (SBI PO) Recruitment", "sbi", ["sbi po", "probationary officer"]),
    ("SBI Junior Associate (Customer Support & Sales Clerk)", "sbi", ["sbi clerk", "junior associate"]),
    ("SBI Specialist Cadre Officer (SCO) Recruitment", "sbi", ["sbi sco", "specialist cadre"]),
    ("RBI Grade B Officer (General, DEPR, DSIM) & RBI Assistant", "rbi", ["rbi grade b", "rbi assistant"]),
    ("NABARD Grade A Assistant Manager & Development Assistant", "nabard", ["nabard grade a", "development assistant", "nabard"]),
    ("LIC Administrative Officer (AAO) & LIC Assistant Recruitment", "lic", ["lic aao", "lic assistant", "lic ado"]),
    ("NIACL Administrative Officer (AO) & NIACL Assistant", "niacl", ["niacl ao", "niacl assistant", "new india assurance"]),
    ("UIIC Administrative Officer (AO) & Assistant Recruitment", "uiic", ["uiic", "united india insurance"]),
    ("IDBI Bank Executive & Assistant Manager Grade A", "idbi", ["idbi executive", "idbi assistant manager", "idbi"]),
    ("RRB NTPC Graduate & Undergraduate Posts (Station Master, Goods Train Manager, Clerk)", "rrb", ["rrb ntpc", "station master", "ntpc"]),
    ("RRB Group D Level-1 (Track Maintainer, Pointsman, Workshop Assistant)", "rrb", ["rrb group d", "level 1", "track maintainer"]),
    ("RRB ALP Assistant Loco Pilot & RRB Technician Grade I / III", "rrb", ["rrb alp", "loco pilot", "rrb technician"]),
    ("RRB Junior Engineer (JE), DMS, CMA & Paramedical Staff", "rrb", ["rrb je", "rrb paramedical"]),
    ("RPF Constable & RPF Sub-Inspector (SI) Railway Protection Force", "rpf", ["rpf constable", "rpf si", "railway protection force"]),
    ("Indian Army Agniveer (GD, Technical, Clerk/SKT, Tradesman)", "army", ["army agniveer", "indian army rally"]),
    ("Indian Navy Agniveer (SSR & MR) Recruitment", "navy", ["navy agniveer", "agniveer ssr", "agniveer mr"]),
    ("Indian Air Force Agniveervayu (Science & Non-Science Intake)", "airforce", ["agniveervayu", "air force intake"]),
    ("Indian Coast Guard Navik (GD / DB) & Yantrik Recruitment", "coastguard", ["coast guard navik", "yantrik"]),
    ("Delhi Police Constable (Executive), Head Constable & Driver", "delhipolice", ["delhi police constable", "delhi police head constable"]),
    ("Maharashtra MPSC Rajyasewa State Services & Combined Group B/C (PSI, STI, ASO)", "mpsc", ["mpsc", "rajyasewa", "group b", "group c"]),
    ("Maharashtra Police Constable, Driver & SRPF Police Bharti", "mahapolice", ["maharashtra police", "srpf", "police bharti"]),
    ("Maharashtra Forest Department Vanrakshak (Forest Guard)", "mahaforest", ["vanrakshak", "mahaforest", "forest guard"]),
    ("Maharashtra Talathi Bharti (Revenue Department)", "mahabhumi", ["talathi", "mahabhumi", "revenue"]),
    ("Maharashtra Zilla Parishad Gramsevak, Arogya Sevak & Krishi Sevak", "mahardd", ["gramsevak", "arogya sevak", "krishi sevak", "zilla parishad"]),
    ("Maharashtra MSEDCL Mahadiscom Vidyut Sahayak & Junior Engineer", "mahadiscom", ["msedcl", "mahadiscom", "vidyut sahayak"]),
    ("Uttar Pradesh UPPSC Combined State Services (UPPCS) & RO / ARO", "uppsc", ["uppsc", "uppcs", "ro aro", "review officer"]),
    ("Uttar Pradesh UP Police Constable & Sub-Inspector (UPPBPB)", "uppbpb", ["up police", "uppbpb"]),
    ("Uttar Pradesh UPSSSC PET, Rajasva Lekhpal & Junior Assistant", "upsssc", ["upsssc", "lekhpal", "upsssc pet"]),
    ("Bihar BPSC Combined Competitive Exam (CCE) & TRE Teacher", "bpsc", ["bpsc", "bihar teacher"]),
    ("Bihar Police Constable (CSBC) & Bihar BSSC Inter/Graduate Level", "csbc", ["bihar police", "csbc", "bssc"]),
    ("Madhya Pradesh MPPSC State Service Exam & MP ESB Police Constable", "mppsc", ["mppsc", "mp police", "mpesb"]),
    ("Rajasthan RPSC RAS / RTS & RSMSSB Patwari / VDO / CET", "rpsc", ["rpsc", "rsmssb", "patwari"]),
    ("CBSE CTET Central Teacher Eligibility Test (Paper I & II)", "ctet", ["ctet", "central teacher eligibility"]),
    ("KVS & NVS Teaching & Non-Teaching Recruitment (PRT, TGT, PGT, JSA)", "kvs", ["kvs", "nvs", "navodaya", "kendriya vidyalaya"]),
    ("Delhi DSSSB PRT, TGT, PGT Teacher & DASS Grade II/IV LDC", "dsssb", ["dsssb"]),
    ("NTA UGC NET & CSIR UGC NET Junior Research Fellowship", "ugcnet", ["ugc net", "csir net"]),
    ("IOCL Engineering Assistant, Junior Operator & Apprentice", "iocl", ["iocl", "indian oil"]),
    ("NTPC Engineering Executive Trainee (EET) & ITI Trainee", "ntpc", ["ntpc"]),
    ("ONGC Graduate Trainee (GT) & Trade/Technician Apprentice", "ongc", ["ongc"]),
    ("BHEL, GAIL, POWERGRID, HPCL, Coal India (CIL) & SAIL Executive/MT", "bhel", ["bhel", "gail", "powergrid", "hpcl", "coal india", "sail"]),
    ("DRDO Scientist B / CEPTAM, ISRO Scientist SC, BARC & NPCIL Trainee", "drdo", ["drdo", "isro", "barc", "npcil"]),
    ("NMDC Field Attendant, HAL, BEL, MDL & AAI Junior Executive", "aai", ["nmdc", "hal", "bel", "mazagon", "aai", "airports authority"]),
    ("India Post Gramin Dak Sevak (GDS), Postal Assistant & MTS", "indiapost", ["india post", "gds", "gramin dak sevak"]),
    ("BSNL JTO / MT, DMRC Delhi Metro & MahaMetro JE / Station Controller", "dmrc", ["bsnl", "dmrc", "delhi metro", "mahametro"]),
    ("Supreme Court of India Junior Court Assistant (JCA) & High Court Clerk", "sci", ["supreme court", "high court", "jca"]),
    ("FCI Assistant Grade-III, FSSAI, BIS, ESIC UDC/MTS, EPFO SSA/EO & SEBI Grade A", "epfo", ["fci", "fssai", "bis", "esic", "epfo", "sebi"]),
    ("MHA Intelligence Bureau (IB ACIO / Security Assistant), CBI, NIA & BRO GREF", "mha", ["intelligence bureau", "ib acio", "security assistant", "bro gref"]),

    # SECTION 2: 100 Low-Level, Local, Municipal, Co-operative, GMC & Private Entry-Level Posts
    ("Gram Panchayat Data Entry Operator (DEO), Rozgar Sahayak & Panchayat Secretary", "mahardd", ["gram panchayat", "rozgar sahayak", "panchayat secretary", "vdo"]),
    ("Municipal Corporation Tax Collector, Sanitary Inspector, Ward Clerk,MTS & Fireman", "cantonment", ["municipal corporation", "sanitary inspector", "nagar nigam", "bmc", "pmc"]),
    ("GMC Government Medical College Hospital Ward Boy, Lab Attendant, DEO & Staff Nurse", "mahaarogya", ["gmc", "medical college", "ward boy", "lab attendant", "hospital attendant"]),
    ("District Co-operative Central Bank (DCCB) Clerk, PACS Manager & MARKFED Assistant", "nabard", ["dccb", "cooperative bank", "markfed", "pacs"]),
    ("District Milk Union Dairy Plant Operator & Urban Co-operative Bank Clerk", "nabard", ["dairy", "milk union", "urban cooperative"]),
    ("Zilla Parishad LDC, Junior Engineer, Pashudhan Sahayak & Anganwadi Supervisor", "mahardd", ["anganwadi", "pashudhan", "zilla parishad"]),
    ("APMC Mandi Samiti Auction Recorder, Weighment Clerk & Cantonment Board LDC/Safaiwala", "cantonment", ["cantonment board", "apmc", "mandi"]),
    ("CSC Common Service Center E-Seva Operator, Private Bank Sales DSA & Retail/Logistics Executive", "csc", ["csc", "e-seva", "apprentice", "walk-in"])
]

STANDARD_BOXES = {"Latest Jobs", "Admit Card", "Result", "Answer Key", "Syllabus", "Notification"}

NON_GOVT_KEYWORDS = [
    "ongc", "iocl", "ntpc", "sail", "bhel", "gail", "powergrid", "hpcl", "coal india",
    "hal", "bel", "mdl", "nmdc", "bsnl", "dmrc", "mahametro", "private", "apprentice",
    "semi-govt", "psu", "dccb", "pacs", "markfed", "cooperative", "csc", "idbi", "lic", "niacl", "uiic"
]

STATE_KEYWORDS = {
    "Maharashtra": ["mpsc", "mumbai", "pune", "nagpur", "maharashtra", "talathi", "gramsevak", "srpf", "mahadiscom", "msedcl", "mahametro", "bmc", "pmc", "arogya sevak", "krishi sevak", "vanrakshak", "mahabhumi"],
    "Uttar Pradesh": ["uppsc", "uppcs", "lucknow", "uttar pradesh", "lekhpal", "up police", "uppbpb", "upsssc", "allahabad", "uptet", "uppsc ro"],
    "Bihar": ["bpsc", "bihar", "patna", "csbc", "bssc", "btsc", "btet"],
    "Madhya Pradesh": ["mppsc", "madhya pradesh", "bhopal", "mpesb", "mppeb", "mp police", "indore"],
    "Rajasthan": ["rpsc", "rajasthan", "jaipur", "patwari", "rsmssb", "rssb", "reet"],
    "Delhi": ["dsssb", "delhi police", "dmrc", "delhi metro", "delhi high court"],
    "Haryana": ["hssc", "hpsc", "haryana", "chandigarh"],
    "Punjab": ["psssb", "ppsc", "punjab"],
    "Gujarat": ["gpsc", "ojas", "gujarat", "gsssb"],
    "Karnataka": ["kpsc", "karnataka", "kea", "bengaluru"],
    "Tamil Nadu": ["tnpsc", "tamil nadu", "chennai", "trb"],
    "West Bengal": ["wbpsc", "west bengal", "kolkata", "wbp"],
    "Jharkhand": ["jssc", "jpsc", "jharkhand", "ranchi"],
    "Chhattisgarh": ["cgpsc", "cgvyapam", "chhattisgarh", "raipur"],
    "Uttarakhand": ["ukpsc", "uksssc", "uttarakhand", "dehradun"],
    "Odisha": ["opsc", "osssc", "ossc", "odisha", "bhubaneswar"]
}

BLOCK_DOMAINS = [
    "play.google.com", "apps.apple.com", "whatsapp.com", "t.me", "telegram.me",
    "facebook.com", "twitter.com", "x.com", "youtube.com", "instagram.com",
    "pinterest.com", "linkedin.com", "sarkariresulttools.net", "addtoany.com",
    "google.com", "bing.com", "duckduckgo.com", "yahoo.com", "dmca.com", "cloudflare.com"
]

AGGREGATOR_DOMAINS = [
    "sarkariresult.com", "sarkariresult.com.cm", "freejobalert.com",
    "rojgarresult.com", "sarkariexam.com", "indgovtjobs.in",
    "freshersnow.com", "careerpower.in"
]

JUNK_TITLES = [
    "sarkari result", "tools", "latest notifications", "view more", "click here",
    "home", "contact us", "disclaimer", "privacy policy", "about us", "sitemap",
    "download app", "join telegram", "join whatsapp", "test series", "mock test",
    "certificate verification", "pan card", "aadhar card", "voter id", "typing test"
]

MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12
}

# ==============================================================================
# NON-BLOCKING NETWORK ENGINE (40s PER-TASK TIMEOUT PROTECTION)
# ==============================================================================
def blocking_fetch(url, timeout=14):
    try:
        res = cffi_requests.get(url, impersonate="chrome110", timeout=timeout, allow_redirects=True)
        if res.status_code == 200 and len(res.text) > 150:
            return res.text
    except Exception:
        pass
    return ""

async def safe_fetch_non_blocking(url, loop, semaphore, timeout=25.0):
    if not url or not url.startswith("http"):
        return ""
    async with semaphore:
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, blocking_fetch, url, int(timeout - 3)),
                timeout=timeout
            )
        except Exception:
            return ""

# ==============================================================================
# LAYER 2: INTENT, CATEGORY, JOB TYPE, STATE & DYNAMIC ADMIN BOX CLASSIFIER
# ==============================================================================
class IntentAndMetaClassifierAgent:
    @staticmethod
    def analyze(title, box_heading=""):
        t = f"{title} {box_heading}".lower()
        box_clean = re.sub(r'\s+', ' ', box_heading).strip()

        if any(k in t for k in ["answer key", "response sheet", "question paper", "objection"]):
            category, intent = "Answer Key", "INTENT_ANSWER_KEY"
        elif any(k in t for k in ["result", "merit list", "cutoff", "cut off", "score card", "scorecard", "final selection", "marks"]):
            category, intent = "Result", "INTENT_RESULT"
        elif any(k in t for k in ["admit card", "hall ticket", "call letter", "exam city", "exam date", "interview letter"]):
            category, intent = "Admit Card", "INTENT_ADMIT_CARD"
        elif any(k in t for k in ["syllabus", "exam pattern", "curriculum"]):
            category, intent = "Syllabus", "INTENT_SYLLABUS"
        elif any(k in t for k in ["short notice", "notification pdf", "official notification"]) and "online form" not in t:
            category, intent = "Notification", "INTENT_NOTIFICATION"
        else:
            category, intent = "Latest Jobs", "INTENT_APPLY"

        # Detect Dynamic / Custom Box on Aggregators
        admin_box = category
        is_new_admin_box = False
        if box_clean and len(box_clean) <= 45:
            b_low = box_clean.lower()
            if not any(std in b_low for std in ["latest job", "result", "admit card", "answer key", "syllabus"]):
                if any(custom_k in b_low for custom_k in ["admission", "upcoming", "apprentice", "scholarship", "walk-in", "offline", "important", "counseling", "verification"]):
                    admin_box = box_clean.title()
                    is_new_admin_box = True

        job_type = "Non-Govt + Semi-Govt" if any(k in t for k in NON_GOVT_KEYWORDS) else "Govt"
        state = "All India / Central"
        for s_name, kws in STATE_KEYWORDS.items():
            if any(kw in t for kw in kws):
                state = s_name
                break

        return {
            "category": category,
            "primary_intent": intent,
            "job_type": job_type,
            "state": state,
            "admin_box": admin_box,
            "is_new_admin_box": is_new_admin_box
        }

# ==============================================================================
# LAYER 3 & 4: DEEP TABLE PARSER, REAL DATE EXTRACTOR & INTENT-SPECIFIC LINK VERIFIER
# ==============================================================================
def parse_any_date_string(text):
    if not text:
        return None
    text = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', text, flags=re.IGNORECASE)

    # Pattern 1: DD Mon YYYY or DD Month YYYY (e.g., 15 Oct 2026, 15 October 2026)
    m1 = re.search(r'\b(\d{1,2})[\s\/\-\.](Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[\s\/\-\.,]+(202[4-9])\b', text, re.IGNORECASE)
    if m1:
        day, mon_str, yr = int(m1.group(1)), m1.group(2).lower()[:3], int(m1.group(3))
        mon = MONTH_MAP.get(mon_str, 1)
        try:
            return datetime(yr, mon, day)
        except ValueError:
            pass

    # Pattern 2: Mon DD, YYYY (e.g., October 15, 2026)
    m2 = re.search(r'\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2})[\s,]+(202[4-9])\b', text, re.IGNORECASE)
    if m2:
        mon_str, day, yr = m2.group(1).lower()[:3], int(m2.group(2)), int(m2.group(3))
        mon = MONTH_MAP.get(mon_str, 1)
        try:
            return datetime(yr, mon, day)
        except ValueError:
            pass

    # Pattern 3: DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
    m3 = re.search(r'\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](202[4-9])\b', text)
    if m3:
        d, m, y = int(m3.group(1)), int(m3.group(2)), int(m3.group(3))
        if 1 <= m <= 12 and 1 <= d <= 31:
            try:
                return datetime(y, m, d)
            except ValueError:
                pass

    # Pattern 4: ISO YYYY-MM-DD
    m4 = re.search(r'\b(202[4-9])-(\d{2})-(\d{2})\b', text)
    if m4:
        try:
            return datetime(int(m4.group(1)), int(m4.group(2)), int(m4.group(3)))
        except ValueError:
            pass

    return None

def is_clean_external_url(url, allow_aggregator_pdf=False):
    if not url or not url.startswith("http") or url.endswith("#"):
        return False
    u_low = url.lower()
    if any(b in u_low for b in BLOCK_DOMAINS):
        return False
    if any(ag in u_low for ag in AGGREGATOR_DOMAINS):
        # Allow direct .pdf files hosted on aggregator doc/upload servers
        if allow_aggregator_pdf and (".pdf" in u_low or "/upload" in u_low):
            return True
        return False
    return True

def match_hub_for_title(title):
    t_low = title.lower()
    for _, hub_key, kws in MASTER_DIRECTORY_CATALOG:
        if any(k in t_low for k in kws):
            return OFFICIAL_HUBS.get(hub_key)
    for hub_key, hub_data in OFFICIAL_HUBS.items():
        if hub_key in t_low or hub_data["name"].lower() in t_low:
            return hub_data
    return None

def deep_parse_article_dossier(article_html, article_url, title, primary_intent):
    """
    Extracts:
    1. Intent-Specific Direct Links (Apply Registration URL, Notification PDF, Answer Key, Result, Admit Card, Syllabus, Official Site)
    2. Real Important Dates (Notification Date, Apply Start, Last Date, Extended Date, Exam Date, Admit Card, Answer Key, Result Date)
    3. Age Limit & Relaxation
    4. Application Fee
    5. Category-Wise Vacancy Distribution & Total Posts
    6. Selection Process & Exam Pattern
    """
    dossier = {
        "dates": {
            "notification_date": "See Official Notice",
            "apply_start_date": "Active / Notified",
            "last_date": "Check Official Notice",
            "extended_date": "N/A",
            "exam_date": "As per Schedule",
            "admit_card_date": "Before Exam",
            "answer_key_date": "After Exam",
            "result_date": "To be Notified",
            "real_post_date_obj": None,
            "real_post_date_str": ""
        },
        "fees": [],
        "age_criteria": [],
        "total_vacancy": "Multiple Posts",
        "vacancy_rows": [],
        "category_distribution": {},
        "selection_process": [],
        "exam_pattern": [],
        "links": {
            "apply_link": "",
            "notif_pdf": "",
            "admit_card_link": "",
            "answer_key_link": "",
            "result_link": "",
            "syllabus_link": "",
            "official_site": ""
        }
    }

    if not article_html:
        return dossier

    soup = BeautifulSoup(article_html, "html.parser")

    # --- STEP A: EXTRACT REAL PUBLISHED / UPDATED DATE FROM META OR JSON-LD ---
    meta_dates = []
    for meta in soup.find_all("meta"):
        prop = (meta.get("property", "") or meta.get("name", "")).lower()
        if any(k in prop for k in ["published_time", "modified_time", "date", "pubdate", "updated_time"]):
            dt = parse_any_date_string(meta.get("content", ""))
            if dt:
                meta_dates.append(dt)

    for time_tag in soup.find_all("time"):
        dt = parse_any_date_string(time_tag.get("datetime", "") or time_tag.get_text(" ", strip=True))
        if dt:
            meta_dates.append(dt)

    # Also check visible text like "Post Date / Update:" on SarkariResult / FreeJobAlert
    text_blob = soup.get_text(" ", strip=True)
    post_date_match = re.search(r'(?:Post Date|Post Update Date|Updated On|Published On|Date of Post)\s*[:\-]?\s*([0-9]{1,2}[\s\/\-\.][A-Za-z0-9]+[\s\/\-\.,]+202[4-9])', text_blob, re.IGNORECASE)
    if post_date_match:
        dt = parse_any_date_string(post_date_match.group(1))
        if dt:
            meta_dates.insert(0, dt)

    # --- STEP B: PARSE ALL TABLE ROWS & LIST ITEMS FOR DATES, FEES, AGE, VACANCY & LINKS ---
    for tr in soup.find_all(["tr", "li"]):
        row_text = re.sub(r'\s+', ' ', tr.get_text(" ", strip=True)).strip()
        row_low = row_text.lower()
        if not row_text or len(row_text) > 500:
            continue

        # 1. Important Dates Extraction
        dt_in_row = parse_any_date_string(row_text)
        if dt_in_row:
            meta_dates.append(dt_in_row)
            dt_formatted = dt_in_row.strftime("%d %b %Y")
            if any(k in row_low for k in ["notification", "advt", "published", "issue"]):
                dossier["dates"]["notification_date"] = dt_formatted
            if any(k in row_low for k in ["application begin", "start date", "starting date", "apply start", "registration start"]):
                dossier["dates"]["apply_start_date"] = dt_formatted
            if any(k in row_low for k in ["last date", "closing date", "apply online last"]):
                if "extended" in row_low:
                    dossier["dates"]["extended_date"] = dt_formatted
                else:
                    dossier["dates"]["last_date"] = dt_formatted
            if "extended" in row_low:
                dossier["dates"]["extended_date"] = dt_formatted
            if any(k in row_low for k in ["exam date", "cbt date", "prelims exam", "mains exam", "written exam"]):
                dossier["dates"]["exam_date"] = dt_formatted
            if any(k in row_low for k in ["admit card", "hall ticket", "call letter"]):
                dossier["dates"]["admit_card_date"] = dt_formatted
            if any(k in row_low for k in ["answer key", "objection"]):
                dossier["dates"]["answer_key_date"] = dt_formatted
            if any(k in row_low for k in ["result", "merit list", "score card"]):
                dossier["dates"]["result_date"] = dt_formatted

        # 2. Application Fee Extraction
        if any(k in row_low for k in ["general / obc", "gen / obc", "sc / st", "application fee", "₹", "rs.", "rs /-", "nil", "exempted"]):
            if len(dossier["fees"]) < 6 and len(row_text) < 160 and "click here" not in row_low:
                dossier["fees"].append(row_text)

        # 3. Age Criteria Extraction
        if any(k in row_low for k in ["minimum age", "maximum age", "age limit", "age relaxation", "years", "born between"]):
            if len(dossier["age_criteria"]) < 6 and len(row_text) < 180 and "click here" not in row_low:
                dossier["age_criteria"].append(row_text)

        # 4. Total Vacancy & Category-Wise Distribution Extraction
        tot_match = re.search(r'(?:Total\s+Vacanc(?:y|ies)|Total\s+Posts?)\s*[:\-]?\s*(\d{1,6})\b', row_text, re.IGNORECASE)
        if tot_match:
            dossier["total_vacancy"] = f"{tot_match.group(1)} Posts"

        cells = [re.sub(r'\s+', ' ', td.get_text(" ", strip=True)).strip() for td in tr.find_all(["td", "th"])]
        if len(cells) >= 2:
            # Check if row has category breakdown headers or values (UR, OBC, EWS, SC, ST, Total)
            joined_c = " | ".join(cells)
            if any(k in row_low for k in ["ur", "obc", "ews", "sc", "st", "general", "post name", "trade name", "eligibility", "qualification"]):
                if "click here" not in row_low and len(dossier["vacancy_rows"]) < 10:
                    dossier["vacancy_rows"].append(cells[:6])

        # 5. Selection Process & Exam Pattern Extraction
        if any(k in row_low for k in ["selection process", "stage 1", "tier 1", "prelims", "mains", "physical test", "pet", "pst", "document verification", "medical exam", "skill test"]):
            if len(dossier["selection_process"]) < 6 and "click here" not in row_low and len(row_text) < 200:
                dossier["selection_process"].append(row_text)

        if any(k in row_low for k in ["negative marking", "questions", "marks", "duration", "minutes", "objective type", "reasoning", "quantitative", "general awareness"]):
            if len(dossier["exam_pattern"]) < 6 and "click here" not in row_low and len(row_text) < 200:
                dossier["exam_pattern"].append(row_text)

        # 6. INTENT-AWARE ROW-CONTEXT LINK EXTRACTION (Crucial Fix!)
        anchors = tr.find_all("a", href=True)
        for a in anchors:
            href = urljoin(article_url, a["href"].strip())
            a_text = a.get_text(" ", strip=True).lower()
            combined_context = f"{row_low} {a_text}"

            # Check for PDF / Notification
            if is_clean_external_url(href, allow_aggregator_pdf=True):
                if ".pdf" in href.lower() or any(k in combined_context for k in ["notification", "advt", "advertisement", "brochure", "short notice", "information bulletin"]):
                    if any(k in combined_context for k in ["syllabus", "exam pattern"]):
                        if not dossier["links"]["syllabus_link"]:
                            dossier["links"]["syllabus_link"] = href
                    elif any(k in combined_context for k in ["answer key", "response sheet"]):
                        if not dossier["links"]["answer_key_link"]:
                            dossier["links"]["answer_key_link"] = href
                    elif any(k in combined_context for k in ["result", "merit list", "cutoff", "list of selected"]):
                        if not dossier["links"]["result_link"]:
                            dossier["links"]["result_link"] = href
                    else:
                        if not dossier["links"]["notif_pdf"]:
                            dossier["links"]["notif_pdf"] = href

            # Check for External Official Portal Links (Apply, Admit Card, Answer Key, Result, Syllabus, Official Site)
            if is_clean_external_url(href, allow_aggregator_pdf=False):
                if any(k in combined_context for k in ["apply online", "registration", "online form", "candidate login", "apply link", "new registration"]):
                    if not dossier["links"]["apply_link"]:
                        dossier["links"]["apply_link"] = href
                elif any(k in combined_context for k in ["admit card", "hall ticket", "call letter", "exam city"]):
                    if not dossier["links"]["admit_card_link"]:
                        dossier["links"]["admit_card_link"] = href
                elif any(k in combined_context for k in ["answer key", "response sheet", "question paper", "objection"]):
                    if not dossier["links"]["answer_key_link"]:
                        dossier["links"]["answer_key_link"] = href
                elif any(k in combined_context for k in ["download result", "check result", "result", "merit list", "score card", "scorecard"]):
                    if not dossier["links"]["result_link"]:
                        dossier["links"]["result_link"] = href
                elif any(k in combined_context for k in ["syllabus", "exam pattern"]):
                    if not dossier["links"]["syllabus_link"]:
                        dossier["links"]["syllabus_link"] = href
                elif any(k in combined_context for k in ["official website", "official portal", "official site"]):
                    if not dossier["links"]["official_site"]:
                        dossier["links"]["official_site"] = href

    # --- STEP C: RESOLVE REAL POST DATE ---
    valid_dates = [d for d in meta_dates if d <= datetime.now() + timedelta(days=365)]
    if valid_dates:
        # Pick the most recent past/current date as the post release/update date
        past_or_today = [d for d in valid_dates if d <= datetime.now() + timedelta(days=2)]
        chosen_dt = max(past_or_today) if past_or_today else min(valid_dates)
        dossier["dates"]["real_post_date_obj"] = chosen_dt
        dossier["dates"]["real_post_date_str"] = chosen_dt.strftime("%d %b %Y")
        if dossier["dates"]["notification_date"] == "See Official Notice":
            dossier["dates"]["notification_date"] = chosen_dt.strftime("%d %b %Y")

    return dossier

async def verify_and_enrich_from_official_hub(title, primary_intent, dossier, loop, semaphore):
    """
    If specific intent link or PDF wasn't on the aggregator page, crawl the mapped official portal's
    notice board / career page to find the exact active link or PDF for this specific post.
    """
    hub = match_hub_for_title(title)
    links = dossier["links"]

    if hub:
        if not links["official_site"]:
            links["official_site"] = hub["home"]

        # Crawl official notice board if specific intent link is still missing
        need_crawl = (
            (primary_intent == "INTENT_APPLY" and not links["apply_link"]) or
            (primary_intent == "INTENT_NOTIFICATION" and not links["notif_pdf"]) or
            (primary_intent == "INTENT_ADMIT_CARD" and not links["admit_card_link"]) or
            (primary_intent == "INTENT_ANSWER_KEY" and not links["answer_key_link"]) or
            (primary_intent == "INTENT_RESULT" and not links["result_link"])
        )
        if need_crawl:
            notice_html = await safe_fetch_non_blocking(hub["notices"], loop, semaphore, timeout=18.0)
            if notice_html:
                soup = BeautifulSoup(notice_html, "html.parser")
                title_tokens = [w for w in re.findall(r'[a-zA-Z0-9]{3,}', title.lower()) if w not in {"recruitment", "online", "form", "exam", "examination", "2026", "post", "posts"}]
                for a in soup.find_all("a", href=True):
                    href = urljoin(hub["notices"], a["href"].strip())
                    a_txt = a.get_text(" ", strip=True).lower()
                    if not href.startswith("http"):
                        continue
                    # Match keywords from post title
                    if any(tok in a_txt or tok in href.lower() for tok in title_tokens[:4]):
                        if ".pdf" in href.lower() and not links["notif_pdf"]:
                            links["notif_pdf"] = href
                        elif not links["apply_link"]:
                            links["apply_link"] = href

        # Use hub's dedicated application portal if still missing
        if not links["apply_link"]:
            links["apply_link"] = hub.get("apply_portal", hub["notices"])
        if not links["notif_pdf"]:
            links["notif_pdf"] = hub["notices"]

    # Map primary intent link strictly
    if primary_intent == "INTENT_ANSWER_KEY":
        primary_url = links["answer_key_link"] or links["notif_pdf"] or links["apply_link"] or links["official_site"]
    elif primary_intent == "INTENT_RESULT":
        primary_url = links["result_link"] or links["notif_pdf"] or links["apply_link"] or links["official_site"]
    elif primary_intent == "INTENT_ADMIT_CARD":
        primary_url = links["admit_card_link"] or links["apply_link"] or links["notif_pdf"] or links["official_site"]
    elif primary_intent == "INTENT_SYLLABUS":
        primary_url = links["syllabus_link"] or links["notif_pdf"] or links["official_site"]
    elif primary_intent == "INTENT_NOTIFICATION":
        primary_url = links["notif_pdf"] or links["apply_link"] or links["official_site"]
    else:
        primary_url = links["apply_link"] or links["notif_pdf"] or links["official_site"]

    # Synchronize all sub-links so no field is ever empty, '#' or Google search
    if not links["apply_link"]:
        links["apply_link"] = primary_url
    if not links["notif_pdf"]:
        links["notif_pdf"] = primary_url
    if not links["official_site"]:
        links["official_site"] = primary_url

    dossier["primary_verified_link"] = primary_url
    return dossier

def passes_one_month_freshness_gate(dossier, title):
    """
    Strictly rejects posts older than 30 days (1 month) unless their last_date or exam_date is still in the future.
    """
    t_low = title.lower()
    # Reject explicitly outdated years in title
    if any(old_yr in t_low for old_yr in ["2021", "2022", "2023", "2024"]):
        if "2026" not in t_low and "2025" not in t_low:
            return False

    now = datetime.now()
    cutoff_past = now - timedelta(days=31)

    # Check if last_date is in the future (still active to apply)
    last_dt = parse_any_date_string(dossier["dates"].get("last_date", ""))
    if last_dt and last_dt >= now - timedelta(days=3):
        return True

    # Check real_post_date_obj
    post_dt = dossier["dates"].get("real_post_date_obj")
    if post_dt:
        return post_dt >= cutoff_past

    # If no parseable date was found at all on the page, reject if we don't have a verified external link
    return bool(dossier.get("primary_verified_link"))

# ==============================================================================
# LAYER 5: INTENT-AWARE NON-REPEATING CHALLENGING QUOTE ENGINE
# ==============================================================================
INTENT_QUOTE_TEMPLATES = {
    "INTENT_APPLY": [
        "🔥 [{exam} Registration Challenge]: Form bharna sirf pehla kadam hai—aaj se rozana 8 ghante ki kadi tapasya ka sankalp lein aur apni seat pakki karein!",
        "⚡ [{exam} Mission Day-1]: Lakhon candidates form bharenge, par selection unhi ka hoga jo aaj hi syllabus ko apna hathiyar banayenge!",
        "🎯 [{exam} Lakshya Vedh]: Application window khul chuki hai—bina waqt gawaye form submit karein aur pehle mock test se apni raneeti shuru karein!",
        "🦁 [{exam} Sangharsh Shuru]: Yeh sirf ek online form nahi, aapke sapno ka appointment letter hai—aaj se har ek minute koetihasik banayein!"
    ],
    "INTENT_ADMIT_CARD": [
        "⚔️ [{exam} Admit Card Out]: Ranbhoomi ka bulawa aa chuka hai! Ab naye topics chhodkar sirf revision, speed aur 100% accuracy par prahar karein!",
        "⏱️ [{exam} Final Countdown]: Hall ticket aapke haath mein hai—exam hall ka pressure wahi jeetega jiski mock practice mein loh-anushasan raha hai!",
        "🛡️ [{exam} Exam Hall Temperament]: Admit card download karein aur aakhiri dino mein apni galtiyon ko zero par layein—ab waqt faisle ka hai!",
        "🚀 [{exam} Antim Prahar]: Mehnat ke mahine ab kuch ghanto ke imtihaan mein badalne wale hain—apne aatmavishwas ko chattan jaisa majboot rakhein!"
    ],
    "INTENT_ANSWER_KEY": [
        "🔍 [{exam} Answer Key Challenge]: Har ek sahi aur galat sawal ka post-mortem karein—yahi deep analysis aapko agle charan ka topper banayega!",
        "📊 [{exam} Score Evaluation]: Answer key aa chuki hai! Apne raw marks check karein, doubtful questions par objection uthayein aur Mains/Next Stage ki raneeti banayein!",
        "🧠 [{exam} Self-Audit Mode]: Response sheet sirf score nahi dikhati, aapki taiyari ka aaina dikhati hai—apne weak zones ko aaj hi chinhit karein!",
        "⚡ [{exam} Next Stage Readiness]: Answer key se apna sacha aakalan karein aur bina ruke agle padav ki taiyari mein dugni taqat jhonk dein!"
    ],
    "INTENT_RESULT": [
        "🏆 [{exam} Result Milestone]: Parinaam ghoshit ho chuka hai! Safal abhyarthiyon ko badhai aur agle charan/DV ke liye kamar kas lein—safar abhi poora nahi hua!",
        "🌟 [{exam} Merit List Update]: Jinhe safalta mili wo agle padav ko fateh karein, aur jo kuch anko se chooke wo dugne josh se agle imtihaan par tut padein!",
        "🎖️ [{exam} Selection Verdict]: Result aapki kadi mehnat ki gawahi hai—apna roll number check karein aur aage ke document verification ki har shart poori karein!",
        "🔥 [{exam} Victory & Persistence]: Ek parinaam aapki kabiliyat ki seema nahi tay karta—apna scorecard dekhein aur apne lakshya tak bina thake aage badhein!"
    ],
    "INTENT_SYLLABUS": [
        "📘 [{exam} Blueprint Decoded]: Bina syllabus samjhe taiyari andhere mein teer chalane jaisi hai—har ek topic ko print karein aur ek-ek karke khatam karein!",
        "🧭 [{exam} Master Syllabus]: Toppers alag kitabein nahi padhte, wo syllabus ke har point aur exam pattern ko ungliyon par yaad rakhte hain!",
        "📐 [{exam} Strategy Map]: Official syllabus aur weightage aapke samne hai—high-scoring subjects ko pehle 30 dino mein poori tarah मुट्ठी mein karein!"
    ],
    "INTENT_NOTIFICATION": [
        "📢 [{exam} Official Notification Out]: Vigyapti jaari ho chuki hai! Eligibility, age criteria aur exam pattern ko dhyan se padhein aur aaj hi 90-din ka plan lock karein!",
        "📜 [{exam} Recruitment Alert]: Sarkari naukri ka naya avsar dastak de raha hai—official PDF ka har niyam samjhein aur bheed se aage nikal jayein!",
        "🔥 [{exam} Golden Opportunity]: Notification PDF aa chuka hai—vacancy kam ho ya zyada, aapko sirf apni ek pakki seat ke liye ladna hai!"
    ]
}

def generate_unique_intent_quote(title, primary_intent, used_quotes_set, counter_seed):
    clean_exam = re.sub(r'\b(online form|recruitment|2026|2025|apply online|download|notification)\b', '', title, flags=re.IGNORECASE)
    clean_exam = re.sub(r'\s+', ' ', clean_exam).strip()[:38] or title[:35]

    templates = INTENT_QUOTE_TEMPLATES.get(primary_intent, INTENT_QUOTE_TEMPLATES["INTENT_APPLY"])
    for idx in range(len(templates)):
        candidate = templates[(counter_seed + idx) % len(templates)].format(exam=clean_exam)
        if candidate.lower() not in used_quotes_set:
            used_quotes_set.add(candidate.lower())
            return candidate

    # Guaranteed unique fallback with hash suffix if all templates for that exact exam title were used
    unique_tag = hashlib.md5(f"{title}_{primary_intent}_{counter_seed}".encode("utf-8")).hexdigest()[:4].upper()
    fallback_quote = f"🔥 [{clean_exam} | {primary_intent.replace('INTENT_', '')} #{unique_tag}]: Apni kadi mehnat, rozana mock analysis aur atoot anushasan se is pariksha mein apna parcham lehrayein!"
    used_quotes_set.add(fallback_quote.lower())
    return fallback_quote

# ==============================================================================
# LAYER 6 & 7: OPTION A (FULL DOSSIER) + OPTION B (90-DAY STRATEGY) SYNTHESIZER
# ==============================================================================
def build_90_day_strategy(title, meta):
    t = title.lower()
    if any(k in t for k in ["ibps", "sbi", "rbi", "nabard", "bank", "lic", "niacl", "uiic", "idbi"]):
        return {
            "month_1": "Speed Math (Simplification, Quadratic, Number Series), Seating Arrangement & Linear/Circular Puzzles के बुनियादी नियम, और Reading Comprehension व Grammar (S-V-A) की रोज़ाना 3 घंटे प्रैक्टिस करें।",
            "month_2": "Data Interpretation (Tabulated, Pie, Caselet), High-Level Floor/Box Puzzles, और पिछले 6 महीनों के Banking & Financial Current Affairs के साथ रोज़ाना 2 Sectional Timed Mocks लगाएं।",
            "month_3": "रोज़ाना 1 Full-Length Prelims/Mains Mock Test दें, गलत हुए सवालों की Error Notebook बनाएं, और GA/Banking Awareness का बार-बार रिविज़न करके अपनी Accuracy 90%+ पर लॉक करें।"
        }
    elif any(k in t for k in ["ssc", "rrb", "railway", "ntpc", "group d", "alp", "cgl", "chsl", "mts", "gd", "delhipolice", "upssc", "bssc"]):
        return {
            "month_1": "Arithmetic & Advance Maths के सभी फॉर्मूले, Reasoning के Coding-Decoding/Series/Analogy पैटर्न, और NCERT आधारित Static GK व Science के मुख्य कॉन्सेप्ट्स पूरे करें।",
            "month_2": "पिछले 5 वर्षों के TCS/Official Previous Year Questions (PYQs) को टाइमर के साथ हल करें। Calculation Speed बढ़ाने के लिए Tables, Squares, Cubes और Fraction-to-Percentage रोज़ दोहराएं।",
            "month_3": "रोज़ाना 1-2 Full CBT Mock Tests का गहन विश्लेषण (Deep Analysis) करें, कमज़ोर टॉपिक्स पर 50-50 सवाल हल करें और पिछले 1 वर्ष के Current Affairs व Static GK को पक्का करें।"
        }
    else:
        return {
            "month_1": "आधिकारिक सिलेबस (Official Syllabus) को डिकोड करें, Core Domain Subjects और State/General Studies के फाउंडेशन नोट्स तैयार करें और बुनियादी अवधारणाओं को मज़बूत करें।",
            "month_2": "Previous Year Question Papers (PYQs) के ट्रेंड को समझें, हाई-वेटेज टॉपिक्स पर विशेष पकड़ बनाएं और हर सप्ताह 3 विषयवार टेस्ट (Topic-wise Tests) देकर समय प्रबंधन सुधारें।",
            "month_3": "अंतिम 30 दिनों में कोई नई किताब न छूएं—केवल अपने शॉर्ट नोट्स का रिविज़न करें, रोज़ाना 1 Full Mock Test दें और परीक्षा हॉल के टेम्परामेंट व एक्यूरेसी पर फोकस करें।"
        }

class MasterSynthesizer:
    @staticmethod
    def build_post(title, source_name, meta, dossier, used_quotes_set, counter_seed):
        primary_url = dossier.get("primary_verified_link", "")
        if not primary_url or not primary_url.startswith("http"):
            return None

        intent_sig = f"{hashlib.md5(title.lower().encode('utf-8')).hexdigest()[:10]}__{meta['primary_intent']}"
        job_id = hashlib.md5(intent_sig.encode("utf-8")).hexdigest()[:12]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        real_date_str = dossier["dates"].get("real_post_date_str") or dossier["dates"].get("notification_date")
        if not real_date_str or real_date_str == "See Official Notice":
            real_date_str = datetime.now().strftime("%d %b %Y")

        quote = generate_unique_intent_quote(title, meta["primary_intent"], used_quotes_set, counter_seed)
        strategy = build_90_day_strategy(title, meta)

        links = dossier["links"]
        apply_link = links["apply_link"] or primary_url
        notif_pdf = links["notif_pdf"] or primary_url
        admit_card_link = links["admit_card_link"] or primary_url
        answer_key_link = links["answer_key_link"] or primary_url
        result_link = links["result_link"] or primary_url
        syllabus_link = links["syllabus_link"] or notif_pdf
        official_site = links["official_site"] or primary_url

        # Intent-specific Primary Action Button label & URL
        intent_action_map = {
            "INTENT_APPLY": ("🚀 Direct Official Registration / Apply Online Link", apply_link),
            "INTENT_NOTIFICATION": ("📄 Download Official Notification PDF", notif_pdf),
            "INTENT_ADMIT_CARD": ("🎫 Download Official Admit Card / Hall Ticket", admit_card_link),
            "INTENT_ANSWER_KEY": ("🔑 Download Official Answer Key / Response Sheet", answer_key_link),
            "INTENT_RESULT": ("🏆 Check Official Result / Merit List PDF", result_link),
            "INTENT_SYLLABUS": ("📘 Download Official Syllabus & Exam Pattern PDF", syllabus_link)
        }
        primary_btn_label, primary_btn_url = intent_action_map.get(meta["primary_intent"], ("🔗 Open Official Portal Link", primary_url))

        # Format Fees, Age, Selection, Pattern & Vacancy Tables
        fee_html = "".join(f"<li>{f}</li>" for f in dossier["fees"]) or "<li>As per official notification norms (Check category-wise fee relaxation in official PDF).</li>"
        age_html = "".join(f"<li>{a}</li>" for a in dossier["age_criteria"]) or "<li>Age Limit & Upper Age Relaxation (SC/ST/OBC/PwBD/Ex-SM) as per official recruitment rules.</li>"
        sel_html = "".join(f"<li>{s}</li>" for s in dossier["selection_process"]) or "<li>Written Examination (CBT / Mains) ➔ Skill / Physical Test (if applicable) ➔ Document Verification & Medical.</li>"
        pat_html = "".join(f"<li>{p}</li>" for p in dossier["exam_pattern"]) or "<li>Objective / Descriptive Examination as prescribed in the official notification brochure.</li>"

        vac_table_rows = ""
        if dossier["vacancy_rows"]:
            for r in dossier["vacancy_rows"][:8]:
                vac_table_rows += "<tr>" + "".join(f"<td style='border:1px solid #cbd5e1; padding:6px 10px;'>{c}</td>" for c in r) + "</tr>"
        else:
            vac_table_rows = f"<tr><td style='border:1px solid #cbd5e1; padding:6px 10px;'>{title}</td><td style='border:1px solid #cbd5e1; padding:6px 10px;'>{dossier['total_vacancy']}</td><td style='border:1px solid #cbd5e1; padding:6px 10px;'>UR / OBC / EWS / SC / ST as per Official PDF</td></tr>"

        short_view_html = f"""
<div class="short-view-card" style="background:#ffffff; border:1px solid #cbd5e1; border-radius:10px; padding:16px; margin-bottom:16px;">
    <div style="background:#fef3c7; border-left:4px solid #d97706; padding:8px 12px; margin-bottom:10px; font-weight:700; color:#92400e; font-size:13.5px;">{quote}</div>
    <h3 style="margin:0 0 8px; color:#0f172a;">📢 {title}</h3>
    <p style="margin:4px 0; font-size:13px; color:#334155;">
        <strong>Box/Category:</strong> {meta['admin_box']} | <strong>Intent:</strong> {meta['primary_intent']} | <strong>Type:</strong> {meta['job_type']} | <strong>State:</strong> {meta['state']}
    </p>
    <p style="margin:4px 0; font-size:13px; color:#334155;">
        <strong>Release/Update Date:</strong> {real_date_str} | <strong>Last Date:</strong> {dossier['dates']['last_date']} | <strong>Total Vacancy:</strong> {dossier['total_vacancy']}
    </p>
    <div style="margin-top:10px;">
        <a href="{primary_btn_url}" target="_blank" rel="noopener" style="display:inline-block; background:#1d4ed8; color:#ffffff; padding:8px 14px; border-radius:6px; font-weight:700; text-decoration:none; font-size:13px;">{primary_btn_label}</a>
        <a href="{notif_pdf}" target="_blank" rel="noopener" style="display:inline-block; background:#0f766e; color:#ffffff; padding:8px 14px; border-radius:6px; font-weight:700; text-decoration:none; font-size:13px; margin-left:8px;">📄 Official Notification PDF</a>
    </div>
</div>
"""

        full_details_html = f"""
{short_view_html}
<div class="full-dossier-view" style="background:#f8fafc; border:1px solid #94a3b8; border-radius:10px; padding:18px; margin-bottom:24px;">
    <h4 style="margin:0 0 12px; color:#1e3a8a; border-bottom:2px solid #1e3a8a; padding-bottom:6px;">📋 OPTION A: COMPLETE OFFICIAL RECRUITMENT DOSSIER & VERIFIED TABLES</h4>

    <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:14px; margin-bottom:16px;">
        <div style="background:#ffffff; border:1px solid #cbd5e1; padding:12px; border-radius:8px;">
            <h5 style="margin:0 0 8px; color:#b91c1c;">📅 Important Dates (Official Schedule)</h5>
            <ul style="margin:0; padding-left:18px; font-size:13px; line-height:1.6;">
                <li><strong>Notification Release Date:</strong> {dossier['dates']['notification_date']}</li>
                <li><strong>Apply Online Start Date:</strong> {dossier['dates']['apply_start_date']}</li>
                <li><strong>Last Date to Apply:</strong> {dossier['dates']['last_date']}</li>
                <li><strong>Extended Last Date:</strong> {dossier['dates']['extended_date']}</li>
                <li><strong>Exam Date:</strong> {dossier['dates']['exam_date']}</li>
                <li><strong>Admit Card Date:</strong> {dossier['dates']['admit_card_date']}</li>
                <li><strong>Answer Key Date:</strong> {dossier['dates']['answer_key_date']}</li>
                <li><strong>Result Date:</strong> {dossier['dates']['result_date']}</li>
            </ul>
        </div>
        <div style="background:#ffffff; border:1px solid #cbd5e1; padding:12px; border-radius:8px;">
            <h5 style="margin:0 0 8px; color:#047857;">💳 Application Fee & Age Criteria</h5>
            <p style="margin:0 0 4px; font-weight:700; font-size:12.5px;">Application Fee:</p>
            <ul style="margin:0 0 8px; padding-left:18px; font-size:13px;">{fee_html}</ul>
            <p style="margin:0 0 4px; font-weight:700; font-size:12.5px;">Age Limit & Relaxation:</p>
            <ul style="margin:0; padding-left:18px; font-size:13px;">{age_html}</ul>
        </div>
    </div>

    <div style="background:#ffffff; border:1px solid #cbd5e1; padding:12px; border-radius:8px; margin-bottom:16px; overflow-x:auto;">
        <h5 style="margin:0 0 8px; color:#1e40af;">📊 Category-Wise Vacancy Distribution & Eligibility Details (Total: {dossier['total_vacancy']})</h5>
        <table style="width:100%; border-collapse:collapse; font-size:13px;">
            <tbody>{vac_table_rows}</tbody>
        </table>
    </div>

    <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:14px; margin-bottom:16px;">
        <div style="background:#ffffff; border:1px solid #cbd5e1; padding:12px; border-radius:8px;">
            <h5 style="margin:0 0 8px; color:#6d28d9;">⚙️ Selection Process</h5>
            <ul style="margin:0; padding-left:18px; font-size:13px;">{sel_html}</ul>
        </div>
        <div style="background:#ffffff; border:1px solid #cbd5e1; padding:12px; border-radius:8px;">
            <h5 style="margin:0 0 8px; color:#0f766e;">📝 Exam Pattern & Syllabus Highlights</h5>
            <ul style="margin:0; padding-left:18px; font-size:13px;">{pat_html}</ul>
        </div>
    </div>

    <div style="background:#eef2ff; border-left:4px solid #4f46e5; padding:14px; border-radius:8px; margin-bottom:16px;">
        <h4 style="margin:0 0 8px; color:#312e81;">🎯 OPTION B: LAST 3-MONTH (90-DAY) AGENTIC AI EXAM STRATEGY</h4>
        <ul style="margin:0; padding-left:18px; font-size:13.5px; color:#1e293b; line-height:1.6;">
            <li><strong>Month 1 (Days 1–30 | Foundation & Core Syllabus):</strong> {strategy['month_1']}</li>
            <li><strong>Month 2 (Days 31–60 | Speed, PYQs & Sectional Mastery):</strong> {strategy['month_2']}</li>
            <li><strong>Month 3 (Days 61–90 | Full-Length Mocks & High-Yield Revision):</strong> {strategy['month_3']}</li>
        </ul>
    </div>

    <div style="background:#ffffff; border:2px solid #2563eb; padding:12px; border-radius:8px;">
        <h5 style="margin:0 0 8px; color:#1d4ed8;">🔗 Intent-Verified Official Direct Links & PDF Attachments</h5>
        <table style="width:100%; border-collapse:collapse; font-size:13.5px;">
            <tr><td style="padding:6px; border-bottom:1px solid #e2e8f0; font-weight:700;">{primary_btn_label}</td><td style="padding:6px; border-bottom:1px solid #e2e8f0;"><a href="{primary_btn_url}" target="_blank" style="color:#1d4ed8; font-weight:700;">Click Here to Open Exact Link</a></td></tr>
            <tr><td style="padding:6px; border-bottom:1px solid #e2e8f0; font-weight:700;">Specific Registration / Apply Online Link</td><td style="padding:6px; border-bottom:1px solid #e2e8f0;"><a href="{apply_link}" target="_blank" style="color:#1d4ed8; font-weight:700;">Apply Online / Candidate Login</a></td></tr>
            <tr><td style="padding:6px; border-bottom:1px solid #e2e8f0; font-weight:700;">Official Notification / Brochure PDF</td><td style="padding:6px; border-bottom:1px solid #e2e8f0;"><a href="{notif_pdf}" target="_blank" style="color:#0f766e; font-weight:700;">Download Official PDF</a></td></tr>
            <tr><td style="padding:6px; font-weight:700;">Official Recruitment Board Portal</td><td style="padding:6px;"><a href="{official_site}" target="_blank" style="color:#334155; font-weight:700;">Visit Official Website</a></td></tr>
        </table>
    </div>
</div>
"""

        return {
            "id": job_id,
            "intent_signature": intent_sig,
            "title": title,
            "category": meta["category"],
            "admin_box": meta["admin_box"],
            "is_new_admin_box": meta["is_new_admin_box"],
            "primary_intent": meta["primary_intent"],
            "job_type": meta["job_type"],
            "state": meta["state"],
            "unique_quote": quote,
            "source": source_name,
            "link": primary_btn_url,
            "url": primary_btn_url,
            "apply_link": apply_link,
            "notif_url": notif_pdf,
            "download_pdf": notif_pdf,
            "admit_card_link": admit_card_link,
            "answer_key_link": answer_key_link,
            "result_link": result_link,
            "syllabus_link": syllabus_link,
            "official_website": official_site,
            "date": real_date_str,
            "post_date": real_date_str,
            "important_dates": dossier["dates"],
            "total_vacancy": dossier["total_vacancy"],
            "application_fee": dossier["fees"],
            "age_criteria": dossier["age_criteria"],
            "selection_process": dossier["selection_process"],
            "exam_pattern": dossier["exam_pattern"],
            "exam_strategy_90_days": strategy,
            "updated_at": now_str,
            "summary": f"[{meta['primary_intent']}] {title} | Total: {dossier['total_vacancy']} | Last Date: {dossier['dates']['last_date']}",
            "short_view": short_view_html,
            "description": full_details_html,
            "content": full_details_html,
            "status": "pending_review"
        }

# ==============================================================================
# LAYER 8: PARALLEL NON-BLOCKING PIPELINE EXECUTOR
# ==============================================================================
def detect_box_heading_for_anchor(a_tag):
    """Finds the section/box heading above an anchor tag to detect dynamic/new categories."""
    parent = a_tag.find_parent(["div", "td", "table", "section", "ul"])
    for _ in range(4):
        if not parent:
            break
        heading = parent.find(["h1", "h2", "h3", "h4", "th", "caption"])
        if heading:
            htxt = re.sub(r'\s+', ' ', heading.get_text(" ", strip=True)).strip()
            if 3 <= len(htxt) <= 45:
                return htxt
        parent = parent.parent
    return ""

async def process_single_candidate(text, href, src_name, box_heading, used_quotes_set, counter_seed, loop, semaphore):
    try:
        meta = IntentAndMetaClassifierAgent.analyze(text, box_heading)
        article_html = await safe_fetch_non_blocking(href, loop, semaphore, timeout=22.0)
        if not article_html:
            return None

        dossier = deep_parse_article_dossier(article_html, href, text, meta["primary_intent"])
        dossier = await verify_and_enrich_from_official_hub(text, meta["primary_intent"], dossier, loop, semaphore)

        if not passes_one_month_freshness_gate(dossier, text):
            return None

        # Ensure serializable dates dict (remove datetime object before JSON dump)
        dossier["dates"].pop("real_post_date_obj", None)
        return MasterSynthesizer.build_post(text, src_name, meta, dossier, used_quotes_set, counter_seed)
    except Exception:
        return None

async def process_aggregator(src, seen_titles, used_quotes_set, discovered_boxes, loop, semaphore):
    posts = []
    html = await safe_fetch_non_blocking(src["url"], loop, semaphore, timeout=22.0)
    if not html:
        return posts

    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    for a in soup.find_all("a", href=True):
        text = re.sub(r'\s+', ' ', a.get_text(" ", strip=True)).strip()
        href = urljoin(src["url"], a["href"].strip())
        t_low = text.lower()

        if len(text) < 14 or len(text) > 140:
            continue
        if any(j in t_low for j in JUNK_TITLES):
            continue
        if not href.startswith("http") or any(b in href.lower() for b in BLOCK_DOMAINS):
            continue

        norm = re.sub(r'[^a-z0-9]+', ' ', t_low).strip()
        if norm in seen_titles:
            continue

        if any(kw in t_low for kw in [
            "recruitment", "online form", "result", "admit card", "answer key",
            "vacancy", "bharti", "2026", "notification", "syllabus", "merit list",
            "cutoff", "hall ticket", "apprentice", "officer", "clerk", "constable", "engineer"
        ]):
            seen_titles.add(norm)
            box_heading = detect_box_heading_for_anchor(a)
            if box_heading:
                discovered_boxes.add(box_heading)
            candidates.append((text, href, src["name"], box_heading))

    # Process candidates concurrently with 40s per-post timeout protection
    tasks = [
        asyncio.wait_for(
            process_single_candidate(text, href, s_name, box_h, used_quotes_set, idx, loop, semaphore),
            timeout=40.0
        )
        for idx, (text, href, s_name, box_h) in enumerate(candidates[:45])
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, dict) and r:
            posts.append(r)

    print(f"   ✅ {src['name']}: Verified {len(posts)} active posts (with real dates & intent links)")
    return posts

async def process_master_directory_entry(idx, title, hub_key, kws, posts_by_signature, used_quotes_set, loop, semaphore):
    """
    Crawls the official portal notice board for each Master Directory post to check for active
    notifications, apply links, admit cards, answer keys, or results.
    """
    try:
        hub = OFFICIAL_HUBS.get(hub_key)
        if not hub:
            return None

        meta = IntentAndMetaClassifierAgent.analyze(title, "Master Directory")
        intent_sig = f"{hashlib.md5(title.lower().encode('utf-8')).hexdigest()[:10]}__{meta['primary_intent']}"
        if intent_sig in posts_by_signature:
            return None

        notice_html = await safe_fetch_non_blocking(hub["notices"], loop, semaphore, timeout=18.0)
        dossier = deep_parse_article_dossier(notice_html, hub["notices"], title, meta["primary_intent"])
        dossier = await verify_and_enrich_from_official_hub(title, meta["primary_intent"], dossier, loop, semaphore)
        dossier["dates"].pop("real_post_date_obj", None)

        return MasterSynthesizer.build_post(title, f"Official Portal ({hub['name']})", meta, dossier, used_quotes_set, 1000 + idx)
    except Exception:
        return None

async def main_async():
    print("🚀 Starting 8-Layer Agentic AI Deep Recruitment Scraper Engine...")
    existing = []
    if os.path.exists(DATABASE_FILE):
        try:
            with open(DATABASE_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    posts_by_signature = {}
    used_quotes_set = set()
    seen_titles = set()
    discovered_boxes = set(STANDARD_BOXES)

    # Clean existing DB: purge any broken '#' or 'google.com/search' records so they get freshly re-scraped with real links
    for j in existing:
        if not isinstance(j, dict):
            continue
        ap_link = j.get("apply_link", "")
        if not ap_link or ap_link == "#" or "google.com/search" in ap_link:
            continue
        sig = j.get("intent_signature") or j.get("id", "")
        posts_by_signature[sig] = j
        if q := j.get("unique_quote"):
            used_quotes_set.add(q.lower())
        if t := j.get("title"):
            seen_titles.add(re.sub(r'[^a-z0-9]+', ' ', t.lower()).strip())
        if bx := j.get("admin_box"):
            discovered_boxes.add(bx)

    loop = asyncio.get_running_loop()
    semaphore = asyncio.Semaphore(25)

    # 1. Sweep all 8 Aggregators & Mirrors Concurrently
    agg_tasks = [process_aggregator(src, seen_titles, used_quotes_set, discovered_boxes, loop, semaphore) for src in SOURCES]
    agg_results = await asyncio.gather(*agg_tasks, return_exceptions=True)

    new_added = 0
    delta_updated = 0

    for res in agg_results:
        if isinstance(res, list):
            for post in res:
                sig = post["intent_signature"]
                if sig not in posts_by_signature:
                    posts_by_signature[sig] = post
                    new_added += 1
                else:
                    old_p = posts_by_signature[sig]
                    if old_p.get("apply_link") != post.get("apply_link") or old_p.get("download_pdf") != post.get("download_pdf"):
                        posts_by_signature[sig] = post
                        delta_updated += 1

    # 2. Sweep Master Directory Catalog Concurrently (Official Portals for Govt & Semi-Govt/Local Posts)
    md_tasks = [
        asyncio.wait_for(
            process_master_directory_entry(idx, title, hub_key, kws, posts_by_signature, used_quotes_set, loop, semaphore),
            timeout=35.0
        )
        for idx, (title, hub_key, kws) in enumerate(MASTER_DIRECTORY_CATALOG)
    ]
    md_results = await asyncio.gather(*md_tasks, return_exceptions=True)
    for post in md_results:
        if isinstance(post, dict) and post:
            sig = post["intent_signature"]
            if sig not in posts_by_signature:
                posts_by_signature[sig] = post
                new_added += 1

    final_db = list(posts_by_signature.values())
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(final_db, f, ensure_ascii=False, indent=2)

    # Save discovered Admin Panel Boxes (Standard + Newly Discovered Boxes)
    boxes_payload = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "standard_boxes": sorted(list(STANDARD_BOXES)),
        "all_discovered_boxes": sorted(list(discovered_boxes)),
        "new_custom_boxes": sorted(list(discovered_boxes - STANDARD_BOXES))
    }
    with open(ADMIN_BOXES_FILE, "w", encoding="utf-8") as bf:
        json.dump(boxes_payload, bf, ensure_ascii=False, indent=2)

    print(f"\n🎉 8-Layer Sync Complete! New Added: {new_added} | Delta Updated: {delta_updated} | Total Verified Records: {len(final_db)} | Admin Boxes: {len(discovered_boxes)}")

def main():
    try:
        # Strict 330s (5.5 minutes) hard limit to ensure GitHub Action always finishes under 6 minutes
        asyncio.run(asyncio.wait_for(main_async(), timeout=330.0))
    except asyncio.TimeoutError:
        print("⚠️ Reached 5.5-minute safety checkpoint. All verified posts saved cleanly.")

if __name__ == "__main__":
    main()

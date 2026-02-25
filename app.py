import streamlit as st
import sqlite3, httpx, json, re, random
from bs4 import BeautifulSoup

st.set_page_config(page_title="Amazon Content Analyser", page_icon="\U0001f6d2", layout="wide")

# ─── THEME CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif!important}
#MainMenu,footer,header{visibility:hidden}
.stDeployButton{display:none!important}
.stApp{background:#F0F4F8!important}
.main .block-container{max-width:1060px;padding:2rem 2rem 5rem}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#0F172A 0%,#1E1B4B 100%)!important;box-shadow:4px 0 24px rgba(0,0,0,.15)!important}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] span,[data-testid="stSidebar"] label,[data-testid="stSidebar"] div{color:#94A3B8!important}
[data-testid="stSidebar"] .stRadio label{font-size:.88rem!important;font-weight:500!important;padding:10px 14px!important;border-radius:10px!important;display:block!important;transition:all .15s!important}
[data-testid="stSidebar"] .stRadio label:hover{background:rgba(255,255,255,.07)!important;color:#E2E8F0!important}
[data-testid="stSidebar"] hr{border-color:rgba(255,255,255,.1)!important}
[data-testid="metric-container"]{background:white!important;border:1.5px solid #E8EDF2!important;border-radius:18px!important;padding:22px 24px!important;box-shadow:0 2px 8px rgba(0,0,0,.05)!important}
[data-testid="metric-container"] label{font-size:.72rem!important;font-weight:700!important;text-transform:uppercase!important;letter-spacing:.06em!important;color:#94A3B8!important}
[data-testid="metric-container"] [data-testid="stMetricValue"]{font-size:2.2rem!important;font-weight:800!important;color:#0F172A!important;letter-spacing:-.03em!important}
.stButton>button{font-family:'Inter',sans-serif!important;font-weight:600!important;font-size:.875rem!important;border-radius:10px!important;padding:.5rem 1.4rem!important;border:1.5px solid #E2E8F0!important;background:white!important;color:#374151!important;transition:all .15s ease!important;box-shadow:0 1px 2px rgba(0,0,0,.05)!important}
.stButton>button:hover{border-color:#6366F1!important;color:#6366F1!important;box-shadow:0 4px 12px rgba(99,102,241,.15)!important}
.stButton>button[kind="primary"]{background:linear-gradient(135deg,#6366F1,#8B5CF6)!important;color:white!important;border:none!important;box-shadow:0 4px 14px rgba(99,102,241,.35)!important}
.stButton>button[kind="primary"]:hover{background:linear-gradient(135deg,#4F46E5,#7C3AED)!important;box-shadow:0 6px 20px rgba(99,102,241,.45)!important;color:white!important;border:none!important}
[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input{border-radius:10px!important;border:1.5px solid #E2E8F0!important;background:white!important;font-size:.875rem!important;color:#1E293B!important;transition:all .2s!important}
[data-testid="stTextInput"] input:focus,[data-testid="stNumberInput"] input:focus{border-color:#6366F1!important;box-shadow:0 0 0 3px rgba(99,102,241,.12)!important}
[data-testid="stTextArea"] textarea{border-radius:12px!important;border:1.5px solid #E2E8F0!important;background:white!important;font-size:.875rem!important;color:#1E293B!important;line-height:1.6!important;transition:all .2s!important}
[data-testid="stTextArea"] textarea:focus{border-color:#6366F1!important;box-shadow:0 0 0 3px rgba(99,102,241,.12)!important}
[data-testid="stSelectbox"]>div>div{border-radius:10px!important;border:1.5px solid #E2E8F0!important;background:white!important}
[data-testid="stExpander"]{background:white!important;border:1.5px solid #E8EDF2!important;border-radius:14px!important;margin-bottom:10px!important;box-shadow:0 1px 4px rgba(0,0,0,.05)!important;overflow:hidden!important}
[data-testid="stExpander"] summary{font-weight:600!important;font-size:.9rem!important;color:#1E293B!important;padding:14px 18px!important;background:white!important}
[data-testid="stExpander"] summary:hover{background:#FAFBFF!important}
[data-testid="stExpander"]>div:last-child{padding:0 18px 18px!important}
[data-testid="stCheckbox"] label{font-size:.875rem!important;color:#374151!important}
[data-testid="stAlert"]{border-radius:12px!important;border:none!important;font-size:.875rem!important}
hr{border:none!important;border-top:1px solid #E8EDF2!important;margin:1.5rem 0!important}
code{background:#EEF2FF!important;color:#4F46E5!important;border-radius:6px!important;padding:2px 7px!important;font-size:.82rem!important}
</style>
""", unsafe_allow_html=True)

# ─── DATABASE ─────────────────────────────────────────────────────────────────
DB = "amazon_analyser.db"

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS product_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            keywords TEXT DEFAULT '[]', created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS scoring_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            title_weight REAL DEFAULT 25, bullets_weight REAL DEFAULT 25,
            aplus_weight REAL DEFAULT 25, keywords_weight REAL DEFAULT 25,
            title_min_length INTEGER DEFAULT 80, title_max_length INTEGER DEFAULT 200,
            title_keyword_in_first INTEGER DEFAULT 1, bullets_min_count INTEGER DEFAULT 5,
            bullets_min_length INTEGER DEFAULT 100, bullets_max_length INTEGER DEFAULT 255,
            keywords_min_coverage REAL DEFAULT 70, keywords_in_title INTEGER DEFAULT 1,
            is_default INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT, asin TEXT NOT NULL,
            product_line_id INTEGER, scoring_rule_id INTEGER,
            product_name TEXT, product_image TEXT, title TEXT,
            bullets TEXT DEFAULT '[]', has_aplus INTEGER DEFAULT 0, description TEXT,
            scrape_error TEXT, total_score REAL,
            title_score REAL, bullets_score REAL, aplus_score REAL, keywords_score REAL,
            title_issues TEXT DEFAULT '[]', bullets_issues TEXT DEFAULT '[]',
            aplus_issues TEXT DEFAULT '[]', keywords_issues TEXT DEFAULT '[]',
            found_keywords TEXT DEFAULT '[]', missing_keywords TEXT DEFAULT '[]',
            suggested_keywords TEXT DEFAULT '[]', created_at TEXT DEFAULT (datetime('now')));
        """)
        if not c.execute("SELECT id FROM scoring_rules WHERE is_default=1").fetchone():
            c.execute("INSERT INTO scoring_rules (name,is_default) VALUES ('Default Rule',1)")

init_db()

# ─── SCRAPER ──────────────────────────────────────────────────────────────────
UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

def scrape(asin):
    url = f"https://www.amazon.co.uk/dp/{asin}"
    headers = {"User-Agent": random.choice(UA), "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
               "Accept-Language": "en-GB,en;q=0.9", "Accept-Encoding": "gzip, deflate, br",
               "Connection": "keep-alive", "Upgrade-Insecure-Requests": "1"}
    with httpx.Client(follow_redirects=True, timeout=30.0) as client:
        r = client.get(url, headers=headers)
    if r.status_code == 503:
        raise Exception("Amazon returned 503 — rate limited. Wait a few minutes and try again.")
    if r.status_code != 200:
        raise Exception(f"HTTP {r.status_code} for ASIN {asin}.")
    if "captcha" in r.text.lower() and "robot" in r.text.lower():
        raise Exception("Amazon returned a CAPTCHA page. Try again in a few minutes.")
    soup = BeautifulSoup(r.text, "html.parser")
    title_el = soup.find("span", id="productTitle")
    title = title_el.get_text(strip=True) if title_el else None
    bullets = []
    feat = soup.find("div", id="feature-bullets")
    if feat:
        bullets = [i.get_text(strip=True) for i in feat.find_all("span", class_="a-list-item") if len(i.get_text(strip=True)) > 10]
    has_aplus = any(soup.find("div", id=aid) and len((soup.find("div", id=aid) or {}).get_text(strip=True) or "") > 50
                    for aid in ["aplus", "aplus3p_feature_div", "aplusBrandStory_feature_div"])
    desc_el = soup.find("div", id="productDescription")
    description = desc_el.get_text(strip=True) if desc_el else ""
    img_el = soup.find("img", id="landingImage") or soup.find("img", id="imgBlkFront")
    image_url = img_el.get("src") if img_el else None
    brand_el = soup.find("a", id="bylineInfo")
    brand = brand_el.get_text(strip=True) if brand_el else None
    return {"title": title, "bullets": bullets, "has_aplus": has_aplus,
            "description": description, "image_url": image_url, "brand": brand}

# ─── ANALYSER ─────────────────────────────────────────────────────────────────
def kw_split(content, keywords):
    cl = content.lower()
    return [k for k in keywords if k.lower() in cl], [k for k in keywords if k.lower() not in cl]

def analyse(scraped, keywords, rule):
    title = scraped.get("title") or ""
    bullets = scraped.get("bullets") or []
    has_aplus = scraped.get("has_aplus", False)
    desc = scraped.get("description") or ""
    mw = rule["title_weight"]
    ti, ts = [], 0
    if not title:
        ti = ["Title could not be retrieved from Amazon."]
    else:
        ln = len(title)
        if ln < rule["title_min_length"]:
            ti.append(f"Title too short ({ln} chars). Target: {rule['title_min_length']}\u2013{rule['title_max_length']} chars.")
            ts += mw * 0.4 * (ln / rule["title_min_length"])
        elif ln > rule["title_max_length"]:
            ti.append(f"Title too long ({ln} chars) \u2014 Amazon may truncate it.")
            ts += mw * 0.30
        else:
            ts += mw * 0.40
        found_t, _ = kw_split(title, keywords)
        kr = len(found_t) / len(keywords) if keywords else 1.0
        ts += mw * 0.40 * kr
        if kr < 0.3:
            ti.append(f"Only {len(found_t)}/{len(keywords)} keywords in title \u2014 move top keywords near the start.")
        elif kr < 0.6:
            ti.append(f"{len(found_t)}/{len(keywords)} keywords in title \u2014 room to improve.")
        if rule.get("title_keyword_in_first") and keywords:
            if not any(k.lower() in title[:80].lower() for k in keywords[:3]):
                ti.append("Primary keyword not in first 80 characters of the title.")
            else:
                ts += mw * 0.20
        if sum(1 for w in title.split() if w.isupper() and len(w) > 2) > 3:
            ti.append("Too many ALL-CAPS words \u2014 use Title Case for better readability.")
    mw2 = rule["bullets_weight"]
    bi, bs = [], 0
    if not bullets:
        bi = ["No bullet points found on the product page."]
    else:
        cnt = len(bullets)
        if cnt < rule["bullets_min_count"]:
            bi.append(f"Only {cnt} bullet(s). Recommended: {rule['bullets_min_count']}.")
            bs += mw2 * 0.30 * (cnt / rule["bullets_min_count"])
        else:
            bs += mw2 * 0.30
        short = [i+1 for i,b in enumerate(bullets) if len(b) < rule["bullets_min_length"]]
        long_ = [i+1 for i,b in enumerate(bullets) if len(b) > rule["bullets_max_length"]]
        if short: bi.append(f"Bullet(s) {short} are too short (< {rule['bullets_min_length']} chars).")
        if long_: bi.append(f"Bullet(s) {long_} exceed {rule['bullets_max_length']} chars \u2014 may be truncated.")
        ok = (cnt - len(short) - len(long_)) / cnt
        bs += mw2 * 0.30 * ok
        found_b, _ = kw_split(" ".join(bullets), keywords)
        kr2 = len(found_b) / len(keywords) if keywords else 1.0
        bs += mw2 * 0.40 * kr2
        if kr2 < 0.5:
            bi.append(f"Low keyword coverage in bullets ({len(found_b)}/{len(keywords)}). Add more target keywords.")
    a_s = rule["aplus_weight"] if has_aplus else 0
    ai = [] if has_aplus else ["No A+ Content detected. Adding A+ can boost conversion by 5\u201310% and improves brand storytelling."]
    mw4 = rule["keywords_weight"]
    ki, ks = [], 0
    all_content = " ".join(filter(None, [title, " ".join(bullets), desc]))
    if not keywords:
        ks, found_k, miss_k = mw4, [], []
        ki = ["No keywords assigned to this product line."]
    else:
        found_k, miss_k = kw_split(all_content, keywords)
        cov = len(found_k) / len(keywords) * 100
        ks = mw4 * (cov / 100)
        thresh = rule.get("keywords_min_coverage", 70)
        if cov < thresh:
            ki.append(f"Keyword coverage {cov:.0f}% (target >= {thresh:.0f}%). Missing: {', '.join(miss_k[:8])}{'...' if len(miss_k)>8 else ''}.")
        if rule.get("keywords_in_title") and keywords:
            ft2, _ = kw_split(title, keywords[:3])
            if not ft2:
                ki.append("None of the top 3 keywords appear in the title \u2014 move them there for SEO impact.")
    tokens = re.findall(r"\b[a-zA-Z]{4,}\b", all_content.lower())
    stop = {"with","this","that","from","have","will","your","their","also","each","which","they",
            "more","than","when","into","only","over","such","used","using","pack","item","product",
            "brand","quality","great","make","made","features","feature","design","provides","include",
            "perfect","ideal","easy","best","good","high","well","help","helps","allows","keep"}
    existing_l = {k.lower() for k in keywords}
    counts = {}
    for t in tokens:
        if t not in stop and t not in existing_l:
            counts[t] = counts.get(t, 0) + 1
    suggestions = sorted(counts, key=lambda x: -counts[x])[:15]
    total = round(min(ts,mw) + min(bs,mw2) + a_s + min(ks,mw4), 1)
    return {"total_score": total,
            "title_score": round(min(ts,mw),1), "bullets_score": round(min(bs,mw2),1),
            "aplus_score": round(a_s,1), "keywords_score": round(min(ks,mw4),1),
            "title_issues": ti, "bullets_issues": bi, "aplus_issues": ai, "keywords_issues": ki,
            "found_keywords": found_k, "missing_keywords": miss_k, "suggested_keywords": suggestions}

# ─── UI HELPERS ───────────────────────────────────────────────────────────────
def _score_meta(s):
    if s is None: s = 0
    if s >= 85: return "#10B981","#D1FAE5","#065F46","Excellent"
    if s >= 65: return "#F59E0B","#FEF3C7","#92400E","Good"
    if s >= 40: return "#F97316","#FFEDD5","#9A3412","Needs Work"
    return "#EF4444","#FEE2E2","#991B1B","Poor"

def _bar_c(pct):
    if pct >= 85: return "#10B981"
    if pct >= 65: return "#F59E0B"
    if pct >= 40: return "#F97316"
    return "#EF4444"

def score_gauge(score, size=115):
    if score is None: score = 0
    c, bg, tc, lbl = _score_meta(score)
    d = 100 - score
    s = str(size)
    sc = str(int(score))
    return (
        f'<div style="display:flex;flex-direction:column;align-items:center;gap:8px">' +
        f'<div style="position:relative;width:{s}px;height:{s}px">' +
        f'<svg viewBox="0 0 36 36" style="width:100%;height:100%;transform:rotate(-90deg)">' +
        f'<circle cx="18" cy="18" r="15.9155" fill="none" stroke="#F1F5F9" stroke-width="2.8"/>' +
        f'<circle cx="18" cy="18" r="15.9155" fill="none" stroke="{c}" stroke-width="2.8" stroke-dasharray="{score} {d}" stroke-linecap="round"/>' +
        f'</svg>' +
        f'<div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center">' +
        f'<span style="font-size:1.55rem;font-weight:800;color:#0F172A;line-height:1">{sc}</span>' +
        f'<span style="font-size:0.6rem;color:#94A3B8;font-weight:600;letter-spacing:.05em">/ 100</span>' +
        f'</div></div>' +
        f'<span style="font-size:.75rem;font-weight:700;background:{bg};color:{tc};padding:3px 12px;border-radius:20px;letter-spacing:.03em">{lbl}</span>' +
        f'</div>'
    )

def score_bar(label, score, max_score, icon=""):
    pct = (score / max_score * 100) if max_score else 0
    color = _bar_c(pct)
    sc = f"{score:.1f}"
    ms = f"{max_score:.0f}"
    pt = f"{pct:.1f}"
    return (
        f'<div style="margin:14px 0">' +
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:7px">' +
        f'<span style="font-size:.88rem;font-weight:600;color:#1E293B">{icon} {label}</span>' +
        f'<div style="display:flex;align-items:center;gap:5px">' +
        f'<span style="font-size:.95rem;font-weight:700;color:{color}">{sc}</span>' +
        f'<span style="font-size:.78rem;color:#CBD5E1;font-weight:500">/ {ms}</span>' +
        f'</div></div>' +
        f'<div style="background:#F1F5F9;border-radius:999px;height:10px;overflow:hidden">' +
        f'<div style="background:{color};width:{pt}%;height:100%;border-radius:999px;box-shadow:0 0 6px {color}55"></div>' +
        f'</div></div>'
    )

def issue_box(text):
    return (
        f'<div style="display:flex;gap:10px;align-items:flex-start;background:#FFFBEB;' +
        f'border:1px solid #FDE68A;border-radius:10px;padding:10px 14px;margin:5px 0;' +
        f'font-size:.82rem;color:#78350F;line-height:1.5">' +
        f'<span style="flex-shrink:0;margin-top:1px">\u26a0\ufe0f</span><span>{text}</span></div>'
    )

def ok_box(label):
    return (
        f'<div style="display:flex;gap:8px;align-items:center;background:#ECFDF5;' +
        f'border:1px solid #A7F3D0;border-radius:10px;padding:9px 14px;margin:5px 0;' +
        f'font-size:.82rem;color:#065F46;font-weight:500">\u2705 {label} — no issues found.</div>'
    )

def kw_pill(text, t="found"):
    styles = {"found":"background:#DCFCE7;color:#166534;border:1px solid #BBF7D0",
              "missing":"background:#FEE2E2;color:#991B1B;border:1px solid #FECACA",
              "suggest":"background:#EEF2FF;color:#3730A3;border:1px solid #C7D2FE"}
    icons = {"found":"\u2713","missing":"\u2717","suggest":"\U0001f4a1"}
    s = styles.get(t, styles["found"])
    i = icons.get(t,"")
    return (f'<span style="{s};display:inline-flex;align-items:center;gap:4px;border-radius:20px;' +
            f'padding:3px 11px;margin:3px;font-size:.78rem;font-weight:600;line-height:1.4">{i} {text}</span>')

def card(html, p="26px"):
    return (f'<div style="background:white;border-radius:18px;padding:{p};' +
            f'border:1px solid #E8EDF2;box-shadow:0 2px 8px rgba(0,0,0,.05);margin-bottom:16px">{html}</div>')

def page_hdr(title, sub=""):
    s = f'<p style="color:#94A3B8;font-size:.9rem;margin:4px 0 0;font-weight:400">{sub}</p>' if sub else ""
    return st.markdown(
        f'<div style="margin-bottom:28px;padding-bottom:20px;border-bottom:1px solid #E8EDF2">' +
        f'<h1 style="font-size:1.65rem;font-weight:800;color:#0F172A;margin:0;letter-spacing:-.02em">{title}</h1>{s}</div>',
        unsafe_allow_html=True)

def show(html): st.markdown(html, unsafe_allow_html=True)

# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('''<div style="padding:8px 4px 16px">
      <div style="font-size:1.2rem;font-weight:800;color:white;letter-spacing:-.02em">
        <span style="color:#F59E0B">Amazon</span> Analyser
      </div>
      <div style="font-size:.75rem;color:#475569;margin-top:4px">Content &amp; SEO Dashboard</div>
    </div>''', unsafe_allow_html=True)
    st.markdown("---")
    page = st.radio("nav", [
        "\U0001f3e0  Dashboard",
        "\U0001f50d  New Analysis",
        "\U0001f3f7  Product Lines",
        "\u2699\ufe0f  Scoring Rules",
        "\U0001f4dc  History",
    ], label_visibility="collapsed")
    st.markdown("---")
    st.markdown('<p style="font-size:.72rem;color:#334155!important;padding:0 4px">Amazon.co.uk \u00b7 UK Marketplace</p>', unsafe_allow_html=True)

# ─── DASHBOARD ────────────────────────────────────────────────────────────────
if page == "\U0001f3e0  Dashboard":
    page_hdr("Dashboard", "Overview of your Amazon listing health")
    conn = db()
    rows = conn.execute("SELECT * FROM results ORDER BY created_at DESC LIMIT 200").fetchall()
    conn.close()
    total_a = len(rows)
    avg_s = round(sum(r["total_score"] or 0 for r in rows) / max(total_a,1), 1)
    poor = sum(1 for r in rows if (r["total_score"] or 0) < 65)
    c1,c2,c3 = st.columns(3)
    c1.metric("Analyses Run", total_a)
    c2.metric("Average Score", f"{avg_s} / 100")
    c3.metric("Need Attention", poor)
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
    show('<h2 style="font-size:1.1rem;font-weight:700;color:#0F172A;margin-bottom:14px">Recent Analyses</h2>')
    if not rows:
        show(card('<div style="text-align:center;padding:40px 20px;color:#94A3B8"><div style="font-size:2.5rem;margin-bottom:12px">\U0001f4e6</div><p style="font-size:1rem;font-weight:600;color:#64748B;margin:0">No analyses yet</p><p style="font-size:.85rem;margin:6px 0 0">Go to <b>New Analysis</b> to get started</p></div>'))
    else:
        tbl = '<div style="background:white;border-radius:18px;border:1px solid #E8EDF2;box-shadow:0 2px 8px rgba(0,0,0,.05);overflow:hidden">' + '<table style="width:100%;border-collapse:collapse;font-size:.85rem">' + '<thead><tr style="background:#F8FAFC;border-bottom:1px solid #E8EDF2">' + "".join(f'<th style="padding:12px 16px;text-align:left;font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#94A3B8;white-space:nowrap">{h}</th>' for h in ["ASIN","Product","Score","Title","Bullets","A+","Keywords","Date"]) + '</tr></thead><tbody>'
        for r in rows[:12]:
            s = r["total_score"]
            c_dot, bg, tc, lbl = _score_meta(s)
            score_cell = f'<span style="background:{bg};color:{tc};padding:3px 10px;border-radius:20px;font-size:.75rem;font-weight:700">{s:.0f} — {lbl}</span>' if s is not None else '<span style="color:#94A3B8">Error</span>'
            aplus_cell = '<span style="color:#10B981;font-weight:600">Yes</span>' if r["has_aplus"] else '<span style="color:#EF4444;font-weight:600">No</span>'
            tbl += (f'<tr style="border-bottom:1px solid #F1F5F9;transition:background .1s" onmouseover="this.style.background='#FAFBFF'" onmouseout="this.style.background=''">' +
                    f'<td style="padding:12px 16px"><code style="background:#EEF2FF;color:#4F46E5;border-radius:6px;padding:2px 8px;font-size:.8rem">{r["asin"]}</code></td>' +
                    f'<td style="padding:12px 16px;color:#374151;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{(r["product_name"] or "—")[:40]}</td>' +
                    f'<td style="padding:12px 16px">{score_cell}</td>' +
                    f'<td style="padding:12px 16px;color:#64748B">{r["title_score"]:.0f if r["title_score"] else "—"}</td>' +
                    f'<td style="padding:12px 16px;color:#64748B">{r["bullets_score"]:.0f if r["bullets_score"] else "—"}</td>' +
                    f'<td style="padding:12px 16px">{aplus_cell}</td>' +
                    f'<td style="padding:12px 16px;color:#64748B">{r["keywords_score"]:.0f if r["keywords_score"] else "—"}</td>' +
                    f'<td style="padding:12px 16px;color:#94A3B8;font-size:.8rem">{str(r["created_at"] or "")[:10]}</td></tr>')
        tbl += '</tbody></table></div>'
        show(tbl)

# ─── NEW ANALYSIS ─────────────────────────────────────────────────────────────
elif page == "\U0001f50d  New Analysis":
    page_hdr("New Analysis", "Scrape and score Amazon.co.uk listings instantly")
    conn = db()
    lines = conn.execute("SELECT * FROM product_lines ORDER BY name").fetchall()
    rules = conn.execute("SELECT * FROM scoring_rules ORDER BY is_default DESC, name").fetchall()
    conn.close()
    if not lines:
        show(card('<div style="text-align:center;padding:32px;color:#64748B"><div style="font-size:2rem;margin-bottom:10px">\U0001f3f7\ufe0f</div><p style="font-weight:600;margin:0">No product lines yet</p><p style="font-size:.85rem;margin:6px 0 0">Create one in <b>Product Lines</b> first, then come back here.</p></div>'))
        st.stop()
    col_l, col_r = st.columns([1, 1], gap="large")
    with col_l:
        show('<p style="font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#94A3B8;margin-bottom:8px">ASINs to Analyse</p>')
        asins_raw = st.text_area("", placeholder="One ASIN per line\nB08N5WRWNW\nB09XYZ1234", height=130, label_visibility="collapsed")
    with col_r:
        show('<p style="font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#94A3B8;margin-bottom:8px">Product Line</p>')
        line_names = [f"{l['name']} ({len(json.loads(l['keywords']))} kws)" for l in lines]
        sel_line = st.selectbox("", line_names, label_visibility="collapsed")
        show('<p style="font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#94A3B8;margin:14px 0 8px">Scoring Rule</p>')
        rule_names = [f"{r['name']}{'  (Default)' if r['is_default'] else ''}" for r in rules]
        sel_rule = st.selectbox(" ", rule_names, label_visibility="collapsed")
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    run = st.button("\u25b6\ufe0f  Run Analysis", type="primary", use_container_width=True)
    if run:
        asins = [a.strip().upper() for a in asins_raw.strip().splitlines() if a.strip()]
        if not asins:
            st.error("Please enter at least one ASIN.")
            st.stop()
        line_obj = lines[line_names.index(sel_line)]
        rule_obj = rules[rule_names.index(sel_rule)]
        keywords = json.loads(line_obj["keywords"])
        rule_dict = dict(rule_obj)
        bar = st.progress(0, text="Preparing...")
        for idx, asin in enumerate(asins):
            bar.progress((idx)/max(len(asins),1), text=f"Scraping {asin}... ({idx+1}/{len(asins)})")
            conn = db()
            try:
                scraped = scrape(asin)
                result = analyse(scraped, keywords, rule_dict)
                pname = scraped.get("brand") or (scraped.get("title") or "")[:60] or asin
                conn.execute("""INSERT INTO results (asin,product_line_id,scoring_rule_id,product_name,product_image,title,bullets,has_aplus,description,total_score,title_score,bullets_score,aplus_score,keywords_score,title_issues,bullets_issues,aplus_issues,keywords_issues,found_keywords,missing_keywords,suggested_keywords) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (asin,line_obj["id"],rule_obj["id"],pname,scraped.get("image_url"),scraped.get("title"),json.dumps(scraped.get("bullets",[])),1 if scraped.get("has_aplus") else 0,scraped.get("description"),result["total_score"],result["title_score"],result["bullets_score"],result["aplus_score"],result["keywords_score"],json.dumps(result["title_issues"]),json.dumps(result["bullets_issues"]),json.dumps(result["aplus_issues"]),json.dumps(result["keywords_issues"]),json.dumps(result["found_keywords"]),json.dumps(result["missing_keywords"]),json.dumps(result["suggested_keywords"])))
                conn.commit()
                # Build result card HTML
                mw = rule_dict; s = result["total_score"]
                bars = (score_bar("Title",          result["title_score"],    mw["title_weight"],    "\U0001f4dd") +
                        score_bar("Bullet Points",  result["bullets_score"],  mw["bullets_weight"],  "\U0001f539") +
                        score_bar("A+ Content",     result["aplus_score"],    mw["aplus_weight"],    "\u2728")    +
                        score_bar("Keywords SEO",   result["keywords_score"], mw["keywords_weight"], "\U0001f511"))
                all_issues = result["title_issues"]+result["bullets_issues"]+result["aplus_issues"]+result["keywords_issues"]
                issues_html = "".join(issue_box(i) for i in all_issues) if all_issues else ok_box("All categories")
                kw_html = ""
                if result["found_keywords"] or result["missing_keywords"]:
                    kw_html += '<div style="margin-top:18px;border-top:1px solid #F1F5F9;padding-top:16px">' + '<p style="font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#94A3B8;margin:0 0 10px">Keywords Coverage</p>' + "".join(kw_pill(k,"found") for k in result["found_keywords"]) + "".join(kw_pill(k,"missing") for k in result["missing_keywords"]) + '<p style="font-size:.72rem;color:#94A3B8;margin:8px 0 0">&nbsp;&#10003; found in listing &nbsp;&middot;&nbsp; &#10007; missing from listing</p></div>'
                if result["suggested_keywords"]:
                    kw_html += '<div style="margin-top:14px"><p style="font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#94A3B8;margin:0 0 10px">Suggested Keywords</p>' + "".join(kw_pill(k,"suggest") for k in result["suggested_keywords"]) + '</div>'
                img_h = f'<img src="{scraped.get("image_url")}" style="width:72px;height:72px;object-fit:contain;border-radius:10px;border:1px solid #F1F5F9;margin-bottom:10px">' if scraped.get("image_url") else ""
                title_p = (scraped.get("title") or "")[:120]
                asin_tag = f'<code style="background:#EEF2FF;color:#4F46E5;padding:4px 12px;border-radius:8px;font-size:.85rem;font-weight:700;letter-spacing:.05em;font-family:monospace">{asin}</code>'
                link = f'<a href="https://www.amazon.co.uk/dp/{asin}" target="_blank" style="font-size:.78rem;color:#94A3B8;text-decoration:none;margin-left:8px">\U0001f517 View on Amazon</a>'
                c_, bg_, tc_, lbl_ = _score_meta(s)
                lbl_badge = f'<span style="background:{bg_};color:{tc_};padding:3px 12px;border-radius:20px;font-size:.75rem;font-weight:700">{lbl_}</span>'
                header = f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:20px;margin-bottom:22px;flex-wrap:wrap"><div style="flex:1;min-width:200px">{img_h}<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">{asin_tag}{lbl_badge}{link}</div><p style="color:#374151;font-size:.9rem;margin:0;line-height:1.5">{title_p}</p></div>{score_gauge(s)}</div>'
                result_html = f'<div style="background:white;border-radius:20px;padding:28px;border:1px solid #E8EDF2;box-shadow:0 4px 16px rgba(0,0,0,.06);margin:20px 0">{header}<div style="border-top:1px solid #F1F5F9;padding-top:20px">{bars}</div><div style="margin-top:16px">{issues_html}</div>{kw_html}</div>'
                show(result_html)
            except Exception as e:
                conn.execute("INSERT INTO results (asin,product_line_id,scoring_rule_id,scrape_error,total_score) VALUES (?,?,?,?,0)", (asin,line_obj["id"],rule_obj["id"],str(e)))
                conn.commit()
                st.error(f"**{asin}** — {e}")
            finally:
                conn.close()
        bar.progress(1.0, text="Done!")

# ─── PRODUCT LINES ────────────────────────────────────────────────────────────
elif page == "\U0001f3f7  Product Lines":
    page_hdr("Product Lines", "Group your products and assign keyword lists to each one")
    conn = db()
    lines = conn.execute("SELECT * FROM product_lines ORDER BY name").fetchall()
    with st.expander("\u2795  Create New Product Line", expanded=len(lines)==0):
        show('<div style="height:4px"></div>')
        c1,c2 = st.columns([1,1], gap="large")
        with c1:
            new_name = st.text_input("Product line name", placeholder="e.g. Coffee Machines")
        with c2:
            show('<p style="font-size:.78rem;color:#94A3B8;margin:0 0 4px;font-weight:600">FORMAT: one keyword per line, or comma-separated</p>')
        new_kws = st.text_area("Keywords", placeholder="coffee machine\nespresso maker\nbarista\nautomatic coffee\ncapsule machine", height=170, label_visibility="visible")
        kc = len([k.strip() for k in re.split(r'[,\n]+', new_kws) if k.strip()])
        col_i, col_b = st.columns([3,1])
        col_i.caption(f"{kc} keyword{'s' if kc!=1 else ''} detected")
        if col_b.button("Create", type="primary", key="create_pl"):
            if not new_name.strip():
                st.error("Please enter a product line name.")
            else:
                kws = [k.strip() for k in re.split(r'[,\n]+', new_kws) if k.strip()]
                try:
                    conn.execute("INSERT INTO product_lines (name,keywords) VALUES (?,?)", (new_name.strip(), json.dumps(kws)))
                    conn.commit(); st.success(f"\u2705 \'{new_name.strip()}\' created with {len(kws)} keywords!"); st.rerun()
                except Exception as e:
                    st.error(str(e))
    show('<div style="height:8px"></div>')
    if not lines:
        show(card('<div style="text-align:center;padding:32px;color:#94A3B8"><div style="font-size:2rem;margin-bottom:10px">\U0001f3f7\ufe0f</div><p style="font-weight:600;margin:0;color:#64748B">No product lines yet</p></div>'))
    for line in lines:
        kws = json.loads(line["keywords"])
        badges = "".join(kw_pill(k,"suggest") for k in kws[:20]) + (f' <span style="color:#94A3B8;font-size:.78rem">+{len(kws)-20} more</span>' if len(kws)>20 else "")
        with st.expander(f"{line['name']}  ·  {len(kws)} keywords"):
            show('<div style="margin-bottom:12px">' + badges + '</div>')
            c1,c2 = st.columns([1,1], gap="large")
            with c1:
                en = st.text_input("Name", value=line["name"], key=f"ln_{line['id']}")
            with c2:
                ek = st.text_area("Keywords (one per line)", value="\n".join(kws), height=160, key=f"lk_{line['id']}")
            ca, cb = st.columns([1,4])
            if ca.button("Save", key=f"ls_{line['id']}"):
                nk = [k.strip() for k in ek.strip().splitlines() if k.strip()]
                conn.execute("UPDATE product_lines SET name=?,keywords=? WHERE id=?", (en.strip(), json.dumps(nk), line["id"]))
                conn.commit(); st.success("Saved!"); st.rerun()
            if cb.button("Delete this product line", key=f"ld_{line['id']}"):
                conn.execute("DELETE FROM product_lines WHERE id=?", (line["id"],))
                conn.commit(); st.rerun()
    conn.close()

# ─── SCORING RULES ────────────────────────────────────────────────────────────
elif page == "\u2699\ufe0f  Scoring Rules":
    page_hdr("Scoring Rules", "Define how each content category is scored and what thresholds to apply")
    conn = db()
    rules = conn.execute("SELECT * FROM scoring_rules ORDER BY is_default DESC, name").fetchall()
    with st.expander("\u2795  Create New Scoring Rule"):
        show('<div style="height:4px"></div>')
        rname = st.text_input("Rule name", placeholder="e.g. Strict SEO")
        show('<div style="background:#F8FAFC;border-radius:12px;padding:16px;margin:12px 0"><p style="font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#94A3B8;margin:0 0 12px">Category Weights — must sum to 100</p>')
        rc1,rc2,rc3,rc4 = st.columns(4)
        tw=rc1.number_input("Title %",0,100,25,key="ntw"); bw=rc2.number_input("Bullets %",0,100,25,key="nbw")
        aw=rc3.number_input("A+ Content %",0,100,25,key="naw"); kw_=rc4.number_input("Keywords %",0,100,25,key="nkw")
        total_w = tw+bw+aw+kw_
        tw_color = "#10B981" if total_w==100 else "#EF4444"
        show(f'</div><p style="font-size:.85rem;font-weight:600;color:{tw_color};margin:0 0 16px">Total: {total_w}/100 {"\u2705" if total_w==100 else "\u26a0\ufe0f Must equal exactly 100"}</p>')
        col1, col2 = st.columns(2, gap="large")
        with col1:
            show('<p style="font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#94A3B8;margin:0 0 10px">Title Rules</p>')
            tc1,tc2 = st.columns(2)
            tmin=tc1.number_input("Min chars",1,500,80,key="ntmin"); tmax=tc2.number_input("Max chars",1,500,200,key="ntmax")
            tkif=st.checkbox("Primary keyword must appear in first 80 chars",True,key="ntkif")
        with col2:
            show('<p style="font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#94A3B8;margin:0 0 10px">Bullet Point Rules</p>')
            bc1,bc2,bc3=st.columns(3)
            bmc=bc1.number_input("Min count",1,20,5,key="nbmc"); bml=bc2.number_input("Min chars",1,500,100,key="nbml"); bmx=bc3.number_input("Max chars",1,1000,255,key="nbmx")
            show('<p style="font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#94A3B8;margin:12px 0 8px">Keyword Rules</p>')
            kmc=st.slider("Min coverage %",0,100,70,key="nkmc")
            kit=st.checkbox("Top 3 keywords must appear in title",True,key="nkit")
        if st.button("Create Rule", type="primary", disabled=(total_w!=100), key="create_rule"):
            if not rname.strip(): st.error("Enter a rule name.")
            else:
                try:
                    conn.execute("INSERT INTO scoring_rules (name,title_weight,bullets_weight,aplus_weight,keywords_weight,title_min_length,title_max_length,title_keyword_in_first,bullets_min_count,bullets_min_length,bullets_max_length,keywords_min_coverage,keywords_in_title) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                 (rname.strip(),tw,bw,aw,kw_,tmin,tmax,int(tkif),bmc,bml,bmx,kmc,int(kit)))
                    conn.commit(); st.success("\u2705 Rule created!"); st.rerun()
                except Exception as e: st.error(str(e))
    show('<div style="height:8px"></div>')
    for rule in rules:
        tag = '<span style="background:#EEF2FF;color:#4F46E5;padding:2px 10px;border-radius:20px;font-size:.72rem;font-weight:700;margin-left:8px">Default</span>' if rule["is_default"] else ""
        with st.expander(f"{rule['name']}"):
            show(f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">' +
                 f'<div style="background:#F8FAFC;border-radius:10px;padding:12px"><p style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#94A3B8;margin:0 0 8px">Weights</p><p style="margin:0;font-size:.85rem;color:#374151">Title <b>{rule["title_weight"]}%</b> &nbsp;·&nbsp; Bullets <b>{rule["bullets_weight"]}%</b> &nbsp;·&nbsp; A+ <b>{rule["aplus_weight"]}%</b> &nbsp;·&nbsp; Keywords <b>{rule["keywords_weight"]}%</b></p></div>' +
                 f'<div style="background:#F8FAFC;border-radius:10px;padding:12px"><p style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#94A3B8;margin:0 0 8px">Thresholds</p><p style="margin:0;font-size:.85rem;color:#374151">Title <b>{rule["title_min_length"]}–{rule["title_max_length"]}</b> chars &nbsp;·&nbsp; Bullets min <b>{rule["bullets_min_count"]}</b> &nbsp;·&nbsp; KW coverage <b>\u2265{rule["keywords_min_coverage"]:.0f}%</b></p></div>' +
                 f'</div>')
            if not rule["is_default"]:
                if st.button("Delete this rule", key=f"rd_{rule['id']}"):
                    conn.execute("DELETE FROM scoring_rules WHERE id=?", (rule["id"],)); conn.commit(); st.rerun()
    conn.close()

# ─── HISTORY ──────────────────────────────────────────────────────────────────
elif page == "\U0001f4dc  History":
    page_hdr("Analysis History", "All past analyses — click any row to expand full details")
    conn = db()
    rows = conn.execute("SELECT * FROM results ORDER BY created_at DESC").fetchall()
    conn.close()
    if not rows:
        show(card('<div style="text-align:center;padding:40px;color:#94A3B8"><div style="font-size:2.5rem;margin-bottom:12px">\U0001f4dc</div><p style="font-size:1rem;font-weight:600;color:#64748B;margin:0">No history yet</p><p style="font-size:.85rem;margin:6px 0 0">Run your first analysis to see results here.</p></div>'))
    else:
        for r in rows:
            s = r["total_score"]
            c_, bg_, tc_, lbl_ = _score_meta(s)
            lbl_badge = f'<span style="background:{bg_};color:{tc_};padding:2px 9px;border-radius:20px;font-size:.72rem;font-weight:700">{lbl_}</span>' if s is not None else '<span style="color:#EF4444;font-size:.72rem">Error</span>'
            exp_label = f"[{str(r['created_at'] or '')[:10]}]  {r['asin']}  ·  {(r['product_name'] or '—')[:40]}  ·  {f'{s:.0f}/100' if s is not None else 'Error'}"
            with st.expander(exp_label):
                if r["scrape_error"]:
                    st.error(f"Scraping failed: {r['scrape_error']}"); continue
                h_col1, h_col2 = st.columns([4,1])
                with h_col2:
                    if r["product_image"]: st.image(r["product_image"], width=100)
                    show(score_gauge(s, 100))
                with h_col1:
                    show(f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px"><code style="background:#EEF2FF;color:#4F46E5;border-radius:8px;padding:4px 12px;font-size:.85rem;font-weight:700">{r["asin"]}</code>{lbl_badge}<a href="https://www.amazon.co.uk/dp/{r["asin"]}" target="_blank" style="font-size:.78rem;color:#94A3B8;text-decoration:none">\U0001f517 View on Amazon</a></div>')
                    if r["title"]:
                        show(f'<p style="color:#1E293B;font-size:.9rem;line-height:1.6;margin:0 0 6px">{r["title"]}</p>')
                        show(f'<p style="color:#94A3B8;font-size:.75rem;margin:0">Title: {len(r["title"])} characters &nbsp;·&nbsp; A+ Content: {"\u2705 Yes" if r["has_aplus"] else "\u274c No"}</p>')
                rw = {"title_weight":25,"bullets_weight":25,"aplus_weight":25,"keywords_weight":25}
                bars = (score_bar("Title",         r["title_score"] or 0,    rw["title_weight"],    "\U0001f4dd") +
                        score_bar("Bullet Points", r["bullets_score"] or 0,  rw["bullets_weight"],  "\U0001f539") +
                        score_bar("A+ Content",    r["aplus_score"] or 0,    rw["aplus_weight"],    "\u2728")    +
                        score_bar("Keywords SEO",  r["keywords_score"] or 0, rw["keywords_weight"], "\U0001f511"))
                show('<div style="margin:16px 0">' + bars + '</div>')
                ti=json.loads(r["title_issues"] or "[]"); bi=json.loads(r["bullets_issues"] or "[]")
                ai=json.loads(r["aplus_issues"] or "[]"); ki=json.loads(r["keywords_issues"] or "[]")
                all_i = ti+bi+ai+ki
                if all_i:
                    show("".join(issue_box(i) for i in all_i))
                found=json.loads(r["found_keywords"] or "[]"); missing=json.loads(r["missing_keywords"] or "[]"); suggest=json.loads(r["suggested_keywords"] or "[]")
                if found or missing:
                    show('<div style="margin-top:16px;border-top:1px solid #F1F5F9;padding-top:14px"><p style="font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#94A3B8;margin:0 0 8px">Keywords</p>' + "".join(kw_pill(k,"found") for k in found) + "".join(kw_pill(k,"missing") for k in missing) + '</div>')
                if suggest:
                    show('<div style="margin-top:12px"><p style="font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#94A3B8;margin:0 0 8px">Suggested</p>' + "".join(kw_pill(k,"suggest") for k in suggest) + '</div>')
                if r["bullets"]:
                    bl = json.loads(r["bullets"])
                    with st.expander(f"View {len(bl)} bullet points"):
                        for i,b in enumerate(bl):
                            show(f'<div style="display:flex;gap:12px;padding:8px 0;border-bottom:1px solid #F8FAFC;font-size:.85rem"><span style="background:#EEF2FF;color:#4F46E5;border-radius:6px;padding:2px 8px;font-weight:700;flex-shrink:0">{i+1}</span><span style="color:#374151;line-height:1.5">{b}</span><span style="color:#94A3B8;flex-shrink:0;font-size:.75rem">{len(b)} ch</span></div>')
                conn2 = db()
                if st.button("Delete this result", key=f"del_{r['id']}"):
                    conn2.execute("DELETE FROM results WHERE id=?", (r["id"],)); conn2.commit(); st.rerun()
                conn2.close()

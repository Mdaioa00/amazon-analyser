import streamlit as st
import sqlite3, httpx, json, re, random
from bs4 import BeautifulSoup
from io import BytesIO
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

st.set_page_config(page_title="Amazon Content Analyser", page_icon="\U0001f6d2", layout="wide")

# ── THEME ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
html,body,[class*="css"]{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif!important}
#MainMenu,footer,header{visibility:hidden}
.stDeployButton{display:none!important}
.stApp{background:#F5F3EE!important}
.main .block-container{max-width:1060px;padding:3rem 2.5rem 6rem}
[data-testid="stSidebar"]{background:#FAFAF7!important;border-right:1px solid #E9E7E0!important;box-shadow:none!important}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] div,[data-testid="stSidebar"] span{color:#6B6963!important}
[data-testid="stSidebar"] .stRadio label{font-size:.875rem!important;font-weight:500!important;color:#3D3B35!important;padding:9px 12px!important;border-radius:9px!important;display:block!important;transition:all .15s!important;cursor:pointer!important;margin:1px 0!important}
[data-testid="stSidebar"] .stRadio label:hover{background:#EDECEA!important;color:#1C1B18!important}
[data-testid="stSidebar"] hr{border-color:#E9E7E0!important}
[data-testid="metric-container"]{background:#FFFFFF!important;border:1px solid #E9E7E0!important;border-radius:18px!important;padding:24px 28px!important;box-shadow:none!important}
[data-testid="metric-container"] label{font-size:.72rem!important;font-weight:700!important;text-transform:uppercase!important;letter-spacing:.07em!important;color:#9B9793!important}
[data-testid="metric-container"] [data-testid="stMetricValue"]{font-size:2.4rem!important;font-weight:800!important;color:#1C1B18!important;letter-spacing:-.04em!important}
.stButton>button{font-family:'Inter',sans-serif!important;font-weight:600!important;font-size:.855rem!important;border-radius:10px!important;padding:.48rem 1.2rem!important;border:1.5px solid #E9E7E0!important;background:#FFFFFF!important;color:#3D3B35!important;transition:all .15s!important;box-shadow:none!important}
.stButton>button:hover{border-color:#1C1B18!important;color:#1C1B18!important;background:#FAFAF7!important}
.stButton>button[kind="primary"]{background:#1C1B18!important;color:#FFFFFF!important;border:none!important}
.stButton>button[kind="primary"]:hover{background:#3D3B35!important;color:#FFFFFF!important;border:none!important}
[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input{border-radius:9px!important;border:1.5px solid #E9E7E0!important;background:#FFFFFF!important;font-size:.875rem!important;color:#1C1B18!important;padding:.52rem .9rem!important;transition:all .2s!important}
[data-testid="stTextInput"] input:focus,[data-testid="stNumberInput"] input:focus{border-color:#1C1B18!important;box-shadow:0 0 0 3px rgba(28,27,24,.07)!important}
[data-testid="stTextArea"] textarea{border-radius:11px!important;border:1.5px solid #E9E7E0!important;background:#FFFFFF!important;font-size:.875rem!important;color:#1C1B18!important;line-height:1.65!important}
[data-testid="stTextArea"] textarea:focus{border-color:#1C1B18!important;box-shadow:0 0 0 3px rgba(28,27,24,.07)!important}
[data-testid="stSelectbox"]>div>div{border-radius:9px!important;border:1.5px solid #E9E7E0!important;background:#FFFFFF!important}
[data-testid="stExpander"]{background:#FFFFFF!important;border:1px solid #E9E7E0!important;border-radius:16px!important;margin-bottom:10px!important;box-shadow:none!important;overflow:hidden!important}
[data-testid="stExpander"] summary{font-weight:600!important;font-size:.88rem!important;color:#1C1B18!important;padding:16px 20px!important;background:#FFFFFF!important;letter-spacing:-.01em!important}
[data-testid="stExpander"] summary:hover{background:#FAFAF7!important}
[data-testid="stExpander"]>div:last-child{padding:4px 20px 20px!important}
[data-testid="stCheckbox"] label{font-size:.875rem!important;color:#3D3B35!important}
[data-testid="stAlert"]{border-radius:12px!important;border:none!important;font-size:.855rem!important}
hr{border:none!important;border-top:1px solid #E9E7E0!important;margin:1.5rem 0!important}
code{background:#F0EEE8!important;color:#3D3B35!important;border-radius:6px!important;padding:2px 8px!important;font-size:.82rem!important;font-family:'Inter',monospace!important}
p,li{color:#3D3B35!important;line-height:1.65!important}
</style>
""", unsafe_allow_html=True)

# ── DATABASE ───────────────────────────────────────────────────────────────────
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

# ── SCRAPER ────────────────────────────────────────────────────────────────────
UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

def scrape(asin):
    url = "https://www.amazon.co.uk/dp/" + asin
    headers = {"User-Agent": random.choice(UA), "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
               "Accept-Language": "en-GB,en;q=0.9", "Accept-Encoding": "gzip, deflate, br",
               "Connection": "keep-alive", "Upgrade-Insecure-Requests": "1"}
    with httpx.Client(follow_redirects=True, timeout=30.0) as client:
        r = client.get(url, headers=headers)
    if r.status_code == 503:
        raise Exception("Amazon returned 503 — rate limited. Wait a few minutes and try again.")
    if r.status_code != 200:
        raise Exception("HTTP " + str(r.status_code) + " for ASIN " + asin)
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

# ── ANALYSER ───────────────────────────────────────────────────────────────────
def kw_split(content, keywords):
    cl = content.lower()
    return [k for k in keywords if k.lower() in cl], [k for k in keywords if k.lower() not in cl]

def analyse(scraped, keywords, rule):
    title   = scraped.get("title") or ""
    bullets = scraped.get("bullets") or []
    has_aplus = scraped.get("has_aplus", False)
    desc    = scraped.get("description") or ""
    mw = rule["title_weight"]; ti, ts = [], 0
    if not title:
        ti = ["Title could not be retrieved from Amazon."]
    else:
        ln = len(title)
        if ln < rule["title_min_length"]:
            ti.append("Title too short (" + str(ln) + " chars). Target: " + str(rule["title_min_length"]) + "\u2013" + str(rule["title_max_length"]) + " chars.")
            ts += mw * 0.4 * (ln / rule["title_min_length"])
        elif ln > rule["title_max_length"]:
            ti.append("Title too long (" + str(ln) + " chars) \u2014 Amazon may truncate it.")
            ts += mw * 0.30
        else:
            ts += mw * 0.40
        found_t, _ = kw_split(title, keywords)
        kr = len(found_t) / len(keywords) if keywords else 1.0
        ts += mw * 0.40 * kr
        if kr < 0.3: ti.append("Only " + str(len(found_t)) + "/" + str(len(keywords)) + " keywords in title \u2014 move top keywords near the start.")
        elif kr < 0.6: ti.append(str(len(found_t)) + "/" + str(len(keywords)) + " keywords in title \u2014 room to improve.")
        if rule.get("title_keyword_in_first") and keywords:
            if not any(k.lower() in title[:80].lower() for k in keywords[:3]):
                ti.append("Primary keyword not in first 80 characters of the title.")
            else:
                ts += mw * 0.20
        if sum(1 for w in title.split() if w.isupper() and len(w) > 2) > 3:
            ti.append("Too many ALL-CAPS words \u2014 use Title Case for better readability.")
    mw2 = rule["bullets_weight"]; bi, bs = [], 0
    if not bullets:
        bi = ["No bullet points found on the product page."]
    else:
        cnt = len(bullets)
        if cnt < rule["bullets_min_count"]:
            bi.append("Only " + str(cnt) + " bullet(s). Recommended: " + str(rule["bullets_min_count"]) + ".")
            bs += mw2 * 0.30 * (cnt / rule["bullets_min_count"])
        else:
            bs += mw2 * 0.30
        short = [i+1 for i,b in enumerate(bullets) if len(b) < rule["bullets_min_length"]]
        long_ = [i+1 for i,b in enumerate(bullets) if len(b) > rule["bullets_max_length"]]
        if short: bi.append("Bullet(s) " + str(short) + " are too short (< " + str(rule["bullets_min_length"]) + " chars).")
        if long_: bi.append("Bullet(s) " + str(long_) + " exceed " + str(rule["bullets_max_length"]) + " chars \u2014 may be truncated.")
        ok = (cnt - len(short) - len(long_)) / cnt
        bs += mw2 * 0.30 * ok
        found_b, _ = kw_split(" ".join(bullets), keywords)
        kr2 = len(found_b) / len(keywords) if keywords else 1.0
        bs += mw2 * 0.40 * kr2
        if kr2 < 0.5: bi.append("Low keyword coverage in bullets (" + str(len(found_b)) + "/" + str(len(keywords)) + "). Add more target keywords.")
    a_s = rule["aplus_weight"] if has_aplus else 0
    ai = [] if has_aplus else ["No A+ Content detected. Adding A+ can boost conversion by 5\u201310%."]
    mw4 = rule["keywords_weight"]; ki, ks = [], 0
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
            ki.append("Keyword coverage " + str(round(cov)) + "% (target \u2265 " + str(round(thresh)) + "%). Missing: " + ", ".join(miss_k[:8]) + ("..." if len(miss_k) > 8 else "") + ".")
        if rule.get("keywords_in_title") and keywords:
            ft2, _ = kw_split(title, keywords[:3])
            if not ft2: ki.append("None of the top 3 keywords appear in the title \u2014 move them there for SEO impact.")
    tokens = re.findall(r"\b[a-zA-Z]{4,}\b", all_content.lower())
    stop = {"with","this","that","from","have","will","your","their","also","each","which","they","more","than","when","into","only","over","such","used","using","pack","item","product","brand","quality","great","make","made","features","feature","design","provides","include","perfect","ideal","easy","best","good","high","well","help","helps","allows","keep"}
    existing_l = {k.lower() for k in keywords}
    counts = {}
    for t in tokens:
        if t not in stop and t not in existing_l: counts[t] = counts.get(t, 0) + 1
    suggestions = sorted(counts, key=lambda x: -counts[x])[:15]
    total = round(min(ts,mw) + min(bs,mw2) + a_s + min(ks,mw4), 1)
    return {"total_score": total,
            "title_score": round(min(ts,mw),1), "bullets_score": round(min(bs,mw2),1),
            "aplus_score": round(a_s,1), "keywords_score": round(min(ks,mw4),1),
            "title_issues": ti, "bullets_issues": bi, "aplus_issues": ai, "keywords_issues": ki,
            "found_keywords": found_k, "missing_keywords": miss_k, "suggested_keywords": suggestions}

# ── KEYWORD GAP ANALYSIS ───────────────────────────────────────────────────────
def keyword_gaps(title, bullets_list, pl_keywords):
    t_lower = (title or "").lower()
    b_text  = " ".join(bullets_list or []).lower()
    title_missing   = [k for k in pl_keywords if k.lower() not in t_lower]
    bullets_missing = [k for k in pl_keywords if k.lower() not in b_text]
    return title_missing, bullets_missing

def suggest_rewrite(bullet, keyword):
    b = bullet.strip().rstrip(".")
    kw = keyword.strip()
    b_lower = b.lower()
    for fs in ["features", "includes", "equipped", "comes with", "designed"]:
        if b_lower.startswith(fs):
            return b + ", " + kw + "."
    for phrase in ["perfect for", "ideal for", "great for", "suitable for"]:
        if phrase in b_lower:
            idx = b_lower.index(phrase) + len(phrase)
            return b[:idx] + " " + kw + " and" + b[idx:] + "."
    if len(b) < 80:
        return kw.capitalize() + " \u2014 " + b + "."
    if "," in b and b.count(",") >= 2:
        parts = b.rsplit(",", 1)
        return parts[0] + ", " + kw + "," + parts[1] + "."
    if " and " in b_lower:
        idx = b_lower.rindex(" and ")
        return b[:idx] + ", " + kw + b[idx:] + "."
    return b + " \u2014 features " + kw + "."

def bullet_rewrite_suggestions(bullets_list, bullets_missing_kws):
    suggestions = []
    for kw in bullets_missing_kws:
        best_idx, best_score = 0, -1
        kw_words = set(kw.lower().split())
        for i, bul in enumerate(bullets_list):
            shared = len(kw_words & set(re.findall(r"\b\w+\b", bul.lower())))
            if shared > best_score:
                best_score, best_idx = shared, i
        if bullets_list:
            suggestions.append({
                "keyword": kw,
                "bullet_idx": best_idx,
                "original": bullets_list[best_idx],
                "suggested": suggest_rewrite(bullets_list[best_idx], kw)
            })
    return suggestions

# ── EXCEL EXPORT ───────────────────────────────────────────────────────────────
def build_excel(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Analysis Results"
    ws.freeze_panes = "A2"
    hdr_fill   = PatternFill("solid", fgColor="1C1B18")
    hdr_font   = Font(bold=True, color="FFFFFF", name="Calibri", size=10)
    alt_fill   = PatternFill("solid", fgColor="F5F3EE")
    score_font = Font(bold=True, name="Calibri", size=10)
    thin       = Border(bottom=Side(style="thin", color="E9E7E0"))
    headers    = ["ASIN","Product Name","Date","Score /100","Title","Bullets","A+","Keywords",
                  "Has A+","Title Missing KWs","Bullets Missing KWs","All Missing KWs","Issues"]
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=col, value=h)
        c.font = hdr_font; c.fill = hdr_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = thin
    for ri, r in enumerate(rows, 2):
        alt = ri % 2 == 0
        title_val   = r["title"] or ""
        bullets_val = r["bullets"] or "[]"
        blist       = json.loads(bullets_val) if bullets_val else []
        pl_kws      = json.loads(r["pl_keywords"] or "[]") if "pl_keywords" in r.keys() else []
        tm, bm      = keyword_gaps(title_val, blist, pl_kws) if pl_kws else ([], [])
        vals = [r["asin"], r["product_name"] or "\u2014", str(r["created_at"] or "")[:10],
                r["total_score"], r["title_score"], r["bullets_score"], r["aplus_score"], r["keywords_score"],
                "Yes" if r["has_aplus"] else "No",
                "; ".join(tm), "; ".join(bm),
                "; ".join(json.loads(r["missing_keywords"] or "[]")),
                "; ".join(json.loads(r["title_issues"] or "[]") + json.loads(r["bullets_issues"] or "[]") +
                           json.loads(r["aplus_issues"] or "[]") + json.loads(r["keywords_issues"] or "[]"))]
        for col, val in enumerate(vals, 1):
            c = ws.cell(row=ri, column=col, value=val)
            c.border = thin
            c.alignment = Alignment(vertical="top", wrap_text=(col >= 10))
            if alt: c.fill = alt_fill
            if col == 4 and val is not None:
                v = float(val)
                c.font = Font(bold=True, color=("16A34A" if v>=85 else "CA8A04" if v>=65 else "EA580C" if v>=40 else "DC2626"), name="Calibri", size=10)
            else:
                c.font = Font(name="Calibri", size=10)
    col_widths = [14,28,12,10,10,10,8,10,8,30,30,30,50]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 20
    out = BytesIO(); wb.save(out); out.seek(0)
    return out.getvalue()

# ── UI PRIMITIVES ──────────────────────────────────────────────────────────────
def _score_meta(s):
    if s is None: s = 0
    if s >= 85: return "#16A34A","#DCFCE7","#166534","Excellent"
    if s >= 65: return "#CA8A04","#FEF9C3","#92400E","Good"
    if s >= 40: return "#EA580C","#FFF1ED","#9A3412","Needs Work"
    return "#DC2626","#FEE2E2","#991B1B","Poor"

def _bar_c(pct):
    if pct >= 85: return "#16A34A"
    if pct >= 65: return "#CA8A04"
    if pct >= 40: return "#EA580C"
    return "#DC2626"

def show(html): st.markdown(html, unsafe_allow_html=True)

def score_gauge(s, size=108):
    if s is None: s = 0
    c, bg, tc, lbl = _score_meta(s)
    pct = max(0, min(100, s))
    rem = 100 - pct
    sz = str(size)
    return (
        '<div style="display:flex;flex-direction:column;align-items:center;gap:8px">'
        '<div style="position:relative;width:' + sz + 'px;height:' + sz + 'px">'
        '<svg viewBox="0 0 36 36" style="width:100%;height:100%;transform:rotate(-90deg)">'
        '<circle cx="18" cy="18" r="15.9155" fill="none" stroke="#F0EEE8" stroke-width="2.2"/>'
        '<circle cx="18" cy="18" r="15.9155" fill="none" stroke="' + c + '" stroke-width="2.2"'
        ' stroke-dasharray="' + str(round(pct,1)) + ' ' + str(round(rem,1)) + '" stroke-linecap="round"/>'
        '</svg>'
        '<div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center">'
        '<span style="font-size:1.5rem;font-weight:800;color:#1C1B18;line-height:1;letter-spacing:-.03em">' + str(int(s)) + '</span>'
        '<span style="font-size:.58rem;color:#9B9793;font-weight:600;letter-spacing:.04em;margin-top:1px">/ 100</span>'
        '</div></div>'
        '<span style="font-size:.72rem;font-weight:700;background:' + bg + ';color:' + tc + ';padding:3px 11px;border-radius:20px;letter-spacing:.02em">' + lbl + '</span>'
        '</div>'
    )

def score_bar(label, score, max_score, icon=""):
    pct  = (score / max_score * 100) if max_score else 0
    color = _bar_c(pct)
    return (
        '<div style="margin:13px 0">'
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'
        '<span style="font-size:.855rem;font-weight:600;color:#1C1B18">' + icon + ' ' + label + '</span>'
        '<div style="display:flex;align-items:center;gap:5px">'
        '<span style="font-size:.95rem;font-weight:800;color:' + color + ';letter-spacing:-.02em">' + str(round(score,1)) + '</span>'
        '<span style="font-size:.75rem;color:#C4C2BB;font-weight:500">/ ' + str(int(max_score)) + '</span>'
        '</div></div>'
        '<div style="background:#F0EEE8;border-radius:999px;height:8px;overflow:hidden">'
        '<div style="background:' + color + ';width:' + str(round(pct,1)) + '%;height:100%;border-radius:999px"></div>'
        '</div></div>'
    )

def issue_box(text):
    return (
        '<div style="display:flex;gap:10px;align-items:flex-start;background:#FFFBEB;'
        'border:1px solid #FDE68A;border-radius:10px;padding:10px 14px;margin:5px 0;'
        'font-size:.825rem;color:#78350F;line-height:1.55">'
        '<span style="flex-shrink:0;margin-top:1px">\u26a0\ufe0f</span>'
        '<span>' + text + '</span></div>'
    )

def ok_box(label):
    return (
        '<div style="display:flex;gap:8px;align-items:center;background:#F0FDF4;'
        'border:1px solid #BBF7D0;border-radius:10px;padding:9px 14px;margin:5px 0;'
        'font-size:.825rem;color:#166534;font-weight:500">'
        '\u2705 ' + label + ' \u2014 no issues found.</div>'
    )

def pill(text, t="found"):
    styles = {
        "found":   "background:#DCFCE7;color:#166534;border:1px solid #BBF7D0",
        "missing": "background:#FEE2E2;color:#991B1B;border:1px solid #FECACA",
        "suggest": "background:#F0EEE8;color:#3D3B35;border:1px solid #DDD9CF",
        "title_miss": "background:#FEF9C3;color:#92400E;border:1px solid #FDE68A",
        "bullet_miss": "background:#FFF1ED;color:#9A3412;border:1px solid #FED7AA",
    }
    icons = {"found":"\u2713","missing":"\u2717","suggest":"\u25B8","title_miss":"T","bullet_miss":"B"}
    s = styles.get(t, styles["found"]); i = icons.get(t, "")
    return ('<span style="' + s + ';display:inline-flex;align-items:center;gap:4px;border-radius:20px;'
            'padding:3px 10px;margin:3px;font-size:.775rem;font-weight:600;line-height:1.4">' + i + ' ' + text + '</span>')

def card(html, p="28px 32px"):
    return ('<div style="background:#FFFFFF;border-radius:20px;padding:' + p + ';'
            'border:1px solid #E9E7E0;margin-bottom:16px">' + html + '</div>')

def section_label(text):
    return '<p style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#9B9793;margin:0 0 10px">' + text + '</p>'

def copy_btn_html(text, uid):
    escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")
    return (
        '<button onclick="navigator.clipboard.writeText(\'' + escaped + '\');'
        'this.innerText=\'\u2713 Copied\';setTimeout(()=>this.innerText=\'Copy\',2000)" '
        'style="background:#F5F3EE;border:1px solid #E9E7E0;border-radius:8px;padding:5px 14px;'
        'font-size:.775rem;font-weight:600;color:#3D3B35;cursor:pointer;transition:all .15s;margin-top:6px">'
        'Copy</button>'
    )

def page_header(title, sub=""):
    s = ('<p style="color:#9B9793;font-size:.9rem;margin:4px 0 0;font-weight:400">' + sub + '</p>') if sub else ""
    show('<div style="margin-bottom:32px;padding-bottom:24px;border-bottom:1px solid #E9E7E0">'
         '<h1 style="font-size:1.7rem;font-weight:800;color:#1C1B18;margin:0;letter-spacing:-.03em">' + title + '</h1>' + s + '</div>')

def empty_state(icon, title, subtitle, cta=""):
    show(card('<div style="text-align:center;padding:48px 24px">'
              '<div style="font-size:2.8rem;margin-bottom:16px">' + icon + '</div>'
              '<p style="font-size:1.05rem;font-weight:700;color:#1C1B18;margin:0 0 8px">' + title + '</p>'
              '<p style="font-size:.875rem;color:#9B9793;margin:0 0 16px">' + subtitle + '</p>'
              + cta + '</div>'))

# ── RESULT CARD (shared between New Analysis and History) ─────────────────────
def render_result(r_asin, r_title, r_bullets_json, r_has_aplus, r_image,
                  r_total, r_title_s, r_bullets_s, r_aplus_s, r_kw_s,
                  r_title_issues, r_bullets_issues, r_aplus_issues, r_kw_issues,
                  r_found_kws, r_missing_kws, r_suggested_kws,
                  rule_weights, pl_keywords):
    s       = r_total or 0
    bullets = json.loads(r_bullets_json or "[]")
    t_miss, b_miss = keyword_gaps(r_title, bullets, pl_keywords)
    rewrites = bullet_rewrite_suggestions(bullets, b_miss) if bullets else []
    c_, bg_, tc_, lbl_ = _score_meta(s)
    img_html = ('<img src="' + (r_image or "") + '" style="width:68px;height:68px;object-fit:contain;'
                'border-radius:10px;border:1px solid #F0EEE8;margin-bottom:12px">') if r_image else ""
    bars = (score_bar("Title",        r_title_s,   rule_weights.get("title_weight",25),   "\U0001f4dd") +
            score_bar("Bullet Points",r_bullets_s, rule_weights.get("bullets_weight",25), "\U0001f539") +
            score_bar("A+ Content",   r_aplus_s,   rule_weights.get("aplus_weight",25),   "\u2728")    +
            score_bar("Keywords SEO", r_kw_s,      rule_weights.get("keywords_weight",25),"\U0001f511"))
    all_issues = r_title_issues + r_bullets_issues + r_aplus_issues + r_kw_issues
    issues_html = "".join(issue_box(i) for i in all_issues) if all_issues else ok_box("All sections")
    header = ('<div style="display:flex;justify-content:space-between;align-items:flex-start;'
              'gap:20px;margin-bottom:24px;flex-wrap:wrap">'
              '<div style="flex:1;min-width:220px">' + img_html +
              '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
              '<code style="background:#F0EEE8;color:#3D3B35;padding:4px 12px;border-radius:8px;'
              'font-size:.85rem;font-weight:700;letter-spacing:.04em">' + r_asin + '</code>'
              '<span style="background:' + bg_ + ';color:' + tc_ + ';padding:3px 12px;border-radius:20px;'
              'font-size:.75rem;font-weight:700;letter-spacing:.02em">' + lbl_ + '</span>'
              '<a href="https://www.amazon.co.uk/dp/' + r_asin + '" target="_blank" '
              'style="font-size:.775rem;color:#9B9793;text-decoration:none">\U0001f517 Amazon</a>'
              '</div>'
              '<p style="color:#3D3B35;font-size:.875rem;margin:0;line-height:1.6">' + (r_title or "\u2014")[:130] + '</p>'
              '</div>' + score_gauge(s) + '</div>')
    show('<div style="background:#FFFFFF;border-radius:22px;padding:30px 32px;'
         'border:1px solid #E9E7E0;margin:20px 0">'
         + header +
         '<div style="border-top:1px solid #F5F3EE;padding-top:20px">' + bars + '</div>'
         '<div style="margin-top:16px">' + issues_html + '</div>')
    # Per-section keyword gaps
    if pl_keywords:
        show(section_label("Keyword gaps by section"))
        cols_html = ('<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">'
                     '<div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:12px;padding:14px 16px">'
                     '<p style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;'
                     'color:#92400E;margin:0 0 8px">\U0001f4dd Missing from Title</p>')
        if t_miss:
            cols_html += "".join(pill(k,"title_miss") for k in t_miss)
        else:
            cols_html += '<span style="font-size:.8rem;color:#16A34A;font-weight:500">\u2713 All keywords present</span>'
        cols_html += ('</div>'
                      '<div style="background:#FFF1ED;border:1px solid #FED7AA;border-radius:12px;padding:14px 16px">'
                      '<p style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;'
                      'color:#9A3412;margin:0 0 8px">\U0001f539 Missing from Bullet Points</p>')
        if b_miss:
            cols_html += "".join(pill(k,"bullet_miss") for k in b_miss)
        else:
            cols_html += '<span style="font-size:.8rem;color:#16A34A;font-weight:500">\u2713 All keywords present</span>'
        cols_html += '</div></div>'
        show(cols_html)
    # Found keywords
    if r_found_kws or r_missing_kws:
        show(section_label("All keywords"))
        show("".join(pill(k,"found") for k in r_found_kws) + "".join(pill(k,"missing") for k in r_missing_kws)
             + '<p style="font-size:.72rem;color:#9B9793;margin:6px 0 0">\u2713 found &nbsp;·&nbsp; \u2717 missing from listing</p>')
    # Rewrite suggestions
    if rewrites:
        show('<div style="margin-top:20px;border-top:1px solid #F5F3EE;padding-top:18px">'
             + section_label("\U0001f4a1 How to add missing keywords to your bullet points"))
        for rw in rewrites:
            uid = r_asin + "_" + re.sub(r"\W","_", rw["keyword"])
            show('<div style="background:#FAFAF7;border:1px solid #E9E7E0;border-radius:14px;padding:16px 20px;margin-bottom:12px">'
                 '<p style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#9B9793;margin:0 0 10px">'
                 'Keyword: <span style="color:#3D3B35">' + rw["keyword"] + '</span>'
                 ' &nbsp;\u2192&nbsp; Suggested edit for Bullet ' + str(rw["bullet_idx"]+1) + '</p>'
                 '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">'
                 '<div><p style="font-size:.72rem;font-weight:600;color:#9B9793;margin:0 0 5px">ORIGINAL</p>'
                 '<p style="font-size:.84rem;color:#6B6963;line-height:1.55;margin:0;'
                 'font-style:italic;padding:10px 12px;background:#F5F3EE;border-radius:8px">' + rw["original"] + '</p></div>'
                 '<div><p style="font-size:.72rem;font-weight:600;color:#1C1B18;margin:0 0 5px">SUGGESTED REWRITE</p>'
                 '<p style="font-size:.84rem;color:#1C1B18;line-height:1.55;margin:0;'
                 'padding:10px 12px;background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px">' + rw["suggested"] + '</p>'
                 + copy_btn_html(rw["suggested"], uid) + '</div>'
                 '</div></div>')
        show('</div>')
    if r_suggested_kws:
        show('<div style="margin-top:14px">' + section_label("Suggested additional keywords (from page content)"))
        show("".join(pill(k,"suggest") for k in r_suggested_kws) + '</div>')
    show('</div>')  # close main card

# ── SIDEBAR ────────────────────────────────────────────────────────────────────
with st.sidebar:
    show('<div style="padding:4px 4px 20px">'
         '<div style="font-size:1.1rem;font-weight:800;color:#1C1B18;letter-spacing:-.02em">Amazon Analyser</div>'
         '<div style="font-size:.75rem;color:#9B9793;margin-top:3px">Content &amp; SEO</div></div>')
    st.markdown("---")
    page = st.radio("nav", [
        "\U0001f3e0  Dashboard",
        "\U0001f50d  New Analysis",
        "\U0001f4dc  History",
        "\U0001f3f7  Product Lines",
        "\u2699\ufe0f  Scoring Rules",
    ], label_visibility="collapsed")
    st.markdown("---")
    show('<div style="padding:0 4px">'
         + section_label("Score Legend")
         + '<div style="display:flex;flex-direction:column;gap:5px">'
         + "".join('<div style="display:flex;align-items:center;gap:8px;font-size:.8rem;color:#3D3B35">'
                   '<span style="width:10px;height:10px;border-radius:50%;background:' + c + ';flex-shrink:0"></span>'
                   + lbl + ' ' + rng + '</div>'
                   for c, lbl, rng in [
                       ("#16A34A","Excellent","\u226585"),
                       ("#CA8A04","Good","65\u201384"),
                       ("#EA580C","Needs Work","40\u201364"),
                       ("#DC2626","Poor","< 40"),
                   ])
         + '</div></div>')

# ── DASHBOARD ──────────────────────────────────────────────────────────────────
if page == "\U0001f3e0  Dashboard":
    page_header("Dashboard", "Overview of your Amazon listing health")
    conn = db()
    rows = conn.execute("SELECT * FROM results ORDER BY created_at DESC LIMIT 200").fetchall()
    plines = conn.execute("SELECT COUNT(*) FROM product_lines").fetchone()[0]
    conn.close()
    total_a = len(rows)
    avg_s   = round(sum(r["total_score"] or 0 for r in rows) / max(total_a,1), 1)
    poor    = sum(1 for r in rows if (r["total_score"] or 0) < 65)
    if total_a == 0:
        empty_state("\U0001f4e6","No analyses yet","Create a Product Line, then run your first analysis to see scores here.")
    else:
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Total Analyses", total_a)
        c2.metric("Average Score", str(avg_s) + " / 100")
        c3.metric("Need Attention", poor)
        c4.metric("Product Lines", plines)
        st.markdown('<div style="height:24px"></div>', unsafe_allow_html=True)
        show('<h2 style="font-size:1.05rem;font-weight:700;color:#1C1B18;margin:0 0 14px;letter-spacing:-.01em">Recent Analyses</h2>')
        tbl = ('<div style="background:#FFFFFF;border-radius:20px;border:1px solid #E9E7E0;overflow:hidden">'
               '<table style="width:100%;border-collapse:collapse;font-size:.84rem">'
               '<thead><tr style="background:#FAFAF7;border-bottom:1px solid #E9E7E0">')
        for h in ["ASIN","Product","Score","Title","Bullets","A+","Keywords","Date"]:
            tbl += ('<th style="padding:12px 16px;text-align:left;font-size:.7rem;font-weight:700;'
                    'text-transform:uppercase;letter-spacing:.07em;color:#9B9793;white-space:nowrap">' + h + '</th>')
        tbl += '</tr></thead><tbody>'
        for r in rows[:15]:
            s = r["total_score"]
            c_, bg_, tc_, lbl_ = _score_meta(s)
            score_cell = ('<span style="background:' + bg_ + ';color:' + tc_ + ';padding:3px 10px;border-radius:20px;'
                          'font-size:.75rem;font-weight:700">' + str(int(s)) + ' \u2014 ' + lbl_ + '</span>') if s is not None else '<span style="color:#9B9793">Error</span>'
            ap = '<span style="color:#16A34A;font-weight:600">Yes</span>' if r["has_aplus"] else '<span style="color:#DC2626;font-weight:600">No</span>'
            def fv(v): return str(int(v)) if v else "\u2014"
            tbl += ('<tr style="border-bottom:1px solid #F5F3EE">'
                    '<td style="padding:12px 16px"><code>' + r["asin"] + '</code></td>'
                    '<td style="padding:12px 16px;color:#3D3B35;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + (r["product_name"] or "\u2014")[:40] + '</td>'
                    '<td style="padding:12px 16px">' + score_cell + '</td>'
                    '<td style="padding:12px 16px;color:#6B6963">' + fv(r["title_score"]) + '</td>'
                    '<td style="padding:12px 16px;color:#6B6963">' + fv(r["bullets_score"]) + '</td>'
                    '<td style="padding:12px 16px">' + ap + '</td>'
                    '<td style="padding:12px 16px;color:#6B6963">' + fv(r["keywords_score"]) + '</td>'
                    '<td style="padding:12px 16px;color:#9B9793;font-size:.78rem">' + str(r["created_at"] or "")[:10] + '</td>'
                    '</tr>')
        tbl += '</tbody></table></div>'
        show(tbl)

# ── NEW ANALYSIS ───────────────────────────────────────────────────────────────
elif page == "\U0001f50d  New Analysis":
    page_header("New Analysis", "Scrape and score Amazon.co.uk listings in seconds")
    conn = db()
    lines = conn.execute("SELECT * FROM product_lines ORDER BY name").fetchall()
    rules = conn.execute("SELECT * FROM scoring_rules ORDER BY is_default DESC, name").fetchall()
    conn.close()
    if not lines:
        empty_state("\U0001f3f7\ufe0f","No product lines yet",
                    "Go to Product Lines to create one with your target keywords, then come back here.")
        st.stop()
    with st.container():
        show(card('<p style="font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#9B9793;margin:0 0 14px">Setup</p>', "20px 28px"))
    col_a, col_b, col_c = st.columns([2,1,1], gap="large")
    with col_a:
        show('<p style="font-size:.78rem;font-weight:600;color:#9B9793;margin:0 0 6px;text-transform:uppercase;letter-spacing:.06em">ASINs (one per line)</p>')
        asins_raw = st.text_area("", placeholder="B08N5WRWNW\nB09XYZ1234\nB07ABCDEF1", height=120, label_visibility="collapsed")
    with col_b:
        show('<p style="font-size:.78rem;font-weight:600;color:#9B9793;margin:0 0 6px;text-transform:uppercase;letter-spacing:.06em">Product Line</p>')
        line_names = [l["name"] + " (" + str(len(json.loads(l["keywords"]))) + " kws)" for l in lines]
        sel_line = st.selectbox("", line_names, label_visibility="collapsed")
    with col_c:
        show('<p style="font-size:.78rem;font-weight:600;color:#9B9793;margin:0 0 6px;text-transform:uppercase;letter-spacing:.06em">Scoring Rule</p>')
        rule_names = [r["name"] + (" (Default)" if r["is_default"] else "") for r in rules]
        sel_rule = st.selectbox(" ", rule_names, label_visibility="collapsed")
    st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
    run = st.button("\u25b6\ufe0f  Run Analysis", type="primary", use_container_width=True)
    if run:
        asins = [a.strip().upper() for a in asins_raw.strip().splitlines() if a.strip()]
        if not asins: st.error("Please enter at least one ASIN."); st.stop()
        line_obj  = lines[line_names.index(sel_line)]
        rule_obj  = rules[rule_names.index(sel_rule)]
        keywords  = json.loads(line_obj["keywords"])
        rule_dict = dict(rule_obj)
        bar = st.progress(0, text="Starting\u2026")
        for idx, asin in enumerate(asins):
            bar.progress(idx / max(len(asins),1), text="Scraping " + asin + "\u2026 (" + str(idx+1) + "/" + str(len(asins)) + ")")
            conn = db()
            try:
                scraped = scrape(asin)
                result  = analyse(scraped, keywords, rule_dict)
                pname   = scraped.get("brand") or (scraped.get("title") or "")[:60] or asin
                conn.execute("INSERT INTO results (asin,product_line_id,scoring_rule_id,product_name,product_image,title,bullets,has_aplus,description,total_score,title_score,bullets_score,aplus_score,keywords_score,title_issues,bullets_issues,aplus_issues,keywords_issues,found_keywords,missing_keywords,suggested_keywords) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (asin,line_obj["id"],rule_obj["id"],pname,scraped.get("image_url"),scraped.get("title"),json.dumps(scraped.get("bullets",[])),1 if scraped.get("has_aplus") else 0,scraped.get("description"),result["total_score"],result["title_score"],result["bullets_score"],result["aplus_score"],result["keywords_score"],json.dumps(result["title_issues"]),json.dumps(result["bullets_issues"]),json.dumps(result["aplus_issues"]),json.dumps(result["keywords_issues"]),json.dumps(result["found_keywords"]),json.dumps(result["missing_keywords"]),json.dumps(result["suggested_keywords"])))
                conn.commit()
                render_result(asin, scraped.get("title"), json.dumps(scraped.get("bullets",[])),
                              scraped.get("has_aplus"), scraped.get("image_url"),
                              result["total_score"], result["title_score"], result["bullets_score"],
                              result["aplus_score"], result["keywords_score"],
                              result["title_issues"], result["bullets_issues"],
                              result["aplus_issues"], result["keywords_issues"],
                              result["found_keywords"], result["missing_keywords"], result["suggested_keywords"],
                              rule_dict, keywords)
            except Exception as e:
                conn.execute("INSERT INTO results (asin,product_line_id,scoring_rule_id,scrape_error,total_score) VALUES (?,?,?,?,0)", (asin,line_obj["id"],rule_obj["id"],str(e)))
                conn.commit()
                st.error("**" + asin + "** \u2014 " + str(e))
            finally:
                conn.close()
        bar.progress(1.0, text="\u2713 Done!")

# ── HISTORY ────────────────────────────────────────────────────────────────────
elif page == "\U0001f4dc  History":
    page_header("History", "All past analyses with full details and re-analysis")
    conn = db()
    rows = conn.execute("SELECT r.*, pl.keywords as pl_keywords FROM results r LEFT JOIN product_lines pl ON r.product_line_id=pl.id ORDER BY r.created_at DESC").fetchall()
    rules_map = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM scoring_rules").fetchall()}
    conn.close()
    if not rows:
        empty_state("\U0001f4dc","No history yet","Run your first analysis and results will appear here.")
    else:
        col_exp, col_dl = st.columns([3,1])
        col_exp.caption(str(len(rows)) + " result" + ("s" if len(rows)!=1 else ""))
        xl = build_excel(rows)
        col_dl.download_button("\u2193 Export Excel", data=xl,
                               file_name="amazon_analysis.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
        st.markdown('<div style="height:12px"></div>', unsafe_allow_html=True)
        for r in rows:
            s = r["total_score"]
            c_, bg_, tc_, lbl_ = _score_meta(s)
            score_tag = (' [' + str(int(s)) + '/100 ' + lbl_ + ']') if s is not None else ' [Error]'
            date_tag  = '  ' + str(r["created_at"] or "")[:10]
            exp_label = r["asin"] + score_tag + '  \u00b7  ' + (r["product_name"] or "\u2014")[:35] + date_tag
            with st.expander(exp_label):
                if r["scrape_error"]:
                    st.error("Scraping failed: " + r["scrape_error"])
                    conn2 = db()
                    if st.button("Delete", key="del_" + str(r["id"])):
                        conn2.execute("DELETE FROM results WHERE id=?", (r["id"],)); conn2.commit(); st.rerun()
                    conn2.close()
                    continue
                pl_keywords = json.loads(r["pl_keywords"] or "[]") if "pl_keywords" in r.keys() else []
                rule_w = rules_map.get(r["scoring_rule_id"], {"title_weight":25,"bullets_weight":25,"aplus_weight":25,"keywords_weight":25})
                render_result(r["asin"], r["title"], r["bullets"], r["has_aplus"], r["product_image"],
                              r["total_score"], r["title_score"], r["bullets_score"],
                              r["aplus_score"], r["keywords_score"],
                              json.loads(r["title_issues"] or "[]"), json.loads(r["bullets_issues"] or "[]"),
                              json.loads(r["aplus_issues"] or "[]"), json.loads(r["keywords_issues"] or "[]"),
                              json.loads(r["found_keywords"] or "[]"), json.loads(r["missing_keywords"] or "[]"),
                              json.loads(r["suggested_keywords"] or "[]"),
                              rule_w, pl_keywords)
                col1, col2 = st.columns([1,3])
                conn2 = db()
                if col1.button("\U0001f5d1 Delete", key="del2_" + str(r["id"])):
                    conn2.execute("DELETE FROM results WHERE id=?", (r["id"],)); conn2.commit(); st.rerun()
                conn2.close()

# ── PRODUCT LINES ──────────────────────────────────────────────────────────────
elif page == "\U0001f3f7  Product Lines":
    page_header("Product Lines", "Group your products and assign target keyword lists")
    conn = db()
    lines = conn.execute("SELECT * FROM product_lines ORDER BY name").fetchall()
    with st.expander("\u2795  Create new product line", expanded=len(lines)==0):
        col1, col2 = st.columns([1,1], gap="large")
        with col1:
            new_name = st.text_input("Name", placeholder="e.g. Coffee Machines")
        with col2:
            kw_count_preview = 0
        new_kws = st.text_area("Keywords", placeholder="One keyword per line or comma-separated:\ncoffee machine\nespresso maker\nbarista\nautomatic coffee", height=180)
        kw_count_preview = len([k.strip() for k in re.split(r"[,\n]+", new_kws) if k.strip()])
        ca, cb = st.columns([1,3])
        ca.caption(str(kw_count_preview) + " keywords detected")
        if cb.button("Create product line", type="primary", key="create_pl"):
            if not new_name.strip():
                st.error("Please enter a name.")
            else:
                kws = [k.strip() for k in re.split(r"[,\n]+", new_kws) if k.strip()]
                try:
                    conn.execute("INSERT INTO product_lines (name,keywords) VALUES (?,?)", (new_name.strip(), json.dumps(kws)))
                    conn.commit(); st.success("\u2713 Created \'" + new_name.strip() + "\' with " + str(len(kws)) + " keywords!"); st.rerun()
                except Exception as e:
                    st.error(str(e))
    st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
    if not lines:
        empty_state("\U0001f3f7\ufe0f","No product lines yet","Create your first product line above to get started.")
    for line in lines:
        kws = json.loads(line["keywords"])
        with st.expander(line["name"] + "  \u00b7  " + str(len(kws)) + " keywords"):
            show("".join(pill(k,"suggest") for k in kws[:25]) + (' <span style="color:#9B9793;font-size:.78rem">+' + str(len(kws)-25) + ' more</span>' if len(kws)>25 else ""))
            show('<div style="height:10px"></div>')
            c1, c2 = st.columns([1,1], gap="large")
            with c1:
                en = st.text_input("Name", value=line["name"], key="ln_" + str(line["id"]))
            with c2:
                show('<p style="font-size:.78rem;color:#9B9793;margin:0 0 4px;font-weight:600">KEYWORDS (one per line)</p>')
            ek = st.text_area("", value="\n".join(kws), height=180, key="lk_" + str(line["id"]), label_visibility="collapsed")
            ca2, cb2 = st.columns([1,4])
            if ca2.button("Save", key="ls_" + str(line["id"])):
                nk = [k.strip() for k in ek.strip().splitlines() if k.strip()]
                conn.execute("UPDATE product_lines SET name=?,keywords=? WHERE id=?", (en.strip(), json.dumps(nk), line["id"]))
                conn.commit(); st.success("Saved!"); st.rerun()
            if cb2.button("Delete this product line", key="ld_" + str(line["id"])):
                conn.execute("DELETE FROM product_lines WHERE id=?", (line["id"],))
                conn.commit(); st.rerun()
    conn.close()

# ── SCORING RULES ──────────────────────────────────────────────────────────────
elif page == "\u2699\ufe0f  Scoring Rules":
    page_header("Scoring Rules", "Configure how listings are scored across each content category")
    conn = db()
    rules = conn.execute("SELECT * FROM scoring_rules ORDER BY is_default DESC, name").fetchall()
    with st.expander("\u2795  Create new scoring rule"):
        rname = st.text_input("Rule name", placeholder="e.g. Strict SEO, Premium Listings")
        show('<p style="font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#9B9793;margin:14px 0 8px">Category Weights (must sum to 100)</p>')
        rc1,rc2,rc3,rc4 = st.columns(4)
        tw=rc1.number_input("Title %",0,100,25,key="ntw"); bw=rc2.number_input("Bullets %",0,100,25,key="nbw")
        aw=rc3.number_input("A+ Content %",0,100,25,key="naw"); kw_=rc4.number_input("Keywords %",0,100,25,key="nkw")
        total_w = tw+bw+aw+kw_
        tw_ok = total_w == 100
        show('<p style="font-size:.855rem;font-weight:600;color:' + ("#16A34A" if tw_ok else "#DC2626") + ';margin:4px 0 16px">'
             + 'Total: ' + str(total_w) + '/100 ' + ("\u2713 Good to go" if tw_ok else "\u26a0\ufe0f Must equal exactly 100") + '</p>')
        col_x, col_y = st.columns(2, gap="large")
        with col_x:
            show('<p style="font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#9B9793;margin:0 0 8px">Title</p>')
            tca, tcb = st.columns(2)
            tmin=tca.number_input("Min chars",1,500,80,key="ntmin"); tmax=tcb.number_input("Max chars",1,500,200,key="ntmax")
            tkif=st.checkbox("Primary keyword in first 80 chars",True,key="ntkif")
        with col_y:
            show('<p style="font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#9B9793;margin:0 0 8px">Bullet Points</p>')
            bca,bcb,bcc = st.columns(3)
            bmc=bca.number_input("Min count",1,20,5,key="nbmc"); bml=bcb.number_input("Min chars",1,500,100,key="nbml"); bmx=bcc.number_input("Max chars",1,1000,255,key="nbmx")
        show('<p style="font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#9B9793;margin:14px 0 8px">Keywords</p>')
        kmc=st.slider("Min coverage %",0,100,70,key="nkmc")
        kit=st.checkbox("Top 3 keywords must appear in title",True,key="nkit")
        if st.button("Create rule", type="primary", disabled=(not tw_ok), key="create_rule"):
            if not rname.strip(): st.error("Enter a name.")
            else:
                try:
                    conn.execute("INSERT INTO scoring_rules (name,title_weight,bullets_weight,aplus_weight,keywords_weight,title_min_length,title_max_length,title_keyword_in_first,bullets_min_count,bullets_min_length,bullets_max_length,keywords_min_coverage,keywords_in_title) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                 (rname.strip(),tw,bw,aw,kw_,tmin,tmax,int(tkif),bmc,bml,bmx,kmc,int(kit)))
                    conn.commit(); st.success("\u2713 Rule created!"); st.rerun()
                except Exception as e: st.error(str(e))
    st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
    for rule in rules:
        tag = ' (Default)' if rule["is_default"] else ''
        with st.expander(rule["name"] + tag):
            show('<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:10px">'
                 '<div style="background:#FAFAF7;border-radius:10px;padding:14px 16px">'
                 '<p style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#9B9793;margin:0 0 6px">Weights</p>'
                 '<p style="font-size:.855rem;color:#3D3B35;margin:0">Title <b>' + str(rule["title_weight"]) + '%</b> &nbsp;\u00b7&nbsp; '
                 'Bullets <b>' + str(rule["bullets_weight"]) + '%</b> &nbsp;\u00b7&nbsp; '
                 'A+ <b>' + str(rule["aplus_weight"]) + '%</b> &nbsp;\u00b7&nbsp; '
                 'Keywords <b>' + str(rule["keywords_weight"]) + '%</b></p></div>'
                 '<div style="background:#FAFAF7;border-radius:10px;padding:14px 16px">'
                 '<p style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#9B9793;margin:0 0 6px">Thresholds</p>'
                 '<p style="font-size:.855rem;color:#3D3B35;margin:0">Title: <b>' + str(rule["title_min_length"]) + '\u2013' + str(rule["title_max_length"]) + '</b> chars &nbsp;\u00b7&nbsp; '
                 'Bullets: min <b>' + str(rule["bullets_min_count"]) + '</b> &nbsp;\u00b7&nbsp; '
                 'KW coverage \u2265 <b>' + str(round(rule["keywords_min_coverage"])) + '%</b></p></div>'
                 '</div>')
            if not rule["is_default"]:
                if st.button("Delete this rule", key="rd_" + str(rule["id"])):
                    conn.execute("DELETE FROM scoring_rules WHERE id=?", (rule["id"],)); conn.commit(); st.rerun()
    conn.close()

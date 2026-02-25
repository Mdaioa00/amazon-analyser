import streamlit as st
import sqlite3, httpx, json, re, random
from bs4 import BeautifulSoup

st.set_page_config(page_title="Amazon Content Analyser", page_icon="\U0001f6d2", layout="wide")

CSS = """
<style>
  [data-testid="stSidebar"] { background: #0f172a; }
  [data-testid="stSidebar"] .stRadio label { color: #cbd5e1 !important; font-size: 0.9rem; }
  .issue-box { background:#fef9c3; border:1px solid #fde68a; border-radius:8px; padding:8px 12px; margin-top:4px; font-size:0.85rem; }
  .kw-found   { display:inline-block; background:#d1fae5; color:#065f46; border-radius:20px; padding:2px 10px; margin:2px; font-size:0.8rem; }
  .kw-missing { display:inline-block; background:#fee2e2; color:#991b1b; border-radius:20px; padding:2px 10px; margin:2px; font-size:0.8rem; }
  .kw-suggest { display:inline-block; background:#e0e7ff; color:#3730a3; border-radius:20px; padding:2px 10px; margin:2px; font-size:0.8rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

DB = "amazon_analyser.db"

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS product_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            keywords TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS scoring_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            title_weight REAL DEFAULT 25,
            bullets_weight REAL DEFAULT 25,
            aplus_weight REAL DEFAULT 25,
            keywords_weight REAL DEFAULT 25,
            title_min_length INTEGER DEFAULT 80,
            title_max_length INTEGER DEFAULT 200,
            title_keyword_in_first INTEGER DEFAULT 1,
            bullets_min_count INTEGER DEFAULT 5,
            bullets_min_length INTEGER DEFAULT 100,
            bullets_max_length INTEGER DEFAULT 255,
            keywords_min_coverage REAL DEFAULT 70,
            keywords_in_title INTEGER DEFAULT 1,
            is_default INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asin TEXT NOT NULL,
            product_line_id INTEGER,
            scoring_rule_id INTEGER,
            product_name TEXT,
            product_image TEXT,
            title TEXT,
            bullets TEXT DEFAULT '[]',
            has_aplus INTEGER DEFAULT 0,
            description TEXT,
            scrape_error TEXT,
            total_score REAL,
            title_score REAL,
            bullets_score REAL,
            aplus_score REAL,
            keywords_score REAL,
            title_issues TEXT DEFAULT '[]',
            bullets_issues TEXT DEFAULT '[]',
            aplus_issues TEXT DEFAULT '[]',
            keywords_issues TEXT DEFAULT '[]',
            found_keywords TEXT DEFAULT '[]',
            missing_keywords TEXT DEFAULT '[]',
            suggested_keywords TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now'))
        );
        """)
        if not c.execute("SELECT id FROM scoring_rules WHERE is_default=1").fetchone():
            c.execute("INSERT INTO scoring_rules (name,is_default) VALUES ('Default Rule',1)")

init_db()

UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

def scrape(asin):
    url = f"https://www.amazon.co.uk/dp/{asin}"
    headers = {"User-Agent": random.choice(UA),
               "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
               "Accept-Language": "en-GB,en;q=0.9",
               "Accept-Encoding": "gzip, deflate, br",
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
    aplus_ids = ["aplus", "aplus3p_feature_div", "aplusBrandStory_feature_div"]
    has_aplus = any(soup.find("div", id=aid) and len((soup.find("div", id=aid) or {}).get_text(strip=True) or "") > 50 for aid in aplus_ids)
    desc_el = soup.find("div", id="productDescription")
    description = desc_el.get_text(strip=True) if desc_el else ""
    img_el = soup.find("img", id="landingImage") or soup.find("img", id="imgBlkFront")
    image_url = img_el.get("src") if img_el else None
    brand_el = soup.find("a", id="bylineInfo")
    brand = brand_el.get_text(strip=True) if brand_el else None
    return {"title": title, "bullets": bullets, "has_aplus": has_aplus,
            "description": description, "image_url": image_url, "brand": brand}

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
            ti.append(f"Title too short ({ln} chars). Target: {rule['title_min_length']}–{rule['title_max_length']} chars.")
            ts += mw * 0.4 * (ln / rule["title_min_length"])
        elif ln > rule["title_max_length"]:
            ti.append(f"Title too long ({ln} chars) — Amazon may truncate it.")
            ts += mw * 0.30
        else:
            ts += mw * 0.40
        found_t, _ = kw_split(title, keywords)
        kr = len(found_t) / len(keywords) if keywords else 1.0
        ts += mw * 0.40 * kr
        if kr < 0.3:
            ti.append(f"Only {len(found_t)}/{len(keywords)} keywords in title — move top keywords near the start.")
        elif kr < 0.6:
            ti.append(f"{len(found_t)}/{len(keywords)} keywords in title — room to improve.")
        if rule.get("title_keyword_in_first") and keywords:
            if not any(k.lower() in title[:80].lower() for k in keywords[:3]):
                ti.append("Primary keyword not in first 80 characters of the title.")
            else:
                ts += mw * 0.20
        if sum(1 for w in title.split() if w.isupper() and len(w) > 2) > 3:
            ti.append("Too many ALL-CAPS words — use Title Case for better readability.")
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
        if short: bi.append(f"Bullet(s) #{short} are too short (< {rule['bullets_min_length']} chars).")
        if long_: bi.append(f"Bullet(s) #{long_} exceed {rule['bullets_max_length']} chars — may be truncated.")
        ok = (cnt - len(short) - len(long_)) / cnt
        bs += mw2 * 0.30 * ok
        found_b, _ = kw_split(" ".join(bullets), keywords)
        kr2 = len(found_b) / len(keywords) if keywords else 1.0
        bs += mw2 * 0.40 * kr2
        if kr2 < 0.5:
            bi.append(f"Low keyword coverage in bullets ({len(found_b)}/{len(keywords)}). Weave in more target keywords.")
    a_s = rule["aplus_weight"] if has_aplus else 0
    ai = [] if has_aplus else ["No A+ Content detected. Adding A+ can boost conversion by 5-10% and improves brand storytelling."]
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
                ki.append("None of the top 3 keywords appear in the title — move them there for SEO impact.")
    tokens = re.findall(r'\b[a-zA-Z]{4,}\b', all_content.lower())
    stop = {"with","this","that","from","have","will","your","their","also","each","which","they","more","than","when","into","only","over","such","used","using","pack","item","product","brand","quality","great","make","made","features","feature","design","provides","include","perfect","ideal","easy","best","good","high","well","help","helps","allows","keep"}
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

def score_emoji(s):
    if s is None: return "⚪"
    if s >= 85: return "🟢"
    if s >= 65: return "🟡"
    if s >= 40: return "🟠"
    return "🔴"

def score_label(s):
    if s is None: return "N/A"
    if s >= 85: return "Excellent"
    if s >= 65: return "Good"
    if s >= 40: return "Needs Work"
    return "Poor"

def progress_bar(score, max_score, label):
    pct = (score / max_score * 100) if max_score else 0
    color = "#10b981" if pct >= 85 else "#f59e0b" if pct >= 65 else "#f97316" if pct >= 40 else "#ef4444"
    st.markdown(f"""
    <div style="margin-bottom:8px">
      <div style="display:flex;justify-content:space-between;font-size:0.85rem;font-weight:600;color:#374151">
        <span>{label}</span><span style="color:#6b7280">{score:.1f} / {max_score:.0f}</span>
      </div>
      <div style="background:#e2e8f0;border-radius:999px;height:10px;margin-top:4px">
        <div style="background:{color};width:{pct:.0f}%;height:10px;border-radius:999px"></div>
      </div>
    </div>""", unsafe_allow_html=True)

def kw_badges(kws, cls):
    return "".join(f'<span class="{cls}">{k}</span>' for k in kws)

def show_issues(issues):
    for iss in issues:
        st.markdown(f'<div class="issue-box">⚠️ {iss}</div>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 🛒 Amazon\n### Content Analyser")
    st.caption("Amazon.co.uk · UK Marketplace")
    st.markdown("---")
    page = st.radio("Go to", ["🏠  Dashboard","🔍  New Analysis",
                               "🏷️  Product Lines","⚙️  Scoring Rules","📜  History"],
                    label_visibility="collapsed")

if page == "🏠  Dashboard":
    st.title("Dashboard")
    conn = db()
    rows = conn.execute("SELECT * FROM results ORDER BY created_at DESC LIMIT 100").fetchall()
    conn.close()
    total_a = len(rows)
    avg_s = round(sum(r["total_score"] or 0 for r in rows) / max(total_a,1), 1)
    poor = sum(1 for r in rows if (r["total_score"] or 0) < 65)
    c1,c2,c3 = st.columns(3)
    c1.metric("📊 Analyses Run", total_a)
    c2.metric("✅ Average Score", f"{avg_s} / 100")
    c3.metric("⚠️ Need Attention", poor)
    st.markdown("---")
    st.subheader("Recent Analyses")
    if not rows:
        st.info("No analyses yet. Go to **New Analysis** to get started.")
    else:
        for r in rows[:10]:
            s = r["total_score"]
            c1,c2,c3,c4 = st.columns([2,4,2,2])
            c1.code(r["asin"])
            c2.write(r["product_name"] or "—")
            c3.write(f"{score_emoji(s)} **{s:.0f}/100**" if s is not None else "❌ Error")
            c4.caption(str(r["created_at"])[:10])

elif page == "🔍  New Analysis":
    st.title("New Analysis")
    conn = db()
    lines = conn.execute("SELECT * FROM product_lines ORDER BY name").fetchall()
    rules = conn.execute("SELECT * FROM scoring_rules ORDER BY is_default DESC, name").fetchall()
    conn.close()
    if not lines:
        st.warning("⚠️ No product lines found. Please create one in **Product Lines** first.")
        st.stop()
    asins_raw = st.text_area("ASINs (one per line)", placeholder="B08N5WRWNW\nB09XYZ1234", height=120)
    line_names = [f"{l['name']} ({len(json.loads(l['keywords']))} keywords)" for l in lines]
    sel_line = st.selectbox("Product Line", line_names)
    rule_names = [f"{r['name']}{'  Default' if r['is_default'] else ''}" for r in rules]
    sel_rule = st.selectbox("Scoring Rule", rule_names)
    if st.button("Run Analysis", type="primary", use_container_width=True):
        asins = [a.strip().upper() for a in asins_raw.strip().splitlines() if a.strip()]
        if not asins:
            st.error("Please enter at least one ASIN.")
            st.stop()
        line_obj = lines[line_names.index(sel_line)]
        rule_obj = rules[rule_names.index(sel_rule)]
        keywords = json.loads(line_obj["keywords"])
        rule_dict = dict(rule_obj)
        bar = st.progress(0, text="Starting...")
        for i, asin in enumerate(asins):
            bar.progress(i / len(asins), text=f"Scraping {asin}...")
            conn = db()
            try:
                scraped = scrape(asin)
                result = analyse(scraped, keywords, rule_dict)
                pname = scraped.get("brand") or (scraped.get("title") or "")[:60] or asin
                conn.execute("""INSERT INTO results (asin,product_line_id,scoring_rule_id,product_name,
                    product_image,title,bullets,has_aplus,description,total_score,title_score,
                    bullets_score,aplus_score,keywords_score,title_issues,bullets_issues,
                    aplus_issues,keywords_issues,found_keywords,missing_keywords,suggested_keywords)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (asin,line_obj["id"],rule_obj["id"],pname,scraped.get("image_url"),
                     scraped.get("title"),json.dumps(scraped.get("bullets",[])),
                     1 if scraped.get("has_aplus") else 0,scraped.get("description"),
                     result["total_score"],result["title_score"],result["bullets_score"],
                     result["aplus_score"],result["keywords_score"],
                     json.dumps(result["title_issues"]),json.dumps(result["bullets_issues"]),
                     json.dumps(result["aplus_issues"]),json.dumps(result["keywords_issues"]),
                     json.dumps(result["found_keywords"]),json.dumps(result["missing_keywords"]),
                     json.dumps(result["suggested_keywords"])))
                conn.commit()
                st.markdown("---")
                s = result["total_score"]
                col1,col2 = st.columns([3,1])
                col1.subheader(f"{score_emoji(s)} {asin} — {s}/100 ({score_label(s)})")
                if scraped.get("title"): col1.caption(scraped["title"][:130])
                if scraped.get("image_url"): col2.image(scraped["image_url"], width=90)
                progress_bar(result["title_score"],    rule_dict["title_weight"],    "📝 Title")
                show_issues(result["title_issues"])
                progress_bar(result["bullets_score"],  rule_dict["bullets_weight"],  "🔘 Bullet Points")
                show_issues(result["bullets_issues"])
                progress_bar(result["aplus_score"],    rule_dict["aplus_weight"],    "✨ A+ Content")
                show_issues(result["aplus_issues"])
                progress_bar(result["keywords_score"], rule_dict["keywords_weight"], "🔑 Keywords SEO")
                show_issues(result["keywords_issues"])
                if result["found_keywords"] or result["missing_keywords"]:
                    st.markdown("**Keywords:**")
                    st.markdown(kw_badges(result["found_keywords"],"kw-found") + kw_badges(result["missing_keywords"],"kw-missing"), unsafe_allow_html=True)
                    st.caption("🟢 Found in listing   🔴 Missing from listing")
                if result["suggested_keywords"]:
                    st.markdown("**💡 Suggested keywords (extracted from product content):**")
                    st.markdown(kw_badges(result["suggested_keywords"],"kw-suggest"), unsafe_allow_html=True)
            except Exception as e:
                conn.execute("INSERT INTO results (asin,product_line_id,scoring_rule_id,scrape_error,total_score) VALUES (?,?,?,?,0)",
                             (asin,line_obj["id"],rule_obj["id"],str(e)))
                conn.commit()
                st.error(f"**{asin}** — {e}")
            finally:
                conn.close()
        bar.progress(1.0, text="Done!")

elif page == "🏷️  Product Lines":
    st.title("Product Lines")
    conn = db()
    lines = conn.execute("SELECT * FROM product_lines ORDER BY name").fetchall()
    with st.expander("➕ Create New Product Line", expanded=len(lines)==0):
        new_name = st.text_input("Product line name", placeholder="e.g. Coffee Machines")
        new_kws  = st.text_area("Keywords (one per line or comma-separated)",
                                placeholder="coffee machine\nespresso maker\nbarista\nautomatic coffee", height=150)
        if st.button("Create", type="primary"):
            if not new_name.strip():
                st.error("Enter a name.")
            else:
                kws = [k.strip() for k in re.split(r'[,\n]+', new_kws) if k.strip()]
                try:
                    conn.execute("INSERT INTO product_lines (name,keywords) VALUES (?,?)", (new_name.strip(), json.dumps(kws)))
                    conn.commit(); st.success(f"Created with {len(kws)} keywords!"); st.rerun()
                except Exception as e:
                    st.error(str(e))
    st.markdown("---")
    if not lines:
        st.info("No product lines yet.")
    for line in lines:
        kws = json.loads(line["keywords"])
        with st.expander(f"**{line['name']}** — {len(kws)} keywords"):
            en = st.text_input("Name", value=line["name"], key=f"ln_{line['id']}")
            ek = st.text_area("Keywords", value="\n".join(kws), height=150, key=f"lk_{line['id']}")
            c1,c2 = st.columns(2)
            if c1.button("Save", key=f"ls_{line['id']}"):
                nk = [k.strip() for k in ek.strip().splitlines() if k.strip()]
                conn.execute("UPDATE product_lines SET name=?,keywords=? WHERE id=?", (en.strip(), json.dumps(nk), line["id"]))
                conn.commit(); st.rerun()
            if c2.button("Delete", key=f"ld_{line['id']}"):
                conn.execute("DELETE FROM product_lines WHERE id=?", (line["id"],))
                conn.commit(); st.rerun()
    conn.close()

elif page == "⚙️  Scoring Rules":
    st.title("Scoring Rules")
    conn = db()
    rules = conn.execute("SELECT * FROM scoring_rules ORDER BY is_default DESC, name").fetchall()
    with st.expander("➕ Create New Scoring Rule"):
        rname = st.text_input("Rule name", placeholder="e.g. Strict SEO")
        st.markdown("**Category Weights** (must sum to 100)")
        rc1,rc2,rc3,rc4 = st.columns(4)
        tw=rc1.number_input("Title %",0,100,25,key="ntw")
        bw=rc2.number_input("Bullets %",0,100,25,key="nbw")
        aw=rc3.number_input("A+ %",0,100,25,key="naw")
        kw_=rc4.number_input("Keywords %",0,100,25,key="nkw")
        total_w = tw+bw+aw+kw_
        st.markdown(f"Total: **{total_w}** {'✅' if total_w==100 else '⚠️ must be 100'}")
        st.markdown("**Title**")
        tc1,tc2=st.columns(2)
        tmin=tc1.number_input("Min chars",1,500,80,key="ntmin"); tmax=tc2.number_input("Max chars",1,500,200,key="ntmax")
        tkif=st.checkbox("Primary keyword in first 80 chars",True,key="ntkif")
        st.markdown("**Bullets**")
        bc1,bc2,bc3=st.columns(3)
        bmc=bc1.number_input("Min count",1,20,5,key="nbmc"); bml=bc2.number_input("Min chars",1,500,100,key="nbml"); bmx=bc3.number_input("Max chars",1,1000,255,key="nbmx")
        st.markdown("**Keywords**")
        kmc=st.slider("Min coverage %",0,100,70,key="nkmc")
        kit=st.checkbox("Top 3 keywords must be in title",True,key="nkit")
        if st.button("Create Rule", type="primary", disabled=(total_w!=100)):
            if not rname.strip(): st.error("Enter a name.")
            else:
                try:
                    conn.execute("INSERT INTO scoring_rules (name,title_weight,bullets_weight,aplus_weight,keywords_weight,title_min_length,title_max_length,title_keyword_in_first,bullets_min_count,bullets_min_length,bullets_max_length,keywords_min_coverage,keywords_in_title) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                 (rname.strip(),tw,bw,aw,kw_,tmin,tmax,int(tkif),bmc,bml,bmx,kmc,int(kit)))
                    conn.commit(); st.success("Rule created!"); st.rerun()
                except Exception as e: st.error(str(e))
    st.markdown("---")
    for rule in rules:
        with st.expander(f"**{rule['name']}**{'  (Default)' if rule['is_default'] else ''}"):
            st.markdown(f"Weights: Title {rule['title_weight']}% | Bullets {rule['bullets_weight']}% | A+ {rule['aplus_weight']}% | Keywords {rule['keywords_weight']}%")
            st.markdown(f"Title: {rule['title_min_length']}–{rule['title_max_length']} chars | Bullets: min {rule['bullets_min_count']}, {rule['bullets_min_length']}–{rule['bullets_max_length']} chars/bullet | KW coverage >= {rule['keywords_min_coverage']}%")
            if not rule["is_default"]:
                if st.button("Delete", key=f"rd_{rule['id']}"):
                    conn.execute("DELETE FROM scoring_rules WHERE id=?", (rule["id"],)); conn.commit(); st.rerun()
    conn.close()

elif page == "📜  History":
    st.title("Analysis History")
    conn = db()
    rows = conn.execute("SELECT * FROM results ORDER BY created_at DESC").fetchall()
    conn.close()
    if not rows:
        st.info("No analyses yet.")
    for r in rows:
        s = r["total_score"]
        label = f"{score_emoji(s)} {r['asin']} — {r['product_name'] or '—'} — {f'{s:.0f}/100' if s is not None else 'Error'} — {str(r['created_at'] or '')[:10]}"
        with st.expander(label):
            if r["scrape_error"]:
                st.error(f"Error: {r['scrape_error']}"); continue
            col1,col2 = st.columns([3,1])
            if r["product_image"]: col2.image(r["product_image"], width=110)
            col1.markdown(f"**Title:** {r['title'] or '—'}")
            if r["title"]: col1.caption(f"{len(r['title'])} characters")
            col1.markdown(f"A+ Content: {'✅ Yes' if r['has_aplus'] else '❌ No'}")
            col1.markdown(f"[View on Amazon](https://www.amazon.co.uk/dp/{r['asin']})")
            rw = {"title_weight":25,"bullets_weight":25,"aplus_weight":25,"keywords_weight":25}
            progress_bar(r["title_score"] or 0,    rw["title_weight"],    "📝 Title")
            show_issues(json.loads(r["title_issues"] or "[]"))
            progress_bar(r["bullets_score"] or 0,  rw["bullets_weight"],  "🔘 Bullet Points")
            show_issues(json.loads(r["bullets_issues"] or "[]"))
            progress_bar(r["aplus_score"] or 0,    rw["aplus_weight"],    "✨ A+ Content")
            show_issues(json.loads(r["aplus_issues"] or "[]"))
            progress_bar(r["keywords_score"] or 0, rw["keywords_weight"], "🔑 Keywords SEO")
            show_issues(json.loads(r["keywords_issues"] or "[]"))
            found=json.loads(r["found_keywords"] or "[]"); missing=json.loads(r["missing_keywords"] or "[]"); suggest=json.loads(r["suggested_keywords"] or "[]")
            if found or missing:
                st.markdown("**Keywords:**")
                st.markdown(kw_badges(found,"kw-found")+kw_badges(missing,"kw-missing"), unsafe_allow_html=True)
                st.caption("🟢 Found   🔴 Missing")
            if suggest:
                st.markdown("**Suggested keywords:**")
                st.markdown(kw_badges(suggest,"kw-suggest"), unsafe_allow_html=True)
            if r["bullets"]:
                with st.expander("View bullet points"):
                    for i,b in enumerate(json.loads(r["bullets"])):
                        st.markdown(f"**{i+1}.** {b}  ({len(b)} chars)")
            conn2 = db()
            if st.button("Delete this result", key=f"del_{r['id']}"):
                conn2.execute("DELETE FROM results WHERE id=?", (r["id"],)); conn2.commit(); st.rerun()
            conn2.close()

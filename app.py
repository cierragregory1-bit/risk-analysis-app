import os, io, re, math, time
from datetime import datetime

import streamlit as st
import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from fpdf import FPDF
from PIL import Image

# =========================
# Page
# =========================
st.set_page_config(page_title="Contingent Property Risk Analysis", page_icon="🏡", layout="wide")

# =========================
# Secrets (Realtor Search only)
# =========================
api = st.secrets.get("realtor_api", {})
API_KEY = api.get("key")
HOST_SEARCH = api.get("host_search", "realtor-search.p.rapidapi.com")

if not API_KEY:
    st.error(
        "❌ API key missing. In **Settings → Secrets**, add:\n\n"
        "```toml\n[realtor_api]\nkey = \"YOUR_RAPIDAPI_KEY\"\n"
        "host_search = \"realtor-search.p.rapidapi.com\"\n```"
    )
    st.stop()

def h_search():
    return {"x-rapidapi-key": API_KEY, "x-rapidapi-host": HOST_SEARCH}

# Optional logo for PDF (put a file named 'logo.png' next to app.py)
LOGO_PATH = "logo.png"

# =========================
# Debug Sidebar
# =========================
st.sidebar.title("Debug")
st.sidebar.caption(
    f"🔑 Using RapidAPI key **{API_KEY[:6]}...{API_KEY[-4:]}**"
)
st.sidebar.caption(f"🌐 Host: {HOST_SEARCH}")

def connectivity_test():
    try:
        url = f"https://{HOST_SEARCH}/properties/nearby-home-values"
        params = {"lat": "32.7327132", "lon": "-97.3089965", "radius": "2"}
        r = requests.get(url, headers=h_search(), params=params, timeout=20)
        st.sidebar.write(f"Status: {r.status_code}")
        st.sidebar.code(r.text[:800], language="json")
    except Exception as e:
        st.sidebar.error(f"Connectivity error: {e}")

if st.sidebar.button("Test Realtor API Connection"):
    connectivity_test()

# =========================
# Helpers
# =========================
def fmt_money(x):
    try: return "${:,.0f}".format(float(x))
    except: return "—"

def safe_median(vals):
    clean = [v for v in vals if v is not None and not (isinstance(v, float) and np.isnan(v))]
    return float(np.median(clean)) if clean else None

def abbreviate(s, n=24):
    if not s: return ""
    return s if len(s) <= n else s[:n-1] + "…"

def load_logo():
    try: return Image.open(LOGO_PATH)
    except: return None

def normalize_address(addr: str) -> str:
    if not addr: return ""
    a = addr.strip()
    # strip common unit markers for cleaner geocoding
    for token in [" Apt ", " Unit ", " Ste ", " Suite ", "#"]:
        a = a.replace(token, " ")
    return " ".join(a.split())

def is_url(s: str) -> bool:
    return s.lower().startswith("http://") or s.lower().startswith("https://")

def parse_realtor_url(url: str):
    """
    Pull a USPS-style address guess from a Realtor listing URL.
    Example:
      .../1105-Freeman-St_Fort-Worth_TX_76104_M81833-43262
      -> '1105 Freeman St, Fort Worth, TX 76104'
    """
    try:
        seg = re.search(r"realestateandhomes-detail/([^/?#]+)", url, flags=re.I)
        if not seg: return None
        slug = seg.group(1)
        slug = slug.split("_M")[0]  # drop trailing property id if present
        parts = slug.split("_")     # ["1105-Freeman-St", "Fort-Worth", "TX", "76104"]
        if len(parts) >= 4:
            street = parts[0].replace("-", " ")
            city   = parts[1].replace("-", " ")
            state  = parts[2]
            zipc   = parts[3]
            return f"{street}, {city}, {state} {zipc}"
        return slug.replace("-", " ").replace("_", " ")
    except Exception:
        return None

# ---- Session flag so we don't call a host you're not subscribed to over and over
if "disable_realtor_autocomplete" not in st.session_state:
    st.session_state.disable_realtor_autocomplete = False

# =========================
# Geocoding: Realtor → OSM → (optional) Google
# =========================
def resolve_latlon_realtor(addr, debug):
    if st.session_state.disable_realtor_autocomplete:
        return None, None, None
    url = f"https://{HOST_SEARCH}/properties/auto-complete"
    r = requests.get(url, headers=h_search(), params={"input": addr}, timeout=20)
    debug.append(("SEARCH auto-complete", r.status_code, r.text[:800]))
    if r.status_code == 403:
        # Not subscribed — stop trying this endpoint for this session
        st.session_state.disable_realtor_autocomplete = True
        return None, None, None
    if r.status_code != 200:
        return None, None, None
    js = r.json()
    hits = js.get("hits") or js.get("data") or js.get("results") or []
    for h in hits:
        lat = h.get("coordinate", {}).get("lat") or h.get("lat")
        lon = h.get("coordinate", {}).get("lon") or h.get("lon")
        line = h.get("address_line") or h.get("line") or h.get("display") or ""
        city = h.get("city") or ""
        disp = ", ".join([p for p in [line, city] if p])
        if lat and lon:
            return float(lat), float(lon), disp or addr
    return None, None, None

def resolve_latlon_osm(addr, debug):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": addr, "format": "jsonv2", "limit": 1, "addressdetails": 1, "countrycodes": "us"}
    headers_nom = {"User-Agent": "contingent-risk-app/1.0 (contact: you@example.com)"}
    r = requests.get(url, params=params, headers=headers_nom, timeout=20)
    debug.append(("OSM nominatim", r.status_code, r.text[:800]))
    if r.status_code != 200: return None, None, None
    data = r.json()
    if not data: return None, None, None
    lat = float(data[0]["lat"]); lon = float(data[0]["lon"])
    disp = data[0].get("display_name", addr)
    return lat, lon, disp

def resolve_latlon_google(addr, debug):
    key = st.secrets.get("google", {}).get("geocoding_key")
    if not key: return None, None, None
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": addr, "key": key, "region": "us"}
    r = requests.get(url, params=params, timeout=15)
    debug.append(("GOOGLE geocode", r.status_code, r.text[:500]))
    if r.status_code != 200: return None, None, None
    js = r.json()
    if js.get("status") != "OK": return None, None, None
    res = js["results"][0]
    loc = res["geometry"]["location"]
    disp = res.get("formatted_address", addr)
    return float(loc["lat"]), float(loc["lng"]), disp

def resolve_to_latlon(address_or_url, debug):
    s = (address_or_url or "").strip()
    if not s: return None, None, None

    # If it's a Realtor URL, parse a USPS-style address guess
    if is_url(s):
        addr_guess = parse_realtor_url(s) or s
        addr_guess = normalize_address(addr_guess)
        lat, lon, disp = resolve_latlon_realtor(addr_guess, debug)
        if lat and lon: return lat, lon, disp
        lat, lon, disp = resolve_latlon_osm(addr_guess, debug)
        if lat and lon: return lat, lon, disp
        return resolve_latlon_google(addr_guess, debug)

    # Plain address
    addr = normalize_address(s)
    lat, lon, disp = resolve_latlon_realtor(addr, debug)
    if lat and lon: return lat, lon, disp
    lat, lon, disp = resolve_latlon_osm(addr, debug)
    if lat and lon: return lat, lon, disp
    return resolve_latlon_google(addr, debug)

# =========================
# Comps fetch with backoff + session cache
# =========================
if "nearby_cache" not in st.session_state:
    st.session_state.nearby_cache = {}

def fetch_nearby_values_once(lat, lon, radius_miles=2.0, limit=25, debug=None):
    cache_key = (round(lat,6), round(lon,6), float(radius_miles))
    if cache_key in st.session_state.nearby_cache:
        return st.session_state.nearby_cache[cache_key]

    url = f"https://{HOST_SEARCH}/properties/nearby-home-values"
    params = {"lat": str(lat), "lon": str(lon), "radius": str(radius_miles)}
    backoffs = [0, 6, 12, 24]  # seconds; tuned to avoid 429 loops
    last_rows = []

    for wait in backoffs:
        if wait:
            time.sleep(wait)
        r = requests.get(url, headers=h_search(), params=params, timeout=25)
        if debug is not None:
            dbg_body = r.text[:800]
            debug.append((f"SEARCH nearby-home-values r={radius_miles} wait={wait}", r.status_code, dbg_body))

        if r.status_code == 429:
            # Too many requests → back off and retry
            continue
        if r.status_code != 200:
            break

        js = r.json()
        raw = js.get("data", {}).get("home_search", {}).get("results", []) \
              or js.get("data") or js.get("results") or js.get("homes") \
              or js.get("listings") or js.get("properties") or []
        rows = []
        for it in raw[:limit]:
            price = it.get("price") or it.get("list_price") or it.get("value") or it.get("estimate") \
                    or (it.get("current_estimates")[0]["estimate"] if isinstance(it.get("current_estimates"), list) and it.get("current_estimates") else None) \
                    or (it.get("avm", {}).get("value") if isinstance(it.get("avm"), dict) else None)
            dom = it.get("days_on_market") or it.get("dom")
            size_field = it.get("building_size", {})
            if isinstance(size_field, dict):
                sqft = size_field.get("size")
            else:
                sqft = size_field or it.get("sqft") or it.get("living_area")
            a = it.get("location", {}).get("address", {}) if isinstance(it.get("location"), dict) else {}
            line = a.get("line") or (it.get("address", {}) or {}).get("line") or it.get("address_line") or it.get("line") or ""
            city = a.get("city") or (it.get("address", {}) or {}).get("city") or it.get("city") or ""
            addr = ", ".join([p for p in [line, city] if p]) or it.get("address") or ""
            if addr:
                rows.append({
                    "address": addr,
                    "price": float(price) if price else None,
                    "dom": int(dom) if dom else None,
                    "sqft": int(sqft) if sqft else None
                })
        last_rows = rows
        break  # successful 200 → stop retrying

    st.session_state.nearby_cache[cache_key] = last_rows
    return last_rows

def dedupe_props(rows):
    seen = set(); out = []
    for r in rows:
        k = (r.get("address"), r.get("price"), r.get("sqft"))
        if k not in seen:
            seen.add(k); out.append(r)
    return out

def fetch_nearby_values(lat, lon, radius_miles=2.0, limit=25, debug=None):
    # Try caller radius first
    results = fetch_nearby_values_once(lat, lon, radius_miles, limit, debug)
    results = dedupe_props(results)
    if len(results) >= 8:
        return results[:limit]

    # If thin, widen gently (avoid hammering API; no parallel calls)
    for rmi in [3.0, 5.0]:
        rows = fetch_nearby_values_once(lat, lon, rmi, limit, debug)
        results.extend(rows)
        results = dedupe_props(results)
        if len(results) >= 8:
            break

    return results[:limit]

# =========================
# Risk model
# =========================
def subject_from_comps(comps):
    prices = [c["price"] for c in comps if c["price"]]
    doms = [c["dom"] for c in comps if c["dom"]]
    return {"price": safe_median(prices), "dom": int(round(safe_median(doms))) if doms else None}

def classify_risk(subject_price, subject_dom, comp_prices, comp_doms):
    reasons = []
    if not comp_prices:
        return "Unavailable", None, None, ["No comparable properties found."]

    comp_price = safe_median(comp_prices)
    comp_dom = safe_median(comp_doms) if comp_doms else None

    price_diff = None
    if subject_price and comp_price:
        price_diff = (subject_price - comp_price) / comp_price * 100
        reasons.append(f"Subject vs comps: {fmt_money(subject_price)} vs {fmt_money(comp_price)} ({price_diff:+.1f}%).")
    else:
        reasons.append("Using comp medians as subject proxy (insufficient subject price).")

    dom_diff = None
    if subject_dom is not None and comp_dom:
        dom_diff = (subject_dom - comp_dom) / comp_dom * 100
        reasons.append(f"Subject DOM vs comps: {subject_dom} vs {int(comp_dom)} ({dom_diff:+.0f}%).")

    # scoring
    price_pen = 5.0 if price_diff is None else max(0.0, min(10.0, (price_diff / 25.0) * 10.0))
    dom_pen   = 3.0 if dom_diff is None else max(0.0, min(10.0, (dom_diff / 150.0) * 10.0))
    score = 0.7 * price_pen + 0.3 * dom_pen

    band = "Low" if score < 3 else "Moderate" if score < 6 else "High"
    prob60 = int(round(1 / (1 + math.exp(0.55 * (score - 5))) * 100))
    reasons.append(f"Composite score **{score:.1f}/10** → {band}.")
    reasons.append(f"Estimated **{prob60}%** probability to sell within 60 days.")
    return band, round(score,1), prob60, reasons

def suggestions_for(band):
    if band == "Low": return [
        "Standard contingency; list within 30 days at competitive pricing.",
        "Minor concessions if no offer by Day 21; maintain weekly agent feedback."
    ]
    if band == "Moderate": return [
        "Staging & pro photos; weekly agent feedback to builder.",
        "Auto price reductions of ~1% at Day 21 and Day 35 if no offers."
    ]
    if band == "High": return [
        "List at/under comp median day one; refresh marketing weekly.",
        "Builder may extend close or convert to non-contingent if not under contract by Day 60."
    ]
    return ["Insufficient data — require tight listing timeline + adjustment plan."]

# =========================
# Charts
# =========================
def bar_chart_with_subject(subject, values, labels, title, ylabel):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(labels, values, label="Comparable Properties")
    if subject:
        ax.axhline(subject, color="#e07a5f", linestyle="--", linewidth=2, label="Subject (proxy)")
    ax.set_title(title); ax.set_ylabel(ylabel)
    ax.legend(loc="upper right")
    plt.xticks(rotation=20, ha="right")
    st.pyplot(fig)

# =========================
# PDF
# =========================
def build_pdf(report):
    pdf = FPDF(); pdf.add_page()
    logo = load_logo()
    if logo:
        tmp = "tmp_logo.png"; logo.save(tmp); pdf.image(tmp, x=10, y=10, w=18); os.remove(tmp)
    pdf.set_font("Arial", "B", 16); pdf.cell(0, 10, "Contingent Property Risk Analysis", ln=True, align="C")
    pdf.set_font("Arial", "", 11); pdf.cell(0, 8, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align="C"); pdf.ln(4)
    pdf.set_font("Arial", "B", 12); pdf.cell(0, 8, "Subject (derived from comps):", ln=True)
    pdf.set_font("Arial", "", 11); pdf.multi_cell(0, 6, f"Address: {report['subject_address']}")
    pdf.cell(0, 6, f"Subject Price (proxy): {fmt_money(report['subject_price'])}", ln=True)
    pdf.cell(0, 6, f"Subject DOM (proxy): {report['subject_dom'] if report['subject_dom'] is not None else '—'}", ln=True); pdf.ln(2)
    pdf.set_font("Arial", "B", 12); pdf.cell(0, 8, f"Risk: {report['risk_band']}  |  Probability (60d): {report['probability_60d']}%", ln=True)
    pdf.set_font("Arial", "", 11)
    for r in report["reasons"]: pdf.multi_cell(0, 6, f"- {r}")
    pdf.ln(1); pdf.set_font("Arial", "B", 12); pdf.cell(0, 8, "Contingency Suggestions:", ln=True)
    pdf.set_font("Arial", "", 11)
    for s in report["suggestions"]: pdf.multi_cell(0, 6, f"- {s}")
    pdf.ln(1); pdf.set_font("Arial", "B", 12); pdf.cell(0, 8, "Comparable Properties:", ln=True)
    pdf.set_font("Arial", "", 11)
    for c in report["comps"][:12]:
        line = f"{c['address']} | {fmt_money(c['price'])} | DOM: {c['dom'] if c['dom'] else '—'} | SqFt: {c['sqft'] if c['sqft'] else '—'}"
        pdf.multi_cell(0, 6, line)
    buf = io.BytesIO(); pdf.output(buf); buf.seek(0); return buf

# =========================
# UI
# =========================
st.title("🏡 Contingent Property Risk Analysis")
st.caption("Paste a Realtor URL *or* type a full address. We parse → geocode (Realtor→OSM→optional Google) → comps → risk → PDF.")

addr_or_url = st.text_input("Enter Address or Realtor.com URL", placeholder="e.g., 1105 Freeman St, Fort Worth, TX 76104 or https://www.realtor.com/realestateandhomes-detail/...")

with st.expander("If the address can’t be resolved, enter coordinates manually"):
    use_manual = st.checkbox("Use manual latitude/longitude")
    colm1, colm2 = st.columns(2)
    manual_lat = colm1.number_input("Latitude", value=0.0, format="%.6f")
    manual_lon = colm2.number_input("Longitude", value=0.0, format="%.6f")

cols = st.columns([1,1,2])
radius = cols[0].slider("Comps radius (miles)", 0.5, 5.0, 2.0, 0.5)
limit  = cols[1].selectbox("Max comps", [10, 15, 20, 25, 30], index=2)
show_debug = cols[2].checkbox("Show Debug Panel", value=False)

go = st.button("Run Analysis", type="primary")

debug_notes = []

if go:
    # Geocode / URL handling
    if use_manual and (manual_lat != 0.0 or manual_lon != 0.0):
        lat, lon, disp = manual_lat, manual_lon, addr_or_url or f"{manual_lat}, {manual_lon}"
    else:
        with st.spinner("Resolving location…"):
            lat, lon, disp = resolve_to_latlon(addr_or_url, debug_notes)

    if not lat or not lon:
        st.error("Could not resolve this location from Realtor/OSM (and optional Google). Try full USPS format or manual lat/lon.")
        if show_debug:
            st.subheader("Debug Panel"); st.json(debug_notes)
        st.stop()

    # Fetch comps
    with st.spinner("Fetching comps…"):
        comps = fetch_nearby_values(lat, lon, radius_miles=radius, limit=limit, debug=debug_notes)

    if not comps:
        st.warning("No comps returned automatically. Enter a few comps manually to generate a report.")
        with st.expander("Enter comps manually (Address, Price, DOM, SqFt)"):
            comp_rows = st.data_editor(
                pd.DataFrame([{"Address":"", "Price":"", "DOM":"", "SqFt":""} for _ in range(5)]),
                num_rows="dynamic",
                use_container_width=True
            )
            if st.button("Use Manual Comps"):
                comps = []
                for _, row in comp_rows.iterrows():
                    addr = str(row.get("Address") or "").strip()
                    if not addr: continue
                    # parse numerics safely
                    def to_float(x):
                        try: return float(str(x).replace(",", "").strip())
                        except: return None
                    def to_int(x):
                        try: return int(str(x).strip())
                        except: return None
                    comps.append({
                        "address": addr,
                        "price": to_float(row.get("Price")),
                        "dom": to_int(row.get("DOM")),
                        "sqft": to_int(row.get("SqFt"))
                    })
        if not comps:
            if show_debug:
                st.subheader("Debug Panel"); st.json(debug_notes)
            st.stop()

    # Subject proxy & risk
    subject = subject_from_comps(comps)
    subject_price, subject_dom = subject["price"], subject["dom"]
    comp_prices = [c["price"] for c in comps if c["price"]]
    comp_doms   = [c["dom"] for c in comps if c["dom"]]

    band, score, prob60, reasons = classify_risk(subject_price, subject_dom, comp_prices, comp_doms)
    suggestions = suggestions_for(band)

    # Summary
    st.markdown(f"**Resolved Location:** {disp or addr_or_url}")
    badge_color = {"Low":"#c7f5d4","Moderate":"#FFEAA7","High":"#f8c2c2"}.get(band,"#e1e7ef")
    st.markdown(
        f"<div style='display:inline-block;padding:6px 12px;border-radius:999px;background:{badge_color};"
        f"border:1px solid rgba(0,0,0,.1);font-weight:600;'>Risk: {band}</div> &nbsp;"
        f"**Probability (60 days): {prob60}%**",
        unsafe_allow_html=True,
    )

    # Details
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Subject (derived)")
        st.write(f"**Subject Price (proxy):** {fmt_money(subject_price)}")
        st.write(f"**Subject DOM (proxy):** {subject_dom if subject_dom is not None else '—'}")
        if comp_prices: st.write(f"**Comp Median Price:** {fmt_money(safe_median(comp_prices))}")
        if comp_doms:   st.write(f"**Comp Median DOM:** {int(safe_median(comp_doms))}")
    with c2:
        st.subheader("Reasoning")
        for r in reasons: st.write("• " + r)

    st.subheader("Comparable Properties")
    df = pd.DataFrame([{
        "Address": abbreviate(c["address"], 42),
        "Price": fmt_money(c["price"]),
        "DOM": c["dom"] if c["dom"] else "—",
        "SqFt": c["sqft"] if c["sqft"] else "—",
    } for c in comps])
    st.dataframe(df, use_container_width=True, height=min(500, 42 + 28*len(df)), hide_index=True)

    st.subheader("Visuals")
    labels = [abbreviate(c["address"], 18) for c in comps[:12]]
    values_price = [c["price"] if c["price"] else 0 for c in comps[:12]]

    # Price chart
    fig1, ax1 = plt.subplots(figsize=(8, 4))
    ax1.bar(labels, values_price, label="Comparable Properties")
    if subject_price: ax1.axhline(subject_price, color="#e07a5f", linestyle="--", linewidth=2, label="Subject (proxy)")
    ax1.set_title("Pricing vs Nearby Values (subject proxy dashed)"); ax1.set_ylabel("Price ($)")
    ax1.legend(loc="upper right"); plt.xticks(rotation=20, ha="right")
    st.pyplot(fig1)

    # DOM chart
    comp_doms_trim = [c["dom"] if c["dom"] else 0 for c in comps[:12]]
    if any(comp_doms_trim):
        fig2, ax2 = plt.subplots(figsize=(8, 4))
        ax2.bar(labels, comp_doms_trim, label="Comparable Properties")
        if subject_dom: ax2.axhline(subject_dom, color="#e07a5f", linestyle="--", linewidth=2, label="Subject (proxy)")
        ax2.set_title("Days on Market vs Comps"); ax2.set_ylabel("Days")
        ax2.legend(loc="upper right"); plt.xticks(rotation=20, ha="right")
        st.pyplot(fig2)

    st.subheader("Contingency Contract Suggestions")
    for s in suggestions: st.write("• " + s)

    # PDF
    st.divider()
    report = {
        "subject_address": disp or addr_or_url,
        "subject_price": subject_price,
        "subject_dom": subject_dom,
        "risk_band": band,
        "probability_60d": prob60,
        "reasons": reasons,
        "suggestions": suggestions,
        "comps": comps,
    }
    pdf_bytes = build_pdf(report)
    st.download_button("📄 Download PDF Report", data=pdf_bytes, file_name="risk_analysis_report.pdf", mime="application/pdf")

    if show_debug:
        st.subheader("Debug Panel")
        st.json(debug_notes)










import os, io, re, math, json
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
# Secrets (two Realtor APIs)
# =========================
api_secrets = st.secrets.get("realtor_api", {})
API_KEY = api_secrets.get("key")
HOST_SEARCH = api_secrets.get("host_search", "realtor-search.p.rapidapi.com")
HOST_APIDOJO = api_secrets.get("host_apidojo", "realtor-com-real-estate.p.rapidapi.com")

if not API_KEY:
    st.error(
        "❌ API key missing. In **Settings → Secrets**, add:\n\n"
        "```toml\n[realtor_api]\nkey = \"YOUR_RAPIDAPI_KEY\"\n"
        "host_search = \"realtor-search.p.rapidapi.com\"\n"
        "host_apidojo = \"realtor-com-real-estate.p.rapidapi.com\"\n```"
    )
    st.stop()

def h_search():   # headers for 'realtor-search'
    return {"x-rapidapi-key": API_KEY, "x-rapidapi-host": HOST_SEARCH}

def h_apidojo():  # headers for Apidojo 'realtor-com-real-estate'
    return {"x-rapidapi-key": API_KEY, "x-rapidapi-host": HOST_APIDOJO}

LOGO_PATH = "logo.png"  # optional

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

def normalize_address(addr):
    if not addr: return ""
    a = addr.strip()
    for token in [" Apt ", " Unit ", " Ste ", " Suite ", "#"]:
        a = a.replace(token, " ")
    return " ".join(a.split())

def is_url(s: str) -> bool:
    return s.lower().startswith("http://") or s.lower().startswith("https://")

def parse_realtor_url(url: str):
    """
    Try to pull a displayable address and an optional property_id from typical Realtor URLs.
    Examples:
      https://www.realtor.com/realestateandhomes-detail/121-Hidden-Creek-Loop_Weatherford_TX_76087_M12345-67890
    Return (address_string or None, property_id or None)
    """
    try:
        path = re.sub(r"https?://[^/]+", "", url)  # strip domain
        # Replace separators with spaces
        clean = path.replace("-", " ").replace("_", " ").strip("/")
        # Try to grab the trailing 'M######-######' pattern (Apidojo style)
        m = re.search(r"M(\d+)-(\d+)", path)
        property_id = None
        if m:
            property_id = f"M{m.group(1)}-{m.group(2)}"

        # Heuristic to reconstruct address-ish text from path segments
        # We'll pull the part after 'detail/' if present
        m2 = re.search(r"realestateandhomes-detail/([^/]+)", path)
        addr_part = m2.group(1) if m2 else None
        if addr_part:
            addr_part = addr_part.replace("-", " ").replace("_", " ")
            # Often contains "Street City State Zip ..." — we’ll return it as-is
            return addr_part, property_id

        # fallback: try splitting path segments
        segs = [s for s in clean.split("/") if s]
        guess = " ".join(segs[-3:]) if segs else None
        return guess, property_id
    except Exception:
        return None, None

# =========================
# Geocoding
# =========================
def resolve_latlon_realtor(addr, debug):
    url = f"https://{HOST_SEARCH}/properties/auto-complete"
    r = requests.get(url, headers=h_search(), params={"input": addr}, timeout=20)
    debug.append(("SEARCH auto-complete", r.status_code, r.text[:800]))
    if r.status_code != 200: return None, None, None
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
    params = {"q": addr, "format": "json", "limit": 1, "addressdetails": 1}
    headers_nom = {"User-Agent": "contingent-risk-app/1.0 (contact: you@example.com)"}
    r = requests.get(url, params=params, headers=headers_nom, timeout=20)
    debug.append(("OSM nominatim", r.status_code, r.text[:800]))
    if r.status_code != 200: return None, None, None
    data = r.json()
    if not data: return None, None, None
    lat = float(data[0]["lat"]); lon = float(data[0]["lon"])
    disp = data[0].get("display_name", addr)
    return lat, lon, disp

def resolve_to_latlon(address_or_url, debug):
    """
    Accepts either an address or a Realtor listing URL.
    If URL:
      - parse address & property_id
      - try Apidojo detail by property_id for exact coords
      - else geocode parsed address (Realtor → OSM)
    If address: geocode as usual.
    """
    if is_url(address_or_url):
        parsed_addr, prop_id = parse_realtor_url(address_or_url)
        parsed_addr = normalize_address(parsed_addr or "")
        # 1) Try detail by property_id (Apidojo)
        if prop_id:
            try:
                url = f"https://{HOST_APIDOJO}/properties/v2/detail"
                r = requests.get(url, headers=h_apidojo(), params={"property_id": prop_id}, timeout=20)
                debug.append(("APIDOJO detail", r.status_code, r.text[:800]))
                if r.status_code == 200:
                    js = r.json()
                    p = js.get("properties", [{}])[0] if isinstance(js.get("properties"), list) else js.get("property") or js
                    a = p.get("address", {}) if isinstance(p.get("address"), dict) else {}
                    lat = a.get("lat") or p.get("lat")
                    lon = a.get("lon") or p.get("lon")
                    disp = (a.get("line") or "") + (", " + a.get("city") if a.get("city") else "")
                    if lat and lon:
                        return float(lat), float(lon), disp or parsed_addr
            except Exception as e:
                debug.append(("APIDOJO detail exception", 0, str(e)))
        # 2) If no property coords, geocode parsed address
        if parsed_addr:
            lat, lon, disp = resolve_latlon_realtor(parsed_addr, debug)
            if lat and lon: return lat, lon, disp
            return resolve_latlon_osm(parsed_addr, debug)
        return None, None, None

    # Not a URL: regular address
    addr = normalize_address(address_or_url)
    lat, lon, disp = resolve_latlon_realtor(addr, debug)
    if lat and lon: return lat, lon, disp
    return resolve_latlon_osm(addr, debug)

# =========================
# Comps fetchers
# =========================
def comps_nearby_home_values(lat, lon, radius, limit, debug):
    """realtor-search: /properties/nearby-home-values"""
    try:
        url = f"https://{HOST_SEARCH}/properties/nearby-home-values"
        params = {"lat": str(lat), "lon": str(lon), "radius": str(radius)}
        r = requests.get(url, headers=h_search(), params=params, timeout=25)
        debug.append(("SEARCH nearby-home-values", r.status_code, r.text[:800]))
        if r.status_code != 200: return []
        js = r.json()
        raw = js.get("data") or js.get("results") or js.get("homes") or js.get("listings") or js.get("properties") or []
        out = []
        for it in raw[:limit]:
            price = it.get("price") or it.get("list_price") or it.get("value") or it.get("estimate") or it.get("avm", {}).get("value")
            dom = it.get("days_on_market") or it.get("dom")
            sqft = (it.get("building_size", {}).get("size") or it.get("sqft") or it.get("living_area"))
            line = (it.get("address", {}).get("line") or it.get("address_line") or it.get("line") or "")
            city = it.get("address", {}).get("city") or it.get("city") or ""
            addr = ", ".join([p for p in [line, city] if p]) or it.get("address") or ""
            if addr:
                out.append({"address": addr, "price": float(price) if price else None, "dom": int(dom) if dom else None, "sqft": int(sqft) if sqft else None})
        return out
    except Exception as e:
        debug.append(("SEARCH nearby-home-values exception", 0, str(e)))
        return []

def comps_apidojo_list_for_sale(lat, lon, radius, limit, debug):
    """apidojo: /properties/v2/list-for-sale with lat/lon"""
    try:
        url = f"https://{HOST_APIDOJO}/properties/v2/list-for-sale"
        params = {"lat": lat, "lon": lon, "radius": radius, "sort": "relevance", "limit": limit}
        r = requests.get(url, headers=h_apidojo(), params=params, timeout=25)
        debug.append(("APIDOJO list-for-sale", r.status_code, r.text[:800]))
        if r.status_code != 200: return []
        js = r.json()
        props = js.get("properties") or []
        out = []
        for p in props[:limit]:
            price = p.get("price")
            dom = p.get("days_on_market") or p.get("dom")
            sqft = (p.get("building_size", {}) or {}).get("size") if isinstance(p.get("building_size"), dict) else p.get("building_size")
            a = p.get("address", {}) if isinstance(p.get("address"), dict) else {}
            line = a.get("line") or ""
            city = a.get("city") or ""
            addr = ", ".join([t for t in [line, city] if t]) or line or city
            if addr:
                out.append({"address": addr, "price": float(price) if price else None, "dom": int(dom) if dom else None, "sqft": int(sqft) if sqft else None})
        return out
    except Exception as e:
        debug.append(("APIDOJO list-for-sale exception", 0, str(e)))
        return []

def fetch_comps(lat, lon, radius, limit, debug):
    comps = comps_nearby_home_values(lat, lon, radius, limit, debug)
    if comps: return comps
    comps = comps_apidojo_list_for_sale(lat, lon, radius, limit, debug)
    return comps

# =========================
# Risk & subject proxy
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

    price_pen = 5.0 if price_diff is None else max(0.0, min(10.0, (price_diff / 25.0) * 10.0))
    dom_pen   = 3.0 if dom_diff is None else max(0.0, min(10.0, (dom_diff / 150.0) * 10.0))
    score = 0.7 * price_pen + 0.3 * dom_pen

    band = "Low" if score < 3 else "Moderate" if score < 6 else "High"
    prob60 = int(round(1 / (1 + math.exp(0.55 * (score - 5))) * 100))
    reasons.append(f"Composite score **{score:.1f}/10** → {band}.")
    reasons.append(f"Estimated **{prob60}%** probability to sell within 60 days.")
    return band, round(score,1), prob60, reasons

def suggestions_for(band):
    if band == "Low": return ["Standard contingency; 30-day listing deadline.", "Minor concessions if no offer by Day 21."]
    if band == "Moderate": return ["Staging + pro photos; weekly agent feedback.", "Auto price cuts 1% at Day 21 and Day 35 if no offers."]
    if band == "High": return ["Aggressive pricing at/under comp median; refresh marketing weekly.", "Builder may extend close or convert to non-contingent if not under contract by Day 60."]
    return ["Insufficient data — require tight listing + adjustment plan."]

# =========================
# Charts
# =========================
def bar_chart_with_subject(subject, values, labels, title, ylabel, color="#5fa8d3"):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(labels, values, color=color, label="Comparable Properties")
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
st.title("🏡 Contingent Property Risk Analysis — Address or Realtor URL")
st.caption("Paste a full Realtor.com URL *or* type an address. We’ll parse → geocode → pull comps → risk it.")

addr_or_url = st.text_input("Enter Address or Realtor.com URL", placeholder="e.g., https://www.realtor.com/realestateandhomes-detail/...")
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
        st.error("Could not resolve this location from Realtor or fallback geocoder. Try city/state/ZIP, or use manual lat/lon.")
        if show_debug:
            st.subheader("Debug Panel"); st.json(debug_notes)
        st.stop()

    # Fetch comps with dual-API fallback
    with st.spinner("Fetching comps…"):
        comps = fetch_comps(lat, lon, radius, limit, debug_notes)

    if not comps:
        st.warning("No comps returned by either API for this area/radius. Try widening the radius or verify your API subscriptions.")
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
    c1, c2 = st








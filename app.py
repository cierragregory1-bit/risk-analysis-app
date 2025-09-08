import os
import io
import math
from datetime import datetime

import streamlit as st
import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from fpdf import FPDF
from PIL import Image

# =========================
# Streamlit / Page settings
# =========================
st.set_page_config(
    page_title="Contingent Property Risk Analysis",
    page_icon="🏡",
    layout="wide"
)

# =========================
# Secrets (Realtor on RapidAPI)
# =========================
API_KEY = st.secrets.get("realtor_api", {}).get("key")
API_HOST = st.secrets.get("realtor_api", {}).get("host", "realtor-search.p.rapidapi.com")

if not API_KEY:
    st.error(
        "❌ API key not found. In **Settings → Secrets**, add:\n\n"
        "```toml\n[realtor_api]\nkey = \"YOUR_RAPIDAPI_KEY\"\nhost = \"realtor-search.p.rapidapi.com\"\n```"
    )
    st.stop()

def realtor_headers():
    return {
        "x-rapidapi-key": API_KEY,
        "x-rapidapi-host": API_HOST
    }

LOGO_PATH = "logo.png"  # optional; put a file named logo.png next to app.py

# =========================
# Helper functions
# =========================
def fmt_money(x):
    try:
        return "${:,.0f}".format(float(x))
    except Exception:
        return "—"

def safe_median(vals):
    clean = [v for v in vals if v is not None and not (isinstance(v, float) and np.isnan(v))]
    return float(np.median(clean)) if clean else None

def abbreviate(s, n=24):
    if not s:
        return ""
    return s if len(s) <= n else s[: n - 1] + "…"

def load_logo():
    try:
        return Image.open(LOGO_PATH)
    except Exception:
        return None

def normalize_address(addr: str) -> str:
    """Light cleanup so geocoders have a better chance."""
    if not addr:
        return addr
    a = addr.strip()
    for token in [" Apt ", " Unit ", " Ste ", " Suite ", "#"]:
        a = a.replace(token, " ")
    a = " ".join(a.split())
    return a

# =========================
# Geocoding
# =========================
def resolve_to_latlon(address: str):
    """
    Try Realtor auto-complete first.
    If that fails, fall back to OpenStreetMap (Nominatim).
    Return (lat, lon, display_address) or (None, None, None).
    """
    addr = normalize_address(address)

    # --- 1) Realtor auto-complete ---
    try:
        url = f"https://{API_HOST}/properties/auto-complete"
        r = requests.get(url, headers=realtor_headers(), params={"input": addr}, timeout=20)
        if r.status_code == 200:
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
    except Exception:
        pass  # ignore, try fallback

    # --- 2) Fallback: OpenStreetMap Nominatim ---
    try:
        nom_url = "https://nominatim.openstreetmap.org/search"
        params = {"q": addr, "format": "json", "limit": 1, "addressdetails": 1}
        headers_nom = {"User-Agent": "contingent-risk-app/1.0 (contact: you@example.com)"}
        r2 = requests.get(nom_url, params=params, headers=headers_nom, timeout=20)
        if r2.status_code == 200:
            data = r2.json()
            if data:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                disp = data[0].get("display_name", addr)
                return lat, lon, disp
    except Exception:
        pass

    return None, None, None

# =========================
# Realtor: comps/nearby values
# =========================
def fetch_nearby_values(lat, lon, radius_miles=2.0, limit=25):
    """
    Calls /properties/nearby-home-values and attempts to normalize output.
    Returns a list of dicts: {address, price, dom, sqft}
    """
    try:
        url = f"https://{API_HOST}/properties/nearby-home-values"
        params = {"lat": str(lat), "lon": str(lon), "radius": str(radius_miles)}
        r = requests.get(url, headers=realtor_headers(), params=params, timeout=25)
        if r.status_code != 200:
            return []
        js = r.json()
        raw = (
            js.get("data")
            or js.get("results")
            or js.get("homes")
            or js.get("listings")
            or js.get("properties")
            or []
        )
        comps = []
        for it in raw[:limit]:
            price = (
                it.get("price")
                or it.get("list_price")
                or it.get("value")
                or it.get("estimate")
                or it.get("avm", {}).get("value")
            )
            dom = it.get("days_on_market") or it.get("dom")
            sqft = (
                it.get("building_size", {}).get("size")
                or it.get("sqft")
                or it.get("living_area")
            )
            line = (
                it.get("address", {}).get("line")
                or it.get("address_line")
                or it.get("line")
                or ""
            )
            city = it.get("address", {}).get("city") or it.get("city") or ""
            addr = ", ".join([p for p in [line, city] if p]) or it.get("address") or ""
            if not addr:
                continue
            comps.append(
                {
                    "address": addr,
                    "price": float(price) if price else None,
                    "dom": int(dom) if dom else None,
                    "sqft": int(sqft) if sqft else None,
                }
            )
        return comps
    except Exception:
        return []

# =========================
# Subject proxy & Risk
# =========================
def subject_from_comps(comps):
    prices = [c["price"] for c in comps if c["price"]]
    doms = [c["dom"] for c in comps if c["dom"]]
    return {
        "price": safe_median(prices),
        "dom": int(round(safe_median(doms))) if doms else None,
    }

def classify_risk(subject_price, subject_dom, comp_prices, comp_doms):
    reasons = []
    if not comp_prices:
        return "Unavailable", None, None, ["No comparable properties found."]

    c_price = safe_median(comp_prices)
    c_dom = safe_median(comp_doms) if comp_doms else None

    price_diff = None
    if subject_price and c_price:
        price_diff = (subject_price - c_price) / c_price * 100
        reasons.append(
            f"Subject vs comps: {fmt_money(subject_price)} vs {fmt_money(c_price)} ({price_diff:+.1f}%)."
        )
    else:
        reasons.append("Using comp medians as subject proxy (insufficient subject price).")

    dom_diff = None
    if subject_dom is not None and c_dom:
        dom_diff = (subject_dom - c_dom) / c_dom * 100
        reasons.append(
            f"Subject DOM vs comps: {subject_dom} vs {int(c_dom)} ({dom_diff:+.0f}%)."
        )

    # Weighted score (0=best 10=worst)
    price_pen = 5.0 if price_diff is None else max(0.0, min(10.0, (price_diff / 25.0) * 10.0))
    dom_pen = 3.0 if dom_diff is None else max(0.0, min(10.0, (dom_diff / 150.0) * 10.0))
    score = 0.7 * price_pen + 0.3 * dom_pen

    band = "Low" if score < 3 else "Moderate" if score < 6 else "High"
    prob60 = int(round(1 / (1 + math.exp(0.55 * (score - 5))) * 100))
    reasons.append(f"Composite score **{score:.1f}/10** → {band}.")
    reasons.append(f"Estimated **{prob60}%** probability to sell within 60 days.")
    return band, round(score, 1), prob60, reasons

def suggestions_for(band):
    if band == "Low":
        return [
            "Standard contingency terms; 30-day listing deadline.",
            "Minor concessions only if no offer by Day 21.",
        ]
    if band == "Moderate":
        return [
            "Staging + pro photos; weekly agent feedback.",
            "Auto price cuts 1% at Day 21 and Day 35 if no offers.",
        ]
    if band == "High":
        return [
            "Aggressive pricing at/under comp median; refresh marketing weekly.",
            "Builder may extend close or convert to non-contingent if not under contract by Day 60.",
        ]
    return ["Insufficient data — require tight listing + adjustment plan."]

# =========================
# Charts
# =========================
def bar_chart_with_subject(subject, values, labels, title, ylabel, color="#5fa8d3"):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(labels, values, color=color, label="Comparable Properties")
    if subject:
        ax.axhline(subject, color="#e07a5f", linestyle="--", linewidth=2, label="Subject (proxy)")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.legend(loc="upper right")
    plt.xticks(rotation=20, ha="right")
    st.pyplot(fig)

# =========================
# PDF builder
# =========================
def build_pdf(report):
    pdf = FPDF()
    pdf.add_page()

    logo = load_logo()
    if logo:
        tmp = "tmp_logo.png"
        logo.save(tmp)
        pdf.image(tmp, x=10, y=10, w=18)
        os.remove(tmp)

    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Contingent Property Risk Analysis", ln=True, align="C")
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align="C")
    pdf.ln(4)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Subject (derived from comps):", ln=True)
    pdf.set_font("Arial", "", 11)
    pdf.multi_cell(0, 6, f"Address: {report['subject_address']}")
    pdf.cell(0, 6, f"Subject Price (proxy): {fmt_money(report['subject_price'])}", ln=True)
    pdf.cell(0, 6, f"Subject DOM (proxy): {report['subject_dom'] if report['subject_dom'] is not None else '—'}", ln=True)
    pdf.ln(2)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, f"Risk: {report['risk_band']}  |  Probability (60d): {report['probability_60d']}%", ln=True)
    pdf.set_font("Arial", "", 11)
    for r in report["reasons"]:
        pdf.multi_cell(0, 6, f"- {r}")
    pdf.ln(1)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Contingency Suggestions:", ln=True)
    pdf.set_font("Arial", "", 11)
    for s in report["suggestions"]:
        pdf.multi_cell(0, 6, f"- {s}")
    pdf.ln(1)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Comparable Properties:", ln=True)
    pdf.set_font("Arial", "", 11)
    for c in report["comps"][:12]:
        line = f"{c['address']} | {fmt_money(c['price'])} | DOM: {c['dom'] if c['dom'] else '—'} | SqFt: {c['sqft'] if c['sqft'] else '—'}"
        pdf.multi_cell(0, 6, line)

    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return buf

# =========================
# UI
# =========================
st.title("🏡 Contingent Property Risk Analysis (Realtor API)")
st.caption("Type an address → we resolve it (Realtor first, then OpenStreetMap fallback) → pull comps → compute risk & probability.")

address = st.text_input(
    "Enter Property Address",
    placeholder="e.g., 121 Hidden Creek Loop, Weatherford, TX"
)

with st.expander("If the address can’t be resolved, enter coordinates manually"):
    use_manual = st.checkbox("Use manual latitude/longitude")
    col_m1, col_m2 = st.columns(2)
    manual_lat = col_m1.number_input("Latitude", value=0.0, format="%.6f")
    manual_lon = col_m2.number_input("Longitude", value=0.0, format="%.6f")

cols_top = st.columns([1, 1, 2])
radius = cols_top[0].slider("Comps search radius (miles)", 0.5, 5.0, 2.0, 0.5)
limit = cols_top[1].selectbox("Max comps", [10, 15, 20, 25, 30], index=2)

go = st.button("Run Analysis", type="primary")

if go:
    # Geocode
    if use_manual and (manual_lat != 0.0 or manual_lon != 0.0):
        lat, lon, display_addr = manual_lat, manual_lon, address or f"{manual_lat}, {manual_lon}"
    else:
        with st.spinner("Resolving address…"):
            lat, lon, display_addr = resolve_to_latlon(address)

    if not lat or not lon:
        st.error(
            "Could not resolve this location from either Realtor or the fallback geocoder.\n\n"
            "Tips: include city/state/ZIP, try a nearby address, or use the manual latitude/longitude input above."
        )
        st.stop()

    # Fetch comps
    with st.spinner("Pulling comps / nearby values…"):
        comps = fetch_nearby_values(lat, lon, radius_miles=radius, limit=limit)

    if not comps:
        st.warning("No comps/nearby values found for this location. Try widening the radius or a nearby address.")
        st.stop()

    # Subject proxy & risk
    subject = subject_from_comps(comps)
    subject_price, subject_dom = subject["price"], subject["dom"]

    comp_prices = [c["price"] for c in comps if c["price"]]
    comp_doms = [c["dom"] for c in comps if c["dom"]]

    band, score, prob60, reasons = classify_risk(subject_price, subject_dom, comp_prices, comp_doms)
    suggestions = suggestions_for(band)

    # Header summary
    st.markdown(f"**Resolved Address:** {display_addr or address}")
    badge_color = {"Low": "#c7f5d4", "Moderate": "#FFEAA7", "High": "#f8c2c2"}.get(band, "#e1e7ef")
    st.markdown(
        f"<div style='display:inline-block;padding:6px 12px;border-radius:999px;background:{badge_color};"
        f"border:1px solid rgba(0,0,0,.1);font-weight:600;'>Risk: {band}</div> &nbsp;"
        f"**Probability (60 days): {prob60}%**",
        unsafe_allow_html=True,
    )

    # Details
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Subject (derived)")
        st.write(f"**Subject Price (proxy):** {fmt_money(subject_price)}")
        st.write(f"**Subject DOM (proxy):** {subject_dom if subject_dom is not None else '—'}")
        if comp_prices:
            st.write(f"**Comp Median Price:** {fmt_money(safe_median(comp_prices))}")
        if comp_doms:
            st.write(f"**Comp Median DOM:** {int(safe_median(comp_doms))}")

    with col2:
        st.subheader("Reasoning")
        for r in reasons:
            st.write("• " + r)

    st.subheader("Comparable Properties")
    df = pd.DataFrame(
        [
            {
                "Address": abbreviate(c["address"], 40),
                "Price": fmt_money(c["price"]),
                "DOM": c["dom"] if c["dom"] else "—",
                "SqFt": c["sqft"] if c["sqft"] else "—",
            }
            for c in comps
        ]
    )
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.subheader("Visuals")
    labels = [abbreviate(c["address"], 18) for c in comps[:12]]
    prices = [c["price"] if c["price"] else 0 for c in comps[:12]]
    bar_chart_with_subject(
        subject_price,
        prices,
        labels,
        "Pricing vs Nearby Values (subject proxy dashed)",
        "Price ($)",
    )

    if comp_doms:
        fig, ax = plt.subplots(figsize=(8, 4))
        dom_vals = [c["dom"] if c["dom"] else 0 for c in comps[:12]]
        ax.bar(labels, dom_vals, color="#9bc53d", label="Comparable Properties")
        if subject_dom:
            ax.axhline(subject_dom, color="#e07a5f", linestyle="--", linewidth=2, label="Subject (proxy)")
        ax.set_title("Days on Market vs Comps")
        ax.set_ylabel("Days")
        ax.legend(loc="upper right")
        plt.xticks(rotation=20, ha="right")
        st.pyplot(fig)

    st.subheader("Contingency Contract Suggestions")
    for s in suggestions:
        st.write("• " + s)

    # PDF download
    st.divider()
    report = {
        "subject_address": display_addr or address,
        "subject_price": subject_price,
        "subject_dom": subject_dom,
        "risk_band": band,
        "probability_60d": prob60,
        "reasons": reasons,
        "suggestions": suggestions,
        "comps": comps,
    }
    pdf_bytes = build_pdf(report)
    st.download_button(
        "📄 Download PDF Report",
        data=pdf_bytes,
        file_name="risk_analysis_report.pdf",
        mime="application/pdf",
    )














# ============================
# Builder Risk Analysis (RentCast)
# fully dressed + PDF export
# ============================

import os
import io
import textwrap
import requests
import math
import statistics as stats
from datetime import datetime

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from fpdf import FPDF

# -----------------------------
# Config & Theme
# -----------------------------
st.set_page_config(
    page_title="Builder Risk Analysis",
    page_icon="🏠",
    layout="wide",
)

# Classy CSS
st.markdown(
    """
    <style>
      .main { padding: 1.8rem 2rem; }
      .metric-card {
        border-radius: 16px; padding: 18px 22px;
        background: #101319; border: 1px solid #2a2f3a;
      }
      .risk-card {
        border-radius: 18px; padding: 18px 24px; border: 1px solid #2a2f3a;
        background: linear-gradient(180deg, #111623 0%, #0E131C 100%);
      }
      .risk-badge {
        display:inline-block; padding: 6px 12px; border-radius: 999px; font-weight: 600;
        background: #FFEAA7; color: #1b1f2a; border: 1px solid #ccb56c;
      }
      .caption { color: #9aa3b2; font-size: 0.9rem; }
      .tight { margin-top:-10px; }
      .footer-note { color:#8d96a6; font-size:0.85rem; }
      .stDownloadButton { border-radius: 12px !important; }
      h1,h2,h3 { letter-spacing: 0.2px; }
    </style>
    """,
    unsafe_allow_html=True
)

# -----------------------------
# Secrets & API keys
# -----------------------------
def get_api_key():
    # Priority: secrets -> env var -> sidebar input
    key = None
    try:
        key = st.secrets.get("RENTCAST_API_KEY", None)
    except Exception:
        key = None
    if not key:
        key = os.environ.get("RENTCAST_API_KEY", None)
    return key

# Allow pasting once if not set
with st.sidebar:
    st.header("🔐 API")
    api_key = get_api_key()
    if not api_key:
        api_key_input = st.text_input("RentCast API Key", type="password")
        if api_key_input:
            api_key = api_key_input
    st.caption("Tip: store it in `.streamlit/secrets.toml` as `RENTCAST_API_KEY`.")

# -----------------------------
# Assets (logo)
# -----------------------------
LOGO_PATH = "logo.png"  # place your provided logo file as logo.png next to app.py

def load_logo():
    try:
        return Image.open(LOGO_PATH)
    except Exception:
        return None

# -----------------------------
# Helpers
# -----------------------------
def abbreviate_address(addr: str, max_len: int = 28) -> str:
    """Abbreviate long addresses to avoid chart overlap."""
    if not addr:
        return ""
    # common street suffixes
    repl = {
        " Road": " Rd", " Street": " St", " Avenue": " Ave", " Boulevard": " Blvd",
        " Drive": " Dr", " Court": " Ct", " Lane": " Ln", " Trail": " Trl",
        " Parkway": " Pkwy", " Place": " Pl", " Highway": " Hwy",
        " North": " N", " South": " S", " East": " E", " West": " W"
    }
    for k, v in repl.items():
        addr = addr.replace(k, v)
    if len(addr) <= max_len:
        return addr
    # try to keep city/state/zip visible
    parts = addr.split(",")
    if len(parts) >= 2:
        left = parts[0].strip()
        right = ", ".join([p.strip() for p in parts[1:]])
        left = (left[:max_len-3] + "…") if len(left) > max_len else left
        return f"{left}, {right}"
    return addr[:max_len-1] + "…"

def fmt_money(x):
    try:
        return "${:,.0f}".format(float(x))
    except Exception:
        return "—"

def safe_median(values):
    vals = [v for v in values if v is not None and not math.isnan(v)]
    if not vals:
        return None
    return float(np.median(vals))

# -----------------------------
# RentCast fetchers
# -----------------------------
RENTCAST_BASE = "https://api.rentcast.io/v1"
HEADERS = lambda key: {"accept": "application/json", "X-Api-Key": key}

def rc_resolve_address(address: str, key: str):
    """Resolve an address to lat/lon via RentCast."""
    try:
        r = requests.get(
            f"{RENTCAST_BASE}/addresses/resolve",
            params={"address": address},
            headers=HEADERS(key),
            timeout=20,
        )
        if r.status_code == 200:
            data = r.json()
            # expected keys: latitude, longitude, addressLine1, city, state, zipCode
            return data
    except Exception:
        pass
    return None

def rc_for_sale(lat, lon, radius_miles, key, limit=12):
    """Nearby for-sale listings."""
    try:
        r = requests.get(
            f"{RENTCAST_BASE}/listings/for-sale",
            params={
                "latitude": lat,
                "longitude": lon,
                "radius": radius_miles,
                "status": "Active",
                "sort": "distance",
                "limit": limit,
            },
            headers=HEADERS(key),
            timeout=25,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []

def rc_recent_sales(lat, lon, radius_miles, key, limit=12):
    """Nearby recent sales (for stronger comps if available)."""
    try:
        r = requests.get(
            f"{RENTCAST_BASE}/sales",
            params={
                "latitude": lat,
                "longitude": lon,
                "radius": radius_miles,
                "sort": "distance",
                "limit": limit,
            },
            headers=HEADERS(key),
            timeout=25,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []

def extract_subject(listings, target_address: str):
    """Find subject listing inside results if RentCast returns it (best effort)."""
    t = (target_address or "").lower().replace("#", "")
    for x in listings or []:
        addr = x.get("formattedAddress") or x.get("address")
        if not addr:
            continue
        a = addr.lower().replace("#", "")
        if t and t in a:
            return x
    return None

def normalize_listing(x):
    """Normalize RentCast listing/sale dict into a consistent structure."""
    addr = x.get("formattedAddress") or x.get("address") or ""
    price = (
        x.get("listPrice")
        or x.get("price")
        or x.get("lastSalePrice")
        or x.get("closingPrice")
        or None
    )
    dom = x.get("daysOnMarket") or x.get("dom") or None
    sqft = x.get("squareFootage") or x.get("livingArea") or x.get("sqft") or None
    year = x.get("yearBuilt") or None
    lat = x.get("latitude") or None
    lon = x.get("longitude") or None
    return {
        "address": addr,
        "price": float(price) if price else None,
        "dom": int(dom) if dom else None,
        "sqft": int(sqft) if sqft else None,
        "year": int(year) if year else None,
        "lat": lat, "lon": lon,
    }

def gather_comps(lat, lon, key, progressive_radii=(0.5, 1, 2, 3), want=6):
    """Progressive radius: try sold first, then active, up to N comps."""
    comps = []
    tried = []
    for r in progressive_radii:
        # recent sales (strongest comps)
        sales = rc_recent_sales(lat, lon, r, key, limit=25)
        tried.append(("sales", r, len(sales)))
        for s in sales:
            comps.append(normalize_listing(s))
        if len([c for c in comps if c["price"]]) >= want:
            break

        # active listings (if we still need)
        active = rc_for_sale(lat, lon, r, key, limit=25)
        tried.append(("for-sale", r, len(active)))
        for a in active:
            comps.append(normalize_listing(a))
        if len([c for c in comps if c["price"]]) >= want:
            break

    # Deduplicate by address
    seen = set()
    deduped = []
    for c in comps:
        k = (c["address"] or "").lower()
        if k and k not in seen:
            seen.add(k)
            deduped.append(c)
    return deduped[: max(want, 6)], tried

# -----------------------------
# Risk Model
# -----------------------------
def classify_risk(subject_price, subject_dom, comp_prices, comp_doms):
    """
    Returns:
      risk_band: str
      score: float 0-10 (10 = very risky)
      probability_60d: int %
      reasoning: str
    """
    reasons = []

    # if no comp prices -> unavailable
    if not comp_prices:
        return "Unavailable", None, None, "No comparable properties found."

    avg_price = safe_median(comp_prices)
    avg_dom = safe_median(comp_doms) if comp_doms else None

    price_diff_pct = None
    if subject_price and avg_price:
        price_diff_pct = (subject_price - avg_price) / avg_price * 100
        reasons.append(f"Subject price vs comps: {fmt_money(subject_price)} vs median {fmt_money(avg_price)} ({price_diff_pct:+.1f}%).")
    else:
        reasons.append("Insufficient price data to determine pricing gap.")

    dom_diff_pct = None
    if subject_dom is not None and avg_dom:
        dom_diff_pct = (subject_dom - avg_dom) / avg_dom * 100
        reasons.append(f"Subject DOM vs comps: {subject_dom} vs median {int(avg_dom)} days ({dom_diff_pct:+.0f}%).")
    elif subject_dom is not None:
        reasons.append(f"Subject DOM provided: {subject_dom} days (insufficient comp DOMs).")

    # Simple buyer pool heuristic (price tiers)
    buyer_pool = "Broad"
    if subject_price:
        if subject_price >= 900_000:
            buyer_pool = "Very Narrow"
        elif subject_price >= 700_000:
            buyer_pool = "Narrow"
        elif subject_price >= 500_000:
            buyer_pool = "Moderate"
        else:
            buyer_pool = "Broad"
        reasons.append(f"Buyer pool heuristic for price point: **{buyer_pool}**.")

    # Weighted score
    score = 0.0
    w_price = 0.55
    w_dom = 0.25
    w_pool = 0.20

    # price penalty ~ 0 if <= 0% over comps, up to ~10 if +25% over
    if price_diff_pct is not None:
        price_penalty = max(0.0, min(10.0, (price_diff_pct / 25.0) * 10.0))
    else:
        price_penalty = 4.0  # unknown pricing: mild risk
    score += w_price * price_penalty

    # DOM penalty ~ 0 if <= comps, up to 10 if +150% over
    if dom_diff_pct is not None:
        dom_penalty = max(0.0, min(10.0, (dom_diff_pct / 150.0) * 10.0))
    else:
        dom_penalty = 2.5
    score += w_dom * dom_penalty

    pool_penalty_map = {"Broad": 1.5, "Moderate": 4.0, "Narrow": 6.5, "Very Narrow": 8.0}
    score += w_pool * pool_penalty_map.get(buyer_pool, 4.0)

    # Banding
    if score < 3.0:
        risk_band = "Low"
    elif score < 6.0:
        risk_band = "Moderate"
    else:
        risk_band = "High"

    # Probability model (rough logistic on score)
    # Lower score -> higher sale probability within 60 days
    p = 1 / (1 + math.exp(0.55 * (score - 5)))  # center at score=5
    probability_60d = int(round(p * 100))

    reasons.append(f"Composite risk score: **{score:.1f}/10** ({risk_band}).")
    reasons.append(f"Estimated probability to sell within 60 days: **{probability_60d}%** (heuristic).")

    return risk_band, round(score, 1), probability_60d, " ".join(reasons)

def contingency_suggestions(risk_band):
    if risk_band == "Low":
        return [
            "List at or very near the median comp value.",
            "Standard buyer incentives only if showing traffic is weak after 2 weeks.",
            "Maintain normal contingency deadlines."
        ]
    if risk_band == "Moderate":
        return [
            "Price within 1–2% of comp median and prepare a 1% scheduled reduction after 21 days if no offers.",
            "Highlight move-in readiness and include light concessions (e.g., closing cost credit or rate buydown).",
            "Shorten buyer response windows to keep momentum."
        ]
    if risk_band == "High":
        return [
            "Start 2–4% below comp median or implement a staged reduction plan (1% every 14 days).",
            "Increase marketing cadence: refreshed media, weekly open houses, agent outreach.",
            "Consider lender buy-down credits and extended rate lock options to expand buyer pool."
        ]
    return ["Insufficient data for recommendations."]

# -----------------------------
# Visualization
# -----------------------------
def chart_pricing(subject_label, subject_price, comps_df):
    fig, ax = plt.subplots(figsize=(9.5, 5))
    labels = [abbreviate_address(a, max_len=26) for a in comps_df["address"]]
    prices = comps_df["price"].to_list()

    # Insert subject first
    labels = [subject_label] + labels
    prices = [subject_price] + prices

    bars = ax.bar(range(len(prices)), prices, alpha=0.95)
    # Color: subject = brand red, comps = blue
    for i, b in enumerate(bars):
        if i == 0:
            b.set_color("#C0392B")
        else:
            b.set_color("#3E7CB1")

    ax.set_title("Pricing vs Comps", fontsize=14)
    ax.set_ylabel("Price ($)")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.grid(axis="y", linestyle="--", alpha=0.3)

    # Value labels (no overlap by placing slightly above bar)
    for idx, (val) in enumerate(zip(prices)):
        v = val[0] if isinstance(val, (list, tuple, np.ndarray, pd.Series)) else val
        if v:  # protect
            ax.text(idx, v + (max(prices) * 0.03), fmt_money(v), ha="center", va="bottom", fontsize=9)

    # Legend
    subj_patch = plt.Rectangle((0,0),1,1,color="#C0392B", label="Subject Property")
    comp_patch = plt.Rectangle((0,0),1,1,color="#3E7CB1", label="Comparable Properties")
    ax.legend(handles=[subj_patch, comp_patch], loc="upper left", frameon=True)
    plt.tight_layout()
    return fig

def chart_dom(subject_label, subject_dom, comps_df):
    if subject_dom is None and comps_df["dom"].dropna().empty:
        return None
    fig, ax = plt.subplots(figsize=(9.5, 5))

    labels = [abbreviate_address(a, max_len=26) for a in comps_df["address"]]
    doms = comps_df["dom"].to_list()

    labels = [subject_label] + labels
    doms = [subject_dom] + doms

    bars = ax.bar(range(len(doms)), doms, alpha=0.95)
    for i, b in enumerate(bars):
        if i == 0:
            b.set_color("#F39C12")
        else:
            b.set_color("#3E7CB1")

    ax.set_title("DOM Pressure", fontsize=14)
    ax.set_ylabel("Days on Market")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.grid













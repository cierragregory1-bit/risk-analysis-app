import streamlit as st
import requests
import matplotlib.pyplot as plt
from fpdf import FPDF
import tempfile
import os

# ==============================
# CONFIG
# ==============================
API_KEY = "92b00e990823456eba2d61ffc2f3f224"
LOGO_PATH = "logo.png"  # <-- put your uploaded logo in the same folder

# ==============================
# RENTCAST API CALL
# ==============================
def get_property_and_comps(address):
    url = "https://api.rentcast.io/v1/properties"
    headers = {"accept": "application/json", "X-Api-Key": API_KEY}
    params = {"address": address}
    res = requests.get(url, headers=headers, params=params)

    if res.status_code != 200:
        return None, None

    data = res.json()
    if not data:
        return None, None

    subject = data[0]

    comps_url = "https://api.rentcast.io/v1/properties/comps"
    comp_params = {"address": address, "limit": 5}
    comps_res = requests.get(comps_url, headers=headers, params=comp_params)
    comps = comps_res.json() if comps_res.status_code == 200 else []

    return subject, comps

# ==============================
# RISK CLASSIFICATION
# ==============================
def classify_risk(price, comp_prices, dom, comp_doms):
    if not comp_prices or not comp_doms:
        return {
            "risk": "Unavailable",
            "color": "gray",
            "reason": "No comparable properties found in RentCast for this location.",
            "probability": "N/A",
            "suggestions": "Try entering another nearby address or broaden the search area."
        }

    avg_price = sum(comp_prices) / len(comp_prices) if comp_prices else 0
    avg_dom = sum(comp_doms) / len(comp_doms) if comp_doms else 0

    if avg_price == 0:
        return {
            "risk": "Unavailable",
            "color": "gray",
            "reason": "Comparable properties returned no valid pricing data.",
            "probability": "N/A",
            "suggestions": "Try another address or check data availability."
        }

    price_diff = abs(price - avg_price) / avg_price
    dom_diff = abs(dom - avg_dom) / avg_dom if avg_dom > 0 else 0

    if price_diff < 0.05 and dom_diff < 0.2:
        return {
            "risk": "Low",
            "color": "#4CAF50",  # green
            "reason": "Price and days on market align closely with comps.",
            "probability": "High (~80%)",
            "suggestions": "Proceed with standard terms. Minor concessions may help accelerate movement."
        }
    elif price_diff < 0.15 and dom_diff < 0.5:
        return {
            "risk": "Moderate",
            "color": "#FFC107",  # yellow
            "reason": "Some deviation in price or days on market compared to comps.",
            "probability": "Medium (~55%)",
            "suggestions": "Consider pricing flexibility and stronger contingencies."
        }
    else:
        return {
            "risk": "High",
            "color": "#F44336",  # red
            "reason": "Significant mismatch between property pricing/DOM and comps.",
            "probability": "Low (~30%)",
            "suggestions": "Recommend contract adjustments, concessions, or price improvements."
        }

# ==============================
# PDF GENERATION
# ==============================
def generate_pdf(subject, comps, analysis, charts):
    pdf = FPDF()
    pdf.add_page()

    if os.path.exists(LOGO_PATH):
        pdf.image(LOGO_PATH, 10, 8, 33)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(200, 10, "Property Risk Analysis Report", ln=True, align="C")

    pdf.set_font("Helvetica", "", 12)
    pdf.cell(200, 10, f"Address: {subject.get('formattedAddress', 'N/A')}", ln=True)
    pdf.cell(200, 10, f"Price: ${subject.get('price', 'N/A')}", ln=True)
    pdf.cell(200, 10, f"Days on Market: {subject.get('daysOnMarket', 'N/A')}", ln=True)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(200, 10, f"Risk Level: {analysis['risk']}", ln=True)
    pdf.set_font("Helvetica", "", 12)
    pdf.multi_cell(0, 10, f"Reason: {analysis['reason']}")
    pdf.multi_cell(0, 10, f"Probability of Sale: {analysis['probability']}")
    pdf.multi_cell(0, 10, f"Suggestions: {analysis['suggestions']}")

    for chart_path in charts:
        pdf.add_page()
        pdf.image(chart_path, x=10, y=20, w=180)

    tmpfile = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(tmpfile.name)
    return tmpfile.name

# ==============================
# STREAMLIT APP
# ==============================
# Custom CSS for branding
st.markdown(
    """
    <style>
        .main {
            background-color: #f9f9f9;
            font-family: 'Helvetica Neue', sans-serif;
        }
        .title {
            font-size: 32px;
            font-weight: bold;
            color: #1E3A8A;
            text-align: center;
            margin-bottom: 10px;
        }
        .subtitle {
            font-size: 18px;
            color: #4B5563;
            text-align: center;
            margin-bottom: 30px;
        }
        .risk-card {
            padding: 15px;
            border-radius: 10px;
            color: white;
            font-weight: bold;
            margin-top: 15px;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# Logo + title
if os.path.exists(LOGO_PATH):
    st.image(LOGO_PATH, width=80)

st.markdown("<div class='title'>🏡 Builder Property Risk Analysis</div>", unsafe_allow_html=True)
st.markdown("<div class='subtitle'>Automated insights powered by RentCast</div>", unsafe_allow_html=True)

address = st.text_input("Enter Property Address")

if st.button("Run Analysis") and address:
    subject, comps = get_property_and_comps(address)

    if not subject:
        st.error("No property data found. Try another address.")
    else:
        subject_price = subject.get("price", 0)
        subject_dom = subject.get("daysOnMarket", 0)
        comp_prices = [c.get("price", 0) for c in comps if c.get("price")]
        comp_doms = [c.get("daysOnMarket", 0) for c in comps if c.get("daysOnMarket")]

        analysis = classify_risk(subject_price, comp_prices, subject_dom, comp_doms)

        # Styled Risk Card
        st.markdown(
            f"<div class='risk-card' style='background-color:{analysis['color']}'>"
            f"Risk Level: {analysis['risk']}</div>",
            unsafe_allow_html=True
        )
        st.write(f"**Reason:** {analysis['reason']}")
        st.write(f"**Probability of Sale in 60 Days:** {analysis['probability']}")
        st.write(f"**Suggestions:** {analysis['suggestions']}")

        # Charts
        charts = []
        if comp_prices:
            fig, ax = plt.subplots()
            labels = ["Subject"] + [c.get("formattedAddress", "Comp")[:20] for c in comps]
            values = [subject_price] + comp_prices
            ax.bar(labels, values, color=["red"] + ["blue"]*len(comp_prices))
            ax.set_title("Pricing vs Comps")
            plt.xticks(rotation=30, ha="right")
            tmpfile = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            plt.savefig(tmpfile.name, bbox_inches="tight")
            charts.append(tmpfile.name)
            st.image(tmpfile.name)

        if comp_doms:
            fig, ax = plt.subplots()
            labels = ["Subject"] + [c.get("formattedAddress", "Comp")[:20] for c in comps]
            values = [subject_dom] + comp_doms
            ax.bar(labels, values, color=["orange"] + ["blue"]*len(comp_doms))
            ax.set_title("Days on Market vs Comps")
            plt.xticks(rotation=30, ha="right")
            tmpfile = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            plt.savefig(tmpfile.name, bbox_inches="tight")
            charts.append(tmpfile.name)
            st.image(tmpfile.name)

        # PDF Export
        pdf_file = generate_pdf(subject, comps, analysis, charts)
        with open(pdf_file, "rb") as f:
            st.download_button("📄 Download PDF Report", f, file_name="RiskAnalysisReport.pdf")











import streamlit as st
import requests
import matplotlib.pyplot as plt
from fpdf import FPDF
import os

# -----------------------
# CONFIG
# -----------------------
RENTCAST_API_KEY = "92b00e990823456eba2d61ffc2f3f224"
HEADERS = {"accept": "application/json", "X-Api-Key": RENTCAST_API_KEY}
LOGO_PATH = "logo.png"  # Make sure to upload your logo into the repo as logo.png

# -----------------------
# FUNCTIONS
# -----------------------
def get_property_data(address):
    url = f"https://api.rentcast.io/v1/properties?address={address}"
    r = requests.get(url, headers=HEADERS)
    if r.status_code == 200 and r.json():
        return r.json()[0]
    return None

def get_comps(address):
    url = f"https://api.rentcast.io/v1/avm/sales?address={address}&radius=1&limit=3"
    r = requests.get(url, headers=HEADERS)
    if r.status_code == 200:
        return r.json().get("comps", [])
    return []

def abbreviate_address(address):
    replacements = {"Street":"St", "Road":"Rd", "Avenue":"Ave", "Boulevard":"Blvd", "Drive":"Dr", "Lane":"Ln"}
    for long, short in replacements.items():
        address = address.replace(long, short)
    return address

def classify_risk(price, comp_prices, dom, comp_doms):
    avg_price = sum(comp_prices) / len(comp_prices) if comp_prices else price
    avg_dom = sum(comp_doms) / len(comp_doms) if comp_doms else dom

    price_diff = abs(price - avg_price) / avg_price
    dom_diff = dom - avg_dom

    if price_diff < 0.05 and dom_diff <= 0:
        risk, color, prob = "Low Risk", "#b7f7a8", 0.85
        reason = "Price aligns with comps and DOM is competitive."
        suggestion = "Proceed confidently. Standard contingencies only."
    elif price_diff < 0.15 and dom_diff <= 30:
        risk, color, prob = "Moderate Risk", "#fff3a3", 0.65
        reason = "Price slightly high or DOM slightly longer than comps."
        suggestion = "Consider inspection/appraisal contingencies. Price adjustment may help."
    else:
        risk, color, prob = "High Risk", "#ffb3b3", 0.40
        reason = "Price significantly above comps or DOM much longer."
        suggestion = "Negotiate aggressively. Add financing/inspection contingencies."

    return {"risk": risk, "color": color, "prob": prob, "reason": reason, "suggestion": suggestion}

def create_pdf(subject, comps, analysis):
    pdf = FPDF()
    pdf.add_page()

    # Add logo at the top
    if os.path.exists(LOGO_PATH):
        pdf.image(LOGO_PATH, 10, 8, 33)  # x, y, width

    # Title
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 15, "Property Risk Analysis Report", ln=True, align="C")
    pdf.ln(10)

    # Subject property
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Subject Property", ln=True)
    pdf.set_font("Helvetica", "", 12)
    pdf.multi_cell(0, 8, f"{subject.get('formattedAddress', 'N/A')}")
    pdf.cell(0, 8, f"List Price: ${subject.get('price', 'N/A'):,}", ln=True)
    pdf.cell(0, 8, f"Days on Market: {subject.get('daysOnMarket', 'N/A')}", ln=True)
    pdf.ln(5)

    # Comps
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Comparable Properties", ln=True)
    pdf.set_font("Helvetica", "", 12)
    for comp in comps:
        pdf.multi_cell(0, 8, f"{comp['formattedAddress']} - ${comp['price']:,} - DOM {comp['daysOnMarket']}")

    pdf.ln(5)

    # Risk Analysis
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Risk Analysis", ln=True)
    pdf.set_font("Helvetica", "", 12)
    pdf.multi_cell(0, 8, f"Classification: {analysis['risk']}")
    pdf.multi_cell(0, 8, f"Probability of Sale in 60 Days: {int(analysis['prob']*100)}%")
    pdf.multi_cell(0, 8, f"Reasoning: {analysis['reason']}")
    pdf.multi_cell(0, 8, f"Suggestions: {analysis['suggestion']}")

    return pdf

# -----------------------
# STREAMLIT APP
# -----------------------
st.title("🏡 Builder Property Risk Analysis (RentCast API)")

address = st.text_input("Enter Property Address")

if st.button("Run Analysis") and address:
    subject = get_property_data(address)
    comps = get_comps(address)

    if not subject:
        st.error("No property data found. Try another address.")
    else:
        subject_price = subject.get("price", 0)
        subject_dom = subject.get("daysOnMarket", 0)
        comp_prices = [c.get("price", 0) for c in comps if c.get("price")]
        comp_doms = [c.get("daysOnMarket", 0) for c in comps if c.get("daysOnMarket")]

        analysis = classify_risk(subject_price, comp_prices, subject_dom, comp_doms)

        # Risk Box
        st.markdown(
            f"<div style='background-color:{analysis['color']};padding:15px;border-radius:10px;'>"
            f"<h3 style='margin:0;'>Risk Classification: {analysis['risk']}</h3>"
            f"<p><b>Probability of Sale (60 days):</b> {int(analysis['prob']*100)}%</p>"
            f"<p><b>Reasoning:</b> {analysis['reason']}</p>"
            f"<p><b>Suggestions:</b> {analysis['suggestion']}</p>"
            "</div>", unsafe_allow_html=True
        )

        # Charts
        if comps:
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))

            prices = [subject_price] + comp_prices
            labels = ["Subject"] + [abbreviate_address(c["formattedAddress"]) for c in comps]
            axes[0].bar(labels, prices, color=["red"] + ["blue"]*len(comp_prices))
            axes[0].set_title("Pricing vs Comps")
            axes[0].set_ylabel("Price ($)")
            axes[0].tick_params(axis='x', rotation=30)

            doms = [subject_dom] + comp_doms
            axes[1].bar(labels, doms, color=["orange"] + ["blue"]*len(comp_doms))
            axes[1].set_title("Days on Market vs Comps")
            axes[1].set_ylabel("Days")
            axes[1].tick_params(axis='x', rotation=30)

            st.pyplot(fig)

        # PDF Export
        pdf = create_pdf(subject, comps, analysis)
        pdf_output = "report.pdf"
        pdf.output(pdf_output)
        with open(pdf_output, "rb") as f:
            st.download_button("📄 Download Full Report", f, file_name="Risk_Analysis_Report.pdf", mime="application/pdf")









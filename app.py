import streamlit as st
import matplotlib.pyplot as plt
from fpdf import FPDF
import tempfile
import os

# --- App Config ---
st.set_page_config(page_title="Builder Property Risk Analysis", layout="wide")
st.title("🏡 Builder Property Risk Analysis")

# --- Sidebar Inputs ---
st.sidebar.header("Enter Property Details")
subject_address = st.sidebar.text_input("Enter Property Address or Zip:")
subject_price = st.sidebar.number_input("Enter Subject Property Price ($)", min_value=0, step=1000)
subject_dom = st.sidebar.number_input("Enter Subject Property DOM (Days on Market)", min_value=0, step=1)

comp1_price = st.sidebar.number_input("Comp 1 Price ($)", min_value=0, step=1000)
comp1_dom = st.sidebar.number_input("Comp 1 DOM", min_value=0, step=1)

comp2_price = st.sidebar.number_input("Comp 2 Price ($)", min_value=0, step=1000)
comp2_dom = st.sidebar.number_input("Comp 2 DOM", min_value=0, step=1)

comp3_price = st.sidebar.number_input("Comp 3 Price ($)", min_value=0, step=1000)
comp3_dom = st.sidebar.number_input("Comp 3 DOM", min_value=0, step=1)

# --- Run Analysis ---
if st.sidebar.button("Run Analysis"):

    # --- Data Prep ---
    comp_prices = [comp1_price, comp2_price, comp3_price]
    comp_doms = [comp1_dom, comp2_dom, comp3_dom]

    avg_comp_price = sum(comp_prices) / len([p for p in comp_prices if p > 0]) if any(comp_prices) else 0
    avg_comp_dom = sum(comp_doms) / len([d for d in comp_doms if d > 0]) if any(comp_doms) else 0

    # --- Risk Scoring ---
    price_score = max(0, 10 - abs(subject_price - avg_comp_price) / (0.1 * avg_comp_price)) if avg_comp_price else 5
    dom_score = max(0, 10 - abs(subject_dom - avg_comp_dom) / (0.1 * avg_comp_dom)) if avg_comp_dom else 5
    buyer_pool_score = (price_score + dom_score) / 2
    overall_score = (price_score + dom_score + buyer_pool_score) / 3

    # --- Risk Category ---
    if overall_score >= 7.5:
        risk_category = "Low Risk ✅"
        bg_color = "#d4edda"  # light green
    elif overall_score >= 5:
        risk_category = "Moderate Risk ⚠️"
        bg_color = "#fff3cd"  # soft yellow
    else:
        risk_category = "High Risk 🚨"
        bg_color = "#f8d7da"  # light red

    # --- Risk Classification Box ---
    st.markdown(
        f"<div style='background-color:{bg_color}; padding:20px; border-radius:12px'>"
        f"<h3>📊 Risk Analysis</h3>"
        f"<b>Pricing:</b> {price_score:.1f} | "
        f"<b>DOM:</b> {dom_score:.1f} | "
        f"<b>Buyer Pool:</b> {buyer_pool_score:.1f} | "
        f"<b>Overall:</b> {overall_score:.1f} → <b>{risk_category}</b>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # --- Progress Bar for Overall Score ---
    st.progress(min(int(overall_score * 10), 100))

    st.divider()

    # --- Charts ---
    st.subheader("📈 Market Comparison Charts")
    col1, col2 = st.columns(2)

    with col1:
        fig, ax = plt.subplots()
        bars = ax.bar(
            ["Subject"] + [f"Comp {i+1}" for i in range(3)],
            [subject_price, comp1_price, comp2_price, comp3_price],
            color=["#ff6b6b", "#4a90e2", "#4a90e2", "#4a90e2"]
        )
        ax.set_ylabel("List Price ($)")
        ax.set_title("Pricing vs Comps")
        ax.bar_label(bars, labels=[f"${val/1000:.0f}k" if val > 0 else "" for val in bars.datavalues], padding=3)
        st.pyplot(fig)

    with col2:
        fig, ax = plt.subplots()
        bars = ax.bar(
            ["Subject"] + [f"Comp {i+1}" for i in range(3)],
            [subject_dom, comp1_dom, comp2_dom, comp3_dom],
            color=["#ffa94d", "#4a90e2", "#4a90e2", "#4a90e2"]
        )
        ax.set_ylabel("Days on Market")
        ax.set_title("DOM Pressure")
        ax.bar_label(bars, labels=[f"{val}" if val > 0 else "" for val in bars.datavalues], padding=3)
        st.pyplot(fig)

    st.divider()

    # --- Reasoning ---
    st.subheader("🧐 Reasoning for Risk Classification")
    reasoning = []
    if price_score < 6:
        reasoning.append("The subject property’s price is significantly higher/lower than comparable properties.")
    else:
        reasoning.append("The subject property’s price is aligned with market comps.")
    if dom_score < 6:
        reasoning.append("Days on Market indicates slower movement compared to comps.")
    else:
        reasoning.append("Days on Market trend is competitive with the area.")
    if buyer_pool_score < 6:
        reasoning.append("Limited buyer pool may reduce demand.")
    else:
        reasoning.append("Buyer pool demand is strong relative to comps.")
    st.write(" ".join(reasoning))

    st.divider()

    # --- Contingency Contract Suggestions ---
    st.subheader("📑 Contingency Contract Suggestions")
    contract_suggestions = []
    if price_score < 6:
        contract_suggestions.append("💲 Include appraisal contingency or price adjustment clause.")
    if dom_score < 6:
        contract_suggestions.append("⚡ Offer seller concessions or interest rate buy-downs.")
    if buyer_pool_score < 6:
        contract_suggestions.append("🎯 Target marketing toward niche buyers or provide repair credits.")
    if not contract_suggestions:
        contract_suggestions.append("✅ Property is well-positioned; standard contract terms apply.")
    for s in contract_suggestions:
        st.markdown(f"- {s}")

    st.divider()

    # --- Probability of Sale in 60 Days ---
    st.subheader("📊 Probability of Sale in 60 Days")
    if overall_score >= 7.5:
        prob_sale = 0.85
    elif overall_score >= 5:
        prob_sale = 0.65
    else:
        prob_sale = 0.35

    st.write(f"Estimated Probability of Sale in 60 days: **{int(prob_sale*100)}%**")
    st.progress(int(prob_sale * 100))

    st.divider()

    # --- Export to PDF Button ---
    if st.button("📄 Download Risk Report (PDF)"):

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(200, 10, "Builder Property Risk Analysis Report", ln=True, align="C")
        pdf.ln(10)

        # Property Details
        pdf.set_font("Arial", "", 12)
        pdf.cell(200, 10, f"Property: {subject_address}", ln=True)
        pdf.cell(200, 10, f"List Price: ${subject_price:,.0f}", ln=True)
        pdf.cell(200, 10, f"Days on Market: {subject_dom}", ln=True)
        pdf.ln(5)

        # Risk Summary
        pdf.set_font("Arial", "B", 12)
        pdf.cell(200, 10, "Risk Classification", ln=True)
        pdf.set_font("Arial", "", 12)
        pdf.multi_cell(200, 8,
            f"Pricing Score: {price_score:.1f}\n"
            f"DOM Score: {dom_score:.1f}\n"
            f"Buyer Pool Score: {buyer_pool_score:.1f}\n"
            f"Overall: {overall_score:.1f} → {risk_category}"
        )
        pdf.ln(5)

        # Probability
        pdf.set_font("Arial", "B", 12)
        pdf.cell(200, 10, "Probability of Sale in 60 Days", ln=True)
        pdf.set_font("Arial", "", 12)
        pdf.cell(200, 10, f"Estimated: {int(prob_sale*100)}%", ln=True)
        pdf.ln(5)

        # Reasoning
        pdf.set_font("Arial", "B", 12)
        pdf.cell(200, 10, "Reasoning", ln=True)
        pdf.set_font("Arial", "", 12)
        for r in reasoning:
            pdf.multi_cell(200, 8, f"- {r}")
        pdf.ln(5)

        # Suggestions
        pdf.set_font("Arial", "B", 12)
        pdf.cell(200, 10, "Contingency Contract Suggestions", ln=True)
        pdf.set_font("Arial", "", 12)
        for s in contract_suggestions:
            pdf.multi_cell(200, 8, f"- {s}")
        pdf.ln(5)

        # Save PDF Temp File
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            pdf.output(tmp_file.name)
            tmp_path = tmp_file.name

        with open(tmp_path, "rb") as file:
            st.download_button(
                label="⬇️ Save PDF Report",
                data=file,
                file_name=f"Risk_Report_{subject_address.replace(' ', '_')}.pdf",
                mime="application/pdf",
            )

        os.remove(tmp_path)







import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
from fpdf import FPDF
import tempfile
import os

# RentCast API Key (yours)
API_KEY = "92b00e990823456eba2d61ffc2f3f224"

st.set_page_config(page_title="Builder Risk Analysis", layout="wide")

st.title("🏠 Builder Property Risk Analysis (with PDF Export)")

# User inputs
address = st.text_input("Enter Property Address", "2457 Farm to Market #1653 Ben Wheeler TX 75754")
subject_price = st.number_input("Enter Subject Property Price ($)", value=350000)
subject_dom = st.number_input("Enter Subject Property DOM (Days on Market)", value=30)

if st.button("Run Analysis"):
    # RentCast API request
    url = "https://api.rentcast.io/v1/properties/comps"
    headers = {"accept": "application/json", "X-Api-Key": API_KEY}
    params = {"address": address, "limit": 3}

    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        comps = response.json()

        if comps:
            df = pd.DataFrame(comps)

            # Display comps table
            st.subheader("Comparable Properties")
            st.dataframe(df[["formattedAddress", "price", "daysOnMarket"]])

            # --- Risk Analysis Logic ---
            avg_price = df["price"].mean()
            avg_dom = df["daysOnMarket"].mean()

            price_diff = (subject_price - avg_price) / avg_price * 100 if avg_price else 0
            dom_diff = subject_dom - avg_dom if avg_dom else subject_dom

            probability = 60
            if price_diff > 10:
                probability -= 20
            elif price_diff < -5:
                probability += 10

            if dom_diff > 15:
                probability -= 15
            elif dom_diff < -10:
                probability += 5

            probability = max(5, min(probability, 95))

            if probability >= 70:
                category, color = "Low Risk", "#90EE90"
            elif 40 <= probability < 70:
                category, color = "Moderate Risk", "#FFD580"
            else:
                category, color = "High Risk", "#FF7F7F"

            # --- Display Risk Analysis ---
            st.subheader("📊 Risk Analysis Summary")
            st.markdown(
                f"""
                <div style="padding:15px; border-radius:10px; background-color:{color}">
                    <h3 style="margin:0;">Risk Classification: {category}</h3>
                    <p style="margin:0;">Probability of Sale in 60 Days: <b>{probability}%</b></p>
                </div>
                """,
                unsafe_allow_html=True
            )

            # Reasoning
            st.markdown("### 🧐 Reasoning for Classification")
            reasoning = []
            if price_diff > 10:
                reasoning.append(f"- Property is priced **{price_diff:.1f}% above** average comps.")
            elif price_diff < -5:
                reasoning.append(f"- Property is priced **{abs(price_diff):.1f}% below** average comps (competitive).")
            else:
                reasoning.append("- Property pricing is roughly in line with comps.")

            if dom_diff > 15:
                reasoning.append(f"- Subject property DOM is **{dom_diff:.0f} days longer** than average comps.")
            elif dom_diff < -10:
                reasoning.append(f"- Subject property DOM is moving faster than comps by **{abs(dom_diff):.0f} days**.")
            else:
                reasoning.append("- Subject DOM is similar to comps.")

            for r in reasoning:
                st.write(r)

            # Contingency contract suggestions
            st.markdown("### 📝 Contingency Contract Suggestions")
            contract_suggestions = [
                "Require property to be listed within **30 days** of contract signing.",
                "If no contract within **60 days**, allow builder to seek backup offers.",
                "Price reductions should follow comp trends if DOM exceeds local average.",
                "Include option to switch to lease or rental if stagnant beyond 90 days."
            ]
            for c in contract_suggestions:
                st.write(c)

            # --- Charts ---
            st.markdown("### 📈 Visual Breakdown")

            fig, ax = plt.subplots()
            labels = ["Subject Property"] + df["formattedAddress"].tolist()
            prices = [subject_price] + df["price"].tolist()
            ax.bar(labels, prices, color=["red"] + ["blue"]*len(df))
            ax.set_ylabel("List Price ($)")
            ax.set_title("Pricing vs Comps")
            plt.xticks(rotation=20, ha="right")
            st.pyplot(fig)

            fig2, ax2 = plt.subplots()
            doms = [subject_dom] + df["daysOnMarket"].tolist()
            ax2.bar(labels, doms, color=["orange"] + ["blue"]*len(df))
            ax2.set_ylabel("Days on Market")
            ax2.set_title("DOM Pressure")
            plt.xticks(rotation=20, ha="right")
            st.pyplot(fig2)

            # --- PDF Export ---
            def create_pdf():
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", size=12)

                pdf.cell(200, 10, txt="Builder Property Risk Analysis", ln=True, align="C")
                pdf.ln(10)

                pdf.multi_cell(0, 10, f"Address: {address}")
                pdf.multi_cell(0, 10, f"Subject Price: ${subject_price:,.0f}")
                pdf.multi_cell(0, 10, f"Subject DOM: {subject_dom} days")
                pdf.ln(5)

                pdf.set_fill_color(255, 220, 220 if category == "High Risk" else 255, 255)
                pdf.multi_cell(0, 10, f"Risk Classification: {category}", fill=True)
                pdf.multi_cell(0, 10, f"Probability of Sale in 60 Days: {probability}%")
                pdf.ln(5)

                pdf.multi_cell(0, 10, "Reasoning:")
                for r in reasoning:
                    pdf.multi_cell(0, 8, r)

                pdf.ln(5)
                pdf.multi_cell(0, 10, "Contingency Contract Suggestions:")
                for c in contract_suggestions:
                    pdf.multi_cell(0, 8, c)

                # Save to temp file
                tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                pdf.output(tmp_file.name)
                return tmp_file.name

            pdf_file = create_pdf()
            with open(pdf_file, "rb") as f:
                st.download_button("📥 Download Full Risk Analysis PDF", f, file_name="risk_analysis.pdf")

            os.remove(pdf_file)

        else:
            st.warning("⚠️ No comps found for this location. Try another address.")
    else:
        st.error(f"RentCast API error: {response.status_code} - {response.text}")








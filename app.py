import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# -----------------------------
# Page Setup
# -----------------------------
st.set_page_config(page_title="Property Risk Analysis", layout="wide")

st.title("🏠 Property Risk Analysis Tool")
st.markdown("Upload property and comparable data to generate risk analytics.")

# -----------------------------
# File Upload
# -----------------------------
uploaded_file = st.file_uploader("Upload your property data (CSV)", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)

    # Make a short address for charts (street + city only)
    def shorten_address(addr):
        parts = addr.split(",")
        return ", ".join(parts[:2]) if len(parts) >= 2 else addr

    df["short_address"] = df["address"].apply(shorten_address)

    # -----------------------------
    # Subject Property (first row)
    # -----------------------------
    subject = df.iloc[0]
    comps = df.iloc[1:]

    st.subheader("📌 Subject Property")
    st.write(subject)

    # -----------------------------
    # Risk Score Calculation
    # -----------------------------
    def calculate_risk(subject, comps):
        pricing_score = max(0, 10 - abs(subject["price"] - comps["price"].mean()) / 10000)
        dom_score = max(0, 10 - abs(subject["dom"] - comps["dom"].mean()) / 5)
        pool_score = min(10, len(comps) / 2)
        overall = round((pricing_score + dom_score + pool_score) / 3, 1)
        return pricing_score, dom_score, pool_score, overall

    pricing, dom, pool, overall = calculate_risk(subject, comps)

    st.subheader("📊 Risk Scores")
    st.markdown(
        f"**Pricing:** {round(pricing,1)} | "
        f"**DOM:** {round(dom,1)} | "
        f"**Buyer Pool:** {round(pool,1)} | "
        f"**Overall:** {overall}"
    )

    # -----------------------------
    # Charts
    # -----------------------------
    col1, col2 = st.columns(2)

    # Pricing vs Comps
    with col1:
        st.markdown("### Pricing vs Comps")
        plt.figure(figsize=(6, 4))
        sns.barplot(x="short_address", y="price", data=comps, color="steelblue", label="Comparable Properties")
        plt.bar(subject["short_address"], subject["price"], color="firebrick", label="Subject Property")
        plt.ylabel("List Price ($)")
        plt.xticks(rotation=30, ha="right", fontsize=8)
        plt.legend()
        plt.tight_layout()
        st.pyplot(plt.gcf())

    # DOM Pressure
    with col2:
        st.markdown("### DOM Pressure")
        plt.figure(figsize=(6, 4))
        sns.barplot(x="short_address", y="dom", data=comps, color="steelblue", label="Comparable Properties")
        plt.bar(subject["short_address"], subject["dom"], color="darkorange", label="Subject Property")
        plt.ylabel("Days on Market")
        plt.xticks(rotation=30, ha="right", fontsize=8)
        plt.legend()
        plt.tight_layout()
        st.pyplot(plt.gcf())

    # -----------------------------
    # Recommended List-Price Band
    # -----------------------------
    avg_comp_price = comps["price"].mean()
    low_band = avg_comp_price * 0.97
    high_band = avg_comp_price * 1.03

    st.subheader("💡 Recommended List-Price Band")
    st.write(f"${low_band:,.0f} – ${high_band:,.0f}")

else:
    st.info("👆 Upload a CSV to begin. First row = Subject Property, rest = Comps")


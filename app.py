import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(page_title="Builder Risk Analysis", layout="wide")

st.title("🏡 Builder Property Risk Analysis")

# --- Risk classification helper ---
def classify_risk(score):
    if score >= 7.5:
        return "🟢 Low Risk", "green"
    elif score >= 5:
        return "🟡 Moderate Risk", "orange"
    else:
        return "🔴 High Risk", "red"

# --- Subject Property ---
st.subheader("Subject Property")
subject_link = st.text_input("Paste Subject Property Zillow Link:")
subject_price = st.number_input("Price ($)", min_value=0, value=300000, step=1000)
subject_dom = st.number_input("Days on Market", min_value=0, value=0, step=1)
subject_sqft = st.number_input("Square Footage", min_value=0, value=0, step=100)
subject_year = st.number_input("Year Built", min_value=1800, value=2000, step=1)

# --- Comparable Properties ---
st.subheader("Comparable Properties (Paste Zillow Links)")
num_comps = st.number_input("How many comps?", min_value=1, max_value=3, value=3, step=1)

comps = []
for i in range(num_comps):
    st.markdown(f"**Comp {i+1}**")
    link = st.text_input(f"Comp {i+1} Zillow Link", key=f"link_{i}")
    price = st.number_input(f"Comp {i+1} Price ($)", min_value=0, value=0, step=1000, key=f"price_{i}")
    dom = st.number_input(f"Comp {i+1} Days on Market", min_value=0, value=0, step=1, key=f"dom_{i}")
    sqft = st.number_input(f"Comp {i+1} Sqft", min_value=0, value=0, step=100, key=f"sqft_{i}")
    year = st.number_input(f"Comp {i+1} Year Built", min_value=1800, value=2000, step=1, key=f"year_{i}")
    comps.append({"Property": f"Comp {i+1}", "Link": link, "Price": price, "DOM": dom, "Sqft": sqft, "Year": year})

# --- Run Analysis ---
if st.button("Run Analysis"):
    comp_df = pd.DataFrame(comps)

    if subject_link and subject_price > 0 and not comp_df.empty:
        subject_df = pd.DataFrame([{
            "Property": "Subject Property",
            "Link": subject_link,
            "Price": subject_price,
            "DOM": subject_dom,
            "Sqft": subject_sqft,
            "Year": subject_year
        }])
        all_df = pd.concat([subject_df, comp_df], ignore_index=True)

        # --- Charts side by side ---
        col1, col2 = st.columns(2)

        with col1:
            fig1, ax1 = plt.subplots()
            ax1.bar(all_df["Property"], all_df["Price"],
                    color=["red"] + ["steelblue"]*(len(all_df)-1))
            ax1.set_title("Pricing vs Comps")
            ax1.set_ylabel("List Price ($)")
            for idx, val in enumerate(all_df["Price"]):
                ax1.text(idx, val + 1000, f"${val:,.0f}", ha="center", va="bottom")
            plt.xticks(rotation=20, ha="right")
            st.pyplot(fig1)

        with col2:
            fig2, ax2 = plt.subplots()
            ax2.bar(all_df["Property"], all_df["DOM"],
                    color=["orange"] + ["steelblue"]*(len(all_df)-1))
            ax2.set_title("DOM Pressure")
            ax2.set_ylabel("Days on Market")
            for idx, val in enumerate(all_df["DOM"]):
                ax2.text(idx, val + 1, f"{val}", ha="center", va="bottom")
            plt.xticks(rotation=20, ha="right")
            st.pyplot(fig2)

        # --- Risk Score ---
        avg_price = comp_df["Price"].mean()
        avg_dom = comp_df["DOM"].mean()

        price_score = max(0, 10 - abs(subject_price - avg_price) / avg_price * 10) if avg_price > 0 else 0
        dom_score = max(0, 10 - abs(subject_dom - avg_dom) / avg_dom * 10) if avg_dom > 0 else 10
        buyer_pool_score = max(0, min(10, len(comps) * 2))  
        overall_score = round((price_score + dom_score + buyer_pool_score) / 3, 1)

        risk_label, risk_color = classify_risk(overall_score)

        st.subheader("📊 Risk Scores (0-10)")
        st.markdown(
            f"**Pricing:** {round(price_score,1)} | "
            f"**DOM:** {round(dom_score,1)} | "
            f"**Buyer Pool:** {round(buyer_pool_score,1)}"
        )
        st.markdown(
            f"### Overall Score: **{overall_score}** → "
            f"<span style='color:{risk_color}; font-weight:bold'>{risk_label}</span>",
            unsafe_allow_html=True
        )

        # --- Comparison Table ---
        st.subheader("📋 Property Comparison Table")
        st.dataframe(all_df.style.format({
            "Price": "${:,.0f}",
            "DOM": "{:,.0f}",
            "Sqft": "{:,.0f}",
            "Year": "{:,.0f}"
        }))
    else:
        st.error("Please fill out subject property and comps.")




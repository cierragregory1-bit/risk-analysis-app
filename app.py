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
                ax1.text(idx, val + 1000, f"${val:



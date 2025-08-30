import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(page_title="Builder Property Risk Analysis", layout="wide")

st.title("🏡 Builder Property Risk Analysis (Manual Input)")

# --- Subject Property Info ---
st.subheader("Subject Property")
subject_address = st.text_input("Enter Subject Property Address or Zip:")
subject_price = st.number_input("Enter Subject Property Price ($)", min_value=0, value=300000, step=1000)
subject_dom = st.number_input("Enter Subject Property DOM (Days on Market)", min_value=0, value=0, step=1)

# --- Manual Comparable Properties Input ---
st.subheader("Comparable Properties (Manual Entry)")
num_comps = st.number_input("How many comps do you want to enter?", min_value=1, max_value=10, value=3, step=1)

comps = []
for i in range(num_comps):
    st.markdown(f"**Comp {i+1}**")
    address = st.text_input(f"Comp {i+1} Address", key=f"addr_{i}")
    price = st.number_input(f"Comp {i+1} Price ($)", min_value=0, value=0, step=1000, key=f"price_{i}")
    dom = st.number_input(f"Comp {i+1} DOM (Days on Market)", min_value=0, value=0, step=1, key=f"dom_{i}")
    comps.append({"Address": address, "Price": price, "DOM": dom})

# --- Run Analysis Button ---
if st.button("Run Analysis"):
    comp_df = pd.DataFrame(comps)

    if subject_address and subject_price > 0 and not comp_df.empty:
        # Add subject property row for charts
        subject_df = pd.DataFrame([{
            "Address": subject_address + " (Subject)",
            "Price": subject_price,
            "DOM": subject_dom
        }])
        all_df = pd.concat([subject_df, comp_df], ignore_index=True)

        # --- Pricing vs Comps Chart ---
        fig1, ax1 = plt.subplots()
        ax1.bar(all_df["Address"], all_df["Price"],
                color=["red"] + ["steelblue"]*(len(all_df)-1))
        ax1.set_title("Pricing vs Comps")
        ax1.set_ylabel("List Price ($)")
        for idx, val in enumerate(all_df["Price"]):
            ax1.text(idx, val + 1000, f"${val:,.0f}", ha="center", va="bottom")
        plt.xticks(rotation=20, ha="right")
        st.pyplot(fig1)

        # --- DOM Pressure Chart ---
        fig2, ax2 = plt.subplots()
        ax2.bar(all_df["Address"], all_df["DOM"],
                color=["orange"] + ["steelblue"]*(len(all_df)-1))
        ax2.set_title("DOM Pressure")
        ax2.set_ylabel("Days on Market")
        for idx, val in enumerate(all_df["DOM"]):
            ax2.text(idx, val + 1, f"{val}", ha="center", va="bottom")
        plt.xticks(rotation=20, ha="right")
        st.pyplot(fig2)

        # --- Risk Score Calculation ---
        avg_price = comp_df["Price"].mean()
        avg_dom = comp_df["DOM"].mean()

        price_score = max(0, 10 - abs(subject_price - avg_price) / avg_price * 10)
        dom_score = max(0, 10 - abs(subject_dom - avg_dom) / avg_dom * 10) if avg_dom > 0 else 10
        buyer_pool_score = max(0, min(10, len(comps) * 2))  # crude proxy
        overall_score = round((price_score + dom_score + buyer_pool_score) / 3, 1)

        st.subheader("📊 Risk Scores (0-10)")
        st.markdown(
            f"**Pricing:** {round(price_score,1)} | "
            f"**DOM:** {round(dom_score,1)} | "
            f"**Buyer Pool:** {round(buyer_pool_score,1)} | "
            f"**Overall:** **{overall_score}**"
        )

    else:
        st.error("Please fill out subject property and comps before running analysis.")

import streamlit as st
import requests
import matplotlib.pyplot as plt

# ========== SETTINGS ==========
REALTOR_API_KEY = "YOUR_RAPIDAPI_KEY"

# ========== DATA FETCHER ==========

def fetch_comps_realtor(address, api_key):
    url = "https://realtor-com-real-estate.p.rapidapi.com/properties/v2/list-for-sale"
    querystring = {"location": address, "limit": 5}  # grab 5 comps
    headers = {
        "x-rapidapi-host": "realtor-com-real-estate.p.rapidapi.com",
        "x-rapidapi-key": api_key
    }
    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=10)
        response.raise_for_status()
        data = response.json().get("properties", [])
        comps = []
        for item in data:
            comps.append({
                "address": item.get("address", {}).get("line", "Unknown")[:25],  # shorten address
                "price": item.get("price", 0),
                "dom": item.get("days_on_market", 0)
            })
        return comps
    except Exception as e:
        st.error(f"Realtor API error: {e}")
        return []

# ========== VISUALS ==========

def plot_price_chart(subject_price, comps):
    fig, ax = plt.subplots()
    labels = ["Subject Property"] + [c["address"] for c in comps]
    prices = [subject_price] + [c["price"] for c in comps]
    colors = ["red"] + ["steelblue"] * len(comps)

    bars = ax.bar(labels, prices, color=colors)
    ax.set_title("Pricing vs Comps")
    ax.set_ylabel("List Price ($)")
    ax.tick_params(axis='x', rotation=20)

    for bar, price in zip(bars, prices):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                f"${price/1000:.0f}k", ha='center', va='bottom', fontsize=8)

    fig.subplots_adjust(bottom=0.25)
    ax.legend(["Subject Property", "Comparable Properties"], 
              loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=2)

    return fig

def plot_dom_chart(subject_dom, comps):
    fig, ax = plt.subplots()
    labels = ["Subject Property"] + [c["address"] for c in comps]
    doms = [subject_dom] + [c["dom"] for c in comps]
    colors = ["orange"] + ["steelblue"] * len(comps)

    bars = ax.bar(labels, doms, color=colors)
    ax.set_title("DOM Pressure")
    ax.set_ylabel("Days on Market")
    ax.tick_params(axis='x', rotation=20)

    for bar, dom in zip(bars, doms):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                f"{dom}", ha='center', va='bottom', fontsize=8)

    fig.subplots_adjust(bottom=0.25)
    ax.legend(["Subject Property", "Comparable Properties"], 
              loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=2)

    return fig

# ========== STREAMLIT APP ==========

st.title("🏠 Builder Property Risk Analysis (Realtor.com API)")

address = st.text_input("Enter Property Address or Zip:")
subject_price = st.number_input("Enter Subject Property Price ($)", min_value=0, step=1000)
subject_dom = st.number_input("Enter Subject Property DOM (Days on Market)", min_value=0, step=1)

if st.button("Run Analysis") and address:
    comps = fetch_comps_realtor(address, REALTOR_API_KEY)

    if comps:
        st.pyplot(plot_price_chart(subject_price, comps))
        st.pyplot(plot_dom_chart(subject_dom, comps))

        avg_price = sum(c["price"] for c in comps if c["price"]) / max(1, len([c for c in comps if c["price"]]))
        risk_score = 10 - min(10, abs(subject_price - avg_price) / avg_price * 10)
        st.subheader(f"📊 Risk Score: {risk_score:.1f}/10")
    else:
        st.warning("No comps found. Try another location.")

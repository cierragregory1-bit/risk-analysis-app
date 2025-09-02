import streamlit as st
import requests
import matplotlib.pyplot as plt
import textwrap

# ------------------------
# CONFIG
# ------------------------
st.set_page_config(page_title="Contingent Property Risk Analysis", layout="wide")

# Use API key from Streamlit secrets
API_KEY = st.secrets["RENTCAST_API_KEY"]
BASE_URL = "https://api.rentcast.io/v1"

# ------------------------
# FUNCTIONS
# ------------------------

def fetch_property_details(address):
    """Fetch subject property details from RentCast."""
    try:
        resp = requests.get(
            f"{BASE_URL}/properties",
            params={"address": address},
            headers={"accept": "application/json", "X-Api-Key": API_KEY},
            timeout=15
        )
        data = resp.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        return {"error": str(e)}


def fetch_comps(address, radius=2):
    """Fetch comparable properties, expand radius until some results are found."""
    try:
        for r in [2, 5, 10]:
            resp = requests.get(
                f"{BASE_URL}/avm/comps",
                params={"address": address, "radius": r, "limit": 5},
                headers={"accept": "application/json", "X-Api-Key": API_KEY},
                timeout=15
            )
            data = resp.json()
            if isinstance(data, list) and data:
                return data
        return []
    except Exception:
        return []


def classify_risk(price, comp_prices, dom, comp_doms):
    """Return risk classification with probability, reasoning, and suggestions."""
    if not comp_prices or not comp_doms:
        return {
            "risk": "Unavailable",
            "color": "gray",
            "reason": "No comps found for this property.",
            "probability": "N/A",
            "suggestions": "Require listing within 30 days and re-evaluate pricing."
        }

    avg_price = sum(comp_prices) / len(comp_prices) if comp_prices else 0
    avg_dom = sum(comp_doms) / len(comp_doms) if comp_doms else 0

    if avg_price == 0:
        return {
            "risk": "Unavailable",
            "color": "gray",
            "reason": "Comps returned no valid pricing.",
            "probability": "N/A",
            "suggestions": "Re-check address or broaden search radius."
        }

    price_diff = abs(price - avg_price) / avg_price
    dom_diff = abs(dom - avg_dom) / avg_dom if avg_dom > 0 else 0

    # Risk levels
    if price_diff < 0.05 and dom_diff < 0.2:
        return {
            "risk": "Low",
            "color": "green",
            "reason": "Price and DOM are aligned with comps.",
            "probability": "High (~80%)",
            "suggestions": "Standard contingency. Minor concessions may help."
        }
    elif price_diff < 0.15 and dom_diff < 0.5:
        return {
            "risk": "Moderate",
            "color": "yellow",
            "reason": "Some deviation from comps in pricing or DOM.",
            "probability": "Medium (~55%)",
            "suggestions": "Stronger contingencies + price flexibility."
        }
    else:
        return {
            "risk": "High",
            "color": "red",
            "reason": "Large mismatch between subject property and comps.",
            "probability": "Low (~30%)",
            "suggestions": "Require early listing + adjust pricing."
        }


def plot_price_chart(subject_price, comp_prices, comp_labels):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(comp_labels, comp_prices, label="Comps", color="skyblue")
    ax.axhline(subject_price, color="orange", linestyle="--", label="Subject Property")
    ax.set_ylabel("Price ($)")
    ax.set_title("Subject Property vs Comparable Prices")
    ax.legend()
    plt.xticks(rotation=30, ha="right")
    st.pyplot(fig)


def plot_dom_chart(subject_dom, comp_doms, comp_labels):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(comp_labels, comp_doms, label="Comps", color="lightgreen")
    ax.axhline(subject_dom, color="orange", linestyle="--", label="Subject Property")
    ax.set_ylabel("Days on Market")
    ax.set_title("Subject Property vs Comparable DOM")
    ax.legend()
    plt.xticks(rotation=30, ha="right")
    st.pyplot(fig)


# ------------------------
# APP LAYOUT
# ------------------------

st.title("🏡 Contingent Property Risk Analysis")
st.markdown("Upload an address to analyze risk based on comps, pricing, and days on market.")

address = st.text_input("Enter Property Address", placeholder="123 Main St, City, State")

if st.button("Run Analysis") and address:
    with st.spinner("Fetching data..."):
        subject = fetch_property_details(address)
        comps = fetch_comps(address)

    if not subject:
        st.error("Could not retrieve subject property details. Please check the address.")
    else:
        st.subheader("📌 Subject Property")
        st.write(f"**Address:** {subject.get('address', 'N/A')}")
        st.write(f"**List Price:** ${subject.get('price', 'N/A')}")
        st.write(f"**Days on Market (DOM):** {subject.get('daysOnMarket', 'N/A')}")

        # Prepare comp data
        comp_prices = [c.get("price", 0) for c in comps if c.get("price")]
        comp_doms = [c.get("daysOnMarket", 0) for c in comps if c.get("daysOnMarket")]
        comp_labels = [
            textwrap.shorten(c.get("address", "Comp"), width=25, placeholder="...")
            for c in comps
        ]

        # Run risk classification
        result = classify_risk(
            subject.get("price", 0),
            comp_prices,
            subject.get("daysOnMarket", 0),
            comp_doms
        )

        st.subheader("📊 Risk Analysis")
        st.markdown(
            f"<div style='padding:10px;background-color:{result['color']};color:white;border-radius:8px'>"
            f"<b>Risk Level:</b> {result['risk']}<br>"
            f"<b>Probability of Sale in 60 Days:</b> {result['probability']}<br>"
            f"<b>Reasoning:</b> {result['reason']}<br>"
            f"<b>Contingency Suggestions:</b> {result['suggestions']}"
            "</div>",
            unsafe_allow_html=True
        )

        # Charts
        if comp_prices and comp_doms:
            st.subheader("📉 Comparative Analysis Charts")
            plot_price_chart(subject.get("price", 0), comp_prices, comp_labels)
            plot_dom_chart(subject.get("daysOnMarket", 0), comp_doms, comp_labels)
        else:
            st.warning("No comps available to display charts.")















import streamlit as st
import requests
import matplotlib.pyplot as plt

# -----------------------------
# Load API Key from secrets
# -----------------------------
API_KEY = st.secrets.get("RENTCAST_API_KEY")

if not API_KEY:
    st.error("❌ API key not found. Please add it in `.streamlit/secrets.toml` like this:\n\n`RENTCAST_API_KEY = \"your_api_key_here\"`")
    st.stop()  # stop execution if no key


# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Contingent Property Risk Analysis", layout="wide")
st.title("🏡 Contingent Property Risk Analysis")
st.write("Upload an address to analyze risk based on comps, pricing, and days on market.")


# -----------------------------
# API Function
# -----------------------------
def fetch_property_data(address):
    """Fetch property data from RentCast API"""
    try:
        url = "https://api.rentcast.io/v1/avm/value"
        headers = {"accept": "application/json", "X-Api-Key": API_KEY}
        params = {"address": address}

        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"API Error {response.status_code}: {response.text}"}

    except Exception as e:
        return {"error": str(e)}


# -----------------------------
# Input field
# -----------------------------
address = st.text_input("Enter Property Address", "")

if st.button("Run Analysis"):
    if not address:
        st.warning("⚠️ Please enter a property address first.")
    else:
        st.info("⏳ Fetching property data...")
        data = fetch_property_data(address)

        if "error" in data:
            st.error(f"❌ Could not retrieve property details.\n\n**Reason:** {data['error']}")
        else:
            # Display property data nicely
            st.success("✅ Property data retrieved successfully!")
            st.json(data)

            # Example: Display a simple chart (stub for now)
            fig, ax = plt.subplots()
            ax.bar(["Estimated Value"], [data.get("avmValue", 0)])
            ax.set_ylabel("Value ($)")
            st.pyplot(fig)


  













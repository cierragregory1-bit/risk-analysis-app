import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
from datetime import date

# ---- CONFIG ----
st.set_page_config(page_title="Contingency Risk Analyzer", layout="wide")

# ---- INPUTS ----
st.title("Contingency Risk Analyzer")
col1, col2 = st.columns([2,1])
with col1:
    address = st.text_input("Property Address", "")
    borrower = st.text_input("Borrower Name", "")
with col2:
    list_price = st.number_input("Subject List Price ($)", min_value=0, step=1000, value=0)
    subject_dom = st.number_input("Subject Days on Market", min_value=0, step=1, value=0)

st.markdown("**Comparable Sales/Actives** (paste or edit):")
default = pd.DataFrame({
    "Address": ["Comp 1","Comp 2","Comp 3"],
    "ListPrice": [0,0,0],
    "SoldPrice": [0,0,0],
    "SqFt": [0,0,0],
    "DOM": [0,0,0],
    "Notes": ["","",""]
})
comps = st.data_editor(default, num_rows="dynamic", use_container_width=True)

# ---- FUNCTIONS ----
def comp_band(df):
    sold = df["SoldPrice"].replace(0, np.nan).dropna()
    if len(sold) < 2:
        sold = df["ListPrice"].replace(0, np.nan).dropna()
    if len(sold) == 0:
        return (0,0,0)
    med = np.median(sold)
    iqr = np.subtract(*np.percentile(sold, [75,25]))
    low = med - iqr/2
    high = med + iqr/2
    return (low, med, high)

def score_price(subject, comp_med):
    if comp_med <= 0 or subject <= 0: return 6  # neutralish if unknown
    delta = (subject - comp_med) / comp_med
    cuts = [ -0.01, 0.01, 0.03, 0.05, 0.07, 0.10 ]
    scores = [3,4,5,6,7,8,9]
    for c,s in zip(cuts, scores):
        if delta <= c: return s
    return 10

def score_dom(subject_dom, comp_dom_med):
    if comp_dom_med <= 0: return 5
    ratio = min(subject_dom/comp_dom_med, 3.0)
    bands = [0.8,1.2,1.6,2.0,2.5]
    scores = [3,5,6,7,8,9]
    for b,s in zip(bands, scores):
        if ratio <= b: return s
    return 10

def score_buyer_pool(subject, buyer_med):
    if subject==0 or buyer_med==0: return 5
    gap = subject - buyer_med
    cuts = [0, 10000, 20000, 35000, 50000]
    scores = [4,5,6,7,8,9]
    for c,s in zip(cuts, scores):
        if gap <= c: return s
    return 10

def overall(price_s, dom_s, buyer_s):
    return round(0.45*price_s + 0.35*dom_s + 0.20*buyer_s, 1)

def prob_from_risk(r):
    if r <= 3: return 0.85
    if r <= 4: return 0.68
    if r <= 5: return 0.55
    if r <= 6: return 0.45
    if r <= 7: return 0.33
    if r <= 8: return 0.20
    return 0.12

def color_for_prob(p):
    return "🟩" if p>=0.60 else ("🟨" if p>=0.40 else ("🟧" if p>=0.25 else "🟥"))

# ---- CALC ----
low, med, high = comp_band(comps)
comp_dom_med = np.median(comps["DOM"].replace(0,np.nan).dropna()) if len(comps)>0 else 0
buyer_med = med if med>0 else (comps["ListPrice"].replace(0,np.nan).dropna().median() if len(comps)>0 else 0)

price_score = score_price(list_price, med)
dom_score   = score_dom(subject_dom, comp_dom_med)
buyer_score = score_buyer_pool(list_price, buyer_med)
overall_risk = overall(price_score, dom_score, buyer_score)
prob60 = prob_from_risk(overall_risk)

# ---- OUTPUT SUMMARY ----
st.subheader("Summary")
st.write(f"**Probability of Selling in 60 Days:** {color_for_prob(prob60)} {int(prob60*100)}%")
st.write(f"**Risk Scores (0-10):** Pricing {price_score} | DOM {dom_score} | Buyer Pool {buyer_score} | **Overall {overall_risk}**")
if med>0:
    st.write(f"**Recommended List-Price Band:** ${int(max(low, med*0.98)):,} – ${int(min(high, med*1.02)):,}")

# ---- CHARTS ----
import matplotlib.pyplot as plt
import seaborn as sns
sns.set_style("whitegrid")

c1, c2 = st.columns(2)
with c1:
    fig, ax = plt.subplots(figsize=(5.2,3))
    labels = ["Subject"] + comps["Address"].tolist()
    vals = [list_price] + comps["ListPrice"].tolist()
    cols = ["#c1121f"] + ["#457b9d"]*len(comps)
    bars = ax.bar(labels, vals, color=cols)
    ax.set_title("Pricing vs Comps")
    ax.set_ylabel("List Price ($)")
    for b,v in zip(bars, vals):
        ax.text(b.get_x()+b.get_width()/2, v, f"${int(v/1000)}k", ha="center", va="bottom", fontsize=9)
    ax.legend([bars[0], bars[1] if len(bars)>1 else bars[0]], ["Subject Property","Comparable Properties"],
              loc="upper center", bbox_to_anchor=(0.5,-0.18), ncol=2, frameon=True)
    st.pyplot(fig)

with c2:
    fig, ax = plt.subplots(figsize=(5.2,3))
    labels = ["Subject"] + comps["Address"].tolist()
    vals = [subject_dom] + comps["DOM"].tolist()
    cols = ["#f77f00"] + ["#457b9d"]*len(comps)
    bars = ax.bar(labels, vals, color=cols)
    ax.set_title("DOM Pressure")
    ax.set_ylabel("Days on Market")
    for b,v in zip(bars, vals):
        ax.text(b.get_x()+b.get_width()/2, v, f"{int(v)}", ha="center", va="bottom", fontsize=9)
    ax.legend([bars[0], bars[1] if len(bars)>1 else bars[0]], ["Subject Property","Comparable Properties"],
              loc="upper center", bbox_to_anchor=(0.5,-0.18), ncol=2, frameon=True)
    st.pyplot(fig)

# Buyer Pool chart (subject vs buyer median)
fig, ax = plt.subplots(figsize=(5.2,3))
labels = ["Subject Price","Buyer Median Budget"]
vals = [list_price if list_price>0 else 0, buyer_med if buyer_med>0 else 0]
cols = ["#e9c46a","#457b9d"]
bars = ax.bar(labels, vals, color=cols)
ax.set_title("Buyer Pool / Affordability")
for b,v in zip(bars, vals):
    ax.text(b.get_x()+b.get_width()/2, v, f"${int(v/1000)}k", ha="center", va="bottom", fontsize=9)
ax.legend(bars, ["Subject Price","Market Buyer Median"], loc="upper center", bbox_to_anchor=(0.5,-0.18), ncol=2, frameon=True)
st.pyplot(fig)

# ---- CONTINGENCY LANGUAGE (auto by risk) ----
st.subheader("Contingency Contract – Suggested Clauses")
def tier(prob):
    p = prob60
    return "GREEN" if p>=0.60 else ("YELLOW" if p>=0.40 else ("ORANGE" if p>=0.25 else "RED"))

risk_tier = tier(prob60)
if risk_tier=="GREEN":
    clauses = [
      ("Listing Deadline","List within 10 days at range aligned to comp median.","Keeps runway and price discipline."),
      ("Price Plan","Day 21: 1% reduction if no offer; Day 35: +1%.","Tracks absorption without renegotiation."),
      ("Exit/Extension","If not under contract by Day 45, builder may extend close or convert to non-contingent.","Protects timeline.")
    ]
elif risk_tier=="YELLOW":
    clauses = [
      ("Listing Deadline","List within 7 days at recommended band (±1.5%).","Early alignment to demand band."),
      ("Staged Reductions","Day 21: 1%; Day 35: +1%; Day 49: +1%.","Counters DOM drag."),
      ("Marketing","Pro photos + open house in first 10 days; weekly feedback shared with builder.","Increases velocity."),
      ("Exit/Protection","If not under contract by Day 60, builder may terminate or require financing bridge evidence.","Caps carry.")
    ]
elif risk_tier=="ORANGE":
    clauses = [
      ("Aggressive Launch","List within 5 days at low end of band.","Price to the lane buyers actually transact in."),
      ("Staged Reductions","Day 14: 1%; Day 28: +1%; Day 42: +1%.","Forces movement in slow lane."),
      ("Concessions","Pre-approve buydown/closing credit up to 1% if no offers by Day 21.","Widen buyer pool."),
      ("Exit/Protection","If not under contract by Day 60, builder may terminate/convert.","Limits carry exposure.")
    ]
else:
    clauses = [
      ("Immediate Realign","List at or below band floor; relaunch media.","Reset market perception."),
      ("Accelerated Cuts","Day 10: 1.5%; Day 21: +1.5%; Day 35: +1%.","Breaks through resistance."),
      ("Proof of Effort","Weekly report to builder; 2 open houses/month.","Ensure execution."),
      ("Hard Exit","If not under contract by Day 45–60, builder may terminate or require non-contingent close.","Prevents prolonged carry.")
    ]

st.table(pd.DataFrame(clauses, columns=["Clause","Language","Rationale"]))

# ---- PDF EXPORT (placeholder) ----
st.markdown("---")
if st.button("Export PDF (v3 Layout)"):
    st.info("PDF export is wired in the full build with your v3 template (ReportLab).")

import streamlit as st
import os
import pandas as pd
import datetime
import plotly.graph_objects as go
from supabase import create_client, Client
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="TFSA Tracker", layout="centered")
# ---------------------
# Supabase Configuration


SUPABASE_URL = os.environ["SUPABASE_URL"].strip()
SUPABASE_KEY = os.environ["SUPABASE_KEY"].strip()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------
# Define annual TFSA limits
TFSA_LIMITS = {
    2009: 5000, 2010: 5000, 2011: 5000,
    2012: 5000, 2013: 5500, 2014: 5500,
    2015: 10000, 2016: 5500, 2017: 5500,
    2018: 5500, 2019: 6000, 2020: 6000,
    2021: 6000, 2022: 6000, 2023: 6500,
    2024: 7000, 2025: 7000
}

# ---------------------
# Supabase Data Functions
def load_start_year(email):
    resp = (
        supabase.table("user_settings")
                 .select("start_year")
                 .eq("user_email", email)
                 .execute()
    )
    if resp.data:
        return resp.data[0]["start_year"]
    return 2009

def save_start_year(email, year):
    supabase.table("user_settings") \
            .upsert({"user_email": email, "start_year": year}) \
            .execute()
def load_data():
    resp = (supabase
            .table("contributions")
            .select("*")
            .eq("user_email", user_email)
            .execute())

    data = resp.data or []
    if not data:
        # return an empty DataFrame with the right columns
        return pd.DataFrame(columns=["id","Date","Institution","Amount"])

    df = pd.DataFrame(data)
    # map your columns
    df["Date"]        = pd.to_datetime(df["date"])
    df["Institution"] = df["institution"]
    df["Amount"]      = df["amount"]
    return df[["id","Date","Institution","Amount"]]

def save_row(date, institution, amount):
    payload = {
        "user_email": user_email,
        "date":       date.isoformat(),
        "institution": institution,
        "amount":     float(amount)
    }
    try:
        # actually insert into Supabase
        resp = supabase.table("contributions").insert(payload).execute()
        st.success("✅ Transaction recorded!")
        
        
    except Exception as e:
        st.error(f"❌ Insert failed: {e}")
        st.error(f"Payload was: {payload}")
        raise
def delete_row(row_id):
    supabase.table("contributions") \
            .delete() \
            .eq("id", row_id) \
            .eq("user_email", user_email) \
            .execute()

def clear_all_data():
    supabase.table("contributions") \
            .delete() \
            .eq("user_email", user_email) \
            .execute()

# ---------------------
# Helper Functions
def get_total_limit(start_year):
    current_year = datetime.datetime.now().year
    return sum([TFSA_LIMITS.get(y, 0) for y in range(start_year, current_year + 1)])

def draw_contribution_bar_plotly(contributed, limit, withdrawal):
    percent_used = (contributed / limit) * 100 if limit > 0 else 0
    remaining = max(limit - contributed, 0)

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=["TFSA Room"],
        y=[limit],
        marker_color='lightgrey',
        width=[0.4],
        opacity=0.3,
        name="Limit",
        hoverinfo='skip'
    ))

    fig.add_trace(go.Bar(
        x=["TFSA Room"],
        y=[contributed],
        marker_color='crimson',
        width=[0.4],
        name="Contributed",
        text=f"{percent_used:.1f}%",
        textposition="inside",
        hovertemplate=f"Deposited: ${contributed:,.2f}<br>Limit: ${limit:,.2f}<extra></extra>"
    ))

    fig.update_layout(
        title="TFSA Contribution Progress",
        barmode="overlay",
        yaxis=dict(title="Amount ($)", range=[0, limit]),
        xaxis=dict(showticklabels=False),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        height=450,
        margin=dict(l=40, r=20, t=40, b=40)
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.markdown(f"""
            <div style='font-size: 18px; padding-top: 60px;'>
                <b>Total Room:</b> ${limit:,.2f}<br><br>
                <b>Deposited:</b> ${contributed:,.2f}<br><br>
                <b>Withdrawal:</b> ${withdrawal:,.2f}<br><br>
                <b>Remaining:</b> ${remaining:,.2f}<br><br>
                <b>Used:</b> {percent_used:.1f}%
            </div>
        """, unsafe_allow_html=True)

# ---------------------
# Main App
if "user_email" not in st.session_state:
    st.session_state.user_email = ""

# Text input bound to session state
user_email = st.text_input(
    "Enter your email to load your TFSA data",
    value=st.session_state.user_email
)
st.session_state.user_email = user_email

if not user_email:
    st.stop()
init_year = load_start_year(user_email)
years = list(TFSA_LIMITS.keys())
default_idx = years.index(init_year) if init_year in years else 0

start_year = st.selectbox(
    "What year did you become eligible for TFSA?",
    years,
    index=default_idx
)

# only save if they actually changed it:
if start_year != init_year:
    save_start_year(user_email, start_year)
st.title("TFSA Contribution Tracker")


limit = get_total_limit(start_year)
st.write(f"Your total TFSA room based on CRA limits: **${limit:,}**")

# Form to add contribution
with st.form("Add Transaction"):
    date = st.date_input("Date", datetime.date.today())
    transaction_type = st.selectbox("Type", ["Deposit", "Withdrawal"])
    institution    = st.text_input("Institution", "Wealthsimple")
    amount         = st.number_input("Amount ($)", min_value=0.0, step=100.0)
    submitted      = st.form_submit_button("Add")

    if submitted:
        signed_amount = amount if transaction_type == "Deposit" else -amount
        save_row(date, institution, signed_amount)
        # No further st.stop() here; save_row handles the rerun/stop.
st_autorefresh(interval=3_0000, limit=None, key="datarefresher")
# Load and format data
df = load_data()
df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
df = df.dropna(subset=["Date"])
df["Year"] = df["Date"].dt.year
df.sort_values("Date", ascending=False, inplace=True)

current_year = datetime.datetime.now().year

# Contribution logic
deposits_by_year = df[df["Amount"] > 0].groupby("Year")["Amount"].sum()
withdrawals_by_year = df[df["Amount"] < 0].groupby("Year")["Amount"].sum().abs()

room_used = 0
carry_forward = 0

for year in range(start_year, current_year + 1):
    limit_year = TFSA_LIMITS.get(year, 0)
    deposit = deposits_by_year.get(year, 0)
    withdrawal = withdrawals_by_year.get(year - 1, 0) if year > start_year else 0

    room_this_year = limit_year + carry_forward + withdrawal
    room_used += deposit
    carry_forward = max(room_this_year - deposit, 0)

# Show summary
current_year_deposits = deposits_by_year.get(current_year, 0)
room_remaining = limit + withdrawals_by_year.loc[withdrawals_by_year.index < current_year].sum() - room_used

st.subheader("Contribution Overview")
draw_contribution_bar_plotly(room_used, limit, withdrawals_by_year.sum())

if room_used > limit:
    st.error("You have OVER-CONTRIBUTED to your TFSA")

# Show transaction table
st.subheader("All Transactions")
st.dataframe(df[["Date", "Institution", "Amount"]])

# Deletion options
if not df.empty:
    delete_label = st.selectbox(
    "Select a transaction to delete",
    df.apply(lambda r: f"{r['Date'].date()} – {r['Institution']} – ${r['Amount']}", axis=1)
)
# Delete one row
if st.button("Delete Selected Row"):
    row = df[
        df.apply(
            lambda r: f"{r['Date'].date()} – {r['Institution']} – ${r['Amount']}",
            axis=1
        ) == delete_label
    ].iloc[0]
    delete_row(row["id"])
    st.success("Deleted!")
    st_autorefresh(interval=1_000, limit=None, key="datarefresher2")
    

# Clear all data (now at top‐level, not inside the delete block)
if st.button("Clear All Data"):
    clear_all_data()
    st.success("All data cleared!")
    st_autorefresh(interval=1_000, limit=None, key="datarefresher3")

import streamlit as st
import pandas as pd
import datetime
import plotly.graph_objects as go
from supabase import create_client, Client
from streamlit_autorefresh import st_autorefresh

# ─── 1) PAGE CONFIG ───────────────────────────────────────────────
st.set_page_config(page_title="TFSA Tracker", layout="centered")

# ─── 2) SUPABASE CLIENT ────────────────────────────────────────────
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─── 3) TFSA LIMITS ────────────────────────────────────────────────
TFSA_LIMITS = {
    2009: 5000, 2010: 5000, 2011: 5000,
    2012: 5000, 2013: 5500, 2014: 5500,
    2015: 10000, 2016: 5500, 2017: 5500,
    2018: 5500, 2019: 6000, 2020: 6000,
    2021: 6000, 2022: 6000, 2023: 6500,
    2024: 7000, 2025: 7000
}

# ─── 4) SESSION‐STATE INITIALIZATION ───────────────────────────────
if "user_email" not in st.session_state:
    st.session_state.user_email = ""

if "start_year" not in st.session_state:
    st.session_state.start_year = 2009

# ─── 5) AUTHENTICATE BY EMAIL ──────────────────────────────────────
user_email = st.text_input(
    "Enter your email to load your TFSA data",
    value=st.session_state.user_email
)
st.session_state.user_email = user_email

if not user_email:
    st.stop()

# ─── 6) LOAD & SAVE USER SETTINGS (start_year) ─────────────────────
def load_start_year(email: str) -> int:
    resp = (
        supabase.table("user_settings")
                .select("start_year")
                .eq("user_email", email)
                .execute()
    )
    if resp.data:
        return resp.data[0]["start_year"]
    # no row => default to 2009
    return 2009

def save_start_year(email: str, year: int):
    supabase.table("user_settings") \
            .upsert({"user_email": email, "start_year": year}) \
            .execute()

# On first load, override session_state from database
initial_year = load_start_year(user_email)
if initial_year in TFSA_LIMITS.keys():
    st.session_state.start_year = initial_year

# present the select box (connected to session_state)
years = list(TFSA_LIMITS.keys())
default_idx = years.index(st.session_state.start_year)
start_year = st.selectbox(
    "What year did you become eligible for TFSA?",
    years,
    index=default_idx,
    key="start_year"   # binds to st.session_state.start_year
)

# If the user changed it, save back to Supabase
if start_year != initial_year:
    save_start_year(user_email, start_year)

st.title("TFSA Contribution Tracker")

# ─── 7) UTILITY FUNCTIONS ──────────────────────────────────────────
@st.cache_data(ttl=10)
def load_data(email: str) -> pd.DataFrame:
    """
    Fetch all contributions for this user_email.
    Relies on RLS policy (user_email = auth.jwt() ->> 'email').
    """
    resp = (
        supabase
        .table("contributions")
        .select("*")
        .eq("user_email", email)
        .execute()
    )
    data = resp.data or []
    if not data:
        # Return empty DataFrame with expected columns
        return pd.DataFrame(columns=["id","Date","Institution","Amount"])
    df = pd.DataFrame(data)
    # Normalize column names
    df["Date"]        = pd.to_datetime(df["date"])
    df["Institution"] = df["institution"]
    df["Amount"]      = df["amount"]
    return df[["id","Date","Institution","Amount"]]

def save_row(date: datetime.date, institution: str, amount: float):
    """
    Insert a new TFSA row tied to this user_email.
    RLS ensures only rows where user_email=auth.jwt() ->> 'email' are accepted.
    """
    payload = {
        "user_email":  user_email,
        "date":        date.isoformat(),
        "institution": institution,
        "amount":      float(amount)
    }
    supabase.table("contributions").insert(payload).execute()
    # Invalidate cache so next load_data fetches fresh
    load_data.clear()

def delete_row(row_id: str):
    """
    Delete a single row by id, but only if user_email matches (RLS).
    """
    supabase.table("contributions").delete() \
            .eq("id", row_id) \
            .eq("user_email", user_email) \
            .execute()
    load_data.clear()

def clear_all_data():
    """
    Delete all rows for this user_email (RLS protects against others).
    """
    supabase.table("contributions").delete() \
            .eq("user_email", user_email) \
            .execute()
    load_data.clear()

def get_total_limit(start_year: int) -> int:
    this_year = datetime.datetime.now().year
    return sum(TFSA_LIMITS[y] for y in range(start_year, this_year + 1))

def draw_contribution_bar_plotly(contributed: float, limit: float, withdrawal: float):
    percent_used = (contributed / limit) * 100 if limit > 0 else 0
    remaining = max(limit - contributed, 0)

    fig = go.Figure()
    # Grey background bar (total room)
    fig.add_trace(go.Bar(
        x=["TFSA Room"], y=[limit],
        marker_color='lightgrey', width=[0.4], opacity=0.3,
        hoverinfo='skip'
    ))
    # Red foreground bar (contributed)
    fig.add_trace(go.Bar(
        x=["TFSA Room"], y=[contributed],
        marker_color='crimson', width=[0.4],
        text=f"{percent_used:.1f}%", textposition="inside",
        hovertemplate=f"Deposited: ${contributed:,.2f}<br>Limit: ${limit:,.2f}<extra></extra>"
    ))
    fig.update_layout(
        title="TFSA Contribution Progress",
        barmode="overlay",
        yaxis=dict(title="Amount ($)", range=[0, limit]),
        xaxis=dict(showticklabels=False),
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        height=450, margin=dict(l=40, r=20, t=40, b=40)
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

# ─── 8) MAIN UI ─────────────────────────────────────────────────────

# 8.1: Show the lifetime TFSA room
total_limit = get_total_limit(start_year)
st.write(f"Your total TFSA room based on CRA limits: **${total_limit:,}**")

# 8.2: “Add Transaction” form
with st.form("Add Transaction"):
    date = st.date_input("Date", datetime.date.today())
    transaction_type = st.selectbox("Transaction Type", ["Deposit", "Withdrawal"])
    institution = st.text_input("Institution", "Wealthsimple")
    amount = st.number_input("Amount ($)", min_value=0.0, step=100.0)
    submitted = st.form_submit_button("Add")

    if submitted:
        signed_amt = amount if transaction_type == "Deposit" else -amount
        save_row(date, institution, signed_amt)
        st.success("✅ Transaction recorded.")

# 8.3: Auto‐refresh only the data section every 10 seconds
st_autorefresh(interval=10_000, limit=None, key="datarefresher")

# 8.4: Load & process data
df = load_data(user_email)
# Ensure “Date” column exists (empty df will still have columns)
if not df.empty:
    df["Year"] = df["Date"].dt.year
    df.sort_values("Date", ascending=False, inplace=True)

    current_year = datetime.datetime.now().year
    deposits_by_year = df[df["Amount"] > 0].groupby("Year")["Amount"].sum()
    withdrawals_by_year = df[df["Amount"] < 0].groupby("Year")["Amount"].sum().abs()

    # Calculate room used and carry forward
    room_used = 0
    carry_forward = 0
    for yr in range(start_year, current_year + 1):
        limit_year = TFSA_LIMITS.get(yr, 0)
        deposit = deposits_by_year.get(yr, 0)
        withdrawal = withdrawals_by_year.get(yr - 1, 0) if yr > start_year else 0
        room_this_year = limit_year + carry_forward + withdrawal
        room_used += deposit
        carry_forward = max(room_this_year - deposit, 0)

    room_remaining = total_limit + withdrawals_by_year.loc[withdrawals_by_year.index < current_year].sum() - room_used

    # 8.5: Display summary & chart
    st.subheader("📊 Contribution Overview")
    draw_contribution_bar_plotly(room_used, total_limit, withdrawals_by_year.sum())

    if room_used > total_limit:
        st.error("⚠️ You have OVER‐CONTRIBUTED to your TFSA")

    # 8.6: Show transaction table
    st.subheader("📄 All Transactions")
    st.dataframe(df[["Date", "Institution", "Amount"]])

    # 8.7: Deletion options
    delete_label = st.selectbox(
        "Select a transaction to delete",
        df.apply(lambda r: f"{r['Date'].date()} – {r['Institution']} – ${r['Amount']}", axis=1)
    )
    if st.button("🗑️ Delete Selected Row"):
        row = df[
            df.apply(lambda r: f"{r['Date'].date()} – {r['Institution']} – ${r['Amount']}", axis=1) == delete_label
        ].iloc[0]
        delete_row(row["id"])
        st.success("Deleted ✅")

    if st.button("❌ Clear All Data"):
        clear_all_data()
        st.success("All data cleared ✅")

else:
    # df is empty
    st.info("No transactions yet. Use the form above to add one.")

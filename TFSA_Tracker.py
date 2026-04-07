import datetime
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from supabase import Client, create_client

st.set_page_config(page_title="TFSA Tracker", layout="wide")


SUPABASE_URL = os.environ["SUPABASE_URL"].strip()
SUPABASE_KEY = os.environ["SUPABASE_KEY"].strip()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Annual TFSA limits published by CRA.
# For years not yet listed here, reuse the latest known limit.
TFSA_LIMITS = {
    2009: 5000,
    2010: 5000,
    2011: 5000,
    2012: 5000,
    2013: 5500,
    2014: 5500,
    2015: 10000,
    2016: 5500,
    2017: 5500,
    2018: 5500,
    2019: 6000,
    2020: 6000,
    2021: 6000,
    2022: 6000,
    2023: 6500,
    2024: 7000,
    2025: 7000,
}
BASE_TFSA_YEAR = min(TFSA_LIMITS.keys())


def get_tfsa_limit_for_year(year: int) -> int:
    if year in TFSA_LIMITS:
        return TFSA_LIMITS[year]
    if year > max(TFSA_LIMITS.keys()):
        latest_known_year = max(TFSA_LIMITS.keys())
        return TFSA_LIMITS[latest_known_year]
    return 0


def load_start_year(email: str) -> int:
    resp = (
        supabase.table("user_settings")
        .select("start_year")
        .eq("user_email", email)
        .execute()
    )
    if resp.data:
        return resp.data[0]["start_year"]
    return 2009


def save_start_year(email: str, year: int) -> None:
    supabase.table("user_settings").upsert(
        {"user_email": email, "start_year": year}
    ).execute()


def load_data(email: str) -> pd.DataFrame:
    resp = supabase.table("contributions").select("*").eq("user_email", email).execute()
    data = resp.data or []

    if not data:
        return pd.DataFrame(columns=["id", "Date", "Institution", "Amount"])

    df = pd.DataFrame(data)
    df["Date"] = pd.to_datetime(df["date"])
    df["Institution"] = df["institution"]
    df["Amount"] = df["amount"]
    return df[["id", "Date", "Institution", "Amount"]]


def save_row(email: str, date: datetime.date, institution: str, amount: float) -> None:
    payload = {
        "user_email": email,
        "date": date.isoformat(),
        "institution": institution,
        "amount": float(amount),
    }
    supabase.table("contributions").insert(payload).execute()


def delete_row(email: str, row_id: int) -> None:
    (
        supabase.table("contributions")
        .delete()
        .eq("id", row_id)
        .eq("user_email", email)
        .execute()
    )


def clear_all_data(email: str) -> None:
    supabase.table("contributions").delete().eq("user_email", email).execute()


def get_total_limit(start_year: int) -> int:
    current_year = datetime.datetime.now().year
    return sum(get_tfsa_limit_for_year(y) for y in range(start_year, current_year + 1))


def build_progress_chart(contributed: float, limit: float) -> go.Figure:
    percent_used = (contributed / limit) * 100 if limit else 0

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=["Contribution Room"],
            y=[limit],
            marker_color="#E5E7EB",
            hoverinfo="skip",
            name="Total Room",
            width=[0.45],
        )
    )
    fig.add_trace(
        go.Bar(
            x=["Contribution Room"],
            y=[contributed],
            marker_color="#0F766E",
            text=f"{percent_used:.1f}% used",
            textposition="inside",
            hovertemplate="Used: $%{y:,.2f}<extra></extra>",
            name="Used",
            width=[0.45],
        )
    )

    fig.update_layout(
        barmode="overlay",
        height=350,
        margin=dict(l=12, r=12, t=12, b=12),
        xaxis=dict(showgrid=False, showticklabels=False),
        yaxis=dict(title="CAD", showgrid=True, gridcolor="#E5E7EB"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def apply_app_style() -> None:
    st.markdown(
        """
        <style>
            .block-container {padding-top: 2rem; padding-bottom: 2rem;}
            .app-title {font-size: 2rem; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 0.25rem;}
            .app-subtitle {color: #4B5563; margin-bottom: 1.25rem;}
            .section-card {
                border: 1px solid #E5E7EB;
                border-radius: 14px;
                padding: 1rem;
                background: #FFFFFF;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


apply_app_style()

if "user_email" not in st.session_state:
    st.session_state.user_email = ""

st.markdown('<div class="app-title">TFSA Tracker</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="app-subtitle">Simple, clear tracking for your TFSA contribution room.</div>',
    unsafe_allow_html=True,
)

user_email = st.text_input(
    "Email", value=st.session_state.user_email, placeholder="name@email.com"
).strip().lower()
st.session_state.user_email = user_email

if not user_email:
    st.info("Enter your email to load your profile.")
    st.stop()

init_year = load_start_year(user_email)
current_year = datetime.datetime.now().year
years = list(range(BASE_TFSA_YEAR, current_year + 1))
default_idx = years.index(init_year) if init_year in years else 0

controls_col1, controls_col2 = st.columns([2, 1])
with controls_col1:
    start_year = st.selectbox(
        "TFSA eligibility year",
        years,
        index=default_idx,
        help="The first year you were eligible for TFSA contribution room.",
    )
with controls_col2:
    st.markdown("<div style='height: 1.9rem'></div>", unsafe_allow_html=True)
    if st.button("Refresh data", use_container_width=True):
        st.rerun()

if start_year != init_year:
    save_start_year(user_email, start_year)

limit = get_total_limit(start_year)
df = load_data(user_email)
df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
df = df.dropna(subset=["Date"]).copy()
df["Year"] = df["Date"].dt.year
df.sort_values("Date", ascending=False, inplace=True)

deposits_by_year = df[df["Amount"] > 0].groupby("Year")["Amount"].sum()
withdrawals_by_year = df[df["Amount"] < 0].groupby("Year")["Amount"].sum().abs()

room_used = deposits_by_year.sum()
total_withdrawals = withdrawals_by_year.sum()
withdrawals_prior_to_current = withdrawals_by_year.loc[
    withdrawals_by_year.index < current_year
].sum()
remaining_room = max(limit + withdrawals_prior_to_current - room_used, 0)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total room", f"${limit:,.0f}")
m2.metric("Contributed", f"${room_used:,.0f}")
m3.metric("Withdrawn", f"${total_withdrawals:,.0f}")
m4.metric("Remaining", f"${remaining_room:,.0f}")

chart_col, action_col = st.columns([2, 1])
with chart_col:
    st.markdown("#### Contribution Overview")
    st.plotly_chart(build_progress_chart(room_used, limit), use_container_width=True)
    if room_used > limit:
        st.error("Potential over-contribution detected. Please review your records.")

with action_col:
    st.markdown("#### Add transaction")
    with st.form("add_transaction", clear_on_submit=True):
        date = st.date_input("Date", datetime.date.today())
        transaction_type = st.radio("Type", ["Deposit", "Withdrawal"], horizontal=True)
        institution = st.text_input("Institution", "Wealthsimple")
        amount = st.number_input("Amount (CAD)", min_value=0.0, step=100.0)
        submitted = st.form_submit_button("Save", use_container_width=True)

        if submitted:
            signed_amount = amount if transaction_type == "Deposit" else -amount
            try:
                save_row(user_email, date, institution, signed_amount)
                st.success("Transaction recorded.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not save transaction: {exc}")

st.markdown("#### Transaction history")

if df.empty:
    st.info("No transactions yet.")
else:
    st.dataframe(
        df[["Date", "Institution", "Amount"]],
        use_container_width=True,
        hide_index=True,
    )

    options = df.apply(
        lambda r: f"{r['Date'].date()} • {r['Institution']} • ${r['Amount']:,.2f}", axis=1
    ).tolist()

    del_col1, del_col2 = st.columns([3, 1])
    with del_col1:
        delete_label = st.selectbox("Select transaction to delete", options)
    with del_col2:
        st.markdown("<div style='height: 1.8rem'></div>", unsafe_allow_html=True)
        if st.button("Delete selected", use_container_width=True):
            row = df[
                df.apply(
                    lambda r: f"{r['Date'].date()} • {r['Institution']} • ${r['Amount']:,.2f}",
                    axis=1,
                )
                == delete_label
            ].iloc[0]
            delete_row(user_email, int(row["id"]))
            st.success("Transaction deleted.")
            st.rerun()

if st.button("Clear all transactions", type="secondary"):
    clear_all_data(user_email)
    st.success("All transactions cleared.")
    st.rerun()

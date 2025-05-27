import streamlit as st
import pandas as pd
import datetime
import plotly.graph_objects as go

st.set_page_config(page_title="TFSA Tracker", layout="centered")

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
# Helper functions
def get_total_limit(start_year):
    current_year = datetime.datetime.now().year
    return sum([TFSA_LIMITS.get(y, 0) for y in range(start_year, current_year + 1)])

def load_data():
    try:
        return pd.read_csv("contributions.csv")
    except:
        return pd.DataFrame(columns=["Date", "Institution", "Amount"])

def save_data(df):
    df.to_csv("contributions.csv", index=False)

def draw_contribution_bar_plotly(contributed, limit, withdrawal):
    percent_used = (contributed / limit) * 100 if limit > 0 else 0
    remaining = max(limit - contributed, 0)

    fig = go.Figure()

    # Grey background (total room)
    fig.add_trace(go.Bar(
        x=["TFSA Room"],
        y=[limit],
        marker_color='lightgrey',
        width=[0.4],
        opacity=0.3,
        name="Limit",
        hoverinfo='skip'
    ))

    # Red bar (contributed)
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

    # Split chart and info in two columns
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
# Main app
st.title("TFSA Contribution Tracker")

start_year = st.selectbox("What year did you become eligible for TFSA?", list(TFSA_LIMITS.keys()))
limit = get_total_limit(start_year)
st.write(f"Your total TFSA room based on CRA limits: **${limit:,}**")

# Form to add contributions
with st.form("Add Transaction"):
    date = st.date_input("Date", value=datetime.date.today())
    transaction_type = st.selectbox("Transaction Type", ["Deposit", "Withdrawal"])
    institution = st.text_input("Institution", "Wealthsimple")
    amount = st.number_input("Amount ($)", min_value=0.0, step=100.0)
    submitted = st.form_submit_button("Add")

    if submitted:
        df = load_data()
        signed_amount = amount if transaction_type == "Deposit" else -amount
        new_row = {"Date": date, "Institution": institution, "Amount": signed_amount}
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        save_data(df)
        st.success(f"{transaction_type} recorded!")

# Load and format data
df = load_data()
df["Date"] = pd.to_datetime(df["Date"])
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
    st.error("⚠️ You have OVER-CONTRIBUTED to your TFSA")

# Show table
st.subheader("📄 All Transactions")
st.dataframe(df[["Date", "Institution", "Amount"]])

# Add deletion options

if not df.empty:
    

    delete_row = st.selectbox("Select a transaction to delete", df.apply(lambda row: f"{row['Date'].date()} - {row['Institution']} - ${row['Amount']}", axis=1))
    if st.button("🗑️ Delete Selected Row"):
        idx_to_delete = df.index[df.apply(lambda row: f"{row['Date'].date()} - {row['Institution']} - ${row['Amount']}", axis=1) == delete_row][0]
        df = df.drop(index=idx_to_delete).reset_index(drop=True)
        save_data(df)
        st.success("Selected row deleted.")
        st.stop()
    if st.button("❌ Clear All Data"):
        save_data(pd.DataFrame(columns=["Date", "Institution", "Amount"]))
        st.success("All data cleared!")
        st.stop()    
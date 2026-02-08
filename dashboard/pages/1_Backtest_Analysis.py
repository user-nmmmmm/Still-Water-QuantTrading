import streamlit as st
import pandas as pd
import plotly.express as px
import os

st.set_page_config(page_title="Backtest Analysis", page_icon="📊", layout="wide")

st.title("📊 Backtest Analysis")

REPORTS_DIR = "reports"

# Helper to load reports
def get_reports():
    if not os.path.exists(REPORTS_DIR):
        return []
    # List directories
    dirs = [d for d in os.listdir(REPORTS_DIR) if os.path.isdir(os.path.join(REPORTS_DIR, d))]
    # Sort by name (date) desc
    dirs.sort(reverse=True)
    return dirs

reports = get_reports()

if not reports:
    st.warning("No reports found in `reports/` directory.")
else:
    selected_report = st.selectbox("Select Report", reports)
    
    report_path = os.path.join(REPORTS_DIR, selected_report)
    
    # Load Data
    equity_file = os.path.join(report_path, "equity.csv")
    trades_file = os.path.join(report_path, "trades.csv")
    report_file = os.path.join(report_path, "report.txt")
    
    # 1. Show Report Summary
    if os.path.exists(report_file):
        with st.expander("📝 Report Summary", expanded=True):
            with open(report_file, "r", encoding='utf-8') as f:
                content = f.read()
            st.text(content)
        
    # 2. Equity Curve
    if os.path.exists(equity_file):
        st.subheader("📈 Equity Curve")
        try:
            df_equity = pd.read_csv(equity_file)
            if not df_equity.empty and 'datetime' in df_equity.columns:
                df_equity['datetime'] = pd.to_datetime(df_equity['datetime'])
                
                fig = px.line(df_equity, x='datetime', y='equity', title='Portfolio Equity')
                st.plotly_chart(fig, use_container_width=True)
                
                # Drawdown
                if 'drawdown_pct' in df_equity.columns:
                    df_equity['drawdown'] = df_equity['drawdown_pct'] * 100
                    fig_dd = px.area(df_equity, x='datetime', y='drawdown', title='Drawdown (%)', color_discrete_sequence=['red'])
                    st.plotly_chart(fig_dd, use_container_width=True)
        except Exception as e:
            st.error(f"Error loading equity curve: {e}")

    # 3. Trade Log
    if os.path.exists(trades_file):
        st.subheader("📋 Trade Log")
        try:
            df_trades = pd.read_csv(trades_file)
            st.dataframe(df_trades, use_container_width=True)
        except Exception as e:
            st.error(f"Error loading trade log: {e}")

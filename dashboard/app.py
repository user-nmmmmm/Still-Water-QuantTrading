import streamlit as st

st.set_page_config(
    page_title="QuantTrading Dashboard",
    page_icon="📈",
    layout="wide"
)

st.title("QuantTrading System Dashboard 📈")

st.markdown("""
Welcome to the **QuantTrading System Dashboard**.

Use the sidebar to navigate between modules:

- **📊 Backtest Analysis**: Analyze historical performance reports, equity curves, and trade logs.
- **⚡ Live Monitor**: Monitor real-time trading status, positions, and PnL.

### System Status
- **Environment**: Windows
- **Date**: 2026-02-08
""")

st.sidebar.success("Select a page above.")

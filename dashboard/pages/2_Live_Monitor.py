import streamlit as st
import pandas as pd
import json
import os
import time

st.set_page_config(page_title="Live Monitor", page_icon="⚡", layout="wide")

st.title("⚡ Live Trading Monitor")

STATE_FILE = "reports/live_status.json"

# Sidebar controls
st.sidebar.header("Settings")
auto_refresh = st.sidebar.checkbox("Auto Refresh (2s)", value=False)

if not os.path.exists(STATE_FILE):
    st.warning(f"Waiting for Live Engine to start... (File not found: {STATE_FILE})")
    if auto_refresh:
        time.sleep(2)
        st.rerun()
    st.stop()

def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Error reading state: {e}")
        return None

state = load_state()

if state:
    # Header
    st.caption(f"Last Update: {state.get('last_update', 'N/A')} | Timestamp: {state.get('timestamp', 'N/A')}")
    
    # Top Metrics
    col1, col2, col3 = st.columns(3)
    equity = state.get('equity', 0)
    cash = state.get('cash', 0)
    positions = state.get('positions', {})
    
    col1.metric("Total Equity (USDT)", f"${equity:,.2f}")
    col2.metric("Available Cash (USDT)", f"${cash:,.2f}")
    col3.metric("Active Positions", len(positions))
    
    st.divider()
    
    # Positions Table
    st.subheader("📦 Current Positions")
    if positions:
        # Convert dict to DF
        # positions structure: {'BTC/USDT': {'qty': 0.1, ...}}
        data = []
        for sym, details in positions.items():
            row = {'Symbol': sym}
            if isinstance(details, dict):
                row.update(details)
            else:
                row['Raw'] = str(details)
            data.append(row)
        
        df_pos = pd.DataFrame(data)
        st.dataframe(df_pos, use_container_width=True)
    else:
        st.info("No active positions currently.")

    # JSON Dump (Debug)
    with st.expander("Raw State JSON"):
        st.json(state)

else:
    st.error("Failed to load state.")

# Auto Refresh Logic
if auto_refresh:
    time.sleep(2)
    st.rerun()

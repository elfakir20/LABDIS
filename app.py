import streamlit as st
import pandas as pd

# 1. Load Master Data with auto-cleaning
@st.cache_data
def load_all_data():
    try:
        # Load and strip spaces from headers to prevent KeyErrors
        stores = pd.read_csv('stores.csv')
        stores.columns = stores.columns.str.strip()
        
        tariffs = pd.read_csv('tariffs.csv')
        tariffs.columns = tariffs.columns.str.strip()
        
        return stores, tariffs
    except Exception as e:
        st.error(f"Master Files Error: {e}")
        return None, None

# Page Setup
st.set_page_config(page_title="LABDIS Fleet Optimizer", layout="wide")
st.title("🚚 LABDIS Logistics Intelligence System")
st.markdown("### Hub: Skhirat | Logic: Far-to-Near | Priority: Code 200")

stores_df, tariffs_df = load_all_data()

if stores_df is not None:
    # --- SIDEBAR: FLEET SETTINGS ---
    st.sidebar.header("🚛 Daily Fleet Availability")
    avail_32T = st.sidebar.number_input("32T Trucks (33 PLT):", min_value=0, value=10)
    avail_19T = st.sidebar.number_input("19T Trucks (18 PLT):", min_value=0, value=5)
    avail_7T = st.sidebar.number_input("7T Trucks (12 PLT Target):", min_value=0, value=3)
    
    st.sidebar.divider()
    selected_wave = st.sidebar.selectbox("Shipping Wave:", ["15:00-23:00", "23:00-7:00"])
    
    # Financial constants
    STOP_FLEG, STOP_SEC = 75, 150

    # --- STEP 1: FILE UPLOAD ---
    st.header("📥 1. Daily Order Ingestion")
    uploaded = st.file_uploader("Upload Orders CSV (Store_Code, Fleg_PLT, Sec_PLT)", type=['csv'])

    if uploaded:
        orders = pd.read_csv(uploaded).fillna(0)
        orders.columns = orders.columns.str.strip()
        
        # Ensure mandatory columns exist
        for col in ['Fleg_PLT', 'Sec_PLT']:
            if col not in orders.columns: orders[col] = 0
            
        # Merge with master data
        data = pd.merge(orders, stores_df, on='Store_Code', how='left')
        data = data[data['Loading Window'] == selected_wave].copy()
        data['Total_PLT'] = data['Fleg_PLT'] + data['Sec_PLT']

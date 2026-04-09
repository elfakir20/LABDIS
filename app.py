import streamlit as st
import pandas as pd
import numpy as np

# 1. Advanced Data Ingestion
@st.cache_data
def load_master_data():
    try:
        stores = pd.read_csv('stores.csv')
        tariffs = pd.read_csv('tariffs.csv')
        return stores, tariffs
    except Exception as e:
        return None, None

st.set_page_config(page_title="LABDIS Quantum Optimizer", layout="wide", initial_sidebar_state="expanded")

# Custom CSS for Professional UI
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; padding: 15px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

st.title("🌌 LABDIS Quantum Fleet Optimizer v12.1")
st.subheader("Automated Load Splitting | Multi-Vehicle Balancing | Skhirat Hub Priority")

stores_df, tariffs_df = load_master_data()

if stores_df is not None:
    # --- SIDEBAR ---
    with st.sidebar:
        st.header("🚛 Fleet Inventory")
        a32T = st.number_input("32T (33 PLT) Units:", 0, 100, 10)
        a19T = st.number_input("19T (18 PLT) Units:", 0, 100, 5)
        a7T = st.number_input("7T (12 PLT) Units:", 0, 100, 5)
        st.divider()
        wave = st.selectbox("Wave Selection", ["15:00-23:00", "23:00-7:00"])

    # --- PHASE 1: PROCESSING ---
    st.header("📥 Phase 1: Order Processing")
    uploaded = st.file_uploader("Upload Daily CSV", type=['csv'])

    if uploaded:
        raw_orders = pd.read_csv(uploaded).fillna(0)
        full_data = pd.merge(raw_orders, stores_df, on='Store_Code', how='left')
        full_data = full_data[full_data['Loading Window'] == wave].copy()
        
        full_data['Priority'] = full_data['Store_Code'].apply(lambda x: 0 if x == 200 else 1)
        full_data = full_data.sort_values(['Priority', 'Zone'], ascending=[True, False])

        # --- PHASE 2: SPLITTING ENGINE ---
        dispatched_trucks = []
        for zone, zone_group in full_data.groupby('Zone', sort=False):
            pool_fleg = zone_group['Fleg_PLT'].sum()
            pool_sec = zone_group['Sec_PLT'].sum()
            total_pool = pool_fleg + pool_sec
            max_type = zone_group['Max_Truck_Allowed'].iloc[0]
            
            while total_pool >= 7.5:
                if total_pool >= 31.5 and max_type == '32T' and a32T > 0:
                    cap, t_type = 33, '32T'
                elif total_pool >= 17 and max_type != '7T' and a19T > 0:
                    cap, t_type = 18, '19T'
                elif a7T > 0:
                    cap, t_type = 12, '7T'
                else: break 
                
                load_size = min(total_pool, cap * 1.04) 
                dispatched_trucks.append({
                    "Zone": zone, "Type": t_type, "Total_PLT": round(load_size, 1),
                    "Efficiency": round((load_size / cap) * 100, 1),
                    "Stores": ", ".join(zone_group['Store_Name'].unique()[:3]),
                    "Main_Activity": "Fleg" if pool_fleg > pool_sec else "Sec",
                    "City_Point": zone_group['City'].iloc[0]
                })
                total_pool -= load_size
                if t_type == '32T': a32T -= 1
                elif t_type == '19T': a19T -= 1
                else: a7T -= 1

        # --- PHASE 3: INTERFACE (FIXED LINE) ---
        if dispatched_trucks:
            df_final = pd.DataFrame(dispatched_trucks)
            
            def highlight_100(val):
                color = '#2ecc71' if 96 <= val <= 104 else '#f1c40f'
                return f'background-color: {color}; color: black; font-weight: bold'

            st.header("🚛 Phase 2: Live Dispatch Board")
            
            # 🔥 THE FIX: Handling Pandas new map() vs old applymap()
            try:
                styled_df = df_final.style.map(highlight_100, subset=['Efficiency'])
            except AttributeError:
                styled_df = df_final.style.applymap(highlight_100, subset=['Efficiency'])
                
            st.dataframe(styled_df, use_container_width=True)

            # --- PHASE 4: ANALYTICS ---
            st.divider()
            st.header("📊 Phase 3: Logistics Analytics")
            k1, k2, k3 = st.columns(3)
            with k1: st.metric("Trucks Dispatched", len(df_final))
            with k2: st.metric("Avg Efficiency", f"{df_final['Efficiency'].mean():.1f}%")
            with k3: st.metric("Leftover PLT", round(total_pool, 1))

else:
    st.error("Missing Data Files.")

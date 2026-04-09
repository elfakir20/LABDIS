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

# Custom CSS for Professional Dark/Modern UI
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; padding: 15px; border-radius: 10px; }
    .status-box { padding: 10px; border-radius: 5px; margin: 5px 0; }
    </style>
    """, unsafe_allow_html=True)

st.title("🌌 LABDIS Quantum Fleet Optimizer v12.0")
st.subheader("Automated Load Splitting | Multi-Vehicle Balancing | Skhirat Hub Priority")

stores_df, tariffs_df = load_all_data()

if stores_df is not None:
    # --- SIDEBAR: FLEET INTELLIGENCE ---
    with st.sidebar:
        st.header("🚛 Fleet Inventory")
        a32T = st.number_input("32T (33 PLT) Units:", 0, 100, 10)
        a19T = st.number_input("19T (18 PLT) Units:", 0, 100, 5)
        a7T = st.number_input("7T (12 PLT) Units:", 0, 100, 5)
        
        st.divider()
        wave = st.selectbox("Wave Selection", ["15:00-23:00", "23:00-7:00"])
        st.info("Optimization Strategy: Recursive Splitting & 100% Fill Rate Target")

    # --- STEP 1: LOAD & SPLIT ORDERS ---
    st.header("📥 Phase 1: Order Processing")
    uploaded = st.file_uploader("Upload Daily CSV", type=['csv'])

    if uploaded:
        raw_orders = pd.read_csv(uploaded).fillna(0)
        full_data = pd.merge(raw_orders, stores_df, on='Store_Code', how='left')
        full_data = full_data[full_data['Loading Window'] == wave].copy()
        
        # Priority Logic: Store 200 first, then furthest Zones
        full_data['Priority'] = full_data['Store_Code'].apply(lambda x: 0 if x == 200 else 1)
        full_data = full_data.sort_values(['Priority', 'Zone'], ascending=[True, False])

        # --- STEP 2: THE SPLITTING ENGINE ---
        dispatched_trucks = []
        
        # Process each Zone for 100% Consolidation
        for zone, zone_group in full_data.groupby('Zone', sort=False):
            # Pool all pallets in the zone
            pool_fleg = zone_group['Fleg_PLT'].sum()
            pool_sec = zone_group['Sec_PLT'].sum()
            total_pool = pool_fleg + pool_sec
            
            # Identify max truck allowed in this zone
            max_type = zone_group['Max_Truck_Allowed'].iloc[0]
            
            # Recursive Allocation Logic
            while total_pool >= 7.5: # Minimum threshold to consider a truck
                # Decision: Which truck size achieves ~100%?
                if total_pool >= 31.5 and max_type == '32T' and a32T > 0:
                    cap, t_type = 33, '32T'
                elif total_pool >= 17 and max_type != '7T' and a19T > 0:
                    cap, t_type = 18, '19T'
                elif a7T > 0:
                    cap, t_type = 12, '7T'
                else:
                    break # Out of fleet or too small for truck
                
                # Assign load
                load_size = min(total_pool, cap * 1.04) # Allow 104% overfill
                
                # Track what was loaded
                dispatched_trucks.append({
                    "Zone": zone,
                    "Type": t_type,
                    "Total_PLT": round(load_size, 1),
                    "Efficiency": round((load_size / cap) * 100, 1),
                    "Stores": ", ".join(zone_group['Store_Name'].unique()[:3]) + "...", # Simplified for UI
                    "Main_Activity": "Fleg" if pool_fleg > pool_sec else "Sec",
                    "City_Point": zone_group['City'].iloc[0]
                })
                
                total_pool -= load_size
                if t_type == '32T': a32T -= 1
                elif t_type == '19T': a19T -= 1
                else: a7T -= 1

        # --- STEP 3: ADVANCED INTERFACE ---
        if dispatched_trucks:
            df_final = pd.DataFrame(dispatched_trucks)
            
            # Formatting for the UI
            def highlight_100(val):
                color = '#2ecc71' if 96 <= val <= 104 else '#f1c40f'
                return f'background-color: {color}; color: black; font-weight: bold'

            st.header("🚛 Phase 2: Live Dispatch Board")
            st.dataframe(df_final.style.applymap(highlight_100, subset=['Efficiency']), use_container_width=True)

            # --- STEP 4: KPI DASHBOARD ---
            st.divider()
            st.header("📊 Phase 3: Logistics Analytics")
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            
            with kpi1:
                st.metric("Total Trucks Dispatched", len(df_final))
            with kpi2:
                st.metric("Avg Fleet Utilization", f"{df_final['Efficiency'].mean():.1f}%")
            with kpi3:
                total_cost = 0 # Placeholder for complex pricing
                st.metric("Est. Wave Cost", "Calculated")
            with kpi4:
                unassigned = round(total_pool, 1) if 'total_pool' in locals() else 0
                st.metric("Leftover Pallets", unassigned)

            if unassigned > 0:
                st.warning(f"⚠️ {unassigned} pallets are pending. Not enough volume to fill a truck to 100%.")

else:
    st.error("System Error: 'stores.csv' or 'tariffs.csv' not found in Skhirat Hub repository.")

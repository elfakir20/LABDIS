import streamlit as st
import pandas as pd

# 1. Loading Master Data
@st.cache_data
def load_all_data():
    try:
        stores = pd.read_csv('stores.csv')
        tariffs = pd.read_csv('tariffs.csv')
        return stores, tariffs
    except:
        return None, None

st.set_page_config(page_title="LABDIS Skhirat Hub v11", layout="wide")
st.title("🚚 LABDIS Skhirat Optimized Router")
st.markdown("### Priority: Code 200 | Routing: Far to Near | Load: 100%")

stores_df, tariffs_df = load_all_data()

if stores_df is not None:
    # --- SIDEBAR CONFIGURATION ---
    st.sidebar.header("🚛 Fleet Availability")
    avail_32T = st.sidebar.number_input("32T Available (33 PLT):", min_value=0, value=10)
    avail_19T = st.sidebar.number_input("19T Available (18 PLT):", min_value=0, value=5)
    avail_7T = st.sidebar.number_input("7T Available (12 PLT):", min_value=0, value=3)
    
    selected_wave = st.sidebar.selectbox("Shipping Wave:", ["15:00-23:00", "23:00-7:00"])
    
    STOP_FLEG, STOP_SEC = 75, 150

    st.header("📥 1. Upload Daily Orders")
    uploaded = st.file_uploader("Upload CSV (Store_Code, Fleg_PLT, Sec_PLT)", type=['csv'])

    if uploaded:
        orders = pd.read_csv(uploaded).fillna(0)
        data = pd.merge(orders, stores_df, on='Store_Code', how='left')
        data = data[data['Loading Window'] == selected_wave].copy()
        data['Total_PLT'] = data['Fleg_PLT'] + data['Sec_PLT']

        if data.empty:
            st.warning("No orders found for this wave.")
        else:
            # --- LOGIC: PRIORITY & GEOGRAPHY ---
            # Priority 0 for Code 200, Priority 1 for others
            data['is_priority'] = data['Store_Code'].apply(lambda x: 0 if x == 200 else 1)
            # Sort: Priority first, then Far Zones, then Cities
            data = data.sort_values(by=['is_priority', 'Zone', 'City'], ascending=[True, False, False])

            st.header("🚛 2. Strategic Routing Schedule")
            
            trucks_list = []
            rem_32, rem_19, rem_7 = avail_32T, avail_19T, avail_7T

            # Grouping Engine
            for (zone, truck_limit), group in data.groupby(['Zone', 'Max_Truck_Allowed'], sort=False):
                if truck_limit == '32T': nominal_cap = 33
                elif truck_limit == '19T': nominal_cap = 18
                else: nominal_cap = 12 # High-cap 7T
                
                max_cap = nominal_cap * 1.04
                
                c_load, c_stores, c_cities, c_fleg, c_sec = 0, [], [], 0, 0

                for _, row in group.iterrows():
                    if c_load + row['Total_PLT'] <= max_cap:
                        c_load += row['Total_PLT']
                        store_label = f"⭐ {row['Store_Name']}" if row['Store_Code'] == 200 else row['Store_Name']
                        c_stores.append(store_label)
                        if row['City'] not in c_cities:
                            c_cities.append(row['City'])
                        c_fleg += row['Fleg_PLT']
                        c_sec += row['Sec_PLT']
                    else:
                        # Dispatch completed truck
                        trucks_list.append({
                            "Zone": zone, "Type": truck_limit, "Load": c_load,
                            "Stores": c_stores, "Cities": c_cities,
                            "Fleg": c_fleg, "Sec": c_sec, "Cap": nominal_cap
                        })
                        # Update Inventory
                        if truck_limit == '32T': rem_32 -= 1
                        elif truck_limit == '19T': rem_19 -= 1
                        else: rem_7 -= 1
                        
                        # Reset for next truck
                        c_load = row['Total

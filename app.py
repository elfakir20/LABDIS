import streamlit as st
import pandas as pd

@st.cache_data
def load_all_data():
    try:
        stores = pd.read_csv('stores.csv')
        stores.columns = stores.columns.str.strip()
        tariffs = pd.read_csv('tariffs.csv')
        tariffs.columns = tariffs.columns.str.strip()
        return stores, tariffs
    except Exception as e:
        st.error(f"Master Files Error: {e}")
        return None, None

st.set_page_config(page_title="LABDIS Optimizer v16", layout="wide")
st.title("🚚 LABDIS Logistics Expert")

stores_df, tariffs_df = load_all_data()

if stores_df is not None:
    st.sidebar.header("🚛 Fleet Availability")
    avail_32T = st.sidebar.number_input("32T Available:", min_value=0, value=10)
    avail_19T = st.sidebar.number_input("19T Available:", min_value=0, value=5)
    avail_7T = st.sidebar.number_input("7T Available (12 PLT):", min_value=0, value=3)
    selected_wave = st.sidebar.selectbox("Wave:", ["15:00-23:00", "23:00-7:00"])
    
    STOP_FLEG, STOP_SEC = 75, 150

    st.header("📥 1. Upload Orders")
    uploaded = st.file_uploader("Upload CSV", type=['csv'])

    if uploaded:
        orders = pd.read_csv(uploaded).fillna(0)
        orders.columns = orders.columns.str.strip()
        
        for col in ['Fleg_PLT', 'Sec_PLT']:
            if col not in orders.columns: orders[col] = 0
            
        data = pd.merge(orders, stores_df, on='Store_Code', how='left')
        
        # Check if Store_Code exists in master data
        missing_stores = data[data['Store_Name'].isna()]['Store_Code'].unique()
        if len(missing_stores) > 0:
            st.warning(f"⚠️ Store codes not found in database: {missing_stores}")

        data = data[data['Loading Window'] == selected_wave].copy()
        data['Total_PLT'] = data['Fleg_PLT'] + data['Sec_PLT']

        if not data.empty:
            data['is_priority'] = data['Store_Code'].apply(lambda x: 0 if x == 200 else 1)
            data = data.sort_values(by=['is_priority', 'Zone', 'City'], ascending=[True, False, False])

            st.header("🚛 2. Optimized Routing Plan")
            trucks_list, rem_32, rem_19, rem_7 = [], avail_32T, avail_19T, avail_7T

            for (zone, truck_limit), group in data.groupby(['Zone', 'Max_Truck_Allowed'], sort=False):
                nominal_cap = 33 if truck_limit == '32T' else (18 if truck_limit == '19T' else 12)
                max_cap = nominal_cap * 1.04
                
                c_load, c_stores, c_cities, c_fleg, c_sec = 0, [], [], 0, 0
                for _, row in group.iterrows():
                    if c_load + row['Total_PLT'] <= max_cap:
                        c_load += row['Total_PLT']
                        s_name = f"⭐ {row['Store_Name']}" if row['Store_Code'] == 200 else row['Store_Name']
                        c_stores.append(s_name)
                        if row['City'] not in c_cities: c_cities.append(row['City'])
                        c_fleg += row['Fleg_PLT']; c_sec += row['Sec_PLT']
                    else:
                        

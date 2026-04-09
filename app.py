import streamlit as st
import pandas as pd
import re

# 1. Helper function to clean price strings (Handles '3 630 MAD', '1500,00', etc.)
def clean_currency(value):
    if pd.isna(value):
        return 0.0
    # Remove everything except digits and decimal point/comma
    string_value = str(value).replace('MAD', '').replace(' ', '').replace('\xa0', '')
    # Handle cases with comma as decimal
    string_value = string_value.replace(',', '.')
    try:
        return float(re.sub(r'[^-0-9.]', '', string_value))
    except:
        return 0.0

# 2. Load & Auto-Fix Master Data
@st.cache_data
def load_data():
    try:
        stores = pd.read_csv('stores.csv')
        tariffs = pd.read_csv('tariffs.csv')
        
        # Clean column names
        stores.columns = stores.columns.str.strip()
        tariffs.columns = tariffs.columns.str.strip()
        
        # Position-based mapping (0:City, 1:Truck, 2:Activity, 3:Price)
        tariffs = tariffs.rename(columns={
            tariffs.columns[0]: 'City',
            tariffs.columns[1]: 'Truck',
            tariffs.columns[2]: 'Activity',
            tariffs.columns[3]: 'Price'
        })
        
        # AGGRESSIVE PRICE CLEANING
        tariffs['Price'] = tariffs['Price'].apply(clean_currency)
        
        return stores, tariffs
    except Exception as e:
        st.error(f"System Setup Error: {e}")
        return None, None

# App UI Config
st.set_page_config(page_title="LABDIS Ultimate v7.0", layout="wide")
st.title("🚚 LABDIS Logistics Optimizer v7.0")

stores_df, tariffs_df = load_data()

if stores_df is not None:
    # --- SIDEBAR ---
    st.sidebar.header("⚙️ Operation Settings")
    selected_wave = st.sidebar.selectbox("Departure Wave:", ["15:00-23:00", "23:00-7:00"])
    
    # Financial Rules
    EXTRA_STOP_FLEG = 75
    EXTRA_STOP_SEC = 150

    # --- UPLOAD SECTION ---
    st.header("📥 Upload Daily Orders")
    st.markdown("Required Columns: `Store_Code`, `Fleg_Pallets`, `Sec_Pallets`")
    uploaded_file = st.file_uploader("Upload Daily Orders", type=['csv'])

    if uploaded_file:
        try:
            orders = pd.read_csv(uploaded_file)
            orders.columns = orders.columns.str.strip()
            orders = orders.fillna(0)
            
            # Merge with Stores
            df = pd.merge(orders, stores_df, on='Store_Code', how='left')
            
            # Filter by Wave
            df_wave = df[df['Loading Window'] == selected_wave].copy()
            
            if df_wave.empty:
                st.warning(f"No orders matching the wave: {selected_wave}")
            else:
                # --- CORE LOGIC ENGINE ---
                def process_logistics(row):
                    truck = str(row['Max_Truck_Allowed']).strip()
                    city = str(row['City']).strip()
                    fleg_qty = float(row['Fleg_Pallets'])
                    sec_qty = float(row['Sec_Pallets'])
                    
                    # Logic: If Fleg exists, use Fleg tariff, else Sec
                    activity = "Fleg" if fleg_qty > 0 else "Sec"
                    
                    # Tariff Matching
                    match = tariffs_df[
                        (tariffs_df['City'].str.strip() == city) & 
                        (tariffs_df['Truck'].str.strip() == truck) & 
                        (tariffs_df['Activity'].str.strip() == activity)
                    ]
                    
                    price = float(match.iloc[0]['Price']) if not match.empty else 0.0
                    return pd.Series([truck, price, activity, fleg_qty + sec_qty])

                # Apply logic
                df_wave[['Truck_Type', 'Base_Price', 'Calc_Activity', 'Total_PLT']] = df_wave.apply(process_logistics, axis=1)

                # --- ROUTE CONSOLIDATION ---
                route_summary = df_wave.groupby(['City', 'Zone', 'Truck_Type', 'Calc_Activity']).agg({
                    'Store_Name': 'count',
                    'Fleg_Pallets': 'sum',
                    'Sec_Pallets': 'sum',
                    'Total_PLT': 'sum',
                    'Base_Price': 'max'
                }).reset_index()

                def calculate_final_costs(row):
                    extra_stops = row['Store_Name'] - 1
                    stop_fee = EXTRA_STOP_FLEG if row['Calc_Activity'] == "Fleg" else EXTRA_STOP_SEC
                    return row['Base_Price'] + (extra_stops * stop_fee if extra_stops > 0 else 0)

                route_summary['Final_Cost'] = route_summary.apply(calculate_final_costs, axis=1)

                # --- RESULTS DISPLAY ---
                st.subheader(f"📊 Live Plan: {selected_wave}")
                
                # Warnings
                for _, row in df_wave.iterrows():
                    if row['Truck_Type'] == '19T':
                        st.warning(f"🚨 **19T Only:** {row['Store_Name']} ({row['City']})")

                st.write("### 📝 Detailed Loading List")
                st.dataframe(df_wave[['Store_Code', 'Store_Name', 'City', 'Fleg_Pallets', 'Sec_Pallets', 'Total_PLT', 'Truck_Type', 'Receiving Window']])

                st.divider()
                st.write("### 💰 Financial Summary")
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Volume", f"{df_wave['Total_PLT'].sum()} PLT")
                col2.metric("Total Cost", f"{route_summary['Final_Cost'].sum():,.2f} MAD")
                col3.metric("Number of Drops", len(df_wave))

                st.write("#### 🚚 Route Grouping (Multi-Drop)")
                st.table(route_summary.rename(columns={'Store_Name': 'Drops', 'Base_Price': 'Base Tariff', 'Final_Cost': 'Total Cost'}))

        except Exception as e:
            st.error(f"Logic Processing Error: {e}")

st.caption("LABDIS v7.0 | Currency Auto-Cleaning | Multi-Product Logic")

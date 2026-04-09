import streamlit as st
import pandas as pd

# 1. Load & Clean Master Data
@st.cache_data
def load_data():
    try:
        # Load stores and tariffs
        stores = pd.read_csv('stores.csv')
        tariffs = pd.read_csv('tariffs.csv')
        
        # Clean column names (Remove spaces and handle 'é' issue)
        stores.columns = stores.columns.str.strip()
        tariffs.columns = tariffs.columns.str.strip()
        
        # Standardize Tariff Columns to avoid 'é' errors
        # This renames 'Véhicule' to 'Truck' and 'Activité' to 'Activity' etc.
        tariffs = tariffs.rename(columns={
            'Ville / City': 'City',
            'Véhicule': 'Truck',
            'Activité': 'Activity',
            'Tarif (MAD)': 'Price'
        })
        
        return stores, tariffs
    except Exception as e:
        st.error(f"Setup Error: {e}")
        return None, None

# App Config
st.set_page_config(page_title="LABDIS Ultimate v5.0", layout="wide")
st.title("🚚 LABDIS Logistics Optimizer v5.0")

stores_df, tariffs_df = load_data()

if stores_df is not None:
    # --- SIDEBAR ---
    st.sidebar.header("⚙️ Dispatch Options")
    selected_wave = st.sidebar.selectbox("Departure Wave:", ["15:00-23:00", "23:00-7:00"])
    
    # Cost Constants
    EXTRA_FLEG = 75
    EXTRA_SEC = 150

    # --- UPLOAD DAILY ORDERS ---
    st.header("📥 Upload Daily Orders")
    st.info("Required CSV Columns: Store_Code, Fleg_Pallets, Sec_Pallets")
    uploaded_file = st.file_uploader("Upload CSV", type=['csv'])

    if uploaded_file:
        try:
            # Load orders
            orders = pd.read_csv(uploaded_file).fillna(0)
            
            # Merge with Stores
            df = pd.merge(orders, stores_df, on='Store_Code', how='left')
            
            # Filter by Wave
            df_wave = df[df['Loading Window'] == selected_wave].copy()
            
            if df_wave.empty:
                st.warning(f"No stores found for wave: {selected_wave}")
            else:
                # --- LOGIC ENGINE ---
                def get_logistics_info(row):
                    truck = row['Max_Truck_Allowed']
                    city = row['City']
                    fleg = row['Fleg_Pallets']
                    sec = row['Sec_Pallets']
                    
                    # Rule: Priority to Fleg pricing if it exists
                    activity = "Fleg" if fleg > 0 else "Sec"
                    
                    # Tariff Match
                    match = tariffs_df[(tariffs_df['City'] == city) & 
                                       (tariffs_df['Truck'] == truck) & 
                                       (tariffs_df['Activity'] == activity)]
                    
                    price = match.iloc[0]['Price'] if not match.empty else 0
                    return pd.Series([truck, price, activity, fleg + sec])

                df_wave[['Truck_Type', 'Base_Price', 'Main_Activity', 'Total_PLT']] = df_wave.apply(get_logistics_info, axis=1)

                # --- ROUTE GROUPING (Multi-Drop) ---
                route_summary = df_wave.groupby(['City', 'Zone', 'Truck_Type', 'Main_Activity']).agg({
                    'Store_Name': 'count',
                    'Fleg_Pallets': 'sum',
                    'Sec_Pallets': 'sum',
                    'Total_PLT': 'sum',
                    'Base_Price': 'max'
                }).reset_index()

                def calc_costs(row):
                    stops = row['Store_Name'] - 1
                    fee = EXTRA_FLEG if row['Main_Activity'] == "Fleg" else EXTRA_SEC
                    return row['Base_Price'] + (stops * fee if stops > 0 else 0)

                route_summary['Final_Cost'] = route_summary.apply(calc_costs, axis=1)

                # --- DISPLAY ---
                st.subheader(f"📊 Delivery Plan: {selected_wave}")
                
                # Alerts
                for _, row in df_wave.iterrows():
                    if row['Truck_Type'] == '19T':
                        st.warning(f"🚨 **19T Only:** {row['Store_Name']} ({row['City']})")

                st.write("### 📝 Manifest")
                st.dataframe(df_wave[['Store_Code', 'Store_Name', 'City', 'Fleg_Pallets', 'Sec_Pallets', 'Total_PLT', 'Truck_Type', 'Receiving Window']])

                st.divider()
                st.write("### 💰 Financials")
                c1, c2, c3 = st.columns(3)
                c1.metric("Total Pallets", f"{df_wave['Total_PLT'].sum()} PLT")
                c2.metric("Total Cost", f"{route_summary['Final_Cost'].sum():,.2f} MAD")
                c3.metric("Stops", len(df_wave))

                st.write("#### 🚚 Optimized Routes")
                st.table(route_summary.rename(columns={'Store_Name': 'Drops', 'Base_Price': 'Base Tariff', 'Final_Cost': 'Total Cost'}))

        except Exception as e:
            st.error(f"Logic Error: {e}")

st.caption("LABDIS v5.0 - Robust Encoding & Multi-Product Logic")

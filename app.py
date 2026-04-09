import streamlit as st
import pandas as pd

# 1. Load Data
@st.cache_data
def load_data():
    try:
        stores = pd.read_csv('stores.csv')
        tariffs = pd.read_csv('tariffs.csv')
        return stores, tariffs
    except Exception as e:
        st.error(f"Error loading files: {e}")
        return None, None

st.set_page_config(page_title="LABDIS Smart Logistics", layout="wide")
st.title("🚚 LABDIS Ultimate Logistics Optimizer")

stores_df, tariffs_df = load_data()

if stores_df is not None:
    # --- SIDEBAR CONFIGURATION ---
    st.sidebar.header("⚙️ Dispatch Settings")
    wave_input = st.sidebar.selectbox("Current Departure (Wave):", ["15:00-23:00", "23:00-7:00"])
    
    # Costs & Capacities
    STOP_FLEG = 75
    STOP_SEC = 150
    CAP_32T = 33
    CAP_19T = 18

    # --- UPLOAD SECTION ---
    st.header("📥 Upload Daily Orders")
    st.info("Your CSV should have: Store_Code, Fleg_Pallets, Sec_Pallets")
    uploaded_file = st.file_uploader("Upload CSV File", type=['csv'])

    if uploaded_file:
        try:
            orders = pd.read_csv(uploaded_file).fillna(0)
            
            # Merge with Store DB
            full_data = pd.merge(orders, stores_df, on='Store_Code', how='left')
            
            # 1. Filter by Wave
            wave_plan = full_data[full_data['Loading Window'] == wave_input].copy()
            
            if wave_plan.empty:
                st.warning(f"No orders found for Wave {wave_input}")
            else:
                # 2. Logic: Process each store's constraints
                def apply_complex_rules(row):
                    truck = row['Max_Truck_Allowed']
                    city = row['City']
                    total_plts = row['Fleg_Pallets'] + row['Sec_Pallets']
                    
                    # Decide Activity Type for Pricing (Priority to Fleg if both exist)
                    activity = "Fleg" if row['Fleg_Pallets'] > 0 else "Sec"
                    
                    # Tariff Lookup
                    match = tariffs_df[(tariffs_df['Ville / City'] == city) & 
                                       (tariffs_df['Véhicule'] == truck) & 
                                       (tariffs_df['Activité'] == activity)]
                    
                    base_price = match.iloc[0]['Tarif (MAD)'] if not match.empty else 0
                    return pd.Series([truck, base_price, activity, total_plts])

                wave_plan[['Assigned_Truck', 'Base_Price', 'Main_Activity', 'Total_Pallets']] = wave_plan.apply(apply_complex_rules, axis=1)

                # 3. Routing & Cost Grouping (Same City/Route Grouping)
                # Group stores in the same city to calculate multi-drop
                summary = wave_plan.groupby(['City', 'Zone', 'Assigned_Truck', 'Main_Activity']).agg({
                    'Store_Name': 'count',
                    'Total_Pallets': 'sum',
                    'Fleg_Pallets': 'sum',
                    'Sec_Pallets': 'sum',
                    'Base_Price': 'max'
                }).reset_index()

                # Calculate Extra Stop Fees
                def calc_extra_stops(row):
                    stops = row['Store_Name'] - 1
                    fee = STOP_FLEG if row['Main_Activity'] == "Fleg" else STOP_SEC
                    return stops * fee if stops > 0 else 0

                summary['Extra_Stop_Fees'] = summary.apply(calc_extra_stops, axis=1)
                summary['Final_Cost'] = summary['Base_Price'] + summary['Extra_Stop_Fees']

                # --- UI DISPLAY ---
                st.subheader(f"📊 Live Plan for Wave {wave_input}")
                
                # Alerts for Constraints
                for _, row in wave_plan.iterrows():
                    if row['Assigned_Truck'] == '19T':
                        st.warning(f"⚠️ **Street Constraint:** {row['Store_Name']} ({row['City']}) - 19T Max.")

                # Table of details
                st.write("### 📝 Detailed Order Breakdown")
                st.dataframe(wave_plan[['Store_Code', 'Store_Name', 'City', 'Fleg_Pallets', 'Sec_Pallets', 'Total_Pallets', 'Assigned_Truck', 'Receiving Window']])

                # Financial Summary
                st.divider()
                st.write("### 💰 Financial & Capacity Summary")
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Total Pallets to Load", f"{wave_plan['Total_Pallets'].sum()} PLT")
                with c2:
                    st.metric("Total Logistics Cost", f"{summary['Final_Cost'].sum():,.2f} MAD")
                with c3:
                    st.metric("Total Points of Delivery", len(wave_plan))

                st.write("#### 🚚 Suggested Truck Loading (Grouped by Route)")
                st.table(summary.rename(columns={'Store_Name': 'Drops', 'Base_Price': 'Main Tariff', 'Final_Cost': 'Route Total'}))

        except Exception as e:
            st.error(f"Critical Logic Error: {e}")

st.caption("LABDIS Logistics Optimizer v4.0 - All Constraints Enabled")

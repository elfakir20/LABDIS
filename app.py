import streamlit as st
import pandas as pd

# Load master data with error handling
@st.cache_data
def load_data():
    try:
        # Using simplified file names as agreed
        stores = pd.read_csv('stores.csv')
        tariffs = pd.read_csv('tariffs.csv')
        return stores, tariffs
    except FileNotFoundError:
        return None, None

# Page configuration
st.set_page_config(page_title="LABDIS Logistics Optimizer", layout="wide")
st.title("🚚 LABDIS Smart Logistics Planner")

stores_df, tariffs_df = load_data()

if stores_df is None:
    st.error("❌ Master files (stores.csv or tariffs.csv) not found in GitHub. Please check file names.")
else:
    # Sidebar Settings
    st.sidebar.header("⚙️ Planning Settings")
    wave = st.sidebar.selectbox("Select Loading Wave:", ["15:00-23:00", "23:00-7:00"])
    activity = st.sidebar.selectbox("Select Activity Type:", ["Fleg", "Sec", "Surgele"])

    # Main Interface - Upload Orders
    st.header("📥 Upload Daily Orders")
    uploaded_file = st.file_uploader("Upload your daily orders CSV file", type=['csv'])

    if uploaded_file:
        try:
            daily_orders = pd.read_csv(uploaded_file)
            
            # Check for the required Store_Code column
            if 'Store_Code' in daily_orders.columns:
                # 1. Merge orders with store database
                res = pd.merge(daily_orders, stores_df, on='Store_Code', how='left')
                
                # 2. Filter by selected Loading Wave
                res_wave = res[res['Loading Window'] == wave].copy()
                
                # 3. Cost Calculation Logic based on City, Truck Type, and Activity
                def calculate_estimated_cost(row):
                    truck = row['Max_Truck_Allowed']
                    city = row['City']
                    # Look up in tariff table
                    match = tariffs_df[(tariffs_df['Ville / City'] == city) & 
                                       (tariffs_df['Véhicule'] == truck) & 
                                       (tariffs_df['Activité'] == activity)]
                    if not match.empty:
                        return match.iloc[0]['Tarif (MAD)']
                    return 0

                res_wave['Estimated_Cost'] = res_wave.apply(calculate_estimated_cost, axis=1)
                
                # UI Result Header
                st.subheader(f"✅ Shipment Plan: {wave} | Activity: {activity}")
                
                # Dynamic Warnings for Restricted Streets (19T)
                for i, row in res_wave.iterrows():
                    if row['Max_Truck_Allowed'] == '19T':
                        st.warning(f"🚨 Constraint: **{row['Store_Name']}** ({row['City']}) allows **19T Trucks** only.")
                
                # Display Resulting Plan
                display_cols = ['Store_Code', 'Store_Name', 'City', 'Max_Truck_Allowed', 'Receiving Window', 'Estimated_Cost']
                st.dataframe(res_wave[display_cols], use_container_width=True)
                
                # Financial Dashboard
                st.divider()
                total_cost = res_wave['Estimated_Cost'].sum()
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total Estimated Cost", f"{total_cost:,.2f} MAD")
                with col2:
                    st.metric("Total Stops", len(res_wave))
                
            else:
                st.error("The uploaded file must contain a 'Store_Code' column.")
        except Exception as e:
            st.error(f"Error processing file: {e}")

# Footer
st.caption("Powered by LABDIS Logistics AI - 2026")

import streamlit as st
import pandas as pd

# 1. Load Master Data from GitHub
@st.cache_data
def load_all_data():
    try:
        stores = pd.read_csv('stores.csv')
        tariffs = pd.read_csv('tariffs.csv')
        return stores, tariffs
    except Exception as e:
        st.error(f"Error loading master files: {e}")
        return None, None

# Page Configuration
st.set_page_config(page_title="LABDIS Ultimate Optimizer", layout="wide")
st.title("🚚 LABDIS AI Fleet & Route Master")
st.markdown("### Fully Integrated Logistics Intelligence System")

stores_df, tariffs_df = load_all_data()

if stores_df is not None:
    # --- SIDEBAR: FLEET & WAVE CONTROL ---
    st.sidebar.header("🕹️ Daily Fleet Availability")
    avail_32T = st.sidebar.number_input("32T Available (33 PLT):", min_value=0, value=10)
    avail_19T = st.sidebar.number_input("19T Available (18 PLT):", min_value=0, value=5)
    avail_7T = st.sidebar.number_input("7T Available (12 PLT Target):", min_value=0, value=3)
    
    st.sidebar.divider()
    active_wave = st.sidebar.selectbox("Active Shipping Wave:", ["15:00-23:00", "23:00-7:00"])
    
    # Financial Rules
    STOP_FLEG = 75
    STOP_SEC = 150

    # --- STEP 1: ORDER INGESTION ---
    st.header("📥 1. Daily Order Ingestion")
    uploaded_file = st.file_uploader("Upload Orders CSV (Store_Code, Fleg_PLT, Sec_PLT)", type=['csv'])

    if uploaded_file:
        orders = pd.read_csv(uploaded_file).fillna(0)
        # Merge orders with master store database
        data = pd.merge(orders, stores_df, on='Store_Code', how='left')
        # Filter by Loading Wave
        data = data[data['Loading Window'] == active_wave].copy()
        data['Total_PLT'] = data['Fleg_PLT'] + data['Sec_PLT']

        if data.empty:
            st.warning(f"No orders found in the database for Wave {active_wave}.")
        else:
            # --- STEP 2: THE RECURSIVE GROUPING ENGINE ---
            st.header("🚛 2. Optimized Loading & Routing Plan")
            
            trucks_final = []
            rem_32, rem_19, rem_7 = avail_32T, avail_19T, avail_7T

            # Group by Zone & Restriction to keep routes geographic
            for (zone, truck_limit), group in data.groupby(['Zone', 'Max_Truck_Allowed']):
                # Set capacity logic (7T at 12 PLT as per request)
                if truck_limit == '32T': nominal_cap = 33
                elif truck_limit == '19T': nominal_cap = 18
                else: nominal_cap = 12 
                
                max_allowed = nominal_cap * 1.04 # 104% Tolerance
                group = group.sort_values(by='City')
                
                c_load, c_stores, c_cities, c_fleg, c_sec = 0, [], [], 0, 0

                for _, row in group.iterrows():
                    if c_load + row['Total_PLT'] <= max_allowed:
                        c_load += row['Total_PLT']
                        c_stores.append(row['Store_Name'])
                        c_cities.append(row['City'])
                        c_fleg += row['Fleg_PLT']
                        c_sec += row['Sec_PLT']
                    else:
                        # Close current truck and decrease fleet count
                        trucks_final.append({
                            "Zone": zone, "Type": truck_limit, "Load": c_load,
                            "Stores": c_stores, "Cities": c_cities,
                            "Fleg": c_fleg, "Sec": c_sec, "Cap": nominal_cap
                        })
                        if truck_limit == '32T': rem_32 -= 1
                        elif truck_limit == '19T': rem_19 -= 1
                        else: rem_7 -= 1
                        
                        # Start next truck
                        c_load, c_stores, c_cities = row['Total_PLT'], [row['Store_Name']], [row['City']]
                        c_fleg, c_sec = row['Fleg_PLT'], row['Sec_PLT']

                # Finalize remaining load in the group
                if c_stores:
                    trucks_final.append({
                        "Zone": zone, "Type": truck_limit, "Load": c_load,
                        "Stores": c_stores, "Cities": c_cities,
                        "Fleg": c_fleg, "Sec": c_sec, "Cap": nominal_cap
                    })
                    if truck_limit == '32T': rem_32 -= 1
                    elif truck_limit == '19T': rem_19 -= 1
                    else: rem_7 -= 1

            # --- STEP 3: COSTING & OUTPUT GENERATION ---
            display_results = []
            for i, t in enumerate(trucks_final):
                efficiency = (t["Load"] / t["Cap"]) * 100
                activity = "Fleg" if t["Fleg"] > 0 else "Sec"
                
                # Financial calculation
                main_city = max(set(t["Cities"]), key=t["Cities"].count)
                price_match = tariffs_df[(tariffs_df['Ville / City'] == main_city) & 
                                         (tariffs_df['Véhicule'] == t["Type"]) & 
                                         (tariffs_df['Activité'] == activity)]
                
                base_p = price_match.iloc[0]['Tarif (MAD)'] if not price_match.empty else 0
                extra_stops_fee = (len(t["Stores"]) - 1) * (STOP_FLEG if activity == "Fleg" else STOP_SEC)
                total_cost = base_p + extra_stops_fee

                display_results.append({
                    "Truck_ID": f"TRK-{i+1:02d}",
                    "Zone": t["Zone"],
                    "Truck_Type": t["Type"],
                    "Route Path": " ➡️ ".join(dict.fromkeys(t["Cities"])),
                    "Stores Detailed": " | ".join(t["Stores"]),
                    "Payload (PLT)": round(t["Load"], 1),
                    "Efficiency_%": round(efficiency, 1),
                    "Activity": activity,
                    "Total Cost (MAD)": total_cost
                })

            results_df = pd.DataFrame(display_results)

            # Efficiency Styling (96-104% Target)
            def color_efficiency(val):
                if 96 <= val <= 104: return 'background-color: #28a745; color: white'
                return 'background-color: #ffc107; color: black'

            st.write("### 🚛 Final Shipment & Routing Schedule")
            st.dataframe(results_df.style.applymap(color_efficiency, subset=['Efficiency_%']), use_container_width=True)

            # --- STEP 4: KPI & FLEET DASHBOARD ---
            st.divider()
            st.header("📊 Fleet Usage & Financial Summary")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("32T Utilization", f"{avail_32T - rem_32} / {avail_32T}")
            with col2:
                st.metric("19T Utilization", f"{avail_19T - rem_19} / {avail_19T}")
            with col3:
                st.metric("7T Utilization", f"{avail_7T - rem_7} / {avail_7T}")
            with col4:
                st.metric("Total Wave Budget", f"{results_df['Total Cost (MAD)'].sum():,.2f} MAD")

            # Availability Warning
            if rem_32 < 0 or rem_19 < 0 or rem_7 < 0:
                st.error("🚨 CRITICAL: Orders exceed current Fleet Availability! Please increase truck numbers or reconsider plan.")

else:
    st.error("Missing Master Data: Please ensure 'stores.csv' and 'tariffs.csv' are in your GitHub repo.")

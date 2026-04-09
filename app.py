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

        if data.empty:
            st.warning("No orders found for the selected wave.")
        else:
            # --- ADVANCED SORTING LOGIC ---
            # Priority 1: Store Code 200 first
            # Priority 2: Zone descending (Far to Near from Skhirat)
            data['is_priority'] = data['Store_Code'].apply(lambda x: 0 if x == 200 else 1)
            data = data.sort_values(by=['is_priority', 'Zone', 'City'], ascending=[True, False, False])

            st.header("🚛 2. Optimized Routing & Loading Plan")
            trucks_list, rem_32, rem_19, rem_7 = [], avail_32T, avail_19T, avail_7T

            # --- CONSOLIDATION ENGINE ---
            for (zone, truck_limit), group in data.groupby(['Zone', 'Max_Truck_Allowed'], sort=False):
                # Set dynamic capacity (7T adjusted to 12 as per your requirement)
                if truck_limit == '32T': nominal_cap = 33
                elif truck_limit == '19T': nominal_cap = 18
                else: nominal_cap = 12 
                
                max_cap = nominal_cap * 1.04 # 104% Overload Tolerance
                
                c_load, c_stores, c_cities, c_fleg, c_sec = 0, [], [], 0, 0
                for _, row in group.iterrows():
                    if c_load + row['Total_PLT'] <= max_cap:
                        c_load += row['Total_PLT']
                        s_name = f"⭐ {row['Store_Name']}" if row['Store_Code'] == 200 else row['Store_Name']
                        c_stores.append(s_name)
                        if row['City'] not in c_cities: c_cities.append(row['City'])
                        c_fleg += row['Fleg_PLT']; c_sec += row['Sec_PLT']
                    else:
                        # Close current truck
                        trucks_list.append({
                            "Zone": zone, "Type": truck_limit, "Load": c_load, 
                            "Stores": c_stores, "Cities": c_cities, 
                            "Fleg": c_fleg, "Sec": c_sec, "Cap": nominal_cap
                        })
                        if truck_limit == '32T': rem_32 -= 1
                        elif truck_limit == '19T': rem_19 -= 1
                        else: rem_7 -= 1
                        
                        # Reset for next truck
                        c_load = row['Total_PLT']
                        c_stores = [f"⭐ {row['Store_Name']}" if row['Store_Code'] == 200 else row['Store_Name']]
                        c_cities = [row['City']]
                        c_fleg, c_sec = row['Fleg_PLT'], row['Sec_PLT']

                # Add last truck of the group
                if c_stores:
                    trucks_list.append({"Zone": zone, "Type": truck_limit, "Load": c_load, "Stores": c_stores, "Cities": c_cities, "Fleg": c_fleg, "Sec": c_sec, "Cap": nominal_cap})
                    if truck_limit == '32T': rem_32 -= 1
                    elif truck_limit == '19T': rem_19 -= 1
                    else: rem_7 -= 1

            # --- FINANCIAL CALCULATION ---
            results = []
            for i, t in enumerate(trucks_list):
                efficiency = (t["Load"] / t["Cap"]) * 100
                activity = "Fleg" if t["Fleg"] > 0 else "Sec"
                main_city = t["Cities"][0]
                
                # Match using your specific tariff column names: 
                # Ville / City | Vehicule | Activit | Tarif
                p_match = tariffs_df[(tariffs_df['Ville / City'] == main_city) & 
                                     (tariffs_df['Vehicule'] == t["Type"]) & 
                                     (tariffs_df['Activit'] == activity)]
                
                base_price = p_match.iloc[0]['Tarif'] if not p_match.empty else 0
                extra_stops_cost = (len(t["Stores"]) - 1) * (STOP_FLEG if activity == "Fleg" else STOP_SEC)
                total_cost = base_price + extra_stops_cost

                results.append({
                    "Truck_ID": f"TRK-{i+1:02d}",
                    "Zone": t["Zone"],
                    "Type": t["Type"],
                    "Route": " ➡️ ".join(t["Cities"]),
                    "Stores Order": " | ".join(t["Stores"]),
                    "Total PLT": round(t["Load"], 1),
                    "Efficiency_%": round(efficiency, 1),
                    "Total Cost (MAD)": total_cost
                })

            final_df = pd.DataFrame(results)

            # Style: Green for 96%-104% (Ideal Load)
            def highlight_efficiency(val):
                if 96 <= val <= 104: return 'background-color: #28a745; color: white'
                return 'background-color: #ffc107; color: black'

            st.dataframe(final_df.style.applymap(highlight_efficiency, subset=['Efficiency_%']), use_container_width=True)

            # --- KPI DASHBOARD ---
            st.divider()
            st.header("📊 Fleet & Financial Overview")
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("32T Used", f"{avail_32T - rem_32} / {avail_32T}")
            with c2: st.metric("19T Used", f"{avail_19T - rem_19} / {avail_19T}")
            with c3: st.metric("7T Used", f"{avail_7T - rem_7} / {avail_7T}")
            with c4: st.metric("Total Wave Cost", f"{final_df['Total Cost (MAD)'].sum():,.2f} MAD")

            if rem_32 < 0 or rem_19 < 0 or rem_7 < 0:
                st.error("🚨 ALERT: Not enough trucks available for today's volume!")

else:
    st.error("Missing Master Data: Ensure 'stores.csv' and 'tariffs.csv' are in your GitHub repository.")

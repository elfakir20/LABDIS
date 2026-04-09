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
            # Code 200 gets Priority 0 (First), others get Priority 1
            data['is_priority'] = data['Store_Code'].apply(lambda x: 0 if x == 200 else 1)
            # Sort: Priority first, then Far Zones, then Cities
            data = data.sort_values(by=['is_priority', 'Zone', 'City'], ascending=[True, False, False])

            st.header("🚛 2. Strategic Routing Schedule")
            
            trucks_list = []
            rem_32, rem_19, rem_7 = avail_32T, avail_19T, avail_7T

            # Grouping Engine
            for (zone, truck_limit), group in data.groupby(['Zone', 'Max_Truck_Allowed'], sort=False):
                if truck_limit == '32T': 
                    nominal_cap = 33
                elif truck_limit == '19T': 
                    nominal_cap = 18
                else: 
                    nominal_cap = 12 # High-cap 7T
                
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
                        c_load = row['Total_PLT']
                        c_stores = [f"⭐ {row['Store_Name']}" if row['Store_Code'] == 200 else row['Store_Name']]
                        c_cities = [row['City']]
                        c_fleg, c_sec = row['Fleg_PLT'], row['Sec_PLT']

                # Last truck in the group
                if c_stores:
                    trucks_list.append({
                        "Zone": zone, "Type": truck_limit, "Load": c_load,
                        "Stores": c_stores, "Cities": c_cities,
                        "Fleg": c_fleg, "Sec": c_sec, "Cap": nominal_cap
                    })
                    if truck_limit == '32T': rem_32 -= 1
                    elif truck_limit == '19T': rem_19 -= 1
                    else: rem_7 -= 1

            # --- OUTPUT & FINANCIALS ---
            results = []
            for i, t in enumerate(trucks_list):
                eff = (t["Load"] / t["Cap"]) * 100
                activity = "Fleg" if t["Fleg"] > 0 else "Sec"
                main_city = t["Cities"][0]
                
                p_match = tariffs_df[(tariffs_df['Ville / City'] == main_city) & 
                                     (tariffs_df['Véhicule'] == t["Type"]) & 
                                     (tariffs_df['Activité'] == activity)]
                
                base_p = price_match.iloc[0]['Tarif (MAD)'] if not p_match.empty else 0
                total_c = base_p + (len(t["Stores"]) - 1) * (STOP_FLEG if activity == "Fleg" else STOP_SEC)

                results.append({
                    "Truck_ID": f"TRK-{i+1:02d}", 
                    "Zone": t["Zone"], 
                    "Truck_Type": t["Type"],
                    "Path": " ➡️ ".join(t["Cities"]),
                    "Deliveries": " | ".join(t["Stores"]),
                    "Payload": round(t["Load"], 1), 
                    "Efficiency_%": round(eff, 1),
                    "Cost (MAD)": total_c
                })

            final_df = pd.DataFrame(results)

            def style_eff(val):
                if 96 <= val <= 104: 
                    return 'background-color: #28a745; color: white'
                return 'background-color: #ffc107; color: black'

            st.dataframe(final_df.style.applymap(style_eff, subset=['Efficiency_%']), use_container_width=True)

            # --- DASHBOARD ---
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("32T Used", f"{avail_32T - rem_32} / {avail_32T}")
            with c2: st.metric("19T Used", f"{avail_19T - rem_19} / {avail_19T}")
            with c3: st.metric("7T Used", f"{avail_7T - rem_7} / {avail_7T}")
            with c4: st.metric("Total Cost", f"{final_df['Cost (MAD)'].sum():,.2f} MAD")

else:
    st.error("Please ensure 'stores.csv' and 'tariffs.csv' are uploaded to your GitHub repository.")

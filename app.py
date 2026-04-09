import streamlit as st
import pandas as pd

@st.cache_data
def load_all_data():
    try:
        stores = pd.read_csv('stores.csv')
        tariffs = pd.read_csv('tariffs.csv')
        return stores, tariffs
    except:
        return None, None

st.set_page_config(page_title="LABDIS Skhirat Hub Optimizer", layout="wide")
st.title("🚚 LABDIS Skhirat Optimized Router (100% Load)")
st.markdown("#### Priority: Code 200 | Routing: Far to Near (Hub: Skhirat)")

stores_df, tariffs_df = load_all_data()

if stores_df is not None:
    # --- SIDEBAR: FLEET ---
    st.sidebar.header("🚛 Fleet Availability")
    avail_32T = st.sidebar.number_input("32T Available:", min_value=0, value=10)
    avail_19T = st.sidebar.number_input("19T Available:", min_value=0, value=5)
    avail_7T = st.sidebar.number_input("7T Available (12 PLT):", min_value=0, value=3)
    
    selected_wave = st.sidebar.selectbox("Shipping Wave:", ["15:00-23:00", "23:00-7:00"])
    
    STOP_FLEG, STOP_SEC = 75, 150

    st.header("📥 1. Upload Orders")
    uploaded = st.file_uploader("Upload CSV (Store_Code, Fleg_PLT, Sec_PLT)", type=['csv'])

    if uploaded:
        orders = pd.read_csv(uploaded).fillna(0)
        data = pd.merge(orders, stores_df, on='Store_Code', how='left')
        data = data[data['Loading Window'] == selected_wave].copy()
        data['Total_PLT'] = data['Fleg_PLT'] + data['Sec_PLT']

        if data.empty:
            st.warning("No orders found.")
        else:
            # --- ADVANCED SORTING LOGIC ---
            # 1. المتاجر بكود 200 هي الأولى
            # 2. الزونات البعيدة هي الأولى (افتراضياً رتبنا حسب الـ Zone تنازلياً)
            data['is_priority'] = data['Store_Code'].apply(lambda x: 0 if x == 200 else 1)
            data = data.sort_values(by=['is_priority', 'Zone', 'City'], ascending=[True, False, False])

            st.header("🚛 2. Optimized Routing (Skhirat Hub)")
            
            trucks_list, rem_32, rem_19, rem_7 = [], avail_32T, avail_19T, avail_7T

            # Grouping by Zone & Truck Limit
            for (zone, truck_limit), group in data.groupby(['Zone', 'Max_Truck_Allowed'], sort=False):
                nominal_cap = 33 if truck_limit == '32T' else (18 if truck_limit == '19T' else 12)
                max_cap = nominal_cap * 1.04
                
                c_load, c_stores, c_cities, c_fleg, c_sec = 0, [], [], 0, 0

                for _, row in group.iterrows():
                    if c_load + row['Total_PLT'] <= max_cap:
                        c_load += row['Total_PLT']
                        # إضافة علامة ⭐ للمتاجر كود 200
                        store_display = f"⭐ {row['Store_Name']}" if row['Store_Code'] == 200 else row['Store_Name']
                        c_stores.append(store_display)
                        if row['City'] not in c_cities: c_cities.append(row['City'])
                        c_fleg += row['Fleg_PLT']
                        c_sec += row['Sec_PLT']
                    else:
                        trucks_list.append({
                            "Zone": zone, "Type": truck_limit, "Load": c_load,
                            "Stores": c_stores, "Cities": c_cities,
                            "Fleg": c_fleg, "Sec": c_sec, "Cap": nominal_cap
                        })
                        if truck_limit == '32T': rem_32 -= 1
                        elif truck_limit == '19T': rem_19 -= 1
                        else: rem_7 -= 1
                        
                        c_load = row['Total_PLT']
                        c_stores = [f"⭐ {row['Store_Name']}" if row['Store_Code'] == 200 else row['Store_Name']]
                        c_cities = [row['City']]
                        c_fleg, c_sec = row['Fleg_PLT'], row['Sec_PLT']

                if c_stores:
                    trucks_list.append({"Zone": zone, "Type": truck_limit, "Load": c_load, "Stores": c_stores, "Cities": c_cities, "Fleg": c_fleg, "Sec": c_sec, "Cap": nominal_cap})
                    if truck_limit == '32T': rem_32 -= 1
                    elif truck_limit == '19T': rem_19 -= 1
                    else: rem_7 -= 1

            # --- DISPLAY & COSTING ---
            results = []
            for i, t in enumerate(trucks_list):
                eff = (t["Load"] / t["Cap"]) * 100
                activity = "Fleg" if t["Fleg"] > 0 else "Sec"
                main_city = t["Cities"][0]
                
                p_match = tariffs_df[(tariffs_df['Ville / City'] == main_city) & (tariffs_df['Véhicule'] == t["Type"]) & (tariffs_df['Activité'] == activity)]
                base_p = p_match.iloc[0]['Tarif (MAD)'] if not p_match.empty else 0
                total_c = base_p + (len(t["Stores"]) - 1) * (STOP_FLEG if activity == "Fleg" else STOP_SEC)

                results.append({
                    "Truck_ID": f"TRK-{i+1:02d}", "Zone": t["Zone"], "Type": t["Type"],
                    "Route Path": " ➡️ ".join(t["Cities"]),
                    "Stores Order": " | ".join(t["Stores"]),
                    "Total PLT": round(t["Load"], 1), "Efficiency_%": round(eff, 1),
                    "Cost (MAD)": total_c
                })

            final_df = pd.DataFrame(results)

            def style_eff(val):
                if 96 <= val <= 104: return 'background-color: #28a745; color: white'
                return 'background-color: #ffc107; color: black'

            st.dataframe(final_df.style.applymap(style_eff, subset=['Efficiency_%']), use_container_width=True)

            # --- KPI DASHBOARD ---
            st.divider()
            st.header("📊 Skhirat Hub Summary")
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("32T Used", f"{avail_32T - rem_32} / {avail_32T}")
            with c2: st.metric("19T Used", f"{avail_19T - rem_19} / {avail_19T}")
            with c3: st.metric("7T Used", f"{avail_7T - rem_7} / {avail_7T}")
            with c4: st.metric("Total Budget", f"{final_df['Cost (MAD)'].sum():,.2f} MAD")

else:
    st.error("Missing files on GitHub.")

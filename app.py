import streamlit as st
import pandas as pd

# 1. Load Master Data
@st.cache_data
def load_all_data():
    try:
        stores = pd.read_csv('stores.csv')
        tariffs = pd.read_csv('tariffs.csv')
        return stores, tariffs
    except:
        return None, None

st.set_page_config(page_title="LABDIS Fleet Optimizer v10", layout="wide")
st.title("💯 LABDIS Ultimate Fleet Manager")

stores_df, tariffs_df = load_all_data()

if stores_df is not None:
    # --- SIDEBAR: FLEET ---
    st.sidebar.header("🚛 Fleet Availability")
    avail_32T = st.sidebar.number_input("32T Available (33 PLT):", min_value=0, value=10)
    avail_19T = st.sidebar.number_input("19T Available (18 PLT):", min_value=0, value=5)
    avail_7T = st.sidebar.number_input("7T Available (12 PLT):", min_value=0, value=3)
    
    selected_wave = st.sidebar.selectbox("Shipping Wave:", ["15:00-23:00", "23:00-7:00"])
    
    STOP_FLEG = 75
    STOP_SEC = 150

    st.header("📥 1. Upload Daily Orders")
    uploaded = st.file_uploader("Upload CSV", type=['csv'])

    if uploaded:
        # قراءة الملف وتنظيف أسماء الأعمدة من أي فراغات زايدة
        orders = pd.read_csv(uploaded)
        orders.columns = orders.columns.str.strip() 
        orders = orders.fillna(0)

        # دمج البيانات مع قاعدة بيانات المتاجر
        data = pd.merge(orders, stores_df, on='Store_Code', how='left')
        data = data[data['Loading Window'] == selected_wave].copy()

        # --- هاد الجزء هو اللي كيحل مشكل KeyError ---
        # كنشوفو الأسماء اللي عندك في الصورة: Fleg_Pallets و Sec_Pallets
        fleg_col = 'Fleg_Pallets' if 'Fleg_Pallets' in data.columns else 'Fleg_PLT'
        sec_col = 'Sec_Pallets' if 'Sec_Pallets' in data.columns else 'Sec_PLT'
        
        data['Total_PLT'] = data[fleg_col] + data[sec_col]
        # ---------------------------------------------

        if data.empty:
            st.warning("No orders found for this wave.")
        else:
            st.header("🚛 2. Optimized Fleet Assignment")
            
            all_trucks = []
            rem_32, rem_19, rem_7 = avail_32T, avail_19T, avail_7T

            for (zone, truck_limit), group in data.groupby(['Zone', 'Max_Truck_Allowed']):
                if truck_limit == '32T': nominal_cap = 33
                elif truck_limit == '19T': nominal_cap = 18
                else: nominal_cap = 12 
                
                max_cap = nominal_cap * 1.04
                group = group.sort_values(by='City')
                
                cur_load, cur_stores, cur_cities, cur_fleg, cur_sec = 0, [], [], 0, 0

                for _, row in group.iterrows():
                    if cur_load + row['Total_PLT'] <= max_cap:
                        cur_load += row['Total_PLT']
                        cur_stores.append(row['Store_Name'])
                        cur_cities.append(row['City'])
                        cur_fleg += row[fleg_col]
                        cur_sec += row[sec_col]
                    else:
                        all_trucks.append({
                            "Zone": zone, "Type": truck_limit, "Load": cur_load,
                            "Stores": cur_stores, "Cities": cur_cities,
                            "Fleg": cur_fleg, "Sec": cur_sec, "Cap": nominal_cap
                        })
                        if truck_limit == '32T': rem_32 -= 1
                        elif truck_limit == '19T': rem_19 -= 1
                        else: rem_7 -= 1
                        
                        cur_load = row['Total_PLT']
                        cur_stores = [row['Store_Name']]
                        cur_cities = [row['City']]
                        cur_fleg, cur_sec = row[fleg_col], row[sec_col]

                if cur_stores:
                    all_trucks.append({
                        "Zone": zone, "Type": truck_limit, "Load": cur_load,
                        "Stores": cur_stores, "Cities": cur_cities,
                        "Fleg": cur_fleg, "Sec": cur_sec, "Cap": nominal_cap
                    })
                    if truck_limit == '32T': rem_32 -= 1
                    elif truck_limit == '19T': rem_19 -= 1
                    else: rem_7 -= 1

            results = []
            for i, t in enumerate(all_trucks):
                fill_rate = (t["Load"] / t["Cap"]) * 100
                main_act = "Fleg" if t["Fleg"] > 0 else "Sec"
                main_city = max(set(t["Cities"]), key=t["Cities"].count)
                
                p_match = tariffs_df[(tariffs_df['Ville / City'] == main_city) & 
                                     (tariffs_df['Véhicule'] == t["Type"]) & 
                                     (tariffs_df['Activité'] == main_act)]
                
                base_p = p_match.iloc[0]['Tarif (MAD)'] if not p_match.empty else 0
                total_c = base_p + (len(t["Stores"]) - 1) * (STOP_FLEG if main_act == "Fleg" else STOP_SEC)

                results.append({
                    "ID": f"TRK-{i+1:02d}", "Zone": t["Zone"], "Type": t["Type"],
                    "Route": " ➡️ ".join(dict.fromkeys(t["Cities"])),
                    "Stores": " | ".join(t["Stores"]),
                    "PLT": round(t["Load"], 1), "Efficiency_%": round(fill_rate, 1),
                    "Cost (MAD)": total_cost if 'total_cost' in locals() else total_c
                })

            final_df = pd.DataFrame(results)

            def style_eff(val):
                if 96 <= val <= 104: return 'background-color: #28a745; color: white'
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
    st.error("Missing files on GitHub.")

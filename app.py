import streamlit as st
import pandas as pd

# 1. Load Master Data
@st.cache_data
def load_all_data():
    try:
        # قراءة الملفات مع تنظيف فوري لأسماء الأعمدة
        stores = pd.read_csv('stores.csv')
        stores.columns = stores.columns.str.strip()
        
        tariffs = pd.read_csv('tariffs.csv')
        tariffs.columns = tariffs.columns.str.strip()
        
        return stores, tariffs
    except Exception as e:
        st.error(f"Error loading master files: {e}")
        return None, None

st.set_page_config(page_title="LABDIS Ultimate Fleet Optimizer", layout="wide")
st.title("🚚 LABDIS Fleet Manager (Error-Proof Version)")

stores_df, tariffs_df = load_all_data()

if stores_df is not None:
    # --- SIDEBAR: FLEET ---
    st.sidebar.header("🚛 Fleet Availability")
    avail_32T = st.sidebar.number_input("32T (33 PLT):", min_value=0, value=10)
    avail_19T = st.sidebar.number_input("19T (18 PLT):", min_value=0, value=5)
    avail_7T = st.sidebar.number_input("7T (12 PLT):", min_value=0, value=3)
    
    selected_wave = st.sidebar.selectbox("Shipping Wave:", ["15:00-23:00", "23:00-7:00"])
    
    STOP_FLEG = 75
    STOP_SEC = 150

    st.header("📥 1. Upload Daily Orders")
    uploaded = st.file_uploader("Upload CSV", type=['csv'])

    if uploaded:
        orders = pd.read_csv(uploaded)
        orders.columns = orders.columns.str.strip() 
        orders = orders.fillna(0)

        # دمج البيانات
        data = pd.merge(orders, stores_df, on='Store_Code', how='left')
        data = data[data['Loading Window'] == selected_wave].copy()

        # التعامل مع أسماء أعمدة الباليطات (من الصورة السابقة)
        f_col = 'Fleg_Pallets' if 'Fleg_Pallets' in data.columns else 'Fleg_PLT'
        s_col = 'Sec_Pallets' if 'Sec_Pallets' in data.columns else 'Sec_PLT'
        data['Total_PLT'] = data[f_col] + data[s_col]

        if data.empty:
            st.warning("No orders found for this wave.")
        else:
            st.header("🚛 2. Optimized Fleet Assignment")
            
            all_trucks = []
            rem_32, rem_19, rem_7 = avail_32T, avail_19T, avail_7T

            for (zone, truck_limit), group in data.groupby(['Zone', 'Max_Truck_Allowed']):
                nominal_cap = 33 if truck_limit == '32T' else 18 if truck_limit == '19T' else 12
                max_cap = nominal_cap * 1.04
                group = group.sort_values(by='City')
                
                cur_load, cur_stores, cur_cities, cur_fleg, cur_sec = 0, [], [], 0, 0

                for _, row in group.iterrows():
                    if cur_load + row['Total_PLT'] <= max_cap:
                        cur_load += row['Total_PLT']
                        cur_stores.append(row['Store_Name'])
                        cur_cities.append(row['City'])
                        cur_fleg += row[f_col]
                        cur_sec += row[s_col]
                    else:
                        all_trucks.append({
                            "Zone": zone, "Type": truck_limit, "Load": cur_load,
                            "Stores": cur_stores, "Cities": cur_cities,
                            "Fleg": cur_fleg, "Sec": cur_sec, "Cap": nominal_cap
                        })
                        if truck_limit == '32T': rem_32 -= 1
                        elif truck_limit == '19T': rem_19 -= 1
                        else: rem_7 -= 1
                        
                        cur_load, cur_stores, cur_cities = row['Total_PLT'], [row['Store_Name']], [row['City']]
                        cur_fleg, cur_sec = row[f_col], row[s_col]

                if cur_stores:
                    all_trucks.append({
                        "Zone": zone, "Type": truck_limit, "Load": cur_load,
                        "Stores": cur_stores, "Cities": cur_cities,
                        "Fleg": cur_fleg, "Sec": cur_sec, "Cap": nominal_cap
                    })
                    if truck_limit == '32T': rem_32 -= 1
                    elif truck_limit == '19T': rem_19 -= 1
                    else: rem_7 -= 1

            # --- إصلاح مشكل KeyError في Tariffs ---
            # البحث عن الأعمدة الصحيحة في ملف التعرفة مهما كان اسمها
            def get_col(df, keywords):
                for col in df.columns:
                    if any(key.lower() in col.lower() for key in keywords):
                        return col
                return None

            v_col = get_col(tariffs_df, ['Véhicule', 'Vehicule', 'Truck', 'Type'])
            c_col = get_col(tariffs_df, ['Ville', 'City', 'Destination'])
            a_col = get_col(tariffs_df, ['Activité', 'Activite', 'Type'])
            p_col = get_col(tariffs_df, ['Tarif', 'Price', 'Prix'])

            results = []
            for i, t in enumerate(all_trucks):
                fill_rate = (t["Load"] / t["Cap"]) * 100
                main_act = "Fleg" if t["Fleg"] > 0 else "Sec"
                main_city = max(set(t["Cities"]), key=t["Cities"].count)
                
                # البحث عن السعر مع حماية من الأخطاء
                base_p = 0
                if all([v_col, c_col, a_col, p_col]):
                    p_match = tariffs_df[(tariffs_df[c_col] == main_city) & 
                                         (tariffs_df[v_col] == t["Type"]) & 
                                         (tariffs_df[a_col] == main_act)]
                    if not p_match.empty:
                        base_p = p_match.iloc[0][p_col]

                total_c = base_p + (len(t["Stores"]) - 1) * (STOP_FLEG if main_act == "Fleg" else STOP_SEC)

                results.append({
                    "ID": f"TRK-{i+1:02d}", "Zone": t["Zone"], "Type": t["Type"],
                    "Route": " ➡️ ".join(dict.fromkeys(t["Cities"])),
                    "Stores": " | ".join(t["Stores"]),
                    "PLT": round(t["Load"], 1), "Efficiency_%": round(fill_rate, 1),
                    "Cost (MAD)": total_c
                })

            final_df = pd.DataFrame(results)
            st.dataframe(final_df, use_container_width=True)

            # --- Dashboard ---
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("32T Used", f"{avail_32T - rem_32} / {avail_32T}")
            with c2: st.metric("19T Used", f"{avail_19T - rem_19} / {avail_19T}")
            with c3: st.metric("7T Used", f"{avail_7T - rem_7} / {avail_7T}")
            with c4: st.metric("Total Cost", f"{final_df['Cost (MAD)'].sum():,.2f} MAD")

else:
    st.error("Missing files on GitHub.")

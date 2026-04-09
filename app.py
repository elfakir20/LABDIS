import streamlit as st
import pandas as pd
import numpy as np

# 1. Loading and Cleaning Data
@st.cache_data
def load_all_data():
    try:
        stores = pd.read_csv('stores.csv')
        tariffs = pd.read_csv('tariffs.csv')
        
        # تحويل الأثمان إلى أرقام وحذف الأخطاء لمنع TypeError
        tariffs['Price'] = pd.to_numeric(tariffs['Price'], errors='coerce')
        tariffs = tariffs.dropna(subset=['Price'])
        
        return stores, tariffs
    except Exception as e:
        st.error(f"Error loading files: {e}")
        return None, None

st.set_page_config(page_title="LABDIS Elite Optimizer v15", layout="wide")
st.title("🚀 LABDIS Elite Logistics AI (Skhirat Hub)")
st.subheader("Priority 200 | 100% Load | Min-Cost Optimization")

stores_df, tariffs_df = load_all_data()

if stores_df is not None:
    # --- SIDEBAR: FLEET CONTROL ---
    with st.sidebar:
        st.header("🚛 Available Fleet Inventory")
        f32 = st.number_input("32T (33 PLT) Units:", 0, 100, 10)
        f19 = st.number_input("19T (18 PLT) Units:", 0, 100, 5)
        f7 = st.number_input("7T (12 PLT) Units:", 0, 100, 5)
        
        st.divider()
        wave = st.selectbox("Shipping Wave", ["15:00-23:00", "23:00-7:00"])
        st.info("Strategy: Lowest Cost Per Pallet (CPP)")

    # --- PHASE 1: DATA PROCESSING & PRIORITY ---
    uploaded = st.file_uploader("Upload Daily Orders CSV", type=['csv'])

    if uploaded:
        orders = pd.read_csv(uploaded).fillna(0)
        data = pd.merge(orders, stores_df, on='Store_Code', how='left')
        data = data[data['Loading Window'] == wave].copy()
        
        # Rule 1: Priority for Store 200
        # Rule 2: Sort by Zone (Furthest from Skhirat)
        data['is_200'] = data['Store_Code'].apply(lambda x: 0 if x == 200 else 1)
        data = data.sort_values(['is_200', 'Zone', 'City'], ascending=[True, False, False])

        # --- PHASE 2: CORE OPTIMIZATION ENGINE ---
        dispatched_trucks = []
        fleet_rem = {'32T': f32, '19T': f19, '7T': f7}

        # نجمع الطلبيات حسب المنطقة (Zone) وقيود الشاحنات
        for (zone, truck_limit), group in data.groupby(['Zone', 'Max_Truck_Allowed'], sort=False):
            zone_fleg = group['Fleg_PLT'].sum()
            zone_sec = group['Sec_PLT'].sum()
            remaining_volume = zone_fleg + zone_sec
            activity = "Fleg" if zone_fleg > zone_sec else "Sec"
            main_city = group['City'].iloc[0]

            while remaining_volume >= 8: # الحد الأدنى لتحميل شاحنة
                options = []
                # فحص الخيارات المتاحة بناءً على الأسطول والتكلفة
                for t_type, cap in [('32T', 33), ('19T', 18), ('7T', 12)]:
                    # التحقق من نوع الشاحنة المسموح به في المنطقة وتوفرها
                    is_allowed = (truck_limit == t_type) or (truck_limit == '32T') or (truck_limit == '19T' and t_type == '7T')
                    
                    if fleet_rem[t_type] > 0 and is_allowed:
                        p_match = tariffs_df[(tariffs_df['City'] == main_city) & 
                                             (tariffs_df['Truck'] == t_type) & 
                                             (tariffs_df['Type'] == activity)]
                        
                        if not p_match.empty:
                            try:
                                price = float(p_match.iloc[0]['Price'])
                                options.append({'type': t_type, 'cap': cap, 'price': price, 'cpp': price/cap})
                            except:
                                continue

                if not options:
                    break

                # منطق الاختيار الذكي:
                # 1. البحث عن الشاحنة التي تعطي امتلاء 100% للحجم المتبقي
                # 2. إذا لم توجد، اختيار الأرخص تكلفة للبليطة الواحدة (CPP)
                best_t = None
                for opt in sorted(options, key=lambda x: x['cap'], reverse=True):
                    if remaining_volume >= opt['cap'] * 0.96:
                        best_t = opt
                        break
                
                if not best_t:
                    best_t = min(options, key=lambda x: x['cpp'])

                # تنفيذ الشحن
                load_to_assign = min(remaining_volume, best_t['cap'] * 1.04)
                fill_rate = (load_to_assign / best_t['cap']) * 100
                
                dispatched_trucks.append({
                    "TRK_ID": f"TRK-{len(dispatched_trucks)+1:02d}",
                    "Zone": zone,
                    "Type": best_t['type'],
                    "Load": round(load_to_assign, 1),
                    "Efficiency_%": round(fill_rate, 1),
                    "Cost_MAD": round(best_t['price'], 2),
                    "Stores": " | ".join(group['Store_Name'].unique()),
                    "City": main_city
                })

                remaining_volume -= load_to_assign
                fleet_rem[best_t['type']] -= 1

        # --- PHASE 3: ADVANCED UI & REPORTING ---
        if dispatched_trucks:
            final_df = pd.DataFrame(dispatched_trucks)
            
            st.header("📝 Dynamic Dispatch Plan")
            
            # تلوين الكفاءة (أخضر للأهداف المحققة 96-104%)
            def style_efficiency(v):
                color = '#27ae60' if 96 <= v <= 104 else '#f39c12'
                return f'background-color: {color}; color: white; font-weight: bold'

            st.dataframe(final_df.style.applymap(style_efficiency, subset=['Efficiency_%']), use_container_width=True)

            # Dashboard Metrics
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Total Trips", len(final_df))
            with c2:
                st.metric("Total Cost (MAD)", f"{final_df['Cost_MAD'].sum():,.2f}")
            with c3:
                st.metric("Avg Efficiency", f"{final_df['Efficiency_%'].mean():.1f}%")
            with c4:
                st.metric("Unassigned Pallets", f"{round(remaining_volume, 1) if 'remaining_volume' in locals() else 0}")

        else:
            st.warning("Insufficient volume to dispatch trucks under the 100% fill-rate constraint.")
else:
    st.error("Configuration Error: Ensure 'stores.csv' and 'tariffs.csv' are present and formatted correctly.")

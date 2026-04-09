import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# 1. Loading Master Data
@st.cache_data
def load_all_data():
    try:
        # تحميل الملفات الأساسية
        stores = pd.read_csv('stores.csv')
        tariffs = pd.read_csv('tariffs.csv')
        return stores, tariffs
    except Exception as e:
        st.error(f"Error loading files: {e}")
        return None, None

st.set_page_config(page_title="LABDIS Final AI Optimizer", layout="wide")

st.title("💰 LABDIS AI Cost & Load Master v14.0")
st.info("Direct Mapping Strategy: City | Truck | Type | Price")

stores_df, tariffs_df = load_all_data()

if stores_df is not None and tariffs_df is not None:
    # --- SIDEBAR: FLEET CONTROL ---
    with st.sidebar:
        st.header("🚛 Available Fleet Today")
        f_32T = st.number_input("32T Available (33 PLT):", 0, 100, 10)
        f_19T = st.number_input("19T Available (18 PLT):", 0, 100, 5)
        f_7T = st.number_input("7T Available (12 PLT):", 0, 100, 5)
        
        st.divider()
        current_wave = st.selectbox("Shipping Wave", ["15:00-23:00", "23:00-7:00"])
        st.caption("Central Hub: Skhirat")

    # --- PHASE 1: DATA PROCESSING ---
    uploaded = st.file_uploader("Upload Daily Orders CSV", type=['csv'])

    if uploaded:
        orders = pd.read_csv(uploaded).fillna(0)
        # دمج البيانات مع قاعدة بيانات المتاجر
        data = pd.merge(orders, stores_df, on='Store_Code', how='left')
        data = data[data['Loading Window'] == current_wave].copy()
        
        # منطق الأولويات: كود 200 أولاً، ثم الأبعد جغرافياً (Zone تنازلياً)
        data['Priority'] = data['Store_Code'].apply(lambda x: 0 if x == 200 else 1)
        data = data.sort_values(['Priority', 'Zone', 'City'], ascending=[True, False, False])

        # --- PHASE 2: OPTIMIZATION ENGINE ---
        dispatched = []
        fleet_count = {'32T': f_32T, '19T': f_19T, '7T': f_7T}
        
        # التجميع حسب المنطقة (Zone) لضمان تحقيق هدف الـ 100%
        for zone, zone_group in data.groupby('Zone', sort=False):
            total_plt = zone_group['Fleg_PLT'].sum() + zone_group['Sec_PLT'].sum()
            main_city = zone_group['City'].iloc[0]
            
            # تحديد نوع النشاط لجلب السعر الصحيح (Fleg أو Sec)
            activity = "Fleg" if zone_group['Fleg_PLT'].sum() >= zone_group['Sec_PLT'].sum() else "Sec"
            
            while total_plt >= 7.5: # الحد الأدنى لتحميل شاحنة
                possible_trucks = []
                
                # البحث في جدول التسعيرة عن الخيارات المتاحة
                for t_type, cap in [('32T', 33), ('19T', 18), ('7T', 12)]:
                    if fleet_count[t_type] > 0:
                        match = tariffs_df[
                            (tariffs_df['City'] == main_city) & 
                            (tariffs_df['Truck'] == t_type) & 
                            (tariffs_df['Type'] == activity)
                        ]
                        if not match.empty:
                            price = match.iloc[0]['Price']
                            cpp = price / cap # التكلفة لكل بليطة
                            possible_trucks.append({'type': t_type, 'cap': cap, 'price': price, 'cpp': cpp})

                if not possible_trucks: break

                # اختيار الشاحنة الأرخص تكلفة (Best Cost Efficiency)
                best = min(possible_trucks, key=lambda x: x['cpp'])
                
                # تصغير الحجم إذا كانت الشاحنة الأصغر ستمتلئ بنسبة 100% وتكون أرخص للرحلة الواحدة
                for opt in possible_trucks:
                    if total_plt <= opt['cap'] * 1.04 and opt['cap'] < best['cap']:
                        best = opt
                
                load = min(total_plt, best['cap'] * 1.04)
                
                dispatched.append({
                    "Zone": zone, 
                    "Truck": best['type'], 
                    "Load (PLT)": round(load, 1),
                    "Efficiency_%": round((load / best['cap']) * 100, 1),
                    "Cost (MAD)": best['price'], 
                    "Main_City": main_city,
                    "Stores_Included": ", ".join(zone_group['Store_Name'].unique())
                })
                
                total_plt -= load
                fleet_count[best['type']] -= 1

        # --- PHASE 3: INTERFACE & VISUALS ---
        if dispatched:
            res_df = pd.DataFrame(dispatched)
            st.header("📋 Optimized Dispatch Board")
            
            # تنسيق لوني لنسبة الامتلاء
            def style_efficiency(val):
                color = '#27ae60' if 96 <= val <= 104 else '#f39c12'
                return f'background-color: {color}; color: white; font-weight: bold'

            st.dataframe(res_df.style.applymap(style_efficiency, subset=['Efficiency_%']), use_container_width=True)

            # Dashboard Metrics
            st.divider()
            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("Total Trips", len(res_df))
            with m2:
                st.metric("Total Wave Cost", f"{res_df['Cost (MAD)'].sum():,.2f} MAD")
            with m3:
                avg_eff = res_df['Efficiency_%'].mean()
                st.metric("Fleet Efficiency", f"{avg_eff:.1f}%")

            # Chart Visualization
            fig = px.bar(res_df, x="Truck", y="Load (PLT)", color="Zone", 
                         title="Truck Load Distribution by Zone",
                         text_auto=True)
            st.plotly_chart(fig, use_container_width=True)

else:
    st.error("Missing Files: Please ensure 'stores.csv' and 'tariffs.csv' are uploaded with correct headers.")

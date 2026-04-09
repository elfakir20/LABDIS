import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# 1. Loading Master Data
@st.cache_data
def load_all_data():
    try:
        # تحميل الملفات مع التأكد من أسماء الأعمدة الجديدة
        stores = pd.read_csv('stores.csv')
        tariffs = pd.read_csv('tariffs.csv')
        return stores, tariffs
    except Exception as e:
        st.error(f"Error: {e}")
        return None, None

st.set_page_config(page_title="LABDIS Final AI Optimizer", layout="wide")

st.title("💰 LABDIS AI Cost & Load Master v14.0")
st.info("Direct Mapping: City | Truck | Type | Price")

stores_df, tariffs_df = load_all_data()

if stores_df is not None and tariffs_df is not None:
    # --- SIDEBAR: FLEET ---
    with st.sidebar:
        st.header("🚛 Available Fleet")
        f_32T = st.number_input("32T Available:", 0, 50, 10)
        f_19T = st.number_input("19T Available:", 0, 5, 5)
        f_7T = st.number_input("7T (12 PLT) Available:", 0, 10, 5)
        
        st.divider()
        current_wave = st.selectbox("Shipping Wave", ["15:00-23:00", "23:00-7:00"])

    # --- PHASE 1: DATA PROCESSING ---
    uploaded = st.file_uploader("Upload Daily Orders CSV", type=['csv'])

    if uploaded:
        orders = pd.read_csv(uploaded).fillna(0)
        # دمج الطلبيات مع بيانات المتاجر (للحصول على الـ Zone و Max_Truck)
        data = pd.merge(orders, stores_df, on='Store_Code', how='left')
        data = data[data['Loading Window'] == current_wave].copy()
        
        # ترتيب الأولويات: كود 200 أولاً ثم الأبعد عن الصخيرات حسب الزون
        data['Priority'] = data['Store_Code'].apply(lambda x: 0 if x == 200 else 1)
        data = data.sort_values(['Priority', 'Zone', 'City'], ascending=[True, False, False])

        # --- PHASE 2: RECURSIVE COST OPTIMIZATION ---
        dispatched = []
        fleet = {'32T': f_32T, '19T': f_19T, '7T': f_7T}
        
        # التجميع حسب المنطقة (Zone) لضمان امتلاء الشاحنة 100%
        for zone, zone_group in data.groupby('Zone', sort=False):
            total_plt = zone_group['Fleg_PLT'].sum() + zone_group['Sec_PLT'].sum()
            main_city = zone_group['City'].iloc[0]
            # تحديد النشاط الغالب (Fleg أو Sec) لجلب السعر الصحيح
            activity = "Fleg" if zone_group['Fleg_PLT'].sum() >= zone_group['Sec_PLT'].sum() else "Sec"
            
            while total_plt >= 7.5: # الحد الأدنى لإرسال شاحنة
                possible_options = []
                # البحث عن أفضل سعر في ملف tariffs بناءً على العناوين الجديدة
                for t_type, cap in [('32T', 33), ('19T', 18), ('7T', 12)]:
                    if fleet[t_type] > 0:
                        # مطابقة الأعمدة: City, Truck, Type كما في صورتك
                        match = tariffs_df[
                            (tariffs_df['City'] == main_city) & 
                            (tariffs_df['Truck'] == t_type) & 
                            (tariffs_df['Type'] == activity)
                        ]
                        if not match.empty:
                            price = match.iloc[0]['Price']
                            cpp = price / cap # Cost Per Pallet
                            possible_options.append({'type': t_type, 'cap': cap, 'price': price, 'cpp': cpp})

                if not possible_options: break

                # اختيار الشاحنة الأرخص تكلفة للبليطة الواحدة
                best = min(possible_options, key=lambda x: x['cpp'])
                
                # تصغير حجم الشاحنة إذا كانت الكمية المتبقية تناسب شاحنة أصغر بامتلاء 100%
                for opt in possible_options:
                    if total_plt <= opt['cap'] * 1.04 and opt['cap'] < best['cap']:
                        best = opt
                
                load = min(total_plt, best['cap'] * 1.04)
                
                dispatched.append({
                    "Zone": zone, "Truck": best['type'], "Load": round(load, 1),
                    "Efficiency_%": round((load / best['cap']) * 100, 1),
                    "Trip_Cost": best['price'], "Route": main_city,
                    "Stores": ", ".join(zone_group['Store_Name'].unique())
                })
                
                total_plt -= load
                fleet[best['type']] -= 1

        # --- PHASE 3: INTERFACE ---
        if dispatched:
            res_df = pd.DataFrame(dispatched)
            st.header("📋 Dispatch Summary")
            
            # تلوين الخلايا (الأخضر للامتلاء المثالي)
            def color_fill(val):
                color = '#27ae60' if 96 <= val <= 104 else '#f39c12'
                return f'background-color: {color}; color: white'

            st.dataframe(res_df.style.applymap(color_fill, subset=['Efficiency_%']), use_container_width=True)

            # Dashboard metrics
            st.divider()
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Total Trips", len(res_df))
            with c2:
                st.metric("Total Budget", f"{res_df['Trip_Cost'].sum():,.2f} MAD")
            with c3:
                avg_eff = res_df['Efficiency_%'].mean()
                st.metric("Avg Efficiency", f"{avg_eff:.1f}%")

            # Chart
            fig = px.bar(res_df, x="Truck", y="Load", color="Zone", title="Load Distribution per Truck Type")
            st.plotly_chart(fig, use_container_width=True)

else:
    st.error("Please check if 'tariffs.csv' has columns: City, Truck, Type, Price")

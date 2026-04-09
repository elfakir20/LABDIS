import streamlit as st
import pandas as pd
import os

# 1. وظيفة تحميل البيانات وتنظيفها
@st.cache_data
def load_all_data():
    base_path = os.path.dirname(__file__)
    stores_path = os.path.join(base_path, 'stores.csv')
    tariffs_path = os.path.join(base_path, 'tariffs.csv')
    
    try:
        if os.path.exists(stores_path) and os.path.exists(tariffs_path):
            stores = pd.read_csv(stores_path)
            tariffs = pd.read_csv(tariffs_path)
            
            # تحويل الأثمان إلى أرقام وحذف القيم غير الصحيحة
            tariffs['Price'] = pd.to_numeric(tariffs['Price'], errors='coerce')
            tariffs = tariffs.dropna(subset=['Price'])
            
            # تنظيف النصوص لضمان مطابقة دقيقة
            for col in ['Truck', 'Type', 'City']:
                tariffs[col] = tariffs[col].astype(str).str.strip()
            tariffs['Truck'] = tariffs['Truck'].str.upper()
            
            return stores, tariffs
        else:
            return None, None
    except Exception as e:
        st.error(f"Error reading CSV files: {e}")
        return None, None

st.set_page_config(page_title="LABDIS Elite v18", layout="wide")
st.title("🚀 LABDIS Elite Logistics AI")
st.info("Skhirat Hub | Priority 200 | Cost-Efficiency Model")

stores_df, tariffs_df = load_all_data()

if stores_df is not None:
    # --- القائمة الجانبية: التحكم في الأسطول ---
    with st.sidebar:
        st.header("🚛 Fleet Inventory")
        f32 = st.number_input("32T (33 PLT):", 0, 100, 10)
        f19 = st.number_input("19T (18 PLT):", 0, 100, 5)
        f7 = st.number_input("7T (12 PLT):", 0, 100, 5)
        
        st.divider()
        wave = st.selectbox("Shipping Wave", ["15:00-23:00", "23:00-7:00"])

    # --- المرحلة 1: معالجة الطلبات ---
    uploaded = st.file_uploader("Upload Daily Orders CSV", type=['csv'])

    if uploaded:
        orders = pd.read_csv(uploaded).fillna(0)
        data = pd.merge(orders, stores_df, on='Store_Code', how='left')
        data = data[data['Loading Window'] == wave].copy()
        
        # منطق الأولويات: كود 200 أولاً ثم الأبعد عن الصخيرات
        data['is_200'] = data['Store_Code'].apply(lambda x: 0 if x == 200 else 1)
        data = data.sort_values(['is_200', 'Zone', 'City'], ascending=[True, False, False])

        # --- المرحلة 2: محرك تحسين التكاليف ---
        dispatched_trucks = []
        fleet_rem = {'32T': f32, '19T': f19, '7T': f7}

        for (zone, truck_limit), group in data.groupby(['Zone', 'Max_Truck_Allowed'], sort=False):
            remaining_vol = group['Fleg_PLT'].sum() + group['Sec_PLT'].sum()
            activity = "Fleg" if group['Fleg_PLT'].sum() > group['Sec_PLT'].sum() else "Sec"
            main_city = str(group['City'].iloc[0])

            while remaining_vol >= 7.5:
                options = []
                for t_type, cap in [('32T', 33), ('19T', 18), ('7T', 12)]:
                    if fleet_rem[t_type] > 0:
                        # البحث عن السعر المطابق في ملف التكاليف
                        p_match = tariffs_df[
                            (tariffs_df['City'].str.lower() == main_city.lower()) & 
                            (tariffs_df['Truck'] == t_type) & 
                            (tariffs_df['Type'].str.contains(activity, case=False, na=False))
                        ]
                        
                        if not p_match.empty:
                            try:
                                price = float(p_match.iloc[0]['Price'])
                                options.append({'type': t_type, 'cap': cap, 'price': price, 'cpp': price/cap})
                            except: continue

                if not options: break

                # اختيار الشاحنة الأنسب (توازن بين الامتلاء 100% وأقل تكلفة)
                best_t = None
                for opt in sorted(options, key=lambda x: x['cap'], reverse=True):
                    if remaining_vol >= opt['cap'] * 0.96:
                        best_t = opt
                        break
                if not best_t: best_t = min(options, key=lambda x: x['cpp'])

                load = min(remaining_vol, best_t['cap'] * 1.04)
                
                dispatched_trucks.append({
                    "TRK_ID": f"TRK-{len(dispatched_trucks)+1:02d}",
                    "Zone": zone, "Type": best_t['type'],
                    "Load": round(load, 1), "Efficiency_%": round((load/best_t['cap'])*100, 1),
                    "Cost_MAD": best_t['price'], "City": main_city
                })
                
                remaining_vol -= load
                fleet_rem[best_t['type']] -= 1

        # --- المرحلة 3: عرض النتائج ---
        if dispatched_trucks:
            res_df = pd.DataFrame(dispatched_trucks)
            st.header("📝 Final Dispatch Plan")
            
            def style_eff(v):
                color = '#27ae60' if 96 <= v <= 104 else '#f39c12'
                return f'background-color: {color}; color: white; font-weight: bold'

            # تعديل applymap إلى map هنا لحل المشكلة
            st.dataframe(res_df.style.map(style_eff, subset=['Efficiency_%']), use_container_width=True)
            
            st.divider()
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Trips", len(res_df))
            c2.metric("Total Cost (MAD)", f"{res_df['Cost_MAD'].sum():,.2f}")
            c3.metric("Avg Efficiency", f"{res_df['Efficiency_%'].mean():.1f}%")
        else:
            st.warning("No trucks could be matched for this volume.")
else:
    st.error("Missing files: app.py, stores.csv, and tariffs.csv must be in the same folder.")

import streamlit as st
import pandas as pd
import numpy as np

@st.cache_data
def load_all_data():
    try:
        # تأكد من أن الأسماء في الملفات مطابقة لما اتفقنا عليه (City, Zone, Truck, Type, Price)
        stores = pd.read_csv('stores.csv') 
        tariffs = pd.read_csv('tariffs.csv')
        return stores, tariffs
    except:
        return None, None

st.set_page_config(page_title="LABDIS Detailed Router", layout="wide")
st.title("🚛 LABDIS AI: Detailed Store Assignment")
st.subheader("Skhirat Hub | Full Load | Store-by-Store Breakdown")

stores_df, tariffs_df = load_all_data()

if stores_df is not None:
    # --- القائمة الجانبية لإدارة الأسطول ---
    with st.sidebar:
        st.header("🚛 Available Fleet")
        f32 = st.number_input("32T (33 PLT):", 0, 50, 10)
        f19 = st.number_input("19T (18 PLT):", 0, 50, 5)
        f7 = st.number_input("7T (12 PLT):", 0, 50, 5)
        wave = st.selectbox("Wave", ["15:00-23:00", "23:00-7:00"])

    uploaded = st.file_uploader("Upload Daily Orders CSV", type=['csv'])

    if uploaded:
        orders = pd.read_csv(uploaded).fillna(0)
        data = pd.merge(orders, stores_df, on='Store_Code', how='left')
        data = data[data['Loading Window'] == wave].copy()
        data['Total_PLT'] = data['Fleg_PLT'] + data['Sec_PLT']
        
        # ترتيب الأولويات: كود 200 أولاً، ثم الأبعد عن الصخيرات
        data['is_200'] = data['Store_Code'].apply(lambda x: 0 if x == 200 else 1)
        data = data.sort_values(['is_200', 'Zone', 'City'], ascending=[True, False, False])

        dispatched_trucks = []
        fleet_rem = {'32T': f32, '19T': f19, '7T': f7}

        # محرك التوزيع الذكي
        for (zone, truck_limit), group in data.groupby(['Zone', 'Max_Truck_Allowed'], sort=False):
            main_city = group['City'].iloc[0]
            # تحويل المتاجر إلى قائمة "بليطات" قابلة للتوزيع
            store_queue = group[['Store_Name', 'Total_PLT', 'Store_Code']].to_dict('records')
            
            while store_queue:
                # تحديد أفضل شاحنة بناءً على الحجم المتبقي والتكلفة
                total_pending = sum(s['Total_PLT'] for s in store_queue)
                
                # اختيار نوع الشاحنة (32T ثم 19T ثم 7T) بناءً على المتاح والامتلاء
                best_t = None
                for t_type, cap in [('32T', 33), ('19T', 18), ('7T', 12)]:
                    if fleet_rem[t_type] > 0 and (truck_limit == t_type or truck_limit == '32T' or (truck_limit == '19T' and t_type == '7T')):
                        if total_pending >= cap * 0.96 or (t_type == '7T' and total_pending > 0):
                            best_t = {'type': t_type, 'cap': cap}
                            break
                
                if not best_t: break

                # ملء الشاحنة بالمتاجر
                current_truck_load = 0
                truck_manifest = []
                max_cap = best_t['cap'] * 1.04
                
                indices_to_remove = []
                for i, store in enumerate(store_queue):
                    space_left = max_cap - current_truck_load
                    if space_left <= 0: break
                    
                    if store['Total_PLT'] <= space_left:
                        # المتجر يدخل بالكامل
                        truck_manifest.append(f"{store['Store_Name']} ({store['Total_PLT']} PLT)")
                        current_truck_load += store['Total_PLT']
                        indices_to_remove.append(i)
                    else:
                        # تقسيم المتجر (يأخذ ما تبقى من مساحة والباقي يبقى في الطابور)
                        truck_manifest.append(f"{store['Store_Name']} ({round(space_left, 1)} PLT - PARTIAL)")
                        store['Total_PLT'] -= space_left
                        current_truck_load += space_left
                        # لا نحذف المتجر من القائمة لأنه مازال فيه بليطات متبقية
                        break
                
                # حذف المتاجر التي شحنت بالكامل
                for index in sorted(indices_to_remove, reverse=True):
                    store_queue.pop(index)

                # حساب التكلفة
                p_match = tariffs_df[(tariffs_df['City'] == main_city) & (tariffs_df['Truck'] == best_t['type'])]
                cost = p_match.iloc[0]['Price'] if not p_match.empty else 0

                dispatched_trucks.append({
                    "Truck_Type": best_t['type'],
                    "Zone": zone,
                    "Destination": main_city,
                    "Total_Load": round(current_truck_load, 1),
                    "Efficiency_%": round((current_truck_load / best_t['cap']) * 100, 1),
                    "Detailed_Manifest": " + ".join(truck_manifest),
                    "Cost_MAD": cost
                })
                fleet_rem[best_t['type']] -= 1

        # عرض النتائج
        if dispatched_trucks:
            res_df = pd.DataFrame(dispatched_trucks)
            st.header("📋 Loading Manifest (Who goes with whom)")
            
            # عرض الجدول مع التركيز على عمود المتاجر التفصيلي
            st.dataframe(res_df[['Truck_Type', 'Zone', 'Detailed_Manifest', 'Total_Load', 'Efficiency_%', 'Cost_MAD']], use_container_width=True)
            
            # رسومات توضيحية
            st.divider()
            st.metric("Total Transportation Cost", f"{res_df['Cost_MAD'].sum():,.2f} MAD")
        else:
            st.warning("No trucks could be filled to 100%. Check your fleet or volume.")

else:
    st.error("Missing Data Files on GitHub.")

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(page_title="LABDIS AI Optimizer v15", layout="wide")

# --- 1. بناء قاعدة البيانات داخلياً (Embedded Data) ---
def get_internal_data():
    # بيانات التسعيرة التي أرسلتها (تم تنظيفها)
    tariff_data = [
        ["Berkane","32T","Fleg",6200], ["Casablanca","32T","Fleg",1540],
        ["Tanger","32T","Fleg",4620], ["Agadir","7T","Fleg",3100],
        ["Fes","19T","Fleg",3024], ["TINGHIR","32T","Fleg",9700],
        ["Rabat","32T","Fleg",1650], ["Mohammedia","32T","Fleg",1100],
        ["Oujda","32T","Fleg",6400], ["Marrakech","32T","Fleg",4840]
    ]
    tariffs = pd.DataFrame(tariff_data, columns=['City', 'Truck', 'Type', 'Price'])
    
    # بيانات المتاجر التي أرسلتها
    store_data = [
        [774,"MARKET RACING","Casablanca","Casa-Settat","19T","23:00-7:00"],
        [769,"RABAT LA CARROUSEL","Rabat","Rabat-Sale","32T","15:00-23:00"],
        [7114,"MARKET TINGHIR","TINGHIR","Draa-Tafilal","32T","15:00-23:00"],
        [7504,"SUPECO SKHIRAT","SKHIRAT","SKHIRAT","19T","15:00-23:00"]
    ]
    stores = pd.DataFrame(store_data, columns=['Store_Code', 'Store_Name', 'City', 'Zone', 'Max_Truck_Allowed', 'Loading Window'])
    
    return stores, tariffs

st.title("💰 LABDIS AI Cost & Load Master v15.0")
st.success("✅ Engine Ready: Internal Database Loaded (No CSV required)")

stores_df, tariffs_df = get_internal_data()

# --- 2. التحكم في الأسطول ---
with st.sidebar:
    st.header("🚛 Fleet Availability")
    f_32t = st.number_input("32T (33 PLT):", 0, 50, 10)
    f_19t = st.number_input("19T (18 PLT):", 0, 50, 5)
    f_7t = st.number_input("7T (12 PLT):", 0, 50, 5)
    wave = st.selectbox("Wave", ["15:00-23:00", "23:00-7:00"])

# --- 3. رفع طلبيات اليوم ---
st.subheader("📊 Daily Orders Input")
uploaded_orders = st.file_uploader("Upload Today's Orders CSV", type=['csv'])

if uploaded_orders:
    orders = pd.read_csv(uploaded_orders)
    # دمج البيانات
    data = pd.merge(orders, stores_df, on='Store_Code', how='left')
    data = data[data['Loading Window'] == wave].copy()
    
    if data.empty:
        st.warning(f"No orders found for the wave: {wave}")
    else:
        # خوارزمية التوزيع الذكي
        dispatched = []
        fleet = {'32T': f_32t, '19T': f_19t, '7T': f_7t}
        
        for zone, group in data.groupby('Zone'):
            total_plt = group['Fleg_PLT'].sum() + group['Sec_PLT'].sum()
            city = group['City'].iloc[0]
            
            while total_plt > 0:
                # البحث عن أفضل خيار سعر
                options = []
                for t, cap in [('32T', 33), ('19T', 18), ('7T', 12)]:
                    if fleet[t] > 0:
                        match = tariffs_df[(tariffs_df['City'] == city) & (tariffs_df['Truck'] == t)]
                        if not match.empty:
                            price = match.iloc[0]['Price']
                            options.append({'type': t, 'cap': cap, 'price': price, 'cpp': price/cap})
                
                if not options: break
                
                best = min(options, key=lambda x: x['cpp'])
                load = min(total_plt, best['cap'])
                
                dispatched.append({
                    "Zone": zone, "Truck": best['type'], "Load": load,
                    "Efficiency": f"{(load/best['cap'])*100:.1f}%",
                    "Cost": best['price'], "City": city
                })
                total_plt -= load
                fleet[best['type']] -= 1

        if dispatched:
            st.write("### 📋 Dispatch Plan")
            st.table(pd.DataFrame(dispatched))
            st.metric("Total Budget", f"{sum(d['Cost'] for d in dispatched):,.2f} MAD")

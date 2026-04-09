import streamlit as st
import pandas as pd

# تحميل قواعد البيانات
@st.cache_data
def load_data():
    # تأكد أن الأسماء مطابقة لما هو موجود في GitHub
    stores = pd.read_csv('DataBase Stor.xlsx - Database .csv')
    tariffs = pd.read_csv('DataBase Stor.xlsx - TRANSPORT TARIFF DATABASE.csv')
    return stores, tariffs

st.set_page_config(page_title="LABDIS Logistics AI", layout="wide")
st.title("🚚 نظام LABDIS لتخطيط الشحنات الذكي")

try:
    stores_df, tariffs_df = load_data()
    
    # القائمة الجانبية
    st.sidebar.header("⚙️ التحكم في النوبات")
    wave = st.sidebar.selectbox("اختر نوبة الشحن الحالية:", ["15:00-23:00", "23:00-7:00"])

    # رفع ملف طلبيات اليوم
    st.header("📥 تحميل طلبيات اليوم")
    uploaded_file = st.file_uploader("ارفع ملف الطلبيات (يجب أن يحتوي على كود المتجر وعدد البليطات)")

    if uploaded_file:
        daily_orders = pd.read_csv(uploaded_file)
        # ربط الطلبيات ببيانات المتاجر
        res = pd.merge(daily_orders, stores_df, on='Store_Code', how='left')
        
        # تصفية حسب النوبة المختارة
        res_wave = res[res['Loading Window'] == wave]
        
        st.subheader(f"✅ الخطة المقترحة لنوبة: {wave}")
        
        # تنبيهات القيود (19T Max)
        for i, row in res_wave.iterrows():
            if row['Max_Truck_Allowed'] == '19T':
                st.warning(f"🚨 تنبيه: المتجر {row['Store_Name']} في {row['City']} شارع ضيق (19T فقط)!")

        st.dataframe(res_wave[['Store_Code', 'Store_Name', 'City', 'Max_Truck_Allowed', 'Receiving Window']])
        
except Exception as e:
    st.error(f"تأكد من رفع ملفات الـ CSV في GitHub: {e}")
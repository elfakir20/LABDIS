import streamlit as st
import pandas as pd

# تحميل البيانات مع معالجة الأخطاء
@st.cache_data
def load_data():
    try:
        # تأكد أن الأسماء مطابقة لما هو موجود في GitHub بعد التعديل
        stores = pd.read_csv('stores.csv')
        tariffs = pd.read_csv('tariffs.csv')
        return stores, tariffs
    except FileNotFoundError:
        return None, None

st.set_page_config(page_title="LABDIS Logistics AI", layout="wide")
st.title("🚚 نظام LABDIS لتخطيط الشحنات الذكي")

stores_df, tariffs_df = load_data()

if stores_df is None:
    st.error("❌ ملفات القاعدة (stores.csv أو tariffs.csv) غير موجودة في GitHub.")
else:
    # القائمة الجانبية
    st.sidebar.header("⚙️ الإعدادات")
    wave = st.sidebar.selectbox("اختر نوبة الشحن:", ["15:00-23:00", "23:00-7:00"])
    activity = st.sidebar.selectbox("نوع النشاط:", ["Fleg", "Sec", "Surgele"])

    # واجهة رفع الطلبيات
    st.header("📥 تحميل طلبيات اليوم")
    uploaded_file = st.file_uploader("ارفع ملف الطلبيات (CSV)", type=['csv'])

    if uploaded_file:
        try:
            daily_orders = pd.read_csv(uploaded_file)
            
            if 'Store_Code' in daily_orders.columns:
                # 1. ربط الطلبيات ببيانات المتاجر
                res = pd.merge(daily_orders, stores_df, on='Store_Code', how='left')
                
                # 2. تصفية حسب النوبة
                res_wave = res[res['Loading Window'] == wave].copy()
                
                # 3. جلب التعرفة (Tarif) بناءً على المدينة والنشاط
                # كنفترضو أن الشاحنة المستعملة هي 32T إلا إذا كان المتجر "ضيق"
                def get_cost(row):
                    truck = row['Max_Truck_Allowed']
                    city = row['City']
                    # البحث في جدول التعرفة
                    match = tariffs_df[(tariffs_df['Ville / City'] == city) & 
                                       (tariffs_df['Véhicule'] == truck) & 
                                       (tariffs_df['Activité'] == activity)]
                    if not match.empty:
                        return match.iloc[0]['Tarif (MAD)']
                    return 0

                res_wave['Estimated_Cost'] = res_wave.apply(get_cost, axis=1)
                
                st.subheader(f"✅ الخطة المقترحة لنوبة: {wave} | النشاط: {activity}")
                
                # عرض التنبيهات
                for i, row in res_wave.iterrows():
                    if row['Max_Truck_Allowed'] == '19T':
                        st.warning(f"🚨 تنبيه: المتجر {row['Store_Name']} ({row['City']}) - شارع ضيق (19T Max)!")
                
                # عرض النتائج
                cols_to_show = ['Store_Code', 'Store_Name', 'City', 'Max_Truck_Allowed', 'Estimated_Cost']
                st.dataframe(res_wave[cols_to_show])
                
                # خلاصة مالية
                total_cost = res_wave['Estimated_Cost'].sum()
                st.metric("المجموع التقديري للتكلفة", f"{total_cost:,.2f} MAD")
                
            else:
                st.error("ملف الطلبيات يجب أن يحتوي على عمود باسم 'Store_Code'")
        except Exception as e:
            st.error(f"حدث خطأ أثناء معالجة الملف: {e}")

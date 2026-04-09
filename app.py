import streamlit as st
import pandas as pd
import os

# =========================
# 🔥 DATA LOADING
# =========================
@st.cache_data
def load_all_data():
    base_path = os.path.dirname(__file__)
    stores_path = os.path.join(base_path, 'stores.csv')
    tariffs_path = os.path.join(base_path, 'tariffs.csv')

    if not (os.path.exists(stores_path) and os.path.exists(tariffs_path)):
        return None, None

    stores = pd.read_csv(stores_path)
    tariffs = pd.read_csv(tariffs_path)

    tariffs['Price'] = pd.to_numeric(tariffs['Price'], errors='coerce')
    tariffs = tariffs.dropna(subset=['Price'])

    tariffs['Truck'] = tariffs['Truck'].str.upper().str.strip()
    tariffs['Type'] = tariffs['Type'].str.strip()

    return stores, tariffs


# =========================
# 🧠 AI SCORING ENGINE
# =========================
def score_truck(volume, cap, price):
    fill = (min(volume, cap) / cap) * 100
    cost_eff = price / cap
    score = (fill * 0.7) - (cost_eff * 0.3)
    return score, fill


# =========================
# 🎨 STYLE FUNCTION
# =========================
def style_eff(v):
    try:
        v = float(v)
        color = '#27ae60' if 96 <= v <= 104 else '#f39c12'
        return f'background-color: {color}; color: white; font-weight: bold'
    except:
        return ''


# =========================
# 🚀 APP CONFIG
# =========================
st.set_page_config(page_title="AI TMS v17", layout="wide")

st.title("🚀 LABDIS AI TMS v17")
st.info("AI Optimization | Cost Control | Fleet Intelligence")

stores_df, tariffs_df = load_all_data()

if stores_df is None:
    st.error("Missing stores.csv or tariffs.csv in project folder")
    st.stop()

# =========================
# 🚛 SIDEBAR FLEET
# =========================
with st.sidebar:
    st.header("🚛 Fleet Control")
    f32 = st.number_input("32T", 0, 100, 10)
    f19 = st.number_input("19T", 0, 100, 5)
    f7 = st.number_input("7T", 0, 100, 5)

    wave = st.selectbox("Wave", ["15:00-23:00", "23:00-7:00"])


# =========================
# 📥 INPUT ORDERS
# =========================
uploaded = st.file_uploader("Upload Orders CSV", type=['csv'])

if uploaded:

    orders = pd.read_csv(uploaded).fillna(0)

    data = pd.merge(orders, stores_df, on='Store_Code', how='left')
    data = data[data['Loading Window'] == wave].copy()

    data['is_200'] = data['Store_Code'].apply(lambda x: 0 if x == 200 else 1)
    data = data.sort_values(['is_200', 'Zone', 'City'], ascending=[True, False, False])

    fleet_rem = {'32T': f32, '19T': f19, '7T': f7}
    dispatched = []

    # =========================
    # 🧠 AI DISPATCH ENGINE
    # =========================
    for (zone, truck_limit), group in data.groupby(['Zone', 'Max_Truck_Allowed'], sort=False):

        remaining_vol = group['Fleg_PLT'].sum() + group['Sec_PLT'].sum()

        activity = "Fleg" if group['Fleg_PLT'].sum() > group['Sec_PLT'].sum() else "Sec"
        main_city = group['City'].iloc[0]

        while remaining_vol >= 7.5:

            options = []

            for t_type, cap in [('32T', 33), ('19T', 18), ('7T', 12)]:

                if fleet_rem[t_type] <= 0:
                    continue

                p_match = tariffs_df[
                    (tariffs_df['City'].str.lower() == main_city.lower()) &
                    (tariffs_df['Truck'] == t_type) &
                    (tariffs_df['Type'].str.contains(activity, case=False, na=False))
                ]

                if not p_match.empty:
                    price = float(p_match.iloc[0]['Price'])

                    score, fill = score_truck(remaining_vol, cap, price)

                    options.append({
                        "type": t_type,
                        "cap": cap,
                        "price": price,
                        "score": score,
                        "fill": fill
                    })

            if not options:
                break

            best = max(options, key=lambda x: x['score'])

            load = min(remaining_vol, best['cap'] * 1.04)

            dispatched.append({
                "TRK_ID": f"TRK-{len(dispatched)+1:02d}",
                "Zone": zone,
                "Type": best['type'],
                "City": main_city,
                "Load": round(load, 1),
                "Efficiency_%": round((load / best['cap']) * 100, 1),
                "Cost_MAD": best['price'],
                "AI_Score": round(best['score'], 2)
            })

            remaining_vol -= load
            fleet_rem[best['type']] -= 1


    # =========================
    # 📊 RESULTS DASHBOARD
    # =========================
    if dispatched:

        res_df = pd.DataFrame(dispatched)

        st.header("📝 AI Dispatch Plan")

        st.write(
            res_df.style.applymap(style_eff, subset=['Efficiency_%'])
        )

        st.divider()

        c1, c2, c3, c4 = st.columns(4)

        c1.metric("🚚 Trips", len(res_df))
        c2.metric("💰 Cost", f"{res_df['Cost_MAD'].sum():,.2f} MAD")
        c3.metric("📦 Avg Efficiency", f"{res_df['Efficiency_%'].mean():.1f}%")
        c4.metric("🧠 Avg AI Score", f"{res_df['AI_Score'].mean():.2f}")

    else:
        st.warning("No optimized trucks generated for this dataset.")

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# 1. Loading Master Data
@st.cache_data
def load_all_data():
    try:
        stores = pd.read_csv('stores.csv')
        tariffs = pd.read_csv('tariffs.csv')
        return stores, tariffs
    except:
        return None, None

st.set_page_config(page_title="LABDIS Smart Cost Optimizer", layout="wide")

# Custom UI for a sophisticated look
st.markdown("""
    <style>
    .stApp { background-color: #f4f7f6; }
    .metric-card { background: white; padding: 20px; border-radius: 10px; box-shadow: 2px 2px 10px rgba(0,0,0,0.1); }
    </style>
    """, unsafe_allow_html=True)

st.title("💰 LABDIS AI Cost & Load Optimizer v13.0")
st.info("Strategy: Minimum Cost + 100% Efficiency + Priority Hub Skhirat")

stores_df, tariffs_df = load_all_data()

if stores_df is not None:
    # --- SIDEBAR: FLEET & CONSTRAINTS ---
    with st.sidebar:
        st.header("🚛 Fleet Availability")
        f_32T = st.number_input("32T (33 PLT) Count:", 0, 50, 10)
        f_19T = st.number_input("19T (18 PLT) Count:", 0, 50, 5)
        f_7T = st.number_input("7T (12 PLT) Count:", 0, 50, 5)
        
        st.divider()
        current_wave = st.selectbox("Shipping Wave", ["15:00-23:00", "23:00-7:00"])
        st.success("Priority: Store Code 200 & Furthest Zones First")

    # --- PHASE 1: DATA PROCESSING ---
    uploaded = st.file_uploader("Upload Daily Orders CSV", type=['csv'])

    if uploaded:
        orders = pd.read_csv(uploaded).fillna(0)
        data = pd.merge(orders, stores_df, on='Store_Code', how='left')
        data = data[data['Loading Window'] == current_wave].copy()
        
        # Priority Logic: Store 200 First, then Far to Near from Skhirat
        data['Priority'] = data['Store_Code'].apply(lambda x: 0 if x == 200 else 1)
        data = data.sort_values(['Priority', 'Zone', 'City'], ascending=[True, False, False])

        # --- PHASE 2: COST-OPTIMIZED ALLOCATION ---
        dispatched = []
        fleet = {'32T': f_32T, '19T': f_19T, '7T': f_7T}
        
        for zone, zone_group in data.groupby('Zone', sort=False):
            remaining_plt = zone_group['Fleg_PLT'].sum() + zone_group['Sec_PLT'].sum()
            main_city = zone_group['City'].iloc[0]
            activity = "Fleg" if zone_group['Fleg_PLT'].sum() > zone_group['Sec_PLT'].sum() else "Sec"
            
            while remaining_plt >= 8: # Minimum to justify a truck
                # Find available vehicle options for this zone
                possible_trucks = []
                for t_type, cap in [('32T', 33), ('19T', 18), ('7T', 12)]:
                    if fleet[t_type] > 0 and zone_group['Max_Truck_Allowed'].iloc[0] in [t_type, '32T']:
                        # Fetch price from tariffs
                        price_row = tariffs_df[(tariffs_df['Ville / City'] == main_city) & 
                                               (tariffs_df['Véhicule'] == t_type) & 
                                               (tariffs_df['Activité'] == activity)]
                        if not price_row.empty:
                            base_price = price_row.iloc[0]['Tarif (MAD)']
                            # Calculation: Cost per Pallet (The ultimate metric for efficiency)
                            cost_per_plt = base_price / cap
                            possible_trucks.append({'type': t_type, 'cap': cap, 'price': base_price, 'cpp': cost_per_plt})

                if not possible_trucks: break

                # THE SMART CHOICE: Select truck with lowest COST PER PALLET that is available
                best_choice = min(possible_trucks, key=lambda x: x['cpp'])
                
                # Check if we should use a smaller truck to hit 100% fill
                for truck in possible_trucks:
                    if remaining_plt <= truck['cap'] * 1.04 and truck['cap'] < best_choice['cap']:
                        best_choice = truck # Downsize for better fill rate
                
                load = min(remaining_plt, best_choice['cap'] * 1.04)
                
                dispatched.append({
                    "Zone": zone, "Truck": best_choice['type'], "Load": round(load, 1),
                    "Fill_%": round((load / best_choice['cap']) * 100, 1),
                    "Cost": best_choice['price'], "City": main_city,
                    "Stores": ", ".join(zone_group['Store_Name'].unique())
                })
                
                remaining_plt -= load
                fleet[best_choice['type']] -= 1

        # --- PHASE 3: ADVANCED VISUALIZATION & RESULTS ---
        res_df = pd.DataFrame(dispatched)
        
        st.header("📊 Delivery Dispatch Board")
        st.dataframe(res_df.style.background_gradient(cmap='Greens', subset=['Fill_%']), use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("💰 Cost Distribution per Zone")
            fig = px.pie(res_df, values='Cost', names='Zone', hole=0.4)
            st.plotly_chart(fig)
        
        with col2:
            st.subheader("🚚 Fleet Utilization Summary")
            fig2 = px.bar(res_df, x='Truck', y='Load', color='Zone', barmode='group')
            st.plotly_chart(fig2)

        st.divider()
        total_cost = res_df['Cost'].sum()
        st.metric("Total Transportation Budget (MAD)", f"{total_cost:,.2f}")

else:
    st.error("Missing Data Files! Connect Skhirat Hub Databases.")

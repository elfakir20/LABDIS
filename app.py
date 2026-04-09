import streamlit as st
import pandas as pd
import numpy as np

# 1. Load Data with simplified headers
@st.cache_data
def load_all_data():
    try:
        stores = pd.read_csv('stores.csv') # Must have: Store_Code, Store_Name, Zone, City, Max_Truck_Allowed, Loading Window
        tariffs = pd.read_csv('tariffs.csv') # Must have: City, Zone, Truck, Type, Price
        return stores, tariffs
    except:
        return None, None

st.set_page_config(page_title="LABDIS Elite Optimizer", layout="wide")
st.title("🚀 LABDIS Elite Logistics AI")
st.subheader("Skhirat Hub | Priority 200 | 100% Load | Cost Optimization")

stores_df, tariffs_df = load_all_data()

if stores_df is not None:
    # --- SIDEBAR: FLEET CONTROL ---
    with st.sidebar:
        st.header("🚛 Available Fleet")
        f32 = st.number_input("32T Available:", 0, 50, 10)
        f19 = st.number_input("19T Available:", 0, 50, 5)
        f7 = st.number_input("7T Available (12 PLT):", 0, 50, 5)
        
        wave = st.selectbox("Wave", ["15:00-23:00", "23:00-7:00"])
        st.write("---")
        st.write("Target: 100% Efficiency (96-104%)")

    # --- PHASE 1: PRE-PROCESSING & SPLITTING ---
    uploaded = st.file_uploader("Upload Orders CSV", type=['csv'])

    if uploaded:
        orders = pd.read_csv(uploaded).fillna(0)
        data = pd.merge(orders, stores_df, on='Store_Code', how='left')
        data = data[data['Loading Window'] == wave].copy()
        
        # Applying Rule: Priority for Code 200 & Far to Near Routing
        data['is_200'] = data['Store_Code'].apply(lambda x: 0 if x == 200 else 1)
        data = data.sort_values(['is_200', 'Zone', 'City'], ascending=[True, False, False])

        # --- PHASE 2: RECURSIVE LOAD BALANCING ENGINE ---
        dispatched_trucks = []
        fleet_rem = {'32T': f32, '19T': f19, '7T': f7}

        for (zone, truck_limit), group in data.groupby(['Zone', 'Max_Truck_Allowed'], sort=False):
            # Sum total volume in the Zone
            zone_fleg = group['Fleg_PLT'].sum()
            zone_sec = group['Sec_PLT'].sum()
            remaining_volume = zone_fleg + zone_sec
            activity = "Fleg" if zone_fleg > zone_sec else "Sec"
            main_city = group['City'].iloc[0]

            while remaining_volume >= 8: # Don't send empty trucks
                # 💰 STEP: Cost Evaluation (Check all possible trucks for this zone)
                options = []
                for t_type, cap in [('32T', 33), ('19T', 18), ('7T', 12)]:
                    # Check if truck is allowed in this zone and available in fleet
                    if fleet_rem[t_type] > 0 and (truck_limit == t_type or truck_limit == '32T' or (truck_limit == '19T' and t_type == '7T')):
                        p_match = tariffs_df[(tariffs_df['City'] == main_city) & 
                                             (tariffs_df['Truck'] == t_type) & 
                                             (tariffs_df['Type'] == activity)]
                        if not p_match.empty:
                            price = p_match.iloc[0]['Price']
                            options.append({'type': t_type, 'cap': cap, 'price': price, 'cpp': price/cap})

                if not options: break

                # Find best truck: Minimum Price that hits 100% Fill Rate
                # We prioritize the truck that fits the 'remaining_volume' best first
                best_t = None
                for opt in sorted(options, key=lambda x: x['cap'], reverse=True):
                    if remaining_volume >= opt['cap'] * 0.96:
                        best_t = opt
                        break
                
                # If no truck fits perfectly, take the one with lowest Cost Per Pallet (CPP)
                if not best_t:
                    best_t = min(options, key=lambda x: x['cpp'])

                # Execution: Fill and Dispatch
                load_to_assign = min(remaining_volume, best_t['cap'] * 1.04)
                fill_rate = (load_to_assign / best_t['cap']) * 100
                
                dispatched_trucks.append({
                    "TRK_ID": f"TRK-{len(dispatched_trucks)+1:02d}",
                    "Zone": zone,
                    "Truck": best_t['type'],
                    "Load": round(load_to_assign, 1),
                    "Efficiency": round(fill_rate, 1),
                    "Cost_MAD": best_t['price'],
                    "Stores": " | ".join(group['Store_Name'].unique()),
                    "Route": f"From Skhirat to {main_city} (via {zone})"
                })

                remaining_volume -= load_to_assign
                fleet_rem[best_t['type']] -= 1

        # --- PHASE 3: ADVANCED REPORTING ---
        if dispatched_trucks:
            final_df = pd.DataFrame(dispatched_trucks)
            
            st.header("📝 Final Dispatch Plan")
            
            # Highlight 100% efficiency
            def style_eff(v):
                color = '#27ae60' if 96 <= v <= 104 else '#f39c12'
                return f'background-color: {color}; color: white; font-weight: bold'

            st.dataframe(final_df.style.applymap(style_eff, subset=['Efficiency']), use_container_width=True)

            # Dashboard metrics
            st.divider()
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Total Trips", len(final_df))
            with c2:
                st.metric("Total Budget", f"{final_df['Cost_MAD'].sum():,.2f} MAD")
            with c3:
                st.metric("Average Fill Rate", f"{final_df['Efficiency'].mean():.1f}%")
        else:
            st.info("No enough volume to create a 100% loaded truck.")
else:
    st.error("Error: Please upload 'stores.csv' and 'tariffs.csv' to your GitHub repo with the new headers.")

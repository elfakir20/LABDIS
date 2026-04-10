import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import io, warnings
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

# Ignore technical warnings
warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# 1. CONFIGURATION & CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
TRUCK_CAPACITY = {"32T": 33, "19T": 18, "7T": 12}
TRUCK_PRIORITY = ["32T", "19T", "7T"]

# Distance ranking for route prioritization (furthest to nearest from Skhirat)
ZONE_DISTANCE_RANK = {
    "Souss-Massa": 10, "Marrakech-Safi": 9, "Draa-Tafilalet": 8,
    "Oriental": 7, "Tanger-Tetouan-Al Hoceima": 6, "Fs-Mekns": 5,
    "Beni Mellal-Khénifra": 4, "El Jadida": 3, "Casa-Settat": 2,
    "Rabat-Sal-Knitra": 1, "Unknown": 0,
}

# ─────────────────────────────────────────────────────────────────────────────
# 2. DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class StoreOrder:
    store_code: str
    store_name: str
    city: str
    zone: str
    max_truck: str
    fleg_plt: int
    sec_plt: int
    total_plt: int

@dataclass
class TruckLoad:
    truck_id: str
    truck_type: str
    city: str
    zone: str
    capacity: int
    stores: List[StoreOrder] = field(default_factory=list)
    fleg_cost: float = 0.0
    sec_cost: float = 0.0

    @property
    def total_plt(self): return sum(s.total_plt for s in self.stores)
    
    @property
    def utilization(self): return self.total_plt / self.capacity if self.capacity else 0
    
    @property
    def total_cost(self): return self.fleg_cost + self.sec_cost
    
    @property
    def manifest(self): 
        return " + ".join([f"{s.store_name} ({s.total_plt} PLT)" for s in self.stores])

# ─────────────────────────────────────────────────────────────────────────────
# 3. CORE LOGIC ENGINES
# ─────────────────────────────────────────────────────────────────────────────
def build_tariff_lookup(df):
    """Creates a fast lookup dictionary for transport costs."""
    lookup = {}
    for _, row in df.iterrows():
        # Key: (city, truck_type, product_type)
        key = (str(row['City']).strip().lower(), str(row['Truck']).strip(), str(row['Type']).strip().lower())
        lookup[key] = float(row['Price'])
    return lookup

def plan_loads(merged_df, lookup):
    """Optimizes store orders into truck loads using First-Fit Decreasing logic."""
    loads = []
    truck_counts = {}
    
    # Sort by furthest zone first
    merged_df['Rank'] = merged_df['Zone'].map(ZONE_DISTANCE_RANK).fillna(0)
    sorted_df = merged_df.sort_values(by=['Rank', 'City'], ascending=[False, True])

    for (zone, city), grp in sorted_df.groupby(["Zone", "City"], sort=False):
        city_max = grp["Max_Truck_Allowed"].iloc[0]
        cap = TRUCK_CAPACITY.get(city_max, 18)
        
        # Bin Packing Algorithm
        current_bins: List[List[StoreOrder]] = []
        for _, row in grp.iterrows():
            so = StoreOrder(
                str(row["Store_Code"]), str(row["Store_Name"]), city, zone, 
                city_max, int(row["Fleg_PLT"]), int(row["Sec_PLT"]), int(row["Total_PLT"])
            )
            
            placed = False
            for b in current_bins:
                if sum(s.total_plt for s in b) + so.total_plt <= cap:
                    b.append(so)
                    placed = True
                    break
            if not placed: current_bins.append([so])
            
        # Finalize Truck Objects
        for b in current_bins:
            t_type = city_max 
            t_id_count = truck_counts.get(t_type, 0) + 1
            truck_counts[t_type] = t_id_count
            
            tl = TruckLoad(f"{t_type}-{t_id_count:03d}", t_type, city, zone, TRUCK_CAPACITY[t_type], b)
            
            # Fetch costs from lookup
            has_fleg = sum(s.fleg_plt for s in b) > 0
            has_sec = sum(s.sec_plt for s in b) > 0
            
            if has_fleg: tl.fleg_cost = lookup.get((city.lower(), t_type, "fleg"), 0)
            if has_sec: tl.sec_cost = lookup.get((city.lower(), t_type, "sec"), 0)
            loads.append(tl)
            
    return loads

# ─────────────────────────────────────────────────────────────────────────────
# 4. STREAMLIT UI & DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(page_title="Skhirat Hub Logistics", layout="wide")
    
    st.markdown("""
        <div style="background: linear-gradient(135deg, #0057B8 0%, #00A3E0 100%); padding:20px; border-radius:10px; color:white;">
            <h1 style='margin:0;'>🚛 Skhirat Hub — Distribution Optimizer</h1>
            <p style='margin:0; opacity:0.8;'>Fleet Optimization & Cost Control System</p>
        </div>
    """, unsafe_allow_html=True)
    st.write("")

    with st.sidebar:
        st.header("📥 Data Input")
        f_stores = st.file_uploader("Upload Stores Database (CSV)", type="csv")
        f_orders = st.file_uploader("Upload Daily Orders (CSV)", type="csv")
        f_tariffs = st.file_uploader("Upload Tariff Table (CSV)", type="csv")
        st.divider()
        st.info("Ensure columns match: Store_Code, Fleg_PLT, Sec_PLT, City, Price.")

    if f_stores and f_orders and f_tariffs:
        # Load Data
        stores = pd.read_csv(f_stores)
        orders = pd.read_csv(f_orders)
        tariffs = pd.read_csv(f_tariffs)
        
        # Build Engine
        lookup = build_tariff_lookup(tariffs)
        merged = orders.merge(stores, on="Store_Code", how="left").fillna(0)
        merged["Total_PLT"] = merged["Fleg_PLT"] + merged["Sec_PLT"]
        
        # Run Optimization
        loads = plan_loads(merged, lookup)
        
        # Convert Results for Display
        res_list = []
        for l in loads:
            res_list.append({
                "Truck ID": l.truck_id, "Type": l.truck_type, "City": l.city, 
                "Zone": l.zone, "PLT Loaded": l.total_plt, 
                "Util %": round(l.utilization*100, 1),
                "Total Cost (MAD)": l.total_cost, "Detailed Manifest": l.manifest
            })
        df_res = pd.DataFrame(res_list)

        # KPI Metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Trucks", len(df_res))
        c2.metric("Total Pallets", int(df_res["PLT Loaded"].sum()))
        c3.metric("Total Cost (MAD)", f"{df_res['Total Cost (MAD)'].sum():,.0f}")
        c4.metric("Avg Utilization", f"{df_res['Util %'].mean():.1f}%")

        # Visual Tabs
        t1, t2, t3 = st.tabs(["📋 Load Plan", "📊 Analytics", "📍 Geography"])
        
        with t1:
            st.subheader("Final Truck Manifest")
            st.dataframe(df_res, use_container_width=True)
            
            # Excel Export
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_res.to_excel(writer, index=False, sheet_name="LoadPlan")
            st.download_button(
                label="⬇️ Download Manifest (Excel)",
                data=output.getvalue(),
                file_name="skhirat_logistics_plan.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        with t2:
            st.subheader("Fleet Utilization & Distribution")
            col_a, col_b = st.columns(2)
            with col_a:
                fig1 = px.pie(df_res, names="Type", title="Truck Type Mix")
                st.plotly_chart(fig1, use_container_width=True)
            with col_b:
                fig2 = px.bar(df_res, x="Zone", y="Total Cost (MAD)", color="Type", title="Costs by Zone")
                st.plotly_chart(fig2, use_container_width=True)

        with t3:
            st.subheader("Store Distribution Map")
            if 'lat' in stores.columns and 'lon' in stores.columns:
                st.map(stores[['lat', 'lon']])
            else:
                st.warning("Mapping requires 'lat' and 'lon' columns in the Stores file.")
    else:
        st.warning("Waiting for CSV file uploads to begin optimization.")

if __name__ == "__main__":
    main()

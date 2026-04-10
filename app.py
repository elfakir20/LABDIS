"""
=============================================================================
  SKHIRAT HUB — LOGISTICS OPTIMIZATION PLATFORM
  Distribution Hub: Skhirat, Morocco
  Engine: Pandas + OR-Tools + Plotly + Streamlit
=============================================================================
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import io, warnings

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# 0. CONSTANTS & CONFIG
# ─────────────────────────────────────────────────────────────────────────────
TRUCK_CAPACITY = {"32T": 33, "19T": 18, "7T": 12}
TRUCK_PRIORITY = ["32T", "19T", "7T"]  # Preferred order
LOAD_MIN_PCT = 0.96
LOAD_MAX_PCT = 1.04
PRIORITY_STORE = "200" # Changed to string for matching consistency

ZONE_DISTANCE_RANK = {
    "Souss-Massa": 10,
    "Marrakech-Safi": 9,
    "Draa-Tafilalet": 8,
    "Oriental": 7,
    "Tanger-Tetouan-Al Hoceima": 6,
    "Fs-Mekns": 5,
    "Beni Mellal-Khénifra": 4,
    "El Jadida": 3,
    "Casa-Settat": 2,
    "Rabat-Sal-Knitra": 1,
    "Unknown": 0,
}

# ─────────────────────────────────────────────────────────────────────────────
# 1. DATA MODELS (Simplified Classes for processing)
# ─────────────────────────────────────────────────────────────────────────────
class StoreOrder:
    def __init__(self, store_code, store_name, city, zone, max_truck, fleg_plt, sec_plt):
        self.store_code = store_code
        self.store_name = store_name
        self.city = city
        self.zone = zone
        self.max_truck = max_truck
        self.fleg_plt = fleg_plt
        self.sec_plt = sec_plt
        self.total_plt = fleg_plt + sec_plt

class TruckLoad:
    def __init__(self, truck_id, truck_type, city, zone, capacity):
        self.truck_id = truck_id
        self.truck_type = truck_type
        self.city = city
        self.zone = zone
        self.capacity = capacity
        self.stores = []
        self.fleg_cost = 0.0
        self.sec_cost = 0.0

    @property
    def total_plt(self): return sum(s.total_plt for s in self.stores)
    @property
    def utilization(self): return self.total_plt / self.capacity if self.capacity else 0.0
    @property
    def manifest(self): return " + ".join([f"{s.store_name} ({s.total_plt}P)" for s in self.stores])

# ─────────────────────────────────────────────────────────────────────────────
# 2. ROBUST LOADERS (Handling 200MB & Encoding Error 0x8e)
# ─────────────────────────────────────────────────────────────────────────────
def load_file_safely(file):
    for enc in ['utf-8', 'latin1', 'cp1252', 'cp1256']:
        try:
            file.seek(0)
            df = pd.read_csv(file, encoding=enc, low_memory=True)
            df.columns = df.columns.str.strip()
            return df
        except: continue
    return None

def load_stores(file):
    df = load_file_safely(file)
    if df is not None:
        df["Store_Code"] = df["Store_Code"].astype(str).str.strip().str.split('.').str[0]
        return df
    return None

def load_orders(file):
    df = load_file_safely(file)
    if df is not None:
        df["Store_Code"] = df["Store_Code"].astype(str).str.strip().str.split('.').str[0]
        df["Fleg_PLT"] = pd.to_numeric(df["Fleg_PLT"], errors="coerce").fillna(0).astype(int)
        df["Sec_PLT"] = pd.to_numeric(df["Sec_PLT"], errors="coerce").fillna(0).astype(int)
        df["Total_PLT"] = df["Fleg_PLT"] + df["Sec_PLT"]
        return df
    return None

def load_tariffs(file):
    df = load_file_safely(file)
    if df is not None:
        df["City"] = df["City"].astype(str).str.strip().str.lower()
        df["Price"] = pd.to_numeric(df["Price"], errors="coerce").fillna(0)
        return df
    return None

# ─────────────────────────────────────────────────────────────────────────────
# 3. TARIFF & PRICING ENGINE
# ─────────────────────────────────────────────────────────────────────────────
def get_price(tariffs, city, truck, ptype):
    match = tariffs[(tariffs['City'] == city.lower()) & 
                    (tariffs['Truck'] == truck) & 
                    (tariffs['Type'].str.lower() == ptype.lower())]
    return match['Price'].iloc[0] if not match.empty else 0.0

# ─────────────────────────────────────────────────────────────────────────────
# 4. CORE PLANNING ENGINE (Bin-Packing)
# ─────────────────────────────────────────────────────────────────────────────
def best_truck_for_load(total_plt, max_truck, tariffs, city, fleg_plt, sec_plt):
    allowed_idx = TRUCK_PRIORITY.index(max_truck) if max_truck in TRUCK_PRIORITY else 0
    candidates = TRUCK_PRIORITY[allowed_idx:]
    best_type = candidates[-1]
    min_cpp = float('inf')

    for t in candidates:
        cap = TRUCK_CAPACITY[t]
        if total_plt <= round(cap * LOAD_MAX_PCT):
            cost = get_price(tariffs, city, t, "fleg") if fleg_plt > 0 else 0
            cost += get_price(tariffs, city, t, "sec") if sec_plt > 0 else 0
            cpp = cost / total_plt if total_plt > 0 else float('inf')
            if cpp < min_cpp:
                min_cpp = cpp
                best_type = t
    return best_type

def plan_loads(merged, tariffs):
    loads = []
    truck_counters = {t: 1 for t in TRUCK_PRIORITY}

    for (zone, city), group in merged.groupby(["Zone", "City"], sort=False):
        group = group.sort_values(by="Total_PLT", ascending=False)
        city_max = group["Max_Truck_Allowed"].iloc[0]
        cap = TRUCK_CAPACITY[city_max]
        
        current_bins = []
        for _, row in group.iterrows():
            so = StoreOrder(row["Store_Code"], row["Store_Name"], city, zone, city_max, row["Fleg_PLT"], row["Sec_PLT"])
            
            placed = False
            for bin_ in current_bins:
                if sum(s.total_plt for s in bin_) + so.total_plt <= round(cap * LOAD_MAX_PCT):
                    bin_.append(so)
                    placed = True
                    break
            if not placed:
                current_bins.append([so])
        
        for b in current_bins:
            b_total = sum(s.total_plt for s in b)
            b_fleg = sum(s.fleg_plt for s in b)
            b_sec = sum(s.sec_plt for s in b)
            t_type = best_truck_for_load(b_total, city_max, tariffs, city, b_fleg, b_sec)
            
            tl = TruckLoad(f"{t_type}-{truck_counters[t_type]:03d}", t_type, city, zone, TRUCK_CAPACITY[t_type])
            tl.stores = b
            tl.fleg_cost = get_price(tariffs, city, t_type, "fleg") if b_fleg > 0 else 0
            tl.sec_cost = get_price(tariffs, city, t_type, "sec") if b_sec > 0 else 0
            loads.append(tl)
            truck_counters[t_type] += 1
            
    return loads

# ─────────────────────────────────────────────────────────────────────────────
# 5. UI & VISUALIZATION (Plotly)
# ─────────────────────────────────────────────────────────────────────────────
def render_kpis(df):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🚛 Total Trucks", len(df))
    c2.metric("📦 Total Pallets", int(df["Loaded_PLT"].sum()))
    c3.metric("💰 Total Cost (MAD)", f"{df['Total_Cost_MAD'].sum():,.0f}")
    c4.metric("⚡ Avg Utilization", f"{df['Utilization_%'].mean():.1f}%")

def main():
    st.set_page_config(page_title="Skhirat Hub PRO", layout="wide")
    st.title("🚛 Skhirat Hub — Optimization Platform")

    with st.sidebar:
        st.header("⚙️ Data Sources")
        s_file = st.file_uploader("Stores Master", type="csv")
        o_file = st.file_uploader("Daily Orders", type="csv")
        t_file = st.file_uploader("Tariffs Table", type="csv")

    if s_file and o_file and t_file:
        stores = load_stores(s_file)
        orders = load_orders(o_file)
        tariffs = load_tariffs(t_file)

        if stores is not None and orders is not None:
            merged = orders.merge(stores, on="Store_Code", how="left")
            merged["Zone_Rank"] = merged["Zone"].map(ZONE_DISTANCE_RANK).fillna(0)
            merged = merged.sort_values("Zone_Rank", ascending=False)

            loads = plan_loads(merged, tariffs)
            
            # Create Result DF
            res_data = []
            for i, tl in enumerate(loads):
                res_data.append({
                    "Seq": i+1, "Truck_ID": tl.truck_id, "Type": tl.truck_type,
                    "Zone": tl.zone, "City": tl.city, "Loaded_PLT": tl.total_plt,
                    "Utilization_%": tl.utilization * 100, 
                    "Total_Cost_MAD": tl.fleg_cost + tl.sec_cost,
                    "Manifest": tl.manifest
                })
            res_df = pd.DataFrame(res_data)

            render_kpis(res_df)
            
            tab1, tab2 = st.tabs(["📋 Manifest", "📊 Analysis"])
            with tab1:
                st.dataframe(res_df, use_container_width=True)
                
                # Export to Excel
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    res_df.to_excel(writer, index=False)
                st.download_button("⬇️ Download Excel", output.getvalue(), "manifest.xlsx")
            
            with tab2:
                fig = px.bar(res_df, x="Truck_ID", y="Utilization_%", color="Type", title="Truck Utilization")
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Please upload all 3 CSV files to begin.")

if __name__ == "__main__":
    main()

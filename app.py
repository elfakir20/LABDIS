"""
=============================================================================
  SKHIRAT HUB — LOGISTICS OPTIMIZATION PLATFORM
  Distribution Hub: Skhirat, Morocco
  Engine: Pandas + Plotly + Streamlit
=============================================================================
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import io, warnings
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# 0. CONSTANTS & CONFIG
# ─────────────────────────────────────────────────────────────────────────────
TRUCK_CAPACITY: Dict[str, int] = {"32T": 33, "19T": 18, "7T": 12}
TRUCK_PRIORITY: List[str] = ["32T", "19T", "7T"]
LOAD_MIN_PCT: float = 0.96
LOAD_MAX_PCT: float = 1.04
PRIORITY_STORE: int = 200

ZONE_DISTANCE_RANK: Dict[str, int] = {
    "Souss-Massa": 10, "Marrakech-Safi": 9, "Draa-Tafilalet": 8,
    "Oriental": 7, "Tanger-Tetouan-Al Hoceima": 6, "Fs-Mekns": 5,
    "Beni Mellal-Khénifra": 4, "El Jadida": 3, "Casa-Settat": 2,
    "Rabat-Sal-Knitra": 1, "Unknown": 0,
}

# ─────────────────────────────────────────────────────────────────────────────
# 1. DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class StoreOrder:
    store_code: str
    store_name: str
    city: str
    zone: str
    max_truck: str
    loading_window: str
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
    def total_plt(self) -> int: return sum(s.total_plt for s in self.stores)
    @property
    def fleg_plt(self) -> int: return sum(s.fleg_plt for s in self.stores)
    @property
    def sec_plt(self) -> int: return sum(s.sec_plt for s in self.stores)
    @property
    def utilization(self) -> float: return self.total_plt / self.capacity if self.capacity else 0.0
    @property
    def total_cost(self) -> float: return self.fleg_cost + self.sec_cost
    @property
    def cost_per_pallet(self) -> float: return self.total_cost / self.total_plt if self.total_plt else 0.0
    @property
    def manifest(self) -> str: return " + ".join([f"{s.store_name} ({s.total_plt} PLT)" for s in self.stores])
    @property
    def zone_rank(self) -> int: return ZONE_DISTANCE_RANK.get(self.zone, 0)

# ─────────────────────────────────────────────────────────────────────────────
# 2. LOADERS & HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def load_stores(file) -> pd.DataFrame:
    df = pd.read_csv(file, encoding="latin1")
    df.columns = df.columns.str.strip()
    df["Store_Code"] = pd.to_numeric(df["Store_Code"], errors="coerce").fillna(0).astype(int).astype(str)
    return df

def load_orders(file) -> pd.DataFrame:
    df = pd.read_csv(file)
    df.columns = df.columns.str.strip()
    df["Store_Code"] = df["Store_Code"].astype(str).str.strip()
    df["Fleg_PLT"] = pd.to_numeric(df["Fleg_PLT"], errors="coerce").fillna(0).astype(int)
    df["Sec_PLT"] = pd.to_numeric(df["Sec_PLT"], errors="coerce").fillna(0).astype(int)
    df["Total_PLT"] = df["Fleg_PLT"] + df["Sec_PLT"]
    return df

def load_tariffs(file) -> pd.DataFrame:
    df = pd.read_csv(file)
    df.columns = df.columns.str.strip()
    df["Price"] = pd.to_numeric(df["Price"], errors="coerce").fillna(0)
    return df

def build_tariff_lookup(tariffs: pd.DataFrame) -> Dict:
    lookup = {}
    for _, row in tariffs.iterrows():
        key = (str(row["City"]).strip().lower(), str(row["Truck"]).strip(), str(row["Type"]).strip().lower())
        lookup[key] = row["Price"]
    return lookup

def get_price(lookup: Dict, city: str, truck: str, ptype: str) -> float:
    key = (city.strip().lower(), truck, ptype.lower())
    return lookup.get(key, 0.0)

def cost_for_truck(load: TruckLoad, lookup: Dict) -> Tuple[float, float]:
    f_c = get_price(lookup, load.city, load.truck_type, "fleg") if load.fleg_plt > 0 else 0.0
    s_c = get_price(lookup, load.city, load.truck_type, "sec") if load.sec_plt > 0 else 0.0
    return f_c, s_c

# ─────────────────────────────────────────────────────────────────────────────
# 3. OPTIMIZATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────
def best_truck_for_load(total_plt: int, max_truck: str, lookup: Dict, city: str, f_plt: int, s_plt: int) -> str:
    allowed_idx = TRUCK_PRIORITY.index(max_truck) if max_truck in TRUCK_PRIORITY else 0
    candidates = TRUCK_PRIORITY[allowed_idx:]
    best_type, best_cpp = candidates[-1], float("inf")

    for t in candidates:
        cap = TRUCK_CAPACITY[t]
        if total_plt > round(cap * LOAD_MAX_PCT): continue
        tc = get_price(lookup, city, t, "fleg") + get_price(lookup, city, t, "sec")
        cpp = tc / total_plt if total_plt > 0 else float("inf")
        if cpp < best_cpp: best_cpp, best_type = cpp, t
    return best_type

def plan_loads(merged: pd.DataFrame, lookup: Dict) -> List[TruckLoad]:
    loads: List[TruckLoad] = []
    truck_counter = {}

    def next_id(t_type: str):
        truck_counter[t_type] = truck_counter.get(t_type, 0) + 1
        return f"{t_type}-{truck_counter[t_type]:03d}"

    for (zone, city), grp in merged.groupby(["Zone", "City"], sort=False):
        city_max_truck = grp["Max_Truck_Allowed"].iloc[0]
        cap = TRUCK_CAPACITY.get(city_max_truck, 18)
        
        store_orders = []
        for _, row in grp.iterrows():
            so = StoreOrder(str(row["Store_Code"]), str(row["Store_Name"]), city, zone, 
                            city_max_truck, str(row.get("Loading_Window", "N/A")), 
                            int(row["Fleg_PLT"]), int(row["Sec_PLT"]), int(row["Total_PLT"]))
            store_orders.append(so)

        # Simple Bin Packing
        current_bins: List[List[StoreOrder]] = []
        for so in sorted(store_orders, key=lambda x: x.total_plt, reverse=True):
            placed = False
            for b in current_bins:
                if sum(s.total_plt for s in b) + so.total_plt <= round(cap * LOAD_MAX_PCT):
                    b.append(so)
                    placed = True
                    break
            if not placed: current_bins.append([so])

        for b in current_bins:
            b_tot, b_f, b_s = sum(s.total_plt for s in b), sum(s.fleg_plt for s in b), sum(s.sec_plt for s in b)
            t_type = best_truck_for_load(b_tot, city_max_truck, lookup, city, b_f, b_s)
            tl = TruckLoad(next_id(t_type), t_type, city, zone, TRUCK_CAPACITY[t_type], b)
            tl.fleg_cost, tl.sec_cost = cost_for_truck(tl, lookup)
            loads.append(tl)
    return loads

# ─────────────────────────────────────────────────────────────────────────────
# 4. VISUALS & UI HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def to_excel(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return buf.getvalue()

def apply_styles():
    st.markdown("""
    <style>
    [data-testid="stMetric"] { background: #1E2130; border: 1px solid #2D3250; border-radius: 10px; padding: 15px; }
    .hub-header { background: linear-gradient(135deg, #0057B8 0%, #00A3E0 100%); border-radius: 12px; padding: 20px; color: white; margin-bottom: 20px;}
    </style>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# 5. MAIN APP
# ─────────────────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(page_title="Skhirat Hub", layout="wide")
    apply_styles()
    
    st.markdown('<div class="hub-header"><h1>🚛 Skhirat Hub — Logistics Platform</h1></div>', unsafe_allow_html=True)

    with st.sidebar:
        st.header("⚙️ Data Upload")
        f_stores = st.file_uploader("Stores CSV", type="csv")
        f_orders = st.file_uploader("Orders CSV", type="csv")
        f_tariffs = st.file_uploader("Tariffs CSV", type="csv")
        
        st.divider()
        l_min = st.slider("Min Load %", 80, 100, 96)
        l_max = st.slider("Max Load %", 100, 120, 104)
        global LOAD_MIN_PCT, LOAD_MAX_PCT
        LOAD_MIN_PCT, LOAD_MAX_PCT = l_min/100, l_max/100

    if not (f_stores and f_orders and f_tariffs):
        st.info("الرجاء رفع ملفات المتاجر، الطلبات، والتعريفات للبدء.")
        return

    # Process
    stores, orders, tariffs = load_stores(f_stores), load_orders(f_orders), load_tariffs(f_tariffs)
    lookup = build_tariff_lookup(tariffs)
    merged = orders.merge(stores, on="Store_Code", how="left").fillna("Unknown")
    loads = plan_loads(merged, lookup)
    
    # Results DataFrame
    res_data = []
    for i, l in enumerate(loads):
        res_data.append({
            "Seq": i+1, "Truck_ID": l.truck_id, "Type": l.truck_type, "City": l.city, "Zone": l.zone,
            "PLT": l.total_plt, "Util_%": round(l.utilization*100, 1), "Cost_MAD": l.total_cost, "Manifest": l.manifest
        })
    df_res = pd.DataFrame(res_data)

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Trucks", len(df_res))
    c2.metric("Total Pallets", int(df_res["PLT"].sum()))
    c3.metric("Total Cost", f"{df_res['Cost_MAD'].sum():,.0f} MAD")
    c4.metric("Avg Util", f"{df_res['Util_%'].mean():.1f}%")

    # Tabs
    t1, t2, t3 = st.tabs(["📋 Manifest", "📊 Analytics", "📍 Map"])
    
    with t1:
        st.dataframe(df_res, use_container_width=True)
        st.download_button("⬇️ Download Excel", to_excel(df_res), "manifest.xlsx")

    with t2:
        fig = px.pie(df_res, names="Type", title="Fleet Mix", hole=.4)
        st.plotly_chart(fig)

    with t3:
        if 'lat' in merged.columns and 'lon' in merged.columns:
            st.map(merged[['lat', 'lon']])
        else:
            st.warning("الخريطة تتطلب أعمدة 'lat' و 'lon' في ملف المتاجر.")

if __name__ == "__main__":
    main()

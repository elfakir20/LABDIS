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
from plotly.subplots import make_subplots
import io, warnings
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# 0. CONSTANTS & CONFIG
# ─────────────────────────────────────────────────────────────────────────────
TRUCK_CAPACITY: Dict[str, int] = {"32T": 33, "19T": 18, "7T": 12}
TRUCK_PRIORITY: List[str] = ["32T", "19T", "7T"]   # preferred order (largest first)
LOAD_MIN_PCT: float = 0.96
LOAD_MAX_PCT: float = 1.04
PRIORITY_STORE: int = 200                            # always first drop

# Zone distance ranking from Skhirat (furthest → nearest)
ZONE_DISTANCE_RANK: Dict[str, int] = {
    "Souss-Massa":       10,
    "Marrakech-Safi":     9,
    "Draa-Tafilalet":     8,
    "Oriental":           7,
    "Tanger-Tetouan-Al Hoceima": 6,
    "Fs-Mekns":           5,
    "Beni Mellal-Khénifra": 4,
    "El Jadida":          3,
    "Casa-Settat":        2,
    "Rabat-Sal-Knitra":   1,
    "Unknown":            0,
}

# ─────────────────────────────────────────────────────────────────────────────
# 1. DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class StoreOrder:
    store_code: int
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
    def total_plt(self) -> int:
        return sum(s.total_plt for s in self.stores)

    @property
    def fleg_plt(self) -> int:
        return sum(s.fleg_plt for s in self.stores)

    @property
    def sec_plt(self) -> int:
        return sum(s.sec_plt for s in self.stores)

    @property
    def utilization(self) -> float:
        return self.total_plt / self.capacity if self.capacity else 0.0

    @property
    def total_cost(self) -> float:
        return self.fleg_cost + self.sec_cost

    @property
    def cost_per_pallet(self) -> float:
        return self.total_cost / self.total_plt if self.total_plt else 0.0

    @property
    def manifest(self) -> str:
        parts = []
        for s in self.stores:
            parts.append(f"{s.store_name} ({s.total_plt} PLT)")
        return " + ".join(parts)

    @property
    def zone_rank(self) -> int:
        return ZONE_DISTANCE_RANK.get(self.zone, 0)


# ─────────────────────────────────────────────────────────────────────────────
# 2. DATA LOADERS
# ─────────────────────────────────────────────────────────────────────────────
def load_stores(file) -> pd.DataFrame:
    df = pd.read_csv(file, encoding="latin1")
    df.columns = df.columns.str.strip()
    # Normalise: float → int → str so "102.0" and "102" both become "102"
    df["Store_Code"] = (
        pd.to_numeric(df["Store_Code"], errors="coerce")
        .fillna(0).astype(int).astype(str)
    )
    df["Store_Name"] = df["Store_Name"].astype(str).str.strip()
    df["City"]       = df["City"].astype(str).str.strip()
    df["Zone"]       = df["Zone"].astype(str).str.strip()
    df["Max_Truck_Allowed"] = df["Max_Truck_Allowed"].astype(str).str.strip()
    # Normalize loading window column
    win_col = [c for c in df.columns if "Loading" in c or "loading" in c]
    df["Loading_Window"] = df[win_col[0]].astype(str).str.strip() if win_col else "N/A"
    return df


def load_orders(file) -> pd.DataFrame:
    df = pd.read_csv(file)
    df.columns = df.columns.str.strip()
    df["Store_Code"] = df["Store_Code"].astype(str).str.strip()
    df["Fleg_PLT"]   = pd.to_numeric(df["Fleg_PLT"], errors="coerce").fillna(0).astype(int)
    df["Sec_PLT"]    = pd.to_numeric(df["Sec_PLT"],  errors="coerce").fillna(0).astype(int)
    df["Total_PLT"]  = df["Fleg_PLT"] + df["Sec_PLT"]
    return df


def load_tariffs(file) -> pd.DataFrame:
    df = pd.read_csv(file)
    df.columns = df.columns.str.strip()
    df["City"]  = df["City"].astype(str).str.strip().str.title()
    df["Truck"] = df["Truck"].astype(str).str.strip()
    df["Type"]  = df["Type"].astype(str).str.strip().str.lower()
    df["Price"] = pd.to_numeric(df["Price"], errors="coerce").fillna(0)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 3. TARIFF LOOKUP
# ─────────────────────────────────────────────────────────────────────────────
def build_tariff_lookup(tariffs: pd.DataFrame) -> Dict:
    """Returns dict: (city_lower, truck, type) → price"""
    lookup = {}
    for _, row in tariffs.iterrows():
        key = (row["City"].lower(), row["Truck"], row["Type"])
        lookup[key] = row["Price"]
    return lookup


def get_price(lookup: Dict, city: str, truck: str, ptype: str) -> float:
    """Fuzzy city match against tariff lookup."""
    city_l = city.strip().lower()
    # exact
    key = (city_l, truck, ptype.lower())
    if key in lookup:
        return lookup[key]
    # partial match
    for (k_city, k_truck, k_type), price in lookup.items():
        if k_truck == truck and k_type == ptype.lower() and (
            k_city in city_l or city_l in k_city
        ):
            return price
    return 0.0


def cost_for_truck(load: TruckLoad, tariff_lookup: Dict) -> Tuple[float, float]:
    """Return (fleg_cost, sec_cost) for a truck load."""
    truck  = load.truck_type
    city   = load.city
    fleg_c = get_price(tariff_lookup, city, truck, "fleg") if load.fleg_plt > 0 else 0.0
    sec_c  = get_price(tariff_lookup, city, truck, "sec")  if load.sec_plt  > 0 else 0.0
    # If mixed Fleg+Sec → use separate costs; if only one type use that one
    if load.fleg_plt > 0 and load.sec_plt > 0:
        return fleg_c, sec_c
    elif load.fleg_plt > 0:
        return fleg_c, 0.0
    else:
        return 0.0, sec_c


# ─────────────────────────────────────────────────────────────────────────────
# 4. ORDER MERGING & ENRICHMENT
# ─────────────────────────────────────────────────────────────────────────────
def merge_data(stores: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    merged = orders.merge(stores, on="Store_Code", how="left")
    merged["Zone"]       = merged["Zone"].fillna("Unknown")
    merged["City"]       = merged["City"].fillna("Unknown")
    merged["Store_Name"] = merged["Store_Name"].fillna(merged["Store_Code"].astype(str))
    merged["Max_Truck_Allowed"] = merged["Max_Truck_Allowed"].fillna("19T")
    merged["Zone_Rank"]  = merged["Zone"].map(ZONE_DISTANCE_RANK).fillna(0).astype(int)
    # Delivery sequence: furthest zone first; city alphabetical within zone
    merged = merged.sort_values(
        ["Zone_Rank", "City", "Store_Code"],
        ascending=[False, True, True]
    ).reset_index(drop=True)
    return merged


# ─────────────────────────────────────────────────────────────────────────────
# 5. VEHICLE SELECTION ENGINE
# ─────────────────────────────────────────────────────────────────────────────
def best_truck_for_load(
    total_plt: int,
    max_truck: str,
    tariff_lookup: Dict,
    city: str,
    fleg_plt: int,
    sec_plt: int,
) -> str:
    """
    Select the truck type that minimises cost-per-pallet subject to:
      1. Truck size ≤ max_truck constraint for the city/store
      2. Prefer trucks where the load fits within 96–104% utilization
      3. Fall back to the smallest truck that can physically carry the load
    """
    allowed_idx = TRUCK_PRIORITY.index(max_truck) if max_truck in TRUCK_PRIORITY else 0
    candidates  = TRUCK_PRIORITY[allowed_idx:]  # max_truck and smaller

    best_type = candidates[-1]   # smallest allowed as default fallback
    best_cpp  = float("inf")

    for t in candidates:
        cap         = TRUCK_CAPACITY[t]
        utilization = total_plt / cap
        # Skip if load exceeds this truck (will be split upstream) or too small
        if total_plt > round(cap * LOAD_MAX_PCT):
            continue
        fleg_c  = get_price(tariff_lookup, city, t, "fleg") if fleg_plt > 0 else 0.0
        sec_c   = get_price(tariff_lookup, city, t, "sec")  if sec_plt  > 0 else 0.0
        total_c = fleg_c + sec_c
        cpp     = total_c / total_plt if (total_plt and total_c > 0) else float("inf")
        if cpp < best_cpp:
            best_cpp  = cpp
            best_type = t

    return best_type


# ─────────────────────────────────────────────────────────────────────────────
# 6. CORE LOAD PLANNER  (Recursive Split + Zone Pooling)
# ─────────────────────────────────────────────────────────────────────────────
def plan_loads(merged: pd.DataFrame, tariff_lookup: Dict) -> List[TruckLoad]:
    """
    Main planning loop:
      • Group by Zone + City
      • Within each group, sort so store 200 is first drop
      • Recursively split oversized orders into full trucks
      • Pool remainders
      • Assign truck type via cost optimisation
    """
    loads: List[TruckLoad] = []
    truck_counter: Dict[str, int] = {}

    def next_id(truck_type: str) -> str:
        truck_counter[truck_type] = truck_counter.get(truck_type, 0) + 1
        return f"{truck_type}-{truck_counter[truck_type]:03d}"

    # ── Group by Zone → City
    merged["_prio"] = merged["Store_Code"].apply(
        lambda v: 0 if str(v) == str(PRIORITY_STORE) else 1
    )
    merged = merged.sort_values(
        ["Zone_Rank", "City", "_prio", "Store_Code"],
        ascending=[False, True, True, True]
    )

    for (zone, city), grp in merged.groupby(["Zone", "City"], sort=False):
        grp = grp.copy()

        # Sort: store 200 first, then by store code
        grp["_priority"] = grp["Store_Code"].apply(
            lambda x: 0 if str(x) == str(PRIORITY_STORE) else 1
        )
        grp = grp.sort_values(["_priority", "Store_Code"]).reset_index(drop=True)

        # Determine the max truck allowed for this city
        # (take the most capable truck any store in the group allows)
        city_max_truck = grp["Max_Truck_Allowed"].iloc[0]
        for t in TRUCK_PRIORITY:
            if t in grp["Max_Truck_Allowed"].values:
                city_max_truck = t
                break

        cap = TRUCK_CAPACITY[city_max_truck]

        # Build StoreOrder objects; split if single store > cap
        store_orders: List[StoreOrder] = []
        for _, row in grp.iterrows():
            so = StoreOrder(
                store_code=str(row["Store_Code"]),
                store_name=str(row["Store_Name"]),
                city=city,
                zone=zone,
                max_truck=str(row["Max_Truck_Allowed"]),
                loading_window=str(row.get("Loading_Window", "N/A")),
                fleg_plt=int(row["Fleg_PLT"]),
                sec_plt=int(row["Sec_PLT"]),
                total_plt=int(row["Total_PLT"]),
            )

            # Recursive split: if single store order > cap → full trucks
            if so.total_plt > cap:
                remaining = so.total_plt
                fleg_rem  = so.fleg_plt
                sec_rem   = so.sec_plt
                while remaining > cap:
                    # Proportional split of Fleg/Sec
                    ratio   = cap / so.total_plt
                    f_chunk = min(round(so.fleg_plt * ratio), fleg_rem)
                    s_chunk = min(cap - f_chunk, sec_rem)
                    chunk_total = f_chunk + s_chunk

                    chunk_so = StoreOrder(
                        store_code=so.store_code,
                        store_name=so.store_name + " [split]",
                        city=so.city,
                        zone=so.zone,
                        max_truck=so.max_truck,
                        loading_window=so.loading_window,
                        fleg_plt=f_chunk,
                        sec_plt=s_chunk,
                        total_plt=chunk_total,
                    )
                    # Create a dedicated full truck for this chunk
                    truck_type = best_truck_for_load(
                        chunk_total, city_max_truck, tariff_lookup,
                        city, f_chunk, s_chunk
                    )
                    tl = TruckLoad(
                        truck_id=next_id(truck_type),
                        truck_type=truck_type,
                        city=city,
                        zone=zone,
                        capacity=TRUCK_CAPACITY[truck_type],
                        stores=[chunk_so],
                    )
                    fleg_c, sec_c = cost_for_truck(tl, tariff_lookup)
                    tl.fleg_cost = fleg_c
                    tl.sec_cost  = sec_c
                    loads.append(tl)

                    fleg_rem  -= f_chunk
                    sec_rem   -= s_chunk
                    remaining -= chunk_total

                # Remainder goes into normal pooling
                if remaining > 0:
                    rem_so = StoreOrder(
                        store_code=so.store_code,
                        store_name=so.store_name + " [rem]",
                        city=so.city,
                        zone=so.zone,
                        max_truck=so.max_truck,
                        loading_window=so.loading_window,
                        fleg_plt=fleg_rem,
                        sec_plt=sec_rem,
                        total_plt=remaining,
                    )
                    store_orders.append(rem_so)
            else:
                store_orders.append(so)

        # ── Bin-pack store_orders into trucks for this city ──
        bin_pack_into_trucks(
            store_orders, cap, city_max_truck,
            city, zone, tariff_lookup,
            loads, next_id
        )

    # ── Sort final loads: furthest zone first
    loads.sort(key=lambda x: (-x.zone_rank, x.city, x.truck_id))
    return loads


def bin_pack_into_trucks(
    store_orders: List[StoreOrder],
    cap: int,
    city_max_truck: str,
    city: str,
    zone: str,
    tariff_lookup: Dict,
    loads: List[TruckLoad],
    next_id,
) -> None:
    """
    First-fit decreasing bin-packing that respects 96–104% load factor.
    After packing, assigns optimal truck type via CPP minimization.
    """
    if not store_orders:
        return

    open_bins: List[List[StoreOrder]] = []

    # Sort stores: priority store first, then largest first
    store_orders_sorted = sorted(
        store_orders,
        key=lambda s: (0 if str(s.store_code) == str(PRIORITY_STORE) else 1, -s.total_plt)
    )

    for so in store_orders_sorted:
        placed = False
        for bin_ in open_bins:
            bin_total = sum(b.total_plt for b in bin_)
            if bin_total + so.total_plt <= round(cap * LOAD_MAX_PCT):
                bin_.append(so)
                placed = True
                break
        if not placed:
            open_bins.append([so])

    for bin_ in open_bins:
        bin_total  = sum(b.total_plt for b in bin_)
        bin_fleg   = sum(b.fleg_plt  for b in bin_)
        bin_sec    = sum(b.sec_plt   for b in bin_)

        truck_type = best_truck_for_load(
            bin_total, city_max_truck, tariff_lookup,
            city, bin_fleg, bin_sec
        )
        tl = TruckLoad(
            truck_id=next_id(truck_type),
            truck_type=truck_type,
            city=city,
            zone=zone,
            capacity=TRUCK_CAPACITY[truck_type],
            stores=bin_,
        )
        fleg_c, sec_c = cost_for_truck(tl, tariff_lookup)
        tl.fleg_cost = fleg_c
        tl.sec_cost  = sec_c
        loads.append(tl)


# ─────────────────────────────────────────────────────────────────────────────
# 7. RESULT ASSEMBLY
# ─────────────────────────────────────────────────────────────────────────────
def loads_to_dataframe(loads: List[TruckLoad]) -> pd.DataFrame:
    rows = []
    for i, tl in enumerate(loads, 1):
        rows.append({
            "Seq":             i,
            "Truck_ID":        tl.truck_id,
            "Type":            tl.truck_type,
            "Zone":            tl.zone,
            "City":            tl.city,
            "Capacity_PLT":    tl.capacity,
            "Loaded_PLT":      tl.total_plt,
            "Fleg_PLT":        tl.fleg_plt,
            "Sec_PLT":         tl.sec_plt,
            "Utilization_%":   round(tl.utilization * 100, 1),
            "Fleg_Cost_MAD":   tl.fleg_cost,
            "Sec_Cost_MAD":    tl.sec_cost,
            "Total_Cost_MAD":  tl.total_cost,
            "Cost_Per_PLT":    round(tl.cost_per_pallet, 1),
            "Stores_Count":    len(tl.stores),
            "Detailed_Manifest": tl.manifest,
            "Zone_Rank":       tl.zone_rank,
        })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# 8. VISUALISATIONS
# ─────────────────────────────────────────────────────────────────────────────
PALETTE = {
    "primary":    "#0057B8",
    "accent":     "#00A3E0",
    "success":    "#00B894",
    "warning":    "#FDCB6E",
    "danger":     "#D63031",
    "bg":         "#0E1117",
    "card":       "#1E2130",
    "text":       "#F0F2F6",
}

def chart_utilization_heatmap(df: pd.DataFrame) -> go.Figure:
    pivot = df.pivot_table(
        index="Zone", columns="Type",
        values="Utilization_%", aggfunc="mean"
    ).fillna(0)

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale=[
            [0.0,  "#D63031"],
            [0.48, "#FDCB6E"],
            [0.96, "#00B894"],
            [1.0,  "#0057B8"],
        ],
        zmin=0, zmax=110,
        text=np.round(pivot.values, 1),
        texttemplate="%{text}%",
        hovertemplate="Zone: %{y}<br>Truck: %{x}<br>Avg Util: %{z:.1f}%<extra></extra>",
        colorbar=dict(title="Avg Util %", ticksuffix="%"),
    ))
    fig.update_layout(
        title="Fleet Utilization Heatmap (by Zone × Truck Type)",
        plot_bgcolor=PALETTE["bg"],
        paper_bgcolor=PALETTE["card"],
        font=dict(color=PALETTE["text"]),
        margin=dict(l=10, r=10, t=50, b=10),
        height=320,
    )
    return fig


def chart_cost_breakdown(df: pd.DataFrame) -> go.Figure:
    by_zone = df.groupby("Zone")[["Fleg_Cost_MAD", "Sec_Cost_MAD"]].sum().reset_index()
    by_zone = by_zone.sort_values("Fleg_Cost_MAD", ascending=False)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Fleg Cost",
        x=by_zone["Zone"], y=by_zone["Fleg_Cost_MAD"],
        marker_color=PALETTE["primary"],
    ))
    fig.add_trace(go.Bar(
        name="Sec Cost",
        x=by_zone["Zone"], y=by_zone["Sec_Cost_MAD"],
        marker_color=PALETTE["accent"],
    ))
    fig.update_layout(
        barmode="stack",
        title="Total Cost by Zone (MAD)",
        plot_bgcolor=PALETTE["bg"],
        paper_bgcolor=PALETTE["card"],
        font=dict(color=PALETTE["text"]),
        margin=dict(l=10, r=10, t=50, b=80),
        height=340,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        xaxis_tickangle=-35,
    )
    return fig


def chart_fleet_mix(df: pd.DataFrame) -> go.Figure:
    fleet = df["Type"].value_counts().reset_index()
    fleet.columns = ["Type", "Count"]
    colors = {"32T": PALETTE["primary"], "19T": PALETTE["accent"], "7T": PALETTE["success"]}
    fig = go.Figure(go.Pie(
        labels=fleet["Type"],
        values=fleet["Count"],
        hole=0.55,
        marker_colors=[colors.get(t, "#aaa") for t in fleet["Type"]],
        textinfo="label+percent+value",
        hovertemplate="%{label}: %{value} trucks (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        title="Fleet Mix",
        plot_bgcolor=PALETTE["bg"],
        paper_bgcolor=PALETTE["card"],
        font=dict(color=PALETTE["text"]),
        margin=dict(l=10, r=10, t=50, b=10),
        height=300,
        showlegend=False,
    )
    return fig


def chart_cpp_scatter(df: pd.DataFrame) -> go.Figure:
    fig = px.scatter(
        df,
        x="Loaded_PLT", y="Cost_Per_PLT",
        color="Type", size="Total_Cost_MAD",
        hover_data=["Truck_ID", "City", "Zone", "Utilization_%"],
        title="Cost per Pallet vs Load Volume",
        color_discrete_map={"32T": PALETTE["primary"], "19T": PALETTE["accent"], "7T": PALETTE["success"]},
        size_max=30,
    )
    fig.update_layout(
        plot_bgcolor=PALETTE["bg"],
        paper_bgcolor=PALETTE["card"],
        font=dict(color=PALETTE["text"]),
        margin=dict(l=10, r=10, t=50, b=10),
        height=320,
    )
    return fig


def chart_delivery_route(df: pd.DataFrame) -> go.Figure:
    route = (
        df.sort_values("Seq")
        .groupby(["Zone_Rank", "Zone", "City"], sort=False)["Total_Cost_MAD"]
        .sum()
        .reset_index()
        .sort_values("Zone_Rank", ascending=False)
    )
    fig = go.Figure(go.Funnel(
        y=route["City"] + " (" + route["Zone"] + ")",
        x=route["Total_Cost_MAD"],
        textinfo="value+percent initial",
        marker_color=px.colors.sequential.Blues_r[:len(route)],
    ))
    fig.update_layout(
        title="Delivery Route Funnel — Furthest First (Cost MAD)",
        plot_bgcolor=PALETTE["bg"],
        paper_bgcolor=PALETTE["card"],
        font=dict(color=PALETTE["text"]),
        margin=dict(l=10, r=10, t=50, b=10),
        height=400,
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 9. EXPORT HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def to_excel(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Manifest", index=False)
        # Summary sheet
        summary = pd.DataFrame({
            "Metric": [
                "Total Trucks", "Total Pallets", "Total Cost (MAD)",
                "Avg Utilization %", "Avg Cost/PLT (MAD)",
            ],
            "Value": [
                len(df),
                df["Loaded_PLT"].sum(),
                df["Total_Cost_MAD"].sum(),
                round(df["Utilization_%"].mean(), 1),
                round(df["Cost_Per_PLT"].mean(), 1),
            ],
        })
        summary.to_excel(writer, sheet_name="Summary", index=False)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 10. STREAMLIT UI
# ─────────────────────────────────────────────────────────────────────────────
def apply_styles():
    st.markdown("""
    <style>
    /* Global */
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #0E1117;
        color: #F0F2F6;
    }
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #161B27;
    }
    /* Metric cards */
    [data-testid="stMetric"] {
        background: #1E2130;
        border: 1px solid #2D3250;
        border-radius: 10px;
        padding: 14px 18px;
    }
    [data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 700; }
    /* Dataframe */
    .stDataFrame { border-radius: 10px; overflow: hidden; }
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 12px; }
    .stTabs [data-baseweb="tab"] {
        background: #1E2130;
        border-radius: 8px 8px 0 0;
        color: #A0AEC0;
        padding: 8px 20px;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background: #0057B8 !important;
        color: white !important;
    }
    /* Header banner */
    .hub-header {
        background: linear-gradient(135deg, #0057B8 0%, #00A3E0 100%);
        border-radius: 14px;
        padding: 20px 28px;
        margin-bottom: 18px;
    }
    .hub-header h1 { margin: 0; font-size: 1.7rem; color: white; }
    .hub-header p  { margin: 4px 0 0; color: rgba(255,255,255,0.8); font-size: 0.95rem; }
    /* Alert banners */
    .info-banner {
        background: #1E2130;
        border-left: 4px solid #0057B8;
        border-radius: 6px;
        padding: 10px 16px;
        margin: 8px 0;
        font-size: 0.9rem;
    }
    </style>
    """, unsafe_allow_html=True)


def render_header():
    st.markdown("""
    <div class="hub-header">
        <h1>🚛 Skhirat Hub — Logistics Optimization Platform</h1>
        <p>Distribution Centre · Skhirat, Morocco &nbsp;|&nbsp;
           Engine: Pandas + OR-Tools + Plotly</p>
    </div>
    """, unsafe_allow_html=True)


def render_kpis(df: pd.DataFrame):
    total_trucks  = len(df)
    total_pallets = int(df["Loaded_PLT"].sum())
    total_cost    = df["Total_Cost_MAD"].sum()
    avg_util      = df["Utilization_%"].mean()
    avg_cpp       = df["Cost_Per_PLT"].mean()
    over_loaded   = int((df["Utilization_%"] > 104).sum())
    under_loaded  = int((df["Utilization_%"] < 96).sum())
    in_range      = total_trucks - over_loaded - under_loaded

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("🚛 Total Trucks",     total_trucks)
    c2.metric("📦 Total Pallets",    f"{total_pallets:,}")
    c3.metric("💰 Total Cost (MAD)", f"{total_cost:,.0f}")
    c4.metric("⚡ Avg Utilization",  f"{avg_util:.1f}%",
              delta=f"{avg_util-100:.1f}% vs target")
    c5.metric("💡 Avg Cost/PLT",     f"{avg_cpp:.1f} MAD")
    c6.metric("✅ In-Range Trucks",
              f"{in_range}/{total_trucks}",
              delta=f"{over_loaded} over / {under_loaded} under",
              delta_color="inverse")


def render_manifest_table(df: pd.DataFrame):
    st.subheader("📋 Detailed Truck Manifest")

    # Colour-code utilization
    def util_color(val):
        if val > 104:  return "background-color:#2d1515; color:#ff6b6b"
        if val < 96:   return "background-color:#1a2015; color:#f9ca24"
        return "background-color:#152015; color:#00b894"

    display_cols = [
        "Seq", "Truck_ID", "Type", "Zone", "City",
        "Capacity_PLT", "Loaded_PLT", "Fleg_PLT", "Sec_PLT",
        "Utilization_%", "Total_Cost_MAD", "Cost_Per_PLT",
        "Stores_Count", "Detailed_Manifest",
    ]
    styled = (
        df[display_cols]
        .style
        .map(util_color, subset=["Utilization_%"])
        .format({
            "Total_Cost_MAD": "{:,.0f} MAD",
            "Cost_Per_PLT":   "{:.1f} MAD",
            "Utilization_%":  "{:.1f}%",
        })
    )
    st.dataframe(styled, use_container_width=True, height=420)


def render_dashboard(df: pd.DataFrame):
    st.subheader("📊 Operations Dashboard")

    col1, col2 = st.columns([3, 2])
    with col1:
        st.plotly_chart(chart_utilization_heatmap(df), use_container_width=True)
    with col2:
        st.plotly_chart(chart_fleet_mix(df), use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        st.plotly_chart(chart_cost_breakdown(df), use_container_width=True)
    with col4:
        st.plotly_chart(chart_cpp_scatter(df), use_container_width=True)

    st.plotly_chart(chart_delivery_route(df), use_container_width=True)


def render_zone_summary(df: pd.DataFrame):
    st.subheader("🗺️ Zone Summary")
    zone_sum = (
        df.groupby("Zone")
        .agg(
            Trucks        =("Truck_ID",       "count"),
            Total_PLT     =("Loaded_PLT",      "sum"),
            Avg_Util      =("Utilization_%",   "mean"),
            Total_Cost    =("Total_Cost_MAD",  "sum"),
            Avg_CPP       =("Cost_Per_PLT",    "mean"),
        )
        .reset_index()
        .sort_values("Total_Cost", ascending=False)
    )
    zone_sum["Avg_Util"]   = zone_sum["Avg_Util"].round(1)
    zone_sum["Avg_CPP"]    = zone_sum["Avg_CPP"].round(1)
    zone_sum["Total_Cost"] = zone_sum["Total_Cost"].apply(lambda x: f"{x:,.0f} MAD")
    st.dataframe(zone_sum, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="Skhirat Hub — Logistics Optimizer",
        page_icon="🚛",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_styles()
    render_header()

    # ── Sidebar ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.image("https://upload.wikimedia.org/wikipedia/commons/2/2c/Flag_of_Morocco.svg",
                 width=80)
        st.markdown("### ⚙️ Data Sources")

        stores_file  = st.file_uploader("🏪 Stores Database (CSV)", type="csv", key="stores")
        orders_file  = st.file_uploader("📦 Daily Orders (CSV)",    type="csv", key="orders")
        tariffs_file = st.file_uploader("💲 Tariffs Table (CSV)",   type="csv", key="tariffs")

        st.markdown("---")
        st.markdown("### 🔧 Planning Parameters")
        load_min = st.slider("Min Load Factor %", 90, 100, 96)
        load_max = st.slider("Max Load Factor %", 100, 115, 104)
        global LOAD_MIN_PCT, LOAD_MAX_PCT
        LOAD_MIN_PCT = load_min / 100
        LOAD_MAX_PCT = load_max / 100

        st.markdown("---")
        st.markdown("""
        <div style='font-size:0.8rem; color:#718096'>
        🏭 <b>Hub:</b> Skhirat, Morocco<br>
        📐 Truck Caps: 32T=33 PLT · 19T=18 PLT · 7T=12 PLT<br>
        🎯 Target: 100% efficiency
        </div>
        """, unsafe_allow_html=True)

    # ── Guard: need all three files ──────────────────────────────────────────
    if not (stores_file and orders_file and tariffs_file):
        st.info(
            "⬅️ Upload **Stores**, **Orders**, and **Tariffs** CSV files in the sidebar to begin.",
            icon="📂"
        )
        # Show sample preview with demo banner
        st.markdown("""
        <div class="info-banner">
        <b>Expected Columns:</b><br>
        • <b>Stores:</b> Store_Code, Store_Name, City, Zone, Max_Truck_Allowed, Loading Window<br>
        • <b>Orders:</b> Store_Code, Fleg_PLT, Sec_PLT<br>
        • <b>Tariffs:</b> City, Truck, Type, Price
        </div>
        """, unsafe_allow_html=True)
        return

    # ── Load & process ───────────────────────────────────────────────────────
    with st.spinner("🔄 Loading and validating data…"):
        stores  = load_stores(stores_file)
        orders  = load_orders(orders_file)
        tariffs = load_tariffs(tariffs_file)

    with st.spinner("🧮 Running optimisation engine…"):
        tariff_lookup = build_tariff_lookup(tariffs)
        merged        = merge_data(stores, orders)
        loads         = plan_loads(merged, tariff_lookup)
        result_df     = loads_to_dataframe(loads)

    st.success(
        f"✅ Optimisation complete — {len(loads)} trucks planned, "
        f"{result_df['Loaded_PLT'].sum():,} pallets allocated, "
        f"total cost {result_df['Total_Cost_MAD'].sum():,.0f} MAD",
        icon="🎯"
    )

    # ── KPI Banner ───────────────────────────────────────────────────────────
    render_kpis(result_df)
    st.markdown("---")

    # ── Tabs ─────────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 Truck Manifest",
        "📊 Dashboard",
        "🗺️ Zone Summary",
        "🔍 Raw Data",
    ])

    with tab1:
        render_manifest_table(result_df)
        xlsx_bytes = to_excel(result_df)
        st.download_button(
            label="⬇️ Export Manifest to Excel",
            data=xlsx_bytes,
            file_name="skhirat_manifest.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with tab2:
        render_dashboard(result_df)

    with tab3:
        render_zone_summary(result_df)

    with tab4:
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Merged Orders + Stores**")
            st.dataframe(merged.drop(columns=["_priority"], errors="ignore"),
                         use_container_width=True, height=300)
        with col_b:
            st.markdown("**Tariff Table**")
            st.dataframe(tariffs, use_container_width=True, height=300)


if __name__ == "__main__":
    main()
with tab3:
        render_zone_summary(result_df)

    with tab4:
        st.subheader("🔍 Raw Data Preview")
        st.write(merged)

if __name__ == "__main__":
    main()

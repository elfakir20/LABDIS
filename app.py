"""
=============================================================================
 SKHIRAT HUB — LOGISTICS OPTIMIZATION PLATFORM (OR-TOOLS VERSION)
=============================================================================
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

TRUCK_CAPACITY = {
    "32T": 33,
    "19T": 18,
    "7T": 12
}

PRIORITY_STORE = "200"

# ─────────────────────────────────────────────────────────────
# DATA LOADERS
# ─────────────────────────────────────────────────────────────

def load_stores(file):
    df = pd.read_csv(file)
    df.columns = df.columns.str.strip()
    df["Store_Code"] = df["Store_Code"].astype(str)
    return df


def load_orders(file):
    df = pd.read_csv(file)
    df.columns = df.columns.str.strip()
    df["Store_Code"] = df["Store_Code"].astype(str)
    df["Total_PLT"] = df["Fleg_PLT"] + df["Sec_PLT"]
    return df


def load_tariffs(file):
    df = pd.read_csv(file)
    df.columns = df.columns.str.strip()
    return df

# ─────────────────────────────────────────────────────────────
# OR-TOOLS ENGINE
# ─────────────────────────────────────────────────────────────

def create_data_model(df):
    data = {}

    # demand
    data["demands"] = df["Total_PLT"].tolist()

    n = len(df)

    # fake distance matrix (zone-based)
    matrix = np.zeros((n, n))

    for i in range(n):
        for j in range(n):
            if df.iloc[i]["Zone"] == df.iloc[j]["Zone"]:
                matrix[i][j] = 10
            else:
                matrix[i][j] = 50

    data["distance_matrix"] = matrix.tolist()

    # vehicles
    data["vehicle_capacities"] = [33] * 50
    data["num_vehicles"] = 50
    data["depot"] = 0

    return data


def solve_vrp(data):
    manager = pywrapcp.RoutingIndexManager(
        len(data["distance_matrix"]),
        data["num_vehicles"],
        data["depot"]
    )

    routing = pywrapcp.RoutingModel(manager)

    # Distance
    def distance_callback(from_index, to_index):
        return int(
            data["distance_matrix"]
            [manager.IndexToNode(from_index)]
            [manager.IndexToNode(to_index)]
        )

    transit_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_index)

    # Demand
    def demand_callback(from_index):
        return int(data["demands"][manager.IndexToNode(from_index)])

    demand_index = routing.RegisterUnaryTransitCallback(demand_callback)

    routing.AddDimensionWithVehicleCapacity(
        demand_index,
        0,
        data["vehicle_capacities"],
        True,
        "Capacity"
    )

    # solver params
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    params.time_limit.FromSeconds(5)

    solution = routing.SolveWithParameters(params)

    return solution, routing, manager


def extract_routes(df, solution, routing, manager):
    routes = []

    if not solution:
        return routes

    for v in range(routing.vehicles()):
        index = routing.Start(v)
        route = []
        load = 0

        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)

            if node < len(df):
                route.append(node)
                load += df.iloc[node]["Total_PLT"]

            index = solution.Value(routing.NextVar(index))

        if route:
            routes.append({
                "Truck": v,
                "Stops": len(route),
                "Load": load
            })

    return routes

# ─────────────────────────────────────────────────────────────
# STREAMLIT APP
# ─────────────────────────────────────────────────────────────

def main():

    st.set_page_config(page_title="Skhirat TMS OR-Tools", layout="wide")

    st.title("🚛 Skhirat Hub — OR-Tools Optimization Engine")

    # Upload
    st.sidebar.header("📂 Upload Data")

    stores_file = st.sidebar.file_uploader("Stores CSV")
    orders_file = st.sidebar.file_uploader("Orders CSV")
    tariffs_file = st.sidebar.file_uploader("Tariffs CSV")

    if not (stores_file and orders_file and tariffs_file):
        st.warning("Please upload all files")
        return

    # Load
    stores = load_stores(stores_file)
    orders = load_orders(orders_file)
    tariffs = load_tariffs(tariffs_file)

    # Merge
    merged = orders.merge(stores, on="Store_Code", how="left")

    # Priority (Store 200 first)
    merged = pd.concat([
        merged[merged["Store_Code"] == PRIORITY_STORE],
        merged[merged["Store_Code"] != PRIORITY_STORE]
    ])

    st.subheader("📦 Raw Data")
    st.dataframe(merged)

    # OR-TOOLS
    st.subheader("⚙️ Optimization Running...")

    data_model = create_data_model(merged)
    solution, routing, manager = solve_vrp(data_model)

    routes = extract_routes(merged, solution, routing, manager)

    df_routes = pd.DataFrame(routes)

    # KPIs
    col1, col2, col3 = st.columns(3)

    col1.metric("🚛 Trucks Used", len(df_routes))
    col2.metric("📦 Total Load", int(df_routes["Load"].sum()) if not df_routes.empty else 0)
    col3.metric("📍 Avg Stops", round(df_routes["Stops"].mean(), 2) if not df_routes.empty else 0)

    # Table
    st.subheader("📋 Optimized Routes")
    st.dataframe(df_routes)

    # Chart
    if not df_routes.empty:
        fig = px.bar(df_routes, x="Truck", y="Load", title="Truck Load Distribution")
        st.plotly_chart(fig)

    st.success("✅ Optimization Complete (OR-Tools Active)")

# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()

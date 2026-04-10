import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

# ================= CONFIG =================

TRUCK_CAPACITY = {"32T": 33, "19T": 18, "7T": 12}
PRIORITY_STORE = "200"

# ================= LOADERS =================

def load_stores(file):
    df = pd.read_csv(file)
    df.columns = df.columns.str.strip()
    df["Store_Code"] = df["Store_Code"].astype(str)
    return df

def load_orders(file):
    df = pd.read_csv(file)
    df.columns = df.columns.str.strip()
    df["Store_Code"] = df["Store_Code"].astype(str)
    df["Fleg_PLT"] = df["Fleg_PLT"].fillna(0).astype(int)
    df["Sec_PLT"] = df["Sec_PLT"].fillna(0).astype(int)
    df["Total_PLT"] = df["Fleg_PLT"] + df["Sec_PLT"]
    return df

def load_tariffs(file):
    df = pd.read_csv(file)
    df.columns = df.columns.str.strip()
    return df

# ================= OR-TOOLS CORE =================

def create_data_model(df):

    df = df.reset_index(drop=True)

    data = {}

    # DEMAND
    data["demands"] = df["Total_PLT"].tolist()

    n = len(df)

    # SAFE CHECK
    if n == 0:
        return None

    # Distance matrix (zone heuristic)
    matrix = np.zeros((n, n))

    for i in range(n):
        for j in range(n):
            matrix[i][j] = 10 if df.iloc[i]["Zone"] == df.iloc[j]["Zone"] else 50

    data["distance_matrix"] = matrix.tolist()

    # 🚛 FIX: realistic fleet size
    data["num_vehicles"] = min(10, n)
    data["vehicle_capacities"] = [33] * data["num_vehicles"]

    data["depot"] = 0

    return data


def solve_vrp(data):

    if data is None:
        return None, None, None

    manager = pywrapcp.RoutingIndexManager(
        len(data["distance_matrix"]),
        data["num_vehicles"],
        data["depot"]
    )

    routing = pywrapcp.RoutingModel(manager)

    # COST
    def distance_callback(from_index, to_index):
        return int(
            data["distance_matrix"]
            [manager.IndexToNode(from_index)]
            [manager.IndexToNode(to_index)]
        )

    transit_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_index)

    # DEMAND
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

    # SOLVER
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromSeconds(3)

    solution = routing.SolveWithParameters(params)

    return solution, routing, manager


def extract_routes(df, solution, routing, manager):

    if solution is None:
        return []

    routes = []

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

# ================= STREAMLIT =================

def main():

    st.set_page_config(page_title="Skhirat TMS PRO", layout="wide")

    st.title("🚛 Skhirat Hub — PRO OR-Tools Engine")

    # Upload
    st.sidebar.header("📂 Data")

    stores_file = st.sidebar.file_uploader("Stores")
    orders_file = st.sidebar.file_uploader("Orders")
    tariffs_file = st.sidebar.file_uploader("Tariffs")

    if not (stores_file and orders_file and tariffs_file):
        st.warning("Upload all files")
        return

    # LOAD
    stores = load_stores(stores_file)
    orders = load_orders(orders_file)

    merged = orders.merge(stores, on="Store_Code", how="left")

    # PRIORITY STORE
    merged = pd.concat([
        merged[merged["Store_Code"] == PRIORITY_STORE],
        merged[merged["Store_Code"] != PRIORITY_STORE]
    ])

    st.subheader("📦 Data Preview")
    st.dataframe(merged)

    # SAFETY CHECK
    if len(merged) == 0:
        st.error("No data after merge")
        return

    # OPTIMIZATION
    st.subheader("⚙️ Running OR-Tools Optimization...")

    try:
        data_model = create_data_model(merged)
        solution, routing, manager = solve_vrp(data_model)

        if solution is None:
            st.error("❌ No feasible solution found")
            return

        routes = extract_routes(merged, solution, routing, manager)

    except Exception as e:
        st.error(f"Optimization error: {e}")
        return

    df_routes = pd.DataFrame(routes)

    # KPIs
    c1, c2, c3 = st.columns(3)

    c1.metric("🚛 Trucks", len(df_routes))
    c2.metric("📦 Load", int(df_routes["Load"].sum()) if not df_routes.empty else 0)
    c3.metric("📍 Avg Stops", round(df_routes["Stops"].mean(), 2) if not df_routes.empty else 0)

    # TABLE
    st.subheader("📋 Routes")
    st.dataframe(df_routes)

    # CHART
    if not df_routes.empty:
        fig = px.bar(df_routes, x="Truck", y="Load", title="Truck Utilization")
        st.plotly_chart(fig)

    st.success("✅ Production OR-Tools Optimization Complete")

# ================= RUN =================

if __name__ == "__main__":
    main()

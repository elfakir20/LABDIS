import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
import io

# ================= CONFIGURATION =================

TRUCK_CAPACITY_32T = 33
PRIORITY_STORE_CODE = "200"

# ================= DATA LOADERS =================

def load_data(stores_file, orders_file):
    try:
        df_s = pd.read_csv(stores_file).applymap(lambda x: x.strip() if isinstance(x, str) else x)
        df_o = pd.read_csv(orders_file).applymap(lambda x: x.strip() if isinstance(x, str) else x)
        
        df_s["Store_Code"] = df_s["Store_Code"].astype(str)
        df_o["Store_Code"] = df_o["Store_Code"].astype(str)
        
        merged = df_o.merge(df_s, on="Store_Code", how="left")
        merged["Total_PLT"] = pd.to_numeric(merged["Fleg_PLT"], errors='coerce').fillna(0) + \
                              pd.to_numeric(merged["Sec_PLT"], errors='coerce').fillna(0)
        return merged
    except Exception as e:
        st.error(f"Error loading CSV files: {e}")
        return None

# ================= OR-TOOLS CORE =================

def solve_logistics_vrp(df):
    # 1. Prepare Data Model
    # We add a dummy Depot at index 0
    demands = [0] + df["Total_PLT"].tolist()
    num_locations = len(demands)
    num_vehicles = max(5, len(df) // 2) # Adaptive fleet size
    vehicle_capacities = [TRUCK_CAPACITY_32T] * num_vehicles
    
    # 2. Distance Matrix (Heuristic based on Zones)
    # 0 is Depot. 1..N are stores.
    dist_matrix = np.zeros((num_locations, num_locations))
    for i in range(num_locations):
        for j in range(num_locations):
            if i == 0 or j == 0:
                dist_matrix[i][j] = 20 # Distance from Depot
            else:
                # Same zone = low cost, different zone = high cost
                z1 = df.iloc[i-1]["Zone"]
                z2 = df.iloc[j-1]["Zone"]
                dist_matrix[i][j] = 5 if z1 == z2 else 40

    # 3. Initialize OR-Tools
    manager = pywrapcp.RoutingIndexManager(num_locations, num_vehicles, 0)
    routing = pywrapcp.RoutingModel(manager)

    # Cost Function
    def distance_callback(from_idx, to_idx):
        return int(dist_matrix[manager.IndexToNode(from_idx)][manager.IndexToNode(to_idx)])

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Demand Function
    def demand_callback(from_idx):
        return int(demands[manager.IndexToNode(from_idx)])

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index, 0, vehicle_capacities, True, "Capacity"
    )

    # 4. Search Parameters
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.FromSeconds(2)

    # 5. Solve
    solution = routing.SolveWithParameters(search_parameters)
    return solution, routing, manager

# ================= UI & EXECUTION =================

def main():
    st.set_page_config(page_title="Skhirat Hub PRO", layout="wide")
    st.title("🚛 Skhirat Hub — Advanced OR-Tools Engine")
    st.markdown("---")

    # Sidebar
    st.sidebar.header("📁 Upload Center")
    s_file = st.sidebar.file_uploader("Stores Database", type="csv")
    o_file = st.sidebar.file_uploader("Daily Orders", type="csv")
    
    if s_file and o_file:
        df = load_data(s_file, o_file)
        
        if df is not None:
            # Sort by Priority Store if exists
            priority_mask = df["Store_Code"] == PRIORITY_STORE_CODE
            df = pd.concat([df[priority_mask], df[~priority_mask]]).reset_index(drop=True)

            st.subheader("📦 Merged Shipment Data")
            st.dataframe(df.head(10), use_container_width=True)

            if st.button("🚀 Run OR-Tools Optimization"):
                with st.spinner("Calculating optimal routes..."):
                    sol, rot, mgr = solve_logistics_vrp(df)
                    
                    if sol:
                        output_routes = []
                        for v in range(rot.vehicles()):
                            idx = rot.Start(v)
                            route_nodes = []
                            route_load = 0
                            while not rot.IsEnd(idx):
                                node = mgr.IndexToNode(idx)
                                if node != 0: # Skip Depot
                                    store = df.iloc[node-1]
                                    route_nodes.append(f"{store['Store_Name']} ({store['Total_PLT']} PLT)")
                                    route_load += demands = store['Total_PLT']
                                idx = sol.Value(rot.NextVar(idx))
                            
                            if route_nodes:
                                output_routes.append({
                                    "Truck_ID": f"T-{v+1:02d}",
                                    "Stops_Count": len(route_nodes),
                                    "Total_Load": route_load,
                                    "Utilization": f"{(route_load

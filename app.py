import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
import io

# ================= CONFIGURATION =================
TRUCK_CAPACITY_LIMIT = 33
DEFAULT_DEPOT_INDEX = 0

# ================= HELPER FUNCTIONS =================
def load_and_merge(s_file, o_file):
    try:
        df_s = pd.read_csv(s_file)
        df_o = pd.read_csv(o_file)
        
        # Clean column names and types
        df_s.columns = df_s.columns.str.strip()
        df_o.columns = df_o.columns.str.strip()
        df_s["Store_Code"] = df_s["Store_Code"].astype(str).str.strip()
        df_o["Store_Code"] = df_o["Store_Code"].astype(str).str.strip()
        
        merged = df_o.merge(df_s, on="Store_Code", how="left")
        merged["Total_PLT"] = pd.to_numeric(merged["Fleg_PLT"], errors='coerce').fillna(0) + \
                              pd.to_numeric(merged["Sec_PLT"], errors='coerce').fillna(0)
        return merged.fillna("Unknown")
    except Exception as e:
        st.error(f"Data Loading Error: {e}")
        return None

# ================= OR-TOOLS ENGINE =================
def solve_routing(df):
    # Demands: 0 for Depot, then store pallets
    demands = [0] + df["Total_PLT"].tolist()
    num_locations = len(demands)
    num_vehicles = max(10, len(df) // 2 + 2)  # Dynamic fleet size
    capacities = [TRUCK_CAPACITY_LIMIT] * num_vehicles

    # Distance Matrix (Heuristic based on Zones)
    # i, j = 0 is Skhirat Depot
    dist_matrix = np.zeros((num_locations, num_locations))
    for i in range(num_locations):
        for j in range(num_locations):
            if i == j: dist_matrix[i][j] = 0
            elif i == 0 or j == 0: dist_matrix[i][j] = 30 # Base distance to Depot
            else:
                # Stores in same zone are "closer"
                z1 = df.iloc[i-1]["Zone"]
                z2 = df.iloc[j-1]["Zone"]
                dist_matrix[i][j] = 5 if z1 == z2 else 50

    # Initialize Manager and Model
    manager = pywrapcp.RoutingIndexManager(num_locations, num_vehicles, DEFAULT_DEPOT_INDEX)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_idx, to_idx):
        return int(dist_matrix[manager.IndexToNode(from_idx)][manager.IndexToNode(to_idx)])

    transit_idx = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    def demand_callback(from_idx):
        return int(demands[manager.IndexToNode(from_idx)])

    demand_idx = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(demand_idx, 0, capacities, True, "Capacity")

    # Parameters
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.time_limit.FromSeconds(3)

    return routing.SolveWithParameters(params), routing, manager, demands

# ================= STREAMLIT UI =================
def main():
    st.set_page_config(page_title="Skhirat PRO TMS", layout="wide")
    st.title("🚛 Skhirat Hub — Optimization Engine (OR-Tools)")
    st.info("Status: Operational | Engine: Google OR-Tools")

    st.sidebar.header("Upload Files")
    s_file = st.sidebar.file_uploader("1. Stores Database", type="csv")
    o_file = st.sidebar.file_uploader("2. Daily Orders", type="csv")

    if s_file and o_file:
        df = load_and_merge(s_file, o_file)
        if df is not None:
            st.success(f"Loaded {len(df)} orders successfully.")
            
            if st.button("🚀 Optimize Delivery Plan"):
                solution, routing, manager, demands = solve_routing(df)
                
                if solution:
                    results = []
                    for vehicle_id in range(routing.vehicles()):
                        index = routing.Start(vehicle_id)
                        plan_output = []
                        route_load = 0
                        while not routing.IsEnd(index):
                            node_index = manager.IndexToNode(index)
                            if node_index != 0:
                                store_data = df.iloc[node_index-1]
                                plan_output.append(f"{store_data['Store_Name']}")
                                route_load += demands[node_index]
                            index = solution.Value(routing.NextVar(index))
                        
                        if plan_output:
                            results.append({
                                "Truck": f"Truck {vehicle_id + 1}",
                                "Stops": len(plan_output),
                                "Load (PLT)": route_load,
                                "Utilization": f"{(route_load/33)*100:.1f}%",
                                "Route Sequence": " ➔ ".join(plan_output)
                            })
                    
                    res_df = pd.DataFrame(results)
                    
                    # Dashboard
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Total Trucks Used", len(res_df))
                    m2.metric("Total Pallets", int(res_df["Load (PLT)"].sum()))
                    m3.metric("Avg Load/Truck", f"{res_df['Load (PLT)'].mean():.1f}")

                    st.subheader("📋 Optimized Load Manifest")
                    st.dataframe(res_df, use_container_width=True)
                    
                    # Chart
                    fig = px.bar(res_df, x="Truck", y="Load (PLT)", title="Capacity Check (Max 33)")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.error("No solution found. Try increasing vehicle capacity or count.")
    else:
        st.warning("Please upload both CSV files to start.")

if __name__ == "__main__":
    main()

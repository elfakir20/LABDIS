import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
import io

# ================= 1. CONFIGURATION =================
# Standard pallet capacity for a 32T truck
MAX_PALLETS = 33 

# ================= 2. CORE FUNCTIONS =================

def load_data(s_file, o_file):
    """Loads and cleans the store and order data."""
    try:
        df_s = pd.read_csv(s_file).applymap(lambda x: x.strip() if isinstance(x, str) else x)
        df_o = pd.read_csv(o_file).applymap(lambda x: x.strip() if isinstance(x, str) else x)
        
        # Ensure Store_Code is string for matching
        df_s["Store_Code"] = df_s["Store_Code"].astype(str)
        df_o["Store_Code"] = df_o["Store_Code"].astype(str)
        
        merged = df_o.merge(df_s, on="Store_Code", how="left")
        
        # Calculate Total Pallets
        merged["Total_PLT"] = pd.to_numeric(merged["Fleg_PLT"], errors='coerce').fillna(0) + \
                              pd.to_numeric(merged["Sec_PLT"], errors='coerce').fillna(0)
        
        return merged.dropna(subset=["Store_Name", "Zone"])
    except Exception as e:
        st.error(f"Data processing error: {e}")
        return None

def solve_vrp(df):
    """OR-Tools VRP Solver logic."""
    # Data preprocessing for OR-Tools
    demands = [0] + df["Total_PLT"].tolist() # 0 is for Depot (Skhirat)
    num_locations = len(demands)
    num_vehicles = max(15, len(df)) # High fleet limit to ensure feasibility
    vehicle_capacities = [MAX_PALLETS] * num_vehicles
    
    # Distance Matrix Heuristic (Zone-based)
    dist_matrix = np.zeros((num_locations, num_locations))
    for i in range(num_locations):
        for j in range(num_locations):
            if i == 0 or j == 0:
                dist_matrix[i][j] = 25 # Average distance to Depot
            else:
                z1, z2 = df.iloc[i-1]["Zone"], df.iloc[j-1]["Zone"]
                dist_matrix[i][j] = 5 if z1 == z2 else 45 # Penalty for changing zones

    # Initialize Routing Model
    manager = pywrapcp.RoutingIndexManager(num_locations, num_vehicles, 0)
    routing = pywrapcp.RoutingModel(manager)

    # Arc Cost
    def distance_callback(from_idx, to_idx):
        return int(dist_matrix[manager.IndexToNode(from_idx)][manager.IndexToNode(to_idx)])
    
    transit_idx = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    # Capacity Constraints
    def demand_callback(from_idx):
        return int(demands[manager.IndexToNode(from_idx)])
    
    demand_idx = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(demand_idx, 0, vehicle_capacities, True, "Capacity")

    # Parameters
    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_params.time_limit.FromSeconds(2) # Fast limit for UI responsiveness

    solution = routing.SolveWithParameters(search_params)
    return solution, routing, manager

# ================= 3. STREAMLIT UI =================

def main():
    st.set_page_config(page_title="Skhirat TMS PRO", layout="wide")
    
    st.title("🚛 Skhirat Hub — Optimization Engine")
    st.markdown("---")

    with st.sidebar:
        st.header("📂 Data Import")
        s_file = st.file_uploader("Stores Master (CSV)", type="csv")
        o_file = st.file_uploader("Daily Orders (CSV)", type="csv")
        
    if s_file and o_file:
        df = load_data(s_file, o_file)
        
        if df is not None and not df.empty:
            st.success(f"Linked {len(df)} orders to store database.")
            
            if st.button("🚀 Calculate Optimized Routes"):
                with st.spinner("Analyzing constraints..."):
                    sol, rot, mgr = solve_vrp(df)
                    
                    if sol:
                        route_data = []
                        for v in range(rot.vehicles()):
                            idx = rot.Start(v)
                            manifest = []
                            load = 0
                            while not rot.IsEnd(idx):
                                node = mgr.IndexToNode(idx)
                                if node != 0:
                                    row = df.iloc[node-1]
                                    manifest.append(f"{row['Store_Name']} ({int(row['Total_PLT'])}P)")
                                    load += row['Total_PLT']
                                idx = sol.Value(rot.NextVar(idx))
                            
                            if manifest:
                                route_data.append({
                                    "Truck": f"Truck {v+1}",
                                    "Stops": len(manifest),
                                    "Load": int(load),
                                    "Utilization (%)": round((load/MAX_PALLETS)*100, 1),
                                    "Manifest": " ➔ ".join(manifest)
                                })
                        
                        # Output
                        res_df = pd.DataFrame(route_data)
                        
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Total Fleet", len(res_df))
                        col2.metric("Total Load (PLT)", int(res_df["Load"].sum()))
                        col3.metric("Avg Utilization", f"{res_df['Utilization (%)'].mean():.1f}%")
                        
                        st.subheader("📋 Optimized Dispatch Plan")
                        st.dataframe(res_df, use_container_width=True)
                        
                        fig = px.bar(res_df, x="Truck", y="Load", color="Utilization (%)",
                                     title="Truck Load Comparison (Max 33 PLT)")
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.error("No feasible solution. Check if a single store order exceeds 33 PLT.")
    else:
        st.info("Upload CSV files to begin optimization.")

if __name__ == "__main__":
    main()

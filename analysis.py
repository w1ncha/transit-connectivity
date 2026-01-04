import pandas as pd
import geopandas as gpd
import networkx as nx
import pickle
import numpy as np
import sys
from shapely.geometry import Point
from sklearn.neighbors import BallTree

# ==========================================
# 1. SETUP & DATA LOADING
# ==========================================
print("Initializing Analysis Engine...")

try:
    # Load Stops (We need Lat/Lon to find nearest neighbors)
    with open('data/stops.pkl', 'rb') as f:
        STOPS_DICT = pickle.load(f)
        
    # Convert Dict to DataFrame for Scikit-Learn
    # Expects format: {'stop_id': {'lat': x, 'lon': y, 'name': z}}
    stops_df = pd.DataFrame.from_dict(STOPS_DICT, orient='index')
    stops_df.index.name = 'stop_id'
    stops_df = stops_df.reset_index()

    # Build BallTree for Fast Spatial Search (Run Once)
    # Convert Lat/Lon to Radians for Haversine metric
    stops_rad = np.deg2rad(stops_df[['stop_lat', 'stop_lon']])
    TREE = BallTree(stops_rad, metric='haversine')
    
    print("Spatial Index built successfully.")

except Exception as e:
    print(f"Error loading data: {e}")
    sys.exit(1)


# ==========================================
# 2. CORE FUNCTIONS
# ==========================================

def get_isochrone(G, start_lat, start_lon, time_budget_mins=30, walk_speed_kph=4.8, max_walk_km=1.0):
    """
    Calculates the reachable area (Isochrone) from a specific point.
    
    1. Snaps User to Graph (Virtual Node).
    2. Runs Dijkstra.
    3. Buffers and Unions results into a Polygon.
    """
    
    # --- STEP 1: SNAP TO NETWORK (The "First Mile") ---
    
    # Convert user input to radians
    user_rad = np.deg2rad([[start_lat, start_lon]])
    
    # Query Tree: Find stops within max_walk_km
    # Earth Radius ~ 6371 km
    radius_rad = max_walk_km / 6371.0
    
    # query_radius returns indices of the stops
    indices, distances = TREE.query_radius(user_rad, r=radius_rad, return_distance=True)
    
    nearby_indices = indices[0]
    nearby_distances_rad = distances[0]
    
    if len(nearby_indices) == 0:
        print("Warning: No stops found within walking distance.")
        return None

    # --- STEP 2: MODIFY GRAPH (Virtual Node) ---
    
    user_node = "USER_START"
    edges_to_remove = []
    
    # Calculate walk speed in meters/minute
    # 4.8 km/h = 4800 m / 60 min = 80 m/min
    walk_speed_mpm = (walk_speed_kph * 1000) / 60.0
    
    # Add temporary edges from USER to nearby stops
    for idx, dist_rad in zip(nearby_indices, nearby_distances_rad):
        stop_id = stops_df.iloc[idx]['stop_id']
        
        # Convert distance to meters
        dist_meters = dist_rad * 6371000
        
        # Calculate walk time
        walk_time_min = dist_meters / walk_speed_mpm
        
        # Only add if walk time fits in budget
        if walk_time_min < time_budget_mins:
            # Add Edge to Graph
            # We don't worry about duplicates because we remove 'user_node' later
            G.add_edge(user_node, stop_id, weight=walk_time_min)
            edges_to_remove.append((user_node, stop_id))

    # --- STEP 3: RUN DIJKSTRA (The "Recursive" Solver) ---
    
    # Finds the shortest path to ALL nodes reachable within cutoff
    # Returns: {Node_ID: Minutes_Taken}
    reachable_nodes = nx.single_source_dijkstra_path_length(
        G, 
        source=user_node, 
        cutoff=time_budget_mins, 
        weight='weight'
    )
    
    # Cleanup: Remove the user node to keep the graph clean for next request
    G.remove_node(user_node)
    
    if len(reachable_nodes) <= 1:
        return None # Only reached the user node itself
        
    
    # --- STEP 4: CREATE GEOMETRY (The Blob) ---
    
    # Filter stops_df to only include reached stops
    # We strip out the "Route Nodes" (e.g., "StopA_Route99") if using expanded graph,
    # and just keep the Street Nodes ("StopA").
    
    results = []
    for node, time_taken in reachable_nodes.items():
        # If using expanded graph, node might be "1234_99B". 
        # We only want to map the base stop "1234".
        base_stop_id = node.split('_')[0] 
        
        # Check if this ID exists in our stops database
        if base_stop_id in STOPS_DICT:
            # How much time is left to walk from this stop?
            remaining_time = time_budget_mins - time_taken
            
            # Walk Radius = Remaining Time * Speed
            radius_meters = remaining_time * walk_speed_mpm
            
            # Save data
            info = STOPS_DICT[base_stop_id]
            results.append({
                'geometry': Point(info['stop_lon'], info['stop_lat']),
                'radius': radius_meters
            })

    if not results:
        return None

    # Convert to GeoDataFrame
    gdf = gpd.GeoDataFrame(results, crs="EPSG:4326")
    
    # PROJECT TO METERS (Critical for Buffering)
    # EPSG:3005 is BC Albers (Standard for Vancouver)
    gdf_metric = gdf.to_crs("EPSG:3005")
    
    # Buffer
    # We draw a circle around every reached stop based on remaining walk time
    gdf_metric['geometry'] = gdf_metric.geometry.buffer(gdf_metric['radius'])
    
    # Union (Merge all circles into one blob)
    blob_metric = gdf_metric.unary_union
    
    # Project back to Lat/Lon for Leaflet/QGIS
    blob_latlon = gpd.GeoSeries([blob_metric], crs="EPSG:3005").to_crs("EPSG:4326")
    
    return blob_latlon[0] # Return the Shapely Polygon


# ==========================================
# 3. TEST SCRIPT (QGIS EXPORT)
# ==========================================
if __name__ == "__main__":
    import graph_builder
    import json
    
    # 1. User Inputs
    TEST_LAT = 49.26259  # Near Commercial-Broadway
    TEST_LON = -123.0768
    TEST_TIME = "08:00"  # 8 AM Rush Hour
    BUDGET = 30          # 30 Minutes
    
    print(f"--- Running Test ---")
    print(f"Start: {TEST_LAT}, {TEST_LON}")
    print(f"Time: {TEST_TIME}, Budget: {BUDGET} mins")

    # 2. Build Graph (Using your builder)
    print("Building Graph...")
    G = graph_builder.build_graph(TEST_TIME, window_minutes=60)
    print(f"Graph Nodes: {len(G.nodes)}")

    # 3. Run Analysis
    print("Calculating Isochrone...")
    polygon = get_isochrone(G, TEST_LAT, TEST_LON, time_budget_mins=BUDGET)
    
    if polygon:
        # 4. Save to GeoJSON for QGIS
        print("Saving 'test_isochrone.geojson'...")
        
        # Wrap in GeoDataFrame to write easily
        final_gdf = gpd.GeoDataFrame({'geometry': [polygon]}, crs="EPSG:4326")
        final_gdf.to_file("test_isochrone.geojson", driver="GeoJSON")
        
        print("Done! Open 'test_isochrone.geojson' in QGIS to verify.")
    else:
        print("Failed to generate polygon.")
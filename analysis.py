import pandas as pd
import geopandas as gpd
import networkx as nx
import pickle
import numpy as np
import sys
from shapely.geometry import Point
from sklearn.neighbors import BallTree

# ===========================
# SETUP & DATA LOADING
# ===========================

print("Initializing Analysis Engine...")

try:
    with open('agg_data/stops.pkl', 'rb') as f:
        STOPS_DICT = pickle.load(f)
        
    stops_df = pd.DataFrame.from_dict(STOPS_DICT, orient='index')
    stops_df.index.name = 'stop_id'
    stops_df = stops_df.reset_index()

    stops_rad = np.deg2rad(stops_df[['lat', 'lon']])
    TREE = BallTree(stops_rad, metric='haversine')
    
    print("Spatial Index built successfully.")

except Exception as e:
    print(f"Error loading data: {e}")
    sys.exit(1)


# =================
# CORE FUNCTIONS
# =================

def get_isochrone(G, start_lat, start_lon, time_budget_mins=30, walk_speed_mps=1.0, max_walk_km=1.0):
    """
    Calculates the reachable area (Isochrone) from a specific point.
    """
    
    # --- 1. PREPARE VARIABLES ---
    
    # FIX: Convert Meters/Second to Meters/Minute
    # 1.0 m/s * 60 = 60 m/min
    walk_speed_mpm = walk_speed_mps * 60.0  
    
    # --- 2. SNAP TO NETWORK ---
    
    user_rad = np.deg2rad([[start_lat, start_lon]])
    radius_rad = max_walk_km / 6371.0
    indices, distances = TREE.query_radius(user_rad, r=radius_rad, return_distance=True)
    
    nearby_indices = indices[0]
    nearby_distances_rad = distances[0]
    
    if len(nearby_indices) == 0:
        print("Warning: No stops found within walking distance.")
        return None

    user_node = "USER_START"
    
    # Add temporary edges from USER to nearby stops
    for idx, dist_rad in zip(nearby_indices, nearby_distances_rad):
        stop_id = str(stops_df.iloc[idx]['stop_id'])
        dist_meters = dist_rad * 6371000
        walk_time_min = dist_meters / walk_speed_mpm
        
        if walk_time_min < time_budget_mins:
            # We add edges to Street Nodes (which are just the stop_id string)
            G.add_edge(user_node, stop_id, weight=walk_time_min)

    # --- 3. RUN DIJKSTRA ---
    
    try:
        reachable_nodes = nx.single_source_dijkstra_path_length(
            G, 
            source=user_node, 
            cutoff=time_budget_mins, 
            weight='weight'
        )
    except:
        # Handle case where user_node isn't connected to anything
        G.remove_node(user_node)
        return None
    
    # DEBUG: Check if we boarded a bus
    # Look for any node that has an underscore (e.g., "1001_99B")
    route_nodes_reached = [n for n in reachable_nodes if "_" in str(n)]
    print(f"DEBUG: Reached {len(reachable_nodes)} total nodes.")
    print(f"DEBUG: Boarded {len(route_nodes_reached)} bus/train vehicles.")
    
    # Cleanup
    G.remove_node(user_node)
    
    if len(reachable_nodes) <= 1:
        return None
        
    
    # --- 4. CREATE ISOCHRONE (The Fix is Here) ---
    
    # DEDUPLICATION: 
    # The Expanded Graph has nodes like "1001" (Street) and "1001_99B" (Bus).
    # We want the BEST time to the physical location "1001".
    
    best_times = {}

    for node, time_taken in reachable_nodes.items():
        # Strip route suffix to get physical ID (e.g., "1001_99B" -> "1001")
        base_stop_id = str(node).split('_')[0]
        
        if base_stop_id not in STOPS_DICT:
            continue
            
        # Keep the shortest time found to this physical location
        if base_stop_id not in best_times:
            best_times[base_stop_id] = time_taken
        else:
            best_times[base_stop_id] = min(best_times[base_stop_id], time_taken)

    # Generate Geometry
    results = []
    
    for stop_id, time_taken in best_times.items():
        # Calculate Remaining Time (The Budget for the final walk)
        remaining_time = time_budget_mins - time_taken
        
        # Calculate Radius (Time * Speed)
        radius_meters = remaining_time * walk_speed_mpm
        
        # We only draw if the circle is meaningful (> 10 meters)
        if radius_meters > 10:
            info = STOPS_DICT[stop_id]
            results.append({
                'geometry': Point(info['lon'], info['lat']),
                'radius': radius_meters
            })

    if not results:
        return None

    # GeoPandas Operations
    gdf = gpd.GeoDataFrame(results, crs="EPSG:4326")
    
    # Project to BC Albers (Meters) for accurate buffering
    gdf_metric = gdf.to_crs("EPSG:3005")
    
    # Buffer the points into circles
    gdf_metric['geometry'] = gdf_metric.geometry.buffer(gdf_metric['radius'])
    
    # Merge all circles into one blob
    blob_metric = gdf_metric.union_all()
    
    # Project back to Lat/Lon
    blob_latlon = gpd.GeoSeries([blob_metric], crs="EPSG:3005").to_crs("EPSG:4326")
    
    return blob_latlon[0]


# ==========================================
# TEST SCRIPT
# ==========================================
if __name__ == "__main__":
    import graph_builder
    
    TEST_LAT = 49.26259
    TEST_LON = -123.0768
    TEST_TIME = "08:00"
    BUDGET = 30
    
    print(f"--- Running Test ---")
    print("Building Graph...")
    G = graph_builder.build_graph(TEST_TIME, window_mins=60)

    print("Calculating Isochrone...")
    polygon = get_isochrone(G, TEST_LAT, TEST_LON, time_budget_mins=BUDGET)
    
    if polygon:
        print("Saving 'test_isochrone.geojson'...")
        final_gdf = gpd.GeoDataFrame({'geometry': [polygon]}, crs="EPSG:4326")
        final_gdf.to_file("agg_data/test_isochrone.geojson", driver="GeoJSON")
        print("Done! Check file in QGIS.")
    else:
        print("Failed to generate polygon.")
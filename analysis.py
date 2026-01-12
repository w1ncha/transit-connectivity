import pandas as pd
import geopandas as gpd
import networkx as nx
import pickle
import numpy as np
import sys
from shapely.geometry import Point
from shapely.geometry import LineString
from sklearn.neighbors import BallTree

# ===========================
# HELPER FUNCTIONS
# ===========================

def check_is_in(coords, file_path):
    check_point = Point(coords)
    polygon = gpd.read_file(file_path)

    if polygon.contains(check_point).any():
        return True
    else:
        return False
    
def get_geometry_for_edge(edge_data):

    if edge_data.get('type') != 'travel': return None
    
    sh_id = edge_data.get('shape_id')
    du = edge_data.get('dist_u')
    dv = edge_data.get('dist_v')
    
    if not sh_id or du is None or dv is None: return None
    if sh_id not in SHAPES_DB: return None
    
    # Lookup
    shape_entry = SHAPES_DB[sh_id]
    all_dists = shape_entry['distances']
    all_coords = shape_entry['coords']
    
    # Slice (Binary Search)
    idx_start = np.searchsorted(all_dists, du, side='right')
    idx_end = np.searchsorted(all_dists, dv, side='right')
    
    # Return Points
    return all_coords[idx_start:idx_end]


# ===========================
# SETUP & DATA LOADING
# ===========================

print("Initializing Analysis Engine...")

try:
    with open('data/stops.pkl', 'rb') as f:
        STOPS_DICT = pickle.load(f)
    with open('data/shapes.pkl', 'rb') as f:
        SHAPES_DB = pickle.load(f)

        
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

# ISOCHRONE FUNCTION

def get_isochrone(G, start_lat, start_lon, time_budget_mins=30, walk_speed_mps=1.2, max_walk_km=1.0):
    """
    Calculates the reachable area (Isochrone) from a specific point.
    """
    
    # 1. PREPARE VARIABLES
    
    # FIX: Convert Meters/Second to Meters/Minute
    # 1.0 m/s * 60 = 60 m/min
    walk_speed_mpm = walk_speed_mps * 60.0  
    
    # 2. SNAP TO NETWORK
    
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

    # 3. RUN DIJKSTRA
    
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
        
    
    # 4. CREATE ISOCHRONE
    
    best_times = {}

    for node, time_taken in reachable_nodes.items():
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
        walk_dist = remaining_time * walk_speed_mpm
        radius_meters = min(walk_dist, max_walk_km*1000)
        
        # We only draw if the circle is meaningful (> 10 meters)
        if radius_meters > 10:
            info = STOPS_DICT[stop_id]
            results.append({
                'geometry': Point(info['lon'], info['lat']),
                'radius': radius_meters
            })

    if not results:
        return None

    # Create GeoDataFrame 
    gdf_points = gpd.GeoDataFrame(results, crs="EPSG:4326")
    
    # Project to BC Albers (Meters) for accurate buffering
    gdf_points_metric = gdf_points.to_crs("EPSG:3005")
    
    # Buffer the points into circles
    gdf_points_metric['geometry'] = gdf_points_metric.geometry.buffer(gdf_points_metric['radius'])
    
    # Merge all circles into one blob
    blob_metric = gdf_points_metric.union_all()
    
    # convert to GDF
    gdf_single = gpd.GeoDataFrame(geometry=[blob_metric], crs="EPSG:3005")

    # We must remove all parts of the polygon that are either on top of water, 
    # or inaccessable by walking (e.g. islands)
    gdf_land = gpd.read_file("data/metro_vancouver_land_poly.geojson")
    gdf_land = gdf_land.to_crs("EPSG:3005")

    gdf_intersection = gpd.overlay(gdf_single, gdf_land, how='intersection')
    gdf_exploded = gdf_intersection.dissolve().explode(index_parts=False)
    gdf_fixed = gpd.sjoin(gdf_exploded, gdf_points_metric, predicate="contains")
    gdf_final = gdf_fixed.dissolve().to_crs("EPSG:4326")

    # Debug
    # print(type(gdf_final))
    return gdf_final

# ROUTING FUNCTION
def get_route(G, start_lat, start_lon, end_lat, end_lon, walk_speed_mps=1.0, max_walk_km=1.0):
    """
    Calculates the shortest path between two points.
    Returns:
       1. GeoDataFrame (LineString) for mapping
       2. Prints the textual path to the terminal
    """
    
    # 1. PREPARE VARIABLES
    walk_speed_mpm = walk_speed_mps * 60.0
    
    # 2. SNAP START POINT (First Mile)
    start_rad = np.deg2rad([[start_lat, start_lon]])
    radius_rad = max_walk_km / 6371.0
    
    s_indices, s_dists = TREE.query_radius(start_rad, r=radius_rad, return_distance=True)
    
    if len(s_indices[0]) == 0:
        print("Error: Start point too far from transit.")
        return None

    # Create Virtual Start Node
    start_node = "USER_START"
    
    for idx, dist_rad in zip(s_indices[0], s_dists[0]):
        stop_id = str(stops_df.iloc[idx]['stop_id'])
        dist_meters = dist_rad * 6371000
        walk_time = dist_meters / walk_speed_mpm
        
        # Add edge: Start -> Stop
        G.add_edge(start_node, stop_id, weight=walk_time, type='walk')

    # 3. SNAP END POINT (Last Mile)
    end_rad = np.deg2rad([[end_lat, end_lon]])
    e_indices, e_dists = TREE.query_radius(end_rad, r=radius_rad, return_distance=True)
    
    if len(e_indices[0]) == 0:
        print("Error: End point too far from transit.")
        G.remove_node(start_node)
        return None

    # Create Virtual End Node
    end_node = "USER_END"
    
    for idx, dist_rad in zip(e_indices[0], e_dists[0]):
        stop_id = str(stops_df.iloc[idx]['stop_id'])
        dist_meters = dist_rad * 6371000
        walk_time = dist_meters / walk_speed_mpm
        
        # Add edge: Stop -> End
        G.add_edge(stop_id, end_node, weight=walk_time, type='walk')

    # 4. RUN SHORTEST PATH
    try:
        node_path = nx.shortest_path(G, source=start_node, target=end_node, weight='weight')
        total_time = nx.shortest_path_length(G, source=start_node, target=end_node, weight='weight')
    except nx.NetworkXNoPath:
        print("No path found between points.")
        G.remove_node(start_node)
        G.remove_node(end_node)
        return None

    # 5. CLEANUP GRAPH
    G.remove_node(start_node)
    G.remove_node(end_node)

# 6. PRINT TEXT INSTRUCTIONS 
    print(f"\n--- PATH FOUND ({total_time:.1f} mins) ---")
    
    step_count = 1
    
    for i in range(len(node_path) - 1):
        u = node_path[i]
        v = node_path[i+1]
        
        # 1. (User -> First Stop)
        if u == "USER_START":
            stop_name = STOPS_DICT.get(v, {}).get('name', v)
            print(f"{step_count}. Walk to {stop_name}")
            step_count += 1
            continue
            
        # 2. (Last Stop -> User)
        if v == "USER_END":
            print(f"{step_count}. Walk to final destination.")
            step_count += 1
            continue

        # 3. Handle Internal Graph Edges
        edge_data = G.get_edge_data(u, v)
        
        if edge_data:
            move_type = edge_data.get('type', 'unknown')
            weight = edge_data.get('weight', 0)
            
            if move_type == 'walk':
                stop_name_v = STOPS_DICT.get(str(v), {}).get('name', v)
                print(f"{step_count}. Walk to {stop_name_v} ({weight:.1f} min)")
                step_count += 1
                
            elif move_type == 'board':
                route = edge_data.get('route_id', 'Unknown')
                print(f"{step_count}. Wait for {route} ({weight:.1f} min avg wait)")
                step_count += 1
                
            elif move_type == 'travel':
                base_v = v.split('_')[0]
                stop_name_v = STOPS_DICT.get(base_v, {}).get('name', base_v)
                print(f"   -> Ride to {stop_name_v} ({weight:.1f} min)")
                
            elif move_type == 'deboard':
                print(f"   -> Get off vehicle.")

    # 7. CONSTRUCT GEOMETRY
    coords = []
    
    coords.append((start_lon, start_lat))
    
    for i in range(len(node_path) - 1):
        u = node_path[i]
        v = node_path[i+1]
        
        if u in ["USER_START", "USER_END"]: continue
        
        # Check Edge
        if G.has_edge(u, v):
            edge_data = G.edges[u, v]
            
            # Try to get curves
            curves = get_geometry_for_edge(edge_data)
            
            if curves:
                coords.extend(curves)
            else:
                # Straight Line Fallback
                # (Strip route ID to get stop lat/lon)
                base_v = str(v).split('_')[0]
                if base_v in STOPS_DICT:
                    info = STOPS_DICT[base_v]
                    coords.append((info['lon'], info['lat']))
                    
    # Add End
    coords.append((end_lon, end_lat))
    
    line = LineString(coords)
    return gpd.GeoDataFrame({'geometry': [line], 'time_min': [total_time]}, crs="EPSG:4326")

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
    final_gdf = get_isochrone(G, TEST_LAT, TEST_LON, time_budget_mins=BUDGET)
    
    if not final_gdf.empty:
        print("Saving 'test_isochrone.geojson'...")
        final_gdf.to_file("data/test_isochrone.geojson", driver="GeoJSON")
        print("Done! Check file in QGIS.")
    else:
        print("Failed to generate polygon.")

# TEST ROUTE GENERATION
    print("\n--- Testing Route Generation ---")
    
    # Destination: Waterfront Station
    DEST_LAT = 49.2858
    DEST_LON = -123.1115
    
    route_gdf = get_route(G, TEST_LAT, TEST_LON, DEST_LAT, DEST_LON)
    
    if route_gdf is not None:
        print("Saving 'test_route.geojson'...")
        route_gdf.to_file("data/test_route.geojson", driver="GeoJSON")
        print("Done! Drag 'test_route.geojson' into QGIS.")
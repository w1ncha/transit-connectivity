import networkx as nx
import pickle
import sys

# ==============================
#  GLOBAL DATA LOADING
# ==============================

print("Loading network data...")

try:
    # Network Edges: {(u, v, route_id): [{'dept': sec, 'dur': sec}, ...]}
    with open('data/network_edges.pkl', 'rb') as f:
        NETWORK_EDGES = pickle.load(f)

    # Transfer Edges: {(u, v, 'transfer'): seconds}
    with open('data/transfer_edges.pkl', 'rb') as f:
        TRANSFER_EDGES = pickle.load(f)

    print("Data loaded successfully.")
    
    # first_key = list(NETWORK_EDGES.keys())[0]
    # print(f"DEBUG: Network Edge Key Type: {type(first_key[0])} Value: '{first_key[0]}'")

    # first_transfer = list(TRANSFER_EDGES.keys())[0]
    # print(f"DEBUG: Transfer Key Type: {type(first_transfer[0])} Value: '{first_transfer[0]}'")

except FileNotFoundError:
    print("Error: Could not find .pkl files in /data folder.")
    print("Did you run preprocessing.py?")
    sys.exit(1)


def parse_time(time_str):
    try:
        h, m = map(int, time_str.split(':'))
        return h * 3600 + m * 60
    except ValueError:
        return None


# =================
# GRAPH BUILDER
# =================

def build_graph(current_time_str, window_mins=60, speed_factor=1.0):
    
    # convert time to seconds
    center_sec = parse_time(current_time_str)
    if center_sec is None:
        raise ValueError("Invalid time format. Use HH:MM")

    # calculate window
    window_seconds = window_mins * 60
    start_window = center_sec - (window_seconds / 2)
    end_window = center_sec + (window_seconds / 2)
    
    G = nx.DiGraph()
        
    # ADD NETWORK EDGES
    for (u, v, route_id), edge_data in NETWORK_EDGES.items():
        
        trips = edge_data['trips']

        # Filter Trips
        valid_trips = [t for t in trips if start_window <= t['dept'] <= end_window]
        if not valid_trips: continue

        # Travel Cost (On the bus)
        count = len(valid_trips)
        total_dur = sum(t['dur'] for t in valid_trips)
        avg_dur_sec = total_dur / count
        adjusted_dur_min = (avg_dur_sec / speed_factor) / 60.0
        
        # Wait Cost (On the street)
        headway_sec = window_seconds / count
        wait_time_min = (headway_sec / 2) / 60.0
        
        # Street Nodes (Physical location)
        street_u = u
        street_v = v
        
        # Route Nodes (Inside the bus)
        route_u = f"{u}_{route_id}"
        route_v = f"{v}_{route_id}"
                
        # BOARDING EDGE (Street -> Bus)
        # Cost = Wait Time
        if not G.has_edge(street_u, route_u):
            G.add_edge(street_u, 
                       route_u, 
                       weight=wait_time_min, 
                       type='board', 
                       route_id=route_id)
        
        # TRAVEL EDGE (Bus -> Bus)
        # Cost = Travel Time (No Wait!)
        G.add_edge(route_u, 
                    route_v, 
                    weight=adjusted_dur_min, 
                    type='travel', 
                    route_id=route_id,
                    shape_id=edge_data['shape_id'],
                    dist_u=edge_data['dist_u'],
                    dist_v=edge_data['dist_v'])
        
        # DEBOARDING EDGE (Bus -> Street)
        # Cost = 0 (Hop off anytime)
        G.add_edge(route_v, street_v, weight=0, type='deboard', route_id=route_id)
        
        """
        print(f"Checking edge {u}->{v}. Window: {start_window} to {end_window}")
        print(f"Sample Trip Time: {trips[0]['dept']}")
        break 
        """

    # ADD TRANSFER EDGES
    # Transfers connect Street Nodes to Street Nodes
    for (u, v, tag), weight_sec in TRANSFER_EDGES.items():
        
        weight_min = weight_sec / 60.0
        
        G.add_edge(
            u, 
            v, 
            weight=weight_min,
            route_id=tag, 
            type='walk'
        )
    return G

# ==========================
# TEST SCRIPT
# ==========================
if __name__ == "__main__":
    print("\n--- Running Graph Builder Test ---")
    
    # Test Parameters
    TEST_TIME = "08:00" # 8:00 AM (Rush Hour)
    TEST_WINDOW = 60    # 1 Hour Window
    
    try:
        # Build
        print(f"Building graph for {TEST_TIME}...")
        graph = build_graph(TEST_TIME, TEST_WINDOW)
        
        # Report Stats
        print(f"Graph built successfully!")
        print(f"Total Nodes (Stops): {len(graph.nodes)}")
        print(f"Total Edges (Connections): {len(graph.edges)}")
        
        # Check specific edge types
        bus_edges = [e for u, v, e in graph.edges(data=True) if e['type'] == 'travel']
        walk_edges = [e for u, v, e in graph.edges(data=True) if e['type'] == 'walk']
        board_edges = [e for u, v, e in graph.edges(data=True) if e['type'] == 'board']
        deboard_edges = [e for u, v, e in graph.edges(data=True) if e['type'] == 'deboard']
        
        print(f"Bus Segments: {len(bus_edges)}")
        print(f"Transfer/Walk Segments: {len(walk_edges)}")
        print(f"Board Segments: {len(board_edges)}")
        print(f"Deboard Segments: {len(deboard_edges)}")
        
        # Sanity Check: Print one random edge
        if len(bus_edges) > 0:
            print(f"\nSample Bus Edge Data: {bus_edges[0]}")

    except Exception as e:
        print(f"\nCRASHED: {e}")
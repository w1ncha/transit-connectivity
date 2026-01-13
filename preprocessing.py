import pandas as pd
import pickle
import pprint


# =======================
# LOADING DATA
# =======================

"""
path = 'txt_data'
data_files = glob.glob(os.path.join(path, "*.txt"))

data = {}

for f in data_files:
    file_name = os.path.splitext(os.path.basename(f))[0]
    data[file_name] = pd.read_csv(f)
"""

trips = pd.read_csv('txt_data/trips.txt', dtype={'shape_id': str})
stop_times = pd.read_csv('txt_data/stop_times.txt', dtype={'stop_id': str})
stops = pd.read_csv('txt_data/stops.txt', dtype={'stop_id': str})
routes = pd.read_csv('txt_data/routes.txt')
transfers = pd.read_csv('txt_data/transfers.txt', dtype={'from_stop_id': str, 'to_stop_id': str})
shapes = pd.read_csv('txt_data/shapes.txt', dtype={'shape_id': str})

# =========================
# NETWORK EDGES FILE
# =========================

# Choose service day

def process_network(day_id=1):

    target_service_id = str(day_id)
    trips['service_id'] = trips['service_id'].astype(str)

    # Filter trips by day
    active_trips = trips[trips['service_id'] == target_service_id]
    active_stop_times = stop_times[stop_times['trip_id'].isin(active_trips['trip_id'])]

    print(f"DEBUG: Processing Day {target_service_id}. Found {len(active_trips)} trips.")

    # Sort values in trip order
    active_stop_times = active_stop_times.sort_values(['trip_id', 'stop_sequence'])

    # Convert time to seconds
    def parse_time(t):
        try:
            h, m, s = map(int, t.split(':'))
            return h * 3600 + m * 60 + s
        except:
            return None
        
    active_stop_times['arrival_sec'] = active_stop_times['arrival_time'].apply(parse_time)

    active_stop_times['shape_dist_traveled'] = active_stop_times['shape_dist_traveled'].fillna(0)

    # Create next stop columns and filter by rows where trip_id doesn't change
    active_stop_times['next_stop_id'] = active_stop_times['stop_id'].shift(-1).fillna(0)
    active_stop_times['next_arrival_sec'] = active_stop_times['arrival_sec'].shift(-1).fillna(0)
    active_stop_times['next_trip_id'] = active_stop_times['trip_id'].shift(-1).fillna(0)
    active_stop_times['next_shape_dist_traveled'] = active_stop_times['shape_dist_traveled'].shift(-1)

    # duration column
    edges = active_stop_times[active_stop_times['trip_id'] == active_stop_times['next_trip_id']].copy()
    edges['duration'] = edges['next_arrival_sec'] - edges['arrival_sec']

    # Adds route name columns
    routes['route_name'] = routes['route_short_name'].fillna("Skytrain") + " " + routes['route_long_name']
    edges = edges.merge(trips[['route_id', 'trip_id', 'shape_id']], on='trip_id', how='left')
    edges = edges.merge(routes[['route_id', 'route_name']], on='route_id', how='left')

    # Cleans data outputs edge.txt for sanity check 
    cols_to_remove = ['arrival_time', 'departure_time', 'stop_headsign', 'pickup_type', 'drop_off_type', 'timepoint', 'next_arrival_sec', 'next_trip_id', 'route_id']
    edges.drop(columns=cols_to_remove, inplace=True)
    edges = edges[['route_name', 'trip_id', 'stop_id', 'next_stop_id', 'stop_sequence', 'arrival_sec', 'duration', 'shape_id', 'shape_dist_traveled', 'next_shape_dist_traveled']]
    edges = edges.sort_values(['route_name', 'trip_id', 'stop_sequence'])
    edges.to_csv('data/edges.csv', index=False)
    # routes.to_csv('data/routes.txt', index=False)

    # create dictionary with
    # key: ('Stop_A', 'Stop_B', 'Route_Name')x
    # value: {'dept': 28800, 'dur': 300}

    network_edges = {}

    iterator = zip(
        edges['stop_id'],
        edges['next_stop_id'],
        edges['route_name'],
        edges['arrival_sec'],
        edges['duration'],
        edges['shape_id'],
        edges['shape_dist_traveled'],
        edges['next_shape_dist_traveled']
    )

    for u, v, route, time, dur, shape, dist_u, dist_v in iterator:

        key = (u, v, route)

        if key not in network_edges:
                    network_edges[key] = {
                        'shape_id': shape,
                        'dist_u': float(dist_u) if pd.notna(dist_u) else None,
                        'dist_v': float(dist_v) if pd.notna(dist_v) else None,
                        'trips': [] 
                    }
        
        network_edges[key]['trips'].append({
            'dept': int(time),
            'dur': int(dur)
        })

    print(f"Network dictionary complete. Created {len(network_edges)} unique route segments. Saving...")

    # save to pickle file
    with open('data/network_edges.pkl', 'wb') as f:
        pickle.dump(dict(network_edges), f)

    return 'data/network_edges.pkl'

# ============================
#  TRANSFER EDGES FILE
# ============================

def process_transfers():

    transfers['min_transfer_time'] //= 2
    # transfers.to_csv('data/transfers_reduced_time.txt')

    transfer_edges = {}

    iterator = zip(
        transfers['from_stop_id'],
        transfers['to_stop_id'],
        transfers['min_transfer_time']
    )

    for u, v, time in iterator:
        key = (u, v, "transfer")

        if pd.isna(time):
            time = 0

        if key in transfer_edges:
            transfer_edges[key] = min(transfer_edges[key], time)
        else:
            transfer_edges[key] = time

    print(f"Transfer dictionary complete. Created {len(transfer_edges)} unique transfer segments. Saving...")

    with open('data/transfer_edges.pkl', 'wb') as f:
        pickle.dump(transfer_edges, f)

    return 'data/transfer_edges.pkl'

# ====================
# STOPS FILE
# ====================

def process_stops():
    stops_dict = {}

    iterator = zip(
        stops['stop_id'],
        stops['stop_name'],
        stops['stop_lat'],
        stops['stop_lon']
    )

    for id, name, lat, lon in iterator:
        key = id
        value = {
            "lat": lat,
            "lon": lon,
            "name": name
        }

        stops_dict[key] = value

    print(f"Stops dictionary complete. Created {len(stops_dict)} stops. Saving...")

    with open('data/stops.pkl', 'wb') as f:
        pickle.dump(stops_dict, f)

    return 'data/stops.pkl'


# ======================
# SHAPES FILE
# ======================

def process_shapes():

    global shapes    
    shapes['shape_dist_traveled'] = pd.to_numeric(shapes['shape_dist_traveled'], errors='coerce')
    shapes = shapes.sort_values(['shape_id', 'shape_dist_traveled'])
    
    shape_db = {}
    
    for sh_id, group in shapes.groupby('shape_id'):
        
        dists = group['shape_dist_traveled'].values
        lats = group['shape_pt_lat'].values
        lons = group['shape_pt_lon'].values
        coords = list(zip(lons, lats))
        
        shape_db[str(sh_id)] = {
            'distances': dists, 
            'coords': coords
        }
        
    print(f"Shape DB built with ({len(shape_db)} shapes). Saving...")
    with open('data/shapes.pkl', 'wb') as f:
        pickle.dump(shape_db, f)
    
    return 'data/shapes.pkl'


# ===================
# TESTING
# ===================

def check_pickle(FILENAME):
    print(f"\n--- INSPECTING: {FILENAME} ---")
    
    try:
        with open(FILENAME, 'rb') as f:
            data = pickle.load(f)
            
        # print general info   
        data_type = type(data)
        print(f"Data Type: {data_type}")
        
        if hasattr(data, '__len__'):
            print(f"Total Items: {len(data)}")
            
        # print content
        print("\n--- SAMPLE CONTENT (First 3 Items) ---")
        
        if isinstance(data, dict):
            keys = list(data.keys())[:3]
            for k in keys:
                print(f"KEY: {k}")
                print(f"VAL: {data[k]}")
                print("-" * 30)
                
        elif isinstance(data, list):
            pprint.pprint(data[:3])
            
        elif isinstance(data, pd.DataFrame):
            print(data.head())
            
        else:
            print(str(data)[:500]) # Print first 500 chars
    
    # error handling
    except FileNotFoundError:
        print(f"Error: File '{FILENAME}' not found.")
    except Exception as e:
        print(f"Error reading pickle: {e}")

def str_check():
    process_network(day_id = 1)
    process_transfers()
    process_stops()

    print("Checking Data Types...")

    # Check Network Edges
    with open('data/network_edges.pkl', 'rb') as f:
        edges = pickle.load(f)
        first_key = list(edges.keys())[0]
        # Key structure: (u, v, route)
        print(f"Network Nodes: {type(first_key[0])} (Should be str)")
        print(f"Network Route: {type(first_key[2])} (Should be str)")

    # Check Transfers
    with open('data/transfer_edges.pkl', 'rb') as f:
        transfers = pickle.load(f)
        first_key = list(transfers.keys())[0]
        print(f"Transfer Nodes: {type(first_key[0])} (Should be str)")

if __name__ == "__main__":
    #  process_network()
    process_stops()
    process_transfers()
    process_shapes()
    check_pickle("data/network_edges.pkl")
    check_pickle("data/transfer_edges.pkl")
    check_pickle("data/stops.pkl")
    check_pickle("data/shapes.pkl")
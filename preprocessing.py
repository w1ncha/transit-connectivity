import pandas as pd
# import glob
# import os
import pickle
from collections import defaultdict

# Load Data
# Data frame is accessible as data['trips'], etc.

"""
path = 'csv_data'
data_files = glob.glob(os.path.join(path, "*.csv"))

data = {}

for f in data_files:
    file_name = os.path.splitext(os.path.basename(f))[0]
    data[file_name] = pd.read_csv(f)
"""

trips = pd.read_csv('csv_data/trips.csv')
stop_times = pd.read_csv('csv_data/stop_times.csv')
routes = pd.read_csv('csv_data/routes.csv')

# Choose service day
day_options = ["weekday", "saturday", "sunday"]
day_map = {"weekday": 1, "saturday": 2, "sunday": 3}

while True:
    day_input = input("Please enter the day [weekday, saturday, sunday]: ").lower().strip()
    if day_input in day_options:
        break
    print("Invalid choice. Please try again.\n")

day_id = day_map[day_input]
# print(f"The day id is {day_id}")

# Filter trips by day
active_trips = trips[trips['service_id'] == day_id]
active_stop_times = stop_times[stop_times['trip_id'].isin(active_trips['trip_id'])]

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

# Create next stop columns and filter by rows where trip_id doesn't change
active_stop_times['next_stop_id'] = active_stop_times['stop_id'].shift(-1).fillna(0).astype(int)
active_stop_times['next_arrival_sec'] = active_stop_times['arrival_sec'].shift(-1).fillna(0).astype(int)
active_stop_times['next_trip_id'] = active_stop_times['trip_id'].shift(-1).fillna(0).astype(int)

# duration column
edges = active_stop_times[active_stop_times['trip_id'] == active_stop_times['next_trip_id']].copy()
edges['duration'] = edges['next_arrival_sec'] - edges['arrival_sec']

# Adds route name columns
routes['route_name'] = routes['route_short_name'].fillna("Skytrain") + " " + routes['route_long_name']
edges = edges.merge(trips[['route_id', 'trip_id']], on='trip_id', how='left')
edges = edges.merge(routes[['route_id', 'route_name']], on='route_id', how='left')

# Cleans data outputs edge.csv for sanity check 
cols_to_remove = ['arrival_time', 'departure_time', 'stop_headsign', 'pickup_type', 'drop_off_type', 'timepoint', 'shape_dist_traveled', 'next_arrival_sec', 'next_trip_id', 'route_id']
edges.drop(columns=cols_to_remove, inplace=True)
edges = edges[['route_name', 'trip_id', 'stop_id', 'next_stop_id', 'stop_sequence', 'arrival_sec', 'duration']]
edges = edges.sort_values(['route_name', 'trip_id', 'stop_sequence'])
edges.to_csv('agg_data/edges.csv', index=False)
# routes.to_csv('agg_data/routes.csv', index=False)

# create dictionary with
# key: ('Stop_A', 'Stop_B', 'Route_Name')
# value: {'dept': 28800, 'dur': 300}

network_edges = defaultdict(list)

iterator = zip(
    edges['stop_id'],
    edges['next_stop_id'],
    edges['route_name'],
    edges['arrival_sec'],
    edges['duration']
)

for u, v, route, time, dur in iterator:
    key = (u, v, route)
    trip_data = {
        'dept': int(time),
        'dur': int(dur)
    }
    
    network_edges[key].append(trip_data)

print(f"Network dictionary complete. Created {len(network_edges)} unique route segments.")

# save to pickle file
print("Saving to file...")
with open('agg_data/network_edges.pkl', 'wb') as f:
    pickle.dump(dict(network_edges), f)

print("Done! 'network_edges.pkl' is ready.")

# peek inside pickle file
"""
sample_key = list(network_edges.keys())[0]
print("\n--- SAMPLE ENTRY ---")
print(f"Key (Start, End, Route): {sample_key}")
print(f"Total Trips on this segment: {len(network_edges[sample_key])}")
print(f"First 3 Trips: {network_edges[sample_key][:3]}")
"""
# working file
# to be added to preprocessing

import pandas as pd
import pickle

transfers = pd.read_csv('csv_data/transfers.csv')
stops = pd.read_csv('csv_data/stops.csv')

transfers = transfers.merge(
    stops[['stop_id', 'stop_code', 'stop_name']],
    left_on='from_stop_id', 
    right_on='stop_id', 
    how='left')

transfers.rename(columns={'stop_code': 'from_stop_code', 'stop_name': 'from_stop_name'}, inplace=True)

transfers = transfers.merge(
    stops[['stop_id', 'stop_code', 'stop_name']],
    left_on='to_stop_id', 
    right_on='stop_id', 
    how='left')

transfers.rename(columns={'stop_code': 'to_stop_code', 'stop_name': 'to_stop_name'}, inplace=True)
transfers.drop(columns=['stop_id_x', 'stop_id_y'], inplace=True)

transfers.to_csv('agg_data/transfers.csv', index=False)

# create dictionary with
# key: {'Stop_A', 'Stop_B', 'transfer'}
# value: 240

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

print(f"Transfer dictionary complete. Created {len(transfer_edges)} unique segments.")

print("Saving to file...")
with open('agg_data/transfer_edges.pkl', 'wb') as f:
    pickle.dump(transfer_edges, f)

print("Done! 'transfer_edges.pkl' is ready.")
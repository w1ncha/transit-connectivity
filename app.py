# Prepare GTFS Data

# only run on acquiring new GTFS Data
# import txt_to_csv

# Run on changing date
import preprocessing
preprocessing.process_network(day_id = 1)
preprocessing.process_transfers()
preprocessing.process_stops()

# Run on changing time
import graph_builder
current_graph = graph_builder.build_graph(
    current_time_str="17:00", 
    window_mins=60,
    speed_factor=1.0  
)

"""
# Run on click
import analysis
final_shape = analysis.get_isochrone(
    G=current_graph,
    start_lat=49.26, 
    start_lon=-123.07, 
    time_budget_mins=30
)
"""
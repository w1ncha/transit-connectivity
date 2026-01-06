import re
import sys
import geopandas as gpd
import geoprocessing
# only run on acquiring new GTFS Data
# import txt_to_csv

# DAY SELECTION
while True:
    day_options = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    day_map = {"monday": 1, "tuesday": 1, "wednesday": 1, "thursday": 1, "friday": 1, "saturday": 2, "sunday": 3}

    day_input = input("Please enter a day of the week or press Enter to exit program:\n").strip().lower()

    if not day_input:
        print("Exiting program...")
        sys.exit()

    if day_input not in day_options:
        print("Invalid entry. Please try again.")
        continue
    
    import preprocessing
    preprocessing.process_network(day_id = day_map[day_input])
    preprocessing.process_transfers()
    preprocessing.process_stops()
    # preprocessing.str_check()
    break # Move to the next loop

# TIME SELECTIOON
while True:
    time_input = input("Please enter a time of day in format HH:MM or press Enter to exit:\n").strip()

    if not time_input:
        print("Exiting program...")
        sys.exit()

    if not re.match(r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$", time_input):
        print("Invalid format or time. Please use HH:MM (e.g., 14:30).")
        continue

    import graph_builder
    current_graph = graph_builder.build_graph(
        current_time_str=time_input, 
        window_mins=60,
        speed_factor=1.0  
    )
    break # Move to the next loop

# COORDINATE SELECTION
while True:
    coords_input = input("Enter Lat, Lon (e.g., 49.2, -123.1) or press Enter to exit:\n").strip()

    if not coords_input:
        print("Exiting program...")
        sys.exit()

    if "," not in coords_input:
        print("Invalid format. Use 'Lat, Lon'.")
        continue

    try:
        start_lat_str, start_lon_str = coords_input.split(",")
        start_lat, start_lon = float(start_lat_str.strip()), float(start_lon_str.strip())

        if not geoprocessing.check_is_in((start_lon, start_lat), "data/METRO VANCOUVER LAND POLY.geojson"):
            print("Error: Those coordinates are outside Metro Vancouver or not on land.")
            continue
        else: 
            break        
    except ValueError:
        print("Invalid input. Please enter numeric degrees.")
        continue

# BUDGET SELECTION
while True:
    budget_raw = input("Enter your time budget (an integer between 1 and 30, inclusive.) or press Enter to exit:\n").strip()
    
    if not budget_raw:
        print("Exiting program...")
        sys.exit()

    try:
        budget_input = int(budget_raw)
        budget_min, budget_max = 1, 30

        if not (budget_min <= budget_input <= budget_max):
            print("Invalid budget. Please try again.")
            continue

        import analysis
        polygon = analysis.get_isochrone(
            G=current_graph,
            start_lat = start_lat, 
            start_lon = start_lon, 
            time_budget_mins = budget_input, 
        )
        if polygon:
            print("Saving 'isochrone.geojson'...")
            final_gdf = gpd.GeoDataFrame({'geometry': [polygon]}, crs="EPSG:4326")
            final_gdf.to_file("data/temp_isochrone.geojson", driver="GeoJSON")
            
            geoprocessing.subtract_water()

            print("A geojson file has been generated for input to GIS in '/output'.")
            break
        else:
            print("Failed to generate polygon.")

    except ValueError:
        print("Error: Try again.")
        continue
        
# DJIKSTRA ROUTING
while True:
    coords_input = input("If you would like to find the route to somewhere within your isochrone, please enter the coordinates. Otherwise, press Enter to exit.\n")

    if not coords_input:
        print("Exiting program...")
        sys.exit()

    if "," not in coords_input:
        print("Invalid format. Use 'Lat, Lon'.")
        continue

    try:
        end_lat_str, end_lon_str = coords_input.split(",")
        end_lat, end_lon = float(end_lat_str.strip()), float(end_lon_str.strip())

        if not geoprocessing.check_is_in((end_lon, end_lat), "data/isochrone.geojson"):
            print("Error: Those coordinates are not within the isochrone.")
            continue
        else: 
            break        
    except ValueError:
        print("Invalid input. Please enter numeric degrees.")
        continue

analysis.get_route(
    G = current_graph,
    start_lat = start_lat,
    start_lon = start_lon,
    end_lat = end_lat,
    end_lon = end_lon,
    walk_speed_mps=1.0, 
    max_walk_km=1.0
)
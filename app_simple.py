# Prepare GTFS Data
import re
import geopandas as gpd
# only run on acquiring new GTFS Data
# import txt_to_csv

# Real app: run on changing date
while True:
    day_options = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    day_map = {"monday": 1, "tuesday": 1, "wednesday": 1, "thursday": 1, "friday": 1, "saturday": 2, "sunday": 3}

    day_input = input("Please enter a day of the week or press Enter to exit program:\n").strip().lower()

    if not day_input:
        print("Exiting program...")
        break

    if day_input not in day_options:
        print("Invalid entry. Please try again.")
        continue
    
    import preprocessing
    preprocessing.process_network(day_id = day_map[day_input])
    preprocessing.process_transfers()
    preprocessing.process_stops()
    # preprocessing.str_check()

    # Real app: run upon changing time
    while True:

        time_input = input("Please enter a time of day in format HH:MM or press Enter to re-enter a day:\n").strip()

        if not time_input:
            break

        if not re.match(r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$", time_input):
            print("Invalid format or time. Please use HH:MM (e.g., 14:30).")
            continue

        import graph_builder
        current_graph = graph_builder.build_graph(
            current_time_str=time_input, 
            window_mins=60,
            speed_factor=1.0  
        )
        
        # real app: run on clicking map
        while True:
            coords_input = input("Enter Lat, Lon (e.g., 49.2, -123.1) or press Enter to re-enter a time:\n").strip()

            if not coords_input:
                break

            # 2. Basic format check
            if "," not in coords_input:
                print("Invalid format. Use 'Lat, Lon'.")
                continue

            try:
                lat_str, lon_str = coords_input.split(",")
                lat, lon = float(lat_str.strip()), float(lon_str.strip())

                lat_valid = 49.0 <= lat <= 49.35
                lon_valid = -123.3 <= lon <= -122.5
                
                if lat_valid and lon_valid:

                    budget_min, budget_max = 1, 30
                    while True:
                        budget_input = int(input("Enter your time budget (an integer between 1 and 30, inclusive.) or press Enter to go back:\n"))
                        if not budget_input:
                            break

                        if not (budget_min <= budget_input <= budget_max):
                            print("Invalid budget. Please try again.")
                            continue

                        import analysis
                        polygon = analysis.get_isochrone(
                            G=current_graph,
                            start_lat = lat, 
                            start_lon = lon, 
                            time_budget_mins = budget_input, 
                        )
                        if polygon:
                            print("Saving 'test_isochrone.geojson'...")
                            final_gdf = gpd.GeoDataFrame({'geometry': [polygon]}, crs="EPSG:4326")
                            final_gdf.to_file("agg_data/test_isochrone.geojson", driver="GeoJSON")
                            print("A geojson file has been generated for input to GIS. You may enter more co-ordinates.")
                            break

                        else:
                            print("Failed to generate polygon.")

                    continue

                else:
                    print("Error: Those coordinates are outside of Vancouver.")
                        
            except ValueError:
                print("Invalid input. Please enter numeric degrees.")

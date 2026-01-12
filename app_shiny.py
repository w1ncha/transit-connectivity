from shiny import App, reactive, ui, req
from shinywidgets import output_widget, render_widget
import ipyleaflet as L
import pandas as pd
import geopandas as gpd
import json
import pickle
import os

# Import your modules
import analysis
import preprocessing
import graph_builder

# =====================
# UI
# =====================

app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.h4("Settings", style="margin-top: 0; font-weight: bold;"),
        ui.input_select("day", "Select Day", choices=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]),
        ui.div(
            ui.tags.label("Select Start Time:", {"for": "start_time"}),
            ui.tags.input(id="start_time", type="time", value="09:00", class_="form-control"),
            class_="form-group shiny-input-container"
        ),
        ui.input_slider("budget", "Time Budget", 5, 60, 30),
        ui.input_slider("frequency", "Frequency Modifier", 0.1, 3.0, 1, step=0.1),
        ui.input_slider("walk_speed", "Walk Speed (m/s)", 0.5, 2.0, 1.2, step=0.1),
        ui.input_slider("max_walk", "Max Walk Distance (km)", 0.1, 2.5, 1.0, step=0.1),
        ui.input_checkbox_group("toggles", "Infrastructure Toggles", 
                                {"bus": "Bus Routes", "skytrain": "SkyTrain", "bridges": "Bridges"}, 
                                selected=["bus", "skytrain", "bridges"]),
        ui.input_action_button("submit", "Update Settings", class_="btn-primary"),
    ),
    ui.card(
        ui.card_header("Metro Vancouver Transit Pulse – Transit Connectivity Simulator"),
        output_widget("map_display"),
        style="height: 90vh;"
    ),
)


# =====================
# SERVER
# =====================

def server(input, output, session):
    
    # 1. STATE MANAGEMENT
    selected_coords = reactive.Value(None)
    
    # Use a standard dictionary or variable for caching logic, NOT a reactive value.
    # This persists as long as the session is active.
    cache_state = {"last_day": None}

    # Initialize Map
    map_obj = L.Map(center=(49.21340119048903, -122.93785360348627), zoom=11)
    map_obj.add_layer(L.basemaps.CartoDB.Positron)
    
    # Initialize User Marker
    user_marker = L.Marker(location=(0,0), draggable=False, visible=False)
    map_obj.add_layer(user_marker)

    # 2. HANDLE CLICKS
    def handle_click(**kwargs):
        # Only trigger on actual clicks
        if kwargs.get('type') == 'click':
            coords = kwargs.get('coordinates')
            print(f"📍 CLICK DETECTED: {coords}")
            
            # Update the Marker visual immediately
            user_marker.location = coords
            user_marker.visible = True
            
            # Update the Reactive Value to trigger computations
            selected_coords.set(coords)
            
    map_obj.on_interaction(handle_click)

    @render_widget
    def map_display():
        return map_obj

    # --- 3. DATA LOADING STAGE ---
    @reactive.Calc
    def get_network_data():
        """
        Triggered by 'Submit'.
        Checks if the day changed. If so, runs preprocessing.
        Always returns the pickle data.
        """
        # Take dependency on submit button
        input.submit()
        
        # Get the day inside isolate so we only update when Submit is clicked
        with reactive.isolate():
            selected_day = input.day()

        # LOGIC: Check standard cache variable, not a reactive value
        if selected_day != cache_state["last_day"]:
            print(f"🔄 Day changed to {selected_day}. Processing Network CSVs...")
            
            day_map = {
                "Monday": 1, "Tuesday": 1, "Wednesday": 1, "Thursday": 1, 
                "Friday": 1, "Saturday": 2, "Sunday": 3
            }
            
            # Run heavy processing
            preprocessing.process_network(day_id=day_map[selected_day])
            
            # Update cache
            cache_state["last_day"] = selected_day
        else:
            print(f"✅ Day is still {selected_day}. Using cached Pickle.")
        
        # Load and return the pickle
        if os.path.exists('data/network_edges.pkl'):
            with open('data/network_edges.pkl', 'rb') as f:
                return pickle.load(f)
        return None

    # --- 4. GRAPH BUILDER STAGE ---
    @reactive.Calc
    def current_graph():
        """
        Builds the graph using the loaded network data and current settings.
        """
        # Ensure network data is loaded
        network_edges = get_network_data()
        req(network_edges)
        
        # Isolate other inputs so they only apply on Submit
        with reactive.isolate():
            time_str = input.start_time()
            freq_mod = input.frequency()
            # active_toggles = input.toggles() 
        
        print(f"Building Graph: {time_str} | Freq: {freq_mod}")
        
        return graph_builder.build_graph(
            current_time_str=time_str,
            window_mins=60,
            frequency_modifier=freq_mod
        )

    # --- 5. ANALYSIS STAGE ---
    @reactive.Calc
    def isochrone_gdf():
        """
        Runs when:
        1. Graph updates (via Submit)
        2. Map is Clicked (via selected_coords)
        """
        # Dependencies that trigger updates
        G = current_graph()
        coords = selected_coords.get()
        
        # Stop if no click yet
        req(coords)
        
        # Parameters (read directly, or isolated if you only want them to update on Submit)
        # Using isolate here means changing the slider won't update the map until you click Submit 
        # OR click the map again. This matches your UI pattern.
        with reactive.isolate():
            budget = input.budget()
            speed = input.walk_speed()
            max_walk = input.max_walk()
            
        print(f"Calculating Isochrone for {coords} with budget {budget}")
        
        try:
            return analysis.get_isochrone(
                G=G,
                start_lat=coords[0],
                start_lon=coords[1],
                time_budget_mins=budget,
                walk_speed_mps=speed,
                max_walk_km=max_walk
            )
        except Exception as e:
            print(f"Error in isochrone calc: {e}")
            return None

    # --- 6. MAP UPDATE ---
    @reactive.Effect
    def update_map():
        # Get data
        gdf = isochrone_gdf()
        
        # Remove old isochrone layers safely
        # We iterate over a tuple copy to avoid modification errors
        for layer in tuple(map_obj.layers):
            # Check if layer has a name attribute and if it matches
            if hasattr(layer, 'name') and layer.name == 'isochrone':
                map_obj.remove_layer(layer)
        
        if gdf is not None and not gdf.empty:
            print("Drawing new Isochrone...")
            
            geo_data = json.loads(gdf.to_json())
            
            new_layer = L.GeoJSON(
                data=geo_data, 
                style={'color': '#2b8cbe', 'fillColor': '#2b8cbe', 'fillOpacity': 0.4},
                name='isochrone' 
            )
            
            map_obj.add_layer(new_layer)

app = App(app_ui, server)
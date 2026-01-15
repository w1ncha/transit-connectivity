from shiny import App, reactive, ui, req, render
from shinywidgets import output_widget, render_widget
from ipywidgets import Layout
from ipyleaflet import AwesomeIcon
from shapely.geometry import Point, shape
import ipyleaflet as L
import geopandas as gpd
import json
import pickle
import os
import re

# Import modules
import analysis
import preprocessing
import graph_builder

LAND_GDF = gpd.read_file("data/metro_vancouver_land_poly.geojson")

# =====================
# UI
# =====================

app_ui = ui.page_sidebar(
    
    ui.sidebar(
        ui.h4("Settings", style="margin-top: 0; font-weight: bold;"),
        ui.input_select("day", "Select Day", choices=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]),
        ui.input_text(
            "start_time", 
            "Select Start Time:", 
            value="17:00", 
            placeholder="HH:MM"
        ),
        ui.input_slider("budget", "Time Budget", 5, 60, 30),
        ui.input_slider("frequency", "Frequency Modifier", 0.1, 3.0, 1.0, step=0.1),
        ui.input_slider("walk_speed", "Walk Speed (m/s)", 0.5, 2.5, 1.2, step=0.1),
        ui.input_slider("max_walk", "Max Walk Distance (km)", 0.1, 3.0, 1.0, step=0.1),

        ui.div(
            ui.input_checkbox_group("toggles", "Infrastructure Toggles", 
                                    {"skytrain": "SkyTrain", "bridges": "Bridges"}, 
                                    selected=["skytrain", "bridges"]),
            style="margin-bottom: -10px;" 
        ),
        
        ui.hr(style="margin-top: 5px; margin-bottom: 10px;"), 
        
        ui.div(
            ui.input_action_button("submit", "Update Settings", class_="btn-primary w-100"),
            ui.div(style="height: 5px;"), 
            ui.input_action_button("clear_map", "Clear Map", class_="btn-danger w-100"),
        ),
    ),

    ui.head_content(
        ui.tags.style("""
            #custom-loading-overlay {
                position: fixed;
                top: 0; left: 0; width: 100%; height: 100%;
                background-color: rgba(0, 0, 0, 0.6);
                color: white;
                display: flex;
                justify-content: center;
                align-items: center;
                font-size: 24px;
                font-weight: bold;
                z-index: 99999;
                backdrop-filter: blur(2px);
                cursor: wait;
                opacity: 0;
                pointer-events: none;
                transition: opacity 0.2s ease-in-out 0.2s;
            }

            html.shiny-busy #custom-loading-overlay {
                opacity: 1;
                pointer-events: auto; 
            }
            
            .leaflet-container,
            .leaflet-interactive {
            cursor: crosshair !important;
            }
            .leaflet-dragging, 
            .leaflet-dragging .leaflet-grab, 
            .leaflet-dragging .leaflet-interactive {
                cursor: grabbing !important; 
            }
        """)
    ),

    ui.div("Calculating...", id="custom-loading-overlay"),
    
    ui.card(
        ui.card_header(
            ui.span(
                "Metro Vancouver Transit Pulse – Transit Connectivity Simulator", 
                style="font-size: 24px; font-weight: bold;"
            ),
            class_="py-3" 
        ),
        
        # 1. THE MAP
        output_widget("map_display", width="100%", height="100%"), 
        
        # 2. THE FLOATING ITINERARY PANEL (Overlay)
        # We use a standard absolute div to ensure it doesn't block the map
        ui.output_ui("itinerary_panel"),

        style="padding: 0; height: 90vh; position: relative;" # relative needed for absolute child
    )
)


# =====================
# SERVER
# =====================

def server(input, output, session):
    
    # Reactive Values
    origin_coords = reactive.Value(None)      
    destination_coords = reactive.Value(None) 
    current_iso_geom = reactive.Value(None)
    # Store route steps here
    current_steps = reactive.Value(None)
    cache_state = {"last_day": None}

    # Initialize Map
    map_obj = L.Map(center=(49.21340119048903, -122.93785360348627), zoom=11, layout=Layout(height='100%'), scroll_wheel_zoom=True)
    map_obj.add_layer(L.basemaps.CartoDB.Positron)
    
    # Markers
    red_icon = AwesomeIcon(name='flag', marker_color='red', icon_color='white')
    blue_icon = AwesomeIcon(name='circle', marker_color='blue', icon_color='white')

    user_marker = L.Marker(location=(0,0), draggable=False, visible=False, icon=blue_icon, title="Origin")
    dest_marker = L.Marker(location=(0,0), draggable=False, visible=False, icon=red_icon, title="Destination")
    
    map_obj.add_layer(user_marker)
    map_obj.add_layer(dest_marker)

    # ---------------------------------------------------------
    # CLICK HANDLER
    # ---------------------------------------------------------
    def handle_click(**kwargs):
        if kwargs.get('type') == 'click':
            coords = kwargs.get('coordinates')

            click_point = Point(coords[1], coords[0])
            active_poly = current_iso_geom.get()

            if active_poly is not None and active_poly.contains(click_point):
                # === CLICK INSIDE: SET DESTINATION ===
                print(f"📍 Destination Clicked: {coords}")
                dest_marker.location = coords
                dest_marker.visible = True
                destination_coords.set(coords)
            else:
                # === CLICK OUTSIDE: NEW ORIGIN ===
                print(f"📍 New Origin Clicked: {coords}")
                
                # Update UI Markers
                user_marker.location = coords
                user_marker.visible = True
                dest_marker.visible = False 
                
                # Update State
                origin_coords.set(coords)
                destination_coords.set(None)
                current_iso_geom.set(None)
                current_steps.set(None) # Clear steps
            
    map_obj.on_interaction(handle_click)

    @render_widget
    def map_display():
        return map_obj
    
    # ---------------------------------------------------------
    # CLEAR BUTTON LOGIC
    # ---------------------------------------------------------
    @reactive.Effect
    @reactive.event(input.clear_map)
    def clear_all():
        print("🗑️ Clearing Map")
        origin_coords.set(None)
        destination_coords.set(None)
        current_iso_geom.set(None)
        current_steps.set(None)
        
        user_marker.visible = False
        dest_marker.visible = False
        
        for layer in map_obj.layers:
            if getattr(layer, 'name', '') in ['isochrone', 'route_path']:
                map_obj.remove_layer(layer)

    # ---------------------------------------------------------
    # DATA & GRAPH
    # ---------------------------------------------------------
    @reactive.Calc
    def get_network_data():
        input.submit() 
        with reactive.isolate():
            selected_day = input.day()

        if selected_day != cache_state["last_day"]:
            day_map = {
                "Monday": 1, "Tuesday": 1, "Wednesday": 1, "Thursday": 1, 
                "Friday": 1, "Saturday": 2, "Sunday": 3
            }
            preprocessing.process_network(day_id=day_map[selected_day])
            cache_state["last_day"] = selected_day
        
        if os.path.exists('data/network_edges.pkl'):
            with open('data/network_edges.pkl', 'rb') as f:
                return pickle.load(f)
        return None

    @reactive.Calc
    def current_graph():
        network_data = get_network_data()
        req(network_data)
        with reactive.isolate():
            time_str = input.start_time()
            freq_mod = input.frequency()

        if not re.match(r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$", time_str):
            return None
        
        return graph_builder.build_graph(
            network_edges = network_data,
            current_time_str=time_str,
            window_mins=60,
            frequency_modifier=freq_mod
        )

    # ---------------------------------------------------------
    # ISOCHRONE CALCULATION
    # ---------------------------------------------------------
    @reactive.Calc
    def isochrone_data():
        G = current_graph()
        coords = origin_coords.get()
        req(coords, G)
        
        with reactive.isolate():
            budget = input.budget()
            speed = input.walk_speed()
            max_walk = input.max_walk()

        if not LAND_GDF.contains(Point(coords[1], coords[0])).any():
            return None
        
        print("Calculating Isochrone...")
        gdf = analysis.get_isochrone(
            G=G,
            start_lat=coords[0],
            start_lon=coords[1],
            time_budget_mins=budget,
            walk_speed_mps=speed,
            max_walk_km=max_walk
        )
        return gdf

    # ---------------------------------------------------------
    # ROUTE CALCULATION
    # ---------------------------------------------------------
    @reactive.Calc
    def route_data():
        orig = origin_coords.get()
        dest = destination_coords.get()
        req(orig, dest)
        
        with reactive.isolate():
            G = current_graph()
            speed = input.walk_speed()
            walk = input.max_walk()
            req(G)

        print(f"Calculating Route from {orig} to {dest}")
        
        try:
            # SAFETY CHECK: Handle if analysis.get_route returns 1 or 2 values
            result = analysis.get_route(
                G=G,
                start_lat=orig[0], start_lon=orig[1],
                end_lat=dest[0], end_lon=dest[1],
                walk_speed_mps=speed, max_walk_km=walk
            )
            
            # If function returns tuple (gdf, steps)
            if isinstance(result, tuple) and len(result) == 2:
                return result[0], result[1]
            
            # If function returns just gdf (fallback)
            return result, ["Route calculated (Update analysis.py for steps)"]

        except Exception as e:
            print(f"Routing Error: {e}")
            return None, None

    # ---------------------------------------------------------
    # UI: ITINERARY PANEL (Rendered via CSS Overlay)
    # ---------------------------------------------------------
    @render.ui
    def itinerary_panel():
        # Get steps from the reactive variable updated in draw_route
        steps = current_steps.get()
        
        if not steps:
            return None
        
        # Build list items
        list_items = ""
        for i, step in enumerate(steps):
            color = "#555"
            fw = "normal"
            list_items += f'<li style="margin-bottom: 6px; color: {color}; font-weight: {fw};">{step}</li>'

        # Return a CSS-Positioned DIV (Not ipywidgets)
        # This will float over the map. Z-Index 1000 ensures it is above the map.
        return ui.HTML(f"""
            <div style="
                position: absolute;
                top: 10px;
                right: 10px;
                width: 320px;
                z-index: 1000;
                background-color: rgba(255, 255, 255, 0.95);
                backdrop-filter: blur(5px);
                border-radius: 12px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.2);
                border: 1px solid rgba(255,255,255,0.3);
                font-family: -apple-system, sans-serif;
                font-size: 13px;
            ">
                <details open>
                    <summary style="
                        padding: 12px 15px;
                        font-weight: bold;
                        font-size: 14px;
                        cursor: pointer;
                        border-bottom: 1px solid #eee;
                        outline: none;
                        user-select: none;
                    ">Trip Itinerary</summary>
                    <ul style="
                        padding: 10px 15px 15px 30px; 
                        margin: 0; 
                        line-height: 1.4; 
                        max-height: 60vh; 
                        overflow-y: auto;
                    ">
                        {list_items}
                    </ul>
                </details>
            </div>
        """)

    # ---------------------------------------------------------
    # DRAW EFFECTS
    # ---------------------------------------------------------
    @reactive.Effect
    def draw_isochrone():
        gdf = isochrone_data()
        
        # Clear existing
        current_steps.set(None) # Hides the panel
        
        for layer in map_obj.layers:
            if layer.name in ['isochrone', 'route_path']:
                map_obj.remove_layer(layer)

        if gdf is None or gdf.empty:
            current_iso_geom.set(None)
            return

        current_iso_geom.set(gdf.geometry.union_all())

        geo_data = json.loads(gdf.to_json())
        new_layer = L.GeoJSON(
            data=geo_data, 
            name='isochrone',
            style={'color': '#2b8cbe', 'fillOpacity': 0.4, 'weight': 2}
        )
        
        map_obj.add_layer(new_layer)
        if user_marker in map_obj.layers:
            map_obj.remove_layer(user_marker)
            map_obj.add_layer(user_marker)
        
        dest_marker.visible = False

    @reactive.Effect
    def draw_route():
        route_gdf, steps = route_data()

        # Update Steps State (Triggers Panel Render)
        current_steps.set(steps)

        # Clear existing route
        for layer in map_obj.layers:
            if layer.name == 'route_path':
                map_obj.remove_layer(layer)

        if route_gdf is None or route_gdf.empty:
            return

        geo_data = json.loads(route_gdf.to_json())
        route_layer = L.GeoJSON(
            data=geo_data,
            name='route_path',
            style={'color': '#d95f0e', 'weight': 5, 'opacity': 0.8}
        )
        
        map_obj.add_layer(route_layer)
        
        if dest_marker in map_obj.layers:
            map_obj.remove_layer(dest_marker)
            map_obj.add_layer(dest_marker)

app = App(app_ui, server)
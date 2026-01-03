### About this project
This is a project I, a Civil Engineering student, am using to learn python and explore my interest in integrating programming and mathematics into transportation engineering!

This project will be an interactive dashboard that lets users visualize the resiliency of the Metro Vancouver transit network. By selecting a specific location and time of day, the dashboard will generate a 'travel bubble' on the map, showing exactly how far a person can get within a set time limit using transit (busses, Skytrain.

Users will then be able to modify city conditions by interacting with on-screen options. For example, they can simulate a snowstorm by slowing down buses, or simulate a major infrastructure failure by virtually closing the Lions Gate Bridge, and watch in real-time as the travel bubble shrinks. Finally, the tool will include accessibility features, allowing users to adjust walking speeds to see how these disruptions disproportionately affect seniors or those with limited mobility compared to the average commuter.

### Current Project Status
This project is current in the preliminary stages. I am working on creating a edge dictionary from the trip information that I can feed into NetworkX to run Djikstra's algorithm. This will allow me to create isochrones, or "travel bubbles".

### Downloading GTFS Data
This project requires updated Translink GTFS Data. 

1. Download latest static GTFS data here: https://www.translink.ca/about-us/doing-business-with-translink/app-developer-resources/gtfs/gtfs-data
2. Unzip file and bring into a ./txt_data folder
3. Run txt_to_csv.py

Now, you should have the files you need to run this dashboard!

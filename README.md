### About this project
This is a project I am using to learn python and explore my interest in integrating programming and mathematics into transportation engineering!

This project will be an interactive dashboard that lets users visualize the resiliency of the Metro Vancouver transit network. By selecting a specific location and time of day, the dashboard will generate a 'travel bubble' on the map, showing exactly how far a person can get within a set time limit using transit (busses, Skytrain, etc.).

Users will then be able to modify city conditions by interacting with on-screen options. For example, they can simulate a snowstorm by slowing down buses, or simulate a major infrastructure failure by virtually closing the Lions Gate Bridge, and watch in real-time as the travel bubble shrinks. Finally, the tool will include accessibility features, allowing users to adjust walking speeds to see how these disruptions disproportionately affect seniors or those with limited mobility compared to the average commuter.

### Current Project Status
This project is currently in progress. I have completed the preliminary backend, means that you can generate 'travel bubbles' using this program. You are able to visualize them by importing the generated .geojson file into a GIS application such as ArcGIS or QGIS. 

![Isochrone Image](git_data/isochrone.png)

The next steps for me are to iron out some bugs (for example, the program currently assumes you can walk on water!). Then, I will work on learning Shiny for Python to create a front end so that the user does not need to use a GIS application. Finally, I will work on some advanced features, including toggling bus/skytrain, changing service frequency, changing walking speeds, disabling infrastructure and

### Downloading GTFS Data
This project requires updated Translink GTFS Data. 

1. Download latest static GTFS data here: https://www.translink.ca/about-us/doing-business-with-translink/app-developer-resources/gtfs/gtfs-data
2. Unzip file and bring into a ./txt_data folder
3. Run txt_to_csv.py

### Running Files
Currently there is no UI! In this development stage, you can run simple_app.py and follow the terminal commands. To change some parameters like walking speed and maximum allowable walk distance, you can edit them in a code editor.

### Sources
This project uses open data files from various governments:
- [Province of BC Boundary Terrestrial](https://open.canada.ca/data/dataset/30aeb5c1-4285-46c8-b60b-15b1a6f4258b)
- [Metro Vancouver Administrative Boundaries](https://open-data-portal-metrovancouver.hub.arcgis.com/datasets/1c86f57d9fcc4fc3a8134328b07f07e6_10/explore?location=49.283369%2C-123.061408%2C9.87)
- [Province of BC Freshwater Atlas Rivers](https://catalogue.data.gov.bc.ca/dataset/f7dac054-efbf-402f-ab62-6fc4b32a619e)

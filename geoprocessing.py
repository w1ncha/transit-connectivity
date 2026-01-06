import geopandas as gpd
from shapely.geometry import Point

def subtract_water():
    gdf1 = gpd.read_file("data/METRO VANCOUVER LAND POLY.geojson")
    gdf2 = gpd.read_file("data/temp_isochrone.geojson")

    gdf1 = gdf1.to_crs("EPSG:3005")
    gdf2 = gdf2.to_crs("EPSG:3005")

    intersection_gdf = gpd.overlay(gdf1, gdf2, how='intersection')

    final_blob = intersection_gdf.dissolve()

    final_blob.to_crs("EPSG:4326").to_file("output/isochrone.geojson", driver='GeoJSON')
    final_blob.to_crs("EPSG:4326").to_file("data/isochrone.geojson", driver='GeoJSON')

    return

def check_is_in(coords, file_path):
    check_point = Point(coords)
    polygon = gpd.read_file(file_path)

    if polygon.contains(check_point).any():
        return True
    else:
        return False
    
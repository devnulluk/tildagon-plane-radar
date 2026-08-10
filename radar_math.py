"""Small, allocation-light geometry helpers for the Plane Radar UI."""
import math
EARTH_RADIUS_KM = 6371.0088

def offset_km(center_lat, center_lon, lat, lon):
    lat0 = math.radians(center_lat); lat1 = math.radians(lat)
    dlat = lat1 - lat0; dlon = math.radians(lon - center_lon); mean_lat = (lat0 + lat1) * 0.5
    east = EARTH_RADIUS_KM * dlon * math.cos(mean_lat); north = EARTH_RADIUS_KM * dlat
    return east, north, math.sqrt(east * east + north * north)

def radar_xy(center_lat, center_lon, lat, lon, outer_km, radius_px):
    east, north, distance = offset_km(center_lat, center_lon, lat, lon)
    if outer_km <= 0: return 0.0, 0.0, distance
    scale = radius_px / outer_km
    return east * scale, -north * scale, distance

def rim_xy(east_km, north_km, radius_px):
    length = math.sqrt(east_km * east_km + north_km * north_km)
    if length <= 0.000001: return 0.0, 0.0
    return (east_km / length) * radius_px, -(north_km / length) * radius_px

def heading_vector(degrees, length):
    angle = math.radians(degrees or 0.0)
    return math.sin(angle) * length, -math.cos(angle) * length

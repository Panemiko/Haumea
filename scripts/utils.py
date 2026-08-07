import re
import math

def sanitize_filename(name: str) -> str:
    """Sanitizes a string to make it safe for filenames."""
    sanitized = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)
    sanitized = re.sub(r'_+', '_', sanitized)
    return sanitized.strip('_')

def parse_grid_option(grid_str: str) -> dict:
    """
    Parses the --grid option which can be:
    - 'lat,lon' -> center point, default radius 5 km
    - 'lat,lon,radius' -> center point and radius in km
    - 'minLat,minLon,maxLat,maxLon' -> bounding box
    
    Returns a dict with keys: 'grid_bbox', 'grid_cell', 'zoom', 'geo'
    """
    if not grid_str:
        return {}
        
    parts = [p.strip() for p in grid_str.split(',') if p.strip()]
    
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        raise ValueError("Grid option coordinates must be valid numbers.")
        
    res = {
        'grid_cell': 0.5,  # Default grid cell is 0.5 km
        'zoom': 16         # Default zoom level for grid cells
    }
    
    if len(nums) == 2:
        # lat, lon -> center point, default 5km radius
        lat, lon = nums[0], nums[1]
        bbox = calculate_bbox_from_center(lat, lon, 5.0)
        res['grid_bbox'] = bbox
        res['geo'] = f"{lat:.6f},{lon:.6f}"
    elif len(nums) == 3:
        # lat, lon, radius
        lat, lon, radius = nums[0], nums[1], nums[2]
        bbox = calculate_bbox_from_center(lat, lon, radius)
        res['grid_bbox'] = bbox
        res['geo'] = f"{lat:.6f},{lon:.6f}"
    elif len(nums) == 4:
        # minLat, minLon, maxLat, maxLon
        res['grid_bbox'] = f"{nums[0]:.6f},{nums[1]:.6f},{nums[2]:.6f},{nums[3]:.6f}"
        lat = (nums[0] + nums[2]) / 2.0
        lon = (nums[1] + nums[3]) / 2.0
        res['geo'] = f"{lat:.6f},{lon:.6f}"
    else:
        raise ValueError("Grid option must have 2 (lat,lon), 3 (lat,lon,radius_km), or 4 (minLat,minLon,maxLat,maxLon) values.")
        
    return res

def calculate_bbox_from_center(lat: float, lon: float, radius_km: float) -> str:
    """Calculates a bounding box around a center coordinate with a given radius in km."""
    # Earth's radius in km is ~6371
    # 1 degree latitude is approximately 111 km
    delta_lat = radius_km / 111.0
    
    # 1 degree longitude is approximately 111 * cos(lat) km
    lat_rad = math.radians(lat)
    cos_lat = math.cos(lat_rad)
    if cos_lat == 0:
        # At the poles, longitude doesn't matter much, let's avoid division by zero
        delta_lon = radius_km / 111.0
    else:
        delta_lon = radius_km / (111.0 * cos_lat)
        
    min_lat = lat - delta_lat
    max_lat = lat + delta_lat
    min_lon = lon - delta_lon
    max_lon = lon + delta_lon
    
    return f"{min_lat:.6f},{min_lon:.6f},{max_lat:.6f},{max_lon:.6f}"

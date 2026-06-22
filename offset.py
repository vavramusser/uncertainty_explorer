import numpy as np
import pandas as pd
from shapely.geometry import Point, Polygon, mapping
from shapely.ops import unary_union
from geopy.distance import geodesic
from geopy import Point as GeoPoint


# center bearing per 8-point cardinal direction (degrees clockwise from north)
DIRECTION_CENTER_BEARINGS = {
    'N': 0, 'NE': 45, 'E': 90, 'SE': 135,
    'S': 180, 'SW': 225, 'W': 270, 'NW': 315,
}

UNIT_TO_KM = {
    'm': 0.001, 'km': 1.0, 'mi': 1.60934, 'ft': 0.0003048,
}


def compute_offset_point(anchor_lat, anchor_lon, distance, direction, units='m'):
    """Geodesic destination of a cardinal offset from an anchor feature.

    Returns (lat, lon) of the point `distance` `units` along `direction` from
    the anchor — i.e. the offset locality itself, not the reference feature.
    """
    if units not in UNIT_TO_KM:
        raise ValueError(f"unsupported unit '{units}' — use m, km, mi, or ft")
    distance_km = distance * UNIT_TO_KM[units]
    bearing = DIRECTION_CENTER_BEARINGS[direction.upper()]
    pt = geodesic(kilometers=distance_km).destination(GeoPoint(anchor_lat, anchor_lon), bearing)
    return pt.latitude, pt.longitude


def compute_wedge(anchor_lat, anchor_lon, distance, direction, units='m', error_pct=0.05):
    
    DIRECTION_BEARINGS = {
        'N':  {'center': 0,   'ccw': 337.5, 'cw': 22.5},
        'NE': {'center': 45,  'ccw': 22.5,  'cw': 67.5},
        'E':  {'center': 90,  'ccw': 67.5,  'cw': 112.5},
        'SE': {'center': 135, 'ccw': 112.5, 'cw': 157.5},
        'S':  {'center': 180, 'ccw': 157.5, 'cw': 202.5},
        'SW': {'center': 225, 'ccw': 202.5, 'cw': 247.5},
        'W':  {'center': 270, 'ccw': 247.5, 'cw': 292.5},
        'NW': {'center': 315, 'ccw': 292.5, 'cw': 337.5},
    }
    
    UNIT_TO_KM = {
        'm':  0.001,
        'km': 1.0,
        'mi': 1.60934,
        'ft': 0.0003048,
    }
    
    if units not in UNIT_TO_KM:
        raise ValueError(f"unsupported unit '{units}' — use m, km, mi, or ft")
    
    distance_km = distance * UNIT_TO_KM[units]
    inner_km = max(0, distance * (1 - error_pct) * UNIT_TO_KM[units])
    outer_km = distance * (1 + error_pct) * UNIT_TO_KM[units]
    
    bearings = DIRECTION_BEARINGS[direction.upper()]
    anchor = GeoPoint(anchor_lat, anchor_lon)
    
    ccw = bearings['ccw']
    cw = bearings['cw']
    
    # handle north wrap-around
    if ccw > cw:
        bearing_range = np.linspace(ccw, cw + 360, 20) % 360
    else:
        bearing_range = np.linspace(ccw, cw, 20)
    
    # outer arc (ccw to cw)
    outer_arc = []
    for bearing in bearing_range:
        pt = geodesic(kilometers=outer_km).destination(anchor, bearing)
        outer_arc.append((pt.longitude, pt.latitude))
    
    # inner arc (cw to ccw — reversed to close the polygon)
    inner_arc = []
    for bearing in reversed(bearing_range):
        pt = geodesic(kilometers=inner_km).destination(anchor, bearing)
        inner_arc.append((pt.longitude, pt.latitude))
    
    # ring: outer arc → inner arc reversed → close
    wedge_coords = outer_arc + inner_arc + [outer_arc[0]]
    
    return Polygon(wedge_coords)


def compute_coordinate_pair_offset(anchor_lat, anchor_lon,
                                    distance_1, direction_1,
                                    distance_2, direction_2,
                                    units='m',
                                    error_pct=0.05):
    """
    Compute a point from anchor by applying two sequential offsets,
    with uncertainty polygon derived from combined distance errors.
    
    Distance error modeled as percentage of each distance component,
    combined in quadrature: error = sqrt((d1*pct)^2 + (d2*pct)^2)
    
    Parameters:
        anchor_lat, anchor_lon: anchor point coordinates
        distance_1, direction_1: first offset
        distance_2, direction_2: second offset
        units: 'm', 'km', 'mi', 'ft'
        error_pct: fractional distance error (default 0.05 = 5%)
    
    Returns:
        result_lat, result_lon: result point
        error_radius_km: combined error radius in km
        uncertainty_polygon: shapely Polygon (buffer around result point)
    """
    
    DIRECTION_BEARINGS = {
        'N': 0, 'NE': 45, 'E': 90, 'SE': 135,
        'S': 180, 'SW': 225, 'W': 270, 'NW': 315,
    }
    
    UNIT_TO_KM = {
        'm':  0.001,
        'km': 1.0,
        'mi': 1.60934,
        'ft': 0.0003048,
    }
    
    if units not in UNIT_TO_KM:
        raise ValueError(f"unsupported unit '{units}' — use m, km, mi, or ft")
    
    d1_km = distance_1 * UNIT_TO_KM[units]
    d2_km = distance_2 * UNIT_TO_KM[units]
    
    b1 = DIRECTION_BEARINGS[direction_1.upper()]
    b2 = DIRECTION_BEARINGS[direction_2.upper()]
    
    # apply first offset
    pt1 = geodesic(kilometers=d1_km).destination(
        GeoPoint(anchor_lat, anchor_lon), b1
    )
    
    # apply second offset from result of first
    pt2 = geodesic(kilometers=d2_km).destination(
        GeoPoint(pt1.latitude, pt1.longitude), b2
    )
    
    result_lat = pt2.latitude
    result_lon = pt2.longitude
    
    # combined error in quadrature (in km)
    e1_km = d1_km * error_pct
    e2_km = d2_km * error_pct
    error_radius_km = np.sqrt(e1_km**2 + e2_km**2)
    
    print(f"d1 error: ±{e1_km*1000:.0f}m")
    print(f"d2 error: ±{e2_km*1000:.0f}m")
    print(f"combined error radius: ±{error_radius_km*1000:.0f}m")
    
    # build uncertainty polygon as buffer around result point
    # approximate degrees per km at this latitude
    lat_deg_per_km = 1 / 111.0
    lon_deg_per_km = 1 / (111.0 * np.cos(np.radians(result_lat)))
    
    # generate circle points
    angles = np.linspace(0, 2 * np.pi, 64)
    circle_coords = [
        (result_lon + error_radius_km * lon_deg_per_km * np.cos(a),
         result_lat + error_radius_km * lat_deg_per_km * np.sin(a))
        for a in angles
    ]
    uncertainty_polygon = Polygon(circle_coords)
    
    return result_lat, result_lon, error_radius_km, uncertainty_polygon


def apply_offset_calculation(row, enrichment_cache):
    """
    For cardinal offset records, compute wedge geometry from anchor coordinates.
    Returns geojson of wedge polygon or None if anchor not available.
    """
    
    if row['sub_type'] != 'cardinal':
        return None
    
    # get anchor coordinates from llm-selected candidate
    llm_id = row.get('llm_geonameid')
    if not llm_id or pd.isna(llm_id):
        return None
    
    # find anchor in candidates
    candidates = row['candidates']
    anchor = next((c for c in candidates if str(c['geonameid']) == str(int(llm_id))), None)
    if not anchor:
        return None
    
    anchor_lat = anchor['latitude']
    anchor_lon = anchor['longitude']
    
    # get offset components from classifier
    classification = row['locality_classification']
    components = classification.get('components', {})
    
    distance = components.get('distance')
    units = components.get('unit', 'mi')
    direction = components.get('direction')
    
    if not all([distance, units, direction]):
        return None
    
    # normalize units
    unit_map = {'mi': 'mi', 'mile': 'mi', 'miles': 'mi', 
                'km': 'km', 'kilometer': 'km', 'kilometers': 'km'}
    units = unit_map.get(units.lower(), 'mi')
    
    try:
        wedge = compute_wedge(anchor_lat, anchor_lon, distance, direction, units=units)
        return mapping(wedge)  # convert to geojson dict
    except Exception as e:
        print(f"error computing wedge for {row['Precise Locality']}: {e}")
        return None
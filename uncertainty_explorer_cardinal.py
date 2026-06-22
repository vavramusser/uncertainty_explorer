import streamlit as st
import folium
from streamlit_folium import st_folium
import math
from shapely.geometry import mapping, shape
from shapely.geometry import Point as ShapelyPoint, Polygon
from pyproj import Transformer
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from offset import compute_wedge
from geopy.distance import geodesic
from geopy import Point as GeoPoint

st.set_page_config(layout="wide", page_title="Chain of Flowers — Uncertainty Explorer")

st.title("🌸 Uncertainty Explorer · Cardinal Offset Point Locality")
st.markdown("*Demonstrating honest spatial uncertainty representation for cardinal offset locality strings*")

# --- default values from Oxford House record ---
DEFAULT_LAT = 54.94853
DEFAULT_LON = -95.26598
DEFAULT_ANCHOR_NAME = "Oxford House"
DEFAULT_DISTANCE = 40
DEFAULT_UNITS = "mi"
DEFAULT_DIRECTION = "SE"
LOCALITY_STRING = "Oxford House, 40 Mi SE"

DIRECTIONS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
DIRECTION_BEARINGS = {
    "N": 0, "NE": 45, "E": 90, "SE": 135,
    "S": 180, "SW": 225, "W": 270, "NW": 315
}

# preserve map state
if 'map_center' not in st.session_state:
    st.session_state.map_center = [DEFAULT_LAT, DEFAULT_LON]
if 'map_zoom' not in st.session_state:
    st.session_state.map_zoom = 7

# --- sidebar controls ---
st.sidebar.title("🛠️Controls")
#st.sidebar.markdown(f"**Locality:** `{LOCALITY_STRING}`")
#st.sidebar.markdown(f"**Anchor:** {DEFAULT_ANCHOR_NAME} ({DEFAULT_LAT:.4f}, {DEFAULT_LON:.4f})")
#st.sidebar.divider()

error_pct = st.sidebar.select_slider(
    "Error % (distance wedge)",
    options=[0, 5, 10, 15, 20, 25],
    value=5,
    help="Percentage of distance used as uncertainty on inner and outer arc"
)

st.sidebar.divider()
st.sidebar.markdown("**Display Options**")
show_wedge = st.sidebar.toggle("Show Uncertainty Wedge", value=True)
show_circular = st.sidebar.toggle("Show Uncertainty Buffer", value=False)
show_arrow = st.sidebar.toggle("Show Distance Line", value=False)

# set defaults first
distance = DEFAULT_DISTANCE
direction = DEFAULT_DIRECTION

st.sidebar.divider()
show_bonus = st.sidebar.toggle("Show Bonus Controls", value=False)

if show_bonus == True:

    distance = st.sidebar.slider(
        "Distance",
        min_value=10,
        max_value=100,
        value=DEFAULT_DISTANCE,
        step=5,
        help=f"Distance in {DEFAULT_UNITS}"
    )
    st.sidebar.markdown(f"*Units: {DEFAULT_UNITS}*")

    direction = st.sidebar.select_slider(
        "Cardinal Direction",
        options=DIRECTIONS,
        value=DEFAULT_DIRECTION
    )

# --- calculations ---
bearing = DIRECTION_BEARINGS[direction]
unit_to_km = {'mi': 1.60934, 'km': 1.0}
distance_km = distance * unit_to_km[DEFAULT_UNITS]

# calculated point
calc_point = geodesic(kilometers=distance_km).destination(
    GeoPoint(DEFAULT_LAT, DEFAULT_LON), bearing
)
calc_lat = calc_point.latitude
calc_lon = calc_point.longitude

# wedge
wedge_geojson = None
wedge_shape = None
try:
    wedge = compute_wedge(
        DEFAULT_LAT, DEFAULT_LON,
        distance, direction,
        units=DEFAULT_UNITS,
        error_pct=error_pct/100
    )
    wedge_shape = wedge
    wedge_geojson = mapping(wedge)
except Exception as e:
    st.warning(f"Wedge calculation error: {e}")

# circular buffer — geodesically accurate
# compute in geographic coordinates using max distance from calc point to wedge vertices
circular_geojson = None
bounding_radius_m = None
bounding_radius_mi = None
bounding_radius_km = None

if wedge_shape is not None:
    from geopy.distance import geodesic as geo_dist
    
    coords = list(wedge_shape.exterior.coords)
    
    # find max geodesic distance from calculated point to any wedge vertex
    max_dist_km = max(
        geo_dist((calc_lat, calc_lon), (c[1], c[0])).km
        for c in coords
    )
    
    bounding_radius_km = max_dist_km
    bounding_radius_m = max_dist_km * 1000
    bounding_radius_mi = max_dist_km / 1.60934
    
if show_circular and wedge_shape is not None:
    from geopy.distance import geodesic as geo_dist
    from geopy import Point as GeoPoint
    
    coords = list(wedge_shape.exterior.coords)
    
    # max geodesic distance from calc point to any wedge vertex
    max_dist_km = max(
        geo_dist((calc_lat, calc_lon), (c[1], c[0])).km
        for c in coords
    )
    
    # generate circle points geodesically at that distance in all directions
    circle_points = []
    for bearing_deg in range(0, 360, 5):
        pt = geo_dist(kilometers=max_dist_km).destination(
            GeoPoint(calc_lat, calc_lon), bearing_deg
        )
        circle_points.append((pt.longitude, pt.latitude))
    circle_points.append(circle_points[0])  # close the polygon
    
    circular_geojson = mapping(Polygon(circle_points))

# --- map ---
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    m = folium.Map(
        location=st.session_state.map_center,
        zoom_start=st.session_state.map_zoom
    )

    # wedge
    if show_wedge and wedge_geojson:
        folium.GeoJson(
            wedge_geojson,
            style_function=lambda x: {
                'fillColor': 'blue', 'color': 'blue',
                'weight': 2, 'fillOpacity': 0.25
            },
            tooltip=f"Uncertainty wedge: {distance} {DEFAULT_UNITS} {direction} ± {error_pct}%"
        ).add_to(m)

    # circular buffer
    if show_circular and circular_geojson:
        folium.GeoJson(
            circular_geojson,
            style_function=lambda x: {
                'fillColor': 'purple', 'color': 'purple',
                'weight': 2, 'fillOpacity': 0.15,
                'dashArray': '5 5'
            },
            tooltip=f"Bounding circle: ± {bounding_radius_mi:.1f} mi"
        ).add_to(m)

    # distance arrow
    if show_arrow:
        folium.PolyLine(
            locations=[[DEFAULT_LAT, DEFAULT_LON], [calc_lat, calc_lon]],
            color='gray',
            weight=2,
            dash_array='8 4',
            tooltip=f"{distance} {DEFAULT_UNITS} {direction}"
        ).add_to(m)
        mid_lat = (DEFAULT_LAT + calc_lat) / 2
        mid_lon = (DEFAULT_LON + calc_lon) / 2
        folium.Marker(
            location=[mid_lat, mid_lon],
            icon=folium.DivIcon(
                html=f'<div style="font-size:11px;color:gray;white-space:nowrap;">{distance} {DEFAULT_UNITS} {direction}</div>',
                icon_size=(120, 20),
                icon_anchor=(60, 10)
            )
        ).add_to(m)

    # anchor point
    folium.Marker(
        location=[DEFAULT_LAT, DEFAULT_LON],
        popup=f"Anchor: {DEFAULT_ANCHOR_NAME}",
        tooltip=DEFAULT_ANCHOR_NAME,
        icon=folium.Icon(color='red', icon='home')
    ).add_to(m)

    # calculated point
    folium.Marker(
        location=[calc_lat, calc_lon],
        popup=f"Calculated: {distance} {DEFAULT_UNITS} {direction} of {DEFAULT_ANCHOR_NAME}",
        tooltip=f"Calculated: {calc_lat:.4f}, {calc_lon:.4f}",
        icon=folium.Icon(color='blue', icon='map-marker')
    ).add_to(m)

    map_data = st_folium(m, width=800, height=550, key="wedge_map")
    if map_data and map_data.get('center'):
        st.session_state.map_center = [map_data['center']['lat'], map_data['center']['lng']]
    if map_data and map_data.get('zoom'):
        st.session_state.map_zoom = map_data['zoom']

with col2:
    st.subheader("🎯 Original Locality")
    st.markdown(f"<span style='font-size:24px'>{LOCALITY_STRING}</span>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    if distance != DEFAULT_DISTANCE or direction != DEFAULT_DIRECTION:
        modified = f"{DEFAULT_ANCHOR_NAME}, {distance} Mi {direction}"
        st.markdown(f"<span style='font-size:20px'>**User-Modified Locality:**<br>&emsp;{modified}</span>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)


    st.subheader("📊 Summary")
    st.markdown(f"<span style='font-size:20px'>**Anchor Point:**<br>&emsp;{DEFAULT_ANCHOR_NAME} ({DEFAULT_LAT:.4f}, {DEFAULT_LON:.4f})</span>", unsafe_allow_html=True)

    inner_dist = distance * (1 - error_pct/100)
    outer_dist = distance * (1 + error_pct/100)

    st.markdown(f"<span style='font-size:20px'>**Distance:**<br>&emsp;{distance} {DEFAULT_UNITS} ± {error_pct}% ({inner_dist:.1f} – {outer_dist:.1f} {DEFAULT_UNITS})</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:20px'>**Direction:**<br>&emsp;{direction} ({bearing}°)</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:20px'>**Calculated Point:**<br>&emsp;{calc_lat:.4f}, {calc_lon:.4f}</span>", unsafe_allow_html=True)

    if bounding_radius_mi is not None:
        st.markdown(f"<span style='font-size:20px'>**Uncertainty Buffer Radius:**<br>&emsp;± {bounding_radius_mi:.1f} mi (± {bounding_radius_km:.1f} km)</span>", unsafe_allow_html=True)

with col3:
    st.subheader("🌐 Darwin Core Output")
    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("#### Calculated Point")
    st.markdown(f"<span style='font-size:15px'>**decimalLatitude:** {calc_lat:.6f}</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:15px'>**decimalLongitude:** {calc_lon:.6f}</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:15px'>**coordinateUncertaintyInMeters:** {bounding_radius_m:.0f}</span>", unsafe_allow_html=True)

    st.divider()

    st.markdown("#### Wedge Footprint")
    # footprint WKT from wedge
    if wedge_shape is not None:
        from shapely import wkt
        wedge_wkt = wedge_shape.wkt

        # wkt as regula text
        wedge_wkt_display = wedge_wkt[:200] + "..." if len(wedge_wkt) > 200 else wedge_wkt
        st.markdown(f"<span style='font-size:15px'>**footprintWKT:** {wedge_wkt_display}</span>", unsafe_allow_html=True)

        # wkt in embedded scroll window
        #st.markdown(f"<span style='font-size:15px'>**footprintWKT:**</span>", unsafe_allow_html=True)
        #st.code(wedge_wkt[:200] + "..." if len(wedge_wkt) > 200 else wedge_wkt, language=None)
        
        st.markdown(f"<span style='font-size:15px'>**footprintSRS:** EPSG:4326</span>", unsafe_allow_html=True)

    st.divider()

    st.markdown("##### Additional Metadata")
    st.markdown(f"<span style='font-size:13px'>**georeferenceRemarks:** cardinal offset wedge, {error_pct}% distance error, {direction} bearing</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:13px'>**georeferenceSources:** GeoNames, OSM</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:13px'>**georeferencedBy:** Chain of Flowers pipeline</span>", unsafe_allow_html=True)
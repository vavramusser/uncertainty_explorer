import streamlit as st
import folium
from streamlit_folium import st_folium
import pickle
import math
from shapely.geometry import mapping, shape, Polygon
from shapely.ops import transform as shapely_transform
from pyproj import Transformer
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from geopy.distance import geodesic
from geopy import Point as GeoPoint

def get_utm_crs(lon, lat):
    zone = int((lon + 180) / 6) + 1
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    return f"EPSG:{epsg}"

def minimum_bounding_circle_projected(shape_geom, center_lat, center_lon):
    from shapely import minimum_bounding_circle
    # --- calculations in projected space (UTM for accuracy) ---
    utm_crs = get_utm_crs(CENTROID_LON, CENTROID_LAT)
    transformer_to = Transformer.from_crs("EPSG:4326", utm_crs, always_xy=True)
    transformer_back = Transformer.from_crs(utm_crs, "EPSG:4326", always_xy=True)
    shape_proj = shapely_transform(transformer_to.transform, shape_geom)
    mbc_proj = minimum_bounding_circle(shape_proj.convex_hull)
    mbc_center = mbc_proj.centroid
    radius_m = math.sqrt(mbc_proj.area / math.pi)
    radius_km = radius_m / 1000
    center_lon_out, center_lat_out = transformer_back.transform(
        mbc_center.x, mbc_center.y
    )
    circle_points = []
    for b in range(0, 360, 1):
        pt = geodesic(kilometers=radius_km).destination(
            GeoPoint(center_lat_out, center_lon_out), b
        )
        circle_points.append((pt.longitude, pt.latitude))
    circle_points.append(circle_points[0])
    return center_lat_out, center_lon_out, radius_km, Polygon(circle_points)

def geodesic_bounding_circle(center_lat, center_lon, shape_geom):
    """Get all coords handling both Polygon and MultiPolygon."""
    if shape_geom.geom_type == 'MultiPolygon':
        all_coords = []
        for geom in shape_geom.geoms:
            all_coords.extend(list(geom.exterior.coords))
    else:
        all_coords = list(shape_geom.exterior.coords)
    
    max_dist_km = max(
        geodesic((center_lat, center_lon), (c[1], c[0])).km
        for c in all_coords
    )
    circle_points = []
    for bearing_deg in range(0, 360, 5):
        pt = geodesic(kilometers=max_dist_km).destination(
            GeoPoint(center_lat, center_lon), bearing_deg
        )
        circle_points.append((pt.longitude, pt.latitude))
    circle_points.append(circle_points[0])
    return Polygon(circle_points), max_dist_km

st.set_page_config(layout="wide", page_title="Chain of Flowers — Named Place Uncertainty")

st.title("🌸 Uncertainty Explorer · Named Place Polygon Locality")
st.markdown("*Demonstrating honest spatial uncertainty representation for named place locality strings*")

# --- load enrichment cache ---
@st.cache_data
def load_cache():
    with open('demo_cache.pkl', 'rb') as f:
        return pickle.load(f)

demo_cache = load_cache()

# --- constants ---
GEONAMEID = 5887418
FEATURE_NAME = "Artillery Lake"
LOCALITY_STRING = "Artillery Lake"
CENTROID_LAT = 63.1726
CENTROID_LON = -107.8744
FEATURE_TYPE = "Lake (LK)"

# --- load and simplify polygon ---
@st.cache_data
def load_polygon():
    geojson = demo_cache[GEONAMEID]['geojson']
    full_shape = shape(geojson)
    simplified = full_shape.simplify(0.01, preserve_topology=True)
    return full_shape, simplified

full_shape, simplified_shape = load_polygon()

# --- session state ---
if 'np_map_center' not in st.session_state:
    st.session_state.np_map_center = [CENTROID_LAT, CENTROID_LON]
if 'np_map_zoom' not in st.session_state:
    st.session_state.np_map_zoom = 8

# --- sidebar controls ---
st.sidebar.title("🛠️ Controls")

uncertainty_type = st.sidebar.radio(
    "Locality Representation",
    options=[
        "Polygon only",
        "Polygon + exterior buffer",
        "Exterior buffer only (donut)"
    ],
    index=0
)

buffer_km = 0
if uncertainty_type in ["Polygon + exterior buffer", "Exterior buffer only (donut)"]:
    buffer_km = st.sidebar.slider(
        "Buffer distance (km)",
        min_value=1,
        max_value=50,
        value=10,
        step=1
    )

st.sidebar.divider()

centroid_method = st.sidebar.radio(
    "Uncertainty Buffer Method",
    options=[
        "Polygon centroid",
        "Area extent"
    ],
    index=0
)

st.sidebar.divider()
st.sidebar.markdown("**Display Options**")
show_polygon_centroid = st.sidebar.toggle("Show Polygon Point/Centroid", value=True)

# only show uncertainty centroid toggle when non-polygon method selected
show_uncertainty_centroid = False
if centroid_method == "Area extent":
    show_uncertainty_centroid = st.sidebar.toggle(
        "Show Area Extent Centroid (Corrected Center)", value=False
    )

show_circle = st.sidebar.toggle("Show Uncertainty Buffer", value=False)


# --- calculations in projected space ---
transformer_to = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
transformer_back = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

simp_proj = shapely_transform(transformer_to.transform, simplified_shape)
full_proj = shapely_transform(transformer_to.transform, full_shape)
buffer_m = buffer_km * 1000

if uncertainty_type == "Polygon only":
    uncertainty_proj = simp_proj
    footprint_proj = full_proj
elif uncertainty_type == "Polygon + exterior buffer":
    uncertainty_proj = simp_proj.buffer(buffer_m)
    footprint_proj = full_proj.buffer(buffer_m)
elif uncertainty_type == "Exterior buffer only (donut)":
    uncertainty_proj = simp_proj.buffer(buffer_m).difference(simp_proj)
    footprint_proj = full_proj.buffer(buffer_m).difference(full_proj)

# convert back for display
uncertainty_shape = shapely_transform(transformer_back.transform, uncertainty_proj)
footprint_shape = shapely_transform(transformer_back.transform, footprint_proj)

# always compute polygon centroid
polygon_centroid_lat = CENTROID_LAT
polygon_centroid_lon = CENTROID_LON

# always compute MBC from the outer extent of the uncertainty area
if uncertainty_type == "Exterior buffer only (donut)":
    # for donut, MBC should encompass the outer ring, not the hole
    # outer ring is uncertainty_shape unioned with simplified_shape
    from shapely.ops import unary_union
    mbc_input = unary_union([uncertainty_shape, simplified_shape])
else:
    mbc_input = uncertainty_shape

mbc_lat, mbc_lon, mbc_radius_km, mbc_circle = minimum_bounding_circle_projected(
    mbc_input, CENTROID_LAT, CENTROID_LON
)

uncertainty_centroid_lat = mbc_lat
uncertainty_centroid_lon = mbc_lon

# active centroid and circle based on method
if centroid_method == "Polygon centroid":
    center_lat = polygon_centroid_lat
    center_lon = polygon_centroid_lon
    bounding_circle, bounding_radius_km = geodesic_bounding_circle(
        center_lat, center_lon, uncertainty_shape
    )
else:
    center_lat = mbc_lat
    center_lon = mbc_lon
    bounding_circle = mbc_circle
    bounding_radius_km = mbc_radius_km

bounding_radius_m = bounding_radius_km * 1000
bounding_radius_mi = bounding_radius_km / 1.60934

# --- layout ---
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    m = folium.Map(
        location=st.session_state.np_map_center,
        zoom_start=st.session_state.np_map_zoom
    )

    if uncertainty_type == "Polygon only":
        folium.GeoJson(
            mapping(simplified_shape),
            style_function=lambda x: {
                'fillColor': 'blue', 'color': 'blue',
                'weight': 2, 'fillOpacity': 0.3
            },
            tooltip=f"Polygon: {FEATURE_NAME}"
        ).add_to(m)

    elif uncertainty_type == "Polygon + exterior buffer":
        folium.GeoJson(
            mapping(simplified_shape),
            style_function=lambda x: {
                'fillColor': 'blue', 'color': 'blue',
                'weight': 2, 'fillOpacity': 0.3
            },
            tooltip=f"Polygon: {FEATURE_NAME}"
        ).add_to(m)
        folium.GeoJson(
            mapping(uncertainty_shape),
            style_function=lambda x: {
                'fillColor': 'blue', 'color': 'blue',
                'weight': 1, 'fillOpacity': 0.1
            },
            tooltip=f"Polygon + {buffer_km} km buffer"
        ).add_to(m)

    elif uncertainty_type == "Exterior buffer only (donut)":
        folium.GeoJson(
            mapping(simplified_shape),
            style_function=lambda x: {
                'fillColor': 'none', 'color': 'blue',
                'weight': 2, 'fillOpacity': 0
            },
            tooltip=f"Feature boundary: {FEATURE_NAME}"
        ).add_to(m)
        folium.GeoJson(
            mapping(uncertainty_shape),
            style_function=lambda x: {
                'fillColor': 'blue', 'color': 'blue',
                'weight': 1, 'fillOpacity': 0.3
            },
            tooltip=f"Boundary buffer: {buffer_km} km"
        ).add_to(m)

    if show_polygon_centroid:
        folium.Marker(
            location=[polygon_centroid_lat, polygon_centroid_lon],
            popup=f"Polygon centroid: {polygon_centroid_lat:.4f}, {polygon_centroid_lon:.4f}",
            tooltip="Polygon centroid",
            icon=folium.Icon(color='red', icon='map-marker')
        ).add_to(m)

    if show_circle:
        folium.GeoJson(
            mapping(bounding_circle),
            style_function=lambda x: {
                'fillColor': 'purple', 'color': 'purple',
                'weight': 2, 'fillOpacity': 0.1,
                'dashArray': '5 5'
            },
            tooltip=f"Bounding circle: ± {bounding_radius_mi:.1f} mi"
        ).add_to(m)

    if show_uncertainty_centroid:
        folium.Marker(
            location=[uncertainty_centroid_lat, uncertainty_centroid_lon],
            popup=f"Area extent centroid: {uncertainty_centroid_lat:.4f}, {uncertainty_centroid_lon:.4f}",
            tooltip="Area extent centroid (MBC)",
            icon=folium.Icon(color='orange', icon='map-marker')
        ).add_to(m)

    map_data = st_folium(m, width=800, height=550, key="np_map")
    if map_data and map_data.get('center'):
        st.session_state.np_map_center = [map_data['center']['lat'], map_data['center']['lng']]
    if map_data and map_data.get('zoom'):
        st.session_state.np_map_zoom = map_data['zoom']

    st.markdown("test")

with col2:
    st.subheader("🎯 Original Locality")
    st.markdown(f"<span style='font-size:24px'>{LOCALITY_STRING}</span>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    st.subheader("📊 Summary")
    st.markdown(f"<span style='font-size:20px'>**Feature:**<br>&emsp;{FEATURE_NAME}</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:20px'>**Feature Point/Centroid:**<br>&emsp;{polygon_centroid_lat:.4f}, {polygon_centroid_lon:.4f}</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:20px'>**GeoNames ID:**<br>&emsp;[{GEONAMEID}](https://www.geonames.org/{GEONAMEID})</span>", unsafe_allow_html=True)
    #st.markdown(f"<span style='font-size:20px'>**Feature Type:** {FEATURE_TYPE}</span>", unsafe_allow_html=True)
    
    st.divider()

    st.markdown(f"<span style='font-size:20px'>**Representative Point:**<br>&emsp;{center_lat:.4f}, {center_lon:.4f}</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:20px'>**Uncertainty Buffer Radius:**<br>&emsp;± {bounding_radius_mi:.1f} mi (± {bounding_radius_km:.1f} km)</span>", unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(f"<span style='font-size:18px'>**User-Selected Uncertainty Type:**<br>&emsp;{uncertainty_type}</span>", unsafe_allow_html=True)
    if buffer_km > 0:
        st.markdown(f"<span style='font-size:18px'>**User-Selected Exterior Buffer Distance:**<br>&emsp;{buffer_km} km</span>", unsafe_allow_html=True)

with col3:
    st.subheader("🌐 Darwin Core Output")
    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("#### Centroid")
    st.markdown(f"<span style='font-size:15px'>**decimalLatitude:** {center_lat:.6f}</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:15px'>**decimalLongitude:** {center_lon:.6f}</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:15px'>**coordinateUncertaintyInMeters:** {bounding_radius_m:.0f}</span>", unsafe_allow_html=True)
    st.divider()
    st.markdown("#### Footprint")
    footprint_wkt = footprint_shape.wkt
    wkt_display = footprint_wkt[:200] + "..." if len(footprint_wkt) > 200 else footprint_wkt
    st.markdown(f"<span style='font-size:15px'>**footprintWKT:** {wkt_display}</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:15px'>**footprintSRS:** EPSG:4326</span>", unsafe_allow_html=True)
    st.divider()
    remarks = f"{uncertainty_type.lower()}"
    if buffer_km > 0:
        remarks += f", {buffer_km} km buffer"
    st.markdown("#### Metadata")
    st.markdown(f"<span style='font-size:13px'>**georeferenceRemarks:** {remarks}</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:13px'>**georeferenceSources:** GeoNames, OSM</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:13px'>**georeferencedBy:** Chain of Flowers pipeline</span>", unsafe_allow_html=True)
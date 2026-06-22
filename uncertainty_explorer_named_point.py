import streamlit as st
import folium
from streamlit_folium import st_folium
import math
from shapely.geometry import mapping, Polygon
from shapely import wkt
import numpy as np
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from geopy.distance import geodesic
from geopy import Point as GeoPoint

st.set_page_config(layout="wide", page_title="Chain of Flowers — Named Point Uncertainty")

st.title("🌸 Uncertainty Explorer · Named Point Buffer Locality")
st.markdown("*Demonstrating honest spatial uncertainty representation for named point locality strings*")

# --- default values from Peggys Cove record (Nova Scotia) ---
DEFAULT_LAT = 44.4929
DEFAULT_LON = -63.91611
FEATURE_NAME = "Peggys Cove"
LOCALITY_STRING = "Peggys Cove"
GEONAMEID = 6100559

# A point-based named locality carries NO inherent geographic extent, so the
# uncertainty radius is an explicit, adjustable assumption about the apparent
# scale of the place — not a measured value. We collapse the messy range of
# GeoNames feature types into a few clear scale buckets rather than implying a
# one-size-fits-all answer.
SIZE_CATEGORIES = [
    {"key": "pinpoint", "label": "Pinpoint  ·  ~1 km", "radius_km": 1,
     "desc": "A small, sharply-defined feature — a rock, spring, or single building."},
    {"key": "local", "label": "Local  ·  ~2 km", "radius_km": 2,
     "desc": "A hamlet, named locality, or small community (e.g. Peggys Cove)."},
    {"key": "town", "label": "Town-scale  ·  ~5 km", "radius_km": 5,
     "desc": "A town, or a named area spanning a few kilometres."},
    {"key": "broad", "label": "Broad  ·  ~10 km", "radius_km": 10,
     "desc": "A large or loosely-defined named place with substantial extent."},
]
DEFAULT_CATEGORY_INDEX = 1  # Peggys Cove reads as local-scale
KM_TO_MI = 1 / 1.60934


def geodesic_buffer(lat, lon, radius_km, n_points=64):
    """Create a geodesic circular buffer polygon around a point.

    Mirrors geometry.geodesic_buffer so the explorer matches pipeline output.
    """
    angles = np.linspace(0, 360, n_points, endpoint=False)
    anchor = GeoPoint(lat, lon)
    coords = []
    for bearing in angles:
        pt = geodesic(kilometers=radius_km).destination(anchor, bearing)
        coords.append((pt.longitude, pt.latitude))
    coords.append(coords[0])
    return Polygon(coords)


# preserve map state
if 'pt_map_center' not in st.session_state:
    st.session_state.pt_map_center = [DEFAULT_LAT, DEFAULT_LON]
if 'pt_map_zoom' not in st.session_state:
    st.session_state.pt_map_zoom = 11

# --- sidebar controls ---
st.sidebar.title("🛠️Controls")

category_labels = [c["label"] for c in SIZE_CATEGORIES]
choice = st.sidebar.radio(
    "Assumed scale of the named place",
    options=category_labels,
    index=DEFAULT_CATEGORY_INDEX,
    help="A point-based locality has no inherent extent — this is an explicit "
         "assumption about the scale of the place, not a measured value."
)
category = next(c for c in SIZE_CATEGORIES if c["label"] == choice)
base_radius_km = category["radius_km"]
st.sidebar.caption(category["desc"])

st.sidebar.divider()
st.sidebar.markdown("**Display Options**")
show_buffer = st.sidebar.toggle("Show Uncertainty Buffer", value=True)
show_anchor = st.sidebar.toggle("Show Anchor Point", value=True)

# default radius from feature type unless overridden by bonus control
radius_km = base_radius_km

st.sidebar.divider()
show_bonus = st.sidebar.toggle("Show Bonus Controls", value=False)

if show_bonus == True:

    radius_km = st.sidebar.slider(
        "Uncertainty Radius (km)",
        min_value=1,
        max_value=50,
        value=base_radius_km,
        step=1,
        help="Override the feature-type default radius"
    )

# --- calculations ---
radius_m = radius_km * 1000
radius_mi = radius_km * KM_TO_MI

buffer_shape = geodesic_buffer(DEFAULT_LAT, DEFAULT_LON, radius_km)
buffer_geojson = mapping(buffer_shape)

# --- map ---
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    m = folium.Map(
        location=st.session_state.pt_map_center,
        zoom_start=st.session_state.pt_map_zoom
    )

    # uncertainty buffer
    if show_buffer and buffer_geojson:
        folium.GeoJson(
            buffer_geojson,
            style_function=lambda x: {
                'fillColor': 'blue', 'color': 'blue',
                'weight': 2, 'fillOpacity': 0.25
            },
            tooltip=f"Uncertainty buffer: ± {radius_mi:.1f} mi ({radius_km} km)"
        ).add_to(m)

    # anchor point
    if show_anchor:
        folium.Marker(
            location=[DEFAULT_LAT, DEFAULT_LON],
            popup=f"Anchor: {FEATURE_NAME}",
            tooltip=FEATURE_NAME,
            icon=folium.Icon(color='red', icon='map-marker')
        ).add_to(m)

    map_data = st_folium(m, width=800, height=550, key="buffer_map")
    if map_data and map_data.get('center'):
        st.session_state.pt_map_center = [map_data['center']['lat'], map_data['center']['lng']]
    if map_data and map_data.get('zoom'):
        st.session_state.pt_map_zoom = map_data['zoom']

with col2:
    st.subheader("🎯 Original Locality")
    st.markdown(f"<span style='font-size:24px'>{LOCALITY_STRING}</span>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    if radius_km != base_radius_km:
        st.markdown(f"<span style='font-size:20px'>**User-Modified Radius:**<br>&emsp;{radius_km} km (feature default {base_radius_km} km)</span>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    st.subheader("📊 Summary")
    st.markdown(f"<span style='font-size:20px'>**Feature:**<br>&emsp;{FEATURE_NAME}</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:20px'>**Feature Point/Centroid:**<br>&emsp;{DEFAULT_LAT:.4f}, {DEFAULT_LON:.4f}</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:20px'>**GeoNames ID:**<br>&emsp;[{GEONAMEID}](https://www.geonames.org/{GEONAMEID})</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:20px'>**Assumed Scale:**<br>&emsp;{category['label']}</span>", unsafe_allow_html=True)

    st.divider()

    st.markdown(f"<span style='font-size:20px'>**Representative Point:**<br>&emsp;{DEFAULT_LAT:.4f}, {DEFAULT_LON:.4f}</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:20px'>**Uncertainty Buffer Radius:**<br>&emsp;± {radius_mi:.1f} mi (± {radius_km:.1f} km)</span>", unsafe_allow_html=True)
    st.caption("A point has no inherent extent — this radius is an assumed scale, adjustable, not a measured value.")

with col3:
    st.subheader("🌐 Darwin Core Output")
    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("#### Representative Point")
    st.markdown(f"<span style='font-size:15px'>**decimalLatitude:** {DEFAULT_LAT:.6f}</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:15px'>**decimalLongitude:** {DEFAULT_LON:.6f}</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:15px'>**coordinateUncertaintyInMeters:** {radius_m:.0f}</span>", unsafe_allow_html=True)

    st.divider()

    st.markdown("#### Buffer Footprint")
    buffer_wkt = buffer_shape.wkt
    buffer_wkt_display = buffer_wkt[:200] + "..." if len(buffer_wkt) > 200 else buffer_wkt
    st.markdown(f"<span style='font-size:15px'>**footprintWKT:** {buffer_wkt_display}</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:15px'>**footprintSRS:** EPSG:4326</span>", unsafe_allow_html=True)

    st.divider()

    st.markdown("##### Additional Metadata")
    st.markdown(f"<span style='font-size:13px'>**georeferenceRemarks:** named point, ~{radius_km}km assumed buffer ({category['key']}-scale)</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:13px'>**georeferenceSources:** GeoNames, OSM</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:13px'>**georeferencedBy:** Chain of Flowers pipeline</span>", unsafe_allow_html=True)

"""Small geometry helpers (miles, WGS84 sphere)."""
import numpy as np

EARTH_RADIUS_MILES = 3958.7613
METERS_PER_MILE = 1609.344


def to_xyz(lat, lon):
    """lat/lon in degrees -> 3D points in miles on a sphere.

    Euclidean (chord) distance between these points is an accurate stand-in for
    great-circle distance at the scales we care about, and lets us use a KD-tree.
    """
    lat = np.radians(np.asarray(lat, dtype=float))
    lon = np.radians(np.asarray(lon, dtype=float))
    c = np.cos(lat)
    return EARTH_RADIUS_MILES * np.column_stack((c * np.cos(lon), c * np.sin(lon), np.sin(lat)))


def haversine_miles(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))


def cumulative_miles(lons, lats):
    """Cumulative distance along a polyline, starting at 0."""
    lons = np.asarray(lons, dtype=float)
    lats = np.asarray(lats, dtype=float)
    seg = haversine_miles(lats[:-1], lons[:-1], lats[1:], lons[1:])
    return np.concatenate(([0.0], np.cumsum(seg)))


def in_usa_bbox(lat, lon):
    """Rough bounding boxes: contiguous US, Alaska, Hawaii."""
    return (
        (24.0 <= lat <= 49.6 and -125.5 <= lon <= -66.5)
        or (51.0 <= lat <= 71.6 and -170.0 <= lon <= -129.0)
        or (18.5 <= lat <= 22.5 and -161.0 <= lon <= -154.5)
    )

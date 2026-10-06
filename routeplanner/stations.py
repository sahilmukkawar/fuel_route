"""In-memory index of fuel stations (loaded once per process)."""
import csv
import functools
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from .geo import to_xyz

STATIONS_CSV = Path(__file__).resolve().parent / "data" / "stations.csv"


@dataclass(frozen=True)
class Station:
    id: int
    name: str
    address: str
    city: str
    state: str
    lat: float
    lon: float
    price: float  # USD per gallon


class StationIndex:
    def __init__(self, stations):
        self.stations = stations
        self.prices = np.array([s.price for s in stations])
        self.xyz = to_xyz([s.lat for s in stations], [s.lon for s in stations])

    def along_route(self, route_xyz, route_miles, corridor_miles):
        """Stations within `corridor_miles` of the route.

        Returns a list of (mile_marker, off_route_miles, Station) sorted by mile marker.
        One KD-tree query for all stations: O(S log R), a few ms for ~7.5k stations.
        """
        tree = cKDTree(route_xyz)
        dist, idx = tree.query(self.xyz, distance_upper_bound=corridor_miles)
        hit = np.isfinite(dist)
        found = [
            (float(route_miles[idx[i]]), float(dist[i]), self.stations[i]) for i in np.flatnonzero(hit)
        ]
        found.sort(key=lambda t: t[0])
        return found


@functools.lru_cache(maxsize=1)
def get_station_index():
    stations = []
    with open(STATIONS_CSV, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            stations.append(
                Station(
                    id=int(row["id"]),
                    name=row["name"],
                    address=row["address"],
                    city=row["city"],
                    state=row["state"],
                    lat=float(row["lat"]),
                    lon=float(row["lon"]),
                    price=float(row["price"]),
                )
            )
    return StationIndex(stations)

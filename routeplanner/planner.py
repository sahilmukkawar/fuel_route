"""Orchestrates: resolve locations -> one route call -> find stations -> optimise."""
import time

import numpy as np
from django.conf import settings

from .clients import ApiCallCounter, fetch_route, resolve_location
from .geo import cumulative_miles, to_xyz
from .optimizer import InfeasibleRoute, plan_fuel_stops
from .stations import get_station_index


def build_plan(start_text, finish_text, *, include_geometry=True, start_fuel_miles=None):
    t0 = time.perf_counter()
    cfg = settings.FUEL_PLANNER
    counter = ApiCallCounter()

    s_lat, s_lon, s_label = resolve_location(start_text, counter)
    f_lat, f_lon, f_label = resolve_location(finish_text, counter)
    coords, osrm_miles, duration_s = fetch_route(
        (s_lat, s_lon), (f_lat, f_lon), counter
    )

    lons = np.array([c[0] for c in coords])
    lats = np.array([c[1] for c in coords])
    miles = cumulative_miles(lons, lats)
    if miles[-1] > 0:
        miles *= osrm_miles / miles[-1]  # align with the routing engine's own distance
    route_xyz = to_xyz(lats, lons)
    total_miles = float(miles[-1])

    index = get_station_index()
    mpg, max_range = cfg["MPG"], cfg["MAX_RANGE_MILES"]

    stops = None
    used_corridor = None
    for corridor in cfg["CORRIDOR_MILES_STEPS"]:
        candidates = index.along_route(route_xyz, miles, corridor)
        try:
            stops, _ = plan_fuel_stops(
                candidates, total_miles, max_range=max_range, mpg=mpg, start_fuel_miles=start_fuel_miles,
                min_saving=cfg["MIN_PRICE_SAVING_PER_GALLON"],
                min_leg_miles=cfg["MIN_LEG_MILES"],
            )
            used_corridor = corridor
            break
        except InfeasibleRoute as exc:
            last_error = exc
    if stops is None:
        raise last_error

    stop_payload = []
    for i, s in enumerate(stops, 1):
        st = s.station
        stop_payload.append(
            {
                "stop": i,
                "station_id": st.id,
                "name": st.name,
                "address": st.address,
                "city": st.city,
                "state": st.state,
                "location": {"lat": st.lat, "lon": st.lon},
                "price_per_gallon": round(st.price, 4),
                "mile_marker": round(s.mile, 1),
                "approx_miles_off_route": round(s.off_route_miles, 1),
                "gallons_purchased": round(s.gallons, 2),
                "cost": round(s.cost, 2),
            }
        )

    gallons_total = total_miles / mpg
    bought = sum(s.gallons for s in stops)
    result = {
        "start": {"query": start_text, "resolved": s_label, "lat": s_lat, "lon": s_lon},
        "finish": {"query": finish_text, "resolved": f_label, "lat": f_lat, "lon": f_lon},
        "total_distance_miles": round(total_miles, 1),
        "estimated_drive_hours": round(duration_s / 3600, 1),
        "vehicle": {"max_range_miles": max_range, "mpg": mpg, "tank_gallons": max_range / mpg},
        "fuel_stops": stop_payload,
        "summary": {
            "total_fuel_cost": round(sum(s.cost for s in stops), 2),
            "gallons_purchased": round(bought, 2),
            "trip_fuel_gallons": round(gallons_total, 2),
            "assumption": "Vehicle departs with a full tank (not billed); the plan buys only the fuel "
            "needed to arrive with an empty tank at the lowest possible cost.",
        },
        "meta": {
            "corridor_miles_used": used_corridor,
            "candidate_stations_in_corridor": len(candidates),
            "external_api_calls": {"routing": counter.routing, "geocoding": counter.geocoding},
            "compute_ms": round((time.perf_counter() - t0) * 1000, 1),
        },
    }
    if include_geometry:
        result["route"] = {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "LineString",
                "coordinates": [[round(x, 5), round(y, 5)] for x, y in coords],
            },
        }
    return result

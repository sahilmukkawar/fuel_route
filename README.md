# Fuel Route API (Django 6.1)

`GET /api/route/?start=...&finish=...` returns the driving route between two USA locations, the
cost-optimal fuel stops along it (500-mile range, 10 mpg) and the total money spent on fuel.
Open `/` for the dashboard: a search form, the route on a map, the cost breakdown, and two charts
showing why those stops were chosen.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate     # Python 3.12+
pip install -r requirements.txt
python manage.py runserver
python manage.py test routeplanner
```

Then open <http://127.0.0.1:8000/>.

No database or API key needed. `routeplanner/data/stations.csv` is already built; regenerate it with
`python manage.py build_stations` (see "Data" below).

## Dashboard

`/` (and `/map/`) serve one page, which calls the API itself:

- **Form** for start, finish and how much range is in the tank at departure. Submitting rewrites the
  query string, so any result stays a shareable link and the back button works.
- **Map** with the route, the chosen stops, and every station the planner considered (toggleable).
- **Fuel price along the route** plots each corridor station by price and mile marker, with the chosen
  stops marked and numbered: a cheap cluster being used, and an expensive stretch skipped, are visible
  at a glance.
- **Fuel in tank** plots the tank draining and refilling, which is what makes the greedy strategy legible.

No build step: one template, vanilla JS, Leaflet from a CDN, charts drawn as inline SVG. Light and dark.

## API

| Param | Required | Notes |
|---|---|---|
| `start`, `finish` | yes | Free text (`"Dallas, TX"`) **or** `lat,lon` (`"32.78,-96.80"`) |
| `include_geometry` | no | `false` drops the route GeoJSON (~375 KB for a coast-to-coast trip) |
| `start_fuel_miles` | no | Range in the tank at departure, default 500 (full) |
| `include_candidates` | no | `true` adds `candidates[]`, every station in the search corridor (what the dashboard charts) |

```
GET /api/route/?start=Los Angeles, CA&finish=New York, NY
GET /api/route/?start=34.05,-118.24&finish=40.71,-74.01        # zero geocoding calls
```

Response (abridged): `total_distance_miles`, `route` (GeoJSON LineString), `fuel_stops[]`
(name, address, city, state, lat/lon, `price_per_gallon`, `mile_marker`, `gallons_purchased`, `cost`),
`summary.total_fuel_cost`, `map_url`, and `meta` with the number of external API calls and compute time.

Errors are JSON `{"error": "..."}`: 400 bad input / outside the USA, 422 no route or infeasible fuel plan,
502 upstream service problem.

## How it works

1. **Routing: one OSRM call** (`router.project-osrm.org`, free, no key) with `overview=full&geometries=geojson`.
   Coordinates as input = 1 external call. Text input adds one Nominatim geocode per place (cached),
   so worst case is 3 calls. Routes and geocodes are cached for an hour.
2. **Station lookup:** the ~6.6k stations are loaded once into memory with a KD-tree query over the route
   points (3D coordinates, so distances are great-circle accurate). All stations within a corridor of the route
   are found in one vectorised query, each with its mile marker along the route.
3. **Optimisation:** the classic gas-station greedy, which is optimal for minimum cost (verified against an
   exact DP in the tests). At each stop it looks at what is reachable on a full tank: go to the nearest
   cheaper station buying only what is needed; if the destination is reachable, buy just enough to arrive
   empty; otherwise fill up and go to the cheapest station in range.
4. Two small practical rules keep results sensible: a station must be at least `$0.05/gal` cheaper
   to be worth steering towards, and hops should be at least 100 miles when possible
   (no 0.8-gallon top-ups). On a 2,885-mile test route this cost about 2% more than the strictly optimal plan
   with 9 stops instead of 17. Set both to `0` in `settings.FUEL_PLANNER` for the strict optimum.

Typical compute time (everything after the routing call) is about 5 ms; most of the remaining response time
is serialising the route geometry.

## Data

The CSV has no coordinates, so `build_stations` geocodes each station to its **city centroid** using the
public [US-Cities-Database](https://github.com/kelvins/US-Cities-Database) (offline, zero per-request API calls).
It also drops 620 Canadian rows, collapses duplicate OPIS IDs (keeping the cheapest listed price) and drops 5
unmatched rows. Result: 6,623 stations.

## Assumptions and limitations (worth saying in the Loom)

- The vehicle **departs with a full tank that is not billed**, so `total_fuel_cost` is the money spent at stops.
  Trips under 500 miles therefore cost $0. `start_fuel_miles` lets you change the starting range
  (e.g. `start_fuel_miles=100`), but the vehicle must be able to reach a first station with it.
- Station positions are city centroids, so `approx_miles_off_route` is an estimate. The planner searches a
  10-mile corridor and widens to 25 then 50 miles only if a leg would otherwise be infeasible.
- The public OSRM server is a demo service with no SLA. Point `OSRM_BASE_URL` at your own OSRM instance
  or swap `clients.fetch_route` for OpenRouteService for production.
- In-process cache (LocMem); use Redis behind multiple workers.
"# fuel_route" 

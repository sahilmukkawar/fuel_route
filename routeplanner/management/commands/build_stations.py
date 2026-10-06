"""Build routeplanner/data/stations.csv from the raw OPIS fuel price CSV.

The raw file has no coordinates, so each station is geocoded to its city centroid using a
public US cities dataset (offline, no per-request API calls). Cleaning rules:
  * drop non-US rows (the file contains Canadian provinces)
  * collapse duplicate OPIS Truckstop IDs, keeping the cheapest listed price
  * drop stations whose city cannot be matched

    python manage.py build_stations --cities /path/to/us_cities.csv

Cities dataset: https://github.com/kelvins/US-Cities-Database (csv/us_cities.csv)
"""
import csv
import re
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

CITIES_URL = "https://raw.githubusercontent.com/kelvins/US-Cities-Database/main/csv/us_cities.csv"
ABBREV = [(r"\bst\.?\b", "saint"), (r"\bmt\.?\b", "mount"), (r"\bft\.?\b", "fort")]


def norm(text):
    t = str(text).lower().strip()
    for pat, rep in ABBREV:
        t = re.sub(pat, rep, t)
    t = re.sub(r"[^a-z0-9 ]", "", t)
    return re.sub(r"\s+", " ", t)


class Command(BaseCommand):
    help = "Geocode and de-duplicate the raw fuel price CSV into routeplanner/data/stations.csv"

    def add_arguments(self, parser):
        parser.add_argument("--raw", default=str(Path(settings.BASE_DIR) / "data" / "fuel-prices-for-be-assessment.csv"))
        parser.add_argument("--cities", help="Path to us_cities.csv (downloaded from GitHub if omitted)")
        parser.add_argument("--out", default=str(Path(settings.BASE_DIR) / "routeplanner" / "data" / "stations.csv"))

    def handle(self, *args, **opts):
        cities_path = opts["cities"]
        if not cities_path:
            cities_path = "/tmp/us_cities.csv"
            self.stdout.write(f"Downloading {CITIES_URL}")
            urllib.request.urlretrieve(CITIES_URL, cities_path)

        centroids = {}
        with open(cities_path, newline="", encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                key = (norm(r["CITY"]), r["STATE_CODE"])
                centroids.setdefault(key, (float(r["LATITUDE"]), float(r["LONGITUDE"])))
        us_states = {k[1] for k in centroids}
        # Common spelling variants / unincorporated places in the raw file.
        aliases = {
            ("port wentworth", "GA"): ("savannah", "GA"),
            ("elizabethport", "NJ"): ("elizabeth", "NJ"),
            ("brookpark", "OH"): ("brook park", "OH"),
            ("henrico", "VA"): ("richmond", "VA"),
            ("university park", "IL"): ("university park", "IL"),
            ("evergreen", "AL"): ("evergreen", "AL"),
        }

        best = {}  # OPIS id -> row
        total = non_us = unmatched = 0
        with open(opts["raw"], newline="", encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                total += 1
                state = r["State"].strip()
                if state not in us_states:
                    non_us += 1
                    continue
                key = (norm(r["City"]), state)
                coord = centroids.get(key) or centroids.get(aliases.get(key, ("", "")))
                if not coord:
                    unmatched += 1
                    continue
                sid = int(r["OPIS Truckstop ID"])
                price = float(r["Retail Price"])
                if sid not in best or price < best[sid]["price"]:
                    best[sid] = {
                        "id": sid,
                        "name": r["Truckstop Name"].strip(),
                        "address": re.sub(r"\s+", " ", r["Address"]).strip(),
                        "city": r["City"].strip(),
                        "state": state,
                        "lat": round(coord[0], 5),
                        "lon": round(coord[1], 5),
                        "price": round(price, 4),
                    }

        out = Path(opts["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["id", "name", "address", "city", "state", "lat", "lon", "price"])
            w.writeheader()
            w.writerows(sorted(best.values(), key=lambda x: x["id"]))
        if not best:
            raise CommandError("No stations written - check input files")
        self.stdout.write(
            self.style.SUCCESS(
                f"rows={total} non_us={non_us} unmatched={unmatched} unique_stations={len(best)} -> {out}"
            )
        )

from unittest import mock

import numpy as np
from django.core.cache import cache
from django.test import SimpleTestCase

from .geo import METERS_PER_MILE, haversine_miles
from .optimizer import InfeasibleRoute, plan_fuel_stops
from .stations import Station


def st(price, i=0):
    return Station(i, f"S{i}", "addr", "City", "TX", 0.0, 0.0, price)


def cand(mile, price, i=0):
    return (mile, 0.0, st(price, i))


class OptimizerTests(SimpleTestCase):
    kw = dict(max_range=500, mpg=10)

    def test_short_trip_needs_no_stops(self):
        stops, cost = plan_fuel_stops([cand(100, 3.0)], 300, **self.kw)
        self.assertEqual(stops, [])
        self.assertEqual(cost, 0)

    def test_buys_only_enough_to_reach_destination(self):
        # 800-mile trip, full tank at start. Cheapest station at mile 300.
        stops, cost = plan_fuel_stops([cand(100, 4.0, 1), cand(300, 3.0, 2)], 800, **self.kw)
        self.assertEqual([s.station.id for s in stops], [2])
        # arrive at 300 with 20 gal, need 50 more to cover remaining 500 miles... buy 30 gal
        self.assertAlmostEqual(stops[0].gallons, 30, places=6)
        self.assertAlmostEqual(cost, 90.0, places=6)

    def test_fills_up_at_cheap_station_before_expensive_stretch(self):
        # Cheap station at 200, only expensive ones later -> fill up fully at the cheap one.
        cands = [cand(200, 2.5, 1), cand(600, 4.5, 2), cand(650, 4.6, 3)]
        stops, cost = plan_fuel_stops(cands, 1000, **self.kw)
        self.assertEqual(stops[0].station.id, 1)
        # arrives with 30 gal, fills to 50 -> buys 20 gal at 2.50
        self.assertAlmostEqual(stops[0].gallons, 20, places=6)

    def test_never_exceeds_tank_capacity_and_arrives_with_nonnegative_fuel(self):
        rng = np.random.default_rng(1)
        miles = np.sort(rng.uniform(10, 2900, 80))
        cands = [cand(float(m), float(rng.uniform(2.8, 4.5)), i) for i, m in enumerate(miles)]
        stops, _ = plan_fuel_stops(cands, 3000, **self.kw)
        fuel, pos = 50.0, 0.0
        for s in stops:
            fuel -= (s.mile - pos) / 10
            self.assertGreaterEqual(fuel, -1e-6)
            fuel += s.gallons
            self.assertLessEqual(fuel, 50 + 1e-6)
            pos = s.mile
        self.assertGreaterEqual(fuel - (3000 - pos) / 10, -1e-6)

    def test_matches_brute_force_on_small_cases(self):
        # Compare greedy to an exhaustive DP over (station, fuel in 1-gallon units).
        rng = np.random.default_rng(7)
        for _ in range(30):
            k = int(rng.integers(3, 9))
            miles = sorted(set(int(x) for x in rng.integers(20, 1400, k)))
            prices = [round(float(rng.uniform(2.8, 4.5)), 2) for _ in miles]
            cands = [cand(float(m), p, i) for i, (m, p) in enumerate(zip(miles, prices))]
            total = 1500.0
            try:
                _, greedy = plan_fuel_stops(cands, total, **self.kw)
            except InfeasibleRoute:
                continue
            self.assertAlmostEqual(greedy, self._dp(miles, prices, total), places=4)

    @staticmethod
    def _dp(miles, prices, total):
        """Exact DP: state = (node, fuel in miles); integer miles so the grid is exact."""
        INF = float("inf")
        pos = [0] + list(miles) + [int(total)]
        price = [0.0] + list(prices) + [0.0]
        cap = 500
        cost = [dict() for _ in pos]
        cost[0][cap] = 0.0
        for i in range(len(pos)):
            row = cost[i]
            if 0 < i < len(pos) - 1:  # may buy fuel at stations (1 mile of fuel at a time)
                for f in range(cap):
                    if f in row:
                        v = row[f] + price[i] / 10
                        if v < row.get(f + 1, INF):
                            row[f + 1] = v
            if i == len(pos) - 1:
                return min(row.values()) if row else INF
            gap = pos[i + 1] - pos[i]
            for f, c in row.items():
                if f >= gap and c < cost[i + 1].get(f - gap, INF):
                    cost[i + 1][f - gap] = c
        return INF

    def test_relaxed_plan_has_fewer_stops_for_a_bounded_cost_increase(self):
        rng = np.random.default_rng(3)
        miles = np.sort(rng.uniform(5, 2900, 120))
        cands = [cand(float(m), float(rng.uniform(2.9, 3.6)), i) for i, m in enumerate(miles)]
        strict, c1 = plan_fuel_stops(cands, 3000, **self.kw)
        relaxed, c2 = plan_fuel_stops(cands, 3000, min_saving=0.05, min_leg_miles=100, **self.kw)
        self.assertLessEqual(len(relaxed), len(strict))
        self.assertGreaterEqual(c2, c1 - 1e-6)           # strict is optimal
        self.assertLess(c2 - c1, 0.15 * 300)             # but the relaxed plan stays close

    def test_infeasible_gap(self):
        with self.assertRaises(InfeasibleRoute):
            plan_fuel_stops([cand(100, 3.0)], 1000, **self.kw)


class ApiTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def _fake_route(self):
        # Straight line Dallas -> Chicago-ish, ~800 miles, dense points
        a, b = (32.78, -96.80), (41.88, -87.63)
        t = np.linspace(0, 1, 800)
        coords = [[a[1] + (b[1] - a[1]) * x, a[0] + (b[0] - a[0]) * x] for x in t]
        d = float(haversine_miles(a[0], a[1], b[0], b[1])) * 1.1
        return coords, d, d / 60 * 3600

    def test_end_to_end_with_mocked_routing(self):
        with mock.patch("routeplanner.planner.fetch_route", return_value=self._fake_route()) as m:
            r = self.client.get("/api/route/", {"start": "32.78,-96.80", "finish": "41.88,-87.63"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(m.call_count, 1)
        self.assertGreater(data["total_distance_miles"], 700)
        self.assertGreaterEqual(len(data["fuel_stops"]), 1)
        self.assertAlmostEqual(
            data["summary"]["total_fuel_cost"], sum(s["cost"] for s in data["fuel_stops"]), places=1
        )
        self.assertEqual(data["route"]["geometry"]["type"], "LineString")
        self.assertIn("/map/?", data["map_url"])

    def test_missing_params(self):
        self.assertEqual(self.client.get("/api/route/").status_code, 400)

    def test_outside_usa(self):
        r = self.client.get("/api/route/", {"start": "51.5,-0.12", "finish": "41.88,-87.63"})
        self.assertEqual(r.status_code, 400)

    def test_map_page(self):
        r = self.client.get("/map/", {"start": "a", "finish": "b"})
        self.assertEqual(r.status_code, 200)

"""Cost-optimal refuelling along a 1-D route.

Classic "gas station problem": given stations at mile markers with prices, a tank that
holds `capacity` gallons and a fixed burn rate, minimise money spent. The greedy rule
below is optimal for this problem:

  at each stop, look at every station reachable on a full tank
    * if a cheaper one exists, buy only enough to reach the nearest cheaper one
    * else if the destination is reachable, buy only enough to get there and finish
    * else fill the tank and go to the cheapest station in range

Fuel already in the tank at the start is treated as free (price 0).
"""
from dataclasses import dataclass

EPS = 1e-9


class InfeasibleRoute(Exception):
    """No sequence of stations lets the vehicle complete the trip."""


@dataclass
class Stop:
    mile: float
    off_route_miles: float
    station: object
    gallons: float
    cost: float


def plan_fuel_stops(candidates, total_miles, *, max_range, mpg, start_fuel_miles=None, min_saving=0.0, min_leg_miles=0.0):
    """candidates: list of (mile, off_route_miles, Station) sorted by mile.

    Returns (stops, total_cost). Raises InfeasibleRoute if a gap exceeds the range.

    min_saving: a station only counts as "cheaper" if it saves at least this many $/gal.
    0 gives the strictly cost-optimal plan; a few cents avoids pointless micro-stops
    (e.g. stopping to buy 0.8 gallons to save a cent) for a tiny, bounded cost increase.

    min_leg_miles: only hop to stations at least this far ahead (when any exist). Prevents
    chains of stops a few miles apart that each top up a fraction of a gallon.
    """
    threshold = max(EPS, min_saving)
    capacity = max_range / mpg
    fuel = (max_range if start_fuel_miles is None else min(start_fuel_miles, max_range)) / mpg
    pos = 0.0
    price_here = 0.0
    cur = -1  # index into candidates; -1 = trip start (not a station)
    stops, total_cost = [], 0.0
    n = len(candidates)

    while pos + fuel * mpg < total_miles - EPS:
        full_reach = pos + max_range
        in_range = []
        j = cur + 1
        while j < n and candidates[j][0] <= full_reach + EPS:
            in_range.append(j)
            j += 1

        far = [j for j in in_range if candidates[j][0] - pos >= min_leg_miles - EPS]
        cheaper = next((j for j in far if candidates[j][2].price < price_here - threshold), None)
        if cheaper is not None:
            target = cheaper
            buy = max(0.0, (candidates[target][0] - pos) / mpg - fuel)
        elif total_miles <= full_reach + EPS:
            target = None  # go straight to destination
            buy = max(0.0, (total_miles - pos) / mpg - fuel)
        else:
            if not in_range:
                raise InfeasibleRoute(f"No station within {max_range:.0f} miles after mile {pos:.1f}")
            # Cheapest in range; among equal prices prefer the farthest along the route.
            target = min(far or in_range, key=lambda j: (candidates[j][2].price, -candidates[j][0]))
            buy = capacity - fuel

        if buy > EPS and cur >= 0:
            m, off, st = candidates[cur]
            cost = buy * price_here
            stops.append(Stop(m, off, st, buy, cost))
            total_cost += cost
            fuel += buy

        if target is None:
            break
        fuel -= (candidates[target][0] - pos) / mpg
        pos = candidates[target][0]
        price_here = candidates[target][2].price
        cur = target

    return stops, total_cost

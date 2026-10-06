from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .clients import RoutingError
from .optimizer import InfeasibleRoute
from .planner import build_plan


def _error(message, status):
    return JsonResponse({"error": message}, status=status)


@require_GET
def route_plan(request):
    """GET /api/route/?start=<text or lat,lon>&finish=<text or lat,lon>

    Optional: include_geometry=false, start_fuel_miles=<0-500>
    """
    start = request.GET.get("start", "").strip()
    finish = request.GET.get("finish", "").strip()
    if not start or not finish:
        return _error("Both 'start' and 'finish' query parameters are required.", 400)

    start_fuel = None
    if "start_fuel_miles" in request.GET:
        try:
            start_fuel = float(request.GET["start_fuel_miles"])
        except ValueError:
            return _error("start_fuel_miles must be a number.", 400)
        if start_fuel < 0:
            return _error("start_fuel_miles must be >= 0.", 400)

    include_geometry = request.GET.get("include_geometry", "true").lower() != "false"

    try:
        plan = build_plan(start, finish, include_geometry=include_geometry, start_fuel_miles=start_fuel)
    except RoutingError as exc:
        return _error(str(exc), exc.status)
    except InfeasibleRoute as exc:
        return _error(f"No feasible fuel plan: {exc}", 422)

    plan["map_url"] = request.build_absolute_uri("/map/?" + request.GET.urlencode())
    return JsonResponse(plan, json_dumps_params={"indent": 2})


@require_GET
def route_map(request):
    """Interactive Leaflet map; fetches the JSON from /api/route/ with the same query string."""
    return render(request, "routeplanner/map.html", {"query": request.GET.urlencode()})

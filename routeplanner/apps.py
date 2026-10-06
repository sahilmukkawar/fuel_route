from django.apps import AppConfig


class RoutePlannerConfig(AppConfig):
    name = "routeplanner"

    def ready(self):
        # Warm the in-memory station index so the first request is fast.
        from .stations import get_station_index

        try:
            get_station_index()
        except FileNotFoundError:
            pass  # run `python manage.py build_stations` first

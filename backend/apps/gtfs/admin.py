"""Admin registrations for GTFS models.

Spatial models use ``GISModelAdmin`` (Django 4.0+) — renders an interactive
OpenStreetMap widget for PointField / LineStringField in the change view.
"""
from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import Agency, GTFSFeed, Route, Shape, Stop, StopTime, Trip


@admin.register(GTFSFeed)
class GTFSFeedAdmin(admin.ModelAdmin):
    list_display = (
        "feed_type",
        "imported_at",
        "routes_count",
        "stops_count",
        "trips_count",
        "stop_times_count",
        "zip_hash",
    )
    list_filter = ("feed_type",)
    search_fields = ("zip_hash",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Agency)
class AgencyAdmin(admin.ModelAdmin):
    list_display = ("agency_id", "name", "url", "timezone", "lang")
    search_fields = ("agency_id", "name")
    list_filter = ("lang", "timezone")


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ("route_id", "short_name", "long_name", "route_type", "agency")
    search_fields = ("route_id", "short_name", "long_name")
    list_filter = ("route_type", "agency")
    raw_id_fields = ("agency",)


@admin.register(Stop)
class StopAdmin(GISModelAdmin):
    list_display = ("stop_id", "name", "location_type")
    search_fields = ("stop_id", "name")
    list_filter = ("location_type",)


@admin.register(Shape)
class ShapeAdmin(GISModelAdmin):
    list_display = ("shape_id",)
    search_fields = ("shape_id",)


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = (
        "trip_id",
        "route",
        "headsign",
        "direction_id",
        "service_id",
        "shape",
    )
    search_fields = ("trip_id", "headsign", "service_id")
    list_filter = ("direction_id", "route__route_type")
    raw_id_fields = ("route", "shape")


@admin.register(StopTime)
class StopTimeAdmin(admin.ModelAdmin):
    list_display = ("trip", "stop_sequence", "stop", "arrival_time", "departure_time")
    search_fields = ("trip__trip_id", "stop__stop_id", "stop__name")
    # No list_filter: StopTime will hold millions of rows — filter UI would
    # force a DISTINCT over the full table on every page load.
    raw_id_fields = ("trip", "stop")
    ordering = ("trip", "stop_sequence")

"""DRF serializers for GTFS data.

Phase 1 preview uses simple {lat, lon} pairs for Stop (Leaflet-friendly);
only Shape uses proper GeoJSON via drf-gis (route-line rendering).
"""
from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer

from apps.gtfs.models import Agency, Route, Shape, Stop, Trip


class AgencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Agency
        fields = ["id", "agency_id", "name", "url", "timezone", "lang"]


class RouteSerializer(serializers.ModelSerializer):
    agency = AgencySerializer(read_only=True)
    route_type_label = serializers.CharField(
        source="get_route_type_display", read_only=True
    )

    class Meta:
        model = Route
        fields = [
            "id", "route_id", "agency",
            "short_name", "long_name",
            "route_type", "route_type_label",
            "color", "text_color",
        ]


class StopSerializer(serializers.ModelSerializer):
    lat = serializers.SerializerMethodField()
    lon = serializers.SerializerMethodField()

    class Meta:
        model = Stop
        fields = ["id", "stop_id", "name", "lat", "lon", "location_type"]

    def get_lat(self, obj):
        return obj.location.y

    def get_lon(self, obj):
        return obj.location.x


class ShapeGeoJSONSerializer(GeoFeatureModelSerializer):
    """GeoJSON Feature for route-shape endpoint.

    Leaflet L.geoJSON() consumes this directly.
    """

    class Meta:
        model = Shape
        geo_field = "geometry"
        fields = ["id", "shape_id"]


_INVERSE_MODE_BY_RT = {0: "tram", 4: "ferry", 7: "funicular"}


class TripActiveSerializer(serializers.ModelSerializer):
    """Faz 5 /api/trips/active/ payload (flat trip + stop_times)."""

    mode = serializers.SerializerMethodField()
    route_id = serializers.CharField(source="route.route_id")
    route_short_name = serializers.CharField(source="route.short_name")
    route_long_name = serializers.CharField(source="route.long_name")
    shape_id = serializers.SerializerMethodField()
    stop_times = serializers.SerializerMethodField()

    class Meta:
        model = Trip
        fields = [
            "trip_id", "route_id", "route_short_name", "route_long_name",
            "shape_id", "direction_id", "headsign", "mode", "stop_times",
        ]

    def get_mode(self, obj):
        rt = obj.route.route_type
        short = (obj.route.short_name or "").lower()
        if rt == 1:
            return "marmaray" if short.startswith("marmaray") else "metro"
        return _INVERSE_MODE_BY_RT.get(rt, "unknown")

    def get_shape_id(self, obj):
        return obj.shape.shape_id if obj.shape_id else None

    def get_stop_times(self, obj):
        # Discovery: arrival_time is timedelta — serialize as int seconds.
        # StopTime.Meta.ordering already includes stop_sequence, so the
        # prefetched list arrives in order. lat/lon embedded for frontend
        # stop projection (KM3-a) — saves a separate /api/stops/ batch fetch.
        return [
            {
                "stop_id": st.stop.stop_id,
                "sequence": st.stop_sequence,
                "arrival_seconds": int(st.arrival_time.total_seconds()),
                "lat": st.stop.location.y,
                "lon": st.stop.location.x,
            }
            for st in obj.stop_times.all()
        ]

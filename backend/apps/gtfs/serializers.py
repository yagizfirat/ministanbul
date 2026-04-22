"""DRF serializers for GTFS data.

Phase 1 preview uses simple {lat, lon} pairs for Stop (Leaflet-friendly);
only Shape uses proper GeoJSON via drf-gis (route-line rendering).
"""
from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer

from apps.gtfs.models import Agency, Route, Shape, Stop


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

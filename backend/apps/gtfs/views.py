"""REST API + preview page for Phase 1 data validation (spec §6.3, §7.1)."""
from django.shortcuts import render
from django_filters import rest_framework as df_filters
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_gis.filters import InBBoxFilter

from apps.gtfs.models import Agency, Route, Shape, Stop, Trip
from apps.gtfs.serializers import (
    AgencySerializer,
    RouteSerializer,
    ShapeGeoJSONSerializer,
    StopSerializer,
)

# Human-readable mode -> GTFS route_type ints. Kept here (not in models)
# because this map is API surface; route_type constants on the model are
# the underlying truth.
MODE_TO_ROUTE_TYPE = {
    "tram": Route.ROUTE_TYPE_TRAM,
    "subway": Route.ROUTE_TYPE_SUBWAY,
    "metro": Route.ROUTE_TYPE_SUBWAY,  # alias — İBB uses both terms
    "rail": Route.ROUTE_TYPE_RAIL,
    "bus": Route.ROUTE_TYPE_BUS,
    "ferry": Route.ROUTE_TYPE_FERRY,
    "aerial": Route.ROUTE_TYPE_AERIAL,
    "funicular": Route.ROUTE_TYPE_FUNICULAR,
}


class RouteFilter(df_filters.FilterSet):
    mode = df_filters.CharFilter(method="filter_mode")
    has_shape = df_filters.BooleanFilter(method="filter_has_shape")

    class Meta:
        model = Route
        fields = ["mode", "has_shape"]

    def filter_mode(self, queryset, name, value):
        rt = MODE_TO_ROUTE_TYPE.get(value.lower())
        if rt is None:
            return queryset.none()
        return queryset.filter(route_type=rt)

    def filter_has_shape(self, queryset, name, value):
        # Route has a shape iff at least one of its trips points at a Shape
        # row. İETT's 9000+ bus routes have no shapes — this filter is how
        # the preview skips them without fetching 9000 × 204 responses.
        if value:
            return queryset.filter(trips__shape__isnull=False).distinct()
        if value is False:
            return queryset.exclude(trips__shape__isnull=False).distinct()
        return queryset


class AgencyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Agency.objects.all().order_by("agency_id")
    serializer_class = AgencySerializer
    lookup_field = "agency_id"


class RouteViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Route.objects.select_related("agency").order_by("route_id")
    serializer_class = RouteSerializer
    lookup_field = "route_id"
    lookup_value_regex = "[^/]+"  # route_ids may contain dots, dashes
    filterset_class = RouteFilter

    @action(detail=True, methods=["get"])
    def stops(self, request, route_id=None):
        """Distinct stops visited by this route, across all its trips.

        TODO(perf): optimize for large routes in Faz 6 — current query walks
        stop_times (1.25M rows) with 2 joins; ordered routes may take 3-5s.
        """
        route = self.get_object()
        qs = (Stop.objects
              .filter(stop_times__trip__route=route)
              .distinct()
              .order_by("name"))
        page = self.paginate_queryset(qs)
        if page is not None:
            ser = StopSerializer(page, many=True)
            return self.get_paginated_response(ser.data)
        return Response(StopSerializer(qs, many=True).data)

    @action(detail=True, methods=["get"])
    def shape(self, request, route_id=None):
        """GeoJSON LineString for the first trip with a shape on this route.

        İETT feeds have no shapes at all — returns 204 No Content (empty
        but meaningful, not an error).
        """
        route = self.get_object()
        trip = (Trip.objects
                .filter(route=route, shape__isnull=False)
                .select_related("shape")
                .first())
        if trip is None or trip.shape is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        ser = ShapeGeoJSONSerializer(trip.shape)
        return Response(ser.data)


class StopBboxFilter(InBBoxFilter):
    """Accept ?bbox=... per spec §6.3 (drf-gis default is ?in_bbox=)."""
    bbox_param = "bbox"


class StopViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Stop.objects.all().order_by("stop_id")
    serializer_class = StopSerializer
    lookup_field = "stop_id"
    lookup_value_regex = "[^/]+"
    filter_backends = [StopBboxFilter]
    bbox_filter_field = "location"
    bbox_filter_include_overlapping = True


def preview(request):
    """Phase 1 Leaflet preview — all stops (clustered) + sample routes."""
    return render(request, "preview.html")

"""REST API + preview page for Phase 1 data validation (spec §6.3, §7.1)."""
from django.db.models import Prefetch
from django.shortcuts import render
from django.utils.cache import patch_cache_control
from django_filters import rest_framework as df_filters
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response
from rest_framework_gis.filters import InBBoxFilter

from apps.gtfs.models import Agency, Route, Shape, Stop, StopTime, Trip
from apps.gtfs.serializers import (
    AgencySerializer,
    RouteSerializer,
    ShapeGeoJSONSerializer,
    StopSerializer,
    TripActiveSerializer,
)
from apps.gtfs.services import MODE_FILTER, active_trips_query
from apps.gtfs.timeutils import ISTANBUL, now_istanbul, parse_hhmmss

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

        TODO(perf): for large routes the current query walks stop_times
        (~1.25M rows) with 2 joins and can take a few seconds. Consider
        a materialized stops-per-route view if this becomes a bottleneck.
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


class ShapeDetailView(RetrieveAPIView):
    """Direct lookup of a Shape geometry by GTFS shape_id.

    Scheduled trips reference their own shape per direction, so the
    frontend fetches each direction's shape directly by shape_id. The
    older `/api/routes/{id}/shape/` endpoint only exposes one arbitrary
    direction's shape and is unsuitable here.
    """

    queryset = Shape.objects.all()
    serializer_class = ShapeGeoJSONSerializer
    lookup_field = "shape_id"

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        # Shape geometry is effectively immutable per shape_id; aggressive
        # cache is safe and cuts the polling cost on the frontend side.
        patch_cache_control(response, max_age=86_400, public=True)
        return response


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
    """Server-rendered Leaflet preview — all stops (clustered) + sample routes."""
    return render(request, "preview.html")


@api_view(["GET"])
def trips_active(request):
    """Trips active right now for the requested mode.

    Query params:
      mode  (required): metro | marmaray | tram | funicular | ferry
      time  (optional): HH:MM:SS in Europe/Istanbul; default now.
    """
    mode = request.query_params.get("mode")
    if mode not in MODE_FILTER:
        return Response(
            {"error": f"mode must be one of {sorted(MODE_FILTER)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    time_param = request.query_params.get("time")
    if time_param:
        try:
            td = parse_hhmmss(time_param)
        except (ValueError, AttributeError):
            return Response(
                {"error": "time must be HH:MM:SS"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        base = now_istanbul().replace(hour=0, minute=0, second=0, microsecond=0)
        now_dt = base + td
    else:
        now_dt = now_istanbul()

    qs = (
        active_trips_query(mode, now_dt)
        .select_related("route", "shape")
        .prefetch_related(
            Prefetch(
                "stop_times",
                queryset=StopTime.objects.select_related("stop").order_by("stop_sequence"),
            )
        )
    )
    data = TripActiveSerializer(qs, many=True).data

    response = Response({
        "mode": mode,
        "now": now_dt.isoformat(),
        "count": len(data),
        "trips": data,
    })
    patch_cache_control(response, max_age=60, public=True)
    return response

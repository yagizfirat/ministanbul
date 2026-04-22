"""GTFS schedule data models.

Reference: https://gtfs.org/schedule/reference/
Spec: MINI_ISTANBUL_3D_SPEC.md §6.2

Indexing notes:
- PointField / LineStringField set ``spatial_index=True`` by default, so
  PostgreSQL creates a GIST index on ``Stop.location`` and ``Shape.geometry``
  automatically. No extra ``Meta.indexes`` entry needed for those.
- ``ForeignKey`` fields get a B-tree index for free; only ``service_id`` needs
  ``db_index=True`` since it is a plain ``CharField``.
"""
from django.contrib.gis.db import models as gis_models
from django.db import models

from apps.core.constants import SRID_WGS84
from apps.core.models import TimestampedModel


class GTFSFeed(TimestampedModel):
    """Tracks each imported GTFS archive. Hash skip => idempotent imports."""

    FEED_TYPE_IETT = "iett"
    FEED_TYPE_PUBLIC = "public"
    FEED_TYPE_CHOICES = [
        (FEED_TYPE_IETT, "İETT"),
        (FEED_TYPE_PUBLIC, "Genel Toplu Ulaşım"),
    ]

    feed_type = models.CharField(max_length=20, choices=FEED_TYPE_CHOICES, unique=True)
    zip_hash = models.CharField(max_length=64, help_text="SHA-256 of source ZIP")
    imported_at = models.DateTimeField()
    routes_count = models.PositiveIntegerField(default=0)
    stops_count = models.PositiveIntegerField(default=0)
    trips_count = models.PositiveIntegerField(default=0)
    stop_times_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "GTFS Feed"
        verbose_name_plural = "GTFS Feeds"

    def __str__(self) -> str:
        return f"{self.get_feed_type_display()} @ {self.imported_at:%Y-%m-%d %H:%M}"


class Agency(TimestampedModel):
    agency_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    url = models.URLField()
    timezone = models.CharField(max_length=50, default="Europe/Istanbul")
    lang = models.CharField(max_length=10, default="tr")

    class Meta:
        verbose_name_plural = "Agencies"

    def __str__(self) -> str:
        return self.name


class Route(TimestampedModel):
    ROUTE_TYPE_TRAM = 0
    ROUTE_TYPE_SUBWAY = 1
    ROUTE_TYPE_RAIL = 2
    ROUTE_TYPE_BUS = 3
    ROUTE_TYPE_FERRY = 4
    ROUTE_TYPE_AERIAL = 6
    ROUTE_TYPE_FUNICULAR = 7
    ROUTE_TYPE_CHOICES = [
        (ROUTE_TYPE_TRAM, "Tram"),
        (ROUTE_TYPE_SUBWAY, "Subway"),
        (ROUTE_TYPE_RAIL, "Rail"),
        (ROUTE_TYPE_BUS, "Bus"),
        (ROUTE_TYPE_FERRY, "Ferry"),
        (ROUTE_TYPE_AERIAL, "Aerial"),
        (ROUTE_TYPE_FUNICULAR, "Funicular"),
    ]

    route_id = models.CharField(max_length=50, unique=True)
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="routes")
    short_name = models.CharField(max_length=50)
    long_name = models.CharField(max_length=200)
    route_type = models.IntegerField(choices=ROUTE_TYPE_CHOICES)
    color = models.CharField(max_length=7, default="#000000")
    text_color = models.CharField(max_length=7, default="#FFFFFF")

    def __str__(self) -> str:
        return f"{self.short_name} — {self.long_name}"


class Stop(TimestampedModel):
    LOCATION_TYPE_STOP = 0
    LOCATION_TYPE_STATION = 1
    LOCATION_TYPE_ENTRANCE = 2
    LOCATION_TYPE_CHOICES = [
        (LOCATION_TYPE_STOP, "Stop"),
        (LOCATION_TYPE_STATION, "Station"),
        (LOCATION_TYPE_ENTRANCE, "Entrance"),
    ]

    stop_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    location = gis_models.PointField(srid=SRID_WGS84)  # GIST auto
    location_type = models.IntegerField(
        choices=LOCATION_TYPE_CHOICES, default=LOCATION_TYPE_STOP
    )

    def __str__(self) -> str:
        return self.name


class Shape(TimestampedModel):
    """Route geometry — critical for vehicle simulation."""

    shape_id = models.CharField(max_length=50, unique=True)
    geometry = gis_models.LineStringField(srid=SRID_WGS84)  # GIST auto

    def __str__(self) -> str:
        return self.shape_id


class Trip(TimestampedModel):
    trip_id = models.CharField(max_length=100, unique=True)
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="trips")
    shape = models.ForeignKey(
        Shape,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="trips",
    )
    headsign = models.CharField(max_length=200)
    direction_id = models.IntegerField(default=0)
    service_id = models.CharField(max_length=50, db_index=True)

    def __str__(self) -> str:
        return f"{self.trip_id} ({self.headsign})"


class StopTime(TimestampedModel):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="stop_times")
    stop = models.ForeignKey(Stop, on_delete=models.CASCADE, related_name="stop_times")
    arrival_time = models.DurationField()  # GTFS HH:MM:SS, may exceed 24h
    departure_time = models.DurationField()
    stop_sequence = models.IntegerField()

    class Meta:
        ordering = ["trip", "stop_sequence"]
        indexes = [
            # Composite for "walk a trip in order" queries — the hot path for
            # both the importer and the schedule-to-vehicle simulator.
            models.Index(fields=["trip", "stop_sequence"], name="st_trip_seq_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.trip_id} #{self.stop_sequence}"

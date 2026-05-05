"""Import GTFS data from data/gtfs/ into PostGIS.

Two sources, each a loose CSV directory with *incompatible* encodings
and delimiters:

  - ``data/gtfs/iett/``    6 CSVs: UTF-8 (with BOM), ``;``-delimited.
                           No shapes.csv — İETT doesn't publish route
                           geometry; downstream code synthesizes from
                           stop sequences or falls back to straight lines.
  - ``data/gtfs/public/``  8 CSVs: cp1254 (Windows Turkish), comma-delim.
                           Includes shapes.csv and frequencies.csv.

Because İBB's CSV formats don't conform to the GTFS spec, we bypass
gtfs-kit (which assumes UTF-8 + comma) and parse with ``pandas.read_csv``
directly, auto-detecting encoding and delimiter per file.

Strategy: wipe-and-reload inside a single atomic transaction.

Load order:
  1. Public first  (older data, Mar 2024)
  2. İETT second   (newer data, Mar 2026) — wins on ID collisions via
                   ``ON CONFLICT DO UPDATE``, matching the realtime layer
                   which only has İETT feeds.

Duplicate IDs across feeds are logged as WARNING (last-writer-wins, not
silent). frequencies.csv is detected and skipped with a WARNING — the
Phase-1 MVP schedule model does not cover frequency-based scheduling.
"""
from __future__ import annotations

import json
import re
import datetime as dt
from datetime import timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd
from django.conf import settings
from django.contrib.gis.geos import LineString, Point
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone as djtz
from tqdm import tqdm

from apps.core.constants import (
    ISTANBUL_LAT_MAX, ISTANBUL_LAT_MIN,
    ISTANBUL_LON_MAX, ISTANBUL_LON_MIN,
    SRID_WGS84,
)
from apps.gtfs.models import (
    Agency, Calendar, GTFSFeed, Route, Shape, Stop, StopTime, Trip,
)

REQUIRED_CSVS = {
    "agency.csv", "calendar.csv", "routes.csv",
    "stops.csv", "trips.csv", "stop_times.csv",
}
ENCODING_SNIFF_BYTES = 65536  # 64 KB — Turkish chars may not appear in first 4 KB

BATCH = 5000

# Categories returned by _sanitize_coord — order drives per-row escalation.
# A row's category is the max over its (lat, lon) categories, so:
#   corrupt        > any valid fix (row is dropped)
#   fixed-3dot     > fixed  (3-dot pattern is rarer, worth surfacing distinctly;
#                              observed: 9 rows with 3-dot lat, zero with 3-dot
#                              on both sides)
#   fixed          > clean
_COORD_SEVERITY = {"clean": 0, "fixed": 1, "fixed-3dot": 2, "corrupt": 3}


def _safe_int(raw, default: int = 0) -> int:
    """Coerce pandas cell to int, tolerating NaN/empty/non-numeric."""
    if raw is None:
        return default
    if isinstance(raw, float) and pd.isna(raw):
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        try:
            s = str(raw).strip()
            return int(s) if s else default
        except (TypeError, ValueError):
            return default


def _sanitize_coord(raw) -> tuple[float | None, str]:
    """Recover a coord from İBB's broken thousand-separator format.

    Observed İETT stops.csv patterns:
      '41.083287780558'          -> 1 dot, clean
      '41.010.675.000.555'       -> 4 dots, thousand-sep style (14 digits)
      '410.191.700.005.564'      -> 4 dots, thousand-sep style (15 digits)
      '41.019.170.055'           -> 3 dots, shorter variant

    Universal rule: strip all dots, reinsert decimal after the first 2 digits
    (Istanbul lat/lon are always 2-digit integer parts: lat 40/41, lon 28/29).

    Returns (value, category) where category ∈
      {clean, fixed-3dot, fixed, corrupt}.
    """
    if raw is None:
        return None, "corrupt"
    s = str(raw).strip()
    if not s:
        return None, "corrupt"

    negative = s.startswith("-")
    if negative or s.startswith("+"):
        s = s[1:]

    dot_count = s.count(".")

    if dot_count == 1:
        try:
            v = float(("-" if negative else "") + s)
            return v, "clean"
        except ValueError:
            return None, "corrupt"

    digits = s.replace(".", "")
    if not digits.isdigit() or len(digits) < 3:
        return None, "corrupt"

    recovered = f"{digits[:2]}.{digits[2:]}"
    try:
        v = float(("-" if negative else "") + recovered)
    except ValueError:
        return None, "corrupt"

    if dot_count == 3:
        return v, "fixed-3dot"
    return v, "fixed"


def _in_istanbul_bbox(lat: float, lon: float) -> bool:
    return (ISTANBUL_LAT_MIN <= lat <= ISTANBUL_LAT_MAX
            and ISTANBUL_LON_MIN <= lon <= ISTANBUL_LON_MAX)


_HEX6_RE = re.compile(r"[0-9a-fA-F]{6}")
_HEX3_RE = re.compile(r"[0-9a-fA-F]{3}")


def _clean_hex(raw) -> str:
    """Normalize a GTFS route_color / route_text_color cell to 6-char hex.

    Public feed's routes.csv has empty color columns; with read_csv's
    ``na_values=[""]`` those become float('nan'), then ``str(nan)`` gave
    the literal string ``'nan'`` — which is truthy, so the old 'or ""'
    guard never fell through to the default. Result was ``'#NAN'`` in DB
    and invalid SVG strokes that rendered invisible polylines.

    Returns "" on any unparseable value; caller picks the default.
    """
    if raw is None:
        return ""
    if isinstance(raw, float) and pd.isna(raw):
        return ""
    s = str(raw).strip()
    if s.lower() in ("", "nan", "none", "null"):
        return ""
    if _HEX6_RE.fullmatch(s):
        return s.upper()
    if _HEX3_RE.fullmatch(s):
        # Expand #abc → #aabbcc
        return "".join(c * 2 for c in s).upper()
    return ""


class Command(BaseCommand):
    help = "Import GTFS data (iett ZIP + public CSV dir) into PostGIS."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true",
                            help="Wipe + reimport even if hashes match.")
        parser.add_argument("--file-iett", type=str, default=None,
                            help="Override iett CSV dir path (default: data/gtfs/iett)")
        parser.add_argument("--file-public", type=str, default=None,
                            help="Override public CSV dir path (default: data/gtfs/public)")
        parser.add_argument("--limit-routes", type=int, default=None,
                            help="Import only first N routes per feed (dev). Implies --force.")

    def handle(self, *args, **opts):
        data_dir = Path(settings.REPO_ROOT) / "data" / "gtfs"
        iett_dir = Path(opts["file_iett"]) if opts["file_iett"] else data_dir / "iett"
        public_dir = Path(opts["file_public"]) if opts["file_public"] else data_dir / "public"
        force = opts["force"]
        limit = opts["limit_routes"]

        if not iett_dir.is_dir():
            raise CommandError(f"iett dir not found: {iett_dir}. Run download_gtfs first.")
        if not public_dir.is_dir():
            raise CommandError(f"public dir not found: {public_dir}. Run download_gtfs first.")

        if limit is not None and not force:
            self.stdout.write(self.style.WARNING(
                f"  --limit-routes {limit} implies --force (subset changes DB state)."
            ))
            force = True

        iett_manifest = self._load_json(data_dir / "iett.manifest.json")
        public_manifest = self._load_json(data_dir / "public.manifest.json")
        if not iett_manifest or not public_manifest:
            raise CommandError(
                "Missing iett.manifest.json or public.manifest.json. Run download_gtfs first."
            )
        iett_hash = iett_manifest["feed_sha256"]
        public_hash = public_manifest["feed_sha256"]

        if not force:
            existing = {f.feed_type: f.zip_hash for f in GTFSFeed.objects.all()}
            if existing.get("iett") == iett_hash and existing.get("public") == public_hash:
                self.stdout.write(self.style.SUCCESS(
                    f"SKIP: both feeds already imported "
                    f"(iett={iett_hash[:12]}..., public={public_hash[:12]}...). "
                    f"Use --force to reimport."
                ))
                return

        self.stdout.write(self.style.MIGRATE_HEADING("\n[parse] Reading feeds via gtfs-kit..."))
        public_feed = self._read_feed(public_dir, "public")
        iett_feed = self._read_feed(iett_dir, "iett")

        if limit is not None:
            public_feed = self._subset_feed(public_feed, limit, "public")
            iett_feed = self._subset_feed(iett_feed, limit, "iett")

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n[load] Opening atomic transaction..."
        ))
        with transaction.atomic():
            self._wipe_gtfs_tables()

            # Public first (older data) — iett will overwrite conflicts.
            public_counts = self._load_feed(public_feed, "public", check_duplicates=False)

            # İETT second (newer) — wins on conflict, warns on duplicates.
            iett_counts = self._load_feed(iett_feed, "iett", check_duplicates=True)

            now = djtz.now()
            GTFSFeed.objects.update_or_create(
                feed_type="public",
                defaults={"zip_hash": public_hash, "imported_at": now, **public_counts},
            )
            GTFSFeed.objects.update_or_create(
                feed_type="iett",
                defaults={"zip_hash": iett_hash, "imported_at": now, **iett_counts},
            )

        self._print_summary(public_counts, iett_counts)

    # ------------------------------------------------------------------
    # IO helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _load_json(path: Path) -> dict | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # Feed reading (pandas.read_csv, per-file encoding + delimiter detection)
    # ------------------------------------------------------------------
    def _read_feed(self, csv_dir: Path, label: str) -> dict:
        present = {p.name for p in csv_dir.glob("*.csv")}
        missing = REQUIRED_CSVS - present
        if missing:
            raise CommandError(
                f"[{label}] missing required CSVs in {csv_dir}: {sorted(missing)}"
            )

        self.stdout.write(f"  [{label}] parsing {len(present)} CSV(s) from {csv_dir.name}/")
        feed: dict = {}
        for csv_path in sorted(csv_dir.glob("*.csv")):
            encoding = self._detect_encoding(csv_path)
            sep = self._detect_sep(csv_path, encoding)
            self.stdout.write(f"    {csv_path.name:<20} encoding={encoding:<10} sep={sep!r}")
            try:
                df = pd.read_csv(
                    csv_path, encoding=encoding, sep=sep,
                    dtype=str, keep_default_na=False, na_values=[""],
                    low_memory=False,
                )
            except Exception as e:
                raise CommandError(
                    f"[{label}] pandas.read_csv({csv_path.name}) failed: "
                    f"{type(e).__name__}: {e}"
                )
            # Strip BOM from first column name. Normal case: utf-8-sig
            # handles U+FEFF. Pathological case: UTF-8 BOM in front of
            # cp1254 body — detector falls back to cp1254 and the 3 BOM
            # bytes decode as 3 cp1254 chars instead of 1 U+FEFF char.
            first = df.columns[0]
            if first.startswith("\ufeff"):
                df.columns = [first.lstrip("\ufeff"), *df.columns[1:]]
            elif first.startswith("ï»¿"):
                df.columns = [first[3:], *df.columns[1:]]
            feed[csv_path.stem] = df

        # Optional files: supply empty DataFrame so downstream code is uniform.
        empty = pd.DataFrame()
        for opt_key in ("shapes", "frequencies", "calendar_dates"):
            feed.setdefault(opt_key, empty)
        return feed

    def _detect_encoding(self, path: Path) -> str:
        """Two-stage detection: BOM presence does NOT imply UTF-8 content.

        İBB exports have shown a BOM-prefixed file whose *body* was cp1254 —
        a tooling bug on their side. So we always verify the body decodes
        before trusting the BOM label.
        """
        head = path.read_bytes()[:ENCODING_SNIFF_BYTES]
        has_bom = head.startswith(b"\xef\xbb\xbf")
        body = head[3:] if has_bom else head
        try:
            body.decode("utf-8")
        except UnicodeDecodeError:
            if has_bom:
                self.stdout.write(self.style.WARNING(
                    f"    {path.name}: UTF-8 BOM present but body is not UTF-8 — "
                    f"falling back to cp1254 (column-name BOM stripped manually)."
                ))
            return "cp1254"
        return "utf-8-sig" if has_bom else "utf-8"

    @staticmethod
    def _detect_sep(path: Path, encoding: str) -> str:
        with path.open(encoding=encoding) as f:
            first = f.readline()
        # GTFS spec mandates comma; İETT emits semicolons. Pick the majority.
        return ";" if first.count(";") > first.count(",") else ","

    # ------------------------------------------------------------------
    def _subset_feed(self, feed: dict, n: int, label: str) -> dict:
        routes = feed["routes"].head(n).copy()
        route_ids = set(routes["route_id"].astype(str))
        trips = feed["trips"][feed["trips"]["route_id"].astype(str).isin(route_ids)].copy()
        trip_ids = set(trips["trip_id"].astype(str))
        stop_times = feed["stop_times"][
            feed["stop_times"]["trip_id"].astype(str).isin(trip_ids)
        ].copy()
        stop_ids = set(stop_times["stop_id"].astype(str))
        stops = feed["stops"][feed["stops"]["stop_id"].astype(str).isin(stop_ids)].copy()

        shapes = feed["shapes"]
        if not shapes.empty and "shape_id" in trips.columns:
            shape_ids = set(trips["shape_id"].dropna().astype(str))
            shapes = shapes[shapes["shape_id"].astype(str).isin(shape_ids)].copy()

        agency = feed["agency"]
        if "agency_id" in agency.columns and "agency_id" in routes.columns:
            ag_ids = set(routes["agency_id"].dropna().astype(str))
            agency = agency[agency["agency_id"].astype(str).isin(ag_ids)].copy()

        self.stdout.write(self.style.WARNING(
            f"  [{label}] subset to first {n} routes: "
            f"agencies={len(agency)}, routes={len(routes)}, stops={len(stops)}, "
            f"shapes_pts={len(shapes)}, trips={len(trips)}, stop_times={len(stop_times)}"
        ))
        return {**feed, "agency": agency, "routes": routes, "trips": trips,
                "stop_times": stop_times, "stops": stops, "shapes": shapes}

    # ------------------------------------------------------------------
    def _wipe_gtfs_tables(self) -> None:
        self.stdout.write("  Wiping existing GTFS tables (TRUNCATE CASCADE)...")
        with connection.cursor() as cur:
            cur.execute(
                "TRUNCATE gtfs_stoptime, gtfs_trip, gtfs_shape, "
                "gtfs_stop, gtfs_route, gtfs_agency, gtfs_calendar "
                "RESTART IDENTITY CASCADE"
            )

    # ------------------------------------------------------------------
    # Feed loader
    # ------------------------------------------------------------------
    def _load_feed(self, feed: dict, label: str, *, check_duplicates: bool) -> dict:
        self.stdout.write(self.style.MIGRATE_LABEL(f"\n  [{label}] loading into DB..."))

        if feed.get("frequencies") is not None and not feed["frequencies"].empty:
            n = len(feed["frequencies"])
            uniq = feed["frequencies"]["trip_id"].nunique() if "trip_id" in feed["frequencies"].columns else "?"
            self.stdout.write(self.style.WARNING(
                f"    Frequency-based scheduling detected ({n} rows, "
                f"{uniq} unique trips), skipped in Phase 1 MVP."
            ))

        self._load_agencies(feed["agency"], label, check_duplicates)
        agency_pk = dict(Agency.objects.values_list("agency_id", "id"))

        self._load_routes(feed["routes"], agency_pk, label, check_duplicates)
        route_pk = dict(Route.objects.values_list("route_id", "id"))

        self._load_stops(feed["stops"], label, check_duplicates)
        stop_pk = dict(Stop.objects.values_list("stop_id", "id"))

        self._load_shapes(feed["shapes"], label)
        shape_pk = dict(Shape.objects.values_list("shape_id", "id"))

        trip_ins = self._load_trips(feed["trips"], route_pk, shape_pk, label, check_duplicates)
        trip_pk = dict(Trip.objects.values_list("trip_id", "id"))

        st_ins = self._load_stop_times(feed["stop_times"], trip_pk, stop_pk, label)

        cal_ins = self._load_calendar(feed.get("calendar"), label)

        counts = {
            "routes_count": len(feed["routes"]),
            "stops_count": len(feed["stops"]),
            "trips_count": trip_ins,
            "stop_times_count": st_ins,
        }
        self.stdout.write(
            f"    [{label}] inserted: agencies={len(feed['agency'])}, "
            f"routes={counts['routes_count']}, stops={counts['stops_count']}, "
            f"trips={counts['trips_count']}, stop_times={counts['stop_times_count']}, "
            f"calendar={cal_ins}"
        )
        return counts

    def _load_agencies(self, df: pd.DataFrame, label: str, check: bool) -> None:
        if df.empty:
            return
        self._warn_duplicates(Agency, "agency_id", df["agency_id"], label, check)
        objs = [
            Agency(
                agency_id=str(r.agency_id),
                name=_demojibake(str(getattr(r, "agency_name", "") or "")),
                url=str(getattr(r, "agency_url", "") or ""),
                timezone=str(getattr(r, "agency_timezone", "") or "Europe/Istanbul"),
                lang=str(getattr(r, "agency_lang", "") or "tr"),
            )
            for r in df.itertuples(index=False)
        ]
        Agency.objects.bulk_create(
            objs, batch_size=BATCH,
            update_conflicts=True, unique_fields=["agency_id"],
            update_fields=["name", "url", "timezone", "lang", "updated_at"],
        )

    def _load_routes(self, df: pd.DataFrame, agency_pk: dict, label: str, check: bool) -> None:
        if df.empty:
            return
        self._warn_duplicates(Route, "route_id", df["route_id"], label, check)
        # Drop intra-file duplicates (observed: İETT routes.csv has 4 repeated
        # route_ids). ON CONFLICT DO UPDATE can't touch the same row twice in
        # one command, so last-wins must happen here in Python.
        before = len(df)
        df = df.drop_duplicates(subset=["route_id"], keep="last")
        intra_dups = before - len(df)
        if intra_dups:
            self.stdout.write(self.style.WARNING(
                f"    [{label}] {intra_dups} intra-file duplicate route_id(s) — kept last occurrence."
            ))
        fallback_agency = next(iter(agency_pk.values())) if agency_pk else None
        objs = []
        skipped_malformed: list[str] = []
        # Raw route_id length budget after the "public:"/"iett:" prefix (7/5
        # chars) is 43 at worst. Router lookups match on the prefixed form.
        prefix = f"{label}:"
        max_raw_len = 50 - len(prefix)
        for r in df.itertuples(index=False):
            rid_raw = str(getattr(r, "route_id", "") or "")
            # Public routes.csv contains at least one row with an embedded
            # newline / unquoted comma, causing pandas to pack multiple fields
            # into route_id (observed: 104 chars with commas). Skip those.
            if (len(rid_raw) > max_raw_len or "," in rid_raw or "\n" in rid_raw
                    or not rid_raw):
                if len(skipped_malformed) < 5:
                    skipped_malformed.append(rid_raw[:80])
                continue

            aid = str(getattr(r, "agency_id", "") or "")
            pk = agency_pk.get(aid, fallback_agency)
            if pk is None:
                continue
            color_hex = _clean_hex(getattr(r, "route_color", None))
            text_hex = _clean_hex(getattr(r, "route_text_color", None))
            rt = getattr(r, "route_type", None)
            objs.append(Route(
                route_id=f"{prefix}{rid_raw}",
                agency_id=pk,
                short_name=_demojibake(str(getattr(r, "route_short_name", "") or ""))[:50],
                long_name=_demojibake(str(getattr(r, "route_long_name", "") or ""))[:200],
                route_type=_safe_int(rt, default=3),
                color=f"#{color_hex}" if color_hex else "#000000",
                text_color=f"#{text_hex}" if text_hex else "#FFFFFF",
            ))
        if skipped_malformed:
            self.stdout.write(self.style.WARNING(
                f"    [{label}] {len(skipped_malformed)} route(s) skipped "
                f"(malformed route_id — embedded commas/newlines or >50 chars). "
                f"Sample: {skipped_malformed[:3]}"
            ))
        Route.objects.bulk_create(
            objs, batch_size=BATCH,
            update_conflicts=True, unique_fields=["route_id"],
            update_fields=["agency_id", "short_name", "long_name", "route_type",
                           "color", "text_color", "updated_at"],
        )

    def _load_stops(self, df: pd.DataFrame, label: str, check: bool) -> None:
        if df.empty:
            return
        self._warn_duplicates(Stop, "stop_id", df["stop_id"], label, check)
        objs = []
        tally = {"clean": 0, "fixed": 0, "fixed-3dot": 0,
                 "corrupt": 0, "out-of-bbox": 0}
        corrupt_samples: list[str] = []
        oob_samples: list[tuple[str, float, float]] = []

        for r in df.itertuples(index=False):
            sid = str(getattr(r, "stop_id", "") or "")
            lat_raw = getattr(r, "stop_lat", None)
            lon_raw = getattr(r, "stop_lon", None)

            lat_val, lat_cat = _sanitize_coord(lat_raw)
            lon_val, lon_cat = _sanitize_coord(lon_raw)

            if lat_val is None or lon_val is None:
                tally["corrupt"] += 1
                if len(corrupt_samples) < 5:
                    corrupt_samples.append(
                        f"{sid} lat={lat_raw!r} lon={lon_raw!r}"
                    )
                continue

            if not _in_istanbul_bbox(lat_val, lon_val):
                tally["out-of-bbox"] += 1
                if len(oob_samples) < 5:
                    oob_samples.append((sid, lat_val, lon_val))
                continue

            # Escalate per-row category to the worst of (lat, lon).
            row_cat = max(
                (lat_cat, lon_cat), key=lambda c: _COORD_SEVERITY[c]
            )
            tally[row_cat] += 1

            objs.append(Stop(
                stop_id=sid,
                name=_demojibake(str(getattr(r, "stop_name", "") or ""))[:200],
                location=Point(lon_val, lat_val, srid=SRID_WGS84),
                location_type=_safe_int(getattr(r, "location_type", 0)),
            ))

        Stop.objects.bulk_create(
            objs, batch_size=BATCH,
            update_conflicts=True, unique_fields=["stop_id"],
            update_fields=["name", "location", "location_type", "updated_at"],
        )

        total = len(df)
        self.stdout.write(
            f"    [{label}] stops: total={total}, clean={tally['clean']}, "
            f"fixed={tally['fixed']}, fixed-3dot={tally['fixed-3dot']}, "
            f"skipped-corrupt={tally['corrupt']}, "
            f"skipped-oob={tally['out-of-bbox']} "
            f"-> inserted {len(objs)}"
        )
        if corrupt_samples:
            self.stdout.write(self.style.WARNING(
                f"    [{label}] corrupt stop samples (first 5, for İBB feedback):"
            ))
            for s in corrupt_samples:
                self.stdout.write(f"      · {s}")
        if oob_samples:
            self.stdout.write(self.style.WARNING(
                f"    [{label}] out-of-bbox samples (sanitize misfire?):"
            ))
            for sid, la, lo in oob_samples:
                self.stdout.write(f"      · {sid} -> lat={la}, lon={lo}")

    def _load_shapes(self, df: pd.DataFrame, label: str) -> None:
        if df.empty:
            return
        # shape_pt_sequence arrives as string (dtype=str at read_csv).
        # Sorting it lexicographically puts '10' before '2' and produces
        # zig-zag polylines — observed in Eminönü preview, every shape.
        # Coerce to int first; drop rows with unparseable sequence.
        df = df.copy()
        df["shape_pt_sequence"] = pd.to_numeric(
            df["shape_pt_sequence"], errors="coerce"
        )
        before = len(df)
        df = df.dropna(subset=["shape_pt_sequence"])
        dropped_seq = before - len(df)
        if dropped_seq:
            self.stdout.write(self.style.WARNING(
                f"    [{label}] shapes: {dropped_seq} point(s) dropped "
                f"(non-numeric shape_pt_sequence)"
            ))
        df["shape_pt_sequence"] = df["shape_pt_sequence"].astype(int)
        df = df.sort_values(["shape_id", "shape_pt_sequence"])
        objs = []
        pts_total = 0
        pts_fixed = 0
        pts_dropped = 0
        shapes_dropped = 0

        for shape_id, grp in df.groupby("shape_id", sort=False):
            pts_total += len(grp)
            coords: list[tuple[float, float]] = []
            for lat_raw, lon_raw in zip(grp["shape_pt_lat"], grp["shape_pt_lon"]):
                lat_val, lat_cat = _sanitize_coord(lat_raw)
                lon_val, lon_cat = _sanitize_coord(lon_raw)
                if lat_val is None or lon_val is None:
                    pts_dropped += 1
                    continue
                if not _in_istanbul_bbox(lat_val, lon_val):
                    pts_dropped += 1
                    continue
                if lat_cat != "clean" or lon_cat != "clean":
                    pts_fixed += 1
                coords.append((lon_val, lat_val))

            if len(coords) < 2:
                shapes_dropped += 1
                continue  # LineString needs >= 2 coords

            objs.append(Shape(
                shape_id=str(shape_id),
                geometry=LineString(coords, srid=SRID_WGS84),
            ))

        if pts_fixed or pts_dropped or shapes_dropped:
            self.stdout.write(
                f"    [{label}] shapes: points_total={pts_total}, "
                f"points_fixed={pts_fixed}, points_dropped={pts_dropped}, "
                f"shapes_dropped={shapes_dropped} -> inserted {len(objs)}"
            )
        if not objs:
            return
        Shape.objects.bulk_create(
            objs, batch_size=BATCH,
            update_conflicts=True, unique_fields=["shape_id"],
            update_fields=["geometry", "updated_at"],
        )

    def _load_trips(self, df: pd.DataFrame, route_pk: dict, shape_pk: dict,
                    label: str, check: bool) -> int:
        if df.empty:
            return 0
        self._warn_duplicates(Trip, "trip_id", df["trip_id"], label, check)
        skipped = 0
        objs = []
        # Routes are stored with a feed prefix ("public:X", "iett:X") to avoid
        # the 118-way route_id collision between feeds. Trip rows reference
        # the raw ID, so we prefix here to match the FK lookup key.
        prefix = f"{label}:"
        for r in df.itertuples(index=False):
            rid = f"{prefix}{str(r.route_id)}"
            if rid not in route_pk:
                skipped += 1
                continue
            sid = getattr(r, "shape_id", None)
            shape_fk = shape_pk.get(str(sid)) if pd.notna(sid) else None
            objs.append(Trip(
                trip_id=str(r.trip_id),
                route_id=route_pk[rid],
                shape_id=shape_fk,
                headsign=_demojibake(str(getattr(r, "trip_headsign", "") or ""))[:200],
                direction_id=_safe_int(getattr(r, "direction_id", 0)),
                service_id=str(getattr(r, "service_id", "") or "")[:50],
            ))
        if skipped:
            self.stdout.write(self.style.WARNING(
                f"    [{label}] {skipped} trips skipped (unknown route_id)"
            ))
        Trip.objects.bulk_create(
            objs, batch_size=BATCH,
            update_conflicts=True, unique_fields=["trip_id"],
            update_fields=["route_id", "shape_id", "headsign", "direction_id",
                           "service_id", "updated_at"],
        )
        return len(objs)

    def _load_calendar(self, df, label: str) -> int:
        # calendar_dates.txt (exception overrides) is intentionally not
        # imported — public feed lacks the file.
        if df is None or df.empty:
            return 0
        weekday_cols = ("monday", "tuesday", "wednesday", "thursday",
                        "friday", "saturday", "sunday")
        objs: list[Calendar] = []
        skipped = 0
        for r in df.itertuples(index=False):
            sid = str(getattr(r, "service_id", "") or "").strip()[:64]
            if not sid:
                skipped += 1
                continue
            sd = _parse_gtfs_date(getattr(r, "start_date", None))
            ed = _parse_gtfs_date(getattr(r, "end_date", None))
            if sd is None or ed is None:
                skipped += 1
                continue
            kwargs = {col: _parse_gtfs_bool(getattr(r, col, None))
                      for col in weekday_cols}
            objs.append(Calendar(service_id=sid, start_date=sd, end_date=ed,
                                 **kwargs))
        if skipped:
            self.stdout.write(self.style.WARNING(
                f"    [{label}] {skipped} calendar rows skipped (bad service_id/date)"
            ))
        # Post-TRUNCATE: fresh inserts only.
        Calendar.objects.bulk_create(objs, batch_size=BATCH)
        return len(objs)

    def _load_stop_times(self, df: pd.DataFrame, trip_pk: dict, stop_pk: dict,
                         label: str) -> int:
        if df.empty:
            return 0
        total = len(df)
        skipped = 0
        objs: list[StopTime] = []

        def _gen() -> Iterable[StopTime]:
            nonlocal skipped
            for r in tqdm(
                df.itertuples(index=False), total=total,
                desc=f"    [{label}] stop_times", leave=True,
            ):
                tid = str(r.trip_id)
                sid = str(r.stop_id)
                tpk = trip_pk.get(tid)
                spk = stop_pk.get(sid)
                if tpk is None or spk is None:
                    skipped += 1
                    continue
                yield StopTime(
                    trip_id=tpk,
                    stop_id=spk,
                    arrival_time=_parse_gtfs_time(getattr(r, "arrival_time", None)),
                    departure_time=_parse_gtfs_time(getattr(r, "departure_time", None)),
                    # _safe_int mirrors the shape sequence guard — stop_sequence
                    # is stored as IntegerField so query-time ordering is already
                    # correct, but this blocks a malformed row from aborting the
                    # whole trip's load with a ValueError.
                    stop_sequence=_safe_int(getattr(r, "stop_sequence", 0)),
                )

        objs = list(_gen())
        if skipped:
            self.stdout.write(self.style.WARNING(
                f"    [{label}] {skipped} stop_times skipped (missing trip/stop refs)"
            ))
        # No upsert for stop_times — post-TRUNCATE, everything is a fresh row.
        StopTime.objects.bulk_create(objs, batch_size=BATCH)
        return len(objs)

    # ------------------------------------------------------------------
    def _warn_duplicates(self, model, field: str, series: pd.Series,
                         label: str, enabled: bool) -> None:
        if not enabled:
            return
        existing = set(model.objects.values_list(field, flat=True))
        if not existing:
            return
        incoming = set(series.astype(str))
        dup = existing & incoming
        if not dup:
            return
        sample = sorted(dup)[:5]
        self.stdout.write(self.style.WARNING(
            f"    DUPLICATE: {len(dup)} {field}(s) in both feeds — "
            f"{label} overwrites previous. Sample: {sample}"
            f"{'...' if len(dup) > 5 else ''}"
        ))

    # ------------------------------------------------------------------
    def _print_summary(self, public_counts: dict, iett_counts: dict) -> None:
        self.stdout.write(self.style.SUCCESS("\n=== Import Complete ==="))
        for label, c in [("public", public_counts), ("iett", iett_counts)]:
            self.stdout.write(
                f"  {label:<6} routes={c['routes_count']}, "
                f"stops={c['stops_count']}, trips={c['trips_count']}, "
                f"stop_times={c['stop_times_count']}"
            )
        self.stdout.write("\n  DB totals (after upsert merge):")
        self.stdout.write(f"    Agency     {Agency.objects.count()}")
        self.stdout.write(f"    Route      {Route.objects.count()}")
        self.stdout.write(f"    Stop       {Stop.objects.count()}")
        self.stdout.write(f"    Shape      {Shape.objects.count()}")
        self.stdout.write(f"    Trip       {Trip.objects.count()}")
        self.stdout.write(f"    StopTime   {StopTime.objects.count()}")


def _parse_gtfs_time(s) -> timedelta:
    """GTFS times are HH:MM:SS; hours may exceed 24 (e.g. '25:15:00')."""
    if s is None or (isinstance(s, float) and pd.isna(s)) or s == "":
        return timedelta(0)
    try:
        h, m, sec = str(s).strip().split(":")
        return timedelta(hours=int(h), minutes=int(m), seconds=int(sec))
    except (ValueError, AttributeError):
        return timedelta(0)


def _parse_gtfs_date(s):
    """GTFS dates are YYYYMMDD strings; return date or None on parse failure."""
    if s is None or (isinstance(s, float) and pd.isna(s)) or s == "":
        return None
    try:
        s = str(s).strip()
        return dt.date(int(s[0:4]), int(s[4:6]), int(s[6:8]))
    except (ValueError, IndexError):
        return None


def _parse_gtfs_bool(s) -> bool:
    """GTFS calendar weekday flags are '0'/'1' strings."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return False
    return str(s).strip() == "1"


_TURKISH_LETTERS = "şŞğĞıİçÇöÖüÜ"
_MOJIBAKE_MARKERS = "ÃÄÅÐĐÞ"


def _demojibake(s: str) -> str:
    """Reverse encoding mojibake using multiple round-trip patterns.

    İBB iETT routes.csv arrives with a mix of cp1252↔UTF-8 and
    latin1↔UTF-8 corruption. We try three passes:

      1. cp1252→UTF-8 round-trip   ("KADIKÃ–Y" → "KADIKÖY")
      2. latin1→UTF-8 round-trip   (cp1252 superset; bytes 0x80-0x9F differ)
      3. utf-8→iso-8859-9          (Turkish-specific reverse direction)

    A pass is only accepted if the result contains at least one
    Turkish-specific letter (ş/ğ/ı/ç/ö/ü etc.) — otherwise we treat
    the round-trip as a coincidence and fall back to the original.

    Idempotent: clean Turkish has no markers → no-op. Strings with
    U+FFFD fail every pass → returned unchanged.
    """
    if not s:
        return s

    # Hızlı yol — marker yoksa ve replacement char yoksa hiç deneme.
    if not any(c in s for c in _MOJIBAKE_MARKERS) and "�" not in s:
        return s

    # Pass 1: cp1252→UTF-8 (en yaygın).
    try:
        result = s.encode("cp1252").decode("utf-8")
        if any(c in result for c in _TURKISH_LETTERS):
            return result
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

    # Pass 2: latin1→UTF-8 (cp1252 superset; byte 0x80-0x9F'de farklı eşler).
    try:
        result = s.encode("latin1").decode("utf-8")
        if any(c in result for c in _TURKISH_LETTERS):
            return result
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

    # Pass 3: utf-8→iso-8859-9 (Türkçe — ters yön bozulma).
    try:
        result = s.encode("utf-8").decode("iso-8859-9")
        if any(c in result for c in _TURKISH_LETTERS) and not any(
            c in result for c in _MOJIBAKE_MARKERS
        ):
            return result
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

    # Hepsi fail → orijinal (kurtarılamaz).
    return s

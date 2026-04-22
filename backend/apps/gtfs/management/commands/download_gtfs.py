"""Download GTFS CSV files from İBB Açık Veri Portalı.

Spec §4.1 — two CKAN datasets, both structured as loose CSV resources
(empirical, 2026-04-21):

  - ``iett-gtfs-verisi``            → 6 CSVs: agency, calendar, routes,
    stops, trips, stop_times. No shapes.csv — İETT does not publish route
    geometry (spec §7.1 fallback: straight-line or OSM snap in Phase 5+).
    A redundant ``stop_times.zip`` resource exists (gzip of stop_times.csv
    only, not a full GTFS bundle) — we ignore it and pull the raw CSV.

  - ``public-transport-gtfs-data``  → 8 CSVs: above 6 + shapes + frequencies.

Strategy: per-file HEAD-before-GET against a ``{feed}.manifest.json`` cache,
so unchanged CSVs are never re-downloaded. Feed-level integrity hash is
sha256 of the canonical ``{filename: sha256}`` mapping — deterministic and
independent of any local repackaging.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from tqdm import tqdm

CKAN_BASE = "https://data.ibb.gov.tr/api/3/action/package_show"

FEEDS = {
    "iett": {
        "dataset_id": "iett-gtfs-verisi",
        "dirname": "iett",
        "expected_files": {
            "agency.csv", "calendar.csv", "routes.csv",
            "stops.csv", "trips.csv", "stop_times.csv",
        },
    },
    "public": {
        "dataset_id": "public-transport-gtfs-data",
        "dirname": "public",
        "expected_files": {
            "agency.csv", "calendar.csv", "frequencies.csv", "routes.csv",
            "shapes.csv", "stop_times.csv", "stops.csv", "trips.csv",
        },
    },
}

DOWNLOAD_CHUNK = 1024 * 64
HTTP_TIMEOUT = 60
USER_AGENT = "mini-istanbul-3d/0.1 (+dev; download_gtfs)"


class Command(BaseCommand):
    help = "Download İETT and/or Public Transport GTFS CSVs from İBB CKAN."

    def add_arguments(self, parser):
        parser.add_argument(
            "--feed", choices=list(FEEDS.keys()) + ["all"], default="all",
            help="Which feed to download (default: all)",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Ignore cached manifest and always re-download.",
        )

    def handle(self, *args, **opts):
        target_dir = Path(settings.REPO_ROOT) / "data" / "gtfs"
        target_dir.mkdir(parents=True, exist_ok=True)

        feeds = list(FEEDS.keys()) if opts["feed"] == "all" else [opts["feed"]]
        results = [self._process_feed(f, target_dir, force=opts["force"]) for f in feeds]

        self.stdout.write(self.style.SUCCESS("\n=== Summary ==="))
        for r in results:
            self.stdout.write(
                f"  {r['feed']:<6} -> {r['status']:<11} "
                f"size={r['size']/1_048_576:.2f} MB  "
                f"sha256={r['sha256'][:12]}... "
                f"({r['files_changed']}/{r['files_total']} files changed)"
            )

    # ------------------------------------------------------------------
    def _process_feed(self, feed: str, target_dir: Path, *, force: bool) -> dict:
        cfg = FEEDS[feed]
        feed_dir = target_dir / cfg["dirname"]
        feed_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = target_dir / f"{feed}.manifest.json"

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n[{feed}] dataset={cfg['dataset_id']}"
        ))

        resources = self._resolve_ckan_csvs(cfg["dataset_id"])
        found_names = {self._url_filename(r["url"]) for r in resources}
        missing = cfg["expected_files"] - found_names
        if missing:
            raise CommandError(
                f"[{feed}] dataset missing expected CSVs: {sorted(missing)}. "
                f"Present: {sorted(found_names)}"
            )
        extra = found_names - cfg["expected_files"]
        if extra:
            self.stdout.write(self.style.WARNING(
                f"  Unexpected CSVs (will still be fetched): {sorted(extra)}"
            ))

        old_manifest = self._load_json(manifest_path) or {}
        old_files = old_manifest.get("files", {})
        new_files: dict[str, dict] = {}
        files_changed = 0

        for res in resources:
            fname = self._url_filename(res["url"])
            url = res["url"]
            self.stdout.write(f"  Resolved [{fname}] URL: {url}")
            dest = feed_dir / fname
            server_meta = self._server_meta(url)

            old_entry = old_files.get(fname)
            if (
                not force and dest.exists() and old_entry
                and self._meta_matches(old_entry, server_meta)
            ):
                self.stdout.write(self.style.WARNING(
                    f"    SKIP: cached meta matches (sha256={old_entry['sha256'][:12]}...)"
                ))
                new_files[fname] = old_entry
                continue

            tmp_path = self._temp_file(feed_dir, fname)
            try:
                sha256 = self._download_with_progress(
                    url, tmp_path, f"    [{fname}] download"
                )
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise

            if dest.exists() and self._sha256(dest) == sha256:
                tmp_path.unlink(missing_ok=True)
                self.stdout.write(self.style.WARNING(
                    f"    UNCHANGED: server bytes identical "
                    f"(sha256={sha256[:12]}...). Local file preserved."
                ))
            else:
                shutil.move(str(tmp_path), str(dest))
                files_changed += 1
                self.stdout.write(self.style.SUCCESS(
                    f"    DOWNLOADED: {fname} "
                    f"({dest.stat().st_size/1024:.1f} KB, sha256={sha256[:12]}...)"
                ))
            new_files[fname] = {
                "url": url, "sha256": sha256,
                "etag": server_meta.get("etag"),
                "last_modified": server_meta.get("last_modified"),
                "content_length": server_meta.get("content_length"),
            }

        feed_hash = self._feed_hash_from_files(new_files)
        total_size = sum((feed_dir / n).stat().st_size for n in new_files)
        manifest = {"files": new_files, "feed_sha256": feed_hash}
        self._save_json(manifest_path, manifest)

        if not force and old_manifest.get("feed_sha256") == feed_hash and files_changed == 0:
            status = "skipped"
        elif files_changed == 0:
            status = "unchanged"
        else:
            status = "downloaded"

        self.stdout.write(self.style.SUCCESS(
            f"  FEED HASH: {feed_hash[:12]}...  "
            f"total={total_size/1_048_576:.2f} MB  "
            f"{files_changed}/{len(new_files)} files changed"
        ))
        return {
            "feed": feed, "status": status, "size": total_size, "sha256": feed_hash,
            "files_changed": files_changed, "files_total": len(new_files),
        }

    # ------------------------------------------------------------------
    # CKAN resolution
    # ------------------------------------------------------------------
    def _resolve_ckan_csvs(self, dataset_id: str) -> list[dict]:
        resp = requests.get(
            CKAN_BASE, params={"id": dataset_id},
            headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            raise CommandError(
                f"CKAN package_show failed: HTTP {resp.status_code} - {resp.text[:200]}"
            )
        data = resp.json()
        if not data.get("success"):
            raise CommandError(f"CKAN response not successful: {data}")
        all_res = data["result"].get("resources", [])
        csvs = [r for r in all_res if (r.get("format") or "").upper() == "CSV"]
        if not csvs:
            raise CommandError(
                f"No CSV resources in dataset {dataset_id!r}. "
                f"Formats present: {[r.get('format') for r in all_res]}"
            )
        return csvs

    @staticmethod
    def _url_filename(url: str) -> str:
        return url.rstrip("/").rsplit("/", 1)[-1]

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------
    def _server_meta(self, url: str) -> dict:
        resp = requests.head(
            url, headers={"User-Agent": USER_AGENT},
            timeout=HTTP_TIMEOUT, allow_redirects=True,
        )
        if resp.status_code >= 400:
            raise CommandError(f"HEAD {url} failed: HTTP {resp.status_code}")
        return {
            "etag": resp.headers.get("ETag"),
            "last_modified": resp.headers.get("Last-Modified"),
            "content_length": resp.headers.get("Content-Length"),
        }

    def _download_with_progress(self, url: str, dest: Path, desc: str) -> str:
        resp = requests.get(
            url, headers={"User-Agent": USER_AGENT},
            timeout=HTTP_TIMEOUT, stream=True,
        )
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0)) or None
        sha = hashlib.sha256()
        with open(dest, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True, unit_divisor=1024,
            desc=desc, leave=True,
        ) as bar:
            for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK):
                if not chunk:
                    continue
                f.write(chunk)
                sha.update(chunk)
                bar.update(len(chunk))
        return sha.hexdigest()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _temp_file(directory: Path, prefix: str) -> Path:
        with tempfile.NamedTemporaryFile(
            dir=directory, prefix=f".{prefix}.dl-", suffix=".tmp", delete=False
        ) as tmp:
            return Path(tmp.name)

    @staticmethod
    def _sha256(path: Path) -> str:
        sha = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                sha.update(chunk)
        return sha.hexdigest()

    @staticmethod
    def _load_json(path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _save_json(path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _meta_matches(local: dict, server: dict) -> bool:
        if server.get("etag") and local.get("etag"):
            return server["etag"] == local["etag"]
        if server.get("last_modified") and local.get("last_modified"):
            return (
                server["last_modified"] == local["last_modified"]
                and server.get("content_length") == local.get("content_length")
            )
        return False

    @staticmethod
    def _feed_hash_from_files(files: dict[str, dict]) -> str:
        # Canonical payload: {filename: sha256}, sorted keys, compact JSON.
        # Stable across re-runs; independent of file order or repackaging.
        payload = {name: entry["sha256"] for name, entry in files.items()}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(canonical).hexdigest()

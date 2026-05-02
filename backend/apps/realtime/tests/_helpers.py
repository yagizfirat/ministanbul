"""Shared test fixtures for the realtime suite.

Yol B (frontend route_id contract): vehicle.route_id now carries the
GTFS Route.route_id PK, not the SHATKODU short_name. Test fixtures used
to assert against ``"29B"``-style literals; with the new contract they
must compare against ``"iett:1562"`` and friends.

``EXPECTED_PK_FOR_HAT`` mirrors what ``build_mapping`` writes into the
``route_id_by_short_name`` cache field for the production DB snapshot
(see Yağız' dev DB, 2026-05-01). Test fixtures import from here instead
of hardcoding PK literals so a future re-import cannot silently break
multiple test files.

Source query (canonical PK = ORDER BY route_id ASC LIMIT 1)::

    SELECT short_name, MIN(route_id)
    FROM gtfs_route
    WHERE agency_id = (SELECT id FROM gtfs_agency WHERE name='IETT')
      AND route_type = 3
    GROUP BY short_name
    HAVING short_name IN ('29B', '15B', '34BZ', '500T')
    ORDER BY short_name;

M2 sits outside the IETT bus β-filter (agency=Metro İstanbul, route_type=1).
Production ``_build_route_id_by_short_name`` will not emit it; integration
tests that simulate an M2 vehicle wire it in manually via this dict.
"""
from __future__ import annotations

EXPECTED_PK_FOR_HAT: dict[str, str] = {
    "29B": "iett:1562",
    "15B": "iett:23965",
    "34BZ": "iett:23573",
    "500T": "iett:23909",
    # Outside IETT bus β-filter — included for integration test fixtures
    # that exercise a public-feed M2 vehicle alongside IETT buses.
    "M2": "public:1298",
}

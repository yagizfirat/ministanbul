"""Build VCR-style SOAP cassettes from ``_research/`` live captures.

Run from anywhere:
    python backend/apps/realtime/tests/cassettes/_build_from_research.py

Each build_* function derives one cassette from exactly one raw file in
``_research/``. Raw files are NEVER modified. Re-running the script
regenerates the cassettes deterministically.

Underscore-prefixed so pytest's ``test_*.py`` collector skips it.
"""
from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

_THIS = Path(__file__).resolve()
# backend/apps/realtime/tests/cassettes/_build_from_research.py
# parents: [cassettes, tests, realtime, apps, backend, repo_root]
REPO_ROOT = _THIS.parents[5]
RESEARCH = REPO_ROOT / "_research"
CASSETTES = _THIS.parent

_SOAP_TEMPLATE = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"'
    ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
    ' xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n'
    "  <soap:Body>\n"
    '    <{method}Response xmlns="http://tempuri.org/">\n'
    "      <{method}Result>{body}</{method}Result>\n"
    "    </{method}Response>\n"
    "  </soap:Body>\n"
    "</soap:Envelope>\n"
)


def _entity_encode(raw: str) -> str:
    """Mirror the gateway: JSON body embedded as XML text is entity-escaped."""
    return (
        raw.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _wrap_soap(method: str, json_body: str) -> str:
    return _SOAP_TEMPLATE.format(method=method, body=_entity_encode(json_body))


def _repair_truncated_json_array(raw: str) -> list:
    """_research/filo_konum_sample.json was sliced at 50 KB mid-element.

    Find the last complete ``},`` boundary and re-close with ``]``.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    last_boundary = raw.rfind("},")
    if last_boundary < 0:
        raise ValueError("no '},' boundary found — cannot repair")
    repaired = raw[: last_boundary + 1] + "]"
    return json.loads(repaired)


def _select_diverse_vehicles(vehicles: list, target: int = 12) -> list:
    """Pick ~target vehicles covering: null Garaj, Hiz=0 and Hiz>0.

    Operator diversity is best-effort — the live sample happens to be
    single-operator, but the selector would fan out if multiples existed.
    """
    def _hiz_is_zero(v):
        return str(v.get("Hiz", "")).strip() in ("0", "0.0", "")

    def _hiz_is_moving(v):
        return not _hiz_is_zero(v) and v.get("Hiz") is not None

    picked: list = []
    seen: set = set()
    operators_seen: set = set()

    def _add(v):
        if v["KapiNo"] in seen:
            return
        seen.add(v["KapiNo"])
        picked.append(v)
        operators_seen.add(v.get("Operator"))

    # Anchor: one null-Garaj, one stopped, one moving.
    for v in vehicles:
        if v.get("Garaj") is None:
            _add(v)
            break
    for v in vehicles:
        if _hiz_is_moving(v):
            _add(v)
            break
    for v in vehicles:
        if _hiz_is_zero(v) and v.get("Garaj") is not None:
            _add(v)
            break
    # Then diversify operators while filling to target.
    for v in vehicles:
        if len(picked) >= target:
            break
        if v.get("Operator") not in operators_seen:
            _add(v)
    # Top up.
    for v in vehicles:
        if len(picked) >= target:
            break
        _add(v)

    return picked[:target]


def build_filo_fetch_ok() -> None:
    raw = (RESEARCH / "filo_konum_sample.json").read_text(encoding="utf-8")
    vehicles = _repair_truncated_json_array(raw)
    print(f"[filo] repaired JSON → {len(vehicles)} vehicles")

    selected = _select_diverse_vehicles(vehicles, target=12)
    operators = {v.get("Operator") for v in selected}
    null_garaj = sum(1 for v in selected if v.get("Garaj") is None)
    stopped = sum(1 for v in selected if str(v.get("Hiz", "")).strip() in ("0", "0.0", ""))
    print(
        f"[filo] selected {len(selected)}: "
        f"operators={len(operators)}, null-garaj={null_garaj}, "
        f"stopped={stopped}, moving={len(selected) - stopped}"
    )

    body = json.dumps(selected, ensure_ascii=False)
    out = CASSETTES / "filo_fetch_ok.xml"
    out.write_text(_wrap_soap("GetFiloAracKonum_json", body), encoding="utf-8")
    print(f"[filo] wrote {out.name} ({out.stat().st_size} bytes)")


def _select_stratified_arsiv(
    records: list, target: int = 550, seed: int = 42
) -> list:
    """Deterministic stratified sample of archive-görev records.

    Invariants on the returned list (see tests/cassettes/README.md):
      - ~`target` rows (may exceed by up to 2 to keep null-start anchors)
      - >=20 distinct SHATKODU
      - >=30 distinct SKAPINUMARA
      - SGOREVDURUM distribution roughly proportional to the full dump
        (T dominant; I/YK/B represented if present)
      - >=2 rows with DTBASLAMAZAMANI=None (so the parser's skip path
        can be exercised by a fixture)

    Deterministic: same input + seed -> same output, every run.
    """
    rng = random.Random(seed)
    ordered = sorted(records, key=lambda r: r["ID"])
    total = len(ordered)
    if total == 0:
        return []

    selected_ids: set = set()
    selected: list = []

    def _take(r):
        if r["ID"] in selected_ids:
            return False
        selected_ids.add(r["ID"])
        selected.append(r)
        return True

    # 1) Diversity anchor: sample ~25 distinct SHATKODU, one T-preferred record each.
    by_hat: dict = {}
    for r in ordered:
        by_hat.setdefault(r["SHATKODU"], []).append(r)
    hat_keys = sorted(by_hat.keys())
    anchor_hat_count = min(25, len(hat_keys))
    for hat in rng.sample(hat_keys, anchor_hat_count):
        hat_recs = by_hat[hat]
        anchor = next((r for r in hat_recs if r["SGOREVDURUM"] == "T"), hat_recs[0])
        _take(anchor)

    # 2) top up until we cover >=30 SKAPINUMARA.
    kapis_covered = {r["SKAPINUMARA"] for r in selected}
    for r in ordered:
        if len(kapis_covered) >= 30:
            break
        if r["SKAPINUMARA"] not in kapis_covered and _take(r):
            kapis_covered.add(r["SKAPINUMARA"])

    # 3) proportional fill per SGOREVDURUM up to `target`.
    #    max(1, ...) guarantees minor statuses (I, YK, B) remain represented
    #    so the parser's skip-non-T path has fixture coverage.
    full_status_counts = Counter(r["SGOREVDURUM"] for r in ordered)
    target_by_status = {
        s: max(1, round(target * c / total)) for s, c in full_status_counts.items()
    }
    current_by_status = Counter(r["SGOREVDURUM"] for r in selected)
    remaining = [r for r in ordered if r["ID"] not in selected_ids]
    rng.shuffle(remaining)
    for r in remaining:
        if len(selected) >= target:
            break
        s = r["SGOREVDURUM"]
        if current_by_status[s] < target_by_status.get(s, 0):
            if _take(r):
                current_by_status[s] += 1
    # top up to exactly `target` with whatever remains (T dominates).
    for r in remaining:
        if len(selected) >= target:
            break
        if _take(r):
            current_by_status[r["SGOREVDURUM"]] += 1

    # 4) enforce >=2 null-DTBASLAMAZAMANI anchors (append; size may grow by 1-2).
    null_anchors = [r for r in selected if r["DTBASLAMAZAMANI"] is None]
    if len(null_anchors) < 2:
        for r in ordered:
            if r["ID"] in selected_ids:
                continue
            if r["DTBASLAMAZAMANI"] is None:
                _take(r)
                null_anchors.append(r)
                if len(null_anchors) >= 2:
                    break

    return selected


def build_arsiv_gorev_20260422_ok() -> None:
    raw = (RESEARCH / "ibb360_arsiv_gorev_yesterday_response.json").read_text(encoding="utf-8")
    data = json.loads(raw)

    full_status = Counter(r["SGOREVDURUM"] for r in data)
    full_hats = len({r["SHATKODU"] for r in data})
    full_kapis = len({r["SKAPINUMARA"] for r in data})
    full_nulls = sum(1 for r in data if r["DTBASLAMAZAMANI"] is None)
    print(
        f"[arsiv-20260422] full: n={len(data)} status={dict(full_status)} "
        f"hats={full_hats} kapis={full_kapis} null_start={full_nulls}"
    )

    selected = _select_stratified_arsiv(data, target=550, seed=42)

    sel_status = Counter(r["SGOREVDURUM"] for r in selected)
    sel_hats = len({r["SHATKODU"] for r in selected})
    sel_kapis = len({r["SKAPINUMARA"] for r in selected})
    sel_nulls = sum(1 for r in selected if r["DTBASLAMAZAMANI"] is None)
    print(
        f"[arsiv-20260422] sample: n={len(selected)} status={dict(sel_status)} "
        f"hats={sel_hats} kapis={sel_kapis} null_start={sel_nulls}"
    )

    # Hard invariants — the cassette is a test fixture; drift should fail loud.
    assert sel_hats >= 20, f"need >=20 SHATKODU, got {sel_hats}"
    assert sel_kapis >= 30, f"need >=30 SKAPINUMARA, got {sel_kapis}"
    assert sel_nulls >= 2, f"need >=2 null DTBASLAMAZAMANI, got {sel_nulls}"

    body = json.dumps(selected, ensure_ascii=False)  # minify
    out = CASSETTES / "arsiv_gorev_20260422_ok.xml"
    out.write_text(_wrap_soap("GetIettArsivGorev_json", body), encoding="utf-8")
    size_kb = out.stat().st_size / 1024
    print(f"[arsiv-20260422] wrote {out.name} ({size_kb:.1f} KB)")


def build_arsiv_gorev_empty_today() -> None:
    raw = (RESEARCH / "ibb360_arsiv_gorev_response.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert data == [], f"expected empty array, got {data!r}"
    body = json.dumps(data)
    out = CASSETTES / "arsiv_gorev_empty_today.xml"
    out.write_text(_wrap_soap("GetIettArsivGorev_json", body), encoding="utf-8")
    print(f"[arsiv-empty] wrote {out.name} ({out.stat().st_size} bytes)")


def build_policy_falsified_fault() -> None:
    raw = (RESEARCH / "arsiv_gorev_today_response.json").read_text(encoding="utf-8")
    # Already a SOAP Fault envelope (wrong-endpoint probe) — copy verbatim.
    out = CASSETTES / "policy_falsified_fault.xml"
    out.write_text(raw, encoding="utf-8")
    print(f"[policy-falsified] wrote {out.name} ({out.stat().st_size} bytes)")


def main() -> None:
    if not RESEARCH.is_dir():
        raise SystemExit(f"_research/ not found at {RESEARCH}")
    build_filo_fetch_ok()
    build_arsiv_gorev_20260422_ok()
    build_arsiv_gorev_empty_today()
    build_policy_falsified_fault()


if __name__ == "__main__":
    main()

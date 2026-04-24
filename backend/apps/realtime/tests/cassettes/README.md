# VCR-style SOAP cassettes

These XML files replay real IETT SOAP envelopes captured during
Phase 1.5 pre-flight and Phase 2 Step 4 research. Tests mock
`requests.post` to return their contents instead of hitting the
live gateway.

## Provenance

Cassettes are derived by `_build_from_research.py`:

| Cassette | Source in `_research/` | Transform |
|---|---|---|
| `filo_fetch_ok.xml` | `filo_konum_sample.json` | 50 KB slice of original dump; script repairs the truncated trailing object, keeps 12 diverse vehicles (null Garaj, stopped & moving, multi-op where available), and wraps in a `GetFiloAracKonum_jsonResponse` SOAP envelope with entity-encoded JSON body. |
| `arsiv_gorev_20260422_ok.xml` | `ibb360_arsiv_gorev_yesterday_response.json` | Deterministic stratified sample (seed=42) of 550 rows from the 55,682-record dump. Invariants: >=20 distinct `SHATKODU`, >=30 distinct `SKAPINUMARA`, SGOREVDURUM distribution proportional to the full dump (T dominant, I/YK/B each >=1 so the parser's skip-non-T path has coverage), >=2 rows with null `DTBASLAMAZAMANI` (skip-null-timestamp path). Minified and wrapped in a `GetIettArsivGorev_jsonResponse` SOAP envelope. |
| `arsiv_gorev_empty_today.xml` | `ibb360_arsiv_gorev_response.json` | 2-byte `[]` dump (today, empty). Wrapped in the same `GetIettArsivGorev_jsonResponse` envelope — confirms adapter handles a valid-but-empty gateway response. |
| `policy_falsified_fault.xml` | `arsiv_gorev_today_response.json` *(misnomer — actually a Policy Falsified fault from the old wrong-endpoint probe)* | Verbatim. Real SOAP Fault envelope from the gateway; used by the violation-response test to exercise `record_violation` + `IettRateLimitViolation`. |

## Regenerating

```
python backend/apps/realtime/tests/cassettes/_build_from_research.py
```

The script never writes to `_research/`; it only reads raw dumps and
produces cassettes here. Re-run after a sanctioned live re-capture
(Step 7 or later) if the upstream format drifts.

## Do not edit by hand

Hand edits will diverge from `_research/` silently. If a new shape
needs to be covered, add a new `build_*` in the script with a clear
function name and a `# source: <raw file>` comment.

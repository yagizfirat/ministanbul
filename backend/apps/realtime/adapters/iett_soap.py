"""IETT SOAP adapter — fetches vehicle positions from api.ibb.gov.tr.

Populated in Phase 2 Step 4: wraps GetFiloAracKonum_json (positions) and
GetIettArsivGorev_json (KapiNo → HatKodu mapping, via ibb360.asmx).
Uses raw requests + string SOAP envelope (zeep is not compatible with the
IETT WSDL, see spec Ek A.11.2). Rate-limited via a shared sliding window
enforced across Celery workers.

TODO (Phase 2 Step 4): IettSoapAdapter(BaseAdapter).
"""

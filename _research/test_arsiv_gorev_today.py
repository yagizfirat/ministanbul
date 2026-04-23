"""
GetIettArsivGorev_json Bugünkü Tarih Testi — Faz 1.5 Pre-flight #2
-------------------------------------------------------------------
Amaç: GetIettArsivGorev_json(Tarih) metodunun bugün için veri dönüp
dönmediğini öğrenmek. Bu metot kapı no → hat kodu eşlemesini veriyor,
Faz 2'nin temel taşı. Spec geçmiş için çalıştığını söylüyor, bugün
için belirsiz.

KURAL: TEK ÇAĞRI. Rate limit ~40dk/72 çağrı sliding window.
Döngü, retry, paralel YOK.

Base alınan:
  - test_ibb_token.py: raw_soap_call() pattern, ham requests + SOAP
    envelope şablonu (zeep broken WSDL nedeniyle kullanılamıyor).
  - test_29b_tracking.py: response regex parse + HTML entity decode.
Her ikisi de parametresiz GetFiloAracKonum_json çağırıyor. Burada
envelope'a <Tarih>YYYY-MM-DD</Tarih> parametresi eklendi.

Tarih formatı: YYYY-MM-DD (ISO 8601). ASMX xs:date/xs:dateTime
default'u. Başarısız olursa DD.MM.YYYY ayrı test — bu script'te yok.
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

import requests

SOAP_URL = "https://api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx"
METHOD = "GetIettArsivGorev_json"
TODAY = date.today().strftime("%Y-%m-%d")

SOAP_ENVELOPE = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <{METHOD} xmlns="http://tempuri.org/">
      <Tarih>{TODAY}</Tarih>
    </{METHOD}>
  </soap:Body>
</soap:Envelope>"""

HEADERS = {
    "Content-Type": "text/xml; charset=utf-8",
    "SOAPAction": f"http://tempuri.org/{METHOD}",
}

OUTPUT_FILE = Path(__file__).parent / "arsiv_gorev_today_response.json"


def detect_response_type(text: str) -> str:
    stripped = text.lstrip()
    if stripped.startswith("<?xml") or stripped.startswith("<"):
        if "soap:Fault" in text or "Policy Falsified" in text:
            return "SOAP Fault / Policy Falsified"
        return "XML (SOAP envelope)"
    if stripped.startswith("{") or stripped.startswith("["):
        return "JSON (raw)"
    return f"other (starts with: {stripped[:40]!r})"


def extract_inner_json(soap_xml: str) -> tuple[bool, object, str]:
    """SOAP envelope içindeki GetIettArsivGorev_jsonResult'ı çıkar ve JSON parse et."""
    m = re.search(
        rf"<{METHOD}Result>(.*?)</{METHOD}Result>",
        soap_xml,
        re.DOTALL,
    )
    if not m:
        return False, None, "Result tag bulunamadı"

    inner = m.group(1)
    decoded = (
        inner.replace("&quot;", '"')
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    try:
        data = json.loads(decoded)
        return True, data, ""
    except json.JSONDecodeError as e:
        return False, decoded[:500], f"JSON parse hatası: {e}"


def main():
    print("=" * 60)
    print(f"GetIettArsivGorev_json TEK ÇAĞRI TESTİ")
    print(f"Tarih parametresi: {TODAY} (format: YYYY-MM-DD)")
    print(f"Endpoint: {SOAP_URL}")
    print("=" * 60)

    try:
        r = requests.post(SOAP_URL, data=SOAP_ENVELOPE, headers=HEADERS, timeout=30)
    except requests.RequestException as e:
        print(f"\n[HATA] İstek atılamadı: {e}")
        sys.exit(1)

    text = r.text
    size = len(text.encode("utf-8"))

    OUTPUT_FILE.write_text(text[:5000], encoding="utf-8")

    print(f"\n--- HTTP ---")
    print(f"  Status code: {r.status_code}")
    print(f"  Response size: {size} byte")
    print(f"  Content-Type: {r.headers.get('Content-Type', '(yok)')}")

    rtype = detect_response_type(text)
    print(f"  Response tipi: {rtype}")

    has_kapino = "KapiNo" in text
    has_hatkodu = "HatKodu" in text
    print(f"\n--- İçerik probe ---")
    print(f"  'KapiNo' geçiyor mu: {has_kapino}")
    print(f"  'HatKodu' geçiyor mu: {has_hatkodu}")

    if "Policy Falsified" in text:
        print(f"\n[UYARI] 'Policy Falsified' → rate limit veya auth sorunu.")
    if "soap:Fault" in text:
        print(f"\n[UYARI] soap:Fault var → server-side hata.")
        m = re.search(r"<faultstring[^>]*>(.*?)</faultstring>", text, re.DOTALL)
        if m:
            print(f"  faultstring: {m.group(1)[:300]}")

    if rtype.startswith("XML"):
        ok, data, err = extract_inner_json(text)
        print(f"\n--- İç JSON ---")
        if ok:
            if isinstance(data, list):
                print(f"  Array, {len(data)} kayıt")
                print(f"\n--- İlk 3 kayıt ---")
                for i, rec in enumerate(data[:3], 1):
                    print(f"  [{i}] {json.dumps(rec, ensure_ascii=False)[:300]}")
            elif isinstance(data, dict):
                print(f"  Dict, keys: {list(data.keys())[:20]}")
                print(f"  Örnek: {json.dumps(data, ensure_ascii=False)[:500]}")
            else:
                print(f"  Tip: {type(data).__name__}, Değer: {str(data)[:300]}")
        else:
            print(f"  Parse başarısız: {err}")
            print(f"  Ham inner (ilk 500): {str(data)[:500]}")

    print(f"\n--- Çıktı ---")
    print(f"  Raw response (ilk 5000 char) yazıldı: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

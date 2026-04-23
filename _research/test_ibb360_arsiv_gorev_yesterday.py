"""
GetIettArsivGorev_json — ibb360.asmx Endpoint Testi (Faz 1.5 Mapping Probe)
--------------------------------------------------------------------------
Amaç: İlk denemede SeferGerceklesme.asmx endpoint'inde "Service Not Found"
dönmüştü. İBB PDF §10.1'e göre doğru endpoint ibb360.asmx. Bu script o
endpoint'i test eder. Metot kapı no (SKAPINUMARA) → hat kodu (SHATKODU)
eşlemesini verir; Faz 2'nin temel taşı.

KURAL: TEK ÇAĞRI. Rate limit ~40dk/72 çağrı sliding window.
Döngü, retry, paralel YOK.

Pattern base: test_arsiv_gorev_today.py (ham requests.post + string SOAP
envelope, zeep YOK).

Farklar:
  - Endpoint: ibb360.asmx (SeferGerceklesme.asmx değil).
  - Tarih formatı: yyyyMMdd (tire YOK) — PDF §10.1.2.
  - User-Agent header: mapping probe kimliği.
"""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

SOAP_URL = "https://api.ibb.gov.tr/iett/ibb/ibb360.asmx"
METHOD = "GetIettArsivGorev_json"
TARGET_DATE = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

SOAP_ENVELOPE = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <{METHOD} xmlns="http://tempuri.org/">
      <Tarih>{TARGET_DATE}</Tarih>
    </{METHOD}>
  </soap:Body>
</soap:Envelope>"""

HEADERS = {
    "Content-Type": "text/xml; charset=utf-8",
    "SOAPAction": f"http://tempuri.org/{METHOD}",
    "User-Agent": "Mini-Istanbul-3D-Research/0.1 (Phase 1.5 mapping probe)",
}

OUTPUT_FILE = Path(__file__).parent / "ibb360_arsiv_gorev_yesterday_response.json"

RATE_LIMIT_HEADER_HINTS = (
    "x-ratelimit",
    "ratelimit",
    "retry-after",
    "x-layer7",
    "layer7",
    "x-quota",
    "x-mashery",
)


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


def print_rate_limit_headers(headers) -> None:
    """Rate limit ile alakalı header'ları yazdır (case-insensitive match)."""
    relevant = []
    for name, value in headers.items():
        lname = name.lower()
        if any(hint in lname for hint in RATE_LIMIT_HEADER_HINTS):
            relevant.append((name, value))
    if not relevant:
        print("  (rate-limit / Layer7 header'ı bulunamadı)")
        return
    for name, value in relevant:
        print(f"  {name}: {value}")


def main():
    print("=" * 60)
    print("GetIettArsivGorev_json TEK ÇAĞRI — ibb360.asmx")
    print(f"Tarih parametresi: {TARGET_DATE} (format: yyyyMMdd)")
    print(f"Endpoint: {SOAP_URL}")
    print(f"User-Agent: {HEADERS['User-Agent']}")
    print("=" * 60)

    try:
        r = requests.post(SOAP_URL, data=SOAP_ENVELOPE, headers=HEADERS, timeout=30)
    except requests.RequestException as e:
        print(f"\n[HATA] İstek atılamadı: {e}")
        sys.exit(1)

    text = r.text
    size = len(text.encode("utf-8"))

    print(f"\n--- HTTP ---")
    print(f"  Status code: {r.status_code}")
    print(f"  Response size: {size} byte")
    print(f"  Content-Type: {r.headers.get('Content-Type', '(yok)')}")

    print(f"\n--- Tüm response header'ları ---")
    for name, value in r.headers.items():
        print(f"  {name}: {value}")

    print(f"\n--- Rate-limit / Layer7 header'ları (filtered) ---")
    print_rate_limit_headers(r.headers)

    rtype = detect_response_type(text)
    print(f"\n--- Response tipi ---")
    print(f"  {rtype}")

    print(f"\n--- Response body (ilk 2000 karakter) ---")
    print(text[:2000])

    print(f"\n--- İçerik probe ---")
    print(f"  'KapiNo' geçiyor mu: {'KapiNo' in text}")
    print(f"  'HatKodu' geçiyor mu: {'HatKodu' in text}")
    print(f"  'SKAPINUMARA' geçiyor mu: {'SKAPINUMARA' in text}")
    print(f"  'SHATKODU' geçiyor mu: {'SHATKODU' in text}")
    print(f"  'SGOREVDURUM' geçiyor mu: {'SGOREVDURUM' in text}")

    if "Policy Falsified" in text:
        print(f"\n[UYARI] 'Policy Falsified' → rate limit veya auth sorunu.")
    if "soap:Fault" in text:
        print(f"\n[UYARI] soap:Fault var → server-side hata.")
        m = re.search(r"<faultstring[^>]*>(.*?)</faultstring>", text, re.DOTALL)
        if m:
            print(f"  faultstring: {m.group(1)[:300]}")
    if "Service Not Found" in text:
        print(f"\n[UYARI] 'Service Not Found' → endpoint yanlış veya metot yok.")

    parsed_ok = False
    parsed_data = None

    if rtype.startswith("XML"):
        ok, data, err = extract_inner_json(text)
        print(f"\n--- İç JSON (SOAP envelope'dan çıkarılan) ---")
        if ok:
            parsed_ok = True
            parsed_data = data
            if isinstance(data, list):
                print(f"  Array, toplam {len(data)} kayıt")
                print(f"\n--- İlk 3 kaydın tam içeriği ---")
                for i, rec in enumerate(data[:3], 1):
                    print(f"  [{i}] {json.dumps(rec, ensure_ascii=False)}")
            elif isinstance(data, dict):
                print(f"  Dict, keys: {list(data.keys())}")
                print(f"  Örnek: {json.dumps(data, ensure_ascii=False)[:500]}")
            else:
                print(f"  Tip: {type(data).__name__}, Değer: {str(data)[:300]}")
        else:
            print(f"  Parse başarısız: {err}")
            print(f"  Ham inner (ilk 500): {str(data)[:500]}")
    elif rtype.startswith("JSON"):
        try:
            data = json.loads(text)
            parsed_ok = True
            parsed_data = data
            print(f"\n--- Raw JSON parse ---")
            if isinstance(data, list):
                print(f"  Array, toplam {len(data)} kayıt")
                print(f"\n--- İlk 3 kaydın tam içeriği ---")
                for i, rec in enumerate(data[:3], 1):
                    print(f"  [{i}] {json.dumps(rec, ensure_ascii=False)}")
            else:
                print(f"  Tip: {type(data).__name__}")
        except json.JSONDecodeError as e:
            print(f"\n[UYARI] JSON parse başarısız: {e}")

    if parsed_ok and isinstance(parsed_data, list) and parsed_data:
        print(f"\n--- Alan istatistikleri ---")

        shatkodu_values = {
            rec.get("SHATKODU")
            for rec in parsed_data
            if isinstance(rec, dict) and rec.get("SHATKODU") is not None
        }
        skapinumara_values = {
            rec.get("SKAPINUMARA")
            for rec in parsed_data
            if isinstance(rec, dict) and rec.get("SKAPINUMARA") is not None
        }
        print(f"  Unique SHATKODU sayısı: {len(shatkodu_values)}")
        print(f"  Unique SKAPINUMARA sayısı: {len(skapinumara_values)}")

        durum_counts: dict = {}
        for rec in parsed_data:
            if not isinstance(rec, dict):
                continue
            v = rec.get("SGOREVDURUM")
            key = "(None)" if v is None else str(v)
            durum_counts[key] = durum_counts.get(key, 0) + 1
        print(f"\n  SGOREVDURUM distinct değerler + kayıt sayısı:")
        if durum_counts:
            for k, v in sorted(durum_counts.items(), key=lambda kv: -kv[1]):
                print(f"    {k!r}: {v}")
        else:
            print(f"    (hiç kayıt bulunamadı)")

    if parsed_ok:
        OUTPUT_FILE.write_text(
            json.dumps(parsed_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n--- Çıktı ---")
        print(f"  Parse edilmiş response yazıldı: {OUTPUT_FILE}")
    else:
        print(f"\n--- Çıktı ---")
        print(f"  JSON parse başarısız → dump dosyası yazılmadı.")


if __name__ == "__main__":
    main()

"""
GetFiloAracKonum_json HatKodu Probe — Faz 1.5 Pre-flight #3
------------------------------------------------------------
Amaç: Spec §5.3'teki "filo response'unda HatKodu YOK, sadece
KapiNo" iddiasını ampirik olarak doğrula veya çürüt. Eğer HatKodu
varsa Faz 2 mimarisi dramatik olarak basitleşir (tek çağrıda
konum + hat); yoksa alternatif yol aranacak.

KURAL: TEK ÇAĞRI. Rate limit ~40dk/72 çağrı sliding window.
Bu oturumda atılan önceki çağrılar:
  1. test_arsiv_gorev_today → Policy Falsified (gateway-level)
  2. test_wsdl_discovery    → WSDL GET (sayıldığı belirsiz)
Bu 3. ciddi çağrı. Kötümser sayımla 68/72 hak kaldı, rahat.

Base: test_29b_tracking.py'deki fetch() fonksiyonu pattern'i —
SOAP envelope, regex decode, HTML entity unescape. Farkı: biz
sadece field keşfi yapıyoruz, araç takibi değil.
"""

import json
import re
import sys
from pathlib import Path

import requests

SOAP_URL = "https://api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx"
METHOD = "GetFiloAracKonum_json"

SOAP_ENVELOPE = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <{METHOD} xmlns="http://tempuri.org/" />
  </soap:Body>
</soap:Envelope>"""

HEADERS = {
    "Content-Type": "text/xml; charset=utf-8",
    "SOAPAction": f"http://tempuri.org/{METHOD}",
}

OUTPUT_FILE = Path(__file__).parent / "filo_konum_sample.json"

# Aradığımız potansiyel hat identifier anahtarları (case-insensitive)
CANDIDATE_KEYS = [
    "HatKodu", "HatNo", "Hat",
    "RouteCode", "RouteNo", "Route",
    "LineCode", "LineNo", "Line",
    "Guzergah", "GuzergahKodu",
    "SeferKodu", "Sefer",
]


def main():
    print("=" * 60)
    print(f"GetFiloAracKonum_json FIELD KEŞİF TESTİ")
    print(f"Endpoint: {SOAP_URL}")
    print("=" * 60)

    try:
        r = requests.post(SOAP_URL, data=SOAP_ENVELOPE, headers=HEADERS, timeout=45)
    except requests.RequestException as e:
        print(f"\n[HATA] İstek başarısız: {e}")
        sys.exit(1)

    text = r.text
    size = len(text.encode("utf-8"))

    print(f"\n--- HTTP ---")
    print(f"  Status: {r.status_code}")
    print(f"  Size: {size} byte ({size/1024:.1f} KB)")
    print(f"  Content-Type: {r.headers.get('Content-Type', '(yok)')}")

    if "Policy Falsified" in text or "soap:Fault" in text:
        print(f"\n[UYARI] Gateway reddi. İlk 400 char:")
        print(f"  {text[:400]}")
        sys.exit(2)

    # SOAP wrapper'dan iç JSON'u çıkar
    m = re.search(
        rf"<{METHOD}Result>(.*?)</{METHOD}Result>",
        text,
        re.DOTALL,
    )
    if not m:
        print(f"\n[HATA] Result tag bulunamadı. İlk 400 char:")
        print(f"  {text[:400]}")
        sys.exit(3)

    inner = m.group(1)
    decoded = (
        inner.replace("&quot;", '"')
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )

    try:
        data = json.loads(decoded)
    except json.JSONDecodeError as e:
        print(f"\n[HATA] JSON parse: {e}")
        print(f"  İlk 300 char inner: {decoded[:300]}")
        sys.exit(4)

    if not isinstance(data, list):
        print(f"\n[UYARI] Response list değil, tip: {type(data).__name__}")
        print(f"  Değer (ilk 500): {str(data)[:500]}")
        sys.exit(5)

    # Sample dosyaya yaz (ilk 50 KB inner JSON)
    sample = decoded[:50_000]
    OUTPUT_FILE.write_text(sample, encoding="utf-8")

    print(f"\n--- İçerik ---")
    print(f"  Toplam araç (len): {len(data)}")
    print(f"  Örnek yazıldı: {OUTPUT_FILE}")

    if len(data) == 0:
        print(f"\n[UYARI] Response array boş — normal çalışma saati dışı?")
        sys.exit(0)

    # İlk 5 aracın key'leri
    print(f"\n--- İlk 5 aracın field'ları ---")
    for i, rec in enumerate(data[:5], 1):
        if isinstance(rec, dict):
            keys = list(rec.keys())
            print(f"  [{i}] keys ({len(keys)}): {keys}")
        else:
            print(f"  [{i}] tip: {type(rec).__name__}, değer: {str(rec)[:200]}")

    # Tüm araçlar üzerinde UNIQUE key union (bazı araçlar bazı field'ları
    # eksik olabilir — diff'i görmek için)
    all_keys = set()
    for rec in data:
        if isinstance(rec, dict):
            all_keys.update(rec.keys())
    print(f"\n--- Tüm araçlarda görülen unique key'ler ({len(all_keys)}) ---")
    print(f"  {sorted(all_keys)}")

    # Candidate key probe: hangi candidate'lar hangi key'e eşleşiyor?
    print(f"\n--- Hat identifier probe (case-insensitive) ---")
    lowered_keys = {k.lower(): k for k in all_keys}
    found = []
    for cand in CANDIDATE_KEYS:
        cand_lower = cand.lower()
        if cand_lower in lowered_keys:
            real_key = lowered_keys[cand_lower]
            # populated vs empty sayısı
            populated = 0
            empty = 0
            samples = []
            for rec in data:
                if isinstance(rec, dict):
                    v = rec.get(real_key)
                    if v is None or v == "" or (isinstance(v, str) and v.strip() == ""):
                        empty += 1
                    else:
                        populated += 1
                        if len(samples) < 5:
                            samples.append(str(v))
            found.append((cand, real_key, populated, empty, samples))
            print(f"  ✓ '{cand}' → '{real_key}' | populated={populated}, empty={empty}")
            print(f"    örnek değerler: {samples}")

    if not found:
        print(f"  ✗ Hiçbir candidate key response'ta yok.")
        print(f"  Spec §5.3 iddiası (HatKodu yok, sadece KapiNo) DOĞRULANDI.")
        print(f"  Faz 2'de alternatif kaynak gerekli (PDF, başka endpoint, heuristic).")
    else:
        print(f"\n  Sonuç: Spec §5.3 iddiası ÇÜRÜTÜLDÜ.")
        print(f"  Faz 2 mimarisi basitleşir: tek çağrıda hem konum hem hat.")

    # Raw string probe — response text'inde bu string'ler geçiyor mu
    # (belki farklı bir yapıda, alt dict'te gömülü)
    print(f"\n--- Raw string probe ---")
    for cand in ["HatKodu", "HatNo", "RouteCode", "LineCode", "Hat\"", "Route\""]:
        count = decoded.count(cand)
        marker = "  ✓" if count > 0 else "  ✗"
        print(f"{marker} '{cand}' geçiş sayısı: {count}")


if __name__ == "__main__":
    main()

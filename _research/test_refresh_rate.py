"""
Backend Refresh Rate Test
-------------------------
Önceki testte fark ettik: API art arda çağrılarda aynı veriyi dönüyor.
Backend'in gerçekten kaç saniyede bir yeni veri yayınladığını ölçelim.

MANTIK:
  - 10 saniyede bir çağrı yap (5 dakika = 30 çağrı)
  - Rastgele 5 aracın konum hash'ini her snapshot'ta karşılaştır
  - Konum ne zaman değişiyor? Backend'in refresh rate'i bu.

GÜVENLİ: 30 çağrı / 5 dakika = saatte ~360 hız. Rate limit pencerende
testte rahat (önceki testte 40 dakikada ~70 istek hakkımız var).
"""

import requests
import time
import json
import re
from datetime import datetime

SOAP_URL = "https://api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx"
SOAP_ENVELOPE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetFiloAracKonum_json xmlns="http://tempuri.org/" />
  </soap:Body>
</soap:Envelope>"""
HEADERS = {
    "Content-Type": "text/xml; charset=utf-8",
    "SOAPAction": "http://tempuri.org/GetFiloAracKonum_json",
}


def fetch():
    try:
        r = requests.post(SOAP_URL, data=SOAP_ENVELOPE, headers=HEADERS, timeout=30)
        if r.status_code != 200 or "soap:Fault" in r.text:
            return None, f"HTTP {r.status_code}"
        match = re.search(
            r"<GetFiloAracKonum_jsonResult>(.*?)</GetFiloAracKonum_jsonResult>",
            r.text, re.DOTALL,
        )
        if not match:
            return None, "Format beklenmedik"
        json_str = (
            match.group(1)
            .replace("&quot;", '"')
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
        )
        return json.loads(json_str), ""
    except Exception as e:
        return None, str(e)[:100]


def snapshot_fingerprint(data, target_buses):
    """Belirli araçların (enlem, boylam) tuple'larını döndür."""
    fp = {}
    for v in data:
        kapi = v.get("KapiNo")
        if kapi in target_buses:
            try:
                lat = float(str(v["Enlem"]).replace(",", "."))
                lon = float(str(v["Boylam"]).replace(",", "."))
                saat = v.get("Saat", "")
                fp[kapi] = (lat, lon, saat)
            except (ValueError, KeyError):
                continue
    return fp


def main():
    print("═" * 60)
    print("BACKEND REFRESH RATE TESTİ — 10 saniye aralık, 30 snapshot")
    print("═" * 60)

    # İlk snapshot ile 10 hareketli araç seç
    print("\nİlk veri çekiliyor...")
    data, err = fetch()
    if not data:
        print(f"✗ Hata: {err}")
        return

    # Hız > 10 km/sa olan ilk 10 araç
    moving = []
    for v in data:
        try:
            hiz = float(str(v.get("Hiz", "0")).replace(",", "."))
            if hiz > 10:
                moving.append(v["KapiNo"])
                if len(moving) == 10:
                    break
        except (ValueError, KeyError):
            continue

    print(f"Takip: {', '.join(moving)}\n")

    history = []  # List of (timestamp, fingerprint_dict)
    print(f"{'#':<4} {'Saat':<10} {'Değişen':<10} {'Durum':<40}")
    print("-" * 60)

    for i in range(1, 31):
        t = time.time()
        now = datetime.now().strftime("%H:%M:%S")
        data, err = fetch()

        if not data:
            print(f"{i:<4} {now:<10} ✗ HATA: {err}")
            time.sleep(10)
            continue

        current_fp = snapshot_fingerprint(data, moving)
        if history:
            prev_fp = history[-1][1]
            changed = sum(
                1 for kapi in current_fp
                if kapi in prev_fp and current_fp[kapi][:2] != prev_fp[kapi][:2]
            )
            change_times = [
                current_fp[kapi][2] for kapi in current_fp
                if kapi in prev_fp and current_fp[kapi][:2] != prev_fp[kapi][:2]
            ]
            sample_saat = change_times[0] if change_times else ""
            status = (
                f"✓ Yeni veri (örnek saat: {sample_saat})"
                if changed > 0
                else "⊘ Aynı veri (backend henüz tazelememiş)"
            )
            print(f"{i:<4} {now:<10} {changed}/10       {status}")
        else:
            print(f"{i:<4} {now:<10} —          İlk snapshot (baseline)")

        history.append((t, current_fp))
        if i < 30:
            time.sleep(10)

    # ANALİZ
    print("\n" + "═" * 60)
    print("ANALİZ — Backend refresh rate hesaplama")
    print("═" * 60)

    refresh_intervals = []
    last_fresh_idx = 0
    for i in range(1, len(history)):
        t_prev, fp_prev = history[i - 1]
        t_cur, fp_cur = history[i]
        any_changed = any(
            kapi in fp_prev and fp_cur[kapi][:2] != fp_prev[kapi][:2]
            for kapi in fp_cur
        )
        if any_changed:
            if last_fresh_idx > 0:
                dt = t_cur - history[last_fresh_idx][0]
                refresh_intervals.append(dt)
            last_fresh_idx = i

    if refresh_intervals:
        avg = sum(refresh_intervals) / len(refresh_intervals)
        mn = min(refresh_intervals)
        mx = max(refresh_intervals)
        print(f"\n📊 Art arda yeni veri gelmesi arasındaki süreler:")
        for iv in refresh_intervals:
            print(f"   {iv:.1f}s")
        print(f"\n📈 Ortalama: {avg:.1f}s | Min: {mn:.1f}s | Max: {mx:.1f}s")

        print(f"\n💡 YORUM:")
        if 25 <= avg <= 35:
            print(f"   Backend her ~30 saniyede veri tazeliyor gibi.")
            print(f"   → Uygulamamızda 30-35 saniyede bir çağrı ideal.")
        elif 55 <= avg <= 65:
            print(f"   Backend her ~60 saniyede veri tazeliyor gibi.")
            print(f"   → Uygulamamızda 60 saniyede bir çağrı ideal.")
        elif avg < 20:
            print(f"   Backend çok sık tazeliyor (~{avg:.0f}s).")
            print(f"   → Daha sık çağrı yapabiliriz ama rate limit'e dikkat.")
        else:
            print(f"   Backend ~{avg:.0f} saniyede tazeliyor.")
            print(f"   → Buna yakın bir aralıkta çağrı yap.")
    else:
        print("\n⚠ Hiç veri değişimi tespit edilmedi. Rate limit'e takılmış olabiliriz.")


if __name__ == "__main__":
    main()

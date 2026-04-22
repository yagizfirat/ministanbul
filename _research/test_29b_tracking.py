"""
29B Takip Testi + Cooldown Testi
----------------------------------
İki amaç:
  1. Belirli bir hattın (varsayılan 29B) otobüslerini zaman içinde takip et
     → Gerçekten 30-60 saniye aralıklı veri ile hareket saptanabiliyor mu?
  2. Önceki long testten sonra servisin ne kadar sürede cooldown olduğunu öl
     → Bloklandıktan sonra kaç dakika beklememiz gerekiyor?

KULLANIM:
    python test_29b_tracking.py cooldown       → Servisin açılmasını bekle, ölç
    python test_29b_tracking.py track          → 29B otobüslerini 5 dakika takip et
    python test_29b_tracking.py track 34E      → Başka bir hat için
    python test_29b_tracking.py track 29B 10   → 10 dakika takip (varsayılan 5)

Önce COOLDOWN testini çalıştır (uzun testten hemen sonra yapıyorsan).
"""

import requests
import time
import sys
import json
import re
from datetime import datetime
from math import radians, cos, sin, sqrt, atan2

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
    """Tüm filoyu çek. (success, data_list, raw_text) döner."""
    try:
        r = requests.post(SOAP_URL, data=SOAP_ENVELOPE, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return False, [], f"HTTP {r.status_code}"
        if "soap:Fault" in r.text or "Policy Falsified" in r.text:
            return False, [], "SOAP Fault / Policy Falsified"

        # SOAP yanıtından JSON'u çıkar
        # GetFiloAracKonum_jsonResult içinde JSON string var
        match = re.search(
            r"<GetFiloAracKonum_jsonResult>(.*?)</GetFiloAracKonum_jsonResult>",
            r.text,
            re.DOTALL,
        )
        if not match:
            return False, [], "Response formatı beklenmedik"

        # HTML entity decode
        json_str = match.group(1)
        json_str = (
            json_str.replace("&quot;", '"')
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
        )
        data = json.loads(json_str)
        return True, data, ""
    except Exception as e:
        return False, [], str(e)[:200]


def haversine(lat1, lon1, lat2, lon2):
    """İki koordinat arasındaki mesafe (metre)."""
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


# ═══════════════════════════════════════════════════════════
# COOLDOWN TEST
# ═══════════════════════════════════════════════════════════
def test_cooldown():
    """Servisin ne kadar sürede cooldown olduğunu ölç."""
    print("═" * 60)
    print("COOLDOWN TEST — Her 30 saniyede tek istek atıyor, servis açılana kadar")
    print("═" * 60)
    print("(Ctrl+C ile iptal edilebilir)\n")

    max_minutes = 30
    check_interval = 30  # saniye
    start = time.time()
    attempt = 0

    while (time.time() - start) < max_minutes * 60:
        attempt += 1
        elapsed_min = (time.time() - start) / 60
        now = datetime.now().strftime("%H:%M:%S")
        success, data, err = fetch()

        if success:
            print(
                f"  {now} | Deneme {attempt} | ✓ SERVİS AÇILDI! "
                f"({elapsed_min:.1f} dakika sonra) | {len(data)} araç"
            )
            print(f"\n🎉 Cooldown süresi yaklaşık {elapsed_min:.1f} dakika")
            return elapsed_min
        else:
            print(f"  {now} | Deneme {attempt} | 🚧 Hâlâ bloklu | {err[:60]}")
            time.sleep(check_interval)

    print(f"\n⚠ {max_minutes} dakika sonra hâlâ açılmadı, manuel test gerekli")
    return None


# ═══════════════════════════════════════════════════════════
# BELİRLİ HAT TAKİBİ
# ═══════════════════════════════════════════════════════════
def track_route(route_hint: str, duration_min: int, interval_sec: int):
    """
    Belirli bir hattın otobüslerini duration_min dakika boyunca
    interval_sec aralıklarla takip et. Hareket mesafesini ölç.

    NOT: GetFiloAracKonum_json'da hat bilgisi yok, sadece Operator/Garaj/KapiNo.
    Bu yüzden "hat filtresi" yapamıyoruz. Bunun yerine 10 rastgele aracı
    seçip onların hareketini izliyoruz.
    """
    print("═" * 60)
    print(f"ARAÇ TAKİP TESTİ")
    print(f"Süre: {duration_min} dakika | Aralık: {interval_sec}s")
    print("=" * 60)
    print("(NOT: API hat bilgisi vermediği için 10 rastgele aracı takip ediyoruz)\n")

    total_checks = int(duration_min * 60 / interval_sec)
    print(f"Toplam {total_checks} veri noktası alınacak\n")

    # Her araç için konum geçmişi: {kapi_no: [(time, lat, lon), ...]}
    history = {}
    tracked_buses = None  # İlk çekimde seçilecek 10 araç

    for check in range(1, total_checks + 1):
        t = time.time()
        now = datetime.now().strftime("%H:%M:%S")
        success, data, err = fetch()

        if not success:
            print(f"  #{check} {now} | ✗ HATA: {err[:80]}")
            time.sleep(interval_sec)
            continue

        # İlk çekimde 10 rastgele aktif aracı seç (hız > 0 olanlardan)
        if tracked_buses is None:
            moving = [
                v
                for v in data
                if float(str(v.get("Hiz", "0")).replace(",", ".")) > 5
            ]
            # Hareketli ilk 10'u al
            tracked_buses = [v["KapiNo"] for v in moving[:10]]
            print(f"  Takip edilen araçlar: {', '.join(tracked_buses)}\n")

        # Bu çekimdeki 10 aracın konumunu kaydet
        snapshot = {}
        for v in data:
            if v["KapiNo"] in tracked_buses:
                try:
                    lat = float(str(v["Enlem"]).replace(",", "."))
                    lon = float(str(v["Boylam"]).replace(",", "."))
                    hiz = float(str(v.get("Hiz", "0")).replace(",", "."))
                    snapshot[v["KapiNo"]] = (t, lat, lon, hiz, v.get("Garaj", "?"))
                except (ValueError, KeyError):
                    continue

        # Önceki konumla karşılaştır, hareket mesafesini hesapla
        movement_msg = []
        for kapi_no, (t_new, lat, lon, hiz, garaj) in snapshot.items():
            if kapi_no in history and history[kapi_no]:
                t_old, lat_old, lon_old, _, _ = history[kapi_no][-1]
                dist = haversine(lat_old, lon_old, lat, lon)
                dt = t_new - t_old
                if dist > 5:  # 5m'den fazla hareket etti
                    movement_msg.append(f"{kapi_no}:{dist:.0f}m/{hiz:.0f}kmh")

            history.setdefault(kapi_no, []).append((t_new, lat, lon, hiz, garaj))

        moved_count = len(movement_msg)
        print(
            f"  #{check} {now} | {len(data)} araç | "
            f"{moved_count}/10 takip aracı hareketli | "
            f"{', '.join(movement_msg[:5])}{'...' if moved_count > 5 else ''}"
        )

        if check < total_checks:
            time.sleep(interval_sec)

    # ÖZET
    print("\n" + "═" * 60)
    print("ÖZET — Her aracın toplam hareketi")
    print("═" * 60)
    for kapi_no, points in history.items():
        if len(points) < 2:
            continue
        total_dist = 0
        for i in range(1, len(points)):
            _, la1, lo1, _, _ = points[i - 1]
            _, la2, lo2, _, _ = points[i]
            total_dist += haversine(la1, lo1, la2, lo2)
        elapsed_min = (points[-1][0] - points[0][0]) / 60
        avg_speed = (total_dist / 1000) / (elapsed_min / 60) if elapsed_min > 0 else 0
        print(
            f"  {kapi_no} | Garaj: {points[0][4][:20]:<20} | "
            f"Toplam: {total_dist:.0f}m | Ort.hız: {avg_speed:.1f} km/sa | "
            f"Veri noktası: {len(points)}"
        )

    print("\n💡 YORUM:")
    print("  Her aracın 'veri noktası' sayısı = kaç ölçüm yaptık")
    print("  'Toplam hareket' = zincirleme mesafe")
    print("  Hat animasyonu için bu noktalar arasında interpolasyon yapılır")


# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "cooldown":
        test_cooldown()
    elif cmd == "track":
        route = sys.argv[2] if len(sys.argv) > 2 else "29B"
        duration = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        interval = int(sys.argv[4]) if len(sys.argv) > 4 else 30
        track_route(route, duration, interval)
    else:
        print(f"Bilinmeyen komut: {cmd}")
        print("Kullanım: python test_29b_tracking.py [cooldown|track]")

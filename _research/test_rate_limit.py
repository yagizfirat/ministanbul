"""
Rate Limit Endurance Test
-------------------------
İETT SOAP servisinin gerçek rate limit davranışını öğrenmek için.

PDF'te "saatte max 100 çağrı" yazıyor ama v2 testinde 5 çağrı sorunsuz geçti.
Bu script, limit gerçekten uygulanıyor mu net cevaplayacak.

İKİ TEST MODU:
  python test_rate_limit.py fast   → 30 saniye, 20 çağrı (hızlı probe)
  python test_rate_limit.py long   → 10 dakika, 200 çağrı (dayanıklılık)
  python test_rate_limit.py        → default: fast

DİKKAT: long mod gerçek sınırları zorlar. Eğer limit varsa IP banlanma
riski vardır. Önce fast ile başla.
"""

import requests
import time
import sys
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


def make_request():
    """Tek SOAP çağrısı. (status, size, elapsed_sec, blocked, err_msg) döner."""
    t0 = time.time()
    try:
        r = requests.post(SOAP_URL, data=SOAP_ENVELOPE, headers=HEADERS, timeout=30)
        dt = time.time() - t0
        body = r.text
        blocked = (
            "Policy Falsified" in body
            or "soap:Fault" in body
            or "Rate" in body
            or r.status_code == 429
        )
        return r.status_code, len(body), dt, blocked, None
    except Exception as e:
        dt = time.time() - t0
        return None, 0, dt, True, str(e)[:100]


def run_test(total_requests: int, interval_sec: float, label: str):
    """N çağrı yap, X saniye aralıklarla, sonuçları tabloyla yaz."""
    print(f"\n{'═' * 60}")
    print(f"  {label}")
    print(f"  Toplam istek: {total_requests} | Aralık: {interval_sec}s")
    print(f"  Tahmini süre: {total_requests * interval_sec / 60:.1f} dakika")
    print(f"  Saatlik hıza denk: {3600 / interval_sec:.0f} çağrı/saat")
    print(f"{'═' * 60}")
    print(f"{'#':<4} {'Saat':<10} {'Status':<8} {'Boyut':<10} {'Süre':<7} {'Durum'}")
    print("-" * 60)

    success = 0
    blocked = 0
    errors = 0
    first_block_at = None
    start_time = time.time()

    for i in range(1, total_requests + 1):
        status, size, dt, is_blocked, err = make_request()
        now = datetime.now().strftime("%H:%M:%S")

        if err:
            errors += 1
            marker = "❌ ERR"
            detail = err
        elif is_blocked:
            blocked += 1
            if first_block_at is None:
                first_block_at = i
            marker = "🚧 BLOCK"
            detail = ""
        else:
            success += 1
            marker = "✓ OK"
            detail = ""

        size_str = f"{size:,}" if size else "-"
        status_str = str(status) if status else "-"
        print(f"{i:<4} {now:<10} {status_str:<8} {size_str:<10} {dt:.2f}s   {marker} {detail}")

        if i < total_requests:
            time.sleep(interval_sec)

    elapsed = time.time() - start_time
    print("-" * 60)
    print(f"\n📊 ÖZET")
    print(f"  Toplam süre        : {elapsed:.1f}s ({elapsed/60:.1f} dk)")
    print(f"  Başarılı           : {success}/{total_requests}")
    print(f"  Engellenen         : {blocked}")
    print(f"  Hata               : {errors}")
    if first_block_at:
        print(f"  ⚠ İlk engel       : {first_block_at}. istekte")
    print()

    if blocked == 0 and errors == 0:
        print("✅ Rate limit TETİKLENMEDİ bu seviyede.")
        print(f"   Saatlik {3600/interval_sec:.0f} çağrı hızı güvenli görünüyor.")
    elif first_block_at and first_block_at < total_requests / 2:
        print("🚨 Rate limit KESIN AKTİF.")
        print(f"   ~{first_block_at} çağrıdan sonra engel başladı.")
    else:
        print("⚠ Aralıklı engeller var — stabil değil.")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "fast"

    if mode == "fast":
        # 30 saniyede 20 çağrı = 1.5s aralık = saatte 2400 hızı
        run_test(20, 1.5, "FAST PROBE — 30 saniye, 20 çağrı")
    elif mode == "long":
        # 10 dakikada 200 çağrı = 3s aralık = saatte 1200 hızı
        print("\n⚠ UYARI: Long mode 10 dakika sürer ve rate limit'e vurmak üzere tasarlandı.")
        print("  Devam etmek için 5 saniye içinde Ctrl+C ile iptal edebilirsin...")
        time.sleep(5)
        run_test(200, 3.0, "ENDURANCE — 10 dakika, 200 çağrı")
    elif mode == "super":
        # Deli mod: 1 dakikada 60 çağrı = saatte 3600
        print("\n🔥 SUPER mode — 1 dakikada 60 çağrı. IP ban riski!")
        time.sleep(3)
        run_test(60, 1.0, "SUPER — 60 çağrı, 1 saniye aralık")
    else:
        print(f"Bilinmeyen mod: {mode}")
        print("Kullanım: python test_rate_limit.py [fast|long|super]")

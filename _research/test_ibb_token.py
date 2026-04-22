"""
İBB API Token Test Script v2
-----------------------------
Önceki versiyon WSDL parse hatasına takılıyordu. Bu versiyon:
  - zeep'i strict=False ile başlatır (bozuk WSDL'i tolere et)
  - Önce WSDL'siz doğrudan SOAP isteği dener (raw POST)
  - CKAN testini doğru endpoint'le yapar

Kullanım:
    1. IBB_API_TOKEN'a token'ını yapıştır
    2. python test_ibb_token_v2.py
"""

import requests
from requests import Session

# ═══════════════════════════════════════════════════════════
IBB_API_TOKEN = "myf_demo"
# ═══════════════════════════════════════════════════════════

SOAP_BASE = "https://api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx"


def raw_soap_call(action_name: str, token: str = None, token_method: str = None):
    """zeep kullanmadan doğrudan HTTP POST ile SOAP çağrısı yap."""
    soap_envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <{action_name} xmlns="http://tempuri.org/" />
  </soap:Body>
</soap:Envelope>"""

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": f"http://tempuri.org/{action_name}",
    }

    url = SOAP_BASE
    if token and token_method == "header":
        headers["Authorization"] = f"Bearer {token}"
        headers["X-API-Token"] = token
        headers["apikey"] = token
    elif token and token_method == "query":
        url = f"{SOAP_BASE}?apikey={token}"

    try:
        r = requests.post(url, data=soap_envelope, headers=headers, timeout=15)
        return r.status_code, r.text[:500], len(r.text)
    except Exception as e:
        return None, str(e), 0


def test_soap_no_auth():
    """Test A: Authentication olmadan SOAP çağrısı"""
    print("\n[TEST A] SOAP — authentication yok, doğrudan çağrı")
    status, body, size = raw_soap_call("GetFiloAracKonum_json")
    print(f"  HTTP Status: {status}")
    print(f"  Response boyutu: {size} byte")

    if status == 200 and "soap:Fault" not in body:
        print(f"  ✓ BAŞARILI — veri geldi, auth gerekmiyor")
        return "no_auth_works"
    elif "Policy Falsified" in body:
        print(f"  ⚠ Policy Falsified — auth gerekli OR rate limit")
        print(f"  İlk 500 char: {body[:500]}")
        return "policy_blocked"
    else:
        print(f"  ✗ Başka bir hata — ilk 500 char:")
        print(f"    {body[:500]}")
        return "other_error"


def test_soap_with_token_header(token):
    """Test B: Token header'da"""
    print("\n[TEST B] SOAP — token HTTP header'da")
    status, body, size = raw_soap_call(
        "GetFiloAracKonum_json", token=token, token_method="header"
    )
    print(f"  HTTP Status: {status}")
    print(f"  Response boyutu: {size} byte")

    if status == 200 and "soap:Fault" not in body:
        print(f"  ✓ BAŞARILI — token header işe yaradı!")
        return True
    else:
        print(f"  ✗ Başarısız — ilk 400 char:")
        print(f"    {body[:400]}")
        return False


def test_soap_with_token_query(token):
    """Test C: Token query string'de"""
    print("\n[TEST C] SOAP — token URL query string'de")
    status, body, size = raw_soap_call(
        "GetFiloAracKonum_json", token=token, token_method="query"
    )
    print(f"  HTTP Status: {status}")
    print(f"  Response boyutu: {size} byte")

    if status == 200 and "soap:Fault" not in body:
        print(f"  ✓ BAŞARILI — token query string işe yaradı!")
        return True
    else:
        print(f"  ✗ Başarısız — ilk 400 char:")
        print(f"    {body[:400]}")
        return False


def test_ckan_status_endpoint(token):
    """Test D: CKAN API site_read endpoint (parametre gerektirmez)"""
    print("\n[TEST D] CKAN API token geçerliliği — site_read")
    url = "https://data.ibb.gov.tr/api/3/action/site_read"
    headers = {"Authorization": token}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json() if r.status_code == 200 else {}
        if data.get("success"):
            print(f"  ✓ CKAN token geçerli (site_read success)")
            return True
        else:
            print(f"  ✗ Status: {r.status_code}, Body: {r.text[:300]}")
            return False
    except Exception as e:
        print(f"  ✗ Hata — {e}")
        return False


def test_rate_limit_probe():
    """Test E: 5 hızlı istek, rate limit davranışı"""
    print("\n[TEST E] Rate limit probe — 5 hızlı ardışık istek")
    print("  (Policy Falsified ne zaman geliyor gözlemliyoruz)")

    import time
    for i in range(5):
        t0 = time.time()
        status, body, size = raw_soap_call("GetFiloAracKonum_json")
        dt = time.time() - t0
        blocked = "Policy Falsified" in body or "soap:Fault" in body
        marker = "✗ BLOCKED" if blocked else "✓ OK"
        print(f"  İstek {i+1}: {marker} | Status {status} | {size} byte | {dt:.1f}s")
        time.sleep(0.5)


if __name__ == "__main__":
    if IBB_API_TOKEN == "YOUR_TOKEN_HERE":
        print("❌ Önce IBB_API_TOKEN değişkenine token'ını yaz!")
        exit(1)

    print("═" * 60)
    print("İBB API Token Test v2 — direct HTTP (no zeep)")
    print("═" * 60)

    # 1. Önce auth olmadan ne oluyor?
    no_auth_result = test_soap_no_auth()

    # 2. Token header ile
    header_works = test_soap_with_token_header(IBB_API_TOKEN)

    # 3. Token query ile
    query_works = test_soap_with_token_query(IBB_API_TOKEN)

    # 4. CKAN token geçerliliği
    ckan_valid = test_ckan_status_endpoint(IBB_API_TOKEN)

    # 5. Rate limit davranışı
    test_rate_limit_probe()

    print("\n" + "═" * 60)
    print("YORUMLAMA")
    print("═" * 60)

    if header_works or query_works:
        print("🎉 Token SOAP'ta çalışıyor — Seçenek C uygulanabilir!")
    elif no_auth_result == "no_auth_works":
        print("📊 SOAP auth gerektirmiyor — rate limit konusu belirsiz")
        print("   Rate limit probe sonuçlarını değerlendir")
    elif no_auth_result == "policy_blocked" and not (header_works or query_works):
        print("🚧 Policy Falsified her yerde — belki bir whitelist/IP-based auth var")
        print("   İBB Destek'e soruyu yönlendirmek lazım")

    print(f"\nCKAN token geçerli mi: {'Evet' if ckan_valid else 'Hayır (farklı endpoint)'}")
# GetHatOtoKonum_json — 29B test cagrisi

**Tarih:** 2026-05-02
**Amac:** Faz 1'de reddedilmis per-hat endpoint'in response semasini ogrenmek. HatKodu dogrulaniyor mu?

---

## Cagri

- **URL:** `https://api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx`
- **SOAPAction:** `"http://tempuri.org/GetHatOtoKonum_json"`
- **Parametre:** `<HatNo>29B</HatNo>`
- **HTTP status:** 500
- **Sure:** 0.06s
- **Response boyutu:** 441 bytes
- **Content-Type:** text/xml;charset=utf-8

Rate limit etkisi: tek cagri, pencere ~40dk/72 cagri limitinin %1.4'u.

---

## Response

Endpoint **HTTP 500 SOAP Fault** dondurdu:

```xml
<soap:Fault>
  <faultcode>soap:Server</faultcode>
  <faultstring>Server was unable to process request. ---&gt;
    Object reference not set to an instance of an object.</faultstring>
  <detail />
</soap:Fault>
```

Bu klasik .NET sunucu-tarafi `NullReferenceException`. **Onemli:** 0.06s cevap suresi
rate limit DEGIL. Rate limit ihlali tipik olarak 30 dakika cooldown'da "Policy
Falsified" SOAP fault doner (Spec Ek A.13 — Faz 1.5 ampirik testi). Burada kod
yolu sunucuda bir field'in `null` oldugu icin patliyor.

Iki olasilik:
1. **Endpoint deprecated / bozuk** — WSDL hala listeliyor ama implementasyon yok
2. **Parametre adi yanlis** — `<HatNo>` yerine `<SHATKODU>` ya da `<HatKodu>` bekliyor olabilir

Faz 1.5'te (Spec Ek A.11) WSDL kesfi yapilmis ama bu metot **test edilmemisti**
("rate limit ekonomik degil" gerekcesiyle reddedilmisti). WSDL'deki parametre adi
`<HatNo>` mi yoksa `<SHATKODU>` mi belirsiz; bu turun dahilinde **ek bir cagri
denemiyoruz** (brief "1 cagri" sinirina sadik).

Raw XML kaydi: `_research/2026-05-02-gethatotokonum-29b-sample.json`

---

## Sema analizi

| Soru | Cevap | Field adi | Ornek |
|---|---|---|---|
| HatKodu var mi? | HAYIR | — | — |
| KapiNo var mi? | HAYIR | — | — |
| lat/lon var mi? | HAYIR | — | — |
| timestamp var mi? | HAYIR | — | — |
| vehicle sayisi | 0 | — | — |

---

## Karar matrisi

**KARAR: REDDET (su anki haliyle)**

HTTP 500 NullReferenceException; rate limit degil, server-side bug ya da
parametre uyusmazligi. Bu turdan sonra tekrar deneme yapmiyoruz.

**Acik kalan kucuk soru:** Parametre adi `<HatNo>` yerine `<SHATKODU>` olabilir mi?
WSDL Faz 1.5'te (Ek A.11) cekilmis ama metot signature'i o tur kayda gecmemis.
Eger Yagiz isterse bir **sonraki turda tek bir ek deneme** yapilabilir
(`<SHATKODU>29B</SHATKODU>` ile; rate limit %1.4 daha kullanim, hala guvenli).

---

## Plan A/B/C etkisi

- **Yol C C1 senaryosu su an kapali.** WSDL parametre adi netleseydi acilabilirdi,
  ama bu turda dogrulanmadi.
- Kalan secenekler:
  - **Yol B + UX kompromisi (one cikan):** Plan A polyline + agresif spatial filter.
    Kesif 3'un S3 sonucuyla zaten ortusuyor — mapping yanlis olan vehicle'lar
    `route_id=None`'a duser. Kullanici az sayida "gorunur 29B" gorur, ama
    onlar gercekten 29B olur.
  - **Mapping kaynak alternatifi:** GTFS-RT VehiclePositions standardi (Trip
    Updates) Istanbul icin mevcut mu? Veya baska bir CKAN dataset'i. Faz 6
    polish'inde arastirilabilir.
  - **GetHatOtoKonum_json ikinci deneme:** WSDL parametre adini kontrol edip
    `<SHATKODU>` ile ek tek cagri (Yagiz onayina bagli, ayri mini-tur).

---

**Script:** `backend/scripts/probe_gethatotokonum.py` (gecici, bu rapor uretildikten sonra silindi).
**Uretim zamani:** 2026-05-02T17:18:27Z

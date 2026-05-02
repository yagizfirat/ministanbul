# GetHatOtoKonum_json v2 — SHATKODU parametresi denemesi

**Tarih:** 2026-05-02
**Amac:** Onceki turun `<HatNo>29B</HatNo>` HTTP 500 NullReferenceException sonucu sonrasi parametre adi hipotezini test etmek. Faz 1 ampirik kayitlarinda `SHATKODU` field'i popular (mevcut SOAP adapter'lari bu adi kullaniyor — `_FLEET_ENVELOPE`'ta gectigi yer yok ama dis veride siklikla).

---

## Cagri

- **URL:** `https://api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx`
- **SOAPAction:** `"http://tempuri.org/GetHatOtoKonum_json"`
- **Parametre:** `<SHATKODU>29B</SHATKODU>`
- **HTTP status:** 500
- **Sure:** 0.08s
- **Response boyutu:** 441 bytes

Rate limit kullanim: bu cagri %1.4. Onceki turun cagrisi ile toplam ~%2.8.

---

## Response

Yine `NullReferenceException` SOAP fault:

```xml
<soap:Fault><faultcode>soap:Server</faultcode><faultstring>Server was unable to process request. ---&gt; Object reference not set to an instance of an object.</faultstring><detail /></soap:Fault>
```

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

## Karar

**REDDET (parametre da yanlis)**

HTTP 500 NullReferenceException tekrar. SHATKODU da yanlis parametre adi — endpoint gercekten bozuk veya WSDL eski. Yol C C1 KESIN KAPALI.

---

## Plan A/B/C etkisi

**Yol C C1 KESIN KAPALI.** SHATKODU da yanlis parametre — endpoint gercekten bozuk ya da WSDL eski. Iki ayri parametre denendi, ikisi de NullReferenceException.

**Sonraki tur — agir karar:** Kesif 1 sonucu beta (mapping coverage kotu, koridorda zaten 29B mapped sifir). Plan A + spatial filter yarim cozum bile degil. Kalan secenekler:

- **Mapping kaynak alternatifi arastirmasi** — GTFS-RT VehiclePositions Istanbul icin var mi, baska CKAN dataset'i, community projeleri
- **Yol B + UX kabul** — "29B mapped vehicle" coverage'i kabul et, sadece mapping'in gosterdigi az sayida vehicle'i goster, spatial filter aktif tut. Kullaniciya 'mapping is best-effort' etiketi.
- **GetHatOtoKonum_json WSDL detayli analizi** — Faz 1.5'in WSDL kaydi (Spec Ek A.11) tekrar incelenip parametre signature dogru tespit edilebilir mi? Veya endpoint deprecated mi WSDL update olmamis mi?

---

**Script:** `backend/scripts/probe_gethatotokonum_v2.py` (gecici, rapor uretildikten sonra silindi).
**Uretim zamani:** 2026-05-02T18:53:32Z

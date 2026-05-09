# Katkıda bulunmak

Projeye ilgi gösterdiğin için teşekkürler.

## Issue açmak

Bug, eksik veri, yanlış davranış veya öneriler için issue açabilirsin. Yazarken şunları paylaşırsan hızlı çözülür:

- Beklediğin davranış, gözlemlediğin davranış
- Tarayıcı, işletim sistemi, mobil/masaüstü
- Mümkünse ekran görüntüsü veya kayıt
- Console'daki hata mesajları (varsa)

İstanbul ulaşım verisi konusunda bilgili biriysen — özellikle GTFS, İETT verisi, hat eşleme, route shape doğruluğu konularında — gözlemlerin çok değerli. "Şu hattın rotası eksik", "şu durak yanlış konumda" gibi raporlar açık veri kalitesini iyileştirmemize yardım eder.

## Pull request akışı

1. Önce issue üzerinden konuş — büyük bir değişikliğe başlamadan yönü hizalayalım.
2. Fork'la, feature branch aç (`feature/durak-arama` gibi).
3. Değişiklik yap, ilgili testleri yaz veya güncelle.
4. Backend: `pytest`. Frontend: `npm test`. İkisi de yeşil olmalı.
5. Commit mesajları açıklayıcı olsun (`fix:`, `feat:`, `docs:`, `chore:` öneki tercih edilir, zorunlu değil).
6. PR aç, ne yaptığını ve niye yaptığını açıkla.

## Geliştirme ortamı

`README.md`'deki "Hızlı başlangıç" bölümünde lokal kurulum özeti var. PostgreSQL+PostGIS ve Redis lokalde çalışır olmalı.

## Kod stili

- **Python:** ruff + black, mevcut config'lere uy.
- **TypeScript:** eslint + prettier, mevcut config'lere uy.
- Dosya başlarına gereksiz yorum koyma; "ne yaptığını" değil "niye öyle yaptığını" yorumlamak daha değerli.

## İletişim

Issue tercih edilir — herkese açık konuşalım, başkaları da öğrenebilsin.

# KM-g Tasarım Turu: Filter mimarisi yeniden değerlendirmesi

**Tarih:** 2026-05-05
**Bağlam:** v0.8.1 KM-e fix (commit `8b9df77`) Reset donmasını çözdü, üç yeni
borç çıktı (Spec Ek A.19 #12 / #13 / #14 — toplu).
**Kapsam:** Sadece kod okuma + tasarım önerisi. Commit yok.
**Hedef:** Üç borcu tek tek yamamak yerine filter mimarisi için doğru
düzeltme katmanını seçmek.

---

## 1. Mevcut filter pipeline'ı (KM-e sonrası gerçek durum)

### 1.1 İki ayrı, birbirinden habersiz kanal

```
                    ┌──────────────────────────────────────────┐
                    │  KANAL A — route_id-based                │
                    │                                          │
   [Reset/Tümü/     │   RouteVisibility (state)                │
    Hiçbiri/        │     ├─ visible: Set<route_id>            │
    hat checkbox]   │     ├─ totalCount: number                │
        │           │     └─ subscribe(listener)               │
        ▼           │              │                           │
   resetToDefault   │              ▼ fire (snapshot)           │
   setBulkVisible   │   debouncedApplyFilters (RAF debounce)   │
   toggle           │              │                           │
                    │              ▼                           │
                    │   getFilterExpression(visible, total)    │
                    │     ├─ size==0     → FILTER_NEVER        │
                    │     ├─ size==total → null                │
                    │     └─ else        → ['in', route_id,..] │
                    │              │                           │
                    │              ▼                           │
                    │   setFilter('route-lines', expr)         │
                    │   setFilter('scheduled-circles', expr)   │
                    └──────────────────────────────────────────┘

                    ┌──────────────────────────────────────────┐
                    │  KANAL B — is_metrobus-based             │
                    │                                          │
   [İETT Otobüs     │   busVisible: bool (main.ts local)       │
    toggle,         │   metrobusVisible: bool (main.ts local)  │
    Metrobüs        │              │                           │
    toggle]         │              ▼                           │
        │           │   debouncedApplyFleet (RAF debounce)     │
        └──────────►│              │                           │
                    │              ▼                           │
                    │   buildFleetFilter(busV, metroV)         │
                    │     → ['case', is_metrobus, metroV,      │
                    │              busV]                       │
                    │              │                           │
                    │              ▼                           │
                    │   setFilter('fleet-circles', expr)       │
                    └──────────────────────────────────────────┘

   [routeFocus           ┌─────────────────────────────────────┐
    çift-tık]            │  KANAL C — focus paint (filter      │
        │                │   değil, opacity)                   │
        ▼                │   routeFocus.subscribe              │
   setFocus / null       │     → applyFocusPaint               │
                         │       → setPaintProperty            │
                         │         circle-opacity 0.2/1.0      │
                         │         (tüm 3 layer)               │
                         │       → setGlowFocus                │
                         └─────────────────────────────────────┘
```

### 1.2 Layer × kanal etkilenim matrisi

| Layer              | Kanal A (route_id) | Kanal B (is_metrobus) | Kanal C (focus paint) |
|--------------------|--------------------|-----------------------|------------------------|
| `route-lines`      | ✓ setFilter        | —                     | ✓ opacity              |
| `route-glow`       | (turn-off prop)    | —                     | ✓ glow filter          |
| `scheduled-circles`| ✓ setFilter        | —                     | ✓ opacity              |
| `fleet-circles`    | ✗ (KM-e Fix-B)     | ✓ setFilter           | ✓ opacity              |

`route-lines`, `scheduled-circles`, `fleet-circles` üçü de focus paint'ten
etkileniyor — circle-opacity feature `route_id ∈ focused` ise 1.0, değilse
**0.2** (yarı şeffaf, görünür kalır).

### 1.3 Reset/Tümü/Hiçbiri'nin gerçek kapsamı

`onSelectAll` (`route_panel.ts:534-537`):
```ts
const ids = allRoutes.map((r) => r.route_id);
opts.visibility.setBulkVisible(ids, true);
```
- `allRoutes` = `routes` parametresi = `[...polylineSummaries, ...ferrySummaries]`
- **Bus / metrobüs hatları yok** (lazy-fetch iptal edildi, KM5-e.2)
- Etki: sadece raylı + vapur route_id'leri → setBulkVisible → Kanal A
- **Kanal B etkilenmez. Kanal C etkilenmez.**

`onSelectNone` (`route_panel.ts:539-542`): aynı kapsam, false ile.

`onReset` (`route_panel.ts:544-546`):
```ts
opts.visibility.resetToDefault(opts.defaultVisibleIds);
```
- `defaultVisibleIds` = `initialIds` = `[...polylineSummaries, ...ferrySummaries].map(r => r.route_id)`
- Aynı: sadece Kanal A, sadece raylı + vapur.

**Sonuç:** üç buton da Kanal B'ye dokunmuyor, Kanal C'ye dokunmuyor.

---

## 2. Üç borç — kök neden analizi

### Borç #14 — "Hiçbiri" otobüs/metrobüs'ü gizlemiyor (UX)

**KÖK NEDEN: Mimari değil, koordinasyon eksikliği.** Buton zaten sadece
Kanal A'yı etkiliyor (bkz. §1.3). Kullanıcı zihinsel modeli ("Hiçbiri =
hepsini gizle") buton kapsamıyla uyuşmuyor.

KM-e Fix-B kararı (fleet-circles'a route_id filter uygulamamak) **doğruydu**:
İETT canlı vehicle.route_id çoğunlukla `null` (KM5-a mapping retire) →
`['in', 'route_id', [...]]` null değer için false → tüm İETT araçları
gizlenirdi. Bu, route_id-based bir Reset'in fleet-circles için anlamsız
olduğu anlamına geliyor.

**Çözüm yönü:** buton callback'leri Kanal B'yi (ve C'yi) de tetiklemeli.
Mimari iki kanal kalmalı — veri iki boyutlu (route_id + is_metrobus), tek
expression imkansız.

### Borç #12 — "Hiçbiri" sonrası "M3 üstünde sarı noktalar" görünüyor

**KÖK NEDEN: #14 ile aynı bug — kategorize edilmiş ayrı görünüm.**

Tek sarı = İETT bus rengi (`MODE_FALLBACK_COLORS.bus = #FFD200`,
`fleet_layer.ts:17`). Scheduled metro vehicle'ı kendi hattı renginin açık
tonu ile çizilir (`scheduled_layer.ts:75`, `lighten(M3 mor, +0.2L)`) —
sarı **olmaz**.

Yağız'ın gördüğü nokta:
- **Olasılık 1 (yüksek):** M3 hattının yakınındaki bir caddede İETT otobüsü
  (`fleet-circles`, sarı). Kanal A "Hiçbiri" olduğunda M3 polyline'ı +
  scheduled M3 noktaları gizlenir, ama fleet-circles'taki sarı bus
  öylece kalır. Görsel olarak "M3 üstünde sarı nokta" olarak okunuyor —
  aslında bus, metro değil.
- **Olasılık 2 (düşük):** scheduled metro vehicle filter'ı sızdı. Bu
  durumda kod hatalı olurdu; kod okuması bir sızıntı göstermiyor.
  `setFilter('scheduled-circles', FILTER_NEVER)` her frame setData sonrası
  da etkin kalır (MapLibre filter persistent, source.setData her frame'de
  filter expression'ı yeniden uygulanır).

**Olasılık 1'i destekleyen ek ipuçları:**
- Renk = sarı (kesin bus, kesin metro değil — paint expression case)
- Konum = M3 hat geometrisinin üstü (M3 İstanbul'un kuzeyi, otobüs hatları
  M3 boyunca çok yoğun çakışıyor)

**Çözüm yönü:** #14 ile aynı — "Hiçbiri" Kanal B'yi de kapatmalı, sarı
noktalar da gitsin.

### Borç #13 — fleet-circles "hayalet küme" (low-opacity stain)

**KÖK NEDEN HİPOTEZİ (orta-yüksek): routeFocus state'i sticky.**

Akış:
1. Kullanıcı bir hata çift-tıklar → `routeFocus.setFocus([routeId])`
2. `applyFocusPaint(focused)` çalışır, fleet-circles paint:
   ```ts
   'circle-opacity': ['case',
     ['in', ['get', 'route_id'], ['literal', focused]], 1.0,
     0.2,
   ]
   ```
3. fleet-circles'taki binlerce route_id-null vehicle (mapping retire) —
   `['in', null, [literal]]` → false → opacity **0.2**
4. Kullanıcı "Hiçbiri" basar → Kanal A çalışır. **routeFocus dokunulmaz.**
5. Render loop her frame ~6900 vehicle setData ile yenilenir, hepsi 0.2
   opacity. Yoğun bölgelerde (M5 koridor sonu = Üsküdar/Çamlıca) küme
   şeffaf-sarı bir leke gibi görünür.
6. Filter Kanal B hâlâ "ikisi açık" → vehicle'lar görünür kalır (Kanal A
   onları etkilemez). Fakat hepsi yarı şeffaf → "hayalet".

`map.on('click', ...)` boş alanda focus reset ediyor (`main.ts:300-307`)
ama "Hiçbiri" buton tıklaması panel'de — `queryRenderedFeatures` çağrılmaz,
focus reset olmaz.

**Alternatif hipotez (düşük):** MapLibre paint state stale. RAF debounce
+ render loop setData çakışması. Bu hipotezi destekleyen kanıt yok;
kanıt focus paint'in 0.2 opacity'si için var.

**Çözüm yönü:** Reset/Tümü/Hiçbiri (en azından "Hiçbiri" + Reset)
routeFocus'u da temizlesin. Ya da daha katmanlı: focus mevcutsa ve
kullanıcı global filter aksiyonu yapıyorsa, focus'u sürdürmek anlamsız.

---

## 3. Üç tasarım seçeneği

### Tasarım A — Minimal koordinasyon (KOORDINE BUTON KAPSAMI)

**Felsefe:** İki kanal mimarisi doğru (veri iki boyutlu), problem
butonların kapsamı dar. Buton callback'lerini her üç kanala da
yayalım.

**Değişiklikler:**

1. `route_panel.ts` — `RoutePanelOptions`'a iki yeni callback:
   ```ts
   onSelectAllChange?: (allOn: boolean) => void;  // Tümü → true, Hiçbiri → false
   onResetRequested?: () => void;
   ```
   `onSelectAll`/`onSelectNone`/`onReset` bu callback'leri tetikler. Panel
   ayrıca bus + metrobüs checkbox'larının `checked` görsel state'ini de
   günceller (Kanal B UI tutarlılığı).

2. `main.ts` — RoutePanel kurulumunda yeni callback'ler:
   ```ts
   onSelectAllChange: (allOn) => {
     busVisible = allOn;
     metrobusVisible = allOn;
     debouncedApplyFleet();
     routeFocus.setFocus(null);  // Kanal C reset
   },
   onResetRequested: () => {
     busVisible = true;
     metrobusVisible = true;
     debouncedApplyFleet();
     routeFocus.setFocus(null);
   },
   ```

3. Buton etiket netleştirmesi (opsiyonel UX iyileştirmesi):
   - "Tümü" → "Hepsi"
   - "Hiçbiri" → "Hiçbiri" (kalır, semantik artık doğru)
   - "Reset" → "Sıfırla"

**Test stratejisi:**
- `route_panel.test.ts`'e ek case: "Hiçbiri tıklanınca onSelectAllChange(false) ve onResetRequested değil"
- "Tümü tıklanınca onSelectAllChange(true)"
- "Reset tıklanınca onResetRequested ve bus checkbox state default'a dönüyor"
- (main.ts side: test edilemez gerçek browser, smoke ile doğrulanır)

**Risk:**
- KM-e'deki Fix-A debounce mantığı dokunulmaz; donma regression yok.
- routeFocus reset eklendi; mevcut "boş alana tıkla → focus reset" davranışı korunur, ek bir tetikleyici eklenmiş olur.
- Mevcut testler: `route_panel.test.ts` "Tümü/Hiçbiri/Reset onBulkChange çağırıyor" gibi case'ler — yeni callback ile genişler, breaking değil.

**Boyut tahmini:** ~50-70 satır (route_panel.ts ~30, main.ts ~15, test ~20).

---

### Tasarım B — Tek-kanal composite filter (REFAKTÖR)

**Felsefe:** Tüm visibility state'i tek bir `CompositeFilter` modülüne
indirgele. Her layer kendi expression'ını ondan alır.

**Yeni dosya:** `state/composite_filter.ts`
```ts
export class CompositeFilter {
  private routeVisible: Set<string>;
  private busVisible: boolean;
  private metrobusVisible: boolean;
  // ... subscribe/listener pattern
  buildRouteLineFilter(): unknown { /* route_id-based */ }
  buildScheduledFilter(): unknown { /* route_id-based, ferry de aynı */ }
  buildFleetFilter(): unknown { /* is_metrobus-based, çünkü route_id null */ }
}
```

**Değişiklikler:**
- `RouteVisibility` → `CompositeFilter`'a katılır veya wrapper olur
- `route_panel.ts` → tüm callback'ler tek `CompositeFilter` instance'ına yazar
- `main.ts` → `applyFilters` + `applyFleetVisibilityFilter` birleşir, tek `applyAllFilters`
- `fleet_layer.ts::buildFleetFilter` taşınır

**Avantajlar:**
- Tek subscribe, tek debounce noktası
- "Tümünü gizle/göster" tek state mutation
- Future flag'ları (örn. tarife-mod görünürlüğü, mod-bazlı toggle) eklemek kolay

**Dezavantajlar:**
- KM-e Fix-A/Fix-B kazanılan stabilite üzerine refaktör — donma regression riski
- ~150-200 satır değişim, mevcut test suite genişlemesi gerekir
- `route_visibility.test.ts` (149 satır) yeniden yazılır
- Ek soyutlama kazancı belirsiz: ortada 3 layer + 3 state var, "tek noktada
  toplama" gerçek bir reuse veya konsistens kazancı sağlamıyor; sadece
  satır taşıma

**Risk değerlendirmesi:**
- Yüksek. v0.8.1 sıkıştırma yolundayız (Yağız notu: "yan etkiler temizlensin
  yayına çıksın"). Refaktör v0.8.2'ye uygun.

**Boyut tahmini:** ~150-200 satır (yeni dosya 80, değişen 70-100, test 50).

---

### Tasarım C — KM-e'yi revert + minimal donma fix

**Felsefe:** Fix-A/Fix-B'yi geri al, donmayı kabul et, "Reset butonuna
debounce" gibi tek bir minimal müdahale ile yeniden dene.

**Pratik:**
- `git revert 8b9df77` (commit'i tersine al)
- Reset/Tümü/Hiçbiri callback'lerinin kendisine RAF debounce/throttle
- fleet-circles çakışmasını başka şekilde (örn. fleet-circles için ayrı
  composite filter `['all', routeF, fleetVisF]` ama route_id null vehicle'lar
  için özel branch) çöz

**Sorunlar:**
- KM-e tanı raporu Fix-B'nin **kesin kanıtlı** olduğunu söylüyor (filter
  çakışması). Revert sonrası fleet-circles araçları "kayboluyor" UX bug'ı
  geri gelir.
- Donma kök sebebi büyük olasılıkla setFilter chain (Hipotez a). Debounce
  sadece o noktada lazım, başka çare yok.
- Yeni Borç #12/#13/#14 zaten yan etki — eski hâlde de aynı UX kafa
  karışıklığı vardı, sadece donma onların üstünü örtüyordu.

**Sonuç:** **Önerilmez.** Bu yol geri adım, çözüm değil.

---

## 4. Önerilen tasarım: A

**Gerekçe:**

1. **Mimari iki kanal kalmak zorunda.** Veri iki boyutlu: scheduled vehicle
   route_id'ye göre filtrelenmeli (her hattın kendi tarifesi var); İETT
   canlı vehicle is_metrobus'a göre filtrelenmeli (route_id null). Bu fark
   ortadan kaldırılamaz; mapping retire kararı (KM5-a) load-bearing.

2. **Borç #12, #13, #14 hep aynı problemin yüzleri:** buton kapsamı dar.
   Mimari problem değil, koordinasyon eksikliği. Tasarım A bu boşluğu
   minimum yüzeyle dolduruyor.

3. **v0.8.1 yayın penceresi.** KM-e ile gelen stabilite (donma çözüldü)
   üzerine refaktör (Tasarım B) riski mantıksız. Tasarım A KM-e'nin
   üstüne ek; geriye dönük uyumlu.

4. **Sürpriz az.** Tasarım A'da sadece olan davranış genişler ("Hiçbiri"
   artık fleet-circles'ı da gizler, focus'u da temizler). Mevcut testler
   kırılmaz. Ek 3-4 case yeterli.

**Implementation taslağı (Tasarım A için):**

```
1. route_panel.ts:
   - RoutePanelOptions'a 2 yeni opt callback (onSelectAllChange, onResetRequested)
   - onSelectAll → opts.visibility.setBulkVisible(true) + onSelectAllChange?.(true)
   - onSelectNone → opts.visibility.setBulkVisible(false) + onSelectAllChange?.(false)
   - onReset → opts.visibility.resetToDefault(...) + onResetRequested?.()
   - Bus + metrobüs checkbox'ları için exposed setter/sync (UI tutarlılık)
   ~30 satır

2. main.ts:
   - createRoutePanel({ ..., onSelectAllChange, onResetRequested })
   - Callback gövdeleri: busVisible/metrobusVisible mutation + debouncedApplyFleet()
     + routeFocus.setFocus(null)
   ~15 satır

3. route_panel.test.ts:
   - Yeni 3 case: Tümü/Hiçbiri/Reset callback tetikleme + checkbox UI sync
   ~25 satır
```

**Toplam ~70 satır.**

**Risk analizi:**

| Risk | Olasılık | Mitigation |
|---|---|---|
| Mevcut route_panel testleri kırılır | Düşük | Yeni callback'ler optional, eski case'ler etkilenmez |
| busVisible/metrobusVisible state diverge (UI vs. main.ts local) | Orta | Single source of truth bus checkbox değişiminde callback hep çalışır; ekstra: panel.setBusVisibility(v: boolean) public API exposing |
| routeFocus reset istenmeyen ortamda atılır (örn. focus aktifken Tümü tıklamak) | Düşük | UX kararı: focus aktifken global aksiyon → focus mantıklı olarak temizlensin (Yağız onayı) |
| Smoke testte hâlâ ghost cluster görünür | Orta | Eğer fix focus reset'i yetmezse, fix-up için debouncedApplyFocusPaint ekle (ek tur) |

**Test stratejisi:**
- Yeni `route_panel.test.ts` case: "Tümü/Hiçbiri/Reset → bus + metrobüs callback'leri tetiklenir, panel checkbox state senkron"
- Mevcut suite (258 test) geçmek zorunda
- Browser smoke (Yağız): "Hiçbiri" → bus + metro yok, focus aktif değil; "Reset" → tüm raylı+vapur+bus+metro açık, focus yok

---

## 5. ADIM 2 öncesi açık karar noktaları

Yağız'ın onaylaması/değiştirmesi gereken noktalar:

1. **routeFocus reset tetikleyicisi.** Tüm üç buton mu (Tümü/Hiçbiri/Reset),
   sadece Hiçbiri+Reset mi? Yoksa hiç mi (focus state ortagonal kalsın)?
   Önerim: üçü de — global aksiyon → temiz başlangıç.

2. **Buton etiket değişikliği** (Tümü/Hiçbiri/Reset → Hepsi/Hiçbiri/Sıfırla)
   gerekli mi? Önerim: dokunmayalım — Tasarım A semantik problemi davranışla
   çözüyor, etiket dokunulmaması diff'i daraltır.

3. **panel.setBusVisibility(bool) public API** ekleme — main.ts callback'lerden
   panel UI'sini senkron güncellemesi gerekiyor (kullanıcı bus checkbox'ı zaten
   true gösteriyor olabilir, "Hiçbiri" sonrası false olmalı). Bu küçük bir
   ek ama API yüzeyini büyütür. Önerim: ekle, alternatifi panel'den ref
   geri vermek karmaşık.

4. **debounce kapsamı.** Tasarım A'da onSelectAllChange callback'i
   `debouncedApplyFleet`'i kullanıyor zaten, ek şey yok. routeFocus.setFocus
   debounced değil — focus paint synchronous; aynı frame'de Kanal A
   debounced apply + Kanal B debounced apply + Kanal C sync paint:
   üç paint tick'i. Sorun çıkmazsa tutalım; çıkarsa Tasarım A v2'de
   focus paint'i de debounce'larız.

---

## 6. Özet

- KM-e mimari doğru ipte; donma gitti, KM-g üç UX bug'ı kaldı.
- Üç bug aynı kök: buton kapsamı sadece Kanal A; Kanal B (bus/metrobüs)
  ve Kanal C (focus) dokunulmuyor.
- Tasarım A önerilir: ~70 satır, geriye dönük uyumlu, mevcut testler
  korunur, yeni 3-4 case eklenir, mimari iki kanal kalır.
- Tasarım B v0.8.2'ye atılabilir bir refaktör; v0.8.1 yayın penceresinde
  riski mantıksız.
- Tasarım C revert; önerilmez.

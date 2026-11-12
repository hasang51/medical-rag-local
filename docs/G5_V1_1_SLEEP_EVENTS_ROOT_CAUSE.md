# G5 v1.1 — Kök neden: uyku olayı, fact satırı ve takvim penceresi

Tarih: 2026-11-12. Sorular: `Son iki uyku kaydım ne zaman?` ve `Dün gece kaç saat uyudum?` İlk vaka: `oracle-pilot-007`.

GPU yeniden çağrılmadı. Kaynak JSON, adaptör, SQLite, `IntentRouter`, `TemporalResolver.build_snapshot`, `EvidenceBuilder` ve `build_twin_messages` CPU üzerinde aynı sınıflarla yürüdü. Canlı model metni 12 Kasım benchmark kaydıdır. O yanıtın alıntıladığı `F318`, `F317`, `F303` ve `F302` bu turda üretilen promptun içindedir. SNOMED paketi bu ortamda olmadığı için bağlayıcı kavram eklemedi; uyku sorusu zaten `sleep` ailesine düşüyor, alıntılanan CCO kimlikleri terminoloji bloğundan önce geliyor.

`clinical_history_search` bu iki soruda çalışmadı. Geçmiş hastalık kapısı olduğu gibi duruyor.

## Hüküm

Kayıtlar kaybolmuyor. Sistem bir **uyku olayını** `(occurredFrom, occurredTo)` aralığı olarak tutmuyor. Her profil gününde aynı olayı yeni bir fact satırı olarak yeniden yazıyor, sonra bu satırları olay sanıp en yeni ikisini alıyor. Takvim sayaçları (`sleep.main.nights-2d`, `sleep.main.nights-3d`) olaydan daha yeni bir pencere sonuna sahip olduğu için listenin başına geçiyor. “Son iki kayıt” ile “son iki takvim gecesi” bu yüzden aynı torbaya düşüyor.

“Dün gece” hesabı sorunun sorulduğu andan yapılmıyor. Çapa, vakanın `evaluated_at` anıdır. “Dün” bu çapanın tek yerel gecesi değil, geriye üç günlük bir penceredir.

## Hipotezler

| ID | Hipotez | Sonuç |
|---|---|---|
| A | İki uyku olayı kaynakta yok | Reddedildi |
| B | Aynı olayın fact satırları ayrı olay sayılıyor | Doğrulandı |
| C | Önceki olay seçildi, 7500 karakter bütçesi sildi | Reddedildi |
| D | Önceki olay, canonical başına 2 satır ve 18 satırlık yürüyüşte seçilmeden kaldı | Doğrulandı |
| E | “Son iki kayıt”, “son iki takvim gecesi” sayacıyla karışıyor | Doğrulandı |
| F | “Dün gece” soru anından veya `cco_as_of` anından hesaplanıyor | Reddedildi |
| G | “Dün gece” çapanın tek yerel gecesidir | Reddedildi |

## 1. İki olay kaynakta var

`source_oracle-pilot-007.json` içinde `sleep` bölümü 78 değer satırı ve 67 `missingData` satırı taşır. Adaptör satır düşürmez: `source_index + 1` kuralıyla 145 takma ad üretir. SQLite `patient_facts` aynı 145 takma adı taşır. Eksik veya fazla satır yok.

`sleep.duration.last-main-sleep` için kaynakta, adaptörden önce, 15 başarılı satır vardır. Bu 15 satır 15 ayrı profil günü anahtarı taşır ve yalnız iki olay aralığına iner:

| Olay aralığı | Süre | Kaç fact satırı |
|---|---:|---:|
| 2026-09-29T01:54:00+03:00 .. 2026-09-29T07:56:58+03:00 | 346 dakika | 2 (`F249`, `F250`) |
| 2026-10-09T00:35:00+03:00 .. 2026-10-09T05:59:17+03:00 | 261 dakika | 13 (`F251`..`F263`) |

Aynı iki aralık süre, skor, verim, derin uyku ve uyanıklık satırlarında da ortaktır. 29 Eylül aralığı 10 canonical ve 2 profil gününe yayılmış 20 satırdır. 9 Ekim aralığı 13 profil gününe yayılır. Gün kovası `sleep.duration.day-total` (`F240`, 261 dakika, 2026-10-09T00:00 .. 2026-10-10T00:00) üçüncü bir uyku değildir; 9 Ekim olayını sivil güne yayar.

Vaka saatleri, hepsi `+03:00`:

| Alan | Değer |
|---|---|
| `evaluated_at` | 2026-10-24T12:00:00+03:00 |
| `exported_at` | 2026-10-21T14:51:36+03:00 |
| `cco_as_of` | 2026-10-20T10:02:00+03:00 |

`recordedAt` bu aralıkların sonundan günler sonradır. 9 Ekim olayının 21 Ekim profil günü kopyası `F263`, 2026-10-21T08:08:35+03:00 tarihinde yazılmıştır. Olay sabahı 9 Ekimdir.

## 2. Aynı olayın fact’leri ayrı olay sayılıyor

Olay kimliği kodda yok. Seçici grup anahtarı `canonical_id` (kodlu tanı ve ilaçta bir de `code`). Profil günü, olay aralığı ve kanıt kaynağı grup anahtarına girmez.

`build_snapshot` adayları `occurred_to`, sonra `source_index` azalan sırada yürür. Her canonical için en çok 2 satır alır, toplamda 18 satırda durur. 9 Ekim aralığının 13 süre satırı aynı `occurred_to` değerini taşır. Sıra `source_index` ile bozulur ve en yeni iki kopya, `F263` ile `F262`, 9 Ekim olayının 21 Ekim ve 20 Ekim profil günleridir. 346 dakikalık satırlar aynı canonicalin 14. ve 15. satırı olduğu için iki kişilik kotaya giremez.

Kanıt kaynağı da olay kimliği olamaz. `measurement-rollup.sleep-episode` takma adı `E91`, iki ayrı aralıkta birden geçer. Ortak kaynak kimliğiyle birleşim, 29 Eylül ile 9 Ekim’i tek olaya yapıştırır. Ayıran alan olay aralığıdır.

Sayı hesabı da satır sayar. `compute_numeric_stats`, `sleep.duration.last-main-sleep` için `sample_count = 15` der. Bu, iki olayın 15 ölçümü değildir. 13 kez yazılmış 261 ile 2 kez yazılmış 346’nın ortalamasıdır. Prompttaki `CALC-sleep-duration-last-main-sleep` bu hesabı taşır ve son değer olarak 261 dakikayı (`F263`) gösterir.

Aktif süzgeç kopyaları temizlemez. 15 süre satırının tamamı `export_status = active` ve `superseded_at` boştur. `supersedes` alanı dışa aktarımda olmayan `P*` öncüllere gider, kardeş profil gününe gitmez.

## 3. Retrieval önceki olayı neden getirmiyor

“Son iki uyku kaydım ne zaman?” yönü:

`intent=patient_exact_query`, `families=[sleep]`, `canonical_ids=[]`, `history` kapalı. “Son iki uyku” kalıbı `son ana uyku|son uyku` ipucuna girmez; arada “iki” vardır. Pencere etiketi “tüm aktif kayıtlar” olur, `since` boştur. Aday: 78 başarılı aktif uyku satırı.

346 dakikalık süre satırlarının sırası 67 ve 68’dir. 29 Eylül’e ait ilk satır 59. sıradadır (`F315`). Seçilen 18 satır bu sıraya gelmeden dolar. Seçilenlerde 29 Eylül aralığı yoktur.

Seçilen 18’in olay dağılımı:

| Seçilen | Ne |
|---|---|
| `F308`, `F307` | `nights-3d`, değer 0, takvim pencereleri |
| `F303`, `F302` | `nights-2d`, değer 0, takvim pencereleri |
| `F240` | 9 Ekim gün kovası, 261 dakika |
| `F209` | türetilmiş derin uyku serisi |
| `F318`+`F317`, `F313`+`F312`, `F296`+`F295`, `F284`+`F283`, `F263`+`F262`, `F221`+`F220` | hep 2026-10-09T00:35 .. 05:59:17; her canonicalin iki profil günü kopyası |

Kanıt üretici bu 18’in ilk 12’sini yazar. Tutulan iki süre satırı `F263` ve `F262` on beşinci ve on altıncı sıradadır; fact satırı olarak kanıta girmezler. 261 dakika prompta hesap satırı ve gün kovası `F240` ile gelir. 7500 karakterlik bütçe daha sonra `F296` ve eksik veri gruplarını keser. `F249` ve `F250` kesilen listede de yoktur; seçilmemişlerdi. Promptta 346 dakika ve 29 Eylül aralığı geçmez.

Canlı yanıt bu promptu okumuştur: birinci madde `F318` ve `F317` ile 9 Ekim 00:35–05:59, ikinci madde `F303` ve `F302` ile “son iki gece sayısı 0”.

Yüzük notu her iki süreyi de yazar ve 9 Ekim’i “son gece” diye adlandırır. Bu not “son iki kayıt” promptuna girmedi; bütçe `BEYAN-sleep-note` satırından önce doldu. Yapısal seçici notu zaten kullanmıyor.

## 4. Son iki kayıt ile son iki takvim gecesi

`sleep.main.nights-2d` sözlük etiketi “Son iki gecenin ana uyku sayısı”dır. Bu bir olay listesi değildir. Değeri, o profil gününün iki takvim günü boyunca kapanmış ana uyku adedidir.

Bu sayaçların `occurred_to` değeri uyku sabahından ileridedir. `F308` (`nights-3d`) 2026-10-22T00:00:00+03:00’te biter ve değer 0’dır. Sıralama olay aralığına göre olduğu için sayaçlar, 9 Ekim olayının önüne geçer. Soru “son iki kayıt” dediğinde yönlendirici ayrı bir operatör seçmez; recency yürüyüşü önce bu sayaçları koyar. Model, aynı olayın iki skor satırını bir dönem, değeri 0 olan sayaç çiftini ikinci kayıt sanır.

`is_derived_window_metric` bu sayaçları pencere türevi olarak işaretler. İşaret yalnız not metnine yazılır. Seçimden düşmezler ve olay kotasından sayılmazlar.

## 5. Dün gece hangi saatten hesaplanıyor

`resolve_window` çapa olarak `evaluated_at`, o yoksa `cco_as_of`, o da yoksa `exported_at` okur. Soru metninde saat yoktur. Fonksiyon süreç saatini okumaz. 12 Kasım benchmark anı ve `cco_as_of` (20 Ekim 10:02) bu hesabın çapası değildir.

Bu vakada çapa `2026-10-24T12:00:00+03:00` olur. “Dün”, “son gece” ve “bu gece” aynı kola girer ve `days = 3` yazar. Üretilen pencere:

`2026-10-21T12:00:00+03:00` .. `2026-10-24T12:00:00+03:00`

Bu, çapanın yerel önceki gecesi değildir. 24 Ekim öğleninden üç gün geriye giden bir aralıktır. İçinde başarılı tek satır vardır: `F308`, `nights-3d`, değer 0, pencere sonu 22 Ekim 00:00. İki uyku olayının `occurred_to` değeri bu `since` anından öncedir; pencere içi sıra listesinde ikisi de yoktur.

Pencere boş olmadığı için “boşsa tüm kayıtlara dön” kolu çalışmaz. 9 Ekim olayı “dün gece” diye içeri alınmaz. Bu vakanın 12 Kasım turu da bu yüzden önceki geceyi saat diye yazmadı: promptta süre satırı yok, `F308` var, bir de çok günlü `MISSING-sleep-duration-day-total` grubu var.

Eksik gruplar sorunun penceresine kesilmez. `data-required` gün kovaları 7 Ekimden 22 Ekime kadar tek grupta durur (`minimumSamples:1`). `sleep.efficiency.last-night` nedeni `stale-window` olan ve aralığı hâlâ 9 Ekim olan altı satırdır; ilk altı eksik gruba girmediği için promptta yoktur.

“Dün gece” promptuna yüzük notu girer. Not, 9 Ekim’i “son gece” diye adlandırır. Yapısal katman bunu “pencere dışı olay” diye işaretlemez. Bu vakada model notu dün gece diye aktarmadı. Başka vakalarda aynı kol, pencereye düşen veya geri dönüşle gelen eski olayı dün gece diye yazdırdı. Kök aynıdır: gece, çapanın tek yerel gecesi olarak tanımlanmıyor.

## Başlangıç katmanı

İlk yanlış karar yönlendiricidedir: “son N kayıt” ve “dün gece” ayrı okuma istemez, ailedeki recency anlık görüntüsüne gider. Kayıtlar bir sonraki katmanda düşer. Olay kimliği olmadığı için canonical başına iki satır, aynı olayın iki kopyasıdır. Takvim sayacının pencere sonu daha yeni olduğu için önceki olayın önüne geçer. Kanıt bütçesi bu eksik listenin üzerinde çalışır.

Bu, 29 Eylül ve 9 Ekim’e kilitli bir metin hatası değildir. Profil günü kopyası taşıyan her zaman serisinde “son N kayıt”, son N olay yerine son olayın N kopyasını ve serinin takvim sayaçlarını getirir.

## Operatörler

Yeni model, LoRA veya yeni depo yok. Mevcut SQLite ve yönlendirici üzerinde iki okuma. Üretim koduna vaka tarihi, 346 veya 261 yazılmaz. `clinical_history.py`, `query_coded_history` ve `HISTORY-EMPTY` sözleşmesi değişmez. Geçmiş kapısı açıksa bu operatörler çalışmaz. “Son ana uykum kaç dakika” mevcut tek metrik ipucunda kalır.

### Olay kimliği

Bir olay, türetilmiş pencere sayacı değildir. `is_derived_window_metric` ile işaretli canonical’ler (`nights-2d`, `nights-3d`, ortalama, bazal ve listedeki diğer pencere türevleri) olay kotasına girmez.

Olay anahtarı, ailenin türetilmemiş başarılı satırlarında `(occurred_from, occurred_to)` aralığıdır. Aynı aralıktaki her canonical için tek değer tutulur: en yeni `recorded_at`. Diğer profil günü kopyaları aynı özniteliktir. `evaluation_key` içindeki profil günü ve `recorded_at`, olay zamanı değildir.

Kanıt takma adı yardımcıdır, birleştirme anahtarı değildir. Aynı kaynak iki ayrı aralıkta geçebiliyor. Aralıklar farklıysa olaylar ayrı kalır.

Sivil gün kovası (`occurred_from` ve `occurred_to` yerel gece yarısı, canonical gün toplamı) bir alt aralık olayıyla aynı günü anlatıyorsa ikinci olay sayılmaz. Ailede alt aralık olayı yoksa gün kovası, o ailenin olay tanesidir. Böylece adım veya günlük toplam serileri de aynı operatörü kullanır.

`data-required` satırı aynı aralığa eksik öznitelik olarak yapışır. Sıfır olay veya ek olay olmaz.

Sıra `occurred_to`, sonra `occurred_from` iledir. Saatlerin kendi `+03:00` ofseti korunur. UTC’ye indirip gün kaydırmak yok.

### `last_n_events`

Tetik: “son N kayıt”, “son N olay”, “son N ölçüm” ve aynı kalıbın uyku, adım, nabız gibi bir aileye bağlanması. N sorudan okunur. Tek isimli metrik sorusu (“son ana uyku”) bu operatöre girmez.

Okuma, 18 satır tavanını ve canonical başına 2 satır kuralını kullanmaz. Tavan N olaydır. Her olay, ölçü canonical’i ve aynı aralıktaki kardeş özniteliklerle döner. İstenen ailede takvim sayacı varsa o sayaç sonuç listesine olay diye yazılmaz; kendi penceresiyle ayrı bir metrik satırı olarak durabilir.

### `events_in_window`

Tetik: “dün gece”, “son gece”, “bu gece”, “dün”, “son N gün” ve olayın o aralıkta istenmesi. Hazır ortalama canonical’i (“7 günlük uyku ortalaması”) bugünkü metrik yolunda kalır.

Çapa yine `evaluated_at`, yoksa `cco_as_of`, yoksa `exported_at`. Soru anı ve süreç saati kullanılmaz. Ofset, çapa damgasının ofsetidir.

“Dün gece”, “son gece” ve “bu gece” üç gün değildir. Çapanın yerel sivil günü D ise pencere, D−1 günü yerel öğlen ile D günü yerel öğlen arasındaki yarı açık aralıktır. Öğleden sonra sorulan bir gecenin sabah bitişi bu aralığa girer. İki sabah önceki olay girmez. “Dün” tek başına, uyku gecesi değilse, önceki yerel sivil gündür. “Son N gün”, çapadan N gün geriye olay aralığının pencereyle kesişmesidir.

Üyelik olay zamanınadır. Profil günü anahtarı “dün” sayılmaz. 21 Ekim profil gününe yazılmış 9 Ekim uykusu, 24 Ekim çapasından bakınca dün gece değildir.

Pencerede olay yoksa kanıt `EVENTS-EMPTY` olur: pencere, çapa ve “bu aralıkta olay yok”. Son olaya geri düşülmez. Son olay ayrıca yazılacaksa etiketi “pencere dışı”dır ve istenen gecenin süresi olamaz. Penceredeki `data-required` satırı eksik veridir, süre 0 değildir. `nights-2d = 0` bir olay süresinin yerine geçmez.

### Kabul

Sentetik fixture. Üretim kodunda vaka tarihi yok. `FakeOllama` gerekmez; kanıt listesi yeter.

- Yeni olay birkaç profil gününde tekrar yazılmış, daha eski ayrı bir aralık duruyorsa `last_n_events(2)` iki aralığı birer kez döndürür. İkinci kota, yeni olayın ikinci kopyasına gitmez.
- Pencere sonu daha yeni olan `nights-2d = 0` bu iki olaydan biri olmaz.
- Çapanın yerel önceki gecesinde olay yoksa yanıt `EVENTS-EMPTY` olur. Daha yeni diye içeri alınan eski aralık, o gece diye etiketlenmez.
- Penceredeki `data-required` satırı eksik kalır, süre 0 yazılmaz.
- `recorded_at` sırası olay sırasını değiştirmez.
- “Daha önce mide rahatsızlığım olmuş mu?” kodlu geçmiş kolunda kalır.
- “Son ana uykum kaç dakika sürdü?” tek metrik kolunda kalır.

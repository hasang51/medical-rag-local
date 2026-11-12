# G5 v1.1 — Kök neden: geçmiş hastalık sorgusu

Tarih: 2026-11-12. Soru: `Daha önce mide rahatsızlığım olmuş mu?` Vaka: `oracle-pilot-006`.

Bu turda model, kayıtlı reflü, özofajit, peptik ülser ve gastrit varken “mide tanısı yok” dedi. GPU yeniden çağrılmadı. Katmanlar CPU üzerinde `DigitalTwinService.prepare_turn` ile yürüdü. Model metni, 12 Kasım canlı benchmark kaydıdır (`eval_count=160`). Aynı metin, bu turda üretilen izinli alıntı listesiyle doğrulayıcıdan tekrar geçirildi.

İz env değişkeni `MEDICAL_RAG_DEBUG_TRACE=1` iken yazılır. Kapalıyken API yanıtı değişmez. Ayrıntılı takma ad listesi `data/runtime/g5-v1-1/gi-layer-trace.json` içindedir.

## Hüküm

Hata **niyet yönlendiricide** başlar ve **zaman çözümleyicinin kapsamsız 18 kayıt tavanında** kayıtları düşürür. Kanıt bütçesi bu kayıtları elemedi; kayıtlar kanıt listesine hiç girmedi. Modele giden bağlamda mide tanısı, gastroskopi veya ilgili ziyaret yoktu. Doğrulayıcı, yanlış yokluk cümlesini kabul etti çünkü cümlenin doğru olup olmadığına bakmıyor; listede olan bir alıntı yeter.

## Hipotezler

| ID | Hipotez | Sonuç |
|---|---|---|
| A | “Mide rahatsızlığı” tanı ailesine ve SNOMED kavramına bağlanmıyor; sorgu tüm ailelerde “en güncel kayıt” oluyor | Doğrulandı |
| B | Mide tanıları aday listesinde var, `max_total_facts=18` onları kesiyor | Doğrulandı |
| C | Kayıtlar seçildi, 7500 karakter bütçesi onları kesti | Reddedildi |
| D | Kayıtlar prompttaydı, model yok saydı | Reddedildi |
| E | Doğrulayıcı, yokluk iddiasını alıntı var diye geçiriyor | Doğrulandı |

## 1. Kaynak JSON ve SQLite

`source_oracle-pilot-006.json` ile `patient_facts` aynı beş aktif tanıyı taşıyor. Eksik veya fazla satır yok.

| Takma ad | Kod | Görünen ad | Olay sonu |
|---|---|---|---|
| F272 | K29.6 | Gastritler, diğer | 2024-04-19 |
| F268 | K20 | Özofajit | 2024-04-19 |
| F271 | K27.3 | Akut peptik ülser | 2024-04-19 |
| F270 | K27 | Peptik ülser, yeri tanımlanmamış | 2020-01-22 |
| F269 | K21.9 | Gastro-özofajial reflü, özofajitsiz | 2017-10-26 |

Aynı Nisan 2024 bandında, kod sütunu boş olan ilişkili satırlar da duruyor: patoloji F345, görüntüleme F315, muayene F614 ve F613. Veri kaybı yok. Hata okuma katmanında.

## 2. Yönlendirici

Çalışma kaydı:

`intent=patient_exact_query`, `families=[]`, `canonical_ids=[]`, `concept_ids=[]`, `personal_cue=false`, `corpus_hits=true`, `family_rule_hit=false`.

Kurallar neden boş kaldı:

- Tanı kalıbı `tanı|teşhis|hastalık|ikd|icd|aile öykü` ister. “Rahatsızlık” ve “olmuş mu” eşleşmez.
- Sözlükte mide için yalnız “midem bulan” ve “karın ağrısı” vardır. “Mide rahatsızlığı” kavram üretmez.
- Kişisel ipucu kalıbında “daha önce” veya “olmuş” yoktur.
- BM25 `sindirim-0` parçasını bulduğu için soru kapsam dışı sayılmaz.
- Aile listesi boş kalınca dal `patient_exact_query` olur.
- `prepare_turn`, boş listeyi `or None` ile **filtresiz** sorguya çevirir.

Yani “daha önce oldu mu?” sorusu, tüm ailelerin en yeni ölçümünü isteyen bir operatöre gider.

## 3. Adaylar ve tavan

Başarılı aktif aday: **309**. Mide kodlarının depo sırası:

| Sıra | Takma ad | Kod |
|---:|---|---|
| 258 | F272 | K29.6 |
| 259 | F268 | K20 |
| 260 | F271 | K27.3 |
| 291 | F270 | K27 |
| 300 | F269 | K21.9 |

Seçilen: **18**. Seçilen mide tanısı: **0**. İlk mide sırası 258, tavan 18. Seçilen aile dağılımı: uyku 4, veri 5, hidrasyon 2, aktivite 3, ziyaret 1, ilaç 1, glukoz 1, tanı 1.

O tek tanı satırı `diagnosis.definitive-count` (F255). Kodlu tanı değil, bir sayaç.

İlişkili Nisan 2024 patoloji, görüntüleme ve muayene satırları da 250. sıranın ötesindedir. Onlar da 18’e girmez.

Karşı olgu: yalnız `diagnosis` ailesinin ilk 18 satırında F272, F268, F271 ve F270 vardır. F269 (2017 reflüsü) yine dışarıda kalır. Aileyi daraltmak dört kodu kurtarır, geçmiş araması yapmaz. Eski kod, “en yeni 18 tanı” tavanının altında kalır.

Kayıtların düştüğü yer burasıdır.

## 4. Kanıt üretici ve bütçe

CCO katmanı bütçesi 6280 karakter, kullanılan 5972. İçeri alınan kimlikler sayaçlar ve yeni giyilebilir satırlardır: `CALC-diagnosis-definitive-count`, `F311` ve benzerleri.

Bütçe yüzünden elenenler: `F63`, `F615` ve dört aktivite `MISSING` grubu. Mide takma adı bu listede yoktur; çünkü seçilmemişlerdi.

Genel katman 1100 karakter hakkının 312’sini kullandı. Tek parça: `sindirim-0`. Bu kişisel kayıt değildir.

Prompt uzunluğu 6286 karakter. `F268`, `F269`, `F270`, `F271`, `F272` metinde yok.

## 5. Modele giden bağlam

Bağlamda kodlu mide tanısı ve Nisan 2024 gastroskopi kanıtı yoktur. Vardır:

- kesin tanı **sayısı**
- su hedefi `F311`
- genel sindirim sözlüğü `sindirim-0`

Canlı yanıt bu üç alıntıyı kullanıp “mide tanısı bulunmamaktadır” ve “sindirim sistemiyle ilgili bulgu saptanmamıştır” dedi. Model, önündeki satırları yok saymadı. Önünde o satırlar yoktu. Sayaç ile kodlu tanıyı karıştırdı ve sözlük cümlesini kişisel yokluk kanıtı gibi kullandı.

## 6. Doğrulayıcı

Aynı yanıt, bu turdaki 23 izinli kimlikle `enforce_twin_contract` içinden geçti.

`abstained=false`, `role_blocked=false`, `matched_citation_count=3`, `absence_language=true`, `checks_claim_truth=false`.

Eşleşen sonekler: `CALC-diagnosis-definitive-count`, `F311`, `sindirim-0`.

Doğrulayıcı iki şeye bakar: izinli bir kimlik metinde var mı, doktor rolü veya doz talimatı var mı. “Bu hastalık yok” cümlesinin, alıntılanan satırın gerçekten o yokluğu söyleyip söylemediğini ölçmez. Sayaç ve sözlük parçası, yanlış yokluk cümlesini içeri alır.

## Başlangıç katmanı

İlk yanlış karar yönlendiricidedir: geçmiş hastalık sorusu tanı aramasına bağlanmaz. Kayıtlar bir sonraki katmanda, filtresiz recency tavanında düşer. Kanıt bütçesi, model ve doğrulayıcı bu eksik bağlamın üzerine çalışır. Doğrulayıcı hatayı durdurmaz.

Bu, vaka 6’ya özel bir metin hatası değildir. “Daha önce X olmuş mu?” kalıbı aile ve kavram seçemezse her eski kodlu tanı aynı 18’lik giyilebilir pencerenin altında kalır.

## Önerilen operatör: `clinical_history_search`

Yeni model, LoRA, Neo4j veya embedding yok. Mevcut SQLite ve yönlendirici üzerinde ikinci bir okuma operatörü.

Tetik: “daha önce”, “olmuş mu”, “geçirdim”, “öykü”, “geçmiş” veya bugün ölçülemeyen bir hastalık/organ sorusu. Tek bir güncel laboratuvar veya uyku metriği sorusu bu operatöre girmez.

Okuma:

1. Sorudaki organ veya yakınma, mevcut Türkçe sözlük ve SNOMED bağından bir kod bölümüne veya aile kümesine gider (sindirim için tanı kodları K2–K3 ve bağlı muayene, görüntüleme, patoloji). Eşleşme kuralı vaka adına veya “gastrit” kelimesine kilitlenmez.
2. Depo, o kümede **tüm aktif kodlu satırları** olay zamanına göre döndürür. “En yeni 18 kayıt, aile fark etmez” kuralı bu operatörde kullanılmaz.
3. Her kod için güncel satır, ön tanı veya kesin tanı ayrımı ve olay aralığı kanıt olur.
4. Hiç satır yoksa kanıt açık bir boş geçmiş öğesidir: “bu aramada kodlu kayıt yok”. Kesin tanı sayacı veya genel sözlük, yokluk kanıtı sayılamaz.
5. Doğrulayıcı, yokluk cümlesini ancak bu boş geçmiş öğesi alıntılanmışsa geçirir. Başka bir CCO kimliği yetmez.

Kabul testleri, FakeOllama ile, GPU’suz:

- İki yaşta kodlu tanısı olan sentetik bir vakada geçmiş sorusu, yeni giyilebilir satırlar daha güncel olsa bile o tanı kimliklerini bağlama koyar.
- Yalnızca `diagnosis.definitive-count` içeren bağlam, “bu tanı yok” cümlesini geçiremez.
- Aramada satır yoksa yanıt, uydurma hastalık yazmadan boş geçmiş öğesini kullanır.
- `case_id` olmayan genel sözlük turu ve acil kestirme aynı kalır.
- 2017 gibi eski bir kod, “son 18 tanı” dışında kalsa bile arama süzgecine girer.

Operatör kodda `clinical_history_search` olarak duruyor. Geçmiş sorusu kod bölümündeki tanıları recency tavanının dışından da bağlama alır. Yokluk cümlesi ancak `HISTORY-EMPTY` alıntısıyla geçer.

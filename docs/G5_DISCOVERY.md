# Medical Digital Twin G5 — Keşif Raporu ve v1 Uygulama Spesifikasyonu

Bu belge, `medical-rag-local` çalışma alanına eklenen iki veri paketinin (`base_cco_reading_tables_colab_20261027-*` ve `SnomedCT_IPS_Terminology_2024`) salt-okunur incelenmesi, mevcut kod tabanının mimari analizi ve çalıştırılan başlangıç test sonuçlarına dayanarak hazırlanmıştır. Rapor içinde hiçbir ham hasta verisi, opak kimlik (UUID), kimlik doğrulama anahtarı veya toplu lisanslı terim dökümü yer almaz.

---

## 1. Gerçek Dosya Envanteri ve Tespit Edilen Veri Şemaları

### 1.1 Veri Paketlerinin Gerçek Yolları ve Arşiv Bütünlüğü

Her iki veri paketi de çalışma alanı kök dizininde iç içe klasörler halinde açılmış (unzipped) durumdadır; kaynak paketlerdeki hiçbir dosya değiştirilmemiştir:

1. **CCO Okuma Tabloları ve Colab Deney Paketi**
   - **Gerçek kök yol**: `base_cco_reading_tables_colab_20261027-20261112T081149Z-1-001/base_cco_reading_tables_colab_20261027/`
   - **İç arşiv 1**: `cco_reading_tables_inputs_20261027.zip` (`5,937,622` bayt, `87` girdi) -> `package/` dizinine birebir açılmıştır (`bundle_manifest.json` içindeki `87` dosyanın tamamında SHA256 uyuşmazlığı: `0`, ZIP-dizin farkı: `0`).
   - **İç arşiv 2**: `runs/reading_tables_40_v1/base_fact_server_results.zip` -> `runs/reading_tables_40_v1/` dizinine birebir açılmıştır (`92` girdi, ZIP-dizin farkı: `0`).
   - **Üst dizin yardımcı dosyaları**:
     - `INSPECT_READ_ME_TR.md` ve `INSPECT_sleep_hrv_examples.json`: Anonimleştirilmiş uyku/HRV inceleme örnekleri ve örnekleme sıklığı notları.
     - `RUN_GUIDE_TR.md` ve `base_cco_reading_tables_20261027.ipynb`: `1` markdown + `7` kod hücresinden oluşan (kayıtlı hücre çıktısı `0`) Colab A100 yürütme defteri.
     - Çalışma zamanı üst verileri: `model_identity.json`, `model_job.json`, `runtime.json`, `serving_process.json`, `gpu_sampler_process.json`, `vllm_private.log`.
   - **`package/` içeriği (`87` manifest-doğrulamalı dosya)**:
     - `source_oracle-pilot-001.json` .. `source_oracle-pilot-020.json`: `20` vakanın tam özgün CCO özeti (`original_cco`) ve yerel projeksiyon arşivi (`local_projection`).
     - `model_oracle-pilot-001.json` .. `model_oracle-pilot-020.json`: `20` vakanın kayıpsız tablo görünümü (`format: "cco-reading-tables/1"`).
     - `reading_oracle-pilot-001.txt` .. `reading_oracle-pilot-020.txt`: `20` vakanın seyrek TSV metin görünümü (`@DOCUMENT`, `@GUIDE`, `@MAP`, `@BLOCK`, `@FAMILY`, `@COLUMNS`, `@END`).
     - `audit_oracle-pilot-001.json` .. `audit_oracle-pilot-020.json`: `20` vakanın opak kimlik eşlemesi ve geri-kurulum doğrulama yan dosyası (`format: "cco-reading-tables/1/audit"`).
     - `requests.jsonl`: `40` dondurulmuş değerlendirme isteği (`20` vaka x `raw` ve `fact_view` kolları).
     - Yardımcı ve doğrulama dosyaları: `bundle_manifest.json`, `scope.json`, `source_reconstruction.json`, `local_token_counts.json`, `preprocessor_source.py`, `eval_base_fact_server.py`, `README.md`.
   - **`runs/reading_tables_40_v1/` deney çıktıları (değiştirilmeyecek 40 tarihsel yanıt)**:
     - `answers/oracle-pilot-001..020__{raw,fact_view}.json`: `40` tamamlanmış model yanıtı (`status: "ok"`, `finish_reason: "stop"`, tamamlama token aralığı `214..627`, süre `1.59..145.60 sn`) ve `40` adet `.pending.json` iz kaydı.
     - `summary.json` (`expected: 40, completed: 40, all_ok: true`), `admission.json` (`context_limit: 232448`, `raw` istem token aralığı `322..9,656`, `fact_view` istem token aralığı `1,087..230,406`), `manifest.json`, `request_bodies.json`, `runtime.json` (`NVIDIA A100-SXM4-80GB`, `vllm 0.20.2`, `cyankiwi/gemma-4-26B-A4B-it-AWQ-4bit`), `launch_config.json`, `input_scope.json`, `gpu_memory.csv`, `pip_freeze.txt`, `vllm_private.log`.

2. **SNOMED CT IPS Terminology (2024 Snapshot)**
   - **Gerçek kök yol**: `SnomedCT_IPS_Terminology_2024/SnomedCT_IPSTerminologyRelease_PRODUCTION_20241216T120000Z/`
   - **Dosya envanteri (`11` dosya, RF2 Snapshot TSV)**:
     - `Readme_en_20240701.txt` (CC BY 4.0 lisans ve dizin açıklaması)
     - `Snapshot/Terminology/sct2_Concept_IPSSnapshot_IPST_20240701.txt` (`19,697` veri satırı)
     - `Snapshot/Terminology/sct2_Description_IPSSnapshot-en_IPST_20240701.txt` (`60,114` veri satırı)
     - `Snapshot/Terminology/sct2_TextDefinition_IPSSnapshot-en_IPST_20240701.txt` (`408` veri satırı)
     - `Snapshot/Terminology/sct2_Relationship_IPSSnapshot_IPST_20240701.txt` (`66,017` veri satırı)
     - `Snapshot/Terminology/sct2_RelationshipConcreteValues_IPSSnapshot_IPST_20240701.txt` (`4,086` veri satırı)
     - `Snapshot/Terminology/sct2_sRefset_IPSOWLExpressionSnapshot_IPST_20240701.txt` (`19,882` veri satırı)
     - `Snapshot/Refset/Language/der2_cRefset_IPSLanguageSnapshot-en_IPST_20240701.txt` (`115,788` veri satırı)
     - `Snapshot/Refset/Content/der2_Refset_IPSSimpleSnapshot_IPST_20240701.txt` (`12,930` veri satırı)
     - `Snapshot/Refset/Metadata/der2_cciRefset_IPSRefsetDescriptorSnapshot_IPST_20240701.txt` (`14` veri satırı)
     - `Snapshot/Refset/Metadata/der2_ssRefset_IPSModuleDependencySnapshot_IPST_20240701.txt` (`1` veri satırı)

---

### 1.2 CCO Veri Şeması ve Alan Eşleştirmesi

Her `source_oracle-pilot-NNN.json` dosyası üst düzeyde iki nesne içerir:
- `original_cco`: `{asOf: str, id: str, subjectId: str, text: str}`
- `local_projection`: `{format: "cco-local-projection/1", subject_id: str, evaluated_at: str, exported_at: str, api_equivalence: "not_established", target_reading_contract: "CCO 0.7.0", historical_reconstruction: bool, unavailable_native_fields: list[str], consent: dict, export_metadata: dict, limits: dict, summary: dict, glossary: {facts, families, rules}, glossary_provenance: dict, sections: dict}`

`20` vakanın `18`'inde (`oracle-pilot-001`..`018`) `16` bölüm ailesine (`sleep`, `cardio`, `activity`, `data`, `hydration`, `recovery`, `wellness`, `lab`, `oxygen`, `medication`, `diagnosis`, `visit`, `vitals`, `imaging`, `glucose`, `pathology`) yayılmış toplam **`13,788`** yapısal satır (`8,617` `facts` + `5,171` `missingData`), son `2` vakada (`oracle-pilot-019`, `oracle-pilot-020`) ise **`0`** yapısal satır yer alır.

İstenen alanların gerçek şemadaki tam karşılıkları:

| İstenen Alan | Gerçek Şemadaki Konumu ve Türü | Doğrulanan Yapı ve Kapsam |
|---|---|---|
| **Subject ID** | `local_projection.subject_id` ve `original_cco.subjectId` (`str`) | Her vakada birbiriyle özdeş 36 karakterlik opak kimlik; `20` vakada `20` tekil hasta. `model_*.json` içinde `~ia` olarak maskelenir; API/arayüzde yalnız `oracle-pilot-001..020` vaka kimliği kullanılır. |
| **`factId`** | `row.factId` (`str`) | Tüm `13,788` satırda mevcuttur. `model_*.json` içinde `provenance.source_index + 1` kuralıyla `F1..Fn` olarak kısaltılır. |
| **`definition`** | `row.definition` (`str`) + `row.evaluationKey` (`str`) + `glossary.facts` | `<canonicalId>\|<version>` formatındadır (`169` benzersiz sürümlü tanım). Pencere/örnek kapsamı `evaluationKey` ile ayrışır (`profile-day:<YYYY-MM-DD>`: `13,110`, `latest`: `140`, `code:tr-drug-barcode:<N>`: `103`, `code:icd-10:<KOD>`: `95`, `sample:...`: `340`). |
| **`value`** | `row.value` (`dict \| null`) | `facts` altındaki `8,617` satırda dolu nesne (`quantity`/`count`/`percentage`: `8,312`, `coded`: `198`, `narrative`: `107`), `missingData` altındaki `5,171` satırda `null`. |
| **`unit`** | `row.value.unit` (`str`) ve `row.comparisons[].unit` (`str`) | Satır üst düzeyinde **yoktur**; `value` nesnesi içindedir (`35` birim: `minute`, `count`, `percent`, `%`, `bpm`, `millisecond`, `step`, `milliliter`, `score`, `minute-of-day`, `hour`, `celsius`, `mg/dL`, `mmHg`, `g/dL`, `10^3/uL`, `mL/min/1.73m2`, `kg`, `cm`, `code`, `text` vb.). |
| **`occurredAt`** | Satırda `row.occurredFrom` & `row.occurredTo` (`str`); kanıtta `row.evidence[].occurredAt` (`str`) | Satır üst düzeyinde tekil `occurredAt` **yoktur**: `13,187` satır aralık (`occurredFrom < occurredTo`), `601` satır nokta olay (`occurredFrom == occurredTo`) taşır; ayrıca `row.validUntil` (`70` satırda dolu) vardır. Tekil `occurredAt` alanı `83,909` kanıt (`evidence[]`) nesnesinin tamamında bulunur. |
| **`recordedAt`** | `row.recordedAt` (`str`, ISO-8601) | Tüm `13,788` satırda bulunur; değerlendiricinin (`evaluator/1.0.0`) kaydı ürettiği zamandır, klinik olay veya uyku başlangıcı zamanı değildir. |
| **`provenance`** | `row.provenance` (`dict`) | Sabit 6 anahtar: `source_index`, `source_row_sha256`, `nested_value`, `legacy_value_fields` (`{flag, narrative, amount}`), `auxiliary_fields` (`{constraints, missingData}`), `export_fields` (`{engineVersion, nextEvaluationAt, status, supersedeReason, supersededAt, supersedesFactId, validFrom}`). |
| **`evidence`** | `row.evidence` (`list[dict]`) | Toplam `83,909` kaynak referansı; her öğe `{occurredAt, role: "source", sourceId, sourceType}` yapısındadır (`55` farklı `sourceType`: giyilebilir günlük/saatlik rollup'lar, `emr.visit-diagnosis`, `emr.prescription-drug`, `emr.visit-examination`, `emr.radiology-report`, `lab.*`, `measurement.*`). |
| **`missingData`** | `sections[<family>].missingData` + `row.provenance.auxiliary_fields.missingData` (`list[str]`) | `5,171` satır `evaluationStatus: "data-required"` ve `value: null` taşır; `auxiliary_fields.missingData` altında `6,761` gereksinim nedeni (`minimumSamples:<N>`, `personal-baseline`, `personal-record`, `recentSamples:...`, `previous-period`, `sleep_closed`, `stale-window`, `reference:...`) yer alır. |
| **`supersession`** | `row.provenance.export_fields` + `row.source_issues` | Tüm `13,788` satırda `status: "active"` ve `supersededAt: null` durumdadır (`scope: "current-active-consent-visible"`). `6,210` satır önceki bir kaydı ezmiştir (`supersedesFactId != null`, `supersedeReason`: `data-correction` [`3,146`] veya `data-arrival` [`3,064`], `source_issues` içinde `"predecessor_not_in_export"`). |

---

### 1.3 SNOMED CT IPS 2024 RF2 Doğrulaması

- **Aktif Kavramlar (`sct2_Concept`)**: `19,697` satırın tamamı aktiftir (`active = '1'`, `moduleId = '999991001000101'`, `10,896` Primitive `900000000000074008`, `8,801` Defined `900000000000073002`). `der2_Refset_IPSSimpleSnapshot` içinde `816080008 |International Patient Summary|` refset altında `12,930` aktif satır ve `12,899` tekil aktif kavram bulunur.
- **Açıklamalar ve Dil Kapsamı (`sct2_Description` + `der2_cRefset_IPSLanguageSnapshot-en`)**:
  - `60,114` aktif açıklamanın tamamı **`languageCode = 'en'`** (`19,697` FSN `900000000000003001` + `40,417` Synonym `900000000000013009`) ve `408` `TextDefinition` satırının tamamı İngilizcedir. Pakette Türkçe (`tr`) açıklama satırı bulunmamaktadır.
  - Dil refset'i `115,788` aktif satır içerir: US English (`900000000000509007`: `57,868`) ve GB English (`900000000000508004`: `57,920`); kabul edilebilirlik: `Preferred` (`900000000000548007`: `79,490`) ve `Acceptable` (`900000000000549004`: `36,298`).
- **İlişki Türleri (`sct2_Relationship` + `sct2_RelationshipConcreteValues`)**:
  - `66,017` aktif çıkarımsal ilişki (`characteristicTypeId = '900000000000011006'`), **`70` farklı `typeId`** içerir. En sık görülenler: `116680003 |Is a|` (`32,111`), `363698007 |Finding site|` (`5,497`), `116676008 |Associated morphology|` (`3,818`), `260686004 |Method|` (`2,407`), `363714003 |Interprets|` (`1,988`), `118169006 |Specimen source topography|` (`1,423`), `405813007 |Procedure site - Direct|` (`1,190`), `762949000 |Has precise active ingredient|` (`1,181`), `127489000 |Has active ingredient|` (`976`), `363713009 |Has interpretation|` (`870`), `42752001 |Due to|` (`530`).
  - `ConcreteValues` tablosunda `6` `typeId` altında `4,086` aktif sayısal ilaç bileşen/güç satırı yer alır.
- **`Headache` Kavramının Doğrulanması (`25064002`)**:
  - Aktif kavram: `25064002`, `active = 1`, IPS Simple Refset üyesi (`True`), FSN: `Headache (finding)`, Tercih edilen terim: `Headache`, Eşanlamlılar: `Head pain`, `Cephalalgia`, `Cephalgia`, `Cephalodynia`, `HA - Headache`, `Pain in head`.
  - Çıkan aktif ilişkiler (`3`): `Is a (116680003) -> 22253000 |Pain (finding)|`, `Is a (116680003) -> 406122000 |Head finding (finding)|`, `Finding site (363698007) -> 69536005 |Head structure (body structure)|`.
  - Gelen aktif ilişkiler: `14` doğrudan alt kavram (`Tension-type headache 398057008`, `Vascular headache 128187005`, `Chronic headache disorder 431237007`, `Frontal headache 267096005`, `Occipital headache 330007`, `Sinus headache 4969004`, `Cervicogenic headache 279016001`, `Orthostatic headache 445511002`, `Posttraumatic headache 54012000` vb.).

---

## 2. Baseline Test Sonuçları ve Mevcut API Sözleşmesi

### 2.1 Başlangıç Test Sonuçları
- **Komut**: `uv run pytest -v -p no:cacheprovider`
- **Sonuç**: `31` test toplandı, `1` canlı model duman testi (`test_live_smoke_records_memory`, `@pytest.mark.ollama`) varsayılan ayarlarla ayrıldı, **`30` test çalıştı: `30 PASSED`, `0 FAILED`** (`4.05s`).
- **Uyarı**: `1` adet `StarletteDeprecationWarning` (`starlette.testclient` `httpx` uyarısı).

### 2.2 Mevcut API Sözleşmesi
- `GET /health` -> `HealthResponse { status: "ok" | "degraded", ollama: "ok" | "unreachable", model: str }`
- `POST /v1/complete` -> `CompleteRequest { prompt: str (1..500) }` -> `CompleteResponse { text, model, num_ctx, eval_count, eval_duration_ns, total_duration_ns }`
- `POST /v1/chat` -> `ChatRequest { question: str (1..500), top_k: int (1..5, default=3) }` -> `ChatResponse { answer, citations, abstained, disclaimer, eval_count, eval_duration_ns, total_duration_ns, done_reason, latency_ms, retrieved_chunk_ids, load_duration_ns, prompt_eval_count, prompt_eval_duration_ns }`

---

## 3. Mevcut Sistemin Mimarisi ve Digital Twin Hedefine Göre Eksikleri

1. **Hasta Durumu ve Kesin Hesaplama Katmanı Yok**: `data/corpus/` altındaki `22` tek paragraflık eğitim metninden ibaret bellek içi `BM25Okapi` dizini kullanılıyor; SQLite tabanlı vaka deposu, tarih penceresi çözümleme veya deterministik min/max/ortalama/son kayıt sorgusu yok.
2. **Model Öncesi Acil Durum Denetimi Yok**: `safety/policy.py` yalnız model yanıt üretildikten sonra alıntı ve rol kontrolü yapıyor; akut kırmızı bayrak semptomlarını modelden önce yakalayan deterministik güvenlik kapısı bulunmuyor.
3. **Sözlük Politikası ile Kişisel Kayıt Çatışması**: Mevcut `SYSTEM_PROMPT` kişisel ölçüm bilgisini reddediyor ve `policy.py` içindeki `\d+\s*mg` deseni hastanın kendi CCO kaydındaki laboratuvar (`mg/dL`) veya reçete değerlerinin kanıtlı aktarımını bile engelliyor.
4. **SNOMED Terminoloji ve Türkçe Semptom Köprüsü Yok**: Türkçe semptom ifadelerini aktif SNOMED CT IPS kavramlarına ve CCO bölüm ailelerine bağlayan bir terminoloji katmanı mevcut değil; `rag/text.py` tek karakterli klinik belirteçleri (`Tip 1/2`, `D`, `A/B/0`) eliyor.
5. **Bilgi Katmanları Ayrışmıyor**: Yanıt şeması ve arayüz hasta verisini (`CCO`), terminolojik kavram bilgisini (`SNOMED`) ve genel eğitim bilgisini (`GENEL`) birbirinden ayırmıyor.

---

## 4. Veri Kapsamı, Lisans ve Bütünlük Riskleri

1. **Git ve Yerel Gizlilik Koruması**: `.gitignore` içine her iki veri paketi ve yerel SQLite veritabanları eklenerek yanlışlıkla versiyon kontrolüne girmesi engellenir; API ve loglarda opak `subjectId`/`factId` değerleri ile ham soru/yanıt metinleri kesinlikle yazılmaz.
2. **`local_projection` ile `original_cco.text` Kapsam Farkı**: Yapısal `local_projection` içinde yer almayan hasta beyanı bölümleri (`## Kullandığı ilaçlar (hasta beyanı)`, `## Hastalıklar (hasta beyanı)`, `## Aile öyküsü (hasta beyanı)`, `## Alerjiler (hasta beyanı)`, `## Ameliyat ve işlemler`, `## Bilinmeyenler`) `original_cco.text` içinden `cco_narrative` kaynağı olarak ayrıştırılarak veri kaybı önlenir.
3. **Türetilmiş Ölçüm, Zaman ve Eksik Veri Kuralları**:
   - `oracle-pilot-019` ve `020` sıfır yapısal satırlı vakalardır; sistem veri yokluğunu açıkça bildirir.
   - `sleep.*` ve `cardio.hrv.*` günlük/seanslık türetilmiş özetlerdir; 5 dakikalık ham seri varsayılmaz ve saatlik alt kırılıma bölünmez.
   - Olay zamanı için `occurredFrom`/`occurredTo`, kanıt zamanı için `evidence[].occurredAt` kullanılır; `recordedAt` olay başlangıcı olarak yorumlanmaz.
   - `evaluationStatus == "data-required"` (`value == null`) kayıtları sıfır veya normal sayılmaz; `auxiliary_fields.missingData` nedenleriyle birlikte raporlanır.
   - Reçete veya aktif export durumu (`status == "active"`), hastanın ilacı bugün fiilen aldığının kanıtı olarak sunulmaz.
4. **SNOMED CT IPS Lisans ve Ontolojik Sınır**: Paket CC BY 4.0 lisansı altındadır (© International Health Terminology Standards Development Organisation 2002–2024). IPS paketi olasılıksal bir hastalık-belirti tanı motoru olarak kullanılmaz; yalnız aktif kavramlar ve açık ilişki türleri (`Is a`, `Finding site`, `Associated morphology`, `Interprets`, `Has active ingredient`) korunarak semptom anlama ve yönlendirme için kullanılır.
5. **Değişmezlik Koruması**: Kaynak veri paketleri (`bundle_manifest.json` içindeki `87` dosya), `runs/reading_tables_40_v1/answers/` altındaki `40` eski yanıt ve `data/runtime/` altındaki CPU/GPU baseline raporları salt-okunur kabul edilir.

---

## 5. G5 v1 İçin Değişecek ve Eklenecek Dosyalar

### Yeni Dosyalar
- `docs/G5_DISCOVERY.md` — Keşif raporu ve mimari sözleşme.
- `src/medical_rag/safety/emergency.py` — Modelden önce çalışan deterministik Türkçe acil durum / kırmızı bayrak denetleyicisi.
- `src/medical_rag/twin/__init__.py`
- `src/medical_rag/twin/cco_adapter.py` — `source_oracle-pilot-001..020.json` (`local_projection` + `original_cco.text` hasta beyanı bölümleri) salt-okunur adaptörü (`F1..Fn` referanslarıyla, opak UUID sızdırmadan).
- `src/medical_rag/twin/fact_repository.py` — SQLite tabanlı hasta kayıt deposu ve kesin SQL/Python hesaplama katmanı (son kayıt, tarih aralığı, min/max/ortalama/sayım, eksik veri gruplama).
- `src/medical_rag/twin/temporal_resolver.py` — Vaka `evaluated_at`/`asOf` referans zamanı, `occurredFrom`/`occurredTo` vs `recordedAt` ayrımı, `supersedesFactId` zinciri ve pencere çözümleyicisi.
- `src/medical_rag/terminology/__init__.py`
- `src/medical_rag/terminology/snomed_importer.py` — SNOMED CT IPS 2024 RF2 aktif kavram, açıklama, dil refset, IPS refset ve tipli ilişki SQLite aktarıcısı.
- `src/medical_rag/terminology/concept_linker.py` — Türkçe semptom/klinik ifade -> aktif SNOMED kavramı (`25064002 Headache` vb.) ve CCO ailesi bağlayıcısı.
- `src/medical_rag/twin/intent_router.py` — Sorgu niyeti (`emergency`, `patient_exact`, `patient_symptom_twin`, `terminology`, `general_dictionary`, `out_of_scope`) ve hedef CCO ailesi yönlendiricisi.
- `src/medical_rag/twin/evidence_builder.py` — Hasta kayıtları (`[CCO:...]`), terminoloji (`[SNOMED:...]`) ve genel klinik sözlük (`[GENEL:...]`) katmanlarını sert sınırlarla ayıran kanıt oluşturucu.
- Test dosyaları: `tests/test_cco_and_temporal.py`, `tests/test_snomed_linker.py`, `tests/test_twin_router_and_safety.py`, `tests/test_twin_api.py`.

### Güncellenecek Mevcut Dosyalar
- `.gitignore` — Veri paketleri ve yerel SQLite veritabanı desenlerinin eklenmesi.
- `src/medical_rag/config.py` — Mevcut varsayılanları değiştirmeden `cco_package_dir`, `snomed_package_dir`, `g5_db_path`, `twin_num_ctx`, `twin_num_predict` ayarlarının eklenmesi.
- `src/medical_rag/llm/ollama_client.py` ve `tests/fakes.py` — Geriye uyumlu opsiyonel `num_ctx` parametresi desteği.
- `src/medical_rag/rag/text.py` — Klinik belirteçleri koruyan yardımcı normalizasyon fonksiyonu.
- `src/medical_rag/rag/prompt.py` ve `src/medical_rag/safety/policy.py` — Mevcut baseline istem/politika korunarak Digital Twin için 3 katmanlı alıntı ve güvenlik sözleşmesinin eklenmesi.
- `src/medical_rag/api/schemas.py`, `src/medical_rag/api/routes.py`, `src/medical_rag/main.py` — Geriye uyumlu opsiyonel `case_id` alanı, `GET /v1/patients` vaka listeleme ucu, model öncesi acil durum kapısı ve katmanlı kanıt yanıt alanları.
- `frontend/src/*` (`types/api.ts`, `lib/api.ts`, `App.tsx`, `HeaderBar.tsx`, `QueryTurnCard.tsx`, `EvidenceAccordion.tsx`, `suggestedQuestions.ts`) — Mod/hasta profili seçici, acil durum uyarı kartı ve 3 katmanlı kanıt görünümü.

---

## 6. İlk Çalışan Üç Hasta Sorusu

1. **Kesin Sayısal/Zamansal Sorgu ve Eksik Veri (`missingData`) Açıklaması (`oracle-pilot-001`)**
   - *"Son ana uykum kaç dakika sürdü, 7 günlük uyku ortalamam nedir ve günlük HRV kişisel bazal değerim neden görünmüyor?"*
   - SQL/Python ile `sleep.duration.last-main-sleep` ve `sleep.duration.7d-average` kesin değerleri, birimleri (`minute`) ve olay zaman aralıkları (`occurredFrom..occurredTo`) getirilir; `cardio.hrv.personal-baseline` için `data-required` ve `minimumSamples` eksik veri nedeni sıfır/normal sayılmadan `[CCO:oracle-pilot-001:...]` alıntısıyla açıklanır.

2. **Semptom Tabanlı SNOMED (`25064002 Headache`) + Kişisel CCO Sentezi (`oracle-pilot-001`)**
   - *"Başım ağrıyor; kişisel kayıtlarımda son uyku düzenim, kalp/HRV ölçümlerim veya kayıtlı tanı ve ilaçlarım açısından hangi veriler var?"*
   - Semptom `25064002 |Headache (finding)|` kavramına ve yapısal ilişkilerine (`Is a -> 22253000 Pain`, `Finding site -> 69536005 Head structure`) bağlanır; hastanın `sleep`, `cardio`, `vitals`, `diagnosis`, `medication` ve hasta beyanı kayıtları çekilir; `[CCO:...]`, `[SNOMED:25064002]` ve `[GENEL:...]` katmanları tanı koymadan ayrı ayrı özetlenir.

3. **Model Öncesi Acil Durum (`Emergency Pre-Check`) Kısa Devresi**
   - *"Göğsümde baskı tarzında şiddetli ağrı, sol koluma yayılan uyuşma ve nefes darlığı başladı; yüzükteki nabzım normal görünüyor, beklemeli miyim?"*
   - Model çağrılmadan (`eval_count = 0`, `emergency = True`) deterministik acil durum uyarısı döner; giyilebilir cihaz verisinin akut acil tabloyu dışlayamayacağı ve derhal `112 Acil Çağrı Merkezi`'ne başvurulması gerektiği bildirilir.

---

## 7. Geliştirme Aşamaları, Test ve Kabul Kriterleri

- **Faz 0 — Keşif Belgesi ve Sızıntı Koruması**: `docs/G5_DISCOVERY.md` oluşturulması, `.gitignore` güncellenmesi, `bundle_manifest.json` (`87` dosya) ve `40` eski yanıtın değişmediğinin doğrulanması, `30` baseline testin geçmesi.
- **Faz 1 — CCO Adapter, SQLite Fact Repository ve Temporal Resolver**: `20` vakada `13,788` yapısal satırın (`8,617` `facts` + `5,171` `missingData`) + hasta beyanı bölümlerinin kayıpsız aktarımı, `oracle-pilot-019/020` sıfır satır doğrulaması, `occurredFrom/To` vs `recordedAt` ayrımı, `supersedesFactId` tekilliği ve opak UUID sızıntısının `0` olması.
- **Faz 2 — SNOMED Importer ve Concept Linker**: `19,697` aktif kavram, `60,114` EN açıklama, `66,017` aktif ilişki (`70` `typeId`) ve `12,930` IPS refset üyeliğinin SQLite üzerinde doğrulanması; Türkçe/İngilizce baş ağrısı ifadelerinin `25064002` kavramına ve ilişkilerine olasılıksal tanı üretmeden bağlanması.
- **Faz 3 — Emergency, Intent Router, 3 Katmanlı Evidence Builder ve Güvenlik Sözleşmesi**: Kırmızı bayrakta `0` model çağrısı, 3 ayrı kanıt katmanının (`CCO`, `SNOMED`, `GENEL`) sert sınırlarla üretilmesi, tanı/reçete/yeni doz iddiasının engellenmesi.
- **Faz 4 — FastAPI + React Entegrasyonu ve Canlı 26B Doğrulaması**: Tüm `30` baseline testin + yeni G5 testlerinin soketsiz ortamda geçmesi, loglarda ham soru/PHI bulunmaması, `frontend` TypeScript/Vite derlemesinin hatasız tamamlanması ve `127.0.0.1:11435` üzerinden `gemma4:26b-a4b-it-q4_K_M` ile ilk 3 hasta sorusunun doğrulanması.

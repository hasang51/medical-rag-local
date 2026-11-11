# Medical RAG

Yerel, tek turlu bir tıbbi sözlük asistanı. Sentetik Türkçe derlemden BM25 ile parça getirir, Gemma 4 ile yanıtlar ve alıntısız veya klinik rol iddiası taşıyan çıktıyı çekimserliğe düşürür.

Tanı, tedavi veya doz üretmez. Derlem eğitim sözlüğüdür; hasta verisi yoktur.

## Mimari

```
tarayıcı → Vite 127.0.0.1:5173
              → FastAPI 127.0.0.1:8000
                   → BM25  data/corpus
                   → Ollama yalnızca loopback
```

Arayüz Ollama’ya bağlanmaz. FastAPI, Ollama adresinin `127.0.0.1` veya `localhost` dışında olmasını reddeder. GPU denemesinde uzak Ollama’ya giden yol yerel SSH tünelidir: `127.0.0.1:11435` → uzak `127.0.0.1:11434`. Windows üzerindeki yerel Ollama `11434` portundadır; tünel ile karıştırılmaz.

Varsayılan model `gemma4:e4b`. 26B hedefi ortam değişkeniyle seçilir: `gemma4:26b-a4b-it-q4_K_M`. Üretim sınırı `num_ctx=2048`, `num_predict=128`, `temperature=0.2`, `think=false`. Akış yoktur. Ollama istemcisi aynı anda tek üretim tutar.

## API

`POST /v1/chat`

```json
{ "question": "Sistolik ve diyastolik kan basıncı ne anlatır?", "top_k": 3 }
```

`question` 1–500 karakterdir. `top_k` 1–5, varsayılan 3. İstekte sohbet geçmişi yoktur; her soru bağımsızdır.

Yanıt `answer`, `citations`, `retrieved_chunk_ids`, `abstained`, `disclaimer` ve süre alanlarını döner. Parça metni ve BM25 skoru şemada yoktur. Eşik altı sorguda model çağrılmaz (`eval_count=0`). Alıntı yoksa veya klinik rol kalıbı varsa yanıt sabit çekimser metindir; bu durumda getirilen parça kimlikleri durabilir.

`GET /health` → `status`, `ollama`, `model`. Model adı yapılandırmadan okunur. Erişilemeyen modeli kurulu değil saymayın.

`503` model veya tünel erişilemez. `504` üretim zaman aşımı. `422` boş veya 500 karakteri aşan soru.

## Çalıştırma

```powershell
uv sync
uv run medical-rag
```

API `http://127.0.0.1:8000` adresindedir. Örnek ortam değişkenleri `.env.example` içindedir. `.env` repoya girmez.

GPU tüneli, model doğrulaması ve arayüz sırası [CALISTIRMA.md](CALISTIRMA.md) dosyasındadır. Pod adresi ve SSH parolası repoda tutulmaz. İş bitince pod durdurulur.

Arayüz:

```powershell
cd frontend
npm install
npm run dev
```

`http://127.0.0.1:5173`. Vite, `/v1` ve `/health` isteklerini `127.0.0.1:8000` adresine iletir.

## Test

```powershell
uv run pytest
```

Canlı Ollama isteyen test `ollama` işaretlidir ve varsayılan koşudan dışarıdadır. `data/runtime/` ölçüm çıktısıdır; repoya girmez.

## Repoda olmayanlar

SSH anahtarları, `.env`, `data/runtime/`, `.cursor/`, sanal ortam, `node_modules` ve model ağırlıkları (`.gguf`) ignore edilir.

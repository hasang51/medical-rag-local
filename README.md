# Medical RAG

Yerel, tek turlu bir tıbbi sözlük asistanı. Sentetik Türkçe derlem üzerinde BM25 ile parça getirir, Gemma 4 ile yanıtlar ve alıntısız ya da klinik rol iddiası taşıyan çıktıyı çekimserliğe düşürür.

Tanı, tedavi veya doz üretmez. Derlem eğitim sözlüğüdür; hasta verisi yoktur.

## Mimari

```
tarayıcı → Vite (127.0.0.1:5173)
              → FastAPI (127.0.0.1:8000)
                   → BM25 (data/corpus)
                   → Ollama (yalnızca loopback)
```

Ollama makine dışına açılmaz. GPU denemesi, RunPod üzerindeki Ollama'ya yerel SSH tüneli (`127.0.0.1:11435` → uzak `127.0.0.1:11434`) ile gider. Arayüz tünele doğrudan bağlanmaz.

Varsayılan model `gemma4:e4b`. 26B hedefi ortam değişkeniyle seçilir: `gemma4:26b-a4b-it-q4_K_M`. Üretim ayarları `num_ctx=2048`, `num_predict=128`, `temperature=0.2`, `think=false`.

## API

`POST /v1/chat`

```json
{ "question": "Sistolik ve diyastolik kan basıncı ne anlatır?", "top_k": 3 }
```

`question` 1–500 karakterdir. `top_k` 1–5, varsayılan 3. İstekte sohbet geçmişi yoktur; her soru bağımsızdır.

Yanıt `answer`, `citations`, `retrieved_chunk_ids`, `abstained`, `disclaimer` ve süre alanlarını döner. Parça metni ve BM25 skoru yanıtta yoktur. Eşik altı sorguda model çağrılmaz. Alıntı yoksa veya klinik rol kalıbı varsa yanıt sabit çekimser metindir.

`GET /health` → `status`, `ollama`, `model`. Model adı yapılandırmadan okunur; erişilemeyen modeli “yok” saymaz.

## Çalıştırma

```powershell
uv sync
uv run medical-rag
```

API `http://127.0.0.1:8000` adresindedir. GPU tüneli, model doğrulaması ve arayüz sırası [CALISTIRMA.md](CALISTIRMA.md) içindedir. Pod adresi ve SSH parolası repoda tutulmaz.

Arayüz:

```powershell
cd frontend
npm install
npm run dev
```

## Test

```powershell
uv run pytest
```

Canlı Ollama isteyen test `ollama` işaretlidir ve varsayılan koşudan dışarıdadır. `data/runtime/` ölçüm çıktısıdır; repoya girmez.

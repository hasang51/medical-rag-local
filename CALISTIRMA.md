# Medical Digital Twin G5 — yeniden açılış

RunPod pod’u panelde **Running** olsun. Eski pod adresini kullanma. Host ve SSH portunu her seferinde panelden al. Pod adresi ve SSH parolası bu dosyaya yazılmaz.

Anahtar: `~\.ssh\runpod_ed25519`. Parolayı terminale sen yaz. Komuta koyma, kaydetme.

Üç PowerShell penceresi açık kalır. Sıra: tünel, API, arayüz. Proje klasörü: `C:\Projects\medical-rag-local`.

## 1. Tünel

`PANEL_PORT` ve `PANEL_HOST` yerine paneldeki değerleri yaz.

```powershell
ssh -N `
  -o IdentitiesOnly=yes `
  -o ExitOnForwardFailure=yes `
  -o ServerAliveInterval=30 `
  -i "$HOME\.ssh\runpod_ed25519" `
  -p PANEL_PORT `
  -L 127.0.0.1:11435:127.0.0.1:11434 `
  root@PANEL_HOST
```

Bu pencere açık kalır. Komut satırına dönmezse tünel duruyor demektir.

Yeni bir PowerShell aç. Model listesi gelsin:

```powershell
curl.exe -sS http://127.0.0.1:11435/api/tags
```

Listede `gemma4:26b-a4b-it-q4_K_M` olmalı. Bağlantı reddedilirse tünel ayaktadır, uzak Ollama kapalıdır. İkinci bir `ollama serve` başlatma. Aynı anahtarla bir kez şunu çalıştır, sonra `curl`’ü tekrarla:

```powershell
ssh -o IdentitiesOnly=yes -i "$HOME\.ssh\runpod_ed25519" -p PANEL_PORT root@PANEL_HOST "setsid /workspace/start-ollama.sh > /tmp/ollama-serve.log 2>&1 < /dev/null &"
```

Windows’taki yerel Ollama `11434` portundadır. GPU modeli `11435` tünelindedir. İkisini karıştırma.

## 2. API

Yeni PowerShell. Bu iki satır olmadan API yerel `11434` ve küçük modele gider. Pencere açık kalsın.

```powershell
cd C:\Projects\medical-rag-local
$env:MEDICAL_RAG_OLLAMA_BASE_URL = "http://127.0.0.1:11435"
$env:MEDICAL_RAG_MODEL = "gemma4:26b-a4b-it-q4_K_M"
uv run medical-rag
```

Kontrol, başka bir pencereden:

```powershell
curl.exe -sS http://127.0.0.1:8000/health
```

Beklenen: `"status":"ok"`, `"ollama":"ok"`, `"model":"gemma4:26b-a4b-it-q4_K_M"`.

## 3. Arayüz

Yeni PowerShell. Bu pencere de açık kalsın.

```powershell
cd C:\Projects\medical-rag-local\frontend
npm run dev
```

Tarayıcı: `http://127.0.0.1:5173`

İlk açılış **oracle-pilot-001** Digital Twin profilidir. Üstte profil listesi, başlık `Medical Digital Twin G5`, rozet `Gemma 4 26B` olmalı. Genel sözlük yalnız listeden ayrıca seçilince açılır.

Hasta listesi boşsa veya proxy hatası görürsen API penceresi kapalıdır. 2. adımı tekrar çalıştır, sayfayı yenile.

## Kapatırken

Üç PowerShell penceresini kapat. Pod hâlâ ücretlendiriyorsa RunPod panelinden pod’u durdur.

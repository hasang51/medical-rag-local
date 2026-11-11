# Medical RAG — Cursor açılış sırası

Host ve SSH portunu her seferinde RunPod panelinden alın. Eski pod adresini yeniden kullanmayın. Pod adresi ve SSH parolası bu dosyaya yazılmaz.

Anahtar: `~\.ssh\runpod_ed25519`. Parolayı terminale siz yazın; kaydetmeyin, komuta koymayın.

Üç terminal yeter. Sıra önemli: önce tünel, sonra API, sonra arayüz.

## 1. Tünel

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

Bu pencere açık kalır. `channel ... connect failed: Connection refused` görürseniz tünel sağlamdır, uzak Ollama durmuştur. Aynı anahtarla ikinci bir komut çalıştırın (parola yine istenebilir):

```powershell
ssh -o IdentitiesOnly=yes -o BatchMode=no -i "$HOME\.ssh\runpod_ed25519" -p PANEL_PORT root@PANEL_HOST "setsid /workspace/start-ollama.sh > /tmp/ollama-serve.log 2>&1 < /dev/null &"
```

`/workspace/start-ollama.sh` Ollama’yı yalnızca `127.0.0.1:11434` üzerinde açar. İkinci bir `ollama serve` başlatmayın.

Doğrulama (yeni bir PowerShell, tünel durmaz):

```powershell
(Invoke-RestMethod http://127.0.0.1:11435/api/version).version
(Invoke-RestMethod http://127.0.0.1:11435/api/tags).models.name
```

Beklenen model: `gemma4:26b-a4b-it-q4_K_M`. Sürüm gelmezse modeli silinmiş saymayın; önce tüneli ve pod’un açık olduğunu kontrol edin.

Windows’taki yerel Ollama `127.0.0.1:11434` üzerindedir. GPU modeli için FastAPI mutlaka `11435` kullanır.

## 2. FastAPI

```powershell
cd C:\Projects\medical-rag-local
$env:MEDICAL_RAG_OLLAMA_BASE_URL = "http://127.0.0.1:11435"
$env:MEDICAL_RAG_MODEL = "gemma4:26b-a4b-it-q4_K_M"
uv run medical-rag
```

Sağlık: `Invoke-RestMethod http://127.0.0.1:8000/health` → `status=ok`, `ollama=ok`, `model=gemma4:26b-a4b-it-q4_K_M`.

## 3. Arayüz

```powershell
cd C:\Projects\medical-rag-local\frontend
npm run dev
```

Tarayıcı: `http://127.0.0.1:5173`. Rozet `Gemma 4 26B` değilse sağlık satırına bakın; arayüz modeli kendisi uydurmaz.

İş bitince RunPod panelinden pod’u durdurun.

# Deploying AmMeeting on an NVIDIA DGX Spark

Run the entire stack — backend, web app, Postgres+pgvector, Redis, **and the AI
itself** (Ollama LLM + optional Whisper STT on the Blackwell GPU) — on one box on
your LAN. Your Mac's Chrome extension and browser talk to the Spark; **nothing
leaves your network.**

```
Your Mac ── Chrome extension ─┐
          └─ browser (web hub) ┴──▶  DGX Spark (http://SPARK_HOST)
                                       :3000 frontend   :8000 backend
                                       db · redis · ollama (GPU) · [stt (GPU)]
```

The Spark is arm64 + DGX OS (Ubuntu) with Docker and the NVIDIA container
toolkit preinstalled — every required image is multi-arch.

## 1. One-time setup on the Spark

```bash
# on the Spark
git clone https://github.com/RW2523/ammeet.git && cd ammeet
cp .env.spark.example .env.spark
ip -4 addr show | grep inet        # find the LAN IP → SPARK_HOST
openssl rand -hex 48               # run twice → SECRET_KEY, TOKEN_ENCRYPTION_KEY
nano .env.spark                    # set SPARK_HOST, POSTGRES_PASSWORD, secrets, CORS
```

## 2. Start the stack

```bash
docker compose -f docker-compose.spark.yml --env-file .env.spark up -d --build
```

First build takes a few minutes. Migrations run automatically before the API starts.

Pull the local models once (≈9 GB + 300 MB, cached in a volume):

```bash
docker compose -f docker-compose.spark.yml exec ollama ollama pull qwen2.5:14b
docker compose -f docker-compose.spark.yml exec ollama ollama pull nomic-embed-text
```

> With 128 GB unified memory the Spark can comfortably run much larger models
> (e.g. `qwen2.5:72b`, `llama3.3:70b`) — start with 14b, scale up if answer
> quality matters more than latency.

Health checks:

```bash
curl http://localhost:8000/api/health        # backend (or /docs in a browser)
curl http://localhost:11434/v1/models        # ollama
docker compose -f docker-compose.spark.yml ps
```

## 3. Point the app's AI at the local GPU

1. Browser (on any LAN machine) → `http://SPARK_HOST:3000` → register (first user).
2. **Settings → AI Models**:
   - Provider: **OpenAI-compatible**
   - Base URL: `http://ollama:11434/v1`  ← container-network name, resolved by the backend
   - Model: `qwen2.5:14b` · Embeddings: `nomic-embed-text`
   - API key: anything non-empty (e.g. `local`) — Ollama ignores it
3. Hit **Test** — a reply means the whole AI path is running on your GPU.

## 4. Connect the Chrome extension (on your Mac)

1. `chrome://extensions` → Developer mode → **Load unpacked** → `chrome-extension/dist`
   (or install from the Web Store once published).
2. Copy the extension **ID** shown on its card.
3. On the Spark, add it to `.env.spark` → `CORS_ORIGINS=...,chrome-extension://<ID>`
   then `docker compose -f docker-compose.spark.yml --env-file .env.spark up -d backend`.
4. In the extension side panel → ⚙️ Settings → Backend URL: `http://SPARK_HOST:8000` → sign in.

> The extension's `host_permissions` cover `localhost` only; LAN access works via
> the CORS entry above — no manifest change needed.

## 5. Optional: local Whisper STT on the GPU

Captions-based capture needs **no STT**. Enable this only for audio-upload /
tab-audio transcription:

```bash
# .env.spark:  STT_PROVIDER=whisper   WHISPER_BASE_URL=http://stt:8000/v1
docker compose -f docker-compose.spark.yml --env-file .env.spark --profile stt up -d
```

**Honest caveat:** the `speaches` CUDA image may lag on arm64. If it won't start
on DGX OS, run whisper.cpp's server natively instead — it builds cleanly with
CUDA on arm64:

```bash
git clone https://github.com/ggml-org/whisper.cpp && cd whisper.cpp
cmake -B build -DGGML_CUDA=1 && cmake --build build -j
./build/bin/whisper-server -m models/ggml-large-v3-turbo.bin --port 8001 --convert
# then: WHISPER_BASE_URL=http://<SPARK_HOST>:8001/v1  (host network, not container)
```

## 6. Verify end-to-end (10 minutes)

1. Web hub → new Speak session → paste a template → points generate **(local LLM ✓)**
2. Mac: join `meet.google.com`, turn on **CC**, side panel → 🎤 Speak → Start
3. Say two of your points → they tick green **(capture → Spark ✓)**
4. Finish & summarize → recap + share link `http://SPARK_HOST:3000/r/…` **(brain ✓)**
5. Knowledge → search something you said **(pgvector ✓)**

## Operations

| Task | Command |
|---|---|
| Logs | `docker compose -f docker-compose.spark.yml logs -f backend` |
| Update app | `git pull && docker compose -f docker-compose.spark.yml --env-file .env.spark up -d --build` (migrations auto-run) |
| Backup DB | `docker compose -f docker-compose.spark.yml exec db pg_dump -U ammeet ammeet > backup.sql` |
| Stop | `docker compose -f docker-compose.spark.yml down` (volumes persist) |

## Scope & limits

- **LAN-only by design.** Share links (`/r/…`) work only for people on your network.
  Exposing to the internet needs a reverse proxy + TLS + real domain — do that
  deliberately, later, not by default.
- `EMAIL_PROVIDER=mock` + no email verification — fine for a personal/team box.
- Meeting-bot (delegate) stays off (`BOT_PROVIDER=mock`) until Phase 3.

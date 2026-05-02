# ISISvoice

Medical triage voice intake microservice for the ASCLEPIO hospital system. Accepts patient audio or text, extracts structured clinical triage data, and delivers results to ASCLEPIO-M1 via webhook.

## Architecture

```
[ASCLEPIO-M1 / Client]
        │
        ▼
[ISISvoice — FastAPI]   ──WHISPER_API_URL──▶  [Whisper Server]
        │
        └──OLLAMA_BASE_URL──▶  [Ollama Server]
        │
        └──TRIAGE_WEBHOOK_URL──▶  [ASCLEPIO-NestJS-M1]
        │
        └──MONGODB_URI──▶  [MongoDB Atlas]
```

**Split deployment:**

| Part | Target | Services |
|------|--------|---------|
| AI backend | Own GPU server | Ollama + Whisper |
| API core | Azure Web App | FastAPI + heuristics |

## Input flows

**Audio intake** → Whisper (transcription) → Ollama (extraction) → webhook to M1

**Text intake** → Ollama (extraction) → webhook to M1

**Saturation fallback** → If Ollama is busy or slow, heuristic engine responds immediately without queuing.

## API

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/triage/symptoms/text` | JWT | Text triage intake |
| POST | `/api/v1/triage/symptoms/audio` | JWT | Audio triage intake |
| POST | `/api/v1/triage/symptoms/audio/base64` | JWT | Base64 audio intake |
| PUT | `/api/v1/triage/record/{id}/vital-signs` | JWT | Add vital signs |
| GET | `/api/v1/triage/record/{id}/preliminary-history` | JWT | Get extracted triage data |
| GET | `/api/v1/triage/procedure/{id}` | JWT | Get full procedure |
| GET | `/api/v1/triage/procedures/my` | JWT (PACIENTE) | Patient's procedures |
| GET | `/api/v1/triage/records` | JWT (ENFERMERO+) | All records |
| POST | `/api/v1/triage/record/{id}/comment` | JWT | Add comment |
| POST | `/api/v1/triage/record/{id}/close` | JWT | Close procedure |
| GET | `/api/v1/health` | — | Health check |
| GET | `/api/v1/ready` | — | Readiness probe |
| GET | `/docs` | — | Swagger UI |
| GET | `/client.html` | — | Web voice client |

## Triage output structure

```json
{
  "sintomas": ["string"],
  "embarazo": false,
  "antecedentes": ["string"],
  "posiblesCausas": ["string"],
  "nivelPrioridad": 3,
  "comentario": "string",
  "comentariosIA": "string",
  "advertenciaIA": "string"
}
```

Priority scale: Manchester triage — 1 (critical) to 5 (non-urgent).

## Resilience

- Ollama timeout → heuristic extraction, no queue wait
- Ollama saturated (`OLLAMA_MAX_CONCURRENT`) → immediate heuristic fallback
- MongoDB unavailable → in-memory buffer, flushes on reconnect
- Whisper failure → HTTP error returned to caller

## Environment

Copy `.env.example` → `.env`. Required variables:

| Variable | Description |
|----------|-------------|
| `OLLAMA_BASE_URL` | Ollama server URL |
| `WHISPER_API_URL` | Whisper server URL |
| `MONGODB_URI` | MongoDB connection string |
| `JWT_SECRET` | Must match ASCLEPIO-NestJS-M1 |
| `TRIAGE_WEBHOOK_URL` | M1 ingestion endpoint |
| `TRIAGE_WEBHOOK_TOKEN` | M1 API key |
| `TRIAGE_HOSPITAL_ID` | Hospital ID for webhook |
| `TRIAGE_ENFERMERO_ID` | Nurse ID for webhook |

## Tech stack

- **FastAPI** + Uvicorn — async REST API
- **OpenAI Whisper** — Spanish speech-to-text (runs on GPU server)
- **Ollama** — local LLM inference (runs on GPU server)
- **MongoDB** + Motor — async persistence
- **PyJWT** — token validation (shared secret with M1)

# ISISvoice — Load Tests

Local-only Locust load tests. Do **not** run against production.

## Pre-requisitos

1. `.env` configurado (copia `.env.example → .env`, rellena `JWT_SECRET` con el mismo secreto que el backend)
2. ISISvoice corriendo localmente: `uvicorn src.app.main:app --reload`
3. PowerShell 7+ (ya incluido en Windows 11)

## Uso rápido

```powershell
# Con Web UI (recomendado para explorar)
.\tests\load\run_load_test.ps1 -Preset nominal

# Headless + reporte HTML/CSV
.\tests\load\run_load_test.ps1 -Preset saturation -Duration 2m -HeadlessReport
```

Web UI disponible en `http://localhost:8089` mientras corre.

## Presets

| Preset       | Usuarios | Qué prueba                                          |
|-------------|----------|-----------------------------------------------------|
| `health`     | 50       | Endpoints públicos `/health`, `/ready`, `/live`     |
| `nominal`    | 10       | Flujo normal paciente + enfermera                   |
| `concurrent` | 20       | Cola LLM con carga media                            |
| `saturation` | 40       | Satura `OLLAMA_MAX_CONCURRENT=2`, prueba cola de 32 |
| `polling`    | 30       | Patrón de polling del modal React (~12 s/poll)      |

## Escenarios (clases Locust)

| Clase           | Rol JWT   | Endpoints principales                          |
|----------------|-----------|------------------------------------------------|
| `HealthUser`    | ninguno   | `GET /health`, `/ready`, `/live`               |
| `PatientUser`   | PACIENTE  | `POST /symptoms/text`, `GET /procedures/my`    |
| `NurseUser`     | ENFERMERO | `GET /records`, `GET /procedure/{id}`          |
| `SaturationUser`| PACIENTE  | `POST /symptoms/text` (agresivo, sin espera)   |
| `PollingUser`   | PACIENTE  | `POST /symptoms/text` + `GET /procedure/{id}`  |

## Métricas clave a observar

- **p50 / p95 / p99** de `POST /symptoms/text` — cuánto tarda el LLM
- **Tasa de 503** en saturación — punto donde la cola (`SESSION_QUEUE_MAX_SIZE=32`) se llena
- **Throughput** de health endpoints — latencia base sin LLM
- **p95 de polling** — debe ser < 500 ms (solo DB, sin LLM)

## Estructura

```
tests/load/
├── token_helper.py   # genera JWTs desde .env local
├── locustfile.py     # 5 escenarios
├── run_load_test.ps1 # runner PowerShell con presets
├── reports/          # CSV + HTML generados con -HeadlessReport
└── README.md
```

## Instalar locust manualmente

```powershell
.venv\Scripts\python.exe -m pip install "locust>=2.29"
```

El script `run_load_test.ps1` lo instala automáticamente si no existe.

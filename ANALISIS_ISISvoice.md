# Analisis de ISISvoice

ISISvoice es un microservicio FastAPI para triage medico por voz y texto. Recibe audio o texto del paciente, lo transcribe si hace falta, extrae informacion clinica estructurada, calcula prioridad de triage, persiste el procedimiento en MongoDB y entrega el caso al backend de ASCLEPIO mediante webhook.

## Resumen ejecutivo

El repo esta organizado en tres capas funcionales:

1. API y rutas: `src/app/main.py` monta la app FastAPI, registra routers y gestiona el ciclo de vida de MongoDB.
2. IA y reglas: `src/app/services/speech_service.py`, `triage_service.py` y `clinical_conversation_service.py` resuelven transcripcion, extraccion clinica y flujo conversacional.
3. Persistencia e integracion: `mongo_service.py` guarda datos, `procedure_service.py` arma el registro final y envia webhook a ASCLEPIO, y `core/auth.py` valida JWT.

La arquitectura esta pensada para despliegue separado: el core API puede vivir en Azure Web App, mientras que Whisper y Ollama corren en un servidor GPU aparte.

## Estructura activa vs legado

El punto de entrada real es `src/app/main.py`, que incluye solo los routers de `src/app/routers/`.

- Activo: `src/app/routers/triage_router.py`, `health_router.py`, `speech_router.py`.
- Activo: `src/app/services/*`, `src/app/models.py`, `src/app/core/*`.
- Legado o no montado por FastAPI: `src/routers/*` y el arbol viejo en `src/routers/`.

Esto importa porque la documentacion y los diagramas deben seguir el runtime actual, no el historial del repo.

## Como arranca el sistema

`src/app/main.py` hace lo siguiente:

- Abre la conexion a MongoDB en el `lifespan` con `mongo_store.connect()`.
- Cierra la conexion al apagar con `mongo_store.close()`.
- Crea la app FastAPI con metadata basica.
- Habilita CORS abierto a todos los orígenes.
- Registra los routers activos de triage, salud y speech.
- Redirige `/` a `/docs`.
- Sirve `/client.html` si el archivo existe en la raiz del proyecto.

## Configuracion

`src/app/core/settings.py` carga variables desde `.env` y centraliza los parametros operativos:

- JWT: `JWT_SECRET`, `JWT_ALGORITHM`.
- Ollama: `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SECONDS`, `OLLAMA_MAX_RETRIES`, `OLLAMA_MAX_CONCURRENT`.
- Whisper: `WHISPER_API_URL`, `WHISPER_MODEL`, `WHISPER_LANGUAGE`, `WHISPER_TIMEOUT_SECONDS`, `WHISPER_MAX_RETRIES`.
- MongoDB: `MONGODB_URI`, `MONGODB_DB`, timeouts y retries.
- Webhook de triage: `TRIAGE_WEBHOOK_URL`, `TRIAGE_WEBHOOK_TOKEN`, `TRIAGE_HOSPITAL_ID`, `TRIAGE_ENFERMERO_ID`.
- Buffer de sesion: `SESSION_QUEUE_MAX_SIZE`, `MAX_HISTORY_MESSAGES`.

Importante: `.env` contiene secretos reales y no debe copiarse ni exponerse en documentacion publica.

## Autenticacion

`src/app/core/auth.py` valida JWT con `PyJWT`.

- Lee el token desde `Authorization: Bearer ...`.
- Exige los claims `sub` y `rol`.
- Normaliza el rol a mayusculas.
- Expone `require_roles(...)` para proteger endpoints por rol.

Roles reconocidos:

- `PACIENTE`
- `ENFERMERO`
- `MEDICO`
- `ADMIN`
- `RECEPCIONISTA`

## Modelos

`src/app/models.py` define el contrato de datos.

- `PatientCreate`, `PatientUpdate`, `PatientResponse`: datos basicos del paciente.
- `TriageDataCore`: historia preliminar con sintomas, embarazo, antecedentes, posibles causas, comentario, prioridad y textos generados por IA.
- `VitalSignsCreate`: signos vitales.
- `Comment` y `ProcedureRecord`: registro completo del procedimiento de triage.
- `ProcedureRecordResponse`: salida de API.

`ProcedureRecord` usa `patient_cedula` como alias de `patient_id` para compatibilidad con la persistencia existente.

## Flujo de triage principal

El router principal es `src/app/routers/triage_router.py`.

### `POST /api/v1/triage/symptoms/text`

Flujo:

1. El usuario debe autenticarse como `PACIENTE`.
2. El payload acepta varios nombres equivalentes: `text_input`, `textInput`, `text`, `symptoms`, `transcript`.
3. El texto se limpia y pasa a `triage_extraction_service.extract_preliminary_history(...)`.
4. Se calcula `confidence_score`.
5. Se genera `procedure_id` con `patient_id + timestamp`.
6. Se crea un registro en MongoDB con `procedure_service.create_triage_record(...)`.
7. Se retorna estado `pending` y una recomendacion clinica.

### `POST /api/v1/triage/symptoms/audio`

Flujo:

1. El paciente sube un archivo de audio.
2. `speech_service.transcribe_audio_bytes(...)` convierte el audio a texto.
3. El texto pasa por el mismo motor de extraccion que el flujo por texto.
4. Se persiste el procedimiento y se intenta enviar webhook a ASCLEPIO.

### `POST /api/v1/triage/symptoms/audio/base64`

Igual que el flujo anterior, pero el audio llega en base64. Primero se decodifica, luego se transcribe y finalmente se crea el registro de triage.

## Actualizacion del procedimiento

Rutas para completar y cerrar el caso:

- `PUT /api/v1/triage/record/{procedure_id}/vital-signs`
- `POST /api/v1/triage/record/{procedure_id}/comment`
- `POST /api/v1/triage/record/{procedure_id}/close`

Comportamiento importante:

- Si un paciente intenta consultar un procedimiento ajeno, el sistema responde `403`.
- Al agregar signos vitales se actualiza el estado a `resolved`.
- Al cerrar un caso se cambia el estado a `closed`.
- Cada comentario se guarda con autor, fecha e identificador unico.

## Consulta de procedimientos

Rutas para lectura:

- `GET /api/v1/triage/record/{procedure_id}/preliminary-history`
- `GET /api/v1/triage/procedure/{procedure_id}`
- `GET /api/v1/triage/procedures/my`
- `GET /api/v1/triage/procedures/me` como alias legacy
- `GET /api/v1/triage/records`

Estas rutas sirven para ver el triage propio del paciente, listar procedimientos o revisar todo el backlog para personal clinico.

## Como decide la prioridad

La logica central esta en `src/app/services/triage_service.py`.

El servicio usa dos niveles de inteligencia:

1. Intento con Ollama si el modelo y la URL estan disponibles y no se supero el limite de concurrencia.
2. Fallback deterministico por reglas si Ollama falla, esta saturado o responde vacio.

### Extraccion con Ollama

El servicio arma un prompt que exige JSON estricto con esta estructura:

- sintomas
- embarazo
- antecedentes
- posiblesCausas
- comentario
- nivelPrioridad
- comentariosIA

Si Ollama responde correctamente, se normalizan los datos a `TriageDataCore`.

### Fallback heuristico

Cuando no hay respuesta de Ollama, el sistema detecta:

- sintomas por palabras clave
- embarazo
- antecedentes
- signos vitales escritos en texto
- sindromes de alto riesgo como SCA, ACV, meningitis, sepsis, apendicitis, embarazo ectopico, hipoglucemia y ofidismo
- patrones de dengue, deshidratacion y malaria
- contexto pediatrico
- comorbilidades de riesgo

La prioridad final sigue una escala Manchester de 1 a 5:

- `1`: critico
- `2`: muy urgente
- `3`: urgente
- `4`: poco urgente
- `5`: no urgente

### Recomendacion textual

`build_recommendation(...)` convierte la prioridad y los hallazgos en una salida corta para personal clinico o integraciones externas. Tambien agrega alertas como:

- evitar ibuprofeno y aspirina si hay sospecha de dengue
- rehidratacion oral o EV si hay deshidratacion
- advertencias por dengue con signos de alarma

## Flujo conversacional clinico

El flujo guiado vive en `src/app/services/clinical_conversation_service.py` y se expone por `src/app/routers/speech_router.py`.

### Endpoints del flujo clinico

- `POST /speech/clinical/start`
- `POST /speech/clinical/audio`
- `POST /speech/ia/analyze`
- `POST /speech/flow/audio`
- `POST /speech/clinical/finalize/{session_id}`
- `GET /speech/health`

### Comportamiento

1. Se crea o reutiliza una sesion con `session_id`.
2. Cada mensaje del paciente se persiste en Mongo si es posible.
3. Si Mongo falla, el flujo no se cae: guarda una copia local en memoria y marca `buffered`.
4. El texto pasa por `triage_extraction_service` para obtener sintesis clinica estructurada.
5. El sistema construye una respuesta del asistente y actualiza el estado de la sesion.
6. Al finalizar, se consolida un resumen final con mensajes y datos estructurados.

### Punto clave

Este flujo no es un chat generativo libre. Es un flujo determinista orientado a triage y historia clinica. El asistente responde con preguntas o recomendaciones fijas y la extraccion clinica intenta mantener la estructura de campo estable.

## Persistencia en MongoDB

La capa de datos esta en `src/app/services/mongo_service.py`.

### Colecciones usadas

- `patients_info`
- `triage_records`

### Estrategia de resiliencia

Si MongoDB no esta disponible:

- se mantienen buffers en memoria para pacientes y procedimientos
- al reconectar, el servicio intenta vaciar esos buffers
- el health check reporta el estado como `degraded` o `buffered` segun el caso

### Indices

Se crean indices sobre:

- `cedula`
- `created_at`
- `procedure_id`
- `patient_cedula`
- `status`
- combinaciones como `(patient_cedula, created_at)` y `(status, updated_at)`

Eso apunta a consultas frecuentes por paciente, por estado y por fecha.

## Integracion externa

### Whisper

`src/app/services/speech_service.py` decide de donde sale la transcripcion:

- si `WHISPER_API_URL` existe, llama a un servicio HTTP remoto en `/transcribe`
- si no existe, usa Whisper local con `librosa`, `torchaudio` o `miniaudio` como rutas de decodificacion

Tambien existe un microservicio separado en `src/whisper_app.py` que expone:

- `GET /health`
- `POST /transcribe`

Ese servicio usa `faster-whisper` y esta pensado para ejecutarse aparte, normalmente en el servidor GPU.

### Ollama

`triage_service.py` consume `OLLAMA_BASE_URL/api/generate`.

Si el modelo responde bien, se usa IA; si no, se cae a heuristicas. Esto evita bloquear al usuario cuando el modelo esta lento o saturado.

### Webhook de ASCLEPIO

`src/app/services/procedure_service.py` construye un payload completo y lo publica en `TRIAGE_WEBHOOK_URL`.

El webhook puede incluir:

- `x-api-key` con `TRIAGE_WEBHOOK_TOKEN`
- query params `hospital_id` y `enfermero_id`
- `procedure_id`, `patient_id`, `transcript`, `input_type`
- `preliminary_history`, `confidence_score`, `status`, `vital_signs`, `comments`
- estado de entrega `pending`, `sent`, `failed` o `skipped`

## Servicio de speech y cliente web

El flujo de speech de `src/app/routers/speech_router.py` combina transcripcion y sesion clinica.

### `POST /speech/transcribe-file`

Endpoint tradicional para subir un archivo y devolver la transcripcion.

### `POST /speech/clinical/start`

Inicia o reutiliza una sesion clinica y devuelve la primera pregunta.

### `POST /speech/clinical/audio`

Transcribe audio y avanza el flujo clinico de la sesion.

### `POST /speech/ia/analyze`

Recibe texto libre del paciente y devuelve la salida clinica estructurada.

### `POST /speech/flow/audio`

Flujo completo: audio -> transcripcion -> IA -> persistencia obligatoria en Mongo.

### `POST /speech/clinical/finalize/{session_id}`

Consolida la historia clinica final de la sesion y la guarda.

### `GET /speech/health`

Verifica el estado del servicio y sus dependencias.

### `client.html`

Existe un cliente HTML simple para pruebas manuales. No es el producto principal, pero sirve como interfaz de demostracion local.

## Despliegue

### `docker-compose.yml`

Este compose corre solo el core FastAPI y opcionalmente MongoDB local.

- `api`: construye desde `src/app/Dockerfile`.
- `mongo`: perfil `full`, util para desarrollo local.
- La API espera variables de entorno para Mongo, Whisper, Ollama, JWT y webhook.

### `docker-compose.gpu-server.yml`

Este compose corre en la maquina con GPU.

- `ollama`: expone `11434` y carga el modelo clinico.
- `whisper`: expone `8001` con `faster-whisper`.

### `src/app/Dockerfile`

Build multi-stage para el core API.

- Instala dependencias de Python.
- Copia `src/`, `client.html` y `.env.example`.
- Expone `8000`.
- Ejecuta `uvicorn app.main:app`.

### `src/Dockerfile.whisper`

Build simple para el servicio Whisper.

- Instala dependencias de audio y `faster-whisper`.
- Expone `8001`.
- Ejecuta `uvicorn whisper_app:app`.

## Salud y readiness

`src/app/routers/health_router.py` expone:

- `GET /api/v1/health`
- `GET /api/v1/ready`
- `GET /api/v1/live`

La health check revisa MongoDB y Whisper local; la readiness probe depende de MongoDB; la liveness siempre responde vivo mientras el proceso siga arriba.

## Lo que muestran los tests

Los tests del repo confirman la intencion del sistema:

- `tests/unit/test_main.py` valida redireccion a docs y `client.html`.
- `tests/unit/test_triage_service.py` cubre heuristicas, prioridad y recomendaciones.
- `tests/unit/test_procedure_service.py` cubre webhook y persistencia de procedimientos.
- `tests/unit/test_mongo_service.py` cubre buffers, indices y health.
- `tests/unit/test_speech_service.py` cubre transcripcion local y remota.

## Riesgos y observaciones

- Hay dos arboles de rutas en el repo, pero el activo es `src/app/`.
- `.env` contiene secretos reales; no deben copiarse a documentacion publica.
- El flujo depende de servicios externos opcionales: Whisper, Ollama y el webhook de ASCLEPIO.
- La logica de triage prioriza continuidad operativa: si Ollama falla, el sistema sigue con heuristicas.

## Prompt para draw.io

Pega este prompt en la IA de draw.io para generar diagramas consistentes del sistema:

```text
Genera un set de diagramas para ISISvoice, un microservicio medico de triage por voz y texto.

Quiero 4 diagramas separados, con estilo limpio, profesional y tecnico, usando labels en espanol:

1. Diagrama de arquitectura general.
	Incluye estos nodos y relaciones:
	- ASCLEPIO-M1 / Cliente
	- ISISvoice FastAPI (core API)
	- Whisper Server remoto en GPU
	- Ollama Server remoto en GPU
	- MongoDB Atlas
	- Webhook ASCLEPIO / NestJS
	- Cliente web client.html

	Flechas obligatorias:
	- Cliente -> ISISvoice por HTTPS
	- ISISvoice -> Whisper cuando WHISPER_API_URL esta configurado
	- ISISvoice -> Ollama cuando OLLAMA_BASE_URL esta configurado
	- ISISvoice -> MongoDB Atlas para persistencia
	- ISISvoice -> Webhook ASCLEPIO para entregar procedimientos
	- client.html -> ISISvoice como interfaz de prueba

2. Diagrama de secuencia: flujo de triage por texto.
	Pasos:
	- PACIENTE autentica con JWT
	- POST /api/v1/triage/symptoms/text
	- TriageExtractionService intenta Ollama
	- Si Ollama responde, normaliza a TriageDataCore
	- Si Ollama falla o se satura, aplica heuristicas
	- ProcedureService crea procedimiento en MongoDB
	- ProcedureService envia webhook a ASCLEPIO
	- API retorna procedure_id, status pending y recommendation

3. Diagrama de secuencia: flujo de triage por audio.
	Pasos:
	- PACIENTE sube audio
	- SpeechService transcribe con Whisper remoto o local
	- Texto resultante pasa a TriageExtractionService
	- Se calcula prioridad Manchester 1 a 5
	- Se guarda en MongoDB
	- Se envia webhook
	- Se responde al cliente con recomendacion clinica

4. Diagrama de estado del procedimiento.
	Estados:
	- pending
	- resolved
	- closed
	- webhook_delivery: pending, sent, failed, skipped
	Transiciones:
	- Crear procedimiento -> pending
	- Agregar signos vitales -> resolved
	- Cerrar procedimiento -> closed
	- Si se envia webhook -> sent
	- Si falla -> failed
	- Si no hay URL configurada -> skipped

Requisitos de estilo:
- Usa cajas claras por capa: cliente, API, servicios de IA, persistencia, integracion externa.
- Diferencia visualmente el core API del GPU server.
- Usa colores sobrios, flechas claras y texto corto.
- Agrega una leyenda de roles: PACIENTE, ENFERMERO, MEDICO, ADMIN.
- Resalta que Ollama tiene fallback a heuristicas y que MongoDB usa buffers en memoria si esta caido.

Tambien agrega una nota final en el diagrama de arquitectura:
- El core FastAPI puede correr en Azure Web App.
- Whisper y Ollama corren separados en un servidor GPU.
- MongoDB Atlas es externo.
```

## Lectura rapida del flujo

Si quieres entender ISISvoice en una sola frase: el paciente entra por texto o audio, Whisper lo convierte a texto, Ollama intenta estructurarlo, heuristicas lo respaldan si el modelo falla, MongoDB guarda el procedimiento y un webhook entrega el caso a ASCLEPIO.

- `x-api-key` con `TRIAGE_WEBHOOK_TOKEN`
- query params `hospital_id` y `enfermero_id`

Esto permite que el backend principal reciba el caso ya estructurado.

## Capa de salud

Hay dos routers de salud:

- `src/app/routers/health_router.py`
- `src/app/routers/speech_router.py` tambien expone `/speech/health`

### `GET /api/v1/health`

Valida MongoDB y Whisper localmente cargado.

### `GET /api/v1/ready`

Usado como readiness probe.

### `GET /api/v1/live`

Usado como liveness probe.

### `GET /speech/health`

Reporta si el engine de sesion y Mongo estan activos o degradados.

## Despliegue

### API principal

Se construye con `src/app/Dockerfile`.

- imagen base `python:3.11-slim`
- instala dependencias de audio y runtime
- copia `src/`, `client.html` y `.env.example`
- ejecuta `uvicorn app.main:app --host 0.0.0.0 --port 8000`

### Servidor GPU

Se construye con `docker-compose.gpu-server.yml`.

- `ollama` en `11434`
- `whisper` en `8001`
- volumen persistente para modelos y cache

### Desarrollo local

`start.sh` automatiza un flujo local clasico:

1. detecta Python
2. crea entorno virtual si no existe
3. instala dependencias
4. verifica Whisper
5. levanta FastAPI en `8000`

## Codigo legado o no activo

El repositorio tiene una carpeta `src/routers/` con routers viejos como `doctor_router.py`, `patient_router.py` y `triage_router.py`.

Esos archivos parecen historicos o de refactor y no son los que monta la app actual. El runtime real usa `src/app/routers/`.

Tambien hay un `src/app/routers/patient_router.py` que hoy solo conserva un `APIRouter` vacio para no romper imports.

## Flujos principales para diagramar

### Flujo 1: triage por texto

Usuario autenticado -> `POST /api/v1/triage/symptoms/text` -> validacion JWT -> extraccion clinica -> calculo de prioridad -> creacion de procedimiento -> persistencia en Mongo -> webhook ASCLEPIO -> respuesta con recomendacion.

### Flujo 2: triage por audio

Usuario autenticado -> `POST /api/v1/triage/symptoms/audio` o `/audio/base64` -> decodificacion audio -> Whisper remoto o local -> texto transcrito -> extraccion clinica -> persistencia -> webhook.

### Flujo 3: sesion clinica conversacional

`/speech/clinical/start` -> sesion inicial -> `/speech/clinical/audio` o `/speech/ia/analyze` -> persistencia incremental -> `/speech/clinical/finalize/{session_id}` -> historia clinica consolidada.

### Flujo 4: soporte operacional

Health checks -> Mongo -> Whisper -> estado degradado o saludable -> readiness/liveness para despliegue.

## Prompt listo para draw.io

Puedes pegar este prompt en draw.io para generar diagramas de arquitectura y flujo:

```text
Create 5 separate diagrams for the ISISvoice system in Spanish.

Diagram 1: High-level architecture
- Show four main blocks: ASCLEPIO-M1 / Client, ISISvoice FastAPI core, GPU server, MongoDB Atlas.
- Connect ASCLEPIO-M1 / Client to ISISvoice with JWT-protected HTTP requests.
- Connect ISISvoice to Whisper Server through WHISPER_API_URL.
- Connect ISISvoice to Ollama Server through OLLAMA_BASE_URL.
- Connect ISISvoice to ASCLEPIO webhook through TRIAGE_WEBHOOK_URL.
- Connect ISISvoice to MongoDB Atlas through MONGODB_URI.
- Add a note that Whisper and Ollama run separately on a GPU server.

Diagram 2: Text triage flow
- Start: authenticated patient.
- Step 1: POST /api/v1/triage/symptoms/text.
- Step 2: JWT role validation = PACIENTE.
- Step 3: normalize input text.
- Step 4: triage_extraction_service.extract_preliminary_history.
- Step 5: if Ollama available and not saturated, use AI JSON extraction.
- Step 6: otherwise use deterministic heuristics.
- Step 7: compute confidence score.
- Step 8: create procedure record in MongoDB.
- Step 9: send webhook to ASCLEPIO.
- End: return procedure_id, patient_id, status pending, recommendation.

Diagram 3: Audio triage flow
- Start: authenticated patient uploads audio.
- Step 1: POST /api/v1/triage/symptoms/audio or /audio/base64.
- Step 2: decode base64 if needed.
- Step 3: transcribe audio with Whisper remote if WHISPER_API_URL is set, otherwise local Whisper.
- Step 4: send transcription to triage extraction service.
- Step 5: determine priority 1 to 5.
- Step 6: persist procedure in MongoDB.
- Step 7: send webhook to ASCLEPIO.
- End: return recommendation and procedure_id.

Diagram 4: Clinical conversation flow
- Start: POST /speech/clinical/start.
- Step 1: create or reuse session_id.
- Step 2: ensure session in MongoDB or local buffer.
- Step 3: POST /speech/clinical/audio or /speech/ia/analyze.
- Step 4: transcribe if audio.
- Step 5: process_user_message.
- Step 6: store message history and structured data.
- Step 7: return assistant reply and stage.
- Step 8: POST /speech/clinical/finalize/{session_id}.
- Step 9: consolidate final clinical history.

Diagram 5: Operational resilience
- Show MongoDB health, Whisper health, Ollama availability, and webhook delivery.
- If MongoDB fails, show buffered fallback in memory.
- If Ollama fails or is saturated, show heuristic fallback.
- If Whisper fails, show HTTP error to caller.
- If webhook fails, show retry logic and webhook_delivery status failed.

Style guidance:
- Use clean medical/enterprise styling.
- Different colors for client, API, AI services, and persistence.
- Use arrows with labels like JWT, HTTP, JSON, webhook, and buffer fallback.
- Include small notes for statuses: healthy, degraded, buffered, sent, failed.
```

## Archivos que mas importan

- [src/app/main.py](src/app/main.py)
- [src/app/core/settings.py](src/app/core/settings.py)
- [src/app/core/auth.py](src/app/core/auth.py)
- [src/app/models.py](src/app/models.py)
- [src/app/services/triage_service.py](src/app/services/triage_service.py)
- [src/app/services/clinical_conversation_service.py](src/app/services/clinical_conversation_service.py)
- [src/app/services/procedure_service.py](src/app/services/procedure_service.py)
- [src/app/services/mongo_service.py](src/app/services/mongo_service.py)
- [src/app/services/speech_service.py](src/app/services/speech_service.py)
- [src/app/routers/triage_router.py](src/app/routers/triage_router.py)
- [src/app/routers/speech_router.py](src/app/routers/speech_router.py)
- [docker-compose.yml](docker-compose.yml)
- [docker-compose.gpu-server.yml](docker-compose.gpu-server.yml)
- [DEPLOY.md](DEPLOY.md)

## Lectura rapida del sistema

Si lo resumimos en una sola frase: ISISvoice toma voz o texto de un paciente, lo convierte en informacion clinica util, lo clasifica por urgencia, lo persiste, y lo entrega al sistema hospitalario para que el triage continue.

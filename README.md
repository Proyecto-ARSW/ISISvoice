# Voice Clinica

## Resumen de arquitectura

### 1) Capa de API
- Framework: FastAPI.
- Entradas: REST para archivos completos y flujo clinico por HTTPS.
- Salidas: JSON de transcripcion, siguiente pregunta clinica y estado de persistencia.

### 2) Capa de orquestacion clinica deterministica
- Servicio: clinical_conversation_service.
- Modelo: reglas por etapas enfocadas en datos de pre-triaje.
- Garantia: salida JSON estable para almacenamiento y consulta.
- Beneficio: no depende de disponibilidad de LLM para responder.

### 3) Capa de transcripcion
- Whisper para ASR en espanol.
- Flujo UI recomendado: grabar audio completo y enviar con boton.
- Decodificacion robusta en archivos: librosa y fallback con torchaudio.

### 4) Capa de entrevista clinica
- Motor de reglas local para capturar campos faltantes.
- Extraccion heuristica desde texto transcrito.
- Pregunta siguiente basada en faltantes clinicos.

### 5) Capa de persistencia
- MongoDB (Atlas o local) con Motor (async).
- Colecciones: sessions y messages.
- Estrategia de resiliencia: buffered mode cuando Mongo no responde.

## Tecnologias y por que se eligieron

- FastAPI:
  - Alto rendimiento async.
  - Swagger integrado.

- Whisper:
  - Muy buena precision en espanol.
  - Funciona local sin dependencia de API externa.

- MongoDB:
  - Esquema flexible para historia clinica incremental.
  - Facil versionado de campos clinicos y metadata.

- Motor (driver async):
  - Integracion natural con FastAPI async.
  - Menor bloqueo del event loop.

## Flujo funcional recomendado para entrevista

1. Abrir client.html.
2. Iniciar sesion clinica.
3. Start Recording.
4. Hablar.
5. Stop Recording.
6. Enviar Audio (audio completo).
7. Revisar Ultima transcripcion detectada.
8. Repetir ciclos de grabacion/envio hasta completar `clinical_data`.
9. Finalizar sesion para consolidar historia.

Nota:
- La sesion se mantiene hasta Finalizar Sesion.
- Esto evita reinicios de contexto y preguntas repetitivas de arranque.

## Endpoints principales

- GET /speech/health
- POST /speech/transcribe-file
- POST /speech/ia/analyze
- POST /speech/flow/audio
- POST /speech/clinical/start
- POST /speech/clinical/audio
- POST /speech/clinical/finalize/{session_id}

Estructura de salida clinica (campo `clinical_data`):
- identification_number
- symptoms
- current_medications
- pregnancy
- recent_trauma
- possible_justification

Swagger:
- http://localhost:8000/docs

Cliente web:
- http://localhost:8000/client.html

## Estructura del proyecto

src/app/
- core/settings.py
- main.py
- routers/speech_router.py
- services/speech_service.py
- services/mongo_service.py
- services/clinical_conversation_service.py

Raiz:
- client.html
- start.sh
- docker-compose.yml
- infra/terraform/

## Variables de entorno principales

ASR:
- WHISPER_MODEL
- WHISPER_LANGUAGE
- WHISPER_TIMEOUT_SECONDS
- WHISPER_MAX_RETRIES
- WHISPER_BEAM_SIZE
- WHISPER_BEST_OF

Mongo:
- MONGODB_URI
- MONGODB_DB
- MONGO_SERVER_SELECTION_TIMEOUT_MS
- MONGO_CONNECT_TIMEOUT_MS
- MONGO_SOCKET_TIMEOUT_MS
- MONGO_OPERATION_TIMEOUT_SECONDS
- MONGO_MAX_RETRIES

## Escalabilidad y resiliencia

Implementado:
- Motor clinico deterministico sin dependencia de LLM para el flujo principal.
- Timeouts y retries para Whisper y Mongo.
- Fallback buffered si Mongo falla.

Recomendado a futuro:
- Redis para estado distribuido de sesiones en multi-instancia.
- Worker pool externo (Celery/RQ) para tareas pesadas.


## Ejecucion local

1. Dependencias:
- Mongo Atlas o Mongo local.

2. Inicio:

- Ejecuta: ./start.sh
- Windows (PowerShell):
  - `python -m uvicorn app.main:app --app-dir src --reload --port 8000`

3. Verificacion rapida:
- http://localhost:8000/speech/health
- http://localhost:8000/client.html

## Infraestructura

Docker:
- docker-compose.yml para API + Mongo local opcional.

Terraform:
- infra/terraform con base para despliegue EC2.
# Voice Clinica

## Resumen de arquitectura

### 1) Capa de API
- Framework: FastAPI.
- Entradas: REST para archivos completos y flujo clinico por HTTPS.
- Salidas: JSON de transcripcion, siguiente pregunta clinica y estado de persistencia.

### 2) Capa de orquestacion clinica deterministica
- Servicio: clinical_conversation_service.
- Modelo: reglas por etapas enfocadas en datos de pre-triaje.
- Garantia: salida JSON estable para almacenamiento y consulta.
- Beneficio: no depende de disponibilidad de LLM para responder.

### 3) Capa de transcripcion
- Whisper para ASR en espanol.
- Flujo UI recomendado: grabar audio completo y enviar con boton.
- Decodificacion robusta en archivos: librosa y fallback con torchaudio.

### 4) Capa de entrevista clinica
- Motor de reglas local para capturar campos faltantes.
- Extraccion heuristica desde texto transcrito.
- Pregunta siguiente basada en faltantes clinicos.

### 5) Capa de persistencia
- MongoDB (Atlas o local) con Motor (async).
- Colecciones: sessions y messages.
- Estrategia de resiliencia: buffered mode cuando Mongo no responde.

## Tecnologias y por que se eligieron

- FastAPI:
  - Alto rendimiento async.
  - Swagger integrado.

- Whisper:
  - Muy buena precision en espanol.
  - Funciona local sin dependencia de API externa.

- MongoDB:
  - Esquema flexible para historia clinica incremental.
  - Facil versionado de campos clinicos y metadata.

- Motor (driver async):
  - Integracion natural con FastAPI async.
  - Menor bloqueo del event loop.

## Flujo funcional recomendado para entrevista

1. Abrir client.html.
2. Iniciar sesion clinica.
3. Start Recording.
4. Hablar.
5. Stop Recording.
6. Enviar Audio (audio completo).
7. Revisar Ultima transcripcion detectada.
8. Repetir ciclos de grabacion/envio hasta completar `clinical_data`.
9. Finalizar sesion para consolidar historia.

Nota:
- La sesion se mantiene hasta Finalizar Sesion.
- Esto evita reinicios de contexto y preguntas repetitivas de arranque.

## Endpoints principales

- GET /speech/health
- POST /speech/transcribe-file
- POST /speech/ia/analyze
- POST /speech/flow/audio
- POST /speech/clinical/start
- POST /speech/clinical/audio
- POST /speech/clinical/finalize/{session_id}

Estructura de salida clinica (campo `clinical_data`):
- identification_number
- symptoms
- current_medications
- pregnancy
- recent_trauma
- possible_justification

Swagger:
- http://localhost:8000/docs

Cliente web:
- http://localhost:8000/client.html

## Estructura del proyecto

src/app/
- core/settings.py
- main.py
- routers/speech_router.py
- services/speech_service.py
- services/mongo_service.py
- services/clinical_conversation_service.py

Raiz:
- client.html
- start.sh
- docker-compose.yml
- infra/terraform/

## Variables de entorno principales

ASR:
- WHISPER_MODEL
- WHISPER_LANGUAGE
- WHISPER_TIMEOUT_SECONDS
- WHISPER_MAX_RETRIES
- WHISPER_BEAM_SIZE
- WHISPER_BEST_OF

Mongo:
- MONGODB_URI
- MONGODB_DB
- MONGO_SERVER_SELECTION_TIMEOUT_MS
- MONGO_CONNECT_TIMEOUT_MS
- MONGO_SOCKET_TIMEOUT_MS
- MONGO_OPERATION_TIMEOUT_SECONDS
- MONGO_MAX_RETRIES

## Escalabilidad y resiliencia

Implementado:
- Motor clinico deterministico sin dependencia de LLM para el flujo principal.
- Timeouts y retries para Whisper y Mongo.
- Fallback buffered si Mongo falla.

Recomendado a futuro:
- Redis para estado distribuido de sesiones en multi-instancia.
- Worker pool externo (Celery/RQ) para tareas pesadas.


## Ejecucion local

1. Dependencias:
- Mongo Atlas o Mongo local.

2. Inicio:

- Ejecuta: ./start.sh
- Windows (PowerShell):
  - `python -m uvicorn app.main:app --app-dir src --reload --port 8000`

3. Verificacion rapida:
- http://localhost:8000/speech/health
- http://localhost:8000/client.html

## Infraestructura

Docker:
- docker-compose.yml para API + Mongo local opcional.

Terraform:
- infra/terraform con base para despliegue EC2.


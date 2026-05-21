"""
Locust load tests for ISISvoice (local only).

Scenarios
---------
HealthUser        – public endpoints, baseline latency
PatientUser       – POST symptoms/text (hits Ollama LLM), GET my procedures
NurseUser         – GET /records list (ENFERMERO, no LLM)
SaturationUser    – aggressive POST symptoms/text to saturate OLLAMA_MAX_CONCURRENT=2
PollingUser       – GET /procedure/{id} polling pattern

Run:
    locust -f tests/load/locustfile.py --host http://localhost:8000
"""
from __future__ import annotations

import random
import uuid

from locust import HttpUser, between, events, task

from tests.load.token_helper import enfermero_token, paciente_token

# ---------------------------------------------------------------------------
# Symptom texts — realistic Spanish medical descriptions
# ---------------------------------------------------------------------------
SYMPTOM_TEXTS = [
    "Tengo fiebre alta de 39 grados desde ayer, dolor de cabeza intenso y escalofríos.",
    "Me duele el pecho al respirar profundo, llevo dos días con tos seca.",
    "Siento el corazón acelerado y me falta el aire cuando camino.",
    "Llevo tres días con diarrea y vómitos, no puedo retener líquidos.",
    "Tengo dolor muy fuerte en el abdomen lado derecho, empeora al moverme.",
    "Me caí y tengo el tobillo muy hinchado, no puedo apoyar el pie.",
    "Me duele la cabeza hace cuatro horas, siento náuseas y sensibilidad a la luz.",
    "Tengo tos con flema amarilla desde hace una semana y fiebre de 38.",
    "Me ardió la garganta y tengo dificultad para tragar desde ayer.",
    "Siento entumecimiento en el brazo izquierdo y mareos desde esta mañana.",
]

# ---------------------------------------------------------------------------
# Shared procedure IDs collected during the run for polling scenarios
# ---------------------------------------------------------------------------
_created_procedure_ids: list[str] = []


@events.init.add_listener
def on_locust_init(environment, **_kwargs):
    """Eagerly validate that .env is configured before starting."""
    try:
        paciente_token()
        enfermero_token()
        print("\n[token_helper] JWT generation OK — .env loaded.\n")
    except RuntimeError as exc:
        print(f"\n[token_helper] ERROR: {exc}\n")
        environment.runner.quit()


# ---------------------------------------------------------------------------
# Scenario 1 — Health baseline (no auth)
# ---------------------------------------------------------------------------
class HealthUser(HttpUser):
    """Hit the three public probes. Establishes zero-auth baseline latency."""

    wait_time = between(0.5, 2)
    weight = 3

    @task(3)
    def health(self):
        self.client.get("/api/v1/health", name="/health")

    @task(1)
    def ready(self):
        self.client.get("/api/v1/ready", name="/ready")

    @task(1)
    def live(self):
        self.client.get("/api/v1/live", name="/live")


# ---------------------------------------------------------------------------
# Scenario 2 — Patient nominal (LLM path)
# ---------------------------------------------------------------------------
class PatientUser(HttpUser):
    """Realistic patient: submit symptoms → wait → poll own procedures."""

    wait_time = between(5, 15)
    weight = 2

    def on_start(self):
        self._user_id = str(uuid.uuid4())
        self._token = paciente_token(self._user_id)
        self._headers = {"Authorization": f"Bearer {self._token}"}
        self._my_procedure_ids: list[str] = []

    @task(2)
    def submit_symptoms(self):
        text = random.choice(SYMPTOM_TEXTS)
        with self.client.post(
            "/api/v1/triage/symptoms/text",
            json={"text_input": text},
            headers=self._headers,
            name="POST /symptoms/text",
            catch_response=True,
            timeout=90,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                pid = data.get("procedure_id")
                if pid:
                    self._my_procedure_ids.append(pid)
                    _created_procedure_ids.append(pid)
                resp.success()
            elif resp.status_code == 503:
                resp.failure(f"Queue full or LLM unavailable: {resp.text}")
            else:
                resp.failure(f"Unexpected {resp.status_code}: {resp.text}")

    @task(1)
    def list_my_procedures(self):
        self.client.get(
            "/api/v1/triage/procedures/my?limit=10",
            headers=self._headers,
            name="GET /procedures/my",
        )

    @task(1)
    def get_procedure(self):
        if not self._my_procedure_ids:
            return
        pid = random.choice(self._my_procedure_ids)
        self.client.get(
            f"/api/v1/triage/procedure/{pid}",
            headers=self._headers,
            name="GET /procedure/{id}",
        )


# ---------------------------------------------------------------------------
# Scenario 3 — Nurse staff (no LLM, read-only)
# ---------------------------------------------------------------------------
class NurseUser(HttpUser):
    """Nurse reviewing triage records. No LLM involvement."""

    wait_time = between(2, 6)
    weight = 1

    def on_start(self):
        self._token = enfermero_token()
        self._headers = {"Authorization": f"Bearer {self._token}"}

    @task(3)
    def list_records(self):
        self.client.get(
            "/api/v1/triage/records?limit=20",
            headers=self._headers,
            name="GET /records",
        )

    @task(1)
    def list_records_pending(self):
        self.client.get(
            "/api/v1/triage/records?status=pending&limit=50",
            headers=self._headers,
            name="GET /records?status=pending",
        )

    @task(1)
    def get_specific_procedure(self):
        if not _created_procedure_ids:
            return
        pid = random.choice(_created_procedure_ids)
        self.client.get(
            f"/api/v1/triage/procedure/{pid}",
            headers=self._headers,
            name="GET /procedure/{id}",
        )


# ---------------------------------------------------------------------------
# Scenario 4 — LLM saturation (OLLAMA_MAX_CONCURRENT=2 stress test)
# ---------------------------------------------------------------------------
class SaturationUser(HttpUser):
    """
    Aggressive POST to symptoms/text to flood OLLAMA_MAX_CONCURRENT=2.
    Expected: queue fills (SESSION_QUEUE_MAX_SIZE=32), then 503s appear.
    Goal: measure queue behavior and heuristic fallback latency.
    """

    wait_time = between(0.1, 0.5)
    weight = 0  # enabled only via --tags saturation

    def on_start(self):
        self._user_id = str(uuid.uuid4())
        self._token = paciente_token(self._user_id)
        self._headers = {"Authorization": f"Bearer {self._token}"}

    @task
    def flood_triage(self):
        text = random.choice(SYMPTOM_TEXTS)
        with self.client.post(
            "/api/v1/triage/symptoms/text",
            json={"text_input": text},
            headers=self._headers,
            name="POST /symptoms/text [saturation]",
            catch_response=True,
            timeout=120,
        ) as resp:
            if resp.status_code in (200, 503):
                resp.success()
            else:
                resp.failure(f"{resp.status_code}: {resp.text[:120]}")


# ---------------------------------------------------------------------------
# Scenario 5 — Polling pattern
# ---------------------------------------------------------------------------
class PollingUser(HttpUser):
    """
    Simulates frontend polling GET /procedure/{id} every ~12 s
    (matches POLL_INTERVAL_MS=12000 in the React modal).
    """

    wait_time = between(10, 14)
    weight = 2

    def on_start(self):
        self._user_id = str(uuid.uuid4())
        self._token = paciente_token(self._user_id)
        self._headers = {"Authorization": f"Bearer {self._token}"}
        self._procedure_id: str | None = None

    @task(1)
    def create_procedure_if_needed(self):
        if self._procedure_id:
            return
        text = random.choice(SYMPTOM_TEXTS)
        with self.client.post(
            "/api/v1/triage/symptoms/text",
            json={"text_input": text},
            headers=self._headers,
            name="POST /symptoms/text [poll-setup]",
            catch_response=True,
            timeout=90,
        ) as resp:
            if resp.status_code == 200:
                self._procedure_id = resp.json().get("procedure_id")
                resp.success()
            else:
                resp.failure(f"{resp.status_code}")

    @task(5)
    def poll_procedure(self):
        if not self._procedure_id:
            return
        self.client.get(
            f"/api/v1/triage/procedure/{self._procedure_id}",
            headers=self._headers,
            name="GET /procedure/{id} [polling]",
        )

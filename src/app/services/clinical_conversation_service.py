from __future__ import annotations

import asyncio
import re
from typing import Any
from collections import defaultdict

from app.core.settings import settings
from app.services.mongo_service import mongo_store


class ClinicalConversationService:
    ALLOWED_FIELDS = {
        "identification_number",
        "symptoms",
        "current_medications",
        "pregnancy",
        "recent_trauma",
        "possible_justification",
    }
    OUTPUT_FIELD_ORDER = (
        "identification_number",
        "symptoms",
        "current_medications",
        "pregnancy",
        "recent_trauma",
        "possible_justification",
    )

    def __init__(self) -> None:
        # Fallback en memoria para mantener la conversacion si Mongo no esta disponible.
        self._local_history: dict[str, list[dict[str, str]]] = defaultdict(list)
        self._local_structured: dict[str, dict[str, Any]] = defaultdict(dict)
        self._session_stage: dict[str, str] = defaultdict(lambda: "identification")

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if text.lower() in {"none", "null", "undefined", "nan"}:
            return ""
        return text

    def _trim_symptoms(self, value: str) -> str:
        text = self._clean_text(value)
        if not text:
            return ""
        text = re.split(
            r",\s*(?:no\s+trauma|trauma|tomo|tomando|medicamentos?|no\s+embarazo|embarazo|porque|debido\s+a|tras|fue\s+despues\s+de|fue\s+después\s+de)\b",
            text,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" .,")
        return text

    def _extract_fields(self, transcript: str) -> dict[str, Any]:
        text = self._clean_text(transcript)
        if not text:
            return {}

        lower = text.lower()
        extracted: dict[str, Any] = {}

        id_match = re.search(
            r"(?:identificacion|numero\s+de\s+identificacion|cedula|documento|id)\s*(?:es|:)?\s*([a-zA-Z0-9-]{4,30})",
            text,
            flags=re.IGNORECASE,
        )
        if id_match:
            extracted["identification_number"] = self._clean_text(id_match.group(1)).upper()

        # Fallback simple cuando el usuario solo dicta el numero.
        if "identification_number" not in extracted:
            only_number = re.fullmatch(r"\s*\d{5,20}\s*", text)
            if only_number:
                extracted["identification_number"] = self._clean_text(text)

        complaint = ""
        pain_match = re.search(r"(me\s+duele\s+[^\.,;]+)", text, flags=re.IGNORECASE)
        if pain_match:
            complaint = self._clean_text(pain_match.group(1))
        if not complaint:
            motive_match = re.search(
                r"(?:motivo(?:\s+principal)?\s+de\s+consulta\s*(?:es|:)?|me\s+siento|siento)\s+(.+)$",
                text,
                flags=re.IGNORECASE,
            )
            if motive_match:
                complaint = self._clean_text(motive_match.group(1))
        if not complaint:
            tengo_match = re.search(r"\btengo\s+(.+)$", text, flags=re.IGNORECASE)
            if tengo_match:
                candidate = self._clean_text(tengo_match.group(1))
                candidate = re.sub(r"^\d{1,3}\s+anos?\s+y\s+", "", candidate, flags=re.IGNORECASE)
                if candidate and not re.fullmatch(r"\d{1,3}\s+anos?", candidate, flags=re.IGNORECASE):
                    complaint = candidate
        if complaint:
            cleaned_symptoms = self._trim_symptoms(complaint.rstrip("."))
            if cleaned_symptoms:
                extracted["symptoms"] = cleaned_symptoms

        symptoms_match = re.search(r"(?:sintomas?|presento|presenta)\s*(?:como|son|:)?\s+(.+)$", text, flags=re.IGNORECASE)
        if symptoms_match:
            cleaned_symptoms = self._trim_symptoms(self._clean_text(symptoms_match.group(1)).rstrip("."))
            if cleaned_symptoms:
                extracted["symptoms"] = cleaned_symptoms

        if "symptoms" not in extracted and any(
            token in lower for token in ["nausea", "vomito", "fiebre", "mareo", "tos", "dolor", "cefalea", "fatiga"]
        ):
            cleaned_symptoms = self._trim_symptoms(text)
            if cleaned_symptoms:
                extracted["symptoms"] = cleaned_symptoms

        trauma_keywords = ["accidente", "caida", "caída", "golpe", "trauma", "choque"]
        if re.search(r"\bno\b.*\b(accidente|caida|caída|golpe|trauma|choque)\b", lower):
            extracted["recent_trauma"] = "no"
        elif any(word in lower for word in trauma_keywords):
            extracted["recent_trauma"] = text

        medications_keywords = [
            "medicamento", "medicamentos", "farmaco", "fármaco", "pastilla", "pastillas", "tratamiento",
            "tomo", "tomando", "consume", "consumo",
        ]
        medications_match = re.search(
            r"(?:tomo|tomando|consume|consumo|medicamentos?\s*(?:actuales)?\s*(?:son|es|:)?|tratamiento\s*(?:actual)?\s*(?:es|:)?|pastillas?\s*(?:actuales)?\s*(?:son|es|:)?)(.+)$",
            text,
            flags=re.IGNORECASE,
        )
        if medications_match:
            meds_value = self._clean_text(medications_match.group(1)).strip(" .,")
            meds_value = re.split(
                r",\s*(?:no\s+trauma|no\s+embarazo|fue\s+despues\s+de|fue\s+después\s+de|porque|debido\s+a|trauma|embarazo)\b",
                meds_value,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip(" .,")
            if meds_value:
                extracted["current_medications"] = meds_value
        elif any(word in lower for word in medications_keywords):
            extracted["current_medications"] = text
        elif re.search(r"\bno\b.*\b(medicamento|medicamentos|farmaco|fármaco|pastilla|pastillas|tratamiento)\b", lower):
            extracted["current_medications"] = "no"

        if any(word in lower for word in ["embarazada", "embarazo", "gestante", "gestacion", "gestación"]):
            if re.search(r"\bno\b.*\b(embarazo|embarazada|gestante)\b", lower):
                extracted["pregnancy"] = "no"
            else:
                extracted["pregnancy"] = "si"

        justification_match = re.search(
            r"(?:porque|por\s+|debido\s+a|despues\s+de|después\s+de|tras)\s+(.+)$",
            text,
            flags=re.IGNORECASE,
        )
        if justification_match:
            extracted["possible_justification"] = self._clean_text(justification_match.group(1)).rstrip(".")

        return {k: v for k, v in extracted.items() if k in self.ALLOWED_FIELDS}

    def _merge_structured_data(self, session_id: str, extracted: dict[str, Any]) -> dict[str, Any]:
        # Lista blanca estricta para evitar persistir campos no requeridos.
        current = {
            key: value
            for key, value in dict(self._local_structured.get(session_id, {})).items()
            if key in self.ALLOWED_FIELDS
        }
        for key, value in extracted.items():
            if key not in self.ALLOWED_FIELDS:
                continue
            cleaned = self._clean_text(value)
            if cleaned != "":
                current[key] = value
        self._local_structured[session_id] = current
        return current

    def _normalize_structured_data(self, structured_data: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key in self.OUTPUT_FIELD_ORDER:
            value = structured_data.get(key)
            cleaned = self._clean_text(value)
            normalized[key] = cleaned if cleaned else None
        return normalized

    def _next_stage_and_question(self, structured_data: dict[str, Any]) -> tuple[str, str]:
        if not structured_data.get("identification_number") or not structured_data.get("symptoms"):
            return (
                "identification",
                "Indica numero de identificacion del paciente y sintomas principales.",
            )
        if not structured_data.get("recent_trauma"):
            return (
                "recent_trauma",
                "Presenta trauma reciente como accidente, caida o golpe?",
            )
        if not structured_data.get("current_medications"):
            return (
                "current_medications",
                "Que medicamentos esta tomando actualmente? Si no toma, responde no.",
            )
        if not structured_data.get("pregnancy"):
            return ("pregnancy", "Existe embarazo o posibilidad de embarazo?")
        if not structured_data.get("possible_justification"):
            return (
                "possible_justification",
                "Existe algun posible justificante del padecimiento (por ejemplo esfuerzo, golpe, alimento o exposicion)?",
            )
        return (
            "ready_to_finalize",
            "Gracias. Se completo la captura basica. Si deseas cerrar la historia, usa el endpoint de finalizacion.",
        )

    def _build_summary(self, structured_data: dict[str, Any]) -> str:
        identification_number = self._clean_text(structured_data.get("identification_number")) or "sin identificacion"
        symptoms = self._clean_text(structured_data.get("symptoms")) or "sin sintomas registrados"
        recent_trauma = self._clean_text(structured_data.get("recent_trauma")) or "sin dato de trauma"
        current_medications = self._clean_text(structured_data.get("current_medications")) or "sin dato de medicamentos"
        pregnancy = self._clean_text(structured_data.get("pregnancy")) or "sin dato de embarazo"
        possible_justification = self._clean_text(structured_data.get("possible_justification")) or "sin justificante reportado"
        return (
            f"Paciente con identificacion {identification_number}. Sintomas: {symptoms}. "
            f"Trauma reciente: {recent_trauma}. Medicamentos actuales: {current_medications}. "
            f"Embarazo: {pregnancy}. Posible justificante: {possible_justification}."
        )

    async def _mongo_with_retries(self, operation_factory: Any) -> Any:
        retries = max(0, settings.mongo_max_retries)
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                return await asyncio.wait_for(
                    operation_factory(),
                    timeout=settings.mongo_operation_timeout_seconds,
                )
            except Exception as exc:
                last_error = exc
                if attempt < retries:
                    await asyncio.sleep(0.2 * (attempt + 1))
        if last_error:
            raise last_error

    async def _append_user_message(self, session_id: str, text: str) -> str:
        self._local_history[session_id].append({"role": "user", "content": text})
        try:
            await self._mongo_with_retries(lambda: mongo_store.ensure_session(session_id))
            await self._mongo_with_retries(
                lambda: mongo_store.append_message(
                    session_id=session_id,
                    role="user",
                    content=text,
                    metadata={"source": "voice", "session_id": session_id},
                )
            )
            return "persisted"
        except Exception:
            return "buffered"

    async def _append_assistant_message(self, session_id: str, text: str) -> str:
        self._local_history[session_id].append({"role": "assistant", "content": text})
        try:
            await self._mongo_with_retries(
                lambda: mongo_store.append_message(
                    session_id=session_id,
                    role="assistant",
                    content=text,
                    metadata={"source": "rules", "session_id": session_id},
                )
            )
            return "persisted"
        except Exception:
            return "buffered"

    async def _load_history(self, session_id: str) -> tuple[list[dict[str, str]], str]:
        try:
            history = await self._mongo_with_retries(lambda: mongo_store.get_history(session_id))
            if history:
                return history, "persisted"
        except Exception:
            pass
        return list(self._local_history.get(session_id, [])), "buffered"

    async def ensure_session(self, session_id: str) -> None:
        # No bloquea la sesion si Mongo esta caido.
        try:
            await self._mongo_with_retries(lambda: mongo_store.ensure_session(session_id))
        except Exception:
            self._local_history.setdefault(session_id, [])
            self._local_structured.setdefault(session_id, {})
            self._session_stage.setdefault(session_id, "identification")

    async def process_user_message(self, session_id: str, transcript: str) -> dict[str, Any]:
        await self.ensure_session(session_id)
        text = transcript.strip()
        if not text:
            return {
                "transcript": "",
                "assistant_reply": "",
                "structured_data": {},
                "status": "no-speech",
                "persistence": "buffered",
            }

        user_persistence = await self._append_user_message(session_id, text)

        _, history_persistence = await self._load_history(session_id)
        extracted = self._extract_fields(text)
        merged_structured = self._merge_structured_data(session_id, extracted)
        next_stage, question = self._next_stage_and_question(merged_structured)
        self._session_stage[session_id] = next_stage
        assistant_reply = question
        model_status = "ok"
        structured_data = self._normalize_structured_data(merged_structured)

        if assistant_reply:
            assistant_persistence = await self._append_assistant_message(session_id, assistant_reply)
        else:
            assistant_persistence = user_persistence

        if structured_data:
            self._local_structured[session_id] = structured_data
            try:
                await self._mongo_with_retries(
                    lambda: mongo_store.save_structured_data(session_id, structured_data)
                )
                struct_persistence = "persisted"
            except Exception:
                struct_persistence = "buffered"
        else:
            struct_persistence = assistant_persistence

        persistence = (
            "persisted"
            if all(
                item == "persisted"
                for item in [user_persistence, history_persistence, assistant_persistence, struct_persistence]
            )
            else "buffered"
        )

        return {
            "transcript": text,
            "assistant_reply": assistant_reply,
            "structured_data": structured_data,
            "status": "success",
            "persistence": persistence,
            "model_status": model_status,
            "stage": next_stage,
        }

    async def finalize_session(self, session_id: str) -> dict[str, Any]:
        """
        Cierra la sesion y guarda la historia clinica completa consolidada.
        """
        history, _ = await self._load_history(session_id)

        if not history:
            empty_record = {"clinical_history": {}, "summary": "No hay datos clinicos registrados."}
            try:
                await self._mongo_with_retries(lambda: mongo_store.ensure_session(session_id))
                await self._mongo_with_retries(lambda: mongo_store.finalize_session(session_id, empty_record))
                persistence = "persisted"
            except Exception:
                persistence = "buffered"
            return {
                "status": "completed",
                "session_id": session_id,
                "final_clinical_history": empty_record,
                "persistence": persistence,
            }

        structured_data = self._normalize_structured_data(dict(self._local_structured.get(session_id, {})))
        final_record = {
            "clinical_history": structured_data,
            "summary": self._build_summary(structured_data),
            "messages": history,
            "engine": "deterministic-rules",
        }

        persistence = "persisted"
        try:
            await self._mongo_with_retries(lambda: mongo_store.ensure_session(session_id))

            # Reintento de flush de conversacion en memoria si faltaba persistir.
            db_history = await self._mongo_with_retries(
                lambda: mongo_store.get_history(session_id, limit=2000)
            )
            db_size = len(db_history)
            local_history = self._local_history.get(session_id, [])
            if len(local_history) > db_size:
                for item in local_history[db_size:]:
                    await self._mongo_with_retries(
                        lambda item=item: mongo_store.append_message(
                            session_id=session_id,
                            role=item["role"],
                            content=item["content"],
                            metadata={"source": "buffer-flush", "session_id": session_id},
                        )
                    )

            await self._mongo_with_retries(lambda: mongo_store.finalize_session(session_id, final_record))
            await self._mongo_with_retries(
                lambda: mongo_store.append_message(
                    session_id=session_id,
                    role="assistant",
                    content="Sesion finalizada. Historia clinica consolidada y guardada.",
                    metadata={"source": "system", "session_id": session_id},
                )
            )
        except Exception:
            persistence = "buffered"

        return {
            "status": "completed",
            "session_id": session_id,
            "final_clinical_history": final_record,
            "persistence": persistence,
        }

    async def health(self) -> dict[str, Any]:
        mongo = await mongo_store.health()
        return {
            "mongo": mongo,
            "clinical_engine": {"status": "up", "type": "deterministic-rules"},
        }


clinical_conversation_service = ClinicalConversationService()

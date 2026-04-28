from __future__ import annotations

import asyncio
from typing import Any
from collections import defaultdict

from app.core.settings import settings
from app.services.mongo_service import mongo_store
from app.services.triage_service import triage_extraction_service


class ClinicalConversationService:
    ALLOWED_FIELDS = {
        "symptoms",
        "current_medications",
        "pregnancy",
        "recent_trauma",
        "possible_justification",
    }
    OUTPUT_FIELD_ORDER = (
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
        self._session_stage: dict[str, str] = defaultdict(lambda: "intake")

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if text.lower() in {"none", "null", "undefined", "nan"}:
            return ""
        return text

    def _normalize_structured_data(self, structured_data: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key in self.OUTPUT_FIELD_ORDER:
            value = structured_data.get(key)
            cleaned = self._clean_text(value)
            normalized[key] = cleaned if cleaned else None
        return normalized

    def _next_stage_and_question(self, structured_data: dict[str, Any]) -> tuple[str, str]:
        if not structured_data.get("symptoms"):
            return (
                "intake",
                "Cuéntame tu condicion o los sintomas que presentas.",
            )
        return ("ready_to_finalize", "")

    def _build_summary(self, structured_data: dict[str, Any]) -> str:
        symptoms = self._clean_text(structured_data.get("symptoms")) or "sin sintomas registrados"
        recent_trauma = self._clean_text(structured_data.get("recent_trauma")) or "sin dato de trauma"
        current_medications = self._clean_text(structured_data.get("current_medications")) or "sin dato de medicamentos"
        pregnancy = self._clean_text(structured_data.get("pregnancy")) or "sin dato de embarazo"
        possible_justification = self._clean_text(structured_data.get("possible_justification")) or "sin justificante reportado"
        return (
            f"Sintomas: {symptoms}. Trauma reciente: {recent_trauma}. Medicamentos actuales: {current_medications}. "
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
        triage_data = await triage_extraction_service.extract_preliminary_history(text)
        recommendation = triage_extraction_service.build_recommendation(triage_data)
        merged_structured = self._normalize_structured_data(triage_data.model_dump())
        self._local_structured[session_id] = merged_structured
        next_stage = "triage_completed"
        assistant_reply = recommendation
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

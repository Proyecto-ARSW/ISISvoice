"""Triage service for extracting preliminary clinical history from text/audio."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any

import httpx

from app.core.settings import settings
from app.models import TriageDataCore


class TriageExtractionService:
    """Build structured preliminary history with deterministic fallback + Ollama."""

    IA_WARNING = "Contenido generado con IA; puede contener errores."
    CHEST_PAIN_TOKEN = "dolor toracico"

    @staticmethod
    def generate_procedure_id(patient_id: str) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", patient_id)[:40] or "unknown"
        return f"{cleaned}_{ts}"

    @staticmethod
    def _clean_text(value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if text.lower() in {"none", "null", "undefined", "nan"}:
            return ""
        return text

    @staticmethod
    def _split_items(text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text)
        parts = re.split(r"[,;]|\by\b|\band\b", normalized, flags=re.IGNORECASE)
        return [p.strip(" .") for p in parts if p.strip(" .")]

    def _detect_pregnancy(self, text: str) -> bool:
        lower = text.lower()
        if re.search(r"\b(no\s+embarazada|no\s+estoy\s+embarazada|niega\s+embarazo)\b", lower):
            return False
        return bool(re.search(r"\b(embarazada|embarazo|gestante|gestacion|gestación)\b", lower))

    def _extract_symptoms(self, text: str) -> list[str]:
        lower = text.lower()
        seeds = [
            "fiebre",
            "dolor de cabeza",
            "cefalea",
            TriageExtractionService.CHEST_PAIN_TOKEN,
            "dolor abdominal",
            "mareo",
            "nauseas",
            "vomito",
            "disnea",
            "tos",
            "fatiga",
        ]
        found = [seed for seed in seeds if seed in lower]
        if found:
            return list(dict.fromkeys(found))

        match = re.search(
            r"(?:sintomas?|tengo|presento|siento|me\s+duele(?:n)?)\s*:?\s*(.+)$",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return [text.strip()] if text.strip() else []
        return self._split_items(match.group(1))

    def _extract_background(self, text: str) -> list[str]:
        match = re.search(
            r"(?:antecedentes?|historial|padezco|sufro\s+de)\s*:?\s*(.+)$",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return []
        return self._split_items(match.group(1))

    def _infer_causes(self, symptoms: list[str]) -> list[str]:
        joined = " ".join(symptoms).lower()
        causes: list[str] = []
        if any(k in joined for k in ["fiebre", "tos", "fatiga"]):
            causes.append("infeccion viral")
        if any(k in joined for k in ["mareo", "debilidad", "fatiga"]):
            causes.append("deshidratacion")
        if any(k in joined for k in [self.CHEST_PAIN_TOKEN, "disnea"]):
            causes.append("evento cardiopulmonar")
        return causes or ["requiere evaluacion clinica"]

    def _priority_from_content(self, symptoms: list[str], pregnancy: bool) -> int:
        content = " ".join(symptoms).lower()
        if any(k in content for k in ["convulsion", "inconsciente", "paro", "infarto"]):
            return 5
        if any(k in content for k in [self.CHEST_PAIN_TOKEN, "disnea severa", "hemorragia"]):
            return 4
        if any(k in content for k in ["fiebre", "vomito", "mareo"]):
            return 3
        if pregnancy and any(k in content for k in ["dolor abdominal", "sangrado"]):
            return 4
        if symptoms:
            return 2
        return 1

    def _build_ai_comment(self, priority: int) -> str:
        if priority >= 5:
            return (
                "IA: Caso critico con riesgo vital potencial. Requiere atencion inmediata, "
                "monitoreo continuo y activacion de protocolo de emergencia."
            )
        if priority == 4:
            return (
                "IA: Caso de alta prioridad. Debe valorarse en menos de 1 hora; "
                "mantener paciente en observacion y control de signos vitales."
            )
        if priority == 3:
            return (
                "IA: Caso de prioridad intermedia. No parece emergencia inmediata, "
                "pero idealmente no debe tardar mas de 3 horas en atencion. "
                "Mientras espera, mantener hidratacion y observacion clinica."
            )
        if priority == 2:
            return (
                "IA: Caso leve-moderado. Se recomienda valoracion medica programada "
                "y vigilancia de empeoramiento de sintomas."
            )
        return (
            "IA: Caso leve sin criterios de alarma aparentes. "
            "Se sugiere orientacion general y control ambulatorio."
        )

    async def _analyze_with_ollama(self, patient_id: str, transcript: str) -> dict[str, Any] | None:
        if not settings.ollama_base_url or not settings.ollama_model:
            return None

        prompt = (
            "Analiza el siguiente relato clinico y responde SOLO JSON valido con esta estructura exacta: "
            '{"sintomas":string[],"embarazo":boolean,"antecedentes":string[],"posiblesCausas":string[],'
            '"comentario":string,"nivelPrioridad":number,"comentariosIA":string}. '
            "Regla: nivelPrioridad de 1 a 5. Texto: "
            f"{transcript}"
        )
        payload = {
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        try:
            timeout = httpx.Timeout(settings.ollama_timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(f"{settings.ollama_base_url}/api/generate", json=payload)
                response.raise_for_status()
                body = response.json()
                raw = self._clean_text(body.get("response"))
                if not raw:
                    return None
                parsed = json.loads(raw)
                parsed["idpaciente"] = patient_id
                return parsed
        except Exception:
            return None

    def _normalize_data(self, patient_id: str, data: dict[str, Any], transcript: str) -> TriageDataCore:
        symptoms = data.get("sintomas") or []
        if isinstance(symptoms, str):
            symptoms = self._split_items(symptoms)
        symptoms = [self._clean_text(x) for x in symptoms if self._clean_text(x)]

        antecedentes = data.get("antecedentes") or []
        if isinstance(antecedentes, str):
            antecedentes = self._split_items(antecedentes)
        antecedentes = [self._clean_text(x) for x in antecedentes if self._clean_text(x)]

        posibles_causas = data.get("posiblesCausas") or []
        if isinstance(posibles_causas, str):
            posibles_causas = self._split_items(posibles_causas)
        posibles_causas = [self._clean_text(x) for x in posibles_causas if self._clean_text(x)]

        embarazo = bool(data.get("embarazo", False))
        nivel = int(data.get("nivelPrioridad") or 3)
        nivel = max(1, min(5, nivel))

        comentario = self._clean_text(data.get("comentario")) or transcript[:280]
        comentarios_ia = self._clean_text(data.get("comentariosIA"))
        if not comentarios_ia:
            comentarios_ia = self._build_ai_comment(nivel)

        return TriageDataCore(
            idpaciente=patient_id,
            sintomas=symptoms,
            embarazo=embarazo,
            antecedentes=antecedentes,
            posiblesCausas=posibles_causas,
            comentario=comentario,
            nivelPrioridad=nivel,
            comentariosIA=comentarios_ia,
            advertenciaIA=self.IA_WARNING,
        )

    async def extract_preliminary_history(self, patient_id: str, transcript: str) -> TriageDataCore:
        cleaned = self._clean_text(transcript)
        ollama_data = await self._analyze_with_ollama(patient_id, cleaned)
        if ollama_data:
            return self._normalize_data(patient_id, ollama_data, cleaned)

        fallback_symptoms = self._extract_symptoms(cleaned)
        fallback_background = self._extract_background(cleaned)
        fallback_pregnancy = self._detect_pregnancy(cleaned)
        fallback_causes = self._infer_causes(fallback_symptoms)
        fallback_priority = self._priority_from_content(fallback_symptoms, fallback_pregnancy)

        return TriageDataCore(
            idpaciente=patient_id,
            sintomas=fallback_symptoms,
            embarazo=fallback_pregnancy,
            antecedentes=fallback_background,
            posiblesCausas=fallback_causes,
            comentario=cleaned[:280],
            nivelPrioridad=fallback_priority,
            comentariosIA=self._build_ai_comment(fallback_priority),
            advertenciaIA=self.IA_WARNING,
        )

    def get_confidence_score(self, triage_data: TriageDataCore) -> float:
        fields = [
            triage_data.sintomas,
            triage_data.posiblesCausas,
            triage_data.comentario,
            triage_data.comentariosIA,
        ]
        filled_count = sum(1 for f in fields if f)
        return round(filled_count / len(fields), 2)


triage_extraction_service = TriageExtractionService()

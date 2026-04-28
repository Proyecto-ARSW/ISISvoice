"""Triage service for extracting preliminary clinical history from text/audio."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import unicodedata
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
    def _strip_accents(text: str) -> str:
        """Normalize accented characters for matching (e.g. torácico → toracico)."""
        return "".join(
            c for c in unicodedata.normalize("NFKD", text)
            if not unicodedata.combining(c)
        )

    @staticmethod
    def _split_items(text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text)
        parts = re.split(r"[,;]|\by\b|\band\b", normalized, flags=re.IGNORECASE)
        return [p.strip(" .") for p in parts if p.strip(" .")]

    def _detect_pregnancy(self, text: str) -> bool:
        normalized = self._strip_accents(text).lower()
        if re.search(r"\b(no\s+embarazada|no\s+estoy\s+embarazada|niega\s+embarazo)\b", normalized):
            return False
        return bool(re.search(r"\b(embarazada|embarazo|gestante|gestacion)\b", normalized))

    def _extract_symptoms(self, text: str) -> list[str]:
        normalized = self._strip_accents(text).lower()
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
        found = [seed for seed in seeds if seed in normalized]
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
        # Manchester triage scale: N1=Critico (red), N5=No urgente (blue)
        content = self._strip_accents(" ".join(symptoms)).lower()
        if any(k in content for k in ["convulsion", "inconsciente", "paro", "infarto"]):
            return 1  # N1 Critico
        if any(k in content for k in [self.CHEST_PAIN_TOKEN, "disnea severa", "hemorragia"]):
            return 2  # N2 Muy urgente
        if pregnancy and any(k in content for k in ["dolor abdominal", "sangrado"]):
            return 2  # N2 Muy urgente
        if any(k in content for k in ["fiebre", "vomito", "mareo"]):
            return 3  # N3 Urgente
        if symptoms:
            return 4  # N4 Poco urgente
        return 5  # N5 No urgente

    def _build_ai_comment(self, priority: int) -> str:
        # N1=Critico, N2=Muy urgente, N3=Urgente, N4=Poco urgente, N5=No urgente
        if priority == 1:
            return (
                "IA: Caso critico con riesgo vital potencial. Requiere atencion inmediata, "
                "monitoreo continuo y activacion de protocolo de emergencia."
            )
        if priority == 2:
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
        if priority == 4:
            return (
                "IA: Caso leve-moderado. Se recomienda valoracion medica programada "
                "y vigilancia de empeoramiento de sintomas."
            )
        return (
            "IA: Caso leve sin criterios de alarma aparentes. "
            "Se sugiere orientacion general y control ambulatorio."
        )

    async def _analyze_with_ollama(self, transcript: str) -> dict[str, Any] | None:
        if not settings.ollama_base_url or not settings.ollama_model:
            return None

        prompt = (
            "Analiza el siguiente relato clinico y responde SOLO JSON valido con esta estructura exacta: "
            '{"sintomas":string[],"embarazo":boolean,"antecedentes":string[],"posiblesCausas":string[],'
            '"comentario":string,"nivelPrioridad":number,"comentariosIA":string}. '
            "Regla: nivelPrioridad escala Manchester 1-5 donde 1=critico/emergencia y 5=no urgente. Texto: "
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
                return json.loads(raw)
        except Exception:
            return None

    def _normalize_data(self, data: dict[str, Any], transcript: str) -> TriageDataCore:
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
            sintomas=symptoms,
            embarazo=embarazo,
            antecedentes=antecedentes,
            posiblesCausas=posibles_causas,
            comentario=comentario,
            nivelPrioridad=nivel,
            comentariosIA=comentarios_ia,
            advertenciaIA=self.IA_WARNING,
        )

    def build_recommendation(self, triage_data: TriageDataCore) -> str:
        # N1=Critico, N2=Muy urgente, N3=Urgente, N4=Poco urgente, N5=No urgente
        symptoms = triage_data.sintomas or []
        causes = triage_data.posiblesCausas or []
        priority = triage_data.nivelPrioridad
        symptom_text = ", ".join(symptoms) if symptoms else "malestar no especificado"
        cause_text = ", ".join(causes) if causes else "requiere evaluacion clinica"

        if priority == 1:
            return (
                "N1 (Critico): atencion inmediata. Traslada al paciente a area critica y activa protocolo de emergencia. "
                f"Hallazgos principales: {symptom_text}. Posibles causas: {cause_text}."
            )
        if priority == 2:
            return (
                "N2 (Muy urgente): valoracion prioritaria en menos de 1 hora. Mantener monitorizacion y control de signos vitales. "
                f"Hallazgos principales: {symptom_text}. Posibles causas: {cause_text}."
            )
        if priority == 3:
            return (
                "N3 (Urgente): evaluacion pronta, idealmente en las proximas horas. Vigilar evolucion y reforzar signos de alarma. "
                f"Hallazgos principales: {symptom_text}. Posibles causas: {cause_text}."
            )
        if priority == 4:
            return (
                "N4 (Poco urgente): cuadro leve a moderado, sin criterios de alarma inmediatos. Indicar observacion y reevaluacion si empeora. "
                f"Hallazgos principales: {symptom_text}."
            )
        return (
            "N5 (No urgente): orientacion ambulatoria y seguimiento si los sintomas persisten. "
            f"Hallazgos principales: {symptom_text}."
        )

    async def extract_preliminary_history(self, transcript: str) -> TriageDataCore:
        cleaned = self._clean_text(transcript)
        ollama_data = await self._analyze_with_ollama(cleaned)
        if ollama_data:
            return self._normalize_data(ollama_data, cleaned)

        fallback_symptoms = self._extract_symptoms(cleaned)
        fallback_background = self._extract_background(cleaned)
        fallback_pregnancy = self._detect_pregnancy(cleaned)
        fallback_causes = self._infer_causes(fallback_symptoms)
        fallback_priority = self._priority_from_content(fallback_symptoms, fallback_pregnancy)

        return TriageDataCore(
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

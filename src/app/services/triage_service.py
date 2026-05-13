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

# Tracks active Ollama requests. When >= ollama_max_concurrent, new requests
# skip Ollama and fall directly to heuristics instead of queuing.
_ollama_active: int = 0

# ---------------------------------------------------------------------------
# Symptom keyword catalog — normalized (sin tildes), lowercase
# ---------------------------------------------------------------------------
_SYMPTOM_SEEDS: list[str] = [
    # Fiebre y sistémicos
    "fiebre", "escalofrios", "sudoracion", "temblores", "calosfriso", "chuchos",
    # Dolor — cabeza / ojos
    "dolor de cabeza", "cefalea", "migrana", "dolor detras de los ojos",
    "dolor retroorbital", "dolor ocular", "fotofobia",
    # Dolor — tórax
    "dolor toracico", "dolor en el pecho", "presion en el pecho", "opresion en el pecho",
    "dolor en el brazo", "dolor en el hombro",
    # Dolor — abdomen
    "dolor abdominal", "dolor de estomago", "colicos", "dolor en el vientre",
    "dolor en la barriga", "dolor en el ombligo", "retortijon",
    "dolor fosa derecha", "dolor lado derecho",
    # Dolor — musculoesquelético (clave en dengue / chikungunya)
    "dolor muscular", "mialgia", "dolor en los musculos",
    "dolor articular", "artralgia", "dolor en las articulaciones",
    "dolor en los huesos", "dolor oseo", "dolor en las piernas",
    "dolor en todo el cuerpo", "cuerpo cortado",
    # Dolor — otras zonas
    "dolor de garganta", "odinofagia", "dolor al tragar",
    "dolor lumbar", "dolor de espalda", "dolor de oidos",
    # Neurológico
    "mareo", "vertigo", "inestabilidad",
    "desmayo", "sincope", "perdida de conocimiento", "se desvanecio",
    "convulsion", "crisis convulsiva", "espasmos",
    "confusion", "desorientacion", "no responde", "somnolencia extrema",
    "no despierta", "rigidez de nuca",
    "no puede mover", "debilidad en un lado", "cara caida", "boca torcida",
    "habla difusa", "no habla bien",
    # Cardiovascular
    "palpitaciones", "latidos rapidos", "taquicardia",
    "presion alta", "hipertension", "presion baja", "hipotension",
    "pulso debil", "pulso rapido",
    # Respiratorio
    "disnea", "dificultad para respirar", "falta de aire", "ahogo",
    "silbido al respirar", "pito al respirar", "sibilancia",
    "tos", "tos con flema", "tos seca", "expectoracion", "hemoptisis",
    "piernas hinchadas", "tos con espuma",
    # Gastrointestinal
    "nauseas", "vomito", "diarrea", "deposiciones liquidas",
    "heces liquidas", "evacuaciones frecuentes",
    "sangre en las heces", "sangre en el vomito", "vomito con sangre",
    "ictericia", "coloracion amarilla", "piel amarilla", "ojos amarillos",
    "distension abdominal",
    # Deshidratación
    "sed intensa", "mucha sed", "boca seca", "labios secos",
    "orina oscura", "orina de color", "orina cafe", "no orina", "sin orinar",
    "no ha orinado", "poco orina", "ojos hundidos", "piel seca",
    "sin fuerzas", "muy decaido", "debilidad extrema",
    # Piel / mucosas / sangrado
    "sarpullido", "manchas en la piel", "erupcion cutanea", "rash",
    "manchas rojas", "puntos rojos", "petequias",
    "sangrado", "sangrando", "hemorragia",
    "sangrado por la nariz", "epistaxis",
    "sangrado de encias", "moretones", "hematomas",
    "sangrado vaginal", "sangre en la orina", "orina con sangre",
    # Trauma
    "golpe", "caida", "accidente", "choque", "atropello",
    "herida", "cortada", "laceracion", "punzada",
    "quemadura", "quemado",
    "fractura", "hueso roto", "luxacion",
    "mordedura", "picadura", "picadura de serpiente", "mordedura de culebra",
    "intoxicacion", "envenenamiento",
    # Obstétrico
    "contracciones", "dolor de parto", "ruptura de fuente", "se rompio la fuente",
    "bebe no se mueve", "no siento el bebe", "fontanela hundida",
    # Otros
    "fatiga", "cansancio excesivo", "agotamiento",
    "inflamacion", "hinchazón", "edema",
    "picazon", "urticaria",
    "dolor al orinar", "ardor al orinar",
    "ojo rojo", "conjuntivitis",
]


class TriageExtractionService:
    """Build structured preliminary history with deterministic fallback + Ollama."""

    IA_WARNING = "Contenido generado con IA; puede contener errores."
    CHEST_PAIN_TOKEN = "dolor toracico"

    # Dengue warning signs — escalation triggers per Minsalud Colombia
    _DENGUE_ALARM_SIGNS = [
        "dolor abdominal persistente", "dolor abdominal",
        "vomito persistente", "vomito con sangre",
        "sangrado", "sangrado por la nariz", "sangrado de encias",
        "petequias", "manchas rojas", "moretones",
        "dificultad para respirar", "falta de aire",
        "no despierta", "confusion", "desorientacion",
        "pulso debil", "hipotension", "presion baja",
    ]

    # Dehydration severity markers
    _DEHYDRATION_SEVERE = [
        "no orina", "no ha orinado", "sin orinar",
        "ojos hundidos", "pulso debil", "hipotension", "presion baja",
        "no despierta", "confusion", "fontanela hundida",
    ]
    _DEHYDRATION_MODERATE = [
        "sed intensa", "mucha sed", "boca seca", "labios secos",
        "orina oscura", "piel seca", "mareo", "debilidad extrema",
        "fatiga", "poco orina",
    ]

    # High-risk comorbidities that lower the alarm threshold
    _HIGH_RISK_CONDITIONS: dict[str, str] = {
        "anticoagulante": "anticoagulado — cualquier sangrado requiere evaluación inmediata",
        "warfarina": "anticoagulado con warfarina — sangrado activo → N1",
        "xarelto": "anticoagulado con rivaroxabán",
        "eliquis": "anticoagulado con apixabán",
        "diabetico": "diabetes — vigilar hipo/hiperglucemia",
        "diabetes": "diabetes",
        "insulina": "usa insulina — riesgo hipoglucemia",
        "inmunosuprimido": "inmunosuprimido — fiebre obliga a descartar sepsis",
        "quimioterapia": "en quimioterapia — neutropenia febril posible",
        "vih": "VIH — evaluar infecciones oportunistas",
        "epoc": "EPOC — disnea con umbral de alarma más bajo",
        "asma": "asma — disnea con umbral de alarma más bajo",
        "marcapasos": "portador de marcapasos",
        "falla cardiaca": "falla cardíaca — disnea/edema con umbral bajo",
        "insuficiencia cardiaca": "insuficiencia cardíaca",
        "trasplantado": "trasplantado — inmunosuprimido",
        "cirrosis": "cirrosis — sangrado gastrointestinal de alto riesgo",
        "hemofilia": "hemofilia — sangrado → N1",
    }

    # Zones endemic for malaria in Colombia
    _ENDEMIC_MALARIA_ZONES: list[str] = [
        "choco", "amazonia", "putumayo", "vaupes", "guainia",
        "pacifico", "cordoba", "sucre", "bolivar", "guajira",
        "vichada", "guaviare", "caqueta", "zona rural", "area rural",
        "rio", "selva", "jungle",
    ]

    _PEDIATRIC_SIGNALS: list[str] = [
        "mi hijo", "mi hija", "el bebe", "la bebe", "el nino", "la nina",
        "recien nacido", "meses de nacido", "meses de vida",
        "ano de edad", "anos de edad", "lactante", "infante",
    ]

    _INTENSITY_HIGH: list[str] = [
        "intenso", "severo", "fuerte", "insoportable", "muy fuerte",
        "extremo", "terrible", "horrible", "agudo", "punzante", "atroz",
    ]

    # ---------------------------------------------------------------------------
    # Utility
    # ---------------------------------------------------------------------------

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
        return "".join(
            c for c in unicodedata.normalize("NFKD", text)
            if not unicodedata.combining(c)
        )

    @staticmethod
    def _split_items(text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text)
        parts = re.split(r"[,;]|\by\b|\band\b", normalized, flags=re.IGNORECASE)
        return [p.strip(" .") for p in parts if p.strip(" .")]

    # ---------------------------------------------------------------------------
    # 1. Negation detection
    # ---------------------------------------------------------------------------

    @staticmethod
    def _is_negated(keyword: str, text: str) -> bool:
        """True if keyword appears immediately after a negation word (up to 3 tokens away)."""
        escaped = re.escape(keyword)
        pattern = (
            rf"\b(?:no|sin|niega|niego|nunca|ausencia\s+de|no\s+hay|no\s+tiene|no\s+tengo|no\s+presenta)"
            rf"\s+(?:\w+\s+){{0,3}}{escaped}"
        )
        return bool(re.search(pattern, text, re.IGNORECASE))

    # ---------------------------------------------------------------------------
    # 2. Vital signs extraction from free text
    # ---------------------------------------------------------------------------

    def _extract_vital_signs_from_text(self, text: str) -> dict[str, float]:
        n = self._strip_accents(text).lower()
        result: dict[str, float] = {}

        bp = re.search(
            r"(?:presion|pa|ta)\s*(?:arterial|de)?\s*(?:es\s+de|de|:)?\s*(\d{2,3})\s*/\s*(\d{2,3})", n
        )
        if bp:
            result["systolic"] = float(bp.group(1))
            result["diastolic"] = float(bp.group(2))

        temp = re.search(
            r"(?:temperatura|fiebre|t)\s*(?:de|:|=)?\s*(\d{2}(?:[.,]\d)?)\s*(?:grados?|°c?)?", n
        )
        if not temp:
            temp = re.search(r"(\d{2}(?:[.,]\d)?)\s*(?:grados?|°c)", n)
        if temp:
            val = float(temp.group(1).replace(",", "."))
            if 35.0 <= val <= 43.0:
                result["temperature"] = val

        spo2 = re.search(
            r"(?:saturacion|sat(?:uracion)?|spo2|oxigeno)\s*(?:de|:|=)?\s*(\d{2,3})\s*%?", n
        )
        if spo2:
            val = float(spo2.group(1))
            if 50 <= val <= 100:
                result["spo2"] = val

        hr = re.search(
            r"(?:pulso|frecuencia\s+cardiaca|fc|ritmo\s+cardiaco)\s*(?:de|:|=)?\s*(\d{2,3})\s*(?:lpm|rpm)?", n
        )
        if hr:
            val = float(hr.group(1))
            if 20 <= val <= 300:
                result["heart_rate"] = val

        return result

    def _priority_from_vitals(self, vitals: dict[str, float]) -> int:
        priority = 5
        spo2 = vitals.get("spo2")
        systolic = vitals.get("systolic")
        temp = vitals.get("temperature")
        hr = vitals.get("heart_rate")

        if spo2 is not None:
            if spo2 < 90:
                priority = min(priority, 1)
            elif spo2 < 94:
                priority = min(priority, 2)

        if systolic is not None:
            if systolic >= 180 or systolic < 80:
                priority = min(priority, 2)

        if temp is not None:
            if temp >= 40.0:
                priority = min(priority, 2)
            elif temp >= 38.5:
                priority = min(priority, 3)

        if hr is not None:
            if hr > 150 or hr < 40:
                priority = min(priority, 2)

        return priority

    # ---------------------------------------------------------------------------
    # 3. Syndrome cluster detection
    # ---------------------------------------------------------------------------

    def _detect_syndrome_clusters(self, text: str) -> list[tuple[str, int]]:
        """Returns list of (cause_label, priority) for recognized clinical syndromes."""
        n = self._strip_accents(text).lower()
        clusters: list[tuple[str, int]] = []

        # IAM / SCA (Síndrome Coronario Agudo)
        chest_pain = any(s in n for s in [self.CHEST_PAIN_TOKEN, "dolor en el pecho", "opresion en el pecho", "presion en el pecho"])
        if chest_pain and any(s in n for s in ["sudoracion", "nauseas", "dolor en el brazo", "dolor en el hombro", "palpitaciones"]):
            clusters.append(("posible SCA/infarto (síndrome coronario agudo)", 1))

        # ACV / Ictus
        focal_neuro = any(s in n for s in ["debilidad en un lado", "no puede mover", "cara caida", "boca torcida", "habla difusa", "no habla bien"])
        if focal_neuro and any(s in n for s in ["cefalea", "dolor de cabeza", "mareo", "confusion"]):
            clusters.append(("posible ACV/ictus — activar protocolo stroke", 1))

        # Meningitis
        if "fiebre" in n and "rigidez de nuca" in n and any(s in n for s in ["cefalea", "vomito", "fotofobia", "confusion"]):
            clusters.append(("posible meningitis bacteriana — emergencia", 1))

        # Sepsis
        if "fiebre" in n and any(s in n for s in ["confusion", "desorientacion", "no responde"]) and any(s in n for s in ["taquicardia", "latidos rapidos", "pulso rapido"]):
            clusters.append(("posible sepsis", 1))

        # Edema pulmonar / ICC descompensada
        dyspnea = any(s in n for s in ["dificultad para respirar", "falta de aire", "disnea"])
        if dyspnea and any(s in n for s in ["piernas hinchadas", "edema", "hinchazón", "tos con espuma"]):
            clusters.append(("posible edema pulmonar / ICC descompensada", 1))

        # Embarazo ectópico
        if any(s in n for s in ["embarazada", "gestante", "embarazo"]) and "dolor abdominal" in n and "sangrado vaginal" in n:
            clusters.append(("posible embarazo ectópico — emergencia", 1))

        # Apendicitis
        if any(s in n for s in ["dolor fosa derecha", "dolor lado derecho", "fosa iliaca"]) and any(s in n for s in ["fiebre", "nauseas", "vomito"]):
            clusters.append(("posible apendicitis", 2))

        # Hipoglucemia
        if any(s in n for s in ["diabetico", "diabetes", "insulina"]) and any(s in n for s in ["mareo", "confusion", "temblores", "sudoracion", "debilidad"]):
            clusters.append(("posible hipoglucemia", 2))

        # Cólico renoureteral
        if any(s in n for s in ["dolor lumbar", "dolor de espalda"]) and any(s in n for s in ["sangre en la orina", "orina con sangre", "ardor al orinar", "dolor al orinar"]):
            clusters.append(("posible cólico renoureteral", 3))

        # Ofidismo siempre N1
        if any(s in n for s in ["mordedura de culebra", "picadura de serpiente", "ofidismo", "culebra", "serpiente"]):
            clusters.append(("ofidismo (mordedura de serpiente) — emergencia", 1))

        return clusters

    # ---------------------------------------------------------------------------
    # 4. High-risk factor detection
    # ---------------------------------------------------------------------------

    def _detect_high_risk_factors(self, text: str) -> list[str]:
        n = self._strip_accents(text).lower()
        return [label for kw, label in self._HIGH_RISK_CONDITIONS.items() if kw in n]

    # ---------------------------------------------------------------------------
    # 5. Pediatric context
    # ---------------------------------------------------------------------------

    def _detect_pediatric_context(self, text: str) -> bool:
        n = self._strip_accents(text).lower()
        return any(s in n for s in self._PEDIATRIC_SIGNALS)

    # ---------------------------------------------------------------------------
    # 6. Geographic / endemic zone context
    # ---------------------------------------------------------------------------

    def _detect_endemic_zone(self, text: str) -> str | None:
        n = self._strip_accents(text).lower()
        for zone in self._ENDEMIC_MALARIA_ZONES:
            if zone in n:
                return zone
        return None

    # ---------------------------------------------------------------------------
    # 7. Duration extraction
    # ---------------------------------------------------------------------------

    def _symptom_duration_days(self, text: str) -> int | None:
        n = self._strip_accents(text).lower()
        m = re.search(r"hace\s+(\d+)\s+dias?", n)
        if m:
            return int(m.group(1))
        m = re.search(r"hace\s+(\d+)\s+semanas?", n)
        if m:
            return int(m.group(1)) * 7
        m = re.search(r"hace\s+(\d+)\s+horas?", n)
        if m:
            return 0
        if any(s in n for s in ["desde ayer", "desde anoche"]):
            return 1
        if any(s in n for s in ["esta manana", "hace un rato", "hace un momento", "ahorita"]):
            return 0
        return None

    # ---------------------------------------------------------------------------
    # 8. High-intensity qualifier
    # ---------------------------------------------------------------------------

    def _has_high_intensity(self, text: str) -> bool:
        n = self._strip_accents(text).lower()
        return any(word in n for word in self._INTENSITY_HIGH)

    # ---------------------------------------------------------------------------
    # Core extraction
    # ---------------------------------------------------------------------------

    def _detect_pregnancy(self, text: str) -> bool:
        normalized = self._strip_accents(text).lower()
        if re.search(
            r"\b(no\s+embarazada|no\s+estoy\s+embarazada|niega\s+embarazo|no\s+esta\s+embarazada)\b",
            normalized,
        ):
            return False
        return bool(
            re.search(
                r"\b(embarazada|embarazo|gestante|gestacion|en\s+estado|semanas\s+de\s+gestacion"
                r"|meses\s+de\s+embarazo|estoy\s+esperando)\b",
                normalized,
            )
        )

    def _extract_symptoms(self, text: str) -> list[str]:
        normalized = self._strip_accents(text).lower()
        # Collect seeds, then filter out negated ones
        found = [
            seed for seed in _SYMPTOM_SEEDS
            if seed in normalized and not self._is_negated(seed, normalized)
        ]
        if found:
            return list(dict.fromkeys(found))

        match = re.search(
            r"(?:sintomas?|tengo|presento|siento|me\s+duele(?:n)?|sufro\s+de|padezco)\s*:?\s*(.+)$",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return [text.strip()] if text.strip() else []
        return self._split_items(match.group(1))

    def _extract_background(self, text: str) -> list[str]:
        match = re.search(
            r"(?:antecedentes?|historial|padezco\s+de|sufro\s+de|me\s+han\s+diagnosticado|tengo\s+diagnostico\s+de)\s*:?\s*(.+)$",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return []
        return self._split_items(match.group(1))

    def _detect_dehydration_severity(self, normalized: str) -> str:
        if any(s in normalized for s in self._DEHYDRATION_SEVERE):
            return "severe"
        moderate_count = sum(1 for s in self._DEHYDRATION_MODERATE if s in normalized)
        if moderate_count >= 2:
            return "moderate"
        if any(s in normalized for s in ["sed intensa", "boca seca", "orina oscura"]):
            return "mild"
        return "none"

    def _detect_dengue_pattern(self, normalized: str) -> bool:
        has_fever = "fiebre" in normalized
        dengue_signs = [
            "cefalea", "dolor de cabeza",
            "dolor detras de los ojos", "dolor retroorbital",
            "mialgia", "dolor muscular", "dolor en los musculos",
            "artralgia", "dolor articular", "cuerpo cortado",
            "sarpullido", "manchas rojas", "erupcion cutanea", "rash",
            "nauseas", "vomito",
        ]
        sign_count = sum(1 for s in dengue_signs if s in normalized)
        return has_fever and sign_count >= 2

    def _detect_dengue_alarm(self, normalized: str) -> bool:
        return any(s in normalized for s in self._DENGUE_ALARM_SIGNS)

    def _infer_causes(
        self, symptoms: list[str], pregnancy: bool = False, transcript: str = ""
    ) -> list[str]:
        joined = " ".join(symptoms).lower()
        raw = self._strip_accents(transcript).lower() if transcript else joined
        causes: list[str] = []

        # Syndrome clusters have priority (most specific)
        for label, _ in self._detect_syndrome_clusters(transcript or joined):
            if label not in causes:
                causes.append(label)

        # Dengue / arbovirales
        dengue_signs = [
            "sarpullido", "manchas rojas", "erupcion cutanea", "rash",
            "dolor detras de los ojos", "dolor retroorbital",
            "mialgia", "artralgia", "dolor en los huesos", "cuerpo cortado",
        ]
        if "fiebre" in joined and any(s in joined for s in dengue_signs):
            if not any("SCA" in c or "ictus" in c or "meningitis" in c for c in causes):
                causes.append("dengue / chikungunya / arboviral")

        # Malaria — boost if from endemic zone
        endemic_zone = self._detect_endemic_zone(raw)
        if "fiebre" in joined and any(s in joined for s in ["escalofrios", "sudoracion", "temblores"]):
            label = f"malaria (zona endémica: {endemic_zone})" if endemic_zone else "malaria (descartar si viene de zona endémica)"
            causes.append(label)

        # Deshidratación
        dehydration_indicators = [
            "sed intensa", "mucha sed", "boca seca", "orina oscura",
            "no orina", "ojos hundidos", "piel seca",
        ]
        if any(s in joined for s in dehydration_indicators) or (
            any(s in joined for s in ["vomito", "diarrea"])
            and any(s in joined for s in ["mareo", "fatiga", "debilidad extrema", "sin fuerzas"])
        ):
            causes.append("deshidratacion")

        # EDA
        if any(s in joined for s in ["diarrea", "deposiciones liquidas", "heces liquidas"]) and any(
            s in joined for s in ["vomito", "nauseas", "dolor abdominal", "colicos"]
        ):
            causes.append("gastroenteritis / EDA")

        # IRA
        if any(s in joined for s in ["tos", "dolor de garganta", "expectoracion"]) and "fiebre" in joined:
            causes.append("infeccion respiratoria aguda (IRA)")

        # Neumonía
        if any(s in joined for s in ["disnea", "dificultad para respirar", "falta de aire"]) and "fiebre" in joined:
            if "posible neumonia" not in " ".join(causes):
                causes.append("posible neumonia / compromiso pulmonar")

        # Evento cardiopulmonar genérico (si no se detectó SCA ya)
        if not any("SCA" in c or "coronario" in c for c in causes):
            if any(s in joined for s in [self.CHEST_PAIN_TOKEN, "presion en el pecho", "opresion en el pecho"]) or (
                "disnea" in joined and "palpitaciones" in joined
            ):
                causes.append("evento cardiopulmonar")

        # HTA / crisis hipertensiva
        if any(s in joined for s in ["presion alta", "hipertension", "cefalea"]) and any(
            s in joined for s in ["palpitaciones", "taquicardia", "vision borrosa"]
        ):
            causes.append("crisis hipertensiva")

        # Trauma
        if any(s in joined for s in ["golpe", "caida", "accidente", "herida", "cortada", "quemadura", "fractura", "luxacion"]):
            causes.append("trauma / lesion mecanica")

        # Intoxicación
        if any(s in joined for s in ["intoxicacion", "envenenamiento"]):
            causes.append("intoxicacion / envenenamiento")

        # Obstétrica (si no se detectó ectópico ya)
        if pregnancy and not any("ectopico" in c for c in causes):
            if any(s in joined for s in ["contracciones", "sangrado vaginal", "ruptura de fuente", "dolor abdominal"]):
                causes.append("complicacion obstetrica")

        # Trastorno neurológico
        if any(s in joined for s in ["convulsion", "crisis convulsiva"]) and not any("ACV" in c or "meningitis" in c for c in causes):
            causes.append("trastorno neurologico / convulsivo")

        # Fiebre sin foco claro (último recurso)
        if "fiebre" in joined and not causes:
            causes.append("sindrome febril — requiere identificar foco")

        # Viral genérica (si no hay causa más específica)
        if any(s in joined for s in ["fiebre", "tos", "fatiga"]) and len(causes) == 0:
            causes.append("infeccion viral")

        return list(dict.fromkeys(causes)) or ["requiere evaluacion clinica"]

    def _priority_from_content(
        self, symptoms: list[str], pregnancy: bool, transcript: str = ""
    ) -> int:
        content = self._strip_accents(" ".join(symptoms)).lower()
        raw = self._strip_accents(transcript).lower() if transcript else content

        # Vital signs from free text (objective beats subjective)
        vitals = self._extract_vital_signs_from_text(raw)
        vital_priority = self._priority_from_vitals(vitals)

        # High-intensity modifier — one level up for key symptoms
        intensity_boost = self._has_high_intensity(raw)

        # High-risk comorbidity → lower thresholds
        high_risk = bool(self._detect_high_risk_factors(raw))

        # Pediatric context
        pediatric = self._detect_pediatric_context(raw)

        # Syndrome clusters (highest specificity)
        clusters = self._detect_syndrome_clusters(raw)
        if clusters:
            cluster_priority = min(p for _, p in clusters)
            return min(vital_priority, cluster_priority)

        # --- N1: Crítico —  riesgo vital inmediato ---
        critical_keywords = [
            "convulsion", "inconsciente", "no despierta", "no responde",
            "paro", "infarto", "paro cardiaco", "paro respiratorio",
            "hemorragia", "sangrado masivo",
            "quemadura extensa", "quemadura en cara",
            "trauma craneoencefalico",
            "intoxicacion grave", "envenenamiento",
        ]
        if any(k in content for k in critical_keywords):
            return min(1, vital_priority)

        # Obstétrica crítica
        if pregnancy and any(k in content for k in ["ruptura de fuente", "bebe no se mueve", "no siento el bebe"]):
            return 1

        # Deshidratación severa (choque)
        severe_dehy = [
            "no orina", "no ha orinado", "ojos hundidos",
            "pulso debil", "confusion", "desorientacion",
        ]
        if any(k in content for k in severe_dehy):
            return min(1, vital_priority)

        # Pediatric: fontanela hundida → N1
        if pediatric and "fontanela hundida" in content:
            return 1

        # Anticoagulado + cualquier sangrado → N1
        if high_risk and any(k in content for k in ["sangrado", "hemorragia", "sangre", "vomito con sangre"]):
            raw_risks = self._detect_high_risk_factors(raw)
            anticoag = any("anticoag" in r or "warfar" in r or "rivarox" in r or "apixab" in r or "hemofilia" in r for r in raw_risks)
            if anticoag:
                return 1

        # --- N2: Muy urgente ---
        very_urgent = [
            self.CHEST_PAIN_TOKEN, "presion en el pecho", "opresion en el pecho",
            "dificultad para respirar", "falta de aire", "ahogo", "silbido al respirar",
            "sangrado activo", "vomito con sangre", "sangre en las heces",
            "presion alta", "hipertension",
            "quemadura", "fractura", "hueso roto",
        ]
        if any(k in content for k in very_urgent):
            p = 2
            if intensity_boost:
                p = 1
            return min(p, vital_priority)

        # Dengue con señales de alarma → N2
        dengue_alarm = [
            "sangrado de encias", "petequias",
            "dolor abdominal", "vomito persistente",
        ]
        if "fiebre" in content and any(k in content for k in dengue_alarm):
            return min(2, vital_priority)

        # Embarazo con sangrado/dolor → N2
        if pregnancy and any(k in content for k in ["sangrado vaginal", "contracciones", "dolor abdominal"]):
            return min(2, vital_priority)

        # Deshidratación moderada (≥2 signos)
        dehydration_moderate = [
            "sed intensa", "boca seca", "orina oscura", "piel seca",
            "mucha sed", "labios secos",
        ]
        if sum(1 for k in dehydration_moderate if k in content) >= 2:
            return min(2, vital_priority)

        # High-risk + cualquier N3 symptom → N2
        if high_risk and any(k in content for k in ["fiebre", "diarrea", "vomito", "disnea", "mareo"]):
            return min(2, vital_priority)

        # Pediatric: fiebre alta → N2 (umbral más bajo)
        if pediatric and "fiebre" in content:
            temp = vitals.get("temperature")
            if temp is None or temp >= 38.0:
                return min(2, vital_priority)

        # --- N3: Urgente ---
        urgent = [
            "fiebre", "vomito", "mareo", "diarrea",
            "dolor abdominal", "cefalea",
            "mialgia", "artralgia", "cuerpo cortado",
            "sarpullido", "erupcion cutanea",
            "escalofrios", "palpitaciones",
            "tos", "dolor de garganta",
            "debilidad extrema", "sed intensa",
        ]
        if any(k in content for k in urgent):
            p = 3
            if intensity_boost:
                p = 2
            return min(p, vital_priority)

        if symptoms:
            return min(4, vital_priority)
        return min(5, vital_priority)

    def _build_ai_comment(
        self,
        priority: int,
        symptoms: list[str] | None = None,
        transcript: str = "",
        high_risk: list[str] | None = None,
        clusters: list[tuple[str, int]] | None = None,
    ) -> str:
        sym_text = self._strip_accents(" ".join(symptoms or [])).lower()
        raw = self._strip_accents(transcript).lower() if transcript else sym_text

        dengue_pattern = self._detect_dengue_pattern(sym_text or raw)
        dehy_severity = self._detect_dehydration_severity(sym_text or raw)
        snake_bite = any(s in raw for s in ["culebra", "serpiente", "ofidismo"])
        obstetric = any(s in raw for s in ["contracciones", "ruptura de fuente", "sangrado vaginal"])
        pediatric = self._detect_pediatric_context(raw)
        endemic_zone = self._detect_endemic_zone(raw)
        risk_factors = high_risk or self._detect_high_risk_factors(raw)
        vitals = self._extract_vital_signs_from_text(raw)

        specific: list[str] = []

        if snake_bite:
            specific.append(
                "OFIDISMO: inmovilizar extremidad, NO torniquete ni incisiones, NO succionar. "
                "Traslado urgente a centro con suero antiofídico polivalente."
            )

        for label, p in (clusters or []):
            if "SCA" in label or "coronario" in label:
                specific.append("SCA posible: ECG inmediato, AAS 300 mg si no está contraindicado, acceso venoso.")
            elif "ACV" in label or "ictus" in label:
                specific.append("Posible ACV: activar protocolo stroke, TC de cráneo urgente, hora exacta de inicio de síntomas.")
            elif "meningitis" in label:
                specific.append("Meningitis posible: aislamiento de contacto, antibiótico IV precoz, TC antes de PL si hay papiledema.")
            elif "sepsis" in label:
                specific.append("Posible sepsis: hemocultivos x2, lactato sérico, antibiótico IV en <1 h (protocolo Sepsis-3).")
            elif "ectopico" in label:
                specific.append("Embarazo ectópico posible: βhCG + ecografía transvaginal urgente, acceso venoso.")
            elif "hipoglucemia" in label:
                specific.append("Hipoglucemia posible: glucometría inmediata; si <70 mg/dL, glucosa oral o IV según tolerancia.")

        if dengue_pattern:
            specific.append(
                "Patrón dengue/arboviral: NO ibuprofeno ni aspirina (riesgo hemorragia). "
                "Solo paracetamol. Vigilar señales alarma: sangrado, dolor abdominal, decaimiento extremo, no orina."
            )

        if endemic_zone and "fiebre" in (sym_text + raw):
            specific.append(
                f"Zona endémica reportada ({endemic_zone}): descartar malaria, "
                "solicitar gota gruesa / frotis de sangre periférica."
            )

        if dehy_severity in ("severe", "moderate"):
            if dehy_severity == "severe":
                specific.append(
                    "DESHIDRATACIÓN SEVERA: hidratación EV urgente (SSN 0.9% o Lactato Ringer). "
                    "Evaluar signos de choque: llenado capilar, tensión arterial, diuresis."
                )
            else:
                specific.append(
                    "Deshidratación moderada: iniciar suero oral (Vida Suero Oral / Pedialyte) o agua de panela con sal. "
                    "Si no tolera vía oral, pasar a hidratación EV."
                )
        elif dehy_severity == "mild":
            specific.append("Hidratación oral preventiva; vigilar aparición de otros signos de deshidratación.")

        if obstetric:
            specific.append("Urgencia obstétrica posible: monitoreo fetal inmediato, no dejar sola a la paciente.")

        if pediatric:
            specific.append("Paciente pediátrico: usar tablas de referencia pediátrica para signos vitales y dosis.")

        if vitals:
            vital_notes = []
            spo2 = vitals.get("spo2")
            temp = vitals.get("temperature")
            systolic = vitals.get("systolic")
            hr = vitals.get("heart_rate")
            if spo2 is not None and spo2 < 94:
                vital_notes.append(f"SpO2 {spo2:.0f}% — oxígeno suplementario")
            if temp is not None and temp >= 38.5:
                vital_notes.append(f"Temperatura {temp}°C — manejo antipirético")
            if systolic is not None and systolic >= 180:
                vital_notes.append(f"TA sistólica {systolic:.0f} mmHg — posible crisis hipertensiva")
            if hr is not None and (hr > 120 or hr < 50):
                vital_notes.append(f"FC {hr:.0f} lpm — monitoreo cardíaco")
            if vital_notes:
                specific.append("Signos vitales en texto: " + "; ".join(vital_notes) + ".")

        if risk_factors:
            specific.append("Comorbilidades: " + " | ".join(risk_factors) + ".")

        base: str
        if priority == 1:
            base = (
                "CASO CRÍTICO — riesgo vital. Atención inmediata, activar código de emergencia, "
                "acceso venoso periférico, monitoreo continuo."
            )
        elif priority == 2:
            base = (
                "Alta prioridad: valoración en menos de 30 minutos. "
                "Control de signos vitales, paciente en observación."
            )
        elif priority == 3:
            base = (
                "Prioridad intermedia: atención en no más de 2 horas. "
                "Hidratación oral, reposo, vigilar signos de alarma. "
                "En Colombia, síndrome febril: siempre descartar dengue."
            )
        elif priority == 4:
            base = (
                "Cuadro leve-moderado: valoración médica programada. "
                "Volver a urgencias si aparece fiebre alta, sangrado o dificultad respiratoria."
            )
        else:
            base = (
                "Cuadro leve sin criterios de alarma. "
                "Orientación ambulatoria, hidratación adecuada, control si persiste."
            )

        parts = ["IA: " + base] + specific
        return " | ".join(parts)

    # ---------------------------------------------------------------------------
    # Ollama integration
    # ---------------------------------------------------------------------------

    async def _analyze_with_ollama(self, transcript: str) -> dict[str, Any] | None:
        global _ollama_active
        if not settings.ollama_base_url or not settings.ollama_model:
            return None
        if _ollama_active >= settings.ollama_max_concurrent:
            return None

        prompt = (
            "Analiza el siguiente relato clinico de un paciente en Colombia y responde SOLO JSON valido "
            "con esta estructura exacta: "
            '{"sintomas":string[],"embarazo":boolean,"antecedentes":string[],"posiblesCausas":string[],'
            '"comentario":string,"nivelPrioridad":number,"comentariosIA":string}. '
            "Regla: nivelPrioridad escala Manchester 1-5 donde 1=critico/emergencia y 5=no urgente. "
            "Considera enfermedades endémicas de Colombia: dengue, chikungunya, malaria, EDA, IRA, deshidratacion. "
            "NO usar ibuprofeno/aspirina si sospecha dengue. Texto: "
            f"{transcript}"
        )
        payload = {
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        import logging
        _log = logging.getLogger(__name__)
        _log.info(f"[Ollama] url={settings.ollama_base_url} model={settings.ollama_model} timeout={settings.ollama_timeout_seconds}")
        _ollama_active += 1
        try:
            timeout = httpx.Timeout(settings.ollama_timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(f"{settings.ollama_base_url}/api/generate", json=payload)
                response.raise_for_status()
                body = response.json()
                raw = self._clean_text(body.get("response"))
                if not raw:
                    _log.warning("[Ollama] response vacío — fallback")
                    return None
                stripped = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
                stripped = re.sub(r"\s*```$", "", stripped.strip())
                return json.loads(stripped)
        except Exception as e:
            _log.error(f"[Ollama] FALLÓ {type(e).__name__}: {e}")
            return None
        finally:
            _ollama_active -= 1

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
            comentarios_ia = self._build_ai_comment(nivel, symptoms, transcript)

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

    # ---------------------------------------------------------------------------
    # Public API — contracts unchanged
    # ---------------------------------------------------------------------------

    def build_recommendation(self, triage_data: TriageDataCore) -> str:
        symptoms = triage_data.sintomas or []
        causes = triage_data.posiblesCausas or []
        priority = triage_data.nivelPrioridad
        symptom_text = ", ".join(symptoms) if symptoms else "malestar no especificado"
        cause_text = ", ".join(causes) if causes else "requiere evaluacion clinica"
        content = self._strip_accents(" ".join(symptoms)).lower()

        dengue_hint = (
            " [ALERTA DENGUE: no administrar ibuprofeno ni aspirina]"
            if self._detect_dengue_pattern(content)
            else ""
        )
        dehy_level = self._detect_dehydration_severity(content)
        dehydration_hint = (
            " [DESHIDRATACION: hidratación oral inmediata o EV si no tolera vía oral]"
            if dehy_level in ("severe", "moderate")
            else ""
        )
        dengue_alarm_hint = (
            " [SEÑALES DE ALARMA DENGUE — prioridad máxima]"
            if self._detect_dengue_alarm(content)
            else ""
        )

        if priority == 1:
            return (
                f"N1 (Crítico): atención inmediata — activar protocolo emergencia, trasladar área crítica."
                f"{dengue_hint}{dengue_alarm_hint}{dehydration_hint} "
                f"Hallazgos: {symptom_text}. Posibles causas: {cause_text}."
            )
        if priority == 2:
            return (
                f"N2 (Muy urgente): valoración en menos de 30 minutos. "
                f"Control signos vitales, monitorización.{dengue_hint}{dengue_alarm_hint}{dehydration_hint} "
                f"Hallazgos: {symptom_text}. Posibles causas: {cause_text}."
            )
        if priority == 3:
            return (
                f"N3 (Urgente): atención en no más de 2 horas. "
                f"Vigilar evolución, reforzar señales de alarma.{dengue_hint}{dehydration_hint} "
                f"Hallazgos: {symptom_text}. Posibles causas: {cause_text}. "
                f"Síndrome febril en Colombia: descartar dengue."
            )
        if priority == 4:
            return (
                f"N4 (Poco urgente): cuadro leve-moderado sin criterios de alarma inmediatos. "
                f"Observación y reevaluación si empeora.{dengue_hint} "
                f"Hallazgos: {symptom_text}."
            )
        return (
            f"N5 (No urgente): orientación ambulatoria; seguimiento si síntomas persisten. "
            f"Hallazgos: {symptom_text}."
        )

    async def extract_preliminary_history(self, transcript: str) -> TriageDataCore:
        cleaned = self._clean_text(transcript)
        ollama_data = await self._analyze_with_ollama(cleaned)
        if ollama_data:
            return self._normalize_data(ollama_data, cleaned)

        fallback_symptoms = self._extract_symptoms(cleaned)
        fallback_background = self._extract_background(cleaned)
        fallback_pregnancy = self._detect_pregnancy(cleaned)
        fallback_causes = self._infer_causes(fallback_symptoms, fallback_pregnancy, cleaned)
        fallback_priority = self._priority_from_content(fallback_symptoms, fallback_pregnancy, cleaned)
        clusters = self._detect_syndrome_clusters(cleaned)
        high_risk = self._detect_high_risk_factors(cleaned)

        return TriageDataCore(
            sintomas=fallback_symptoms,
            embarazo=fallback_pregnancy,
            antecedentes=fallback_background,
            posiblesCausas=fallback_causes,
            comentario=cleaned[:280],
            nivelPrioridad=fallback_priority,
            comentariosIA=self._build_ai_comment(
                fallback_priority,
                fallback_symptoms,
                cleaned,
                high_risk,
                clusters,
            ),
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

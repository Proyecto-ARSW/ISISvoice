"""Triage service for extracting clinical data from transcripts."""
from datetime import datetime
import re
from typing import Optional, Dict, Any
from app.models import TriageDataCore


class TriageExtractionService:
    """Service for extracting triage data from patient transcripts."""

    @staticmethod
    def generate_procedure_id(cedula: Optional[str]) -> str:
        """
        Generate unique procedure ID from cedula and timestamp.
        Format: cedula_YYYYMMDDHHmmss
        """
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        if cedula:
            cedula_clean = re.sub(r"\D", "", cedula)[:15]
            return f"{cedula_clean}_{ts}"
        return f"unknown_{ts}"

    @staticmethod
    def _clean_text(value: Any) -> str:
        """Clean and normalize text values."""
        if value is None:
            return ""
        text = str(value).strip()
        if text.lower() in {"none", "null", "undefined", "nan", ""}:
            return ""
        return text

    @staticmethod
    def _extract_cedula(text: str) -> Optional[str]:
        """Extract cedula/ID number from text."""
        # Pattern: "cédula es 1234567890" or just "1234567890"
        match = re.search(
            r"(?:cedula|cédula|identificacion|identificación|id|documento)\s*(?:es|:)?\s*([0-9]{5,20})",
            text,
            flags=re.IGNORECASE
        )
        if match:
            return match.group(1)
        
        # Fallback: look for standalone numbers
        only_number = re.search(r"\b([0-9]{6,20})\b", text)
        if only_number:
            return only_number.group(1)
        
        return None

    @staticmethod
    def _extract_symptoms(text: str) -> Optional[str]:
        """Extract primary symptoms from text."""
        # Pattern: "me duele...", "tengo...", "me siento..."
        patterns = [
            r"(?:me\s+duele|me\s+duelen)\s+(.+?)(?:\.|,|$|\b(?:y|no|trauma|medicamentos?|embarazo)\b)",
            r"(?:tengo|presento|siento)\s+(.+?)(?:\.|,|$|\b(?:y|no|trauma|medicamentos?|embarazo)\b)",
            r"(?:motivo\s+de\s+consulta)\s*(?:es|:)?\s*(.+?)(?:\.|,|$)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                symptoms = TriageExtractionService._clean_text(match.group(1))
                if symptoms:
                    return symptoms
        
        return None

    @staticmethod
    def _extract_pregnancy(text: str) -> Optional[str]:
        """Extract pregnancy status from text."""
        if re.search(r"\b(?:no\s+embarazada|no\s+estoy\s+embarazada|not\s+pregnant)\b", text, flags=re.IGNORECASE):
            return "no"
        if re.search(r"\b(?:embarazada|pregnant|gestante|estoy\s+embarazada)\b", text, flags=re.IGNORECASE):
            return "si"
        if re.search(r"\b(?:no\s+se|no\s+sé|desconozco|posible|podría|pueda)\b", text, flags=re.IGNORECASE):
            return None
        return None

    @staticmethod
    def _extract_trauma(text: str) -> Optional[str]:
        """Extract recent trauma information."""
        if re.search(r"\b(?:no\s+trauma|sin\s+trauma|ningun\s+trauma|ningún\s+trauma|no\s+tuve\s+trauma)\b", text, flags=re.IGNORECASE):
            return "no"

        trauma_patterns = [
            r"(?:trauma|accidente|golpe|caída|caida|fractura)\s*(?:en|hace|reciente)?(?:\s+(\w+))?\s*(?:dias|horas|años)?",
            r"(?:me\s+cai|me\s+caí|me\s+golpee|me\s+golpeé)\b\s*(.+?)(?:[,\.]|$)",
            r"(?:accidente|trauma|lesión|lesion)\s*(?::)?\s*(.+?)(?:[,\.]|$)",
        ]
        
        for pattern in trauma_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                trauma = TriageExtractionService._clean_text(
                    match.group(1) if match.lastindex else match.group(0)
                )
                if trauma and trauma.lower() != "no":
                    return trauma
        
        return None

    @staticmethod
    def _extract_justification(text: str) -> Optional[str]:
        """Extract possible justification/context."""
        patterns = [
            r"(?:antecedente|antecedentes|historial|historia|previousamente|previamente)\s*(?::)?\s*(.+?)(?:[,\.]|$)",
            r"(?:porque|por que|porqué|por lo que|debido a)\s+(.+?)(?:[,\.]|$)",
            r"(?:tengo|padezco|sufro\s+de)\s+(?:hipertension|diabetes|asma|alergia|otras\s+enfermedades?)\b(.+?)(?:[,\.]|$)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                justification = TriageExtractionService._clean_text(match.group(1))
                if justification:
                    return justification
        
        return None

    def extract_triage_data(self, transcript: str) -> TriageDataCore:
        """
        Extract triage data from a patient transcript.
        
        Args:
            transcript: Patient input (voice transcription or text)
        
        Returns:
            TriageDataCore with extracted data
        """
        text = self._clean_text(transcript)
        
        cedula = self._extract_cedula(text)
        symptoms = self._extract_symptoms(text)
        pregnancy = self._extract_pregnancy(text)
        trauma = self._extract_trauma(text)
        justification = self._extract_justification(text)
        
        return TriageDataCore(
            identification_number=cedula,
            symptoms=symptoms,
            pregnancy=pregnancy,
            recent_trauma=trauma,
            possible_justification=justification,
        )

    def get_confidence_score(self, triage_data: TriageDataCore) -> float:
        """
        Calculate extraction confidence score (0-1).
        Higher score means more fields were successfully extracted.
        """
        fields = [
            triage_data.identification_number,
            triage_data.symptoms,
            triage_data.pregnancy,
            triage_data.recent_trauma,
            triage_data.possible_justification,
        ]
        filled_count = sum(1 for f in fields if f is not None and f != "")
        total_fields = len(fields)
        return round(filled_count / total_fields, 2) if total_fields > 0 else 0.0


# Singleton instance
triage_extraction_service = TriageExtractionService()

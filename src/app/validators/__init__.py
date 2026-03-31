"""Validators for clinical triage data."""
import re
from datetime import date
from typing import Optional
from pydantic import ValidationError


class TriageDataValidator:
    """Validators for triage data extraction."""

    @staticmethod
    def validate_cedula(cedula: Optional[str]) -> bool:
        """Validate cedula format."""
        if not cedula:
            return False
        cleaned = re.sub(r"\D", "", cedula)
        if len(cleaned) < 5 or len(cleaned) > 20:
            return False
        return True

    @staticmethod
    def validate_symptoms(symptoms: Optional[str]) -> bool:
        """Validate symptoms field."""
        if not symptoms:
            return True  # Optional field
        if len(symptoms) < 3 or len(symptoms) > 500:
            return False
        return True

    @staticmethod
    def validate_pregnancy(pregnancy: Optional[str]) -> bool:
        """Validate pregnancy status."""
        if pregnancy is None:
            return True
        valid_values = {"si", "no", "sí", "desconoce", "desconozco"}
        return pregnancy.lower() in valid_values

    @staticmethod
    def validate_trauma(trauma: Optional[str]) -> bool:
        """Validate trauma field."""
        if trauma is None:
            return True
        if len(trauma) < 2 or len(trauma) > 300:
            return False
        return True

    @staticmethod
    def validate_justification(justification: Optional[str]) -> bool:
        """Validate justification field."""
        if justification is None:
            return True
        if len(justification) < 2 or len(justification) > 300:
            return False
        return True


class VitalSignsValidator:
    """Validators for vital signs with medical ranges."""

    # Medical ranges (conservative)
    VALID_RANGES = {
        "frecuencia_cardiaca": (40, 180),  # bpm
        "temperatura": (35.0, 42.0),  # Celsius
        "saturacion_oxigeno": (70, 100),  # %
        "frecuencia_respiratoria": (8, 40),  # rpm
        "peso": (1.0, 300.0),  # kg
        "talla": (30.0, 250.0),  # cm
        "glucemia": (20, 600),  # mg/dL
        "escala_dolor": (0, 10),  # 0-10
    }

    @staticmethod
    def validate_frecuencia_cardiaca(value: Optional[int]) -> bool:
        """Validate heart rate."""
        if value is None:
            return True
        min_val, max_val = VitalSignsValidator.VALID_RANGES["frecuencia_cardiaca"]
        return min_val <= value <= max_val

    @staticmethod
    def validate_temperatura(value: Optional[float]) -> bool:
        """Validate temperature."""
        if value is None:
            return True
        min_val, max_val = VitalSignsValidator.VALID_RANGES["temperatura"]
        return min_val <= value <= max_val

    @staticmethod
    def validate_presion_arterial(value: Optional[str]) -> bool:
        """Validate blood pressure format and values."""
        if value is None:
            return True
        match = re.match(r"^(\d{2,3})/(\d{2,3})$", str(value).strip())
        if not match:
            return False
        systolic, diastolic = int(match.group(1)), int(match.group(2))
        # Systolic should be > diastolic
        if systolic <= diastolic:
            return False
        # Reasonable ranges
        if not (60 <= systolic <= 250):
            return False
        if not (40 <= diastolic <= 150):
            return False
        return True

    @staticmethod
    def validate_saturacion_oxigeno(value: Optional[int]) -> bool:
        """Validate oxygen saturation."""
        if value is None:
            return True
        min_val, max_val = VitalSignsValidator.VALID_RANGES["saturacion_oxigeno"]
        return min_val <= value <= max_val

    @staticmethod
    def validate_frecuencia_respiratoria(value: Optional[int]) -> bool:
        """Validate respiratory rate."""
        if value is None:
            return True
        min_val, max_val = VitalSignsValidator.VALID_RANGES["frecuencia_respiratoria"]
        return min_val <= value <= max_val

    @staticmethod
    def validate_peso(value: Optional[float]) -> bool:
        """Validate weight."""
        if value is None:
            return True
        min_val, max_val = VitalSignsValidator.VALID_RANGES["peso"]
        return min_val <= value <= max_val

    @staticmethod
    def validate_talla(value: Optional[float]) -> bool:
        """Validate height."""
        if value is None:
            return True
        min_val, max_val = VitalSignsValidator.VALID_RANGES["talla"]
        return min_val <= value <= max_val

    @staticmethod
    def validate_glucemia(value: Optional[int]) -> bool:
        """Validate blood glucose."""
        if value is None:
            return True
        min_val, max_val = VitalSignsValidator.VALID_RANGES["glucemia"]
        return min_val <= value <= max_val

    @classmethod
    def validate_all(cls, vital_signs_dict: dict) -> tuple[bool, Optional[str]]:
        """
        Validate all vital signs at once.
        
        Returns:
            (is_valid, error_message)
        """
        validators = {
            "frecuencia_cardiaca": cls.validate_frecuencia_cardiaca,
            "temperatura": cls.validate_temperatura,
            "presion_arterial": cls.validate_presion_arterial,
            "saturacion_oxigeno": cls.validate_saturacion_oxigeno,
            "frecuencia_respiratoria": cls.validate_frecuencia_respiratoria,
            "peso": cls.validate_peso,
            "talla": cls.validate_talla,
            "glucemia": cls.validate_glucemia,
        }
        
        for field, validator in validators.items():
            value = vital_signs_dict.get(field)
            if not validator(value):
                return False, f"Invalid {field}: {value}"
        
        return True, None


class PatientDataValidator:
    """Validators for patient basic information."""

    @staticmethod
    def validate_cedula(cedula: str) -> bool:
        """Validate cedula format."""
        if not cedula:
            return False
        cleaned = re.sub(r"\D", "", cedula)
        return 6 <= len(cleaned) <= 15

    @staticmethod
    def validate_names(names: str) -> bool:
        """Validate name fields."""
        if not names or len(names) < 2 or len(names) > 100:
            return False
        return True

    @staticmethod
    def validate_fecha_nacimiento(fecha: date) -> bool:
        """Validate date of birth."""
        if not fecha:
            return False
        today = date.today()
        # Age should be between 0 and 150 years
        age = (today - fecha).days / 365.25
        return 0 <= age <= 150

    @staticmethod
    def validate_genero(genero: str) -> bool:
        """Validate gender."""
        valid = {"M", "F", "Otro"}
        return genero in valid

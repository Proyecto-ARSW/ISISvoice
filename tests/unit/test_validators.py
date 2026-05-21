"""Tests for app.validators module."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.validators import TriageDataValidator, VitalSignsValidator, PatientDataValidator


# ─── TriageDataValidator ──────────────────────────────────────────────────────

class TestTriageDataValidatorCedula:
    def test_valid_cedula(self):
        assert TriageDataValidator.validate_cedula("12345678") is True

    def test_none_returns_false(self):
        assert TriageDataValidator.validate_cedula(None) is False

    def test_empty_returns_false(self):
        assert TriageDataValidator.validate_cedula("") is False

    def test_too_short_returns_false(self):
        assert TriageDataValidator.validate_cedula("123") is False

    def test_too_long_returns_false(self):
        assert TriageDataValidator.validate_cedula("1" * 21) is False

    def test_letters_stripped_for_length(self):
        # "CC-12345678" → cleaned = "12345678" → 8 digits → valid
        assert TriageDataValidator.validate_cedula("CC-12345678") is True

    def test_exactly_5_digits_valid(self):
        assert TriageDataValidator.validate_cedula("12345") is True

    def test_exactly_20_digits_valid(self):
        assert TriageDataValidator.validate_cedula("1" * 20) is True


class TestTriageDataValidatorSymptoms:
    def test_none_returns_true(self):
        assert TriageDataValidator.validate_symptoms(None) is True

    def test_empty_returns_true(self):
        assert TriageDataValidator.validate_symptoms("") is True

    def test_too_short_returns_false(self):
        assert TriageDataValidator.validate_symptoms("ab") is False

    def test_too_long_returns_false(self):
        assert TriageDataValidator.validate_symptoms("a" * 501) is False

    def test_valid_symptoms(self):
        assert TriageDataValidator.validate_symptoms("fiebre alta y dolor de cabeza") is True


class TestTriageDataValidatorPregnancy:
    def test_none_returns_true(self):
        assert TriageDataValidator.validate_pregnancy(None) is True

    def test_si_valid(self):
        assert TriageDataValidator.validate_pregnancy("si") is True

    def test_no_valid(self):
        assert TriageDataValidator.validate_pregnancy("no") is True

    def test_sí_with_accent(self):
        assert TriageDataValidator.validate_pregnancy("sí") is True

    def test_desconoce_valid(self):
        assert TriageDataValidator.validate_pregnancy("desconoce") is True

    def test_desconozco_valid(self):
        assert TriageDataValidator.validate_pregnancy("desconozco") is True

    def test_invalid_value(self):
        assert TriageDataValidator.validate_pregnancy("quizas") is False

    def test_uppercase_valid(self):
        assert TriageDataValidator.validate_pregnancy("SI") is True


class TestTriageDataValidatorTrauma:
    def test_none_returns_true(self):
        assert TriageDataValidator.validate_trauma(None) is True

    def test_too_short_returns_false(self):
        assert TriageDataValidator.validate_trauma("a") is False

    def test_too_long_returns_false(self):
        assert TriageDataValidator.validate_trauma("a" * 301) is False

    def test_valid_trauma(self):
        assert TriageDataValidator.validate_trauma("caida de moto") is True


class TestTriageDataValidatorJustification:
    def test_none_returns_true(self):
        assert TriageDataValidator.validate_justification(None) is True

    def test_too_short_returns_false(self):
        assert TriageDataValidator.validate_justification("x") is False

    def test_too_long_returns_false(self):
        assert TriageDataValidator.validate_justification("x" * 301) is False

    def test_valid_justification(self):
        assert TriageDataValidator.validate_justification("accidente laboral") is True


# ─── VitalSignsValidator ──────────────────────────────────────────────────────

class TestVitalSignsValidatorFrecuenciaCardiaca:
    def test_none_returns_true(self):
        assert VitalSignsValidator.validate_frecuencia_cardiaca(None) is True

    def test_valid_normal(self):
        assert VitalSignsValidator.validate_frecuencia_cardiaca(72) is True

    def test_below_min_returns_false(self):
        assert VitalSignsValidator.validate_frecuencia_cardiaca(30) is False

    def test_above_max_returns_false(self):
        assert VitalSignsValidator.validate_frecuencia_cardiaca(200) is False

    def test_at_min_boundary(self):
        assert VitalSignsValidator.validate_frecuencia_cardiaca(40) is True

    def test_at_max_boundary(self):
        assert VitalSignsValidator.validate_frecuencia_cardiaca(180) is True


class TestVitalSignsValidatorTemperatura:
    def test_none_returns_true(self):
        assert VitalSignsValidator.validate_temperatura(None) is True

    def test_valid_febrile(self):
        assert VitalSignsValidator.validate_temperatura(38.5) is True

    def test_below_min_returns_false(self):
        assert VitalSignsValidator.validate_temperatura(34.0) is False

    def test_above_max_returns_false(self):
        assert VitalSignsValidator.validate_temperatura(43.0) is False

    def test_at_boundaries(self):
        assert VitalSignsValidator.validate_temperatura(35.0) is True
        assert VitalSignsValidator.validate_temperatura(42.0) is True


class TestVitalSignsValidatorPresionArterial:
    def test_none_returns_true(self):
        assert VitalSignsValidator.validate_presion_arterial(None) is True

    def test_valid_bp(self):
        assert VitalSignsValidator.validate_presion_arterial("120/80") is True

    def test_invalid_format_no_slash(self):
        assert VitalSignsValidator.validate_presion_arterial("120-80") is False

    def test_systolic_below_diastolic_returns_false(self):
        assert VitalSignsValidator.validate_presion_arterial("70/80") is False

    def test_systolic_out_of_range(self):
        assert VitalSignsValidator.validate_presion_arterial("280/90") is False

    def test_diastolic_out_of_range(self):
        assert VitalSignsValidator.validate_presion_arterial("130/160") is False

    def test_high_bp_valid(self):
        assert VitalSignsValidator.validate_presion_arterial("180/110") is True

    def test_low_systolic_out_of_range(self):
        assert VitalSignsValidator.validate_presion_arterial("50/30") is False


class TestVitalSignsValidatorSaturacionOxigeno:
    def test_none_returns_true(self):
        assert VitalSignsValidator.validate_saturacion_oxigeno(None) is True

    def test_valid_normal(self):
        assert VitalSignsValidator.validate_saturacion_oxigeno(98) is True

    def test_below_min_returns_false(self):
        assert VitalSignsValidator.validate_saturacion_oxigeno(60) is False

    def test_above_max_returns_false(self):
        assert VitalSignsValidator.validate_saturacion_oxigeno(101) is False


class TestVitalSignsValidatorFrecuenciaRespiratoria:
    def test_none_returns_true(self):
        assert VitalSignsValidator.validate_frecuencia_respiratoria(None) is True

    def test_valid(self):
        assert VitalSignsValidator.validate_frecuencia_respiratoria(18) is True

    def test_out_of_range(self):
        assert VitalSignsValidator.validate_frecuencia_respiratoria(50) is False


class TestVitalSignsValidatorPeso:
    def test_none_returns_true(self):
        assert VitalSignsValidator.validate_peso(None) is True

    def test_valid(self):
        assert VitalSignsValidator.validate_peso(70.0) is True

    def test_too_low(self):
        assert VitalSignsValidator.validate_peso(0.5) is False

    def test_too_high(self):
        assert VitalSignsValidator.validate_peso(350.0) is False


class TestVitalSignsValidatorTalla:
    def test_none_returns_true(self):
        assert VitalSignsValidator.validate_talla(None) is True

    def test_valid(self):
        assert VitalSignsValidator.validate_talla(170.0) is True

    def test_too_low(self):
        assert VitalSignsValidator.validate_talla(20.0) is False

    def test_too_high(self):
        assert VitalSignsValidator.validate_talla(300.0) is False


class TestVitalSignsValidatorGlucemia:
    def test_none_returns_true(self):
        assert VitalSignsValidator.validate_glucemia(None) is True

    def test_valid(self):
        assert VitalSignsValidator.validate_glucemia(100) is True

    def test_too_low(self):
        assert VitalSignsValidator.validate_glucemia(10) is False

    def test_too_high(self):
        assert VitalSignsValidator.validate_glucemia(700) is False


class TestVitalSignsValidatorAll:
    def test_all_valid(self):
        valid, err = VitalSignsValidator.validate_all({
            "frecuencia_cardiaca": 72,
            "temperatura": 37.0,
            "saturacion_oxigeno": 98,
        })
        assert valid is True
        assert err is None

    def test_invalid_field_returns_false_with_message(self):
        valid, err = VitalSignsValidator.validate_all({
            "frecuencia_cardiaca": 300,
        })
        assert valid is False
        assert "frecuencia_cardiaca" in err

    def test_empty_dict_returns_true(self):
        valid, err = VitalSignsValidator.validate_all({})
        assert valid is True
        assert err is None

    def test_none_values_are_valid(self):
        valid, err = VitalSignsValidator.validate_all({
            "temperatura": None,
            "presion_arterial": None,
        })
        assert valid is True


# ─── PatientDataValidator ─────────────────────────────────────────────────────

class TestPatientDataValidatorCedula:
    def test_valid_cedula(self):
        assert PatientDataValidator.validate_cedula("12345678") is True

    def test_empty_returns_false(self):
        assert PatientDataValidator.validate_cedula("") is False

    def test_too_short_returns_false(self):
        assert PatientDataValidator.validate_cedula("12345") is False

    def test_too_long_returns_false(self):
        assert PatientDataValidator.validate_cedula("1" * 16) is False

    def test_exactly_6_digits(self):
        assert PatientDataValidator.validate_cedula("123456") is True

    def test_exactly_15_digits(self):
        assert PatientDataValidator.validate_cedula("1" * 15) is True


class TestPatientDataValidatorNames:
    def test_valid_name(self):
        assert PatientDataValidator.validate_names("Juan Perez") is True

    def test_empty_returns_false(self):
        assert PatientDataValidator.validate_names("") is False

    def test_too_short(self):
        assert PatientDataValidator.validate_names("A") is False

    def test_too_long(self):
        assert PatientDataValidator.validate_names("A" * 101) is False

    def test_exactly_2_chars(self):
        assert PatientDataValidator.validate_names("Li") is True


class TestPatientDataValidatorFechaNacimiento:
    def test_valid_adult_dob(self):
        dob = date.today() - timedelta(days=365 * 30)
        assert PatientDataValidator.validate_fecha_nacimiento(dob) is True

    def test_future_date_returns_false(self):
        future = date.today() + timedelta(days=1)
        assert PatientDataValidator.validate_fecha_nacimiento(future) is False

    def test_too_old_returns_false(self):
        ancient = date.today() - timedelta(days=365 * 200)
        assert PatientDataValidator.validate_fecha_nacimiento(ancient) is False

    def test_today_valid(self):
        assert PatientDataValidator.validate_fecha_nacimiento(date.today()) is True


class TestPatientDataValidatorGenero:
    def test_male(self):
        assert PatientDataValidator.validate_genero("M") is True

    def test_female(self):
        assert PatientDataValidator.validate_genero("F") is True

    def test_otro(self):
        assert PatientDataValidator.validate_genero("Otro") is True

    def test_invalid(self):
        assert PatientDataValidator.validate_genero("X") is False

    def test_lowercase_invalid(self):
        assert PatientDataValidator.validate_genero("m") is False

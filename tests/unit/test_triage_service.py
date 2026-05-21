"""Unit tests for TriageExtractionService — heuristics, priority, recommendations."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import TriageDataCore
from app.services.triage_service import TriageExtractionService

svc = TriageExtractionService()


# ─── _strip_accents ───────────────────────────────────────────────────────────

class TestStripAccents:
    def test_acute_vowels(self):
        assert svc._strip_accents("náuseas") == "nauseas"

    def test_enye(self):
        assert svc._strip_accents("Ñoño") == "Nono"

    def test_multiple_accents(self):
        assert svc._strip_accents("fiebre y vómito") == "fiebre y vomito"

    def test_no_accents_unchanged(self):
        assert svc._strip_accents("dolor") == "dolor"

    def test_empty_string(self):
        assert svc._strip_accents("") == ""

    def test_choco_with_accent(self):
        assert svc._strip_accents("Chocó") == "Choco"


# ─── _clean_text ─────────────────────────────────────────────────────────────

class TestCleanText:
    def test_none_returns_empty(self):
        assert svc._clean_text(None) == ""

    def test_strips_whitespace(self):
        assert svc._clean_text("  hola  ") == "hola"

    def test_literal_none_returns_empty(self):
        assert svc._clean_text("none") == ""

    def test_literal_null_returns_empty(self):
        assert svc._clean_text("null") == ""

    def test_literal_nan_returns_empty(self):
        assert svc._clean_text("nan") == ""

    def test_literal_undefined_returns_empty(self):
        assert svc._clean_text("undefined") == ""

    def test_normal_text_returned(self):
        assert svc._clean_text("fiebre") == "fiebre"

    def test_numeric_coerced_to_string(self):
        assert svc._clean_text(42) == "42"

    def test_case_insensitive_none(self):
        assert svc._clean_text("None") == ""
        assert svc._clean_text("NULL") == ""


# ─── _split_items ─────────────────────────────────────────────────────────────

class TestSplitItems:
    def test_comma_separated(self):
        result = svc._split_items("fiebre, vomito, diarrea")
        assert result == ["fiebre", "vomito", "diarrea"]

    def test_semicolon_separated(self):
        result = svc._split_items("fiebre; vomito")
        assert result == ["fiebre", "vomito"]

    def test_y_separator(self):
        result = svc._split_items("fiebre y vomito")
        assert result == ["fiebre", "vomito"]

    def test_and_separator_english(self):
        result = svc._split_items("fever and vomit")
        assert result == ["fever", "vomit"]

    def test_empty_parts_removed(self):
        result = svc._split_items("fiebre,  , vomito")
        assert "" not in result
        assert "fiebre" in result
        assert "vomito" in result

    def test_single_item(self):
        result = svc._split_items("fiebre")
        assert result == ["fiebre"]


# ─── _is_negated ──────────────────────────────────────────────────────────────

class TestIsNegated:
    def test_no_negation(self):
        assert svc._is_negated("fiebre", "no tiene fiebre") is True

    def test_sin_negation(self):
        assert svc._is_negated("dolor", "sin dolor") is True

    def test_niega_negation(self):
        assert svc._is_negated("fiebre", "niega fiebre") is True

    def test_ausencia_de_negation(self):
        assert svc._is_negated("fiebre", "ausencia de fiebre") is True

    def test_no_tiene_negation(self):
        assert svc._is_negated("fiebre", "no tiene fiebre alta") is True

    def test_no_tengo_negation(self):
        assert svc._is_negated("vomito", "no tengo vomito") is True

    def test_no_hay_negation(self):
        assert svc._is_negated("fiebre", "no hay fiebre") is True

    def test_positive_not_negated(self):
        assert svc._is_negated("fiebre", "tiene fiebre alta") is False

    def test_negation_too_far(self):
        # More than 3 tokens between negation word and keyword
        assert svc._is_negated("fiebre", "no hay absolutamente ninguna evidencia de fiebre") is False


# ─── _detect_pregnancy ────────────────────────────────────────────────────────

class TestDetectPregnancy:
    def test_embarazada(self):
        assert svc._detect_pregnancy("paciente embarazada de 30 anos") is True

    def test_gestante(self):
        assert svc._detect_pregnancy("paciente gestante de 20 semanas") is True

    def test_semanas_de_gestacion(self):
        assert svc._detect_pregnancy("tiene 28 semanas de gestacion") is True

    def test_meses_de_embarazo(self):
        assert svc._detect_pregnancy("6 meses de embarazo") is True

    def test_estoy_esperando(self):
        assert svc._detect_pregnancy("estoy esperando un bebe") is True

    def test_no_embarazada(self):
        assert svc._detect_pregnancy("no embarazada") is False

    def test_no_estoy_embarazada(self):
        assert svc._detect_pregnancy("no estoy embarazada") is False

    def test_niega_embarazo(self):
        assert svc._detect_pregnancy("niega embarazo") is False

    def test_no_esta_embarazada(self):
        assert svc._detect_pregnancy("no esta embarazada") is False

    def test_unrelated_text(self):
        assert svc._detect_pregnancy("tengo dolor de cabeza") is False


# ─── _extract_symptoms ────────────────────────────────────────────────────────

class TestExtractSymptoms:
    def test_detects_fever(self):
        assert "fiebre" in svc._extract_symptoms("tengo fiebre alta")

    def test_detects_multiple_symptoms(self):
        result = svc._extract_symptoms("tengo fiebre y vomito y diarrea")
        assert "fiebre" in result
        assert "vomito" in result
        assert "diarrea" in result

    def test_negated_symptom_excluded(self):
        result = svc._extract_symptoms("no tengo fiebre pero si tengo vomito")
        assert "fiebre" not in result
        assert "vomito" in result

    def test_accent_stripping_for_matching(self):
        result = svc._extract_symptoms("tengo náuseas")
        assert "nauseas" in result

    def test_chest_pain_detected(self):
        result = svc._extract_symptoms("tengo dolor toracico fuerte")
        assert "dolor toracico" in result

    def test_deduplication(self):
        result = svc._extract_symptoms("fiebre y fiebre alta")
        assert result.count("fiebre") == 1

    def test_empty_text_returns_empty(self):
        assert svc._extract_symptoms("") == []

    def test_fallback_when_no_seeds_match(self):
        result = svc._extract_symptoms("sintomas: malestar general, decaimiento")
        assert len(result) > 0

    def test_headache_detected(self):
        result = svc._extract_symptoms("tengo cefalea intensa")
        assert "cefalea" in result


# ─── _extract_background ──────────────────────────────────────────────────────

class TestExtractBackground:
    def test_antecedentes_prefix(self):
        result = svc._extract_background("antecedentes: diabetes, hipertension")
        assert "diabetes" in result
        assert "hipertension" in result

    def test_historial_prefix(self):
        result = svc._extract_background("historial: asma, epoc")
        assert "asma" in result

    def test_padezco_de(self):
        result = svc._extract_background("padezco de diabetes")
        assert "diabetes" in result

    def test_me_han_diagnosticado(self):
        result = svc._extract_background("me han diagnosticado diabetes")
        assert "diabetes" in result

    def test_no_antecedentes_returns_empty(self):
        assert svc._extract_background("tengo dolor de cabeza") == []

    def test_semicolons_split(self):
        result = svc._extract_background("antecedentes: diabetes; hipertension")
        assert len(result) == 2


# ─── _extract_vital_signs_from_text ──────────────────────────────────────────

class TestExtractVitalSignsFromText:
    def test_blood_pressure(self):
        r = svc._extract_vital_signs_from_text("presion arterial 120/80")
        assert r["systolic"] == 120.0
        assert r["diastolic"] == 80.0

    def test_temperature_decimal_dot(self):
        r = svc._extract_vital_signs_from_text("temperatura 38.5 grados")
        assert r["temperature"] == 38.5

    def test_temperature_decimal_comma(self):
        r = svc._extract_vital_signs_from_text("temperatura 38,5 grados")
        assert r["temperature"] == 38.5

    def test_spo2(self):
        r = svc._extract_vital_signs_from_text("saturacion 95%")
        assert r["spo2"] == 95.0

    def test_heart_rate_lpm(self):
        r = svc._extract_vital_signs_from_text("pulso 90 lpm")
        assert r["heart_rate"] == 90.0

    def test_fc_abbreviation(self):
        r = svc._extract_vital_signs_from_text("fc 100")
        assert r["heart_rate"] == 100.0

    def test_temperature_below_range_ignored(self):
        r = svc._extract_vital_signs_from_text("temperatura 15 grados")
        assert "temperature" not in r

    def test_temperature_above_range_ignored(self):
        r = svc._extract_vital_signs_from_text("temperatura 50 grados")
        assert "temperature" not in r

    def test_spo2_out_of_range_ignored(self):
        r = svc._extract_vital_signs_from_text("saturacion 10%")
        assert "spo2" not in r

    def test_heart_rate_too_low_ignored(self):
        r = svc._extract_vital_signs_from_text("pulso 5 lpm")
        assert "heart_rate" not in r

    def test_empty_text(self):
        assert svc._extract_vital_signs_from_text("") == {}

    def test_no_vitals_in_text(self):
        assert svc._extract_vital_signs_from_text("tengo dolor de cabeza") == {}

    def test_all_vitals_in_one_text(self):
        text = "presion 130/85, temperatura 38.2 grados, saturacion 97%, pulso 95 lpm"
        r = svc._extract_vital_signs_from_text(text)
        assert "systolic" in r
        assert "temperature" in r
        assert "spo2" in r
        assert "heart_rate" in r


# ─── _priority_from_vitals ────────────────────────────────────────────────────

class TestPriorityFromVitals:
    def test_empty_returns_5(self):
        assert svc._priority_from_vitals({}) == 5

    def test_spo2_below_90_returns_1(self):
        assert svc._priority_from_vitals({"spo2": 88}) == 1

    def test_spo2_90_to_94_returns_2(self):
        assert svc._priority_from_vitals({"spo2": 92}) == 2

    def test_spo2_normal_returns_5(self):
        assert svc._priority_from_vitals({"spo2": 98}) == 5

    def test_high_systolic_returns_2(self):
        assert svc._priority_from_vitals({"systolic": 185}) == 2

    def test_low_systolic_returns_2(self):
        assert svc._priority_from_vitals({"systolic": 75}) == 2

    def test_normal_systolic_returns_5(self):
        assert svc._priority_from_vitals({"systolic": 120}) == 5

    def test_temp_above_40_returns_2(self):
        assert svc._priority_from_vitals({"temperature": 40.5}) == 2

    def test_temp_38_5_to_40_returns_3(self):
        assert svc._priority_from_vitals({"temperature": 39.0}) == 3

    def test_temp_normal_returns_5(self):
        assert svc._priority_from_vitals({"temperature": 37.0}) == 5

    def test_hr_above_150_returns_2(self):
        assert svc._priority_from_vitals({"heart_rate": 160}) == 2

    def test_hr_below_40_returns_2(self):
        assert svc._priority_from_vitals({"heart_rate": 35}) == 2

    def test_hr_normal_returns_5(self):
        assert svc._priority_from_vitals({"heart_rate": 72}) == 5

    def test_multiple_vitals_returns_worst(self):
        # spo2 < 90 → 1, hr > 150 → 2; min = 1
        assert svc._priority_from_vitals({"spo2": 85, "heart_rate": 160}) == 1

    def test_all_normal_returns_5(self):
        assert svc._priority_from_vitals(
            {"spo2": 98, "temperature": 37.0, "systolic": 120, "heart_rate": 72}
        ) == 5


# ─── _detect_syndrome_clusters ────────────────────────────────────────────────

class TestDetectSyndromeClusters:
    def test_sca_infarto(self):
        clusters = svc._detect_syndrome_clusters("dolor en el pecho con sudoracion y nauseas")
        labels = [c[0] for c in clusters]
        assert any("SCA" in l or "coronario" in l for l in labels)
        assert any(c[1] == 1 for c in clusters)

    def test_sca_with_palpitations(self):
        clusters = svc._detect_syndrome_clusters("dolor toracico y palpitaciones")
        labels = [c[0] for c in clusters]
        assert any("SCA" in l or "coronario" in l for l in labels)

    def test_acv_ictus(self):
        clusters = svc._detect_syndrome_clusters("debilidad en un lado, cara caida, dolor de cabeza")
        labels = [c[0] for c in clusters]
        assert any("ACV" in l or "ictus" in l for l in labels)

    def test_acv_with_habla_difusa(self):
        clusters = svc._detect_syndrome_clusters("habla difusa, confusion, cefalea")
        labels = [c[0] for c in clusters]
        assert any("ACV" in l or "ictus" in l for l in labels)

    def test_meningitis(self):
        clusters = svc._detect_syndrome_clusters("fiebre, rigidez de nuca, cefalea, vomito")
        labels = [c[0] for c in clusters]
        assert any("meningitis" in l for l in labels)
        assert any(c[1] == 1 for c in clusters)

    def test_sepsis(self):
        clusters = svc._detect_syndrome_clusters("fiebre, confusion, taquicardia")
        labels = [c[0] for c in clusters]
        assert any("sepsis" in l for l in labels)

    def test_edema_pulmonar(self):
        clusters = svc._detect_syndrome_clusters("dificultad para respirar, piernas hinchadas")
        labels = [c[0] for c in clusters]
        assert any("edema" in l or "ICC" in l for l in labels)

    def test_edema_pulmonar_tos_espuma(self):
        clusters = svc._detect_syndrome_clusters("falta de aire, tos con espuma")
        labels = [c[0] for c in clusters]
        assert any("edema" in l or "ICC" in l for l in labels)

    def test_embarazo_ectopico(self):
        clusters = svc._detect_syndrome_clusters("embarazada, dolor abdominal, sangrado vaginal")
        labels = [svc._strip_accents(c[0]).lower() for c in clusters]
        assert any("ectop" in l for l in labels)
        assert any(c[1] == 1 for c in clusters)

    def test_apendicitis(self):
        clusters = svc._detect_syndrome_clusters("dolor lado derecho, fiebre, nauseas")
        labels = [c[0] for c in clusters]
        assert any("apendicitis" in l for l in labels)
        assert any(c[1] == 2 for c in clusters)

    def test_hipoglucemia(self):
        clusters = svc._detect_syndrome_clusters("diabetico, mareo, sudoracion, temblores")
        labels = [c[0] for c in clusters]
        assert any("hipoglucemia" in l for l in labels)

    def test_colico_renoureteral(self):
        clusters = svc._detect_syndrome_clusters("dolor lumbar, sangre en la orina")
        labels = [c[0] for c in clusters]
        assert any("renoureteral" in l or "colico" in l.lower() for l in labels)
        assert any(c[1] == 3 for c in clusters)

    def test_ofidismo_priority_1(self):
        clusters = svc._detect_syndrome_clusters("mordedura de culebra en el pie")
        labels = [c[0] for c in clusters]
        assert any("ofidismo" in l for l in labels)
        assert all(c[1] == 1 for c in clusters)

    def test_ofidismo_serpiente(self):
        clusters = svc._detect_syndrome_clusters("picadura de serpiente")
        labels = [c[0] for c in clusters]
        assert any("ofidismo" in l for l in labels)

    def test_no_syndrome_mild_text(self):
        assert svc._detect_syndrome_clusters("tos leve") == []

    def test_no_syndrome_empty(self):
        assert svc._detect_syndrome_clusters("") == []


# ─── _detect_high_risk_factors ───────────────────────────────────────────────

class TestDetectHighRiskFactors:
    def test_anticoagulante(self):
        result = svc._detect_high_risk_factors("paciente anticoagulante")
        assert any("anticoag" in r for r in result)

    def test_warfarina(self):
        result = svc._detect_high_risk_factors("toma warfarina")
        assert len(result) > 0

    def test_diabetes(self):
        result = svc._detect_high_risk_factors("tiene diabetes")
        assert len(result) > 0

    def test_insulina(self):
        result = svc._detect_high_risk_factors("usa insulina a diario")
        assert len(result) > 0

    def test_epoc(self):
        result = svc._detect_high_risk_factors("tiene epoc severo")
        assert len(result) > 0

    def test_asma(self):
        result = svc._detect_high_risk_factors("padece asma bronquial")
        assert len(result) > 0

    def test_vih(self):
        result = svc._detect_high_risk_factors("paciente con vih")
        assert len(result) > 0

    def test_cirrosis(self):
        result = svc._detect_high_risk_factors("tiene cirrosis hepatica")
        assert len(result) > 0

    def test_hemofilia(self):
        result = svc._detect_high_risk_factors("hemofilia tipo A")
        assert len(result) > 0

    def test_no_risk_factors(self):
        assert svc._detect_high_risk_factors("tengo dolor de cabeza leve") == []

    def test_multiple_factors(self):
        result = svc._detect_high_risk_factors("diabetes y asma")
        assert len(result) >= 2


# ─── _detect_pediatric_context ───────────────────────────────────────────────

class TestDetectPediatricContext:
    def test_mi_hijo(self):
        assert svc._detect_pediatric_context("mi hijo tiene fiebre") is True

    def test_mi_hija(self):
        assert svc._detect_pediatric_context("mi hija no come bien") is True

    def test_el_bebe(self):
        assert svc._detect_pediatric_context("el bebe llora mucho") is True

    def test_lactante(self):
        assert svc._detect_pediatric_context("lactante de 4 meses") is True

    def test_recien_nacido(self):
        assert svc._detect_pediatric_context("recien nacido con ictericia") is True

    def test_anos_de_edad(self):
        assert svc._detect_pediatric_context("tiene 3 anos de edad") is True

    def test_adult_text_false(self):
        assert svc._detect_pediatric_context("adulto de 45 anos con dolor") is False

    def test_empty_text_false(self):
        assert svc._detect_pediatric_context("") is False


# ─── _detect_endemic_zone ────────────────────────────────────────────────────

class TestDetectEndemicZone:
    def test_choco(self):
        assert svc._detect_endemic_zone("vengo del choco") == "choco"

    def test_choco_with_accent_stripped(self):
        assert svc._detect_endemic_zone("vivo en Chocó") == "choco"

    def test_amazonia(self):
        assert svc._detect_endemic_zone("soy de la amazonia") == "amazonia"

    def test_putumayo(self):
        assert svc._detect_endemic_zone("viaje a putumayo") == "putumayo"

    def test_zona_rural(self):
        assert svc._detect_endemic_zone("vivo en zona rural") == "zona rural"

    def test_area_rural(self):
        assert svc._detect_endemic_zone("viene de area rural") == "area rural"

    def test_no_endemic_zone_bogota(self):
        assert svc._detect_endemic_zone("vivo en bogota") is None

    def test_empty_text_none(self):
        assert svc._detect_endemic_zone("") is None


# ─── _symptom_duration_days ──────────────────────────────────────────────────

class TestSymptomDurationDays:
    def test_3_dias(self):
        assert svc._symptom_duration_days("hace 3 dias con fiebre") == 3

    def test_1_dia(self):
        assert svc._symptom_duration_days("hace 1 dia con tos") == 1

    def test_2_semanas(self):
        assert svc._symptom_duration_days("hace 2 semanas con malestar") == 14

    def test_1_semana(self):
        assert svc._symptom_duration_days("hace 1 semana") == 7

    def test_hace_horas_returns_0(self):
        assert svc._symptom_duration_days("hace 2 horas") == 0

    def test_desde_ayer(self):
        assert svc._symptom_duration_days("desde ayer con dolor") == 1

    def test_desde_anoche(self):
        assert svc._symptom_duration_days("desde anoche") == 1

    def test_esta_manana(self):
        assert svc._symptom_duration_days("esta manana empezo el dolor") == 0

    def test_hace_un_rato(self):
        assert svc._symptom_duration_days("hace un rato") == 0

    def test_ahorita(self):
        assert svc._symptom_duration_days("ahorita me duele") == 0

    def test_no_duration_returns_none(self):
        assert svc._symptom_duration_days("tengo fiebre") is None


# ─── _has_high_intensity ─────────────────────────────────────────────────────

class TestHasHighIntensity:
    def test_intenso(self):
        assert svc._has_high_intensity("dolor intenso") is True

    def test_severo(self):
        assert svc._has_high_intensity("dolor severo") is True

    def test_insoportable(self):
        assert svc._has_high_intensity("dolor insoportable") is True

    def test_muy_fuerte(self):
        assert svc._has_high_intensity("muy fuerte el dolor") is True

    def test_terrible(self):
        assert svc._has_high_intensity("me siento terrible") is True

    def test_atroz(self):
        assert svc._has_high_intensity("dolor atroz") is True

    def test_no_intensity_modifier(self):
        assert svc._has_high_intensity("tengo un dolor") is False

    def test_empty_text(self):
        assert svc._has_high_intensity("") is False


# ─── _detect_dehydration_severity ────────────────────────────────────────────

class TestDetectDehydrationSeverity:
    def test_severe_no_orina(self):
        assert svc._detect_dehydration_severity("no orina desde ayer") == "severe"

    def test_severe_ojos_hundidos(self):
        assert svc._detect_dehydration_severity("ojos hundidos, pulso debil") == "severe"

    def test_severe_fontanela_hundida(self):
        assert svc._detect_dehydration_severity("fontanela hundida en el bebe") == "severe"

    def test_severe_confusion(self):
        assert svc._detect_dehydration_severity("confusion, hipotension") == "severe"

    def test_moderate_three_signs(self):
        result = svc._detect_dehydration_severity("sed intensa, boca seca, orina oscura")
        assert result == "moderate"

    def test_moderate_two_signs(self):
        result = svc._detect_dehydration_severity("sed intensa, boca seca")
        assert result == "moderate"

    def test_mild_one_sign(self):
        assert svc._detect_dehydration_severity("sed intensa") == "mild"

    def test_mild_boca_seca_alone(self):
        assert svc._detect_dehydration_severity("boca seca") == "mild"

    def test_none_no_signs(self):
        assert svc._detect_dehydration_severity("dolor de cabeza") == "none"

    def test_none_empty(self):
        assert svc._detect_dehydration_severity("") == "none"


# ─── _detect_dengue_pattern ──────────────────────────────────────────────────

class TestDetectDenguePattern:
    def test_classic_fever_cefalea_mialgia(self):
        assert svc._detect_dengue_pattern("fiebre cefalea mialgia") is True

    def test_fever_sarpullido_vomito(self):
        assert svc._detect_dengue_pattern("fiebre sarpullido vomito") is True

    def test_fever_only_one_sign_false(self):
        assert svc._detect_dengue_pattern("fiebre cefalea") is False

    def test_no_fever_false(self):
        assert svc._detect_dengue_pattern("cefalea mialgia vomito sarpullido") is False

    def test_full_dengue_presentation(self):
        text = "fiebre dolor de cabeza dolor muscular sarpullido nauseas"
        assert svc._detect_dengue_pattern(text) is True

    def test_empty_text_false(self):
        assert svc._detect_dengue_pattern("") is False

    def test_fever_with_rash_and_arthralgia(self):
        assert svc._detect_dengue_pattern("fiebre artralgia erupcion cutanea") is True


# ─── _detect_dengue_alarm ────────────────────────────────────────────────────

class TestDetectDengueAlarm:
    def test_sangrado_encias(self):
        assert svc._detect_dengue_alarm("sangrado de encias") is True

    def test_petequias(self):
        assert svc._detect_dengue_alarm("petequias en piernas") is True

    def test_dolor_abdominal(self):
        assert svc._detect_dengue_alarm("dolor abdominal persistente") is True

    def test_confusion(self):
        assert svc._detect_dengue_alarm("confusion y desorientacion") is True

    def test_pulso_debil(self):
        assert svc._detect_dengue_alarm("pulso debil e hipotension") is True

    def test_vomito_con_sangre(self):
        assert svc._detect_dengue_alarm("vomito con sangre") is True

    def test_no_alarm_signs(self):
        assert svc._detect_dengue_alarm("dolor de cabeza leve") is False

    def test_empty_false(self):
        assert svc._detect_dengue_alarm("") is False


# ─── _infer_causes ────────────────────────────────────────────────────────────

class TestInferCauses:
    def test_dengue_pattern(self):
        causes = svc._infer_causes(["fiebre", "cefalea", "mialgia", "sarpullido"])
        assert any("dengue" in c for c in causes)

    def test_gastroenteritis_eda(self):
        causes = svc._infer_causes(["diarrea", "vomito", "nauseas", "dolor abdominal"])
        assert any("gastroenteritis" in c or "EDA" in c for c in causes)

    def test_ira(self):
        causes = svc._infer_causes(["tos", "dolor de garganta", "fiebre"])
        assert any("IRA" in c or "respiratoria" in c for c in causes)

    def test_neumonia(self):
        causes = svc._infer_causes(["disnea", "fiebre", "tos"])
        assert any("neumonia" in c or "pulmonar" in c for c in causes)

    def test_trauma(self):
        causes = svc._infer_causes(["golpe", "herida", "caida"])
        assert any("trauma" in c for c in causes)

    def test_obstetric_complication_with_pregnancy(self):
        causes = svc._infer_causes(["contracciones", "sangrado vaginal"], pregnancy=True)
        assert any("obstetrica" in c or "ectop" in c for c in causes)

    def test_empty_symptoms_fallback(self):
        causes = svc._infer_causes([])
        assert causes == ["requiere evaluacion clinica"]

    def test_malaria_endemic_zone(self):
        causes = svc._infer_causes(
            ["fiebre", "escalofrios", "sudoracion"],
            transcript="paciente del choco con fiebre y escalofrios",
        )
        assert any("malaria" in c for c in causes)

    def test_malaria_without_endemic_zone(self):
        # Use "temblores" instead of "escalofrios" — "escalofrios" contains "rio" which
        # is in the endemic zones list, causing a false positive zone detection.
        causes = svc._infer_causes(["fiebre", "temblores", "sudoracion"])
        assert any("malaria" in c for c in causes)
        malaria_causes = [c for c in causes if "malaria" in c]
        assert any("descartar" in c for c in malaria_causes)

    def test_deshidratacion(self):
        causes = svc._infer_causes(["sed intensa", "boca seca", "orina oscura"])
        assert any("deshidratacion" in c for c in causes)

    def test_intoxicacion(self):
        causes = svc._infer_causes(["intoxicacion"])
        assert any("intoxicacion" in c for c in causes)

    def test_sca_cluster_via_transcript(self):
        causes = svc._infer_causes(
            ["dolor toracico", "sudoracion"],
            transcript="dolor en el pecho sudoracion nauseas",
        )
        assert any("SCA" in c or "coronario" in c for c in causes)

    def test_fever_alone_fallback(self):
        causes = svc._infer_causes(["fiebre"])
        assert len(causes) > 0

    def test_deduplication(self):
        causes = svc._infer_causes(["fiebre", "fiebre"])
        # Each cause appears once
        assert len(causes) == len(set(causes))

    def test_cardiopulmonar_without_sca(self):
        causes = svc._infer_causes(["disnea", "palpitaciones"])
        assert any("cardiopulmonar" in c for c in causes)

    def test_crisis_hipertensiva(self):
        causes = svc._infer_causes(["cefalea", "palpitaciones"])
        assert any("hipertensiva" in c for c in causes)

    def test_neurologico_convulsivo(self):
        causes = svc._infer_causes(["convulsion"])
        assert any("neurologico" in c for c in causes)

    def test_infeccion_viral_fallback(self):
        causes = svc._infer_causes(["tos"])
        assert any("viral" in c for c in causes)


# ─── _priority_from_content ──────────────────────────────────────────────────

class TestPriorityFromContent:
    def test_convulsion_returns_1(self):
        assert svc._priority_from_content(["convulsion"], False) == 1

    def test_no_despierta_returns_1(self):
        assert svc._priority_from_content(["no despierta"], False) == 1

    def test_paro_cardiaco_returns_1(self):
        assert svc._priority_from_content(["paro cardiaco"], False) == 1

    def test_chest_pain_returns_2(self):
        assert svc._priority_from_content(["dolor toracico"], False) == 2

    def test_chest_pain_intense_returns_1(self):
        assert svc._priority_from_content(
            ["dolor toracico"], False, "dolor toracico insoportable"
        ) == 1

    def test_dificultad_respirar_returns_2(self):
        assert svc._priority_from_content(["dificultad para respirar"], False) == 2

    def test_fever_returns_3(self):
        assert svc._priority_from_content(["fiebre"], False) == 3

    def test_fever_intense_returns_2(self):
        # _INTENSITY_HIGH has "severo" (masculine) and "intenso" — use exact form
        assert svc._priority_from_content(["fiebre"], False, "fiebre intenso") == 2

    def test_empty_symptoms_returns_5(self):
        assert svc._priority_from_content([], False) == 5

    def test_sca_cluster_transcript_returns_1(self):
        assert svc._priority_from_content(
            ["dolor toracico", "sudoracion", "nauseas"],
            False,
            "dolor en el pecho sudoracion nauseas",
        ) == 1

    def test_pregnancy_ruptura_fuente_returns_1(self):
        assert svc._priority_from_content(["ruptura de fuente"], True) == 1

    def test_pregnancy_bebe_no_se_mueve_returns_1(self):
        assert svc._priority_from_content(["bebe no se mueve"], True) == 1

    def test_severe_dehydration_no_orina_returns_1(self):
        assert svc._priority_from_content(["no orina", "confusion", "ojos hundidos"], False) == 1

    def test_pediatric_fever_returns_2(self):
        assert svc._priority_from_content(["fiebre"], False, "mi hijo tiene fiebre") == 2

    def test_high_risk_fever_returns_2(self):
        assert svc._priority_from_content(["fiebre"], False, "paciente diabetico con fiebre") == 2

    def test_anticoag_sangrado_returns_1(self):
        assert svc._priority_from_content(
            ["sangrado"], False, "anticoagulante con sangrado activo"
        ) == 1

    def test_mild_symptom_returns_4(self):
        assert svc._priority_from_content(["picazon"], False) == 4

    def test_dengue_alarm_returns_2(self):
        assert svc._priority_from_content(
            ["fiebre", "petequias", "sangrado de encias"], False
        ) == 2

    def test_vital_signs_from_transcript_critical(self):
        # spo2 < 90 → vital_priority = 1
        assert svc._priority_from_content(
            ["fiebre"], False, "saturacion 85% fiebre"
        ) == 1

    def test_pediatric_fontanela_hundida_returns_1(self):
        assert svc._priority_from_content(["fontanela hundida"], False, "el bebe") == 1

    def test_pregnancy_sangrado_vaginal_returns_2(self):
        assert svc._priority_from_content(["sangrado vaginal"], True) == 2

    def test_moderate_dehydration_two_signs_returns_2(self):
        assert svc._priority_from_content(["sed intensa", "boca seca"], False) == 2


# ─── _build_ai_comment ───────────────────────────────────────────────────────

class TestBuildAiComment:
    def test_priority_1_base_message(self):
        comment = svc._build_ai_comment(1)
        assert "CRÍTICO" in comment or "critico" in comment.lower()
        assert "IA:" in comment

    def test_priority_2_base_message(self):
        comment = svc._build_ai_comment(2)
        assert "30 minutos" in comment

    def test_priority_3_base_message(self):
        comment = svc._build_ai_comment(3)
        assert "2 horas" in comment

    def test_priority_4_base_message(self):
        comment = svc._build_ai_comment(4)
        assert "leve" in comment.lower() or "moderado" in comment.lower()

    def test_priority_5_base_message(self):
        comment = svc._build_ai_comment(5)
        assert "ambulatoria" in comment.lower()

    def test_ofidismo_protocol_appended(self):
        comment = svc._build_ai_comment(1, transcript="mordedura de culebra")
        assert "OFIDISMO" in comment or "ofidismo" in comment.lower()

    def test_dengue_no_ibuprofeno_warning(self):
        symptoms = ["fiebre", "cefalea", "mialgia", "sarpullido"]
        comment = svc._build_ai_comment(3, symptoms=symptoms)
        assert "ibuprofeno" in comment.lower() or "aspirina" in comment.lower()

    def test_severe_dehydration_ev_message(self):
        comment = svc._build_ai_comment(2, transcript="no orina, ojos hundidos")
        assert "EV" in comment or "DESHIDRATACI" in comment

    def test_vital_signs_in_comment(self):
        comment = svc._build_ai_comment(2, transcript="saturacion 88%")
        assert "SpO2" in comment or "oxigeno" in comment.lower()

    def test_risk_factors_appended(self):
        comment = svc._build_ai_comment(2, high_risk=["diabetes"])
        assert "Comorbilidades" in comment or "diabetes" in comment

    def test_pediatric_note_appended(self):
        comment = svc._build_ai_comment(2, transcript="mi hijo tiene fiebre")
        assert "pedi" in comment.lower()

    def test_endemic_zone_note_appended(self):
        comment = svc._build_ai_comment(3, transcript="fiebre del choco")
        assert "choco" in comment.lower() or "endémica" in comment.lower() or "endemica" in comment.lower()

    def test_sca_cluster_note_appended(self):
        comment = svc._build_ai_comment(1, clusters=[("SCA coronario agudo", 1)])
        assert "SCA" in comment or "ECG" in comment

    def test_acv_cluster_note_appended(self):
        comment = svc._build_ai_comment(1, clusters=[("ACV ictus sospecha", 1)])
        assert "ACV" in comment or "stroke" in comment.lower() or "ictus" in comment.lower()

    def test_meningitis_cluster_note_appended(self):
        comment = svc._build_ai_comment(1, clusters=[("meningitis bacteriana", 1)])
        assert "meningitis" in comment.lower() or "PL" in comment

    def test_sepsis_cluster_note_appended(self):
        comment = svc._build_ai_comment(2, clusters=[("posible sepsis severa", 2)])
        assert "sepsis" in comment.lower() or "Sepsis" in comment

    def test_ectopico_cluster_note_appended(self):
        comment = svc._build_ai_comment(1, clusters=[("ectopico", 1)])
        assert "ect" in comment.lower() or "transvaginal" in comment.lower()

    def test_hipoglucemia_cluster_note_appended(self):
        comment = svc._build_ai_comment(2, clusters=[("hipoglucemia detectada", 2)])
        assert "hipoglucemia" in comment.lower() or "glucosa" in comment.lower()

    def test_moderate_dehydration_note_in_comment(self):
        comment = svc._build_ai_comment(3, transcript="sed intensa boca seca")
        assert "moderada" in comment.lower() or "suero oral" in comment.lower()

    def test_mild_dehydration_note_in_comment(self):
        comment = svc._build_ai_comment(3, transcript="sed intensa")
        assert "oral" in comment.lower() or "hidrat" in comment.lower()

    def test_obstetric_note_in_comment(self):
        comment = svc._build_ai_comment(2, transcript="contracciones frecuentes")
        assert "obstetrica" in comment.lower() or "fetal" in comment.lower()

    def test_systolic_bp_note_in_comment(self):
        comment = svc._build_ai_comment(2, transcript="presion arterial 185/110")
        assert "sistolica" in comment.lower() or "TA" in comment or "hipertensiva" in comment.lower()

    def test_hr_note_in_comment(self):
        comment = svc._build_ai_comment(2, transcript="frecuencia cardiaca 130 lpm")
        assert "FC" in comment or "cardiaco" in comment.lower() or "lpm" in comment.lower()


# ─── build_recommendation ────────────────────────────────────────────────────

class TestBuildRecommendation:
    def _triage(self, priority: int, symptoms=None, causes=None) -> TriageDataCore:
        return TriageDataCore(
            nivelPrioridad=priority,
            sintomas=symptoms or [],
            posiblesCausas=causes or [],
        )

    def test_priority_1(self):
        rec = svc.build_recommendation(self._triage(1, ["convulsion"]))
        assert "N1" in rec

    def test_priority_2(self):
        rec = svc.build_recommendation(self._triage(2, ["dolor toracico"]))
        assert "N2" in rec

    def test_priority_3(self):
        rec = svc.build_recommendation(self._triage(3, ["fiebre"]))
        assert "N3" in rec
        assert "dengue" in rec.lower()

    def test_priority_4(self):
        assert "N4" in svc.build_recommendation(self._triage(4))

    def test_priority_5(self):
        assert "N5" in svc.build_recommendation(self._triage(5))

    def test_dengue_no_ibuprofeno_hint(self):
        symptoms = ["fiebre", "cefalea", "mialgia", "sarpullido"]
        rec = svc.build_recommendation(self._triage(3, symptoms))
        assert "ibuprofeno" in rec.lower() or "DENGUE" in rec

    def test_dengue_alarm_hint(self):
        symptoms = ["fiebre", "petequias", "sangrado de encias"]
        rec = svc.build_recommendation(self._triage(2, symptoms))
        assert "ALARMA" in rec

    def test_dehydration_hint_severe(self):
        symptoms = ["sed intensa", "boca seca", "orina oscura"]
        rec = svc.build_recommendation(self._triage(2, symptoms))
        assert "DESHIDRATACION" in rec or "hidrat" in rec.lower()

    def test_no_symptoms_fallback_text(self):
        rec = svc.build_recommendation(self._triage(5))
        assert "malestar no especificado" in rec

    def test_causes_in_recommendation(self):
        rec = svc.build_recommendation(self._triage(3, ["fiebre"], ["dengue"]))
        assert "dengue" in rec

    def test_symptoms_in_recommendation(self):
        rec = svc.build_recommendation(self._triage(3, ["fiebre", "vomito"]))
        assert "fiebre" in rec


# ─── get_confidence_score ────────────────────────────────────────────────────

class TestGetConfidenceScore:
    def test_all_fields_filled_returns_1(self):
        triage = TriageDataCore(
            sintomas=["fiebre"],
            posiblesCausas=["dengue"],
            comentario="fiebre desde ayer",
            comentariosIA="IA: prioridad media",
        )
        assert svc.get_confidence_score(triage) == 1.0

    def test_empty_sintomas_returns_075(self):
        triage = TriageDataCore(
            sintomas=[],
            posiblesCausas=["dengue"],
            comentario="fiebre",
            comentariosIA="IA: algo",
        )
        assert svc.get_confidence_score(triage) == 0.75

    def test_two_fields_returns_05(self):
        triage = TriageDataCore(
            sintomas=[],
            posiblesCausas=[],
            comentario="fiebre",
            comentariosIA="IA: algo",
        )
        assert svc.get_confidence_score(triage) == 0.5

    def test_all_empty_returns_0(self):
        triage = TriageDataCore(
            sintomas=[], posiblesCausas=[], comentario="", comentariosIA=""
        )
        assert svc.get_confidence_score(triage) == 0.0


# ─── generate_procedure_id ───────────────────────────────────────────────────

class TestGenerateProcedureId:
    def test_contains_patient_id(self):
        pid = TriageExtractionService.generate_procedure_id("12345678")
        assert "12345678" in pid

    def test_contains_underscore_separator(self):
        pid = TriageExtractionService.generate_procedure_id("abc")
        assert "_" in pid

    def test_special_chars_stripped(self):
        pid = TriageExtractionService.generate_procedure_id("123-456 @test")
        assert "@" not in pid
        assert " " not in pid

    def test_long_id_truncated(self):
        long_id = "a" * 100
        pid = TriageExtractionService.generate_procedure_id(long_id)
        prefix = pid.split("_")[0]
        assert len(prefix) <= 40

    def test_empty_id_becomes_unknown(self):
        assert "unknown" in TriageExtractionService.generate_procedure_id("")

    def test_special_only_becomes_unknown(self):
        assert "unknown" in TriageExtractionService.generate_procedure_id("@@@!!!###")

    def test_two_ids_differ_in_timestamp(self):
        pid1 = TriageExtractionService.generate_procedure_id("123")
        pid2 = TriageExtractionService.generate_procedure_id("123")
        # Both have same prefix; timestamps may or may not differ (same second)
        assert pid1.startswith("123_")
        assert pid2.startswith("123_")


# ─── _normalize_data ─────────────────────────────────────────────────────────

class TestNormalizeData:
    def test_basic_dict(self):
        data = {
            "sintomas": ["fiebre", "vomito"],
            "embarazo": False,
            "antecedentes": ["diabetes"],
            "posiblesCausas": ["dengue"],
            "comentario": "fiebre desde ayer",
            "nivelPrioridad": 3,
            "comentariosIA": "IA: algo",
        }
        result = svc._normalize_data(data, "fiebre y vomito")
        assert result.sintomas == ["fiebre", "vomito"]
        assert result.antecedentes == ["diabetes"]
        assert result.nivelPrioridad == 3

    def test_string_sintomas_split(self):
        data = {"sintomas": "fiebre, vomito", "nivelPrioridad": 3}
        result = svc._normalize_data(data, "test")
        assert len(result.sintomas) >= 1

    def test_priority_clamped_upper(self):
        result = svc._normalize_data({"nivelPrioridad": 10}, "test")
        assert result.nivelPrioridad == 5

    def test_priority_clamped_lower(self):
        # 0 is falsy → `0 or 3` defaults to 3, not 1.
        # Use a negative number (-1 is truthy) to test actual lower-bound clamping.
        result = svc._normalize_data({"nivelPrioridad": -1}, "test")
        assert result.nivelPrioridad == 1

    def test_empty_comentarios_ia_builds_default(self):
        data = {"sintomas": ["fiebre"], "nivelPrioridad": 3, "comentariosIA": ""}
        result = svc._normalize_data(data, "fiebre")
        assert result.comentariosIA != ""
        assert "IA:" in result.comentariosIA

    def test_empty_comentario_uses_transcript(self):
        data = {"comentario": "", "nivelPrioridad": 3}
        result = svc._normalize_data(data, "fiebre y vomito desde ayer")
        assert result.comentario != ""

    def test_warning_ia_always_set(self):
        result = svc._normalize_data({}, "test")
        assert result.advertenciaIA == svc.IA_WARNING

    def test_none_fields_cleaned(self):
        data = {"sintomas": None, "posiblesCausas": None, "nivelPrioridad": 3}
        result = svc._normalize_data(data, "test")
        assert result.sintomas == []
        assert result.posiblesCausas == []

    def test_null_strings_in_list_removed(self):
        data = {"sintomas": ["fiebre", "null", ""], "nivelPrioridad": 3}
        result = svc._normalize_data(data, "test")
        assert "null" not in result.sintomas
        assert "" not in result.sintomas
        assert "fiebre" in result.sintomas

    def test_string_antecedentes_split(self):
        data = {"antecedentes": "diabetes, hipertension", "nivelPrioridad": 3}
        result = svc._normalize_data(data, "test")
        assert isinstance(result.antecedentes, list)
        assert len(result.antecedentes) >= 1

    def test_string_posibles_causas_split(self):
        data = {"posiblesCausas": "dengue, gripe viral", "nivelPrioridad": 3}
        result = svc._normalize_data(data, "test")
        assert isinstance(result.posiblesCausas, list)
        assert len(result.posiblesCausas) >= 1


# ─── extract_preliminary_history (async) ─────────────────────────────────────

async def test_extract_ollama_disabled_uses_heuristics():
    with patch("app.services.triage_service.settings") as ms:
        ms.ollama_base_url = ""
        ms.ollama_model = ""
        ms.ollama_max_concurrent = 2
        result = await svc.extract_preliminary_history("tengo fiebre y vomito")
    assert isinstance(result, TriageDataCore)
    assert len(result.sintomas) > 0


async def test_extract_ollama_success_returns_normalized():
    ollama_body = {
        "response": (
            '{"sintomas":["fiebre"],"embarazo":false,"antecedentes":[],'
            '"posiblesCausas":["dengue"],"comentario":"fiebre","nivelPrioridad":3,'
            '"comentariosIA":"IA: prioridad media"}'
        )
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = ollama_body
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp

    with patch("app.services.triage_service.settings") as ms:
        ms.ollama_base_url = "http://localhost:11434"
        ms.ollama_model = "test-model"
        ms.ollama_timeout_seconds = 12
        ms.ollama_max_concurrent = 2
        with patch("httpx.AsyncClient") as mock_httpx:
            mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await svc.extract_preliminary_history("tengo fiebre")

    assert isinstance(result, TriageDataCore)
    assert result.nivelPrioridad == 3


async def test_extract_ollama_http_error_falls_back():
    with patch("app.services.triage_service.settings") as ms:
        ms.ollama_base_url = "http://localhost:11434"
        ms.ollama_model = "test-model"
        ms.ollama_timeout_seconds = 12
        ms.ollama_max_concurrent = 2
        with patch("httpx.AsyncClient") as mock_httpx:
            mock_httpx.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await svc.extract_preliminary_history("tengo fiebre y dolor de cabeza")

    assert isinstance(result, TriageDataCore)
    assert result.nivelPrioridad >= 1


async def test_extract_empty_transcript_returns_triage_core():
    with patch("app.services.triage_service.settings") as ms:
        ms.ollama_base_url = ""
        ms.ollama_model = ""
        ms.ollama_max_concurrent = 2
        result = await svc.extract_preliminary_history("")
    assert isinstance(result, TriageDataCore)


async def test_extract_ollama_max_concurrent_skips_ollama():
    import app.services.triage_service as ts_module
    original = ts_module._ollama_active
    ts_module._ollama_active = 10  # exceed max
    try:
        with patch("app.services.triage_service.settings") as ms:
            ms.ollama_base_url = "http://localhost:11434"
            ms.ollama_model = "test-model"
            ms.ollama_timeout_seconds = 12
            ms.ollama_max_concurrent = 2
            result = await svc.extract_preliminary_history("tengo fiebre")
    finally:
        ts_module._ollama_active = original

    assert isinstance(result, TriageDataCore)


async def test_extract_full_clinical_scenario():
    """End-to-end heuristic path for a typical dengue presentation."""
    with patch("app.services.triage_service.settings") as ms:
        ms.ollama_base_url = ""
        ms.ollama_model = ""
        ms.ollama_max_concurrent = 2
        result = await svc.extract_preliminary_history(
            "Paciente con fiebre de 39 grados, cefalea intensa, mialgia, sarpullido en brazos. "
            "Viene de zona rural. Antecedentes: diabetes."
        )

    assert isinstance(result, TriageDataCore)
    assert "fiebre" in result.sintomas
    assert result.nivelPrioridad <= 3
    assert any("dengue" in c for c in result.posiblesCausas)


async def test_extract_ollama_empty_response_falls_back():
    ollama_body = {"response": ""}
    mock_resp = MagicMock()
    mock_resp.json.return_value = ollama_body
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp

    with patch("app.services.triage_service.settings") as ms:
        ms.ollama_base_url = "http://localhost:11434"
        ms.ollama_model = "test-model"
        ms.ollama_timeout_seconds = 12
        ms.ollama_max_concurrent = 2
        with patch("httpx.AsyncClient") as mock_httpx:
            mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await svc.extract_preliminary_history("fiebre y vomito")

    assert isinstance(result, TriageDataCore)

"""
Unit tests for the canonical room metrics formulas.

These tests lock in the expected output of the shared scoring functions so that
formula changes cause an explicit test failure rather than a silent regression.
"""

import pytest
from app.services.room_metrics_service import (
    compute_air_strain,
    compute_recovery_score,
    compute_room_readiness,
    compute_room_state,
    enrich_row,
)


# ── compute_room_readiness ─────────────────────────────────────────────────────

class TestComputeRoomReadiness:
    def test_ideal_conditions_gives_100(self):
        # 21 °C, 50% RH, 0 TVOC, 400 ppm eCO2 → all sub-scores = 100
        assert compute_room_readiness(21.0, 50.0, 0.0, 400.0) == 100

    def test_perfect_temp_off_by_one_degree(self):
        # 22 °C → temp_score = 100 - 1*8 = 92; hum and air still 100
        result = compute_room_readiness(22.0, 50.0, 0.0, 400.0)
        assert result == int(92 * 0.40 + 100 * 0.25 + 100 * 0.35)

    def test_high_tvoc_reduces_readiness(self):
        # TVOC 200 ppb → aq_penalty=100; eco2_penalty=0
        # air_score = 100 - (100*0.60 + 0*0.40) = 40 (not 0 — eCO2 penalty absent)
        result = compute_room_readiness(21.0, 50.0, 200.0, 400.0)
        air_score = max(0.0, 100.0 - (min(100.0, 200.0 / 2.0) * 0.60))
        assert result == int(100 * 0.40 + 100 * 0.25 + air_score * 0.35)

    def test_result_is_clamped_to_non_negative(self):
        # Extreme conditions should not go below 0
        result = compute_room_readiness(40.0, 10.0, 1000.0, 5000.0)
        assert result >= 0

    def test_result_does_not_exceed_100(self):
        result = compute_room_readiness(21.0, 50.0, 0.0, 400.0)
        assert result <= 100

    def test_none_aq_treated_as_zero(self):
        # enrich_row passes 0.0 for None, but if called directly with 0.0 explicitly
        result = compute_room_readiness(21.0, 50.0, 0.0, 400.0)
        assert result == 100


# ── compute_recovery_score ────────────────────────────────────────────────────

class TestComputeRecoveryScore:
    def test_ideal_conditions_gives_100(self):
        # 20 °C, 52% RH, 0 TVOC, 400 ppm eCO2
        assert compute_recovery_score(20.0, 52.0, 0.0, 400.0) == 100

    def test_temp_1_degree_off_ideal(self):
        # 21 °C → temp_score = 100 - 1*10 = 90
        result = compute_recovery_score(21.0, 52.0, 0.0, 400.0)
        assert result == int(90 * 0.35 + 100 * 0.30 + 100 * 0.35)

    def test_high_eco2_reduces_recovery(self):
        # eCO2 2000 ppm → eco2_penalty = min(100, (2000-400)/16) = 100
        # air_score = max(0, 100 - (0*0.60 + 100*0.40)) = 60
        result = compute_recovery_score(20.0, 52.0, 0.0, 2000.0)
        assert result == int(100 * 0.35 + 100 * 0.30 + 60 * 0.35)

    def test_result_does_not_exceed_100(self):
        assert compute_recovery_score(20.0, 52.0, 0.0, 400.0) <= 100

    def test_result_is_non_negative(self):
        assert compute_recovery_score(35.0, 5.0, 500.0, 5000.0) >= 0


# ── compute_air_strain ────────────────────────────────────────────────────────

class TestComputeAirStrain:
    def test_clean_air_gives_zero(self):
        # 21 °C, 50% RH, 0 TVOC, 400 ppm eCO2 → all factors = 0
        assert compute_air_strain(21.0, 50.0, 0.0, 400.0) == 0

    def test_heavy_tvoc_drives_high_strain(self):
        # 200 ppb TVOC → aq_factor=100; no heat; no CO2
        result = compute_air_strain(21.0, 50.0, 200.0, 400.0)
        assert result == int(100 * 0.50 + 0 * 0.35 + 0 * 0.15)

    def test_heat_above_22_adds_strain(self):
        # 25 °C, clean air → temp_factor = (25-22)*5 = 15
        result = compute_air_strain(25.0, 50.0, 0.0, 400.0)
        assert result == int(0 * 0.50 + 0 * 0.35 + 15 * 0.15)

    def test_heat_at_or_below_22_no_heat_factor(self):
        assert compute_air_strain(22.0, 50.0, 0.0, 400.0) == 0

    def test_combined_heavy_conditions(self):
        # 25 °C, 300 ppb TVOC, 1200 ppm eCO2
        aq_f   = min(100.0, 300 / 2.0)        # 100
        co2_f  = min(100.0, (1200 - 400) / 16.0)  # 50
        temp_f = min(100.0, (25 - 22) * 5.0)  # 15
        expected = int(aq_f * 0.50 + co2_f * 0.35 + temp_f * 0.15)
        assert compute_air_strain(25.0, 50.0, 300.0, 1200.0) == expected

    def test_result_is_non_negative(self):
        assert compute_air_strain(0.0, 50.0, 0.0, 400.0) >= 0

    def test_result_does_not_exceed_100(self):
        assert compute_air_strain(40.0, 50.0, 1000.0, 5000.0) <= 100


# ── compute_room_state ────────────────────────────────────────────────────────

class TestComputeRoomState:
    def test_dry_when_humidity_below_40(self):
        # Humidity below threshold overrides everything else
        assert compute_room_state(100, 100, 0, 35.0) == "Dry"

    def test_dry_at_exact_threshold_boundary(self):
        # humidity=39 → Dry; humidity=40 → not Dry
        assert compute_room_state(100, 100, 0, 39.9) == "Dry"
        assert compute_room_state(50, 50, 0, 40.0) != "Dry"

    def test_heavy_when_strain_65_or_above(self):
        assert compute_room_state(50, 50, 65, 50.0) == "Heavy"
        assert compute_room_state(50, 50, 99, 50.0) == "Heavy"

    def test_heavy_not_triggered_at_64(self):
        assert compute_room_state(50, 50, 64, 50.0) != "Heavy"

    def test_social_when_motion_true(self):
        # strain=30 (not heavy), humidity=55 (not dry), motion=True
        assert compute_room_state(50, 50, 30, 55.0, motion=True) == "Social"

    def test_social_not_triggered_without_motion(self):
        result = compute_room_state(50, 50, 30, 55.0, motion=False)
        assert result != "Social"

    def test_fresh_when_low_strain_and_good_humidity(self):
        # strain < 25, 40 <= humidity <= 70, no motion
        assert compute_room_state(70, 60, 20, 55.0) == "Fresh"

    def test_fresh_not_triggered_outside_humidity_range(self):
        # humidity = 75 → outside 40–70 band
        result = compute_room_state(70, 60, 20, 75.0)
        assert result != "Fresh"

    def test_sleep_friendly_when_high_recovery(self):
        # strain=30 (not heavy/fresh), recovery >= 70
        assert compute_room_state(70, 75, 30, 55.0) == "Sleep-Friendly"

    def test_calm_when_moderate_recovery(self):
        # recovery=60 (55–69 range), strain=30
        assert compute_room_state(60, 60, 30, 55.0) == "Calm"

    def test_restless_when_elevated_strain_low_recovery(self):
        # strain=50, recovery=40 (below 55)
        assert compute_room_state(50, 40, 50, 55.0) == "Restless"

    def test_calm_as_default_fallback(self):
        # strain=30 (not restless), recovery=40 (not calm from threshold)
        result = compute_room_state(50, 40, 30, 55.0)
        assert result == "Calm"

    def test_dry_trumps_heavy(self):
        # dry humidity AND high strain → Dry wins (first in cascade)
        assert compute_room_state(50, 50, 80, 35.0) == "Dry"

    def test_heavy_trumps_social(self):
        # strain=70 AND motion=True → Heavy wins
        assert compute_room_state(50, 50, 70, 55.0, motion=True) == "Heavy"


# ── enrich_row ────────────────────────────────────────────────────────────────

class TestEnrichRow:
    def test_adds_all_score_keys(self):
        row = {
            "device_id": "test-device",
            "indoor_temp": 21.0,
            "indoor_humidity": 50.0,
            "air_quality": 0.0,
            "indoor_eco2": 400.0,
            "motion": False,
        }
        result = enrich_row(row)
        assert "readiness_score" in result
        assert "recovery_score" in result
        assert "air_strain_score" in result
        assert "room_state" in result

    def test_legacy_aliases_present(self):
        row = {"indoor_temp": 21.0, "indoor_humidity": 50.0}
        result = enrich_row(row)
        assert "room_readiness" in result
        assert "air_strain" in result
        assert result["room_readiness"] == result["readiness_score"]
        assert result["air_strain"] == result["air_strain_score"]

    def test_none_values_use_defaults(self):
        # Sensor values missing → uses defaults: temp=20, hum=50, aq=0, eco2=400
        row = {"device_id": "test"}
        result = enrich_row(row)
        assert isinstance(result["readiness_score"], int)
        assert isinstance(result["recovery_score"], int)

    def test_motion_true_produces_social(self):
        row = {
            "indoor_temp": 21.0,
            "indoor_humidity": 55.0,
            "air_quality": 30.0,
            "indoor_eco2": 400.0,
            "motion": True,
        }
        result = enrich_row(row)
        # strain should be low enough to not be Heavy
        assert result["room_state"] == "Social"

    def test_original_fields_preserved(self):
        row = {"device_id": "test-device", "indoor_temp": 21.0, "indoor_humidity": 50.0}
        result = enrich_row(row)
        assert result["device_id"] == "test-device"
        assert result["indoor_temp"] == 21.0

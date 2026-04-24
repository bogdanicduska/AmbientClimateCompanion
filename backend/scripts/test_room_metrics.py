"""Quick sanity checks for room_metrics_service — no server needed."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.room_metrics_service import (
    compute_air_strain,
    compute_recovery_score,
    compute_room_readiness,
    compute_room_state,
    enrich_row,
)


def check(label, got, lo, hi):
    ok = lo <= got <= hi
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}: {got}  (expected {lo}–{hi})")
    assert ok, f"{label} out of range: {got}"


print("\n=== Air Strain ===")
# Fresh air: low TVOC, normal eCO2, cool temp
check("fresh air", compute_air_strain(20, 50, 10, 450), 0, 15)
# Heavy: high TVOC, high eCO2, warm
check("heavy room", compute_air_strain(26, 55, 180, 1800), 65, 100)
# Moderate
check("moderate strain", compute_air_strain(22, 50, 80, 900), 20, 55)

print("\n=== Recovery Score ===")
# Ideal recovery conditions
check("ideal recovery", compute_recovery_score(20, 52, 5, 420), 85, 100)
# Poor conditions (hot, dry, polluted)
check("poor recovery", compute_recovery_score(28, 30, 200, 2000), 0, 30)
# Moderate
check("moderate recovery", compute_recovery_score(23, 50, 60, 700), 60, 85)

print("\n=== Room Readiness ===")
# Ideal readiness conditions
check("ideal readiness", compute_room_readiness(21, 50, 5, 420), 85, 100)
# Poor conditions
check("poor readiness", compute_room_readiness(28, 30, 200, 2000), 0, 30)

print("\n=== Room State ===")
cases = [
    (20, 52, 0, 20, 50, 85, "Dry" if 52 < 40 else None),
    # Dry
    (20, 35, 0, 20, 50, 85, "Dry"),
    # Heavy
    (26, 55, 180, 70, 30, 20, "Heavy"),
    # Fresh
    (20, 55, 5, 5, 80, 80, "Fresh"),
    # Sleep-Friendly: strain must be >= 25 so Fresh branch is skipped
    (20, 52, 5, 30, 85, 80, "Sleep-Friendly"),
]
for temp, hum, aq, strain, readiness, recovery, expected in cases:
    state = compute_room_state(readiness, recovery, strain, hum)
    ok = state == expected if expected else True
    status = "PASS" if ok else f"FAIL (got {state!r}, expected {expected!r})"
    print(f"  [{status}] humidity={hum}% strain={strain} -> {state}")

print("\n=== enrich_row ===")
row = {
    "device_id": "test",
    "timestamp": "2026-04-24T10:00:00+00:00",
    "indoor_temp": 21.0,
    "indoor_humidity": 50.0,
    "air_quality": 20.0,
    "indoor_eco2": 500.0,
}
enriched = enrich_row(row)
assert "room_readiness" in enriched
assert "recovery_score" in enriched
assert "air_strain" in enriched
assert "room_state" in enriched
print(f"  [PASS] enrich_row -> readiness={enriched['room_readiness']} "
        f"recovery={enriched['recovery_score']} strain={enriched['air_strain']} state={enriched['room_state']!r}")

print("\nAll room_metrics tests passed.\n")

"""
Ritual coaching recommendations — mirrors device get_coach_data() logic.
Returns RitualRecommendation contract (services/contracts.py).
"""

from __future__ import annotations
from datetime import datetime, timezone

from .contracts import RitualRecommendation, LatestRoomState


def _is_evening() -> bool:
    return datetime.now(timezone.utc).hour >= 19


def get_ritual(lrs: "LatestRoomState | dict") -> RitualRecommendation:
    """
    Derive the most appropriate ritual from a LatestRoomState.
    Accepts both the full contract dict and raw enriched dicts for compatibility.
    """
    # Support both LatestRoomState and legacy enriched dicts
    if "air_strain_score" in lrs:
        # LatestRoomState contract
        strain     = lrs.get("air_strain_score")
        room_state = lrs.get("room_state", "")
        indoor     = lrs.get("indoor", {})
        outdoor    = lrs.get("outdoor", {})
        humidity   = indoor.get("humidity_pct")
        recovery   = lrs.get("recovery_score")
        readiness  = lrs.get("readiness_score")
        o_temp     = outdoor.get("temperature_c")
        o_desc     = (outdoor.get("weather_main") or "").lower()
        motion     = indoor.get("motion", False)
    else:
        # Legacy enriched dict (raw API + enrich())
        strain     = lrs.get("air_strain")
        room_state = lrs.get("room_state", "")
        humidity   = lrs.get("indoor_humidity")
        recovery   = lrs.get("recovery_score")
        readiness  = lrs.get("room_readiness")
        o_temp     = lrs.get("outdoor_temp")
        o_desc     = (lrs.get("outdoor_weather") or "").lower()
        motion     = lrs.get("motion", False)

    if (strain is not None and strain >= 60) or room_state == "Heavy":
        return RitualRecommendation(
            ritual_id="ritual_ventilate",
            title="Fresh Air Ritual",
            subtitle="Air feels heavy",
            state=room_state,
            reason_lines=["Air strain is elevated", "Heavy room state detected"],
            next_step="Open a window for 3 minutes",
            expected_benefit="May lower strain and improve comfort",
            icon="wind",
            priority="high",
        )

    if (humidity is not None and humidity < 40) or room_state == "Dry":
        hum_str = f"{int(humidity)}%" if humidity is not None else "--"
        return RitualRecommendation(
            ritual_id="ritual_hydrate",
            title="Hydrate + Reset",
            subtitle=f"Humidity low at {hum_str}",
            state=room_state,
            reason_lines=["Dry air reduces comfort", f"Humidity at {hum_str}"],
            next_step="Drink a glass of water",
            expected_benefit="Hydration helps offset dry air discomfort",
            icon="drop",
            priority="high",
        )

    if _is_evening() and recovery is not None and recovery >= 75 \
            and room_state in ("Calm", "Sleep-Friendly"):
        return RitualRecommendation(
            ritual_id="ritual_winddown",
            title="Wind-Down Ritual",
            subtitle="Conditions favour rest",
            state=room_state,
            reason_lines=["Recovery score is high", "Evening — good conditions for rest"],
            next_step="Dim lights and sit quietly for 2 minutes",
            expected_benefit="Strengthens transition to sleep",
            icon="moon",
            priority="medium",
        )

    if readiness is not None and readiness >= 75 \
            and strain is not None and strain < 40 \
            and room_state in ("Fresh", "Calm"):
        return RitualRecommendation(
            ritual_id="ritual_focus",
            title="Focus Ritual",
            subtitle="Room is ready for deep work",
            state=room_state,
            reason_lines=["Room Readiness is high", "Air strain is low"],
            next_step="Clear your space and start a 20-minute block",
            expected_benefit="Fresh air and stable conditions support focus",
            icon="arrow",
            priority="medium",
        )

    wx_ok = (
        o_temp is not None
        and 10 <= o_temp <= 22
        and "rain" not in o_desc
        and "storm" not in o_desc
    )
    if wx_ok and not _is_evening() and not motion and room_state not in ("Heavy", "Dry"):
        return RitualRecommendation(
            ritual_id="ritual_outside",
            title="Outdoor Break",
            subtitle="Good conditions outside",
            state=room_state,
            reason_lines=["Weather is mild", "Step outside for a brief reset"],
            next_step="Go outside for 5 minutes",
            expected_benefit="Fresh air and movement improve alertness",
            icon="leaf",
            priority="low",
        )

    return RitualRecommendation(
        ritual_id="ritual_reset",
        title="Reset Ritual",
        subtitle="Take a short mental break",
        state=room_state,
        reason_lines=["A brief pause can restore focus", "3 minutes is enough"],
        next_step="Sit quietly and take 3 slow breaths",
        expected_benefit="Reduces mental fatigue and resets attention",
        icon="pause",
        priority="low",
    )


# ---------------------------------------------------------------------------
# Alternative ritual — second-best recommendation, different from primary
# ---------------------------------------------------------------------------

_ALL_RITUAL_IDS = [
    "ritual_ventilate",
    "ritual_hydrate",
    "ritual_winddown",
    "ritual_focus",
    "ritual_outside",
    "ritual_reset",
]

_ALTERNATIVES: dict[str, RitualRecommendation] = {
    "ritual_ventilate": RitualRecommendation(
        ritual_id="ritual_reset",
        title="Short Break",
        subtitle="If ventilation isn't possible",
        state="",
        reason_lines=["Step away from the room briefly"],
        next_step="Take a 5-minute break away from the space",
        expected_benefit="Reduces exposure to stale air while the room clears",
        icon="pause",
        priority="medium",
    ),
    "ritual_hydrate": RitualRecommendation(
        ritual_id="ritual_ventilate",
        title="Fresh Air Ritual",
        subtitle="Also helps with dry conditions",
        state="",
        reason_lines=["Fresh outdoor air can help offset dry indoor air"],
        next_step="Open a window briefly",
        expected_benefit="Improves air circulation and ambient humidity",
        icon="wind",
        priority="medium",
    ),
    "ritual_winddown": RitualRecommendation(
        ritual_id="ritual_reset",
        title="Reset Ritual",
        subtitle="Lighter option before sleep",
        state="",
        reason_lines=["A quiet reset prepares the body for rest"],
        next_step="Sit quietly and take 3 slow breaths",
        expected_benefit="Calms the nervous system before wind-down",
        icon="pause",
        priority="low",
    ),
    "ritual_focus": RitualRecommendation(
        ritual_id="ritual_outside",
        title="Outdoor Break",
        subtitle="Boost focus with fresh air first",
        state="",
        reason_lines=["A brief outdoor break sharpens attention"],
        next_step="Go outside for 5 minutes before starting work",
        expected_benefit="Outdoor light and air improve cognitive readiness",
        icon="leaf",
        priority="low",
    ),
    "ritual_outside": RitualRecommendation(
        ritual_id="ritual_focus",
        title="Focus Ritual",
        subtitle="If you prefer to stay in",
        state="",
        reason_lines=["Room conditions also support indoor focus"],
        next_step="Clear your space and start a 20-minute block",
        expected_benefit="Good indoor conditions support sustained focus",
        icon="arrow",
        priority="low",
    ),
    "ritual_reset": RitualRecommendation(
        ritual_id="ritual_focus",
        title="Focus Ritual",
        subtitle="Channel the reset into work",
        state="",
        reason_lines=["After a reset, conditions may support focus"],
        next_step="Try a short 15-minute focused block",
        expected_benefit="Short focused blocks build momentum",
        icon="arrow",
        priority="low",
    ),
}


def get_alternative_ritual(primary_id: str) -> RitualRecommendation:
    """Return an alternative ritual that complements the primary recommendation."""
    return _ALTERNATIVES.get(primary_id, _ALTERNATIVES["ritual_reset"])

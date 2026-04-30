"""
State chip helpers — delegates to services/state_meta (single source of truth).
Kept for backward compatibility and direct component use.
"""

from services.state_meta import state_meta, state_subtitle, state_accent, ACCENT_HEX

# Re-export the canonical dict for any component that still uses _STATE_COLORS
STATE_COLORS = {
    k: {"bg": v["bg"], "border": v["border"], "text": v["text"], "desc": v["subtitle"]}
    for k, v in {
        "Fresh":          {"bg": "#071F10", "border": "#0F4020", "text": "#3DFF8A",  "subtitle": "Light, usable, and supportive"},
        "Calm":           {"bg": "#071220", "border": "#0E2848", "text": "#66CCFF",  "subtitle": "Balanced, stable, and quiet"},
        "Dry":            {"bg": "#1C1200", "border": "#3A2800", "text": "#FFD060",  "subtitle": "Humidity too low — comfort reduced"},
        "Heavy":          {"bg": "#1C0500", "border": "#4A1000", "text": "#FF6644",  "subtitle": "Air feels stale or burdened"},
        "Social":         {"bg": "#181500", "border": "#383000", "text": "#DDDD00",  "subtitle": "Room is active and in use"},
        "Sleep-Friendly": {"bg": "#060F1C", "border": "#0C1E38", "text": "#88BBFF",  "subtitle": "Suitable for rest and calm"},
        "Restless":       {"bg": "#1A0E00", "border": "#3A2000", "text": "#FF9944",  "subtitle": "Conditions are unbalanced"},
    }.items()
}


def state_color(state: str) -> dict:
    m = state_meta(state)
    return {"bg": m["bg"], "border": m["border"], "text": m["text"], "desc": m["subtitle"]}

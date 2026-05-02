"""
Score explanations and trend arrows — pure functions, no Streamlit calls.
explanations() returns lists; callers join for display or embed in contracts.
"""

from __future__ import annotations
import pandas as pd


# ---------------------------------------------------------------------------
# Factor lists (contract: Explanations.readiness / recovery / air_strain)
# ---------------------------------------------------------------------------

def build_explanations(row: dict) -> dict[str, list[str] | str]:
    """
    Return explanation lists for each score plus room_state_subtitle.
    Keys: readiness, recovery, air_strain, room_state_subtitle
    """
    from .state_meta import state_subtitle  # local import to avoid circular

    temp     = row.get("indoor_temp")
    humidity = row.get("indoor_humidity")
    tvoc     = row.get("air_quality")
    eco2     = row.get("indoor_eco2")
    motion   = row.get("motion")
    state    = row.get("room_state", "")

    r_parts: list[str] = []
    if temp is not None:
        if 19 <= temp <= 23:     r_parts.append("good temp")
        elif temp > 26:          r_parts.append("slightly warm")
        elif temp < 17:          r_parts.append("too cool")
        else:                    r_parts.append("temp ok")
    if humidity is not None:
        if 40 <= humidity <= 60: r_parts.append("good humidity")
        elif humidity < 40:      r_parts.append("dry air")
        elif humidity > 70:      r_parts.append("humid")
    if tvoc is not None:
        if tvoc < 100:           r_parts.append("fresh air")
        elif tvoc < 150:         r_parts.append("moderate TVOC")
        else:                    r_parts.append("high TVOC")

    v_parts: list[str] = []
    if temp is not None:
        if 18 <= temp <= 22:     v_parts.append("restful temp")
        elif temp > 24:          v_parts.append("warm for rest")
        elif temp < 17:          v_parts.append("cool")
    if humidity is not None:
        if 45 <= humidity <= 65: v_parts.append("good humidity")
        elif humidity < 40:      v_parts.append("dry room")
    if motion:                   v_parts.append("recent activity")
    elif tvoc is not None and tvoc < 100:
                                 v_parts.append("clean air")

    s_parts: list[str] = []
    if tvoc is not None:
        if tvoc < 50:            s_parts.append("fresh air")
        elif tvoc < 100:         s_parts.append(f"low CO2")
        elif tvoc < 150:         s_parts.append(f"TVOC moderate ({int(tvoc)})")
        else:                    s_parts.append(f"TVOC high ({int(tvoc)})")
    if eco2 is not None:
        if eco2 < 800:           s_parts.append(f"low CO2")
        elif eco2 < 1200:        s_parts.append(f"CO₂ elevated ({int(eco2)})")
        else:                    s_parts.append(f"CO₂ high ({int(eco2)})")

    return {
        "readiness":           r_parts,
        "recovery":            v_parts,
        "air_strain":          s_parts,
        "room_state_subtitle": state_subtitle(state),
    }


def joined(parts: list[str]) -> str:
    """Join explanation list to display string."""
    return "  ·  ".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# Trend arrows
# ---------------------------------------------------------------------------

def score_trend(
    current: int | None,
    df: "pd.DataFrame",
    col: str,
) -> tuple[str, str, str]:
    """Return (arrow_glyph, delta_label, color) vs 1h rolling average."""
    if current is None or df is None or df.empty or col not in df.columns:
        return "", "", "#556677"
    try:
        cutoff = df["timestamp"].max() - pd.Timedelta(hours=1)
        recent = df[df["timestamp"] >= cutoff][col].dropna()
        if recent.empty:
            return "", "", "#556677"
        avg   = recent.mean()
        delta = int(round(current - avg))
        if abs(delta) < 2:
            return "→", "stable", "#556677"
        if delta > 0:
            return "↑", f"+{delta}", "#3DFF8A"
        return "↓", str(delta), "#FF8844"
    except Exception:
        return "", "", "#556677"

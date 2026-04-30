"""
Analytical layer: score explanations, trend deltas, daily story, outdoor suitability.
All functions are pure (no Streamlit calls) — they return strings/tuples for use in components.
"""

from __future__ import annotations
import pandas as pd


# ---------------------------------------------------------------------------
# "Why this score?" — short explanation built from live sensor values
# ---------------------------------------------------------------------------

def score_explanations(row: dict) -> dict[str, str]:
    """
    Return one-line explanations for each score based on the contributing factors.
    Keys: readiness_why, recovery_why, strain_why
    """
    temp     = row.get("indoor_temp")
    humidity = row.get("indoor_humidity")
    tvoc     = row.get("air_quality")
    eco2     = row.get("indoor_eco2")
    motion   = row.get("motion")

    # --- readiness factors ---
    r_parts = []
    if temp is not None:
        if 19 <= temp <= 23:         r_parts.append("good temp")
        elif temp > 26:              r_parts.append("too warm")
        elif temp < 17:              r_parts.append("too cool")
        else:                        r_parts.append("temp ok")
    if humidity is not None:
        if 40 <= humidity <= 60:     r_parts.append("good humidity")
        elif humidity < 40:          r_parts.append("dry air")
        elif humidity > 70:          r_parts.append("humid")
    if tvoc is not None:
        if tvoc < 100:               r_parts.append("fresh air")
        elif tvoc < 150:             r_parts.append("moderate TVOC")
        else:                        r_parts.append("high TVOC")

    # --- recovery factors ---
    v_parts = []
    if temp is not None:
        if 18 <= temp <= 22:         v_parts.append("restful temp")
        elif temp > 24:              v_parts.append("warm for rest")
        elif temp < 17:              v_parts.append("cool")
    if humidity is not None:
        if 45 <= humidity <= 65:     v_parts.append("good humidity")
        elif humidity < 40:          v_parts.append("dry room")
    if motion:                       v_parts.append("recent activity")
    elif tvoc is not None and tvoc < 100:
                                     v_parts.append("quiet, clean air")

    # --- air strain factors ---
    s_parts = []
    if tvoc is not None:
        if tvoc < 50:                s_parts.append(f"TVOC {int(tvoc)} ppb")
        elif tvoc < 100:             s_parts.append(f"TVOC ok ({int(tvoc)})")
        elif tvoc < 150:             s_parts.append(f"TVOC moderate ({int(tvoc)})")
        else:                        s_parts.append(f"TVOC high ({int(tvoc)})")
    if eco2 is not None:
        if eco2 < 800:               s_parts.append(f"CO₂ {int(eco2)} ppm")
        elif eco2 < 1200:            s_parts.append(f"CO₂ elevated ({int(eco2)})")
        else:                        s_parts.append(f"CO₂ high ({int(eco2)})")

    def _join(parts):
        return "  ·  ".join(parts) if parts else ""

    return {
        "readiness_why": _join(r_parts),
        "recovery_why":  _join(v_parts),
        "strain_why":    _join(s_parts),
    }


# ---------------------------------------------------------------------------
# Trend arrows — compare current score to the rolling 1h average
# ---------------------------------------------------------------------------

def score_trend(
    current: int | None,
    df: pd.DataFrame,
    col: str,
) -> tuple[str, str, str]:
    """
    Return (arrow_glyph, delta_label, color) comparing current value to the
    1-hour rolling average in the history DataFrame.

    If data is insufficient, returns ('', '', '#556677').
    """
    if current is None or df is None or df.empty or col not in df.columns:
        return "", "", "#556677"

    try:
        cutoff = df["timestamp"].max() - pd.Timedelta(hours=1)
        recent = df[df["timestamp"] >= cutoff][col].dropna()
        if recent.empty:
            return "", "", "#556677"
        avg = recent.mean()
        delta = int(round(current - avg))
        if abs(delta) < 2:
            return "→", "stable", "#556677"
        if delta > 0:
            return "↑", f"+{delta}", "#3DFF8A"
        return "↓", str(delta), "#FF8844"
    except Exception:
        return "", "", "#556677"


# ---------------------------------------------------------------------------
# Daily Room Story — 2–4 sentence narrative from history DataFrame
# ---------------------------------------------------------------------------

def daily_story(df: pd.DataFrame) -> list[str]:
    """
    Derive 2–4 readable sentences about how the room performed over the window.
    Returns a list of sentences (each rendered as a bullet).
    """
    if df is None or df.empty:
        return []

    sentences = []

    # 1. Dominant room state
    if "room_state" in df.columns:
        counts = df["room_state"].value_counts(normalize=True)
        top_state = counts.index[0] if not counts.empty else None
        top_pct = int(counts.iloc[0] * 100) if not counts.empty else 0
        if top_state and top_pct >= 30:
            sentences.append(
                f"The room was **{top_state}** for {top_pct}% of the recorded window."
            )
            if len(counts) > 1:
                second = counts.index[1]
                second_pct = int(counts.iloc[1] * 100)
                if second_pct >= 15:
                    sentences.append(
                        f"Conditions shifted to **{second}** for another {second_pct}%."
                    )

    # 2. Average readiness
    if "room_readiness" in df.columns:
        avg_r = int(df["room_readiness"].mean())
        if avg_r >= 75:
            sentences.append(f"Room Readiness averaged **{avg_r}** — well-supported for presence and focus.")
        elif avg_r >= 55:
            sentences.append(f"Room Readiness averaged **{avg_r}** — moderate support throughout.")
        else:
            sentences.append(f"Room Readiness averaged **{avg_r}** — room conditions were below ideal.")

    # 3. Air strain peak
    if "air_strain" in df.columns:
        peak_strain = int(df["air_strain"].max())
        peak_time_row = df.loc[df["air_strain"].idxmax()]
        try:
            peak_time = peak_time_row["timestamp"].strftime("%H:%M")
        except Exception:
            peak_time = None
        if peak_strain >= 60:
            loc = f" at {peak_time}" if peak_time else ""
            sentences.append(f"Air strain peaked at **{peak_strain}**{loc} — ventilation would have helped.")
        elif peak_strain < 20:
            sentences.append("Air strain stayed low throughout — air quality was consistently fresh.")

    # 4. Humidity issue periods
    if "indoor_humidity" in df.columns:
        dry_pct = int((df["indoor_humidity"] < 40).mean() * 100)
        if dry_pct >= 20:
            sentences.append(
                f"Dry air conditions (humidity below 40%) were present for {dry_pct}% of the window."
            )
        elif dry_pct == 0:
            sentences.append("Humidity stayed within the comfort range throughout.")

    # 5. Recovery evening peak
    if "recovery_score" in df.columns and "timestamp" in df.columns:
        try:
            evening = df[df["timestamp"].dt.hour >= 20]
            if not evening.empty:
                eve_avg = int(evening["recovery_score"].mean())
                if eve_avg >= 70:
                    sentences.append(
                        f"Recovery conditions strengthened in the evening (avg **{eve_avg}**)."
                    )
        except Exception:
            pass

    return sentences[:5]


# ---------------------------------------------------------------------------
# Outdoor suitability — coaching line for the weather panel
# ---------------------------------------------------------------------------

def outdoor_suitability(row: dict) -> str:
    """Return a one-line suitability hint for going outside."""
    temp = row.get("outdoor_temp")
    desc = (row.get("outdoor_weather") or "").lower()

    if temp is None:
        return "Outdoor data unavailable."

    bad_weather = any(w in desc for w in ("rain", "storm", "thunder", "snow", "drizzle"))

    if bad_weather:
        return f"Outdoor conditions unfavourable ({desc})."
    if temp < 8:
        return f"Cold outside ({temp:.0f}°C) — dress warmly for a break."
    if 10 <= temp <= 22:
        return f"Good outdoor conditions ({temp:.0f}°C) — suitable for a short break."
    if temp > 28:
        return f"Warm outside ({temp:.0f}°C) — avoid midday heat."
    return f"Outdoor temp {temp:.0f}°C — conditions are acceptable."

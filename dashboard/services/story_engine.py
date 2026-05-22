"""
Daily Room Story — pure functions, no Streamlit calls.
Returns DailyRoomStory contract (services/contracts.py).
"""

from __future__ import annotations
from datetime import datetime, timezone
import pandas as pd

from .contracts import DailyRoomStory, LatestRoomState


# ---------------------------------------------------------------------------
# 3.5  Build DailyRoomStory contract from history DataFrame
# ---------------------------------------------------------------------------

def to_daily_story(df: pd.DataFrame, device_id: str = "") -> DailyRoomStory | None:
    """
    Build a DailyRoomStory from a chart-ready DataFrame (series_to_df output).
    Returns None if the DataFrame is empty or missing required columns.
    """
    if df is None or df.empty:
        return None

    headline, bullets = _story_parts(df)
    if not headline:
        return None

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        date_str = df["timestamp"].max().strftime("%Y-%m-%d")
    except Exception:
        pass

    return DailyRoomStory(
        date=date_str,
        headline=headline,
        bullets=bullets[:4],
        summary_type="daily_story",
    )


def _story_parts(df: pd.DataFrame) -> tuple[str, list[str]]:
    """Return (headline, bullets) from history DataFrame."""
    headline = ""
    bullets: list[str] = []

    # --- headline from dominant state ---
    if "room_state" in df.columns:
        counts = df["room_state"].value_counts(normalize=True)
        if not counts.empty:
            top_state = counts.index[0]
            top_pct   = int(counts.iloc[0] * 100)
            if top_pct >= 30:
                if top_pct >= 95:
                    headline = f"Your room stayed {top_state.lower()} for the entire recorded window."
                else:
                    headline = f"Your room was {top_state.lower()} for {top_pct}% of the window."

    if not headline and "room_readiness" in df.columns:
        avg_r = int(df["room_readiness"].mean())
        headline = (
            f"Room Readiness averaged {avg_r} — well-supported." if avg_r >= 75 else
            f"Room Readiness averaged {avg_r} — moderate conditions." if avg_r >= 55 else
            f"Room Readiness averaged {avg_r} — conditions were below ideal."
        )

    # --- secondary state bullet ---
    if "room_state" in df.columns:
        counts = df["room_state"].value_counts(normalize=True)
        if len(counts) > 1:
            second = counts.index[1]
            second_pct = int(counts.iloc[1] * 100)
            if second_pct >= 15:
                bullets.append(f"Conditions shifted to {second.lower()} for another {second_pct}%.")

    # --- readiness bullet ---
    if "room_readiness" in df.columns:
        avg_r = int(df["room_readiness"].mean())
        if avg_r >= 75:
            bullets.append(f"Room Readiness averaged {avg_r} — well-supported for presence and focus.")
        elif avg_r < 55:
            bullets.append(f"Room Readiness averaged {avg_r} — room conditions were below ideal.")

    # --- air strain bullet ---
    if "air_strain" in df.columns:
        peak_strain = int(df["air_strain"].max())
        peak_time_row = df.loc[df["air_strain"].idxmax()]
        try:
            peak_time = peak_time_row["timestamp"].strftime("%H:%M")
        except Exception:
            peak_time = None
        if peak_strain >= 60:
            loc = f" at {peak_time}" if peak_time else ""
            bullets.append(f"Air strain peaked at {peak_strain}{loc} — ventilation would have helped.")
        elif peak_strain < 20:
            bullets.append("Air strain stayed low throughout — air quality was consistently fresh.")

    # --- humidity bullet ---
    if "indoor_humidity" in df.columns:
        dry_pct = int((df["indoor_humidity"] < 40).mean() * 100)
        if dry_pct >= 20:
            bullets.append(f"Dry air (below 40%) was present for {dry_pct}% of the window.")
        elif dry_pct == 0:
            bullets.append("Humidity stayed within the comfort range throughout.")

    # --- recovery evening bullet ---
    if "recovery_score" in df.columns and "timestamp" in df.columns:
        try:
            evening = df[df["timestamp"].dt.hour >= 20]
            if not evening.empty:
                eve_avg = int(evening["recovery_score"].mean())
                if eve_avg >= 70:
                    bullets.append(f"Recovery conditions improved after 20:00 (avg {eve_avg}).")
        except Exception:
            pass

    return headline, bullets


# ---------------------------------------------------------------------------
# Outdoor suitability coaching line
# ---------------------------------------------------------------------------

def outdoor_suitability(lrs: "LatestRoomState | dict") -> str:
    """Return a one-line suitability hint for going outside."""
    if "outdoor" in lrs:
        outdoor = lrs.get("outdoor") or {}
        temp = outdoor.get("temperature_c")
        desc = (outdoor.get("weather_main") or "").lower()
    else:
        temp = lrs.get("outdoor_temp")
        desc = (lrs.get("outdoor_weather") or "").lower()

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

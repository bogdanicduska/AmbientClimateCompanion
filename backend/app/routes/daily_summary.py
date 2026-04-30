"""
GET /api/v1/daily-summary?device_id=<id>&date=<yyyy-mm-dd>

Returns a DailyRoomStory for a given device and calendar date.
If date is omitted, defaults to today UTC.
"""

from datetime import datetime, timezone, date as date_type
from flask import Blueprint, jsonify, request, current_app

from app.services.bigquery_service import get_history
from app.services.room_metrics_service import enrich_row
from app.utils.logger import get_logger

daily_summary_bp = Blueprint("daily_summary", __name__)
logger = get_logger(__name__)


@daily_summary_bp.get("/daily-summary")
def daily_summary():
    device_id = request.args.get("device_id")
    if not device_id:
        return jsonify({"success": False, "message": "device_id is required"}), 400

    date_str = request.args.get("date")
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"success": False, "message": "date must be yyyy-mm-dd"}), 400
    else:
        target_date = datetime.now(timezone.utc).date()

    try:
        # Fetch up to 48h so we capture the full requested day even with timezone offsets
        records = [enrich_row(r) for r in get_history(device_id, current_app.config, hours=48)]
        story   = _build_story(records, target_date, device_id)
        return jsonify({"success": True, "data": story}), 200
    except Exception:
        current_app.logger.exception(f"daily-summary failed for {device_id}")
        return jsonify({"success": False, "message": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# Story builder
# ---------------------------------------------------------------------------

def _build_story(records: list[dict], target_date: date_type, device_id: str) -> dict:
    # Filter to the requested calendar day (UTC)
    day_rows = []
    for r in records:
        ts = r.get("timestamp", "")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.date() == target_date:
                day_rows.append(r)
        except Exception:
            continue

    if not day_rows:
        return {
            "date":         target_date.isoformat(),
            "headline":     "No data recorded for this date.",
            "bullets":      [],
            "summary_type": "daily_story",
        }

    headline = _headline(day_rows)
    bullets  = _bullets(day_rows)

    return {
        "date":         target_date.isoformat(),
        "headline":     headline,
        "bullets":      bullets[:4],
        "summary_type": "daily_story",
    }


def _headline(rows: list[dict]) -> str:
    state_counts: dict[str, int] = {}
    for r in rows:
        s = r.get("room_state", "")
        if s:
            state_counts[s] = state_counts.get(s, 0) + 1
    if not state_counts:
        return "Room was active today."
    top_state = max(state_counts, key=lambda k: state_counts[k])
    pct = int(state_counts[top_state] / len(rows) * 100)
    if pct >= 30:
        return f"Today your room was {top_state.lower()} for {pct}% of the day."
    avg_r = int(sum(r.get("readiness_score", r.get("room_readiness", 0)) for r in rows) / len(rows))
    if avg_r >= 75:
        return f"Today's room readiness averaged {avg_r} — a good day overall."
    return f"Today's room readiness averaged {avg_r}."


def _bullets(rows: list[dict]) -> list[str]:
    bullets = []
    n = len(rows)

    # Air strain peak
    strains = [r.get("air_strain_score", r.get("air_strain", 0)) or 0 for r in rows]
    peak_s  = max(strains) if strains else 0
    if peak_s >= 60:
        bullets.append(f"Air strain peaked at {peak_s} — ventilation would have helped.")
    elif peak_s < 20:
        bullets.append("Air strain stayed low throughout — air quality was consistently fresh.")

    # Readiness
    readiness_vals = [r.get("readiness_score", r.get("room_readiness", 0)) or 0 for r in rows]
    avg_r = int(sum(readiness_vals) / len(readiness_vals)) if readiness_vals else 0
    if avg_r >= 75:
        bullets.append(f"Room Readiness averaged {avg_r} — well-supported for presence and focus.")
    elif avg_r < 55:
        bullets.append(f"Room Readiness averaged {avg_r} — conditions were below ideal.")

    # Dry air
    hums = [r.get("indoor_humidity") for r in rows if r.get("indoor_humidity") is not None]
    if hums:
        dry_pct = int(sum(1 for h in hums if h < 40) / len(hums) * 100)
        if dry_pct >= 20:
            bullets.append(f"Dry air (below 40%) was present for {dry_pct}% of the day.")
        elif dry_pct == 0:
            bullets.append("Humidity stayed within the comfort range throughout the day.")

    # Evening recovery
    eve_rows = []
    for r in rows:
        ts = r.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.hour >= 20:
                eve_rows.append(r)
        except Exception:
            pass
    if eve_rows:
        eve_rec = [r.get("recovery_score", 0) or 0 for r in eve_rows]
        eve_avg = int(sum(eve_rec) / len(eve_rec))
        if eve_avg >= 70:
            bullets.append(f"Recovery conditions improved after 20:00 (avg {eve_avg}).")

    return bullets

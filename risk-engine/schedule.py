"""
F1 schedule for lock/unfreeze logic. Uses same source as frontend (Ergast API).
- Hard lock at Q1 start: once Q1 begins, that round's team_picks must never change.
- Unfreeze after race: assume race ends 2 hours after race start; only then can users lock in for the next round.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
import requests

SCHEDULE_URL = "https://api.jolpi.ca/ergast/f1/current.json"
RACE_DURATION_HOURS = 2

# In-memory cache: (schedule_list, fetched_at). Refetch after 15 minutes.
_cache: Optional[tuple[list[dict], datetime]] = None
_CACHE_TTL = timedelta(minutes=15)


def _parse_utc(date_str: str, time_str: str) -> Optional[datetime]:
    """Parse Ergast date (YYYY-MM-DD) and time (HH:MM:SSZ) to UTC datetime."""
    if not date_str:
        return None
    time_part = (time_str or "00:00:00").replace("Z", "").strip()
    try:
        dt = datetime.fromisoformat(f"{date_str}T{time_part}+00:00")
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return datetime.fromisoformat(f"{date_str}T00:00:00+00:00")


def fetch_schedule() -> list[dict]:
    """
    Fetch current season schedule. Each item: {
        "round": str,
        "qualifying_utc": datetime (Q1 start – lock at this time),
        "race_start_utc": datetime,
        "race_end_utc": datetime (race_start + 2h – unfreeze after this for next round),
        "race_name": str,
    }
    """
    global _cache
    now = datetime.now(timezone.utc)
    if _cache is not None and (now - _cache[1]) < _CACHE_TTL:
        return _cache[0]

    try:
        r = requests.get(SCHEDULE_URL, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return _cache[0] if _cache else []

    races_raw = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    out = []
    for race in races_raw:
        round_id = str(race.get("round", ""))
        if not round_id:
            continue
        date_str = race.get("date")
        time_str = race.get("time")
        qual = race.get("Qualifying") or {}
        q_date = qual.get("date")
        q_time = qual.get("time")

        qualifying_utc = _parse_utc(q_date, q_time) if q_date else None
        race_start_utc = _parse_utc(date_str, time_str) if date_str else None
        race_end_utc = (race_start_utc + timedelta(hours=RACE_DURATION_HOURS)) if race_start_utc else None

        out.append({
            "round": round_id,
            "qualifying_utc": qualifying_utc,
            "race_start_utc": race_start_utc,
            "race_end_utc": race_end_utc,
            "race_name": race.get("raceName") or f"Round {round_id}",
        })

    out.sort(key=lambda x: (x["qualifying_utc"] or datetime.max.replace(tzinfo=timezone.utc)))
    _cache = (out, now)
    return out


def get_round_info(schedule: list[dict], round_id: str) -> Optional[dict]:
    """Get schedule entry for a round. round_id can be str or int."""
    rid = str(round_id)
    for r in schedule:
        if r["round"] == rid:
            return r
    return None


def is_round_locked(round_id: str, now: Optional[datetime] = None) -> bool:
    """
    True if this round is locked: Q1 has started. Team picks for this round must not be changed.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    schedule = fetch_schedule()
    info = get_round_info(schedule, round_id)
    if not info or not info.get("qualifying_utc"):
        return False
    return now >= info["qualifying_utc"]


def is_round_closed_by_race(round_id: str, now: Optional[datetime] = None) -> bool:
    """True if race has ended (race_start + 2h passed). Used for 'unfreeze' – after this, next round is open."""
    if now is None:
        now = datetime.now(timezone.utc)
    schedule = fetch_schedule()
    info = get_round_info(schedule, round_id)
    if not info or not info.get("race_end_utc"):
        return False
    return now >= info["race_end_utc"]


def can_edit_round(round_id: str, now: Optional[datetime] = None) -> tuple[bool, str]:
    """
    Can we create/update TeamPick for this round?
    - Not allowed if round is locked (Q1 already started).
    - Not allowed if round is not yet open (e.g. round 2 while race 1 not over).
    Returns (allowed, reason_message).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    schedule = fetch_schedule()
    if not schedule:
        return True, ""  # No schedule: allow (e.g. API down)

    info = get_round_info(schedule, round_id)
    if not info:
        return False, "Round not found in schedule."

    # Hard lock: Q1 started – never allow edits to this round's picks
    if info.get("qualifying_utc") and now >= info["qualifying_utc"]:
        return False, "Team lock is closed. Picks freeze at Q1 and cannot be changed until the next round opens after the race."

    # Unfreeze: for round 1, always allow until Q1. For round N>1, allow only after previous race ended (race + 2h)
    try:
        idx = next(i for i, r in enumerate(schedule) if r["round"] == str(round_id))
    except StopIteration:
        return False, "Round not found."
    if idx > 0:
        prev = schedule[idx - 1]
        prev_end = prev.get("race_end_utc")
        if prev_end and now < prev_end:
            return False, "Previous race has not finished yet. You can lock in for this round after the race ends (about 2 hours after race start)."
    return True, ""


def get_next_editable_round(now: Optional[datetime] = None) -> Optional[str]:
    """First round that is currently open for editing (not locked, and previous race ended if any)."""
    if now is None:
        now = datetime.now(timezone.utc)
    schedule = fetch_schedule()
    for r in schedule:
        allowed, _ = can_edit_round(r["round"], now)
        if allowed:
            return r["round"]
    return None


def get_lock_status(round_id: str, now: Optional[datetime] = None) -> dict:
    """
    Full lock status for a round: locked (Q1 passed), closed (race ended), next_unfreeze_utc (for display).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    schedule = fetch_schedule()
    info = get_round_info(schedule, round_id)
    locked = is_round_locked(round_id, now)
    race_ended = is_round_closed_by_race(round_id, now)
    can_edit, reason = can_edit_round(round_id, now)
    next_unfreeze = None
    if info and not race_ended and info.get("race_end_utc"):
        next_unfreeze = info["race_end_utc"].isoformat()
    return {
        "round": str(round_id),
        "locked": locked,
        "race_ended": race_ended,
        "can_edit": can_edit,
        "reason": reason or None,
        "next_unfreeze_utc": next_unfreeze,
    }

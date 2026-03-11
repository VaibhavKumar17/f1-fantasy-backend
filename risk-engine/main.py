from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.drivers import get_current_drivers
from routers.constructors import get_constructors
from database import engine
import models
from fastapi import Body
from database import SessionLocal
from models import Team, TeamPick, RaceScore
from scoring import get_last_race_results, get_race_results, calculate_team_score
from schedule import can_edit_round, get_lock_status, fetch_schedule, get_next_editable_round
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Allow frontend to call this API (any localhost port for dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/race-results")
def race_results():
    return get_last_race_results()

@app.get("/teams")
def get_teams():

    db = SessionLocal()

    teams = db.query(Team).all()

    return teams
@app.get("/constructors")
def constructors():
    return {"constructors": get_constructors()}


@app.post("/create-team")
def create_team(team: dict = Body(...)):
    username = team.get("username")
    drivers = team.get("drivers")
    constructors_list = team.get("constructors")
    race_round = team.get("race_round")
    if not username or not drivers:
        return {"error": "username and drivers are required"}
    if not isinstance(drivers, list) or len(drivers) != 5:
        return {"error": "drivers must be a list of 5 driver ids"}
    if len(set(drivers)) != 5:
        return {"error": "Drivers must be unique"}
    if not constructors_list or not isinstance(constructors_list, list) or len(constructors_list) != 2:
        return {"error": "constructors must be a list of 2 constructor ids"}
    if len(set(constructors_list)) != 2:
        return {"error": "Constructors must be different"}

    con1, con2 = constructors_list[0], constructors_list[1]

    db = SessionLocal()
    try:
        existing = db.query(Team).filter(Team.username == username).first()
        if existing:
            existing.driver1, existing.driver2, existing.driver3, existing.driver4, existing.driver5 = drivers
            existing.constructor1, existing.constructor2 = con1, con2
            db.commit()
        else:
            new_team = Team(
                username=username,
                driver1=drivers[0],
                driver2=drivers[1],
                driver3=drivers[2],
                driver4=drivers[3],
                driver5=drivers[4],
                constructor1=con1,
                constructor2=con2,
            )
            db.add(new_team)
            db.commit()

        if race_round:
            round_str = str(race_round)
            # 1) Leaderboard already stored for this round – no changes
            closed = db.query(RaceScore).filter(RaceScore.race_round == round_str).first() is not None
            if closed:
                db.close()
                return {"error": "This round is closed. You cannot change your team pick after the race has been closed."}
            # 2) Hard lock: Q1 started – team_picks for this round must never change. Unfreeze only after race (race + 2h).
            allowed, reason = can_edit_round(round_str)
            if not allowed:
                db.close()
                return {"error": reason or "Team lock is closed for this round."}

            pick = db.query(TeamPick).filter(
                TeamPick.username == username,
                TeamPick.race_round == round_str,
            ).first()
            if pick:
                pick.driver1, pick.driver2, pick.driver3, pick.driver4, pick.driver5 = drivers
                pick.constructor1, pick.constructor2 = con1, con2
            else:
                db.add(TeamPick(
                    username=username,
                    race_round=round_str,
                    driver1=drivers[0],
                    driver2=drivers[1],
                    driver3=drivers[2],
                    driver4=drivers[3],
                    driver5=drivers[4],
                    constructor1=con1,
                    constructor2=con2,
                ))
            db.commit()
        return {"message": "Team created successfully" if not existing else "Team updated successfully"}
    except Exception as e:
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()
@app.get("/leaderboard")
def leaderboard():
    """Season leaderboard: sum of points from all closed races. Fallback: last race with current teams."""
    db = SessionLocal()
    try:
        rows = db.query(RaceScore.race_round, RaceScore.username, RaceScore.points).all()
        if rows:
            totals = {}
            for (_, username, points) in rows:
                totals[username] = totals.get(username, 0) + points
            out = [{"username": u, "points": p} for u, p in totals.items()]
            out.sort(key=lambda x: x["points"], reverse=True)
            for i, t in enumerate(out):
                t["rank"] = i + 1
            return out
        race_results = get_last_race_results()
        if isinstance(race_results, dict):
            teams = db.query(Team).all()
            out = []
            for team in teams:
                drivers = [team.driver1, team.driver2, team.driver3, team.driver4, team.driver5]
                score = calculate_team_score(drivers, race_results)
                out.append({"username": team.username, "points": score})
            out.sort(key=lambda x: x["points"], reverse=True)
            for i, t in enumerate(out):
                t["rank"] = i + 1
            return out
        return []
    finally:
        db.close()


@app.get("/leaderboard/season")
def leaderboard_season():
    """Cumulative season standings from stored race scores. Fallback: last race + current teams so teams show before any race is closed."""
    db = SessionLocal()
    try:
        # Group by (race_round, username) to avoid any accidental duplicates before summing per user.
        rows = db.query(RaceScore.race_round, RaceScore.username, RaceScore.points).all()
        if rows:
            per_round_user = {}
            for (round_id, username, points) in rows:
                key = (str(round_id), username)
                # Keep the max points per round/user in case of duplicates
                per_round_user[key] = max(per_round_user.get(key, 0), points)

            totals = {}
            for (_, username), points in per_round_user.items():
                totals[username] = totals.get(username, 0) + points

            out = [{"username": u, "points": p} for u, p in totals.items()]
            out.sort(key=lambda x: x["points"], reverse=True)
            for i, t in enumerate(out):
                t["rank"] = i + 1
            return out
        race_results = get_last_race_results()
        if isinstance(race_results, dict) and "message" not in race_results:
            teams = db.query(Team).all()
            out = []
            for team in teams:
                drivers = [team.driver1, team.driver2, team.driver3, team.driver4, team.driver5]
                score = calculate_team_score(drivers, race_results)
                out.append({"username": team.username, "points": score})
            out.sort(key=lambda x: x["points"], reverse=True)
            for i, t in enumerate(out):
                t["rank"] = i + 1
            return out
        teams = db.query(Team).all()
        out = [{"username": t.username, "points": 0, "rank": i + 1} for i, t in enumerate(teams)]
        return out
    finally:
        db.close()


@app.get("/leaderboard/race/{round_id}")
def leaderboard_race(round_id: str):
    """Leaderboard for a specific race.

    Primary source: stored RaceScore rows (after /close-race is called).
    Fallback: if no stored scores yet, compute on the fly from TeamPick and live race results.
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(RaceScore)
            .filter(RaceScore.race_round == str(round_id))
            .order_by(RaceScore.points.desc())
            .all()
        )
        if rows:
            out = [{"username": r.username, "points": r.points, "rank": i + 1} for i, r in enumerate(rows)]
            return out

        # Fallback: no stored scores yet – use TeamPick and (if available) live results
        picks = db.query(TeamPick).filter(TeamPick.race_round == str(round_id)).all()
        if not picks:
            return []

        results = get_race_results(str(round_id))
        scores = []
        for pick in picks:
            drivers = [pick.driver1, pick.driver2, pick.driver3, pick.driver4, pick.driver5]
            points = calculate_team_score(drivers, results) if results else 0
            scores.append({"username": pick.username, "points": points})

        scores.sort(key=lambda x: x["points"], reverse=True)
        for i, s in enumerate(scores):
            s["rank"] = i + 1
        return scores
    finally:
        db.close()


@app.get("/schedule")
def api_schedule():
    """Current season schedule with lock/unfreeze times (Q1 = lock, race_end = race_start + 2h). For display and debugging."""
    schedule = fetch_schedule()
    return {
        "races": [
            {
                "round": r["round"],
                "race_name": r["race_name"],
                "qualifying_utc": r["qualifying_utc"].isoformat() if r.get("qualifying_utc") else None,
                "race_start_utc": r["race_start_utc"].isoformat() if r.get("race_start_utc") else None,
                "race_end_utc": r["race_end_utc"].isoformat() if r.get("race_end_utc") else None,
            }
            for r in schedule
        ],
        "next_editable_round": get_next_editable_round(),
    }


@app.get("/lock-status/{round_id}")
def lock_status(round_id: str):
    """
    Lock status for a round. Uses schedule: locked at Q1, unfreeze after race (race start + 2h).
    - locked: Q1 has started – team_picks for this round cannot be changed.
    - race_ended: race is over (2h after start); next round becomes editable.
    - closed: leaderboard stored (RaceScore); round fully finalised.
    """
    db = SessionLocal()
    try:
        rid = str(round_id)
        status = get_lock_status(rid)
        closed = db.query(RaceScore).filter(RaceScore.race_round == rid).first() is not None
        status["closed"] = closed
        if closed:
            status["can_edit"] = False
            status["reason"] = "Round closed; leaderboard stored."
        return status
    finally:
        db.close()


@app.get("/leaderboard/history")
def leaderboard_history():
    """List of past races with leaderboards (round, race_name).

    Primary source: stored RaceScore rows (after /close-race).
    Fallback: if none stored yet, infer rounds from TeamPick so the race tab can still show \"live\" leaderboards.
    """
    db = SessionLocal()
    try:
        rows = db.query(RaceScore.race_round, RaceScore.race_name).distinct().all()
        seen = set()
        out = []
        for (rd, name) in rows:
            if rd not in seen:
                seen.add(rd)
                out.append({"round": rd, "race_name": name or f"Round {rd}"})

        # Fallback: if no stored race scores yet, infer from team picks
        if not out:
            pick_rounds = db.query(TeamPick.race_round).distinct().all()
            for (rd,) in pick_rounds:
                if rd:
                    out.append({"round": rd, "race_name": f"Round {rd}"})

        out.sort(key=lambda x: int(x["round"]) if str(x["round"]).isdigit() else 0)
        return out
    finally:
        db.close()


@app.post("/close-race")
def close_race(body: dict = Body(...)):
    """Store leaderboard for a race after the weekend. Call this after the RACE finishes (not after qualifying).
    Body: { "round": "1", "race_name": "Australian GP" }.
    Once closed, team picks for that round cannot be changed and the round appears in leaderboard history."""
    db = SessionLocal()
    round_id = body.get("round")
    race_name = body.get("race_name") or f"Round {round_id}"
    if not round_id:
        db.close()
        return {"error": "round is required"}
    results = get_race_results(round_id)
    if not results:
        db.close()
        return {"error": "No results for this round yet"}
    try:
        # Overwrite any existing scores for this round so closing the same race twice doesn't double-count.
        db.query(RaceScore).filter(RaceScore.race_round == str(round_id)).delete()
        picks = db.query(TeamPick).filter(TeamPick.race_round == str(round_id)).all()
        for pick in picks:
            drivers = [pick.driver1, pick.driver2, pick.driver3, pick.driver4, pick.driver5]
            points = calculate_team_score(drivers, results)
            db.add(RaceScore(race_round=str(round_id), race_name=race_name, username=pick.username, points=points))
        db.commit()
        return {"message": f"Race {round_id} closed", "entries": len(picks)}
    except Exception as e:
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()


models.Base.metadata.create_all(bind=engine)
@app.get("/drivers")
def get_drivers():
    return {"drivers": get_current_drivers()}
app.mount("/", StaticFiles(directory="static", html=True), name="static")
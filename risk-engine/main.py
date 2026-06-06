from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from routers.drivers import get_current_drivers
from routers.constructors import get_constructors
from database import engine
import models
from fastapi import Body
from database import SessionLocal
from models import Team, TeamPick, RaceScore
from scoring import get_last_race_results, get_race_results, calculate_team_score, calculate_constructor_score
from schedule import can_edit_round, get_lock_status, fetch_schedule, get_next_editable_round, is_round_locked
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
    driver_results, constructor_points = get_last_race_results()
    return {"drivers": driver_results, "constructors": constructor_points}

@app.get("/race-results/{round_id}")
def race_results_for_round(round_id: str):
    driver_results, constructor_points = get_race_results(round_id)
    return {"drivers": driver_results or {}, "constructors": constructor_points or {}}

@app.get("/teams")
def get_teams():

    db = SessionLocal()

    teams = db.query(Team).all()

    return teams
@app.get("/constructors")
def constructors():
    return {"constructors": get_constructors()}


def get_user_team_for_round(db, username: str, round_id: str):
    """
    Resolve the team pick for a user for a given round.
    If the round is locked:
        Find the most recent TeamPick for this user for any round <= round_id.
        Do NOT fall back to the current active team (which might be from a later round).
    If the round is not locked:
        Return the global Team entry (if it exists).
    """
    rid_int = int(round_id) if round_id.isdigit() else 0
    locked = is_round_locked(round_id)
    
    if not locked:
        team = db.query(Team).filter(Team.username == username).first()
        if team:
            return {
                "username": username,
                "race_round": round_id,
                "drivers": [team.driver1, team.driver2, team.driver3, team.driver4, team.driver5],
                "constructors": [team.constructor1, team.constructor2],
            }
        return None
    else:
        picks = db.query(TeamPick).filter(TeamPick.username == username).all()
        valid_picks = []
        for p in picks:
            p_round_int = int(p.race_round) if p.race_round.isdigit() else 0
            if p_round_int <= rid_int:
                valid_picks.append((p_round_int, p))
        if valid_picks:
            valid_picks.sort(key=lambda x: x[0], reverse=True)
            best_pick = valid_picks[0][1]
            return {
                "username": username,
                "race_round": round_id,
                "drivers": [best_pick.driver1, best_pick.driver2, best_pick.driver3, best_pick.driver4, best_pick.driver5],
                "constructors": [best_pick.constructor1, best_pick.constructor2],
            }
        return None

@app.post("/create-team")
def create_team(team: dict = Body(...)):
    username = team.get("username")
    drivers = team.get("drivers")
    constructors_list = team.get("constructors")
    race_round = team.get("race_round")
    if not username or not drivers:
        raise HTTPException(status_code=400, detail="username and drivers are required")
    if not isinstance(drivers, list) or len(drivers) != 5:
        raise HTTPException(status_code=400, detail="drivers must be a list of 5 driver ids")
    if len(set(drivers)) != 5:
        raise HTTPException(status_code=400, detail="Drivers must be unique")
    if not constructors_list or not isinstance(constructors_list, list) or len(constructors_list) != 2:
        raise HTTPException(status_code=400, detail="constructors must be a list of 2 constructor ids")
    if len(set(constructors_list)) != 2:
        raise HTTPException(status_code=400, detail="Constructors must be different")

    con1, con2 = constructors_list[0], constructors_list[1]

    # Determine the target round securely
    if race_round:
        round_str = str(race_round)
    else:
        round_str = get_next_editable_round()
        if not round_str:
            raise HTTPException(status_code=400, detail="No round is currently open for editing. Teams are locked during the weekend.")

    db = SessionLocal()
    try:
        # Check if the round is closed
        closed = db.query(RaceScore).filter(RaceScore.race_round == round_str).first() is not None
        if closed:
            raise HTTPException(status_code=400, detail="This round is closed. You cannot change your team pick after the race has been closed.")

        # Check if the round is locked
        allowed, reason = can_edit_round(round_str)
        if not allowed:
            raise HTTPException(status_code=400, detail=reason or "Team lock is closed for this round.")

        # Update global Team table (current active team)
        existing = db.query(Team).filter(Team.username == username).first()
        if existing:
            existing.driver1, existing.driver2, existing.driver3, existing.driver4, existing.driver5 = drivers
            existing.constructor1, existing.constructor2 = con1, con2
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

        # Update TeamPick for history reference
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
        return {"message": f"Team locked in successfully for Round {round_str}"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
@app.get("/leaderboard")
def leaderboard():
    """Season leaderboard: sum of points from all closed races."""
    db = SessionLocal()
    try:
        rows = db.query(RaceScore.race_round, RaceScore.username, RaceScore.points).all()
        totals = {}
        for (_, username, points) in rows:
            totals[username] = totals.get(username, 0) + (points or 0)
        out = [{"username": u, "points": p} for u, p in totals.items()]
        
        # Merge in all registered teams with 0 points if not present
        all_teams = db.query(Team).all()
        for team in all_teams:
            if not any(x["username"] == team.username for x in out):
                out.append({"username": team.username, "points": 0})
                
        out.sort(key=lambda x: x["points"], reverse=True)
        for i, t in enumerate(out):
            t["rank"] = i + 1
        return out
    finally:
        db.close()


@app.get("/leaderboard/season")
def leaderboard_season(type: str = "combined"):
    """Cumulative season standings. type: 'combined' (WDC + WCC), 'wdc' (drivers only), 'wcc' (constructors only)."""
    db = SessionLocal()
    try:
        if type == "wdc":
            query_col = RaceScore.driver_points
        elif type == "wcc":
            query_col = RaceScore.constructor_points
        else:
            query_col = RaceScore.points

        rows = db.query(RaceScore.race_round, RaceScore.username, query_col).all()
        per_round_user = {}
        for (round_id, username, points) in rows:
            key = (str(round_id), username)
            per_round_user[key] = max(per_round_user.get(key, 0), points or 0)

        totals = {}
        for (_, username), points in per_round_user.items():
            totals[username] = totals.get(username, 0) + (points or 0)

        out = [{"username": u, "points": p} for u, p in totals.items()]
        
        all_teams = db.query(Team).all()
        for team in all_teams:
            if not any(x["username"] == team.username for x in out):
                out.append({"username": team.username, "points": 0})
                
        out.sort(key=lambda x: x["points"], reverse=True)
        for i, t in enumerate(out):
            t["rank"] = i + 1
        return out
    finally:
        db.close()


@app.get("/leaderboard/race/{round_id}")
def leaderboard_race(round_id: str, type: str = "combined"):
    """Leaderboard for a specific race. type: 'combined' (WDC + WCC), 'wdc' (drivers only), 'wcc' (constructors only)."""
    db = SessionLocal()
    try:
        if type == "wdc":
            db_rows = db.query(RaceScore).filter(RaceScore.race_round == str(round_id)).all()
            db_rows.sort(key=lambda x: x.driver_points, reverse=True)
            out = [{"username": r.username, "points": r.driver_points, "rank": i + 1} for i, r in enumerate(db_rows)]
            if out:
                return out
        elif type == "wcc":
            db_rows = db.query(RaceScore).filter(RaceScore.race_round == str(round_id)).all()
            db_rows.sort(key=lambda x: x.constructor_points, reverse=True)
            out = [{"username": r.username, "points": r.constructor_points, "rank": i + 1} for i, r in enumerate(db_rows)]
            if out:
                return out
        else:
            db_rows = (
                db.query(RaceScore)
                .filter(RaceScore.race_round == str(round_id))
                .order_by(RaceScore.points.desc())
                .all()
            )
            out = [{"username": r.username, "points": r.points, "rank": i + 1} for i, r in enumerate(db_rows)]
            if out:
                return out

        all_teams = db.query(Team).all()
        driver_results, constructor_points = get_race_results(str(round_id))
        scores = []
        for t in all_teams:
            resolved = get_user_team_for_round(db, t.username, str(round_id))
            if resolved:
                drivers = resolved["drivers"]
                constructors = resolved["constructors"]
                driver_score = calculate_team_score(drivers, driver_results or {})
                constructor_score = calculate_constructor_score(constructors, constructor_points or {})
                if type == "wdc":
                    score = driver_score
                elif type == "wcc":
                    score = constructor_score
                else:
                    score = driver_score + constructor_score
                scores.append({"username": t.username, "points": score})

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


@app.get("/round-teams/{round_id}")
def round_teams(round_id: str, username: str | None = None):
    """
    Locked teams for a round.
    - Before Q1 lock: only returns the requesting user's team (if username is provided).
    - After Q1 lock: returns all teams for that round.
    """
    db = SessionLocal()
    try:
        rid = str(round_id)
        locked = is_round_locked(rid)
        
        # Get all usernames from Team table to resolve
        all_teams = db.query(Team).all()
        usernames = [t.username for t in all_teams]
        
        teams = []
        if not locked and username:
            # Before lock: only resolve the requesting user's team
            if username in usernames:
                resolved = get_user_team_for_round(db, username, rid)
                if resolved:
                    teams.append(resolved)
        elif locked:
            # After lock: resolve everyone's team
            for u in usernames:
                resolved = get_user_team_for_round(db, u, rid)
                if resolved:
                    teams.append(resolved)
                    
        return {"round": rid, "locked": locked, "teams": teams}
    finally:
        db.close()


@app.get("/leaderboard/history")
def leaderboard_history():
    """List of past races with leaderboards (round, race_name).
    Only returns rounds that actually have closed results stored in RaceScore.
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
        raise HTTPException(status_code=400, detail="round is required")
    driver_results, constructor_points = get_race_results(round_id)
    if not driver_results:
        db.close()
        raise HTTPException(status_code=400, detail="No results for this round yet")
    try:
        # Overwrite any existing scores for this round so closing the same race twice doesn't double-count.
        db.query(RaceScore).filter(RaceScore.race_round == str(round_id)).delete()
        
        # Resolve teams for all users for this round
        all_teams = db.query(Team).all()
        entries_count = 0
        for t in all_teams:
            resolved = get_user_team_for_round(db, t.username, str(round_id))
            if resolved:
                drivers = resolved["drivers"]
                constructors = resolved["constructors"]
                driver_score = calculate_team_score(drivers, driver_results or {})
                constructor_score = calculate_constructor_score(constructors, constructor_points or {})
                db.add(RaceScore(
                    race_round=str(round_id), 
                    race_name=race_name, 
                    username=t.username, 
                    points=driver_score + constructor_score,
                    driver_points=driver_score,
                    constructor_points=constructor_score
                ))
                entries_count += 1
        db.commit()
        return {"message": f"Race {round_id} closed", "entries": entries_count}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


models.Base.metadata.create_all(bind=engine)

@app.get("/drivers")
def get_drivers():
    return {"drivers": get_current_drivers()}

@app.get("/debug-db")
def debug_db():
    db = SessionLocal()
    try:
        teams = db.query(Team).all()
        picks = db.query(TeamPick).all()
        scores = db.query(RaceScore).all()
        return {
            "teams": [
                {
                    "id": t.id,
                    "username": t.username,
                    "drivers": [t.driver1, t.driver2, t.driver3, t.driver4, t.driver5],
                    "constructors": [t.constructor1, t.constructor2]
                }
                for t in teams
            ],
            "team_picks": [
                {
                    "id": p.id,
                    "username": p.username,
                    "race_round": p.race_round,
                    "drivers": [p.driver1, p.driver2, p.driver3, p.driver4, p.driver5],
                    "constructors": [p.constructor1, p.constructor2]
                }
                for p in picks
            ],
            "race_scores": [
                {
                    "id": s.id,
                    "race_round": s.race_round,
                    "race_name": s.race_name,
                    "username": s.username,
                    "points": s.points,
                    "driver_points": s.driver_points,
                    "constructor_points": s.constructor_points
                }
                for s in scores
            ]
        }
    finally:
        db.close()

def seed_and_backfill_historical_data():
    db = SessionLocal()
    try:
        # 1. Seed Rock profile if missing
        rock = db.query(Team).filter(Team.username == "Rock").first()
        if not rock:
            print("Seeding Rock user team...")
            db.add(Team(
                username="Rock",
                driver1="leclerc",
                driver2="antonelli",
                driver3="russell",
                driver4="alonso",
                driver5="colapinto",
                constructor1="mercedes",
                constructor2="audi"
            ))
            db.commit()

        # 2. Seed indianguru Round 1 pick if missing
        guru_r1 = db.query(TeamPick).filter(TeamPick.username == "indianguru", TeamPick.race_round == "1").first()
        if not guru_r1:
            print("Seeding indianguru Round 1 pick...")
            db.add(TeamPick(
                username="indianguru",
                race_round="1",
                driver1="russell",
                driver2="piastri",
                driver3="colapinto",
                driver4="perez",
                driver5="hadjar",
                constructor1="mercedes",
                constructor2="williams"
            ))

        # 3. Seed Rock Round 2 pick if missing
        rock_r2 = db.query(TeamPick).filter(TeamPick.username == "Rock", TeamPick.race_round == "2").first()
        if not rock_r2:
            print("Seeding Rock Round 2 pick...")
            db.add(TeamPick(
                username="Rock",
                race_round="2",
                driver1="leclerc",
                driver2="antonelli",
                driver3="russell",
                driver4="alonso",
                driver5="colapinto",
                constructor1="mercedes",
                constructor2="audi"
            ))

        # 4. Backfill Round 4 and 5 picks for users who registered (exist in Team table)
        all_teams = db.query(Team).all()
        for t in all_teams:
            # Backfill for rounds 4 and 5 if picks are missing
            for r in ["4", "5"]:
                existing_pick = db.query(TeamPick).filter(TeamPick.username == t.username, TeamPick.race_round == r).first()
                if not existing_pick:
                    print(f"Backfilling pick for {t.username} for Round {r} using active team...")
                    db.add(TeamPick(
                        username=t.username,
                        race_round=r,
                        driver1=t.driver1,
                        driver2=t.driver2,
                        driver3=t.driver3,
                        driver4=t.driver4,
                        driver5=t.driver5,
                        constructor1=t.constructor1,
                        constructor2=t.constructor2
                    ))
        db.commit()
    except Exception as e:
        print("Error during database seeding/backfilling:", e)
        db.rollback()
    finally:
        db.close()

# Database Schema upgrade & automatic recalculation on startup
def upgrade_db_schema_and_recalculate():
    import sqlalchemy
    db = SessionLocal()
    try:
        cursor = db.execute(sqlalchemy.text("PRAGMA table_info(race_scores)"))
        cols = [row[1] for row in cursor.fetchall()]
        if "driver_points" not in cols:
            print("Upgrading database schema for race_scores...")
            db.execute(sqlalchemy.text("DROP TABLE IF EXISTS race_scores"))
            db.commit()
            
            models.Base.metadata.create_all(bind=engine)
            print("Database schema upgraded successfully.")
            
        # Run seeding and backfilling
        seed_and_backfill_historical_data()
        
        # Deduplicate to prevent race condition double-counting
        db.execute(sqlalchemy.text("""
            DELETE FROM team_picks 
            WHERE id NOT IN (
                SELECT MAX(id) 
                FROM team_picks 
                GROUP BY username, race_round
            )
        """))
        db.execute(sqlalchemy.text("""
            DELETE FROM race_scores 
            WHERE id NOT IN (
                SELECT MAX(id) 
                FROM race_scores 
                GROUP BY username, race_round
            )
        """))
        db.commit()
        
        # Recalculate scores for any completed rounds that don't have entries in race_scores.
        rounds = db.query(TeamPick.race_round).distinct().all()
        for (round_str,) in rounds:
            if not round_str:
                continue
                
            # If scores already exist for this round, don't recalculate
            existing_count = db.query(RaceScore).filter(RaceScore.race_round == round_str).count()
            if existing_count > 0:
                print(f"Scores for Round {round_str} already exist. Skipping recalculation.")
                continue
                
            print(f"Recalculating scores for Round {round_str}...")
            driver_results, constructor_points = get_race_results(round_str)
            if not driver_results:
                print(f"Could not get race results for Round {round_str}. Skipping.")
                continue
                
            race_name = f"Round {round_str}"
            try:
                from schedule import fetch_schedule, get_round_info
                sch = fetch_schedule()
                info = get_round_info(sch, round_str)
                if info and info.get("race_name"):
                    race_name = info["race_name"]
            except Exception:
                pass
                
            picks = db.query(TeamPick).filter(models.TeamPick.race_round == round_str).all()
            for pick in picks:
                drivers = [pick.driver1, pick.driver2, pick.driver3, pick.driver4, pick.driver5]
                constructors = [pick.constructor1, pick.constructor2]
                
                driver_score = calculate_team_score(drivers, driver_results)
                constructor_score = calculate_constructor_score(constructors, constructor_points)
                
                db.add(RaceScore(
                    race_round=round_str,
                    race_name=race_name,
                    username=pick.username,
                    points=driver_score + constructor_score,
                    driver_points=driver_score,
                    constructor_points=constructor_score
                ))
            db.commit()
            print(f"Round {round_str} scores recalculated successfully.")
    except Exception as e:
        print("Error during database upgrade or recalculation:", e)
    finally:
        db.close()

upgrade_db_schema_and_recalculate()

app.mount("/", StaticFiles(directory="static", html=True), name="static")
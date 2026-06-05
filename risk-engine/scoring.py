POINTS = {
    1: 25,
    2: 18,
    3: 15,
    4: 12,
    5: 10,
    6: 8,
    7: 6,
    8: 4,
    9: 2,
    10: 1,
}
import requests


def normalize_driver_id(driver_id: str) -> str:
    """Map frontend driver ID to Ergast API driver ID."""
    if driver_id == "max_verstappen":
        return "verstappen"
    return driver_id


def denormalize_driver_id(driver_id: str) -> str:
    """Map Ergast API driver ID to frontend driver ID."""
    if driver_id == "verstappen":
        return "max_verstappen"
    return driver_id


def denormalize_constructor_id(c_id: str) -> str:
    """Map Ergast API constructor ID to frontend constructor ID."""
    c_id_lower = c_id.lower()
    if c_id_lower in ("red_bull", "redbull"):
        return "red_bull"
    if c_id_lower in ("rb", "racing_bulls", "racingbulls", "visa_cash_app_rb", "alphatauri"):
        return "rb"
    if c_id_lower in ("audi", "sauber", "kick_sauber", "kick", "stake"):
        return "audi"
    return c_id_lower


def _driver_points_for_position(position: int) -> int:
    return POINTS.get(position, 0)


def get_last_race_results():
    """
    Latest race results.
    Returns a tuple: (driver_results, constructor_points)
    - driver_results: dict driver_id -> finishing position (int)
    - constructor_points: dict constructor_id -> sum of driver points for that constructor
    """
    url = "https://api.jolpi.ca/ergast/f1/current/last/results.json"
    response = requests.get(url)
    data = response.json()
    races = data["MRData"]["RaceTable"]["Races"]
    if len(races) == 0:
        return {"message": "No race results available yet"}, {}
    results = races[0]["Results"]
    driver_results = {}
    constructor_points = {}
    for r in results:
        driver_id = r["Driver"]["driverId"]
        frontend_driver_id = denormalize_driver_id(driver_id)
        position = int(r["position"])
        driver_results[frontend_driver_id] = position
        
        constructor_id = r["Constructor"]["constructorId"]
        frontend_c_id = denormalize_constructor_id(constructor_id)
        pts = _driver_points_for_position(position)
        constructor_points[frontend_c_id] = constructor_points.get(frontend_c_id, 0) + pts
    return driver_results, constructor_points


def get_race_results(race_round):
    """
    Get results for a specific round (e.g. "1", "2").
    Returns a tuple (driver_results, constructor_points) or (None, None) if no results.
    """
    url = f"https://api.jolpi.ca/ergast/f1/current/{race_round}/results.json"
    response = requests.get(url)
    data = response.json()
    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    if len(races) == 0:
        return None, None
    results = races[0].get("Results", [])
    driver_results = {}
    constructor_points = {}
    for r in results:
        driver_id = r["Driver"]["driverId"]
        frontend_driver_id = denormalize_driver_id(driver_id)
        position = int(r["position"])
        driver_results[frontend_driver_id] = position
        
        constructor_id = r["Constructor"]["constructorId"]
        frontend_c_id = denormalize_constructor_id(constructor_id)
        pts = _driver_points_for_position(position)
        constructor_points[frontend_c_id] = constructor_points.get(frontend_c_id, 0) + pts
    return driver_results, constructor_points


def calculate_team_score(team_drivers, race_results):
    """Driver points for a team, given driver_results mapping driver_id -> finishing position."""
    if not race_results:
        return 0
    total = 0
    for driver in team_drivers:
        norm_driver = normalize_driver_id(driver)
        denorm_driver = denormalize_driver_id(driver)
        if denorm_driver in race_results:
            position = race_results[denorm_driver]
            total += _driver_points_for_position(position)
        elif norm_driver in race_results:
            position = race_results[norm_driver]
            total += _driver_points_for_position(position)
    return total


def calculate_constructor_score(constructor_ids, constructor_points):
    """Total constructor points for selected constructor IDs."""
    if not constructor_points or not constructor_ids:
        return 0
    total = 0
    for cid in constructor_ids:
        if cid:
            total += constructor_points.get(cid, 0)
    return total

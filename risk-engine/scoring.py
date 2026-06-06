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


FALLBACK_RACE_RESULTS = {
    "1": (
        {'russell': 1, 'antonelli': 2, 'leclerc': 3, 'hamilton': 4, 'norris': 5, 'max_verstappen': 6, 'bearman': 7, 'arvid_lindblad': 8, 'bortoleto': 9, 'gasly': 10, 'ocon': 11, 'albon': 12, 'lawson': 13, 'colapinto': 14, 'sainz': 15, 'perez': 16, 'stroll': 17, 'alonso': 18, 'bottas': 19, 'hadjar': 20, 'piastri': 21, 'hulkenberg': 22},
        {'mercedes': 43, 'ferrari': 27, 'mclaren': 10, 'red_bull': 8, 'haas': 6, 'rb': 4, 'audi': 2, 'alpine': 1, 'williams': 0, 'cadillac': 0, 'aston_martin': 0}
    ),
    "2": (
        {'antonelli': 1, 'russell': 2, 'hamilton': 3, 'leclerc': 4, 'bearman': 5, 'gasly': 6, 'lawson': 7, 'hadjar': 8, 'sainz': 9, 'colapinto': 10, 'hulkenberg': 11, 'arvid_lindblad': 12, 'bottas': 13, 'ocon': 14, 'perez': 15, 'max_verstappen': 16, 'alonso': 17, 'stroll': 18, 'piastri': 19, 'norris': 20, 'bortoleto': 21, 'albon': 22},
        {'mercedes': 43, 'ferrari': 27, 'haas': 10, 'alpine': 9, 'rb': 6, 'red_bull': 4, 'williams': 2, 'audi': 0, 'cadillac': 0, 'aston_martin': 0, 'mclaren': 0}
    ),
    "4": (
        {'antonelli': 1, 'norris': 2, 'piastri': 3, 'russell': 4, 'max_verstappen': 5, 'hamilton': 6, 'colapinto': 7, 'leclerc': 8, 'sainz': 9, 'albon': 10, 'bearman': 11, 'bortoleto': 12, 'ocon': 13, 'arvid_lindblad': 14, 'alonso': 15, 'perez': 16, 'stroll': 17, 'bottas': 18, 'hulkenberg': 19, 'lawson': 20, 'gasly': 21, 'hadjar': 22},
        {'mercedes': 37, 'mclaren': 33, 'red_bull': 10, 'ferrari': 12, 'alpine': 6, 'williams': 3, 'haas': 0, 'audi': 0, 'rb': 0, 'aston_martin': 0, 'cadillac': 0}
    ),
    "5": (
        {'antonelli': 1, 'hamilton': 2, 'max_verstappen': 3, 'leclerc': 4, 'hadjar': 5, 'colapinto': 6, 'lawson': 7, 'gasly': 8, 'sainz': 9, 'bearman': 10, 'piastri': 11, 'hulkenberg': 12, 'bortoleto': 13, 'ocon': 14, 'stroll': 15, 'bottas': 16, 'perez': 17, 'norris': 18, 'russell': 19, 'alonso': 20, 'albon': 21, 'arvid_lindblad': 22},
        {'mercedes': 25, 'ferrari': 30, 'red_bull': 25, 'alpine': 12, 'rb': 6, 'williams': 2, 'haas': 1, 'mclaren': 0, 'audi': 0, 'aston_martin': 0, 'cadillac': 0}
    )
}

def get_race_results(race_round):
    """
    Get results for a specific round (e.g. "1", "2").
    Returns a tuple (driver_results, constructor_points) or (None, None) if no results.
    """
    import time
    round_str = str(race_round)
    url = f"https://api.jolpi.ca/ergast/f1/current/{round_str}/results.json"
    
    # Try fetching from API with retries
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
                if len(races) > 0:
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
            elif response.status_code == 429:
                time.sleep(2) # Backoff on rate limit
        except Exception as e:
            print(f"API attempt {attempt+1} failed for round {round_str}: {e}")
            time.sleep(1)
            
    # Fallback to local verified results if available
    if round_str in FALLBACK_RACE_RESULTS:
        print(f"Using local fallback results for Round {round_str}")
        return FALLBACK_RACE_RESULTS[round_str]
        
    return None, None


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

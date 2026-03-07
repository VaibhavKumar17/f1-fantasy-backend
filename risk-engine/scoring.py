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
    10: 1
}
import requests

import requests

def get_last_race_results():
    url = "https://api.jolpi.ca/ergast/f1/current/last/results.json"
    response = requests.get(url)
    data = response.json()
    races = data["MRData"]["RaceTable"]["Races"]
    if len(races) == 0:
        return {"message": "No race results available yet"}
    results = races[0]["Results"]
    race_results = {}
    for r in results:
        driver_id = r["Driver"]["driverId"]
        position = int(r["position"])
        race_results[driver_id] = position
    return race_results


def get_race_results(race_round):
    """Get results for a specific round (e.g. "1", "2"). Returns dict driver_id -> position or None if no results."""
    url = f"https://api.jolpi.ca/ergast/f1/current/{race_round}/results.json"
    response = requests.get(url)
    data = response.json()
    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    if len(races) == 0:
        return None
    results = races[0].get("Results", [])
    race_results = {}
    for r in results:
        driver_id = r["Driver"]["driverId"]
        position = int(r["position"])
        race_results[driver_id] = position
    return race_results
def calculate_team_score(team_drivers, race_results):

    total = 0

    for driver in team_drivers:

        if driver in race_results:

            position = race_results[driver]

            if position in POINTS:
                total += POINTS[position]

    return total
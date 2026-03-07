import requests

def get_current_drivers():
    url = "https://api.jolpi.ca/ergast/f1/current/drivers.json"
    
    response = requests.get(url)
    data = response.json()

    drivers = []

    for d in data["MRData"]["DriverTable"]["Drivers"]:
        drivers.append({
            "id": d["driverId"],
            "name": f"{d['givenName']} {d['familyName']}"
        })

    return drivers
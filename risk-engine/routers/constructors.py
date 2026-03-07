import requests

def get_constructors():
    url = "https://api.jolpi.ca/ergast/f1/current/constructors.json"
    response = requests.get(url)
    data = response.json()
    constructors = data.get("MRData", {}).get("ConstructorTable", {}).get("Constructors", [])
    return [
        {"id": c["constructorId"], "name": c["name"], "nationality": c.get("nationality", "")}
        for c in constructors
    ]

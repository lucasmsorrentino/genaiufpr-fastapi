import requests
from fastapi import FastAPI
GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
app = FastAPI()
@app.get("/temperatura-cidade")
def temperatura_cidade(nome_cidade: str):
    geo_params = {
        "name": nome_cidade,
        "count": 1
    }
    geo_response = requests.get(GEO_URL, params=geo_params)
    geo_data = geo_response.json()
    lat = geo_data["results"][0]["latitude"]
    lon = geo_data["results"][0]["longitude"]
    weather_params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": True
    }
    weather_response = requests.get(WEATHER_URL, params=weather_params)
    weather_data = weather_response.json()
    return weather_data["current_weather"]["temperature"]   
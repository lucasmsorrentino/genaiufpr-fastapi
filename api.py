"""API de temperatura por cidade — exercício da aula de Deploy (GenAI UFPR).

Consome duas APIs abertas da open-meteo: primeiro o geocoding, para converter o
nome da cidade em coordenadas, depois a previsão para essas coordenadas.
"""

import requests
from fastapi import FastAPI, HTTPException

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_S = 10

app = FastAPI(
    title="Clima API",
    description="Temperatura atual de uma cidade, via open-meteo.",
    version="1.0.0",
)


@app.get("/temperatura-cidade")
def temperatura_cidade(nome_cidade: str):
    geo_response = requests.get(
        GEO_URL, params={"name": nome_cidade, "count": 1}, timeout=TIMEOUT_S
    )
    geo_response.raise_for_status()
    resultados = geo_response.json().get("results")
    # Cidade inexistente devolve {} sem a chave "results": sem esta guarda, o
    # acesso a results[0] estoura IndexError e o cliente recebe um 500 opaco.
    if not resultados:
        raise HTTPException(status_code=404, detail=f"Cidade não encontrada: {nome_cidade}")

    local = resultados[0]
    weather_response = requests.get(
        WEATHER_URL,
        params={
            "latitude": local["latitude"],
            "longitude": local["longitude"],
            "current_weather": True,
        },
        timeout=TIMEOUT_S,
    )
    weather_response.raise_for_status()
    atual = weather_response.json()["current_weather"]

    return {
        "cidade": local.get("name"),
        "pais": local.get("country"),
        "temperatura_c": atual["temperature"],
        "vento_kmh": atual.get("windspeed"),
    }


@app.get("/health")
def health():
    return {"status": "ok"}

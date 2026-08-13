"""API de temperatura por cidade — exercício da aula de Deploy (GenAI UFPR).

Consome duas APIs abertas da open-meteo: primeiro o geocoding, para converter o
nome da cidade em coordenadas, depois a previsão para essas coordenadas.
"""

import ipaddress
import os
import threading
import time
from collections import defaultdict, deque

import requests
from fastapi import Depends, FastAPI, HTTPException, Query, Request

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_S = 10

# Esta API está publicada na internet e repassa cada chamada para a open-meteo,
# que é gratuita e tem política de uso justo. Sem teto, uma rajada de terceiros
# gastaria a cota do servidor (ou renderia um bloqueio do IP) sem que o dono
# percebesse.
LIMITE_POR_MINUTO = int(os.getenv("RATE_LIMIT", "30"))
_JANELA_S = 60.0
_SWEEP_S = 300.0
_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()
_prox_sweep = time.monotonic() + _SWEEP_S

app = FastAPI(
    title="Clima API",
    description="Temperatura atual de uma cidade, via open-meteo.",
    version="1.1.0",
)


def _proxy_confiavel(ip: str) -> bool:
    """O par da conexão é um proxy local, e não um cliente da internet?

    O container é publicado em `127.0.0.1:8001` do host, então a única origem
    possível é o proxy do próprio host, que chega pelo gateway da bridge do
    Docker (`172.17.0.1`) — endereço privado, nunca `127.0.0.1`, porque o pacote
    é traduzido por NAT antes de entrar no container. Aceitar apenas origens
    privadas cobre esse caso sem abrir mão da garantia: um cliente da internet
    jamais aparece como par aqui.
    """
    try:
        endereco = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return endereco.is_loopback or endereco.is_private


def _ip_do_cliente(request: Request) -> str:
    """IP real de quem chamou.

    O tráfego público chega pelo Tailscale Funnel, que entrega a requisição no
    loopback do host: sem olhar o `X-Forwarded-For`, todo mundo viraria o mesmo
    cliente e o limite por IP seria, na prática, um limite global. O cabeçalho é
    aceito só quando o par é um proxy local, então não dá para forjá-lo de fora.
    """
    par = request.client.host if request.client else ""
    if _proxy_confiavel(par):
        encaminhado = request.headers.get("x-forwarded-for", "")
        if encaminhado:
            return encaminhado.split(",")[0].strip()
    return par or "desconhecido"


def rate_limit(request: Request) -> None:
    global _prox_sweep
    ip = _ip_do_cliente(request)
    agora = time.monotonic()
    with _lock:
        marcas = _hits[ip]
        while marcas and agora - marcas[0] > _JANELA_S:
            marcas.popleft()
        if len(marcas) >= LIMITE_POR_MINUTO:
            raise HTTPException(
                status_code=429,
                detail="Muitas requisições. Tente novamente em instantes.",
            )
        marcas.append(agora)

        # Sem esta varredura o dicionário guardaria uma entrada por IP visitante
        # para sempre, o que é um vazamento de memória lento num processo longo.
        if agora >= _prox_sweep:
            for chave in [
                k for k, v in _hits.items() if not v or agora - v[-1] > _JANELA_S
            ]:
                del _hits[chave]
            _prox_sweep = agora + _SWEEP_S


def _consultar(url: str, params: dict) -> dict:
    """Chama a open-meteo tratando a indisponibilidade dela como 502.

    Sem isto, um timeout ou um 5xx do upstream sobe como exceção não tratada: o
    cliente recebe um 500 opaco e o traceback expõe a URL e os parâmetros da
    chamada interna.
    """
    try:
        resposta = requests.get(url, params=params, timeout=TIMEOUT_S)
        resposta.raise_for_status()
        return resposta.json()
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502, detail="Serviço de meteorologia indisponível."
        ) from exc


@app.get("/temperatura-cidade", dependencies=[Depends(rate_limit)])
def temperatura_cidade(
    nome_cidade: str = Query(min_length=1, max_length=80, description="Nome da cidade"),
):
    geo = _consultar(GEO_URL, {"name": nome_cidade, "count": 1})
    resultados = geo.get("results")
    # Cidade inexistente devolve {} sem a chave "results": sem esta guarda, o
    # acesso a results[0] estoura IndexError e o cliente recebe um 500 opaco.
    if not resultados:
        raise HTTPException(
            status_code=404, detail=f"Cidade não encontrada: {nome_cidade}"
        )

    local = resultados[0]
    previsao = _consultar(
        WEATHER_URL,
        {
            "latitude": local["latitude"],
            "longitude": local["longitude"],
            "current_weather": True,
        },
    )
    atual = previsao["current_weather"]

    return {
        "cidade": local.get("name"),
        "pais": local.get("country"),
        "temperatura_c": atual["temperature"],
        "vento_kmh": atual.get("windspeed"),
    }


@app.get("/health")
def health(request: Request):
    # `cliente` devolve o IP que o rate limit está usando como chave. Atrás de um
    # proxy é o único jeito barato de saber se o encaminhamento está correto: se
    # aparecer 127.0.0.1 aqui, o limite virou global em vez de por IP.
    return {"status": "ok", "cliente": _ip_do_cliente(request)}

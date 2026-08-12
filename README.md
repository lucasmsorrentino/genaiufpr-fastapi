# genaiufpr-fastapi — API de temperatura por cidade

Exercício guiado da aula **Deploy e Projeto Final** (Especialização em IA
Generativa — UFPR). Uma API FastAPI que consome duas APIs abertas da
[open-meteo](https://open-meteo.com): geocoding para converter o nome da cidade
em coordenadas, e previsão para obter a temperatura atual.

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/temperatura-cidade?nome_cidade=Curitiba` | Temperatura atual da cidade |
| `GET` | `/health` | Verificação de vida |
| `GET` | `/docs` | OpenAPI interativo |

```bash
curl "http://localhost:8000/temperatura-cidade?nome_cidade=Curitiba"
# {"cidade":"Curitiba","pais":"Brazil","temperatura_c":15.7,"vento_kmh":10.9}
```

Cidade inexistente devolve **404** com mensagem, não um 500 opaco.

## Rodando com Docker

```bash
docker build -t clima-api .
docker run --rm -p 8000:8000 clima-api
```

Para publicar num servidor remoto pelo método de imagem exportada:

```bash
docker save clima-api | gzip > clima-api.tar.gz
scp clima-api.tar.gz ubuntu@<IP>:~
ssh ubuntu@<IP> 'gunzip -c clima-api.tar.gz | docker load && \
  docker run -d --name clima --restart unless-stopped -p 8000:8000 clima-api'
```

> Se a máquina de origem for x86 e o servidor for ARM (ou vice-versa), a imagem
> exportada não executa (`exec format error`) — nesse caso, faça o `git clone` e
> o `docker build` no próprio servidor.

## Projeto final

O projeto final desta disciplina está em repositório separado, por ser uma
aplicação distinta e bem maior:

**➡️ [ufpr-rag-api](https://github.com/lucasmsorrentino/ufpr-rag-api)** — busca
semântica em ~3.300 documentos institucionais da UFPR (35.359 trechos indexados),
publicada em **duas máquinas** na Oracle Cloud conforme a sugestão 3a da aula: uma
VM contém o modelo e **não expõe nenhuma porta à internet**, outra hospeda a API
pública que conversa com ela pela rede privada.

Aplicação no ar: <http://167.234.235.90:8000>

## Notas de implementação

Três problemas que impediam o build original e ficam registrados porque são
armadilhas comuns:

- **`CMD` em JSON quebrado em duas linhas** — o array precisa de `\` na quebra,
  senão o Docker não consegue parsear a forma exec.
- **`uvicorn clima_api:app`** — `clima_api` é o nome do *ambiente conda* (`-n`),
  não do módulo. O arquivo é `api.py`, logo `api:app`.
- **arquivo `dockerfile` em minúsculo** — o `docker build` procura `Dockerfile`.
  Passa despercebido no Windows (sistema de arquivos sem distinção de caixa) e
  falha no Linux do servidor.

Além disso, o canal `defaults` do conda não tem `fastapi` nem `uvicorn`, e não
havia build de `python=3.14` para eles — daí `conda-forge` e `python=3.11`.

# genaiufpr-fastapi — API de temperatura por cidade

Repositório da disciplina **Deploy e Projeto Final** (Especialização em IA
Generativa — UFPR, prof. Paulo Lisboa de Almeida).

## Os dois trabalhos da disciplina

A aula gerou duas entregas, em repositórios separados porque são projetos de
tamanho e propósito diferentes:

| | Repositório | O que é |
|---|---|---|
| **Exercício guiado** | **`genaiufpr-fastapi`** (este) | A API de temperatura construída passo a passo durante a aula: FastAPI consumindo a open-meteo, empacotada em Docker e publicada num servidor remoto. |
| **Projeto final** | [`ufpr-rag-api`](https://github.com/lucasmsorrentino/ufpr-rag-api) | Busca semântica em ~3.400 documentos institucionais da UFPR (35.359 trechos indexados), na arquitetura de **duas máquinas** sugerida na aula: uma VM contém o modelo e não expõe porta nenhuma à internet, outra hospeda a API pública que conversa com ela pela rede privada. |

Aplicações no ar:

- **Clima (este repo):** <https://ufpr-rag.tail9f5159.ts.net:8443/docs>
- **RAG (projeto final):** <https://ufpr-rag.tail9f5159.ts.net>

As duas rodam na mesma VM da Oracle Cloud, e por isso dividem o nome de host —
o endereço é o nome da máquina na rede Tailscale, não o nome da aplicação. O
que separa as duas é a porta: `443` para o RAG, `8443` para o clima.

---

## Esta API

Consome duas APIs abertas da [open-meteo](https://open-meteo.com): geocoding
para converter o nome da cidade em coordenadas, e previsão para obter a
temperatura atual.

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/temperatura-cidade?nome_cidade=Curitiba` | Temperatura atual da cidade |
| `GET` | `/health` | Verificação de vida |
| `GET` | `/docs` | OpenAPI interativo |

```bash
curl "https://ufpr-rag.tail9f5159.ts.net:8443/temperatura-cidade?nome_cidade=Curitiba"
# {"cidade":"Curitiba","pais":"Brazil","temperatura_c":15.7,"vento_kmh":10.9}
```

Cidade inexistente devolve **404** com mensagem; open-meteo fora do ar devolve
**502**; rajada de chamadas devolve **429**. Nenhum desses vira um 500 opaco.

---

## Rodando localmente

```bash
docker build -t clima-api .
docker run --rm -p 8000:8000 clima-api
```

Depois, <http://localhost:8000/docs>.

Sem Docker, com conda:

```bash
conda env create -f environment.yml
conda activate clima_api
uvicorn api:app --reload
```

---

## Deploy

A aula apresenta dois métodos de levar a imagem ao servidor. Este projeto usa o
segundo, **clonar e buildar no servidor**:

```bash
git clone https://github.com/lucasmsorrentino/genaiufpr-fastapi.git ~/clima-src
cd ~/clima-src && sudo docker build -t clima-api .
sudo docker run -d --name clima --restart unless-stopped \
  -p 127.0.0.1:8001:8000 clima-api
```

O motivo é o da própria aula: a imagem parte da `continuumio/miniconda3` e passa
de 1 GB, então exportar com `docker save` e transferir por `scp` significaria
subir essa massa toda pela internet doméstica. Clonar e buildar no servidor
transfere alguns kilobytes de código.

O outro método, para referência (funciona quando a arquitetura da máquina de
origem é a mesma do servidor — `docker save` de uma imagem x86 não executa numa
VM ARM, e vice-versa):

```bash
docker save clima-api | gzip > clima-api.tar.gz
scp clima-api.tar.gz ubuntu@<IP>:~
ssh ubuntu@<IP> 'gunzip -c clima-api.tar.gz | docker load'
```

### Publicação sem abrir porta

O container é publicado em `127.0.0.1:8001` — ele não escuta na interface
pública da VM. Quem alcança essa porta é o `tailscaled`, no mesmo host, que
expõe a aplicação na internet por **Tailscale Funnel**:

```bash
sudo tailscale funnel --bg --https=8443 8001
```

O tráfego entra pelo túnel WireGuard que a própria VM abre de dentro para fora,
com certificado Let's Encrypt gerenciado. **Nenhuma regra de ingress é criada
para esta aplicação** — a VM segue com a porta 22 como única porta aberta. É a
mesma mecânica usada no projeto final, que o repositório do RAG documenta em
detalhe.

---

## Notas de implementação

### Três bugs que impediam o build original

Ficam registrados porque são armadilhas comuns:

- **`CMD` em JSON quebrado em duas linhas** — o array precisa de `\` na quebra,
  senão o Docker não consegue parsear a forma exec.
- **`uvicorn clima_api:app`** — `clima_api` é o nome do *ambiente conda* (`-n`),
  não do módulo. O arquivo é `api.py`, logo `api:app`.
- **arquivo `dockerfile` em minúsculo** — o `docker build` procura `Dockerfile`.
  Passa despercebido no Windows (sistema de arquivos sem distinção de caixa) e
  falha no Linux do servidor.

Além disso, o canal `defaults` do conda não tem `fastapi` nem `uvicorn`, e não
havia build de `python=3.14` para eles — daí `conda-forge` e `python=3.11`.

### Três ajustes por estar exposta na internet

O código da aula é correto para rodar em `localhost`. Publicado, ganhou:

- **Falha do upstream vira `502`** — um timeout da open-meteo subia como exceção
  não tratada, o cliente recebia `500` e o traceback registrava a URL e os
  parâmetros da chamada interna.
- **Teto de tamanho no `nome_cidade`** — a entrada é repassada a um serviço de
  terceiro; aceitar string de tamanho arbitrário é repassar o abuso adiante.
- **Rate limit por IP** (30/min) — cada chamada consome a cota gratuita da
  open-meteo. Sem teto, uma rajada de terceiros gastaria a cota do servidor, ou
  renderia um bloqueio do IP, sem que o dono percebesse.

O rate limit tem um detalhe que só aparece atrás de proxy: o Funnel entrega o
tráfego em `127.0.0.1`, então todo cliente chegaria com o mesmo IP e o limite
"por IP" viraria um limite global. O IP real vem do `X-Forwarded-For`, aceito
**apenas** quando quem conecta é o loopback — de fora, o cabeçalho não pode ser
forjado, porque a única entrada é o proxy local.

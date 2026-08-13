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

**Limitação conhecida: o nome resolve pelo índice do open-meteo, não por fama.**
`Lisboa` responde de Moçambique — não por erro de desempate, mas porque a
capital portuguesa está indexada como `Lisbon`, e todos os homônimos retornados
são de fato outros lugares chamados Lisboa. O mesmo vale para `Londres`
(devolve a da Argentina; a inglesa é `London`).

Tentei corrigir isso desempatando pela cidade mais populosa e **desfiz**: em 12
nomes ambíguos testados a escolha mudou em 2, e nas duas para pior — `Salvador`
passou a devolver *El Salvador*, o país, em vez da cidade da Bahia, e `Valencia`
trocou a Espanha pela Venezuela. A ordenação do próprio open-meteo pondera
melhor que população sozinha. Resolver de verdade exigiria aceitar país ou
coordenadas como parâmetro, o que sai do escopo do exercício.

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
- **Rate limit** (60/min) — cada chamada consome a cota gratuita da open-meteo.
  Sem teto, uma rajada de terceiros gastaria a cota do servidor, ou renderia um
  bloqueio do IP, sem que o dono percebesse.

### O que a medição mostrou sobre o rate limit

A intenção era limitar **por visitante**. Medindo, não dá — e o motivo tem duas
camadas, ambas invisíveis em `localhost`:

1. **O Docker esconde o par da conexão.** O container é publicado em
   `127.0.0.1:8001`, mas dentro dele a origem aparece como `172.17.0.1`, o
   gateway da bridge: o pacote sofre NAT antes de entrar. Uma verificação do
   tipo `if ip == "127.0.0.1"` nunca é verdadeira ali dentro.
2. **O Funnel não preserva o IP do visitante.** O `X-Forwarded-For` chega com o
   endereço do relay de entrada da Tailscale — um `100.x` constante, e
   diferente do IP da própria VM no tailnet. Três chamadas de máquinas
   diferentes produzem o mesmo valor.

O `/health` devolve o IP detectado justamente para tornar isso verificável:

```bash
curl https://ufpr-rag.tail9f5159.ts.net:8443/health
# {"status":"ok","cliente":"100.66.216.50"}   <- o relay, não quem chamou
```

Então o limite é **global**, não por visitante. Ele ainda cumpre o objetivo
principal — proteger a cota da open-meteo e uma VM de 1 GB de RAM contra um
laço descontrolado — mas não isola um abusador dos demais, e por isso o teto é
folgado. A leitura do cabeçalho fica no código porque é o comportamento correto
atrás de um proxy que preserve o IP, e é aceita apenas quando o par da conexão
é privado, de modo que não pode ser forjada pela internet.

É a contrapartida honesta de publicar sem abrir porta: o preço de não ter
superfície exposta é não enxergar quem está do outro lado.

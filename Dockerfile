FROM continuumio/miniconda3

WORKDIR /app

# O ambiente é criado antes de copiar o código: só refaz esta camada quando
# o environment.yml muda, e não a cada edição da API.
COPY environment.yml .
RUN conda env create -f environment.yml && conda clean --all --yes

COPY . .

EXPOSE 8000

# `clima_api` é o nome do AMBIENTE conda (-n); o módulo é `api.py`, logo `api:app`.
CMD ["conda", "run", "--no-capture-output", "-n", "clima_api", \
     "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]

# Imagem de submissão. Segue o contrato de execução da organização:
#
#   docker run --network none \
#     -v <txt>:/data/in -v <saida>:/data/out -v <base.db>:/data/base/desafio1_bracis.db \
#     verificador-citacoes:latest --input /data/in --output /data/out
#
# Sem pesos e sem dados dentro da imagem, como exige o regulamento: a base
# canônica entra por volume. Sem rede em runtime — o pipeline é determinístico e
# só usa a biblioteca padrão do Python.
# Versão exata e digest fixos: o bundle reproduzível é reexecutado pela
# organização depois do fechamento, e `3.12-slim` flutua. 3.12.3 é a versão em
# que as medições foram feitas.
FROM python:3.12.3-slim@sha256:afc139a0a640942491ec481ad8dda10f2c5b753f5c969393b12480155fe15a63

# Sem bytecode residual e sem buffer, para que a saída do container apareça na hora.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    VERIFICADOR_DB=/data/base/desafio1_bracis.db \
    VERIFICADOR_INDICE=/data/base/indice_cabecalhos.json

WORKDIR /app

# requirements.txt é gerado do uv.lock por `make requirements`. Hoje sai vazio —
# o runtime não tem dependência externa — mas o passo fica no lugar para o dia
# em que tiver, com as versões pinadas pelo lockfile.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY scripts/ ./scripts/

ENV PYTHONPATH=/app/src

ENTRYPOINT ["python", "-m", "verificador.cli"]

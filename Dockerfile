# Imagem da entrega; roda o mesmo run.sh do host, sem dados nem rede:
#
#   docker build -t verificador-citacoes .
#   docker run --rm --network none \
#     -v "$DB":/dados/base.db:ro -v "$TXT":/dados/txt:ro -v "$SAIDA_DIR":/saida \
#     verificador-citacoes /dados/base.db /dados/txt /saida/submission.csv
#
# Versão e digest fixos para a reexecução ser reproduzível.
FROM python:3.12.3-slim@sha256:afc139a0a640942491ec481ad8dda10f2c5b753f5c969393b12480155fe15a63

# Repete as variáveis do run.sh para quem usar `--entrypoint python`.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PYTHONUTF8=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Gerado do uv.lock por `make requirements`; hoje vazio (só biblioteca padrão).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY run.sh ./
COPY src/ ./src/

# Bash explícito: não depende do bit de execução do run.sh.
ENTRYPOINT ["bash", "/app/run.sh"]

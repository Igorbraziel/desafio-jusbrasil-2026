# Imagem da entrega. Roda o mesmo run.sh da execução no host:
#
#   docker build -t verificador-citacoes .
#   docker run --rm --network none \
#     -v "$DB":/dados/base.db:ro -v "$TXT":/dados/txt:ro -v "$SAIDA_DIR":/saida \
#     verificador-citacoes /dados/base.db /dados/txt /saida/submission.csv
#
# Funciona também com `--user $(id -u):$(id -g)` e `--read-only`: nada é escrito
# fora de /saida (e da pasta de JSONs, se passada como quarto argumento).
#
# Sem pesos e sem dados dentro da imagem, como exige o regulamento: a base
# canônica entra por volume. Sem rede em runtime — o pipeline é determinístico e
# só usa a biblioteca padrão do Python.
# Versão exata e digest fixos: o bundle reproduzível é reexecutado pela
# organização depois do fechamento, e `3.12-slim` flutua. 3.12.3 é a versão em
# que as medições foram feitas.
FROM python:3.12.3-slim@sha256:afc139a0a640942491ec481ad8dda10f2c5b753f5c969393b12480155fe15a63

# O run.sh exporta as mesmas variáveis; repeti-las aqui cobre quem chamar o
# módulo direto na imagem (`--entrypoint python`).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PYTHONUTF8=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# requirements.txt é gerado do uv.lock por `make requirements`. Hoje sai vazio —
# o runtime não tem dependência externa — mas o passo fica no lugar para o dia
# em que tiver, com as versões pinadas pelo lockfile.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY run.sh ./
COPY src/ ./src/

# Exec form com o bash explícito: não depende do bit de execução do run.sh, que
# se perde num checkout que não o preserva.
ENTRYPOINT ["bash", "/app/run.sh"]

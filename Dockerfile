# Imagem de submissão. Segue o contrato de execução da organização — um ponto de
# entrada único que recebe o banco e a pasta de .txt e escreve o CSV no formato
# da submissão:
#
#   docker build -t verificador-citacoes .
#   docker run --rm --network none \
#     -v <banco.db>:/in/base.db:ro -v <pasta_txt>:/in/txt:ro -v <pasta_saida>:/out \
#     verificador-citacoes /in/base.db /in/txt /out/submission.csv
#
# Os argumentos são os mesmos de `bash run.sh <caminho_db> <pasta_txt> <arquivo_saida>`.
# Sem pesos e sem dados dentro da imagem: o banco entra por volume, e toda a
# cobertura (acórdãos, súmulas, dispositivos) é construída dele a cada execução.
# Sem rede em runtime — o pipeline é determinístico e só usa a biblioteca padrão.
# Versão exata e digest fixos: o bundle é reexecutado pela organização depois do
# fechamento, e `3.12-slim` flutua. 3.12.3 é a versão em que as medições foram feitas.
FROM python:3.12.3-slim@sha256:afc139a0a640942491ec481ad8dda10f2c5b753f5c969393b12480155fe15a63

# Sem bytecode residual e sem buffer, para que a saída do container apareça na hora.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0

WORKDIR /app

# requirements.txt é gerado do uv.lock por `make requirements`. Hoje sai vazio —
# o runtime não tem dependência externa — mas o passo fica no lugar para o dia
# em que tiver, com as versões pinadas pelo lockfile.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY run.sh ./

ENTRYPOINT ["bash", "/app/run.sh"]

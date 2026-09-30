#!/usr/bin/env bash
# Ponto de entrada da avaliação final.
#
#   bash run.sh <caminho_db> <pasta_txt> <arquivo_saida.csv>
#
# Lê o banco canônico e os .txt, e escreve o CSV no formato da submissão
# (documento_id,citacoes). A cobertura inteira — acórdãos, súmulas e
# dispositivos — é construída do banco recebido, a cada execução. Só usa a
# biblioteca padrão do Python (3.10 ou mais novo; as medições são em 3.12), sem
# rede, sem GPU e sem pesos de modelo. Resultado determinístico.
set -euo pipefail

if [ "$#" -ne 3 ]; then
    echo "uso: bash run.sh <caminho_db> <pasta_txt> <arquivo_saida.csv>" >&2
    exit 2
fi
DB="$1"
TXT="$2"
SAIDA="$3"
[ -f "$DB" ] || { echo "banco não encontrado: $DB" >&2; exit 2; }
[ -d "$TXT" ] || { echo "pasta de .txt não encontrada: $TXT" >&2; exit 2; }

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
"$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 10))' || {
    echo "é preciso Python 3.10 ou mais novo (encontrado: $("$PYTHON" --version 2>&1))" >&2
    exit 2
}

PYTHONPATH="$RAIZ/src${PYTHONPATH:+:$PYTHONPATH}" PYTHONHASHSEED=0 \
    "$PYTHON" -m verificador.cli --db "$DB" --input "$TXT" --csv "$SAIDA"

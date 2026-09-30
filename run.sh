#!/usr/bin/env bash
# Ponto de entrada único da entrega: base canônica + pasta de pareceres
# -> submission.csv no formato das submissões do Kaggle.
#
#   bash run.sh <caminho_db> <pasta_txt> <arquivo_saida> [pasta_json]
#
# A avaliação final roda este script sobre uma base e pareceres novos, sem
# ninguém nosso por perto. Por isso ele só depende do bash e de um Python ≥ 3.10
# com a biblioteca padrão — ou, na falta dele, do Docker —, aceita caminhos
# relativos a quem chama e com espaços, e todo erro sai com mensagem e código
# ≠ 0. Até escolher entre Python e Docker ele só usa builtins do bash: um PATH
# mínimo não o derruba antes da mensagem.
#
# Variáveis: PYTHON (interpretador a usar), VERIFICADOR_DOCKER=1 (força o
# Docker), VERIFICADOR_IMAGEM (imagem; padrão verificador-citacoes:latest).

# `sh run.sh` roda o script no sh do sistema, que pode não ter arrays.
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

USAGE="uso: bash run.sh <caminho_db> <pasta_txt> <arquivo_saida> [pasta_json]

  caminho_db     base canônica (SQLite com a tabela documentos)
  pasta_txt      pasta com os pareceres .txt
  arquivo_saida  submission.csv a gravar, no formato das submissões do Kaggle
  pasta_json     opcional: grava também um JSON do contrato por documento

variáveis: PYTHON (interpretador), VERIFICADOR_DOCKER=1 (força o Docker),
           VERIFICADOR_IMAGEM (imagem; padrão verificador-citacoes:latest)"

die() {
  printf 'run.sh: %s\n' "$1" >&2
  exit 1
}

usage() {
  printf '%s\n' "$USAGE" >&2
  exit 2
}

# Diretório de um caminho, sem `dirname`: "a/b" -> "a", "b" -> ".", "/b" -> "/".
parent_of() {
  case "$1" in
    */*)
      local parent="${1%/*}"
      printf '%s\n' "${parent:-/}"
      ;;
    *) printf '.\n' ;;
  esac
}

absolute_dir() {
  (CDPATH='' cd -P -- "$1" && pwd -P)
}

absolute_file() {
  local parent
  parent="$(absolute_dir "$(parent_of "$1")")"
  printf '%s/%s\n' "${parent%/}" "${1##*/}"
}

# `docker run <imagem> bash run.sh a b c` chega aqui como `bash run.sh a b c`,
# porque o ENTRYPOINT da imagem já é `bash /app/run.sh`.
while [ "$#" -gt 3 ]; do
  case "$1" in
    bash | sh | run.sh | ./run.sh | /app/run.sh) shift ;;
    *) break ;;
  esac
done

for arg in "$@"; do
  case "$arg" in
    -h | --help) usage ;;
  esac
done
if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
  usage
fi

db="$1"
txt="$2"
out="$3"
json="${4:-}"

[ -f "$db" ] || die "base canônica não encontrada: $db"
[ -d "$txt" ] || die "pasta de entrada não encontrada: $txt"
case "$out" in
  */) die "arquivo_saida termina em /; passe o caminho do CSV: $out" ;;
esac
[ ! -d "$out" ] || die "arquivo_saida é uma pasta; passe o caminho do CSV: $out"

# Sem `cd` no shell principal: os caminhos relativos continuam relativos à pasta
# de quem chamou.
DIR="$(absolute_dir "$(parent_of "${BASH_SOURCE[0]}")")"

export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONUNBUFFERED=1
# `-m` põe a pasta de quem chamou à frente do PYTHONPATH, e um `verificador` que
# estivesse lá tomaria o lugar do nosso. Vale do 3.11 em diante; o 3.10 ignora.
export PYTHONSAFEPATH=1

# sqlite3 entra na checagem porque há Python compilado sem ele, e só a versão
# não bastaria: o primeiro candidato "adequado" quebraria ao abrir a base.
python_ok() {
  "$1" -c 'import sqlite3, sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1
}

run_python() {
  export PYTHONPATH="$DIR/src"
  # A forma `--opção=valor` aceita caminho que começa com hífen.
  if [ -n "$json" ]; then
    exec "$1" -m verificador.cli "--db=$db" "--input=$txt" "--csv=$out" "--output=$json"
  fi
  exec "$1" -m verificador.cli "--db=$db" "--input=$txt" "--csv=$out"
}

# A imagem com o nome pedido só serve se o ENTRYPOINT for este script. Uma
# construída de uma versão anterior do repositório chamava a CLI direto e
# quebrava com erro de argumento, sem CSV; ela é reconstruída.
image_is_current() {
  local entrypoint
  entrypoint="$(docker image inspect --format '{{json .Config.Entrypoint}}' "$1" 2>/dev/null)" ||
    return 1
  [ "$entrypoint" = '["bash","/app/run.sh"]' ]
}

run_docker() {
  local image="${VERIFICADOR_IMAGEM:-verificador-citacoes:latest}"
  command -v docker >/dev/null 2>&1 ||
    die "é preciso Python ≥ 3.10 com sqlite3 ou Docker, e nenhum dos dois foi encontrado (defina PYTHON=/caminho/do/python3)"
  docker info >/dev/null 2>&1 || die "o Docker não responde (daemon parado ou sem permissão)"
  if ! image_is_current "$image"; then
    printf 'run.sh: construindo a imagem %s a partir de %s\n' "$image" "$DIR" >&2
    docker build -t "$image" "$DIR" >&2 || die "não consegui construir a imagem $image"
  fi

  # A pasta de saída é criada aqui, e não pelo Docker: um volume inexistente ele
  # cria como root, e o container rodando com o nosso usuário não escreveria.
  local out_dir db_abs txt_abs out_abs
  out_dir="$(parent_of "$out")"
  mkdir -p -- "$out_dir"
  db_abs="$(absolute_file "$db")"
  txt_abs="$(absolute_dir "$txt")"
  out_abs="$(absolute_dir "$out_dir")"

  local mounts=(-v "$db_abs:/dados/base.db:ro" -v "$txt_abs:/dados/txt:ro" -v "$out_abs:/saida")
  local args=(/dados/base.db /dados/txt "/saida/${out##*/}")
  if [ -n "$json" ]; then
    local json_abs
    mkdir -p -- "$json"
    json_abs="$(absolute_dir "$json")"
    mounts+=(-v "$json_abs:/json")
    args+=(/json)
  fi
  exec docker run --rm --network none --user "$(id -u):$(id -g)" "${mounts[@]}" "$image" "${args[@]}"
}

if [ "${VERIFICADOR_DOCKER:-}" != 1 ]; then
  if [ -n "${PYTHON:-}" ]; then
    python_ok "$PYTHON" || die "PYTHON=$PYTHON não é um Python ≥ 3.10 com sqlite3"
    run_python "$PYTHON"
  fi
  for candidate in python3.12 python3.13 python3.14 python3.11 python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && python_ok "$candidate"; then
      run_python "$candidate"
    fi
  done
  printf 'run.sh: nenhum Python ≥ 3.10 com sqlite3 encontrado; usando o Docker\n' >&2
fi
run_docker

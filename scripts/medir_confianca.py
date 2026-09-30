"""Mede a acurácia real de cada caminho de decisão, para calibrar ``CONFIANCA``.

Os oito valores de :data:`verificador.resolucao.CONFIANCA` eram palpite — o
próprio comentário no código dizia isso. Palpite custa: o bônus de calibração da
métrica oficial é ``b = 0,10·(1 − Brier)``, e o Brier é **minimizado exatamente
em p = acurácia**. Emitir 0,93 num caminho que acerta 0,99 joga bônus fora;
emitir 0,93 num que acerta 0,70 é pior, porque a punição é quadrática.

O método: rodar o pipeline sobre o corpus **perturbado**, casar cada predição
com o gabarito traduzido pela mesma regra do avaliador oficial (IoU ≥ 0,5) e
contar, por caminho de decisão, quantas vezes a predição estava certa — mesma
classe e, nas ``real``, mesmo ``id_canonico``. A predição sem par fica de fora,
como no Brier oficial, que só conta pares casados.

Por que sob perturbação e não no conjunto limpo: no limpo todo caminho acerta
100%, e calibrar por ele mandaria emitir 1,0 em tudo. O conjunto cego tem formas
que a amostra não tem, e o arnês é a única aproximação disponível dessa
diferença. A taxa padrão é a de operação (0,15), a mesma dos checkpoints.

Uso:
    python scripts/medir_confianca.py                  # todas as classes, 3 sementes
    python scripts/medir_confianca.py --taxa 0.2 --sementes 5
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from perturbar import CLASSES, gerar_corpus  # noqa: E402

from verificador.base_canonica import BaseCanonica  # noqa: E402
from verificador.cli import _carregar_base  # noqa: E402
from verificador.deteccao import detectar  # noqa: E402
from verificador.resolucao import CONFIANCA, resolver  # noqa: E402
from verificador.texto import carregar  # noqa: E402

IOU_MIN = 0.5


def _iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    if not inter:
        return 0.0
    return inter / ((a[1] - a[0]) + (b[1] - b[0]) - inter)


def _ler_goldenset(caminho: Path) -> dict[str, list[dict[str, str]]]:
    import csv

    por_documento: dict[str, list[dict[str, str]]] = defaultdict(list)
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            por_documento[linha["documento_id"]].append(linha)
    return por_documento


def _caminho_de_decisao(familia: str, classe: str, confianca: float) -> str:
    """O nome do caminho que produziu esta decisão.

    Deriva da classe **e** da confiança emitida. A confiança sozinha não basta:
    depois da calibração dois caminhos de classes diferentes podem compartilhar o
    mesmo valor — `real_desempate` e `inventada_processo` ficaram ambos em 0,83 —
    e a busca cega atribuía as observações ao caminho errado.

    É indireto de propósito: evita duplicar aqui a árvore de decisão de
    ``resolucao.resolver``, que mudaria sem este script perceber.
    """
    candidatos = [
        nome
        for nome, valor in CONFIANCA.items()
        if nome.startswith(f"{classe}_") and abs(valor - confianca) < 1e-9
    ]
    if len(candidatos) == 1:
        return candidatos[0]
    if candidatos:
        # Empate dentro da mesma classe: o script não consegue separar, e relatar
        # um número agregado seria pior que relatar a ambiguidade.
        return f"AMBÍGUO({'|'.join(sorted(candidatos))})"
    return f"{familia}:{classe}:{confianca}"


@contextmanager
def _valores_distintos():
    """Troca, durante a medição, cada valor de `CONFIANCA` por um sentinela único.

    O caminho é reconhecido pelo valor emitido, e dois caminhos da mesma classe
    com o mesmo valor ficavam indistinguíveis — `real_unico` e `real_tabela`
    sempre saíram como AMBÍGUO, e com a tabela em 1,0 as três `inventada` se
    fundiam. Os sentinelas tornam a medição independente dos valores da tabela.
    """
    originais = dict(CONFIANCA)
    CONFIANCA.update({nome: i / 1000 for i, nome in enumerate(originais, start=1)})
    try:
        yield
    finally:
        CONFIANCA.update(originais)


def medir(base: BaseCanonica, pasta_txt: Path, goldenset: Path) -> dict[str, tuple[int, int]]:
    """Devolve ``{caminho: (acertos, total)}`` sobre um corpus já perturbado."""
    with _valores_distintos():
        return _medir(base, pasta_txt, goldenset)


def _medir(base: BaseCanonica, pasta_txt: Path, goldenset: Path) -> dict[str, tuple[int, int]]:
    gold = _ler_goldenset(goldenset)
    contagem: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    for caminho_txt in sorted(pasta_txt.glob("*.txt")):
        texto = carregar(caminho_txt)
        esperadas = [
            (int(g["inicio"]), int(g["fim"]), g["classificacao"], g["id_canonico"])
            for g in gold.get(caminho_txt.stem, [])
        ]

        for achado in detectar(texto):
            classe, id_canonico, confianca = resolver(achado, base)
            nome = _caminho_de_decisao(achado.familia, classe, confianca)

            melhor = None
            melhor_iou = 0.0
            for esperada in esperadas:
                valor = _iou((achado.inicio, achado.fim), (esperada[0], esperada[1]))
                if valor >= IOU_MIN and valor > melhor_iou:
                    melhor, melhor_iou = esperada, valor

            if melhor is None:
                # Predição sem par fica de fora, como no Brier oficial: o bônus
                # de calibração só conta pares casados. Contá-la como erro
                # puxava a acurácia para baixo de um valor que a métrica não vê.
                continue
            contagem[nome][1] += 1
            if classe != melhor[2]:
                continue
            if classe == "real":
                esperado = (melhor[3] or "").strip().lstrip("0")
                if str(id_canonico).lstrip("0") != esperado:
                    continue
            contagem[nome][0] += 1

    return {nome: (a, t) for nome, (a, t) in contagem.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--taxa", type=float, default=0.15)
    parser.add_argument("--sementes", type=int, default=3)
    parser.add_argument("--db", type=Path, default=RAIZ / "data/dev/desafio1_bracis.db")
    parser.add_argument("--indice", type=Path, default=RAIZ / "data/dev/indice_cabecalhos.json")
    parser.add_argument("--saida", type=Path, default=None)
    args = parser.parse_args()

    # O mesmo carregamento do CLI: banco primeiro, JSON só de reserva.
    base = _carregar_base(args.indice, args.db)
    trabalho = RAIZ / "data/tmp/confianca"
    if trabalho.exists():
        shutil.rmtree(trabalho)

    total: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    # O corpus limpo entra uma vez: é o caminho feliz, e ignorá-lo enviesaria a
    # medição para baixo. As perturbações entram por semente.
    for acertos, (nome, (a, t)) in enumerate(
        medir(base, RAIZ / "data/dev/txt", RAIZ / "data/dev/goldenset.csv").items()
    ):
        del acertos
        total[nome][0] += a
        total[nome][1] += t

    for semente in range(args.sementes):
        destino = trabalho / f"todas-{semente}"
        gerar_corpus(
            RAIZ / "data/dev/txt",
            RAIZ / "data/dev/goldenset.csv",
            destino,
            list(CLASSES),
            args.taxa,
            semente,
        )
        for nome, (a, t) in medir(base, destino / "txt", destino / "goldenset.csv").items():
            total[nome][0] += a
            total[nome][1] += t

    print(f"\nAcurácia por caminho de decisão — taxa {args.taxa}, {args.sementes} sementes")
    print("(inclui o corpus limpo; só pares casados, como o Brier oficial)\n")
    print(f"  {'caminho':<24} {'acertos':>9} {'total':>7} {'acurácia':>10} {'hoje':>7}")
    print("  " + "-" * 62)
    calibrado: dict[str, float] = {}
    for nome in sorted(total, key=lambda n: -total[n][1]):
        acertos, n = total[nome]
        if not n:
            continue
        taxa_acerto = acertos / n
        calibrado[nome] = round(taxa_acerto, 3)
        atual = CONFIANCA.get(nome)
        print(
            f"  {nome:<24} {acertos:>9} {n:>7} {taxa_acerto:>10.3f} "
            f"{(f'{atual:.3f}' if atual is not None else '—'):>7}"
        )

    nao_exercidos = sorted(set(CONFIANCA) - set(calibrado))
    if nao_exercidos:
        print(f"\n  não exercidos pelo arnês (mantêm o valor atual): {', '.join(nao_exercidos)}")

    if args.saida:
        args.saida.write_text(json.dumps(calibrado, indent=2, ensure_ascii=False) + "\n")
        print(f"\n  gravado em {args.saida}")


if __name__ == "__main__":
    main()

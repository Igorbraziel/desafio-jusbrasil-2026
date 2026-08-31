"""Métrica local — APROXIMAÇÃO, a ser substituída pelo script oficial.

    ⚠ O script de avaliação oficial da organização sai em 01/09/2026. Este aqui
      é a nossa leitura da métrica descrita no material do desafio, escrito para
      termos um número antes disso. Quando o oficial chegar, troque este arquivo
      e compare os dois: divergência é sinal de que interpretamos alguma regra
      errado, e é melhor descobrir isso em setembro do que em outubro.

O que está descrito e implementamos aqui:

* alinhamento entre predição e gabarito por sobreposição de spans, IoU ≥ 0,5;
* F1 macro sobre as três classes, calculado por nível;
* penalidade dupla para classificar como ``real`` uma citação ``inventada``;
* ``real`` só conta com o ``id_canonico`` correto;
* bônus de calibração de até 10% para confiança bem calibrada (Brier baixo);
* score final: média ponderada dos níveis, peso 1× no nível 1 e 2× no nível 2.

O que **não** está especificado publicamente e escolhemos por conta própria:

* a forma exata do bônus de calibração — usamos ``f1 * (1 + 0,10 * (1 - Brier))``;
* o alinhamento guloso por maior IoU quando vários spans concorrem;
* contar a penalidade dupla como peso 2 no FP de ``real`` e no FN de ``inventada``.

Uso:
    python scripts/avaliar.py --predicoes data/out --goldenset data/dev/goldenset.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

CLASSES = ("real", "inventada", "incompleta")
LIMIAR_IOU = 0.5
PESOS = {1: 1.0, 2: 2.0}
PENALIDADE_DUPLA = 2.0
BONUS_MAXIMO = 0.10


@dataclass
class Item:
    inicio: int
    fim: int
    classificacao: str
    id_canonico: str | None
    confianca: float | None = None


def iou(a: Item, b: Item) -> float:
    intersecao = max(0, min(a.fim, b.fim) - max(a.inicio, b.inicio))
    uniao = (a.fim - a.inicio) + (b.fim - b.inicio) - intersecao
    return intersecao / uniao if uniao else 0.0


def alinhar(gabarito: list[Item], predicoes: list[Item]) -> list[tuple[int | None, int | None]]:
    """Casa predição com gabarito pelo maior IoU, acima do limiar."""
    pares = sorted(
        (
            (iou(g, p), i, j)
            for i, g in enumerate(gabarito)
            for j, p in enumerate(predicoes)
            if iou(g, p) >= LIMIAR_IOU
        ),
        key=lambda t: (-t[0], t[1], t[2]),
    )
    usados_g: set[int] = set()
    usados_p: set[int] = set()
    alinhamento: list[tuple[int | None, int | None]] = []
    for _, i, j in pares:
        if i in usados_g or j in usados_p:
            continue
        usados_g.add(i)
        usados_p.add(j)
        alinhamento.append((i, j))
    alinhamento += [(i, None) for i in range(len(gabarito)) if i not in usados_g]
    alinhamento += [(None, j) for j in range(len(predicoes)) if j not in usados_p]
    return alinhamento


def carregar_gabarito(caminho: Path) -> dict[str, tuple[int, list[Item]]]:
    docs: dict[str, tuple[int, list[Item]]] = {}
    for linha in csv.DictReader(caminho.open(encoding="utf-8")):
        doc = linha["documento_id"]
        nivel = int(linha["nivel"])
        item = Item(
            inicio=int(linha["inicio"]),
            fim=int(linha["fim"]),
            classificacao=linha["classificacao"],
            id_canonico=linha["id_canonico"].strip() or None,
        )
        docs.setdefault(doc, (nivel, []))[1].append(item)
    return docs


def carregar_predicoes(pasta: Path, documento_id: str) -> list[Item]:
    caminho = pasta / f"{documento_id}.json"
    if not caminho.exists():
        return []
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    itens: list[Item] = []
    for c in dados.get("citacoes", []):
        resolucao = c.get("resolucao") or {}
        itens.append(
            Item(
                inicio=int(c["inicio"]),
                fim=int(c["fim"]),
                classificacao=c["classificacao"],
                id_canonico=(
                    str(resolucao["id_canonico"]) if resolucao.get("id_canonico") else None
                ),
                confianca=c.get("confianca"),
            )
        )
    return itens


def f1_macro(tp: Counter, fp: Counter, fn: Counter) -> tuple[float, dict[str, float]]:
    por_classe: dict[str, float] = {}
    for classe in CLASSES:
        precisao = tp[classe] / (tp[classe] + fp[classe]) if tp[classe] + fp[classe] else 0.0
        recall = tp[classe] / (tp[classe] + fn[classe]) if tp[classe] + fn[classe] else 0.0
        por_classe[classe] = (
            2 * precisao * recall / (precisao + recall) if precisao + recall else 0.0
        )
    return sum(por_classe.values()) / len(CLASSES), por_classe


def avaliar(pasta_predicoes: Path, caminho_gabarito: Path) -> dict:
    gabarito = carregar_gabarito(caminho_gabarito)
    por_nivel: dict[int, dict] = {
        n: {
            "tp": Counter(),
            "fp": Counter(),
            "fn": Counter(),
            "brier": [],
            "confusao": Counter(),
            "criticos": 0,
        }
        for n in PESOS
    }

    for documento_id, (nivel, itens_gabarito) in sorted(gabarito.items()):
        acumulado = por_nivel[nivel]
        predicoes = carregar_predicoes(pasta_predicoes, documento_id)
        for i, j in alinhar(itens_gabarito, predicoes):
            esperado = itens_gabarito[i] if i is not None else None
            obtido = predicoes[j] if j is not None else None

            if esperado is None:  # predição sem par: falso positivo
                acumulado["fp"][obtido.classificacao] += 1
                acumulado["confusao"][("(nada)", obtido.classificacao)] += 1
                acumulado["brier"].append((obtido.confianca, False))
                continue
            if obtido is None:  # citação não detectada: erro de recall
                acumulado["fn"][esperado.classificacao] += 1
                acumulado["confusao"][(esperado.classificacao, "(nada)")] += 1
                continue

            acumulado["confusao"][(esperado.classificacao, obtido.classificacao)] += 1
            certo = esperado.classificacao == obtido.classificacao
            if certo and esperado.classificacao == "real":
                certo = esperado.id_canonico == obtido.id_canonico
            acumulado["brier"].append((obtido.confianca, certo))

            if certo:
                acumulado["tp"][esperado.classificacao] += 1
                continue
            # Chamar de real o que é inventada é o erro que um sistema em
            # produção precisa evitar: pesa dobrado.
            peso = (
                PENALIDADE_DUPLA
                if esperado.classificacao == "inventada" and obtido.classificacao == "real"
                else 1.0
            )
            if peso > 1:
                acumulado["criticos"] += 1
            acumulado["fn"][esperado.classificacao] += peso
            acumulado["fp"][obtido.classificacao] += peso

    resultado: dict = {"niveis": {}}
    soma_pesos = total = 0.0
    for nivel, acumulado in por_nivel.items():
        macro, por_classe = f1_macro(acumulado["tp"], acumulado["fp"], acumulado["fn"])
        com_confianca = [(c, ok) for c, ok in acumulado["brier"] if c is not None]
        brier = (
            sum((c - (1.0 if ok else 0.0)) ** 2 for c, ok in com_confianca) / len(com_confianca)
            if com_confianca
            else None
        )
        bonus = BONUS_MAXIMO * (1 - brier) if brier is not None else 0.0
        # O bônus é multiplicativo e o score fica limitado a 1: sem o teto, um
        # sistema bem calibrado pontuaria acima do máximo da métrica.
        score = min(1.0, macro * (1 + bonus))
        resultado["niveis"][nivel] = {
            "f1_macro": macro,
            "f1_por_classe": por_classe,
            "brier": brier,
            "score": score,
            "criticos": acumulado["criticos"],
            "confusao": acumulado["confusao"],
        }
        total += score * PESOS[nivel]
        soma_pesos += PESOS[nivel]
    resultado["score_final"] = total / soma_pesos if soma_pesos else 0.0
    return resultado


def imprimir(resultado: dict) -> None:
    for nivel, dados in sorted(resultado["niveis"].items()):
        print(f"\n─── Nível {nivel} (peso {PESOS[nivel]:.0f}×)")
        for classe in CLASSES:
            print(f"    F1 {classe:<11} {dados['f1_por_classe'][classe]:.4f}")
        print(f"    F1 macro       {dados['f1_macro']:.4f}")
        brier = dados["brier"]
        print(f"    Brier          {brier:.4f}" if brier is not None else "    Brier          —")
        print(f"    score          {dados['score']:.4f}")
        print(f"    inventada→real {dados['criticos']}  (erro crítico, pesa dobrado)")
        erros = {k: v for k, v in dados["confusao"].items() if k[0] != k[1]}
        if erros:
            print("    confusões:")
            for (esperado, obtido), n in sorted(erros.items(), key=lambda kv: -kv[1]):
                print(f"      {esperado:<11} → {obtido:<11} {n}")
    print(f"\n═══ SCORE FINAL (média ponderada 1×/2×): {resultado['score_final']:.4f}\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--predicoes", type=Path, default=Path("data/out"))
    p.add_argument("--goldenset", type=Path, default=Path("data/dev/goldenset.csv"))
    p.add_argument("--json", action="store_true", help="imprime o resultado em JSON")
    args = p.parse_args(argv)

    if not args.goldenset.exists():
        raise SystemExit(f"gabarito não encontrado: {args.goldenset} (rode `make dados`)")

    resultado = avaliar(args.predicoes, args.goldenset)
    if args.json:
        limpo = {
            "score_final": resultado["score_final"],
            "niveis": {
                n: {k: v for k, v in d.items() if k != "confusao"}
                for n, d in resultado["niveis"].items()
            },
        }
        print(json.dumps(limpo, ensure_ascii=False, indent=2))
    else:
        imprimir(resultado)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Avaliação local pela métrica **oficial** do Kaggle.

Este script não implementa a métrica. Ele carrega o ``kaggle_metric.py`` da
organização e delega o score a ele — o número que sai aqui é o número do
leaderboard. O que acrescentamos é o diagnóstico que o oficial não imprime:
matriz de confusão, τ e F1 por classe.

Por que não reimplementar: a versão anterior deste arquivo era a nossa leitura
da métrica escrita antes de o oficial sair, e **divergia** em três pontos — o
mais caro sendo a penalidade do erro grave, que no oficial é
``s = macroF1 × (1 − 0,5·τ)``, multiplicativa sobre o score do nível, e não peso
2 nas contagens. Ver docs/avaliacao.md.

O diagnóstico reusa ``_casar`` e os parsers do próprio oficial, e confere o
``macro_f1`` que acumula contra o que o oficial devolve — se divergir, avisa em
vez de mentir em silêncio.

Os arquivos da organização vivem em ``data/dev/ferramentas/``, que é gitignored:
num clone limpo é preciso rodar ``make dados-kaggle`` antes.

Uso:
    python scripts/avaliar.py --predicoes data/out
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from construir_solution import linhas_solution  # noqa: E402

FERRAMENTAS = RAIZ / "data" / "dev" / "ferramentas"
CLASSES = ("real", "inventada", "incompleta")
VAZIO = "-"


def carregar_modulo(caminho: Path, nome: str) -> ModuleType:
    """Importa um .py solto pelo caminho (os oficiais não são um pacote)."""
    if not caminho.exists():
        raise SystemExit(
            f"{caminho.name} não encontrado em {caminho.parent}.\n"
            "Rode `make dados-kaggle` para baixar as ferramentas da organização."
        )
    spec = importlib.util.spec_from_file_location(nome, caminho)
    if spec is None or spec.loader is None:  # pragma: no cover - caminho inválido
        raise SystemExit(f"não consegui carregar {caminho}")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def montar_submission(
    pasta: Path, documentos: list[str], encode
) -> tuple[list[dict[str, str]], list[str]]:
    """Empacota os JSONs de ``pasta`` no formato de submissão do Kaggle.

    Usa o ``encode`` do conversor oficial, para o CSV local ser exatamente o que
    seria submetido. Documento sem JSON entra com célula vazia e é reportado:
    localmente isso vira score baixo, mas o Kaggle **rejeita** a submissão
    inteira nesse caso.
    """
    linhas: list[dict[str, str]] = []
    ausentes: list[str] = []
    for documento in documentos:
        caminho = pasta / f"{documento}.json"
        if not caminho.exists():
            ausentes.append(documento)
            linhas.append({"documento_id": documento, "citacoes": VAZIO})
            continue
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        linhas.append({"documento_id": documento, "citacoes": encode(dados)})
    return linhas, ausentes


def diagnosticar(km: ModuleType, solucao: list[dict], submissao: list[dict]) -> dict[int, dict]:
    """Matriz de confusão e contagens por nível, pela mesma lógica do oficial."""
    por_nivel: dict[int, dict] = {}
    submissao_por_doc = {linha["documento_id"]: linha["citacoes"] for linha in submissao}

    for linha in solucao:
        documento = linha["documento_id"]
        nivel = int(linha["nivel"])
        acumulado = por_nivel.setdefault(
            nivel,
            {
                "tp": Counter(),
                "fp": Counter(),
                "fn": Counter(),
                "suporte": Counter(),
                "confusao": Counter(),
                "tau_num": 0,
                "tau_den": 0,
                "extra_ignoradas": 0,
            },
        )
        golds = km._parse_solution_cell(linha["citacoes"], documento)
        preds = km._parse_submission_cell(submissao_por_doc.get(documento, VAZIO), documento)
        pares, golds_sem_par, preds_sem_par = km._casar(golds, preds)

        for g in golds:
            acumulado["suporte"][g["classe"]] += 1
            if g["classe"] == "inventada":
                acumulado["tau_den"] += 1

        for gi, pi in pares:
            g, p = golds[gi], preds[pi]
            esperada, predita = g["classe"], p["classe"]
            acumulado["confusao"][(esperada, predita)] += 1
            if esperada == predita:
                if esperada == "real" and p["id_canonico"] not in g["doc_ids"]:
                    # link errado: custa precisão, não recall (§5.1)
                    acumulado["fp"]["real"] += 1
                    acumulado["confusao"][("real", "real (link errado)")] += 1
                    acumulado["confusao"][(esperada, predita)] -= 1
                else:
                    acumulado["tp"][esperada] += 1
            else:
                acumulado["fn"][esperada] += 1
                acumulado["fp"][predita] += 1
                if esperada == "inventada" and predita == "real":
                    acumulado["tau_num"] += 1

        for gi in golds_sem_par:
            acumulado["fn"][golds[gi]["classe"]] += 1
            acumulado["confusao"][(golds[gi]["classe"], "(não detectada)")] += 1

        casados = [golds[gi] for gi, _ in pares]
        for pi in preds_sem_par:
            p = preds[pi]
            if any(km._contida(p, g) for g in casados):
                acumulado["extra_ignoradas"] += 1  # regra EXTRA §6
                continue
            acumulado["fp"][p["classe"]] += 1
            acumulado["confusao"][("(espúria)", p["classe"])] += 1

    return por_nivel


def _f1(tp: int, fp: int, fn: int) -> float:
    denominador = 2 * tp + fp + fn
    return (2 * tp / denominador) if denominador else 0.0


def imprimir(oficial: dict, diagnostico: dict[int, dict], ausentes: list[str]) -> None:
    if ausentes:
        print(
            f"\n⚠ {len(ausentes)} documento(s) sem JSON em data/out/ "
            f"(ex.: {', '.join(ausentes[:3])}).\n"
            "  Localmente entram como 'sem citações'; o Kaggle REJEITA a submissão."
        )

    for nivel, dados in sorted(oficial["niveis"].items()):
        acumulado = diagnostico.get(nivel, {})
        print(f"\n─── Nível {nivel} (peso {km_peso(nivel):.0f}×)")
        for classe in CLASSES:
            f1_oficial = dados["f1_por_classe"].get(classe)
            suporte = acumulado.get("suporte", Counter())[classe]
            if f1_oficial is None:
                print(f"    F1 {classe:<11} —        (sem ocorrência)")
                continue
            print(f"    F1 {classe:<11} {f1_oficial:.4f}   (suporte {suporte})")
        print(f"    F1 macro       {dados['macro_f1']:.4f}")
        print(
            f"    τ              {dados['tau']:.4f}   ({acumulado.get('tau_num', 0)}"
            f"/{acumulado.get('tau_den', 0)} inventada→real)"
        )
        print(f"    penalidade     ×{1 - 0.5 * dados['tau']:.4f}  →  s = {dados['s']:.4f}")
        print(f"    bônus Brier    ×{1 + dados['b']:.4f}  →  score = {dados['score']:.4f}")
        if acumulado.get("extra_ignoradas"):
            print(f"    extras §6      {acumulado['extra_ignoradas']} ignoradas (não contam FP)")

        confusao = acumulado.get("confusao", Counter())
        erros = {k: v for k, v in confusao.items() if k[0] != k[1] and v}
        if erros:
            print("    erros:")
            for (esperada, predita), n in sorted(erros.items(), key=lambda kv: -kv[1]):
                print(f"      {esperada:<16} → {predita:<20} {n}")

        conferido = _conferir_macro(dados, acumulado)
        if conferido is not None:
            print(
                f"    ⚠ divergência no diagnóstico: acumulei {conferido:.4f}, "
                f"oficial {dados['macro_f1']:.4f}"
            )

    print(f"\n═══ SCORE FINAL (1×N1 + 2×N2)/3: {oficial['score_final']:.4f}\n")


def _conferir_macro(dados: dict, acumulado: dict) -> float | None:
    """Recalcula o macro-F1 pelo que acumulamos; devolve o valor se divergir."""
    if not acumulado:
        return None
    f1s = [
        _f1(acumulado["tp"][c], acumulado["fp"][c], acumulado["fn"][c])
        for c in CLASSES
        if acumulado["suporte"][c]
    ]
    if not f1s:
        return None
    nosso = sum(f1s) / len(f1s)
    return None if abs(nosso - dados["macro_f1"]) < 1e-9 else nosso


def km_peso(nivel: int) -> float:
    return {1: 1.0, 2: 2.0}.get(nivel, 1.0)


def avaliar(
    pasta_predicoes: Path,
    caminho_goldenset: Path,
    ferramentas: Path = FERRAMENTAS,
) -> dict:
    """Score oficial mais o diagnóstico, num dicionário só.

    ``niveis`` vem do ``kaggle_metric`` sem alteração — as chaves são as dele
    (``macro_f1``, ``tau``, ``s``, ``b``, ``score``). ``diagnostico`` traz as
    contagens e a matriz de confusão, e ``ausentes`` os documentos sem JSON.
    """
    import pandas as pd

    km = carregar_modulo(ferramentas / "kaggle_metric.py", "kaggle_metric")
    conversor = carregar_modulo(ferramentas / "json_to_submission.py", "json_to_submission")

    solucao = linhas_solution(caminho_goldenset)
    submissao, ausentes = montar_submission(
        pasta_predicoes, [linha["documento_id"] for linha in solucao], conversor.encode
    )

    try:
        oficial = km.avaliar(pd.DataFrame(solucao), pd.DataFrame(submissao))
    except km.ParticipantVisibleError as erro:
        raise SystemExit(f"a submissão seria rejeitada pelo Kaggle:\n  {erro}") from None

    return {
        **oficial,
        "diagnostico": diagnosticar(km, solucao, submissao),
        "ausentes": ausentes,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--predicoes", type=Path, default=Path("data/out"))
    p.add_argument("--goldenset", type=Path, default=Path("data/dev/goldenset.csv"))
    p.add_argument("--ferramentas", type=Path, default=FERRAMENTAS)
    p.add_argument("--json", action="store_true", help="imprime o resultado em JSON")
    args = p.parse_args(argv)

    if not args.goldenset.exists():
        raise SystemExit(f"gabarito não encontrado: {args.goldenset} (rode `make dados-kaggle`)")

    resultado = avaliar(args.predicoes, args.goldenset, args.ferramentas)

    if args.json:
        enxuto = {"score_final": resultado["score_final"], "niveis": resultado["niveis"]}
        print(json.dumps(enxuto, ensure_ascii=False, indent=2, default=float))
    else:
        imprimir(resultado, resultado["diagnostico"], resultado["ausentes"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

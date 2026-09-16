# 00 — Linha de base do pipeline

**Data:** 15/09/2026 · **Commit:** `04200b9` (na `main`)

## O que foi feito

Os quatro stubs viraram implementação, e a avaliação local passou a delegar à
métrica oficial do Kaggle em vez de reimplementá-la.

## A medição

```bash
make rodar && make avaliar
```

| | Nível 1 | Nível 2 (peso 2×) |
|---|---|---|
| F1 `real` / `inventada` / `incompleta` | 1,0000 / 1,0000 / 1,0000 | 1,0000 / 1,0000 / 1,0000 |
| F1 macro | 1,0000 | 1,0000 |
| τ (inventada→real) | 0 | 0 |
| score | 1,0990 | 1,0987 |

**Score final: 1,0988.** As 192 citações do gabarito detectadas, classificadas e
linkadas. `submission.csv` aceito por `kaggle_metric.score()` sem rejeição.

Detecção isolada: recall 192/192, precisão 192/192.
Índice (`scripts/medir_regiao.py`): recall 77/77, zero falso positivo nas
`inventada`, 2.231 números, **26 acórdãos sem número** e **282 números ambíguos**.

Custo: 0,5 ms/documento — o teto do regulamento é 60 s.

Os valores estão em `data/dev/baseline.json` para comparação automática.

## Como ler esse número

É a mesma amostra usada para construir a solução. `docs/dados.md § Riscos` lista
o que ela não mede: classes processuais não vistas, ruído de OCR fora do
subconjunto observado, e formas de `incompleta` diferentes do único padrão que
sobrou no gabarito. O leaderboard sobre o conjunto final é a primeira medida
honesta.

## O que mudou de decisão

Três achados da leitura do `kaggle_metric.py` mudaram o desenho, e estão em
`docs/decisoes/`:

1. A penalidade do erro grave é `macroF1 × (1 − 0,5·τ)`, multiplicativa sobre o
   score do nível — não peso 2 nas contagens, como nossa leitura anterior supunha.
2. Link errado num par `real`×`real` custa **só precisão**, sem FN. Isso inverteu
   a decisão sobre duplicatas: desempatar domina rebaixar para `incompleta`.
3. O bônus de calibração é limitado a zero por baixo, então emitir `confianca`
   nunca piora o score.

## O que ficou aberto

- Os **26 órfãos** e os **282 ambíguos** do índice, alvos da etapa 01.
- Nenhuma medida de comportamento fora desta amostra.

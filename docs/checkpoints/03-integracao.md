# 03 — Integração com a `main` e política de conteúdo

**Data:** 16/09/2026 · **Commit:** `2a5b455` · **Branch:** `parser-hierarquico`

## O que foi feito

Merge de `origin/main`, que havia avançado em paralelo com a distribuição final
de 15/09 e com a remoção de conteúdo derivado do gabarito.

Onze arquivos em conflito, resolvidos por critério e não por lado:

| arquivo | ficou com | por quê |
|---|---|---|
| `docs/dados.md`, `docs/investigacao.md` | `main` | já descreviam os padrões sem citar o conteúdo |
| `tests/test_base_canonica.py`, `test_deteccao.py` | `main` | números sintéticos, mesma cobertura |
| `scripts/baixar_dados.py` | `main` | mais completo; cobre o rename e o BOM |
| `scripts/avaliar.py` | esta branch | delega à métrica oficial em vez de reimplementá-la |
| `deteccao.py` | os dois | blocos complementares, nada a escolher |
| `resolucao.py` | os dois, com correção | ver abaixo |

## A política, que passou a valer aqui também

O repositório é público e o dataset não pode ser redistribuído. Documentação e
testes não reproduzem mais trecho de citação, `documento_id`, nome de relator
nem número do acervo — os exemplos passam a ser sintéticos, preservando o
**padrão** de ruído que ilustram.

O que foi higienizado deste lado: os três checkpoints, as três ADRs e os
comentários de `normalizacao.py`, `deteccao.py`, `base_canonica.py`,
`perturbar.py`, `construir_solution.py` e `test_estrutura.py`.

## A ADR 0003 estava errada

O desempate de duplicatas por maior `texto_len` vinha de três pares observados
na distribuição de 04/09. A revisão de 15/09 removeu dois deles e **reapontou o
par restante para o candidato mais curto**. Verifiquei contra os dados: a
regularidade era coincidência, e o único caso vivo a contradiz.

A decisão de **chutar em vez de rebaixar** continua — a assimetria da métrica é
real, e rebaixar custa duas classes contra uma. O que caiu foi o critério: a
ordenação segue determinística mas é declarada arbitrária, e a confiança do
caminho reflete isso.

**Erro de método, registrado para não repetir:** uma conclusão medida numa
distribuição foi carregada para a distribuição seguinte sem reverificação.
Quando os dados mudam, toda observação derivada deles volta a ser hipótese.

## Portões

| | |
|---|---|
| `uv run pytest -q` | 60 passed |
| `uv run ruff check . && ruff format --check .` | limpo |
| `make rodar && make avaliar` | **1,0988** |
| arquivos sob `data/` no push | **0** |

## O que ficou aberto

1. **Nada foi submetido ao Kaggle.** `data/submission.csv` está gerado e
   validado contra a métrica oficial, aguardando envio manual pela conta da
   equipe.
2. `ocr_numero` segue sendo o ponto fraco sob perturbação (checkpoint 02).
3. A fase 3 (dataset estrutural dos acórdãos) não começou.
4. Onde as duas abordagens estavam certas por motivos diferentes, ficou a desta
   branch; vale revisar com o Igor antes de fundir na `main`.

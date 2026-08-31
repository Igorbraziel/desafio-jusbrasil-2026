# 0001 — Baseline determinística, sem pesos de modelo

**Data:** 31/08/2026 · **Situação:** vigente

## Contexto

O regulamento permite modelos de pesos abertos e o envelope de avaliação tem uma
GPU de 24 GB. A tentação inicial é montar um pipeline com um LLM aberto fazendo
extração e classificação.

Mas a tarefa, lida de perto, não é de geração: a classe de uma citação é uma
*consequência da cardinalidade de uma consulta* a uma base fechada de 1.016
registros. `1 candidato → real`, `0 → inventada`, `≥2 sem desempate →
incompleta`. Um modelo não sabe o que está na cobertura congelada; a base sabe.

O que é genuinamente difícil é a **normalização de superfície** — casar
`R.Esp. n° 1.45g.779-MA` ao mesmo número que `Recurso Especial nº 1.459.779/MA`.
E isso é um problema de string, não de semântica.

## Decisão

Pipeline inteiramente determinístico: expressões regulares para detectar spans,
normalização de superfície para desfazer o ruído, e consulta por chave a um
índice pré-construído. Nenhum peso de modelo.

## Consequências

**A favor:**
- ~9 ms/documento contra um teto de 60 s. Roda em CPU; a máquina de
  desenvolvimento nem tem GPU.
- Reprodutibilidade trivial: nada de seed, temperatura ou revisão de HF para
  declarar. A verificação da organização (re-executar e comparar, tolerância de
  5%) é atendida por construção — a saída é bit a bit idêntica.
- Cada erro é rastreável até uma regra específica, o que torna o ciclo de
  depuração muito mais curto que ajustar um prompt.

**Contra:**
- Não generaliza para formas de citação que não anteciparmos. Ver *Onde isto
  provavelmente cai* em [../dados.md](../dados.md#onde-isto-provavelmente-cai).
- A lista de frases vagas é curada à mão e é o ponto mais frágil da solução.

## Quando revisitar

Se o conjunto cego trouxer formas de citação vaga fora da nossa lista, o recall
de `incompleta` cai e o F1 macro junto. O remédio natural seria um classificador
leve de pesos abertos aplicado **só a essa decisão** (é citação vaga ou é
prosa?), mantendo o resto determinístico. O manifesto do modelo já está no lugar
para receber a declaração.

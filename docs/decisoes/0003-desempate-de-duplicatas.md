# 0003 — Desempatar duplicatas em vez de rebaixar, sem critério defensável

**Data:** 15/09/2026, revista em 16/09/2026 · **Situação:** vigente, com a
justificativa original **refutada**

## Contexto

A regra de cardinalidade diz que 2 ou mais candidatos "sem critério de
desempate" é `incompleta`. A base de 15/09 ainda tem um número que é o número
próprio de dois registros distintos, e a pergunta é se vale chutar ou desistir.

## O que a métrica decide, e continua valendo

A leitura do `kaggle_metric.py` resolve a primeira metade por aritmética:

| escolha | custo na métrica |
|---|---|
| chutar `real` e errar o link | **só** `fp[real]` — precisão |
| rebaixar para `incompleta` | `fn[real]` **e** `fp[incompleta]` — duas classes |

Rebaixar custa estritamente mais, e o chute ainda tem chance de acertar. Então
chutamos. Essa parte da decisão não mudou.

## O que foi refutado

A versão original desta ADR desempatava pelo **maior `texto_len`**, apoiada em
três pares observáveis na distribuição de 04/09, em que o gabarito escolhia
sempre o registro mais longo.

A distribuição de 15/09 desfez isso de duas formas ao mesmo tempo: removeu dois
dos três pares — apagando em cada um o registro que o gabarito **não** escolhia,
o que elimina a escolha em vez de justificá-la — e **reapontou o par restante
para o candidato mais curto**.

Ou seja, a regularidade era coincidência de três observações, e o único caso que
sobrou a contradiz. A ressalva que a versão original trazia ("é pouca evidência
para uma regra") estava certa, e eu a ignorei ao promover a observação a
critério.

**Erro de método a não repetir:** a conclusão veio de uma tabela medida na
distribuição anterior e foi carregada para a nova sem reverificação. Quando os
dados mudam, toda observação derivada deles volta a ser hipótese.

## Decisão

`candidatos_por_numero` mantém ordenação determinística e a resolução pega o
primeiro candidato. A ordem é **estável e arbitrária**: serve para o resultado
ser reproduzível, não porque descreva o critério da organização.

A `confianca` desse caminho é deliberadamente baixa, bem abaixo da do caso de
candidato único, para que o Brier reflita que é um chute.

## Consequências

Errar o desempate custa uma citação em precisão, não duas classes. Com um par
ambíguo restante não há como inferir critério, e a alternativa de tratar
cardinalidade ≥ 2 como `incompleta` erraria esse caso com certeza em vez de
metade das vezes.

Fica como risco assumido para o conjunto cego, que pode ter mais pares.

## Quando revisitar

Se o `solution.csv` do Kaggle aceitar conjunto de `doc_ids` — o parser oficial
lê o campo como conjunto separado por `:` —, o desempate deixa de importar. Não
dá para verificar daqui; uma submissão resolve.

# Decisões de projeto

Um arquivo por decisão, numerado, com o contexto que a motivou e o que ela
custa. O ponto não é registrar *o que* foi feito — o código diz isso — mas *por
quê*, para dar como revisitar a decisão quando o contexto mudar.

Modelo sugerido:

```markdown
# 000N — Título curto no imperativo

**Data:** DD/MM/AAAA · **Situação:** vigente | substituída por 000M | abandonada

## Contexto
O que estava em jogo. De preferência com número medido, não impressão.

## Decisão
O que foi decidido, em uma ou duas frases.

## Consequências
O que melhora, o que piora, e o que passa a ser difícil de mudar.

## Quando revisitar
O sinal concreto que indicaria que a decisão envelheceu.
```

Decisões que valem registro neste desafio, quando forem tomadas: usar ou não
modelo de pesos abertos (e qual), como resolver duplicatas na base canônica,
qual o critério para separar distrator de citação, e como calibrar a confiança.

| # | Decisão | Situação |
|---|---|---|
| [0001](0001-baseline-deterministica.md) | Manter o pipeline determinístico, sem pesos de modelo | vigente |
| [0002](0002-ancora-no-numero.md) | Ancorar a detecção de processo no número, não na sigla | vigente |
| [0003](0003-desempate-de-duplicatas.md) | Desempatar duplicatas em vez de rebaixar | vigente; critério original refutado, desempate pela classe desde 24/09 |
| [0004](0004-ner-de-pesos-abertos.md) | Não usar NER de pesos abertos na detecção | vigente — medido e descartado |
| [0005](0005-base-nova-no-conjunto-cego.md) | Derivar do `.db` tudo o que é conteúdo da base | vigente |

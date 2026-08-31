# Avaliação

> ⚠️ **O script oficial sai em 01/09/2026.** Até lá,
> [`scripts/avaliar.py`](../scripts/avaliar.py) é a *nossa leitura* da métrica
> descrita no material do desafio. Quando o oficial chegar, substitua e compare
> os dois: divergência é sinal de que interpretamos alguma regra errado, e é
> melhor descobrir isso em setembro do que em outubro.

## Como as soluções são medidas

A avaliação é 100% automática, por um script público de referência executado
contra um gabarito interno mantido pela organização. O script é o mesmo da
avaliação oficial: todo score é reproduzível localmente.

- **Alinhamento por span.** Predição e gabarito casam por sobreposição com
  **IoU ≥ 0,5**. Não é preciso acertar a borda exata — mas quem não entrega o
  span de uma citação não consegue classificá-la, e isso conta como erro de
  recall.
- **F1 macro** sobre as três classes (`real`, `inventada`, `incompleta`),
  calculado **por nível**.
- **`real` exige o `id_canonico` correto.** Acertar o rótulo sem o doc_id certo
  não conta.
- **Penalidade dupla** para classificar como `real` uma citação `inventada` — o
  erro mais grave, porque é o que um sistema em produção precisa evitar.
- **Bônus de calibração de até 10%** para sistemas que reportam confiança bem
  calibrada (Brier score baixo).
- **Score final:** média ponderada dos dois níveis, peso 1× no nível 1 e 2× no
  nível 2.

## Leaderboard e ranking final

Durante as submissões, um leaderboard público atualizado em tempo real usa **40%**
do conjunto de teste. O ranking final é calculado sobre os **60% restantes**,
mantidos em sigilo até o encerramento. Otimizar demais para o leaderboard
público não garante nada no resultado final.

## O que nossa implementação escolheu por conta própria

Estes pontos não estão especificados publicamente. Estão isolados no topo de
[`scripts/avaliar.py`](../scripts/avaliar.py) para serem fáceis de trocar:

| Ponto | Nossa escolha |
|---|---|
| forma do bônus de calibração | `f1 × (1 + 0,10 × (1 − Brier))`, com teto em 1,0 |
| alinhamento quando vários spans concorrem | guloso pelo maior IoU |
| como contar a penalidade dupla | peso 2 no FP de `real` e no FN de `inventada` |
| predições sem par | falso positivo da classe predita; entram no Brier como erro |

## Como medir localmente

```bash
make rodar      # gera data/out/
make avaliar    # F1 macro por nível, Brier e score ponderado
```

O avaliador também imprime a matriz de confusão e a contagem de
`inventada`→`real`, que é o erro que pesa dobrado. Enquanto o pipeline estiver
incompleto, `make rodar` falha com `NotImplementedError` — é o esperado.

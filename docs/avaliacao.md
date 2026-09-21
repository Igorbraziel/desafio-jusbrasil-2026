# Avaliação

> ⚠️ **O script oficial está em `data/dev/ferramentas/kaggle_metric.py`.** A
> descrição abaixo foi lida dele, não do material de divulgação — e em três
> pontos ele **diverge** do que [`scripts/avaliar.py`](../scripts/avaliar.py)
> assumia. Enquanto `make avaliar` não apontar para o oficial, o número que ele
> imprime não é o do leaderboard.

## Como as soluções são medidas

Quatro passos, na ordem em que o `kaggle_metric.py` os aplica:

**1. Alinhamento.** Predição e gabarito casam por **IoU ≥ 0,5** em codepoints,
1-para-1, guloso pelo maior IoU. O limiar de 0,5 não é arbitrário: com ele, e
com as citações do gabarito disjuntas, uma predição não consegue casar com dois
golds ao mesmo tempo — é o que torna o guloso **ótimo**, não aproximado.

**2. F1 macro por classe, por nível**, com `f1 = 2·tp / (2·tp + fp + fn)`.
Classe sem ocorrência no nível fica fora da média.

**3. Penalidade do erro grave:** `s = macroF1 × (1 − γ·τ)`, com **γ = 0,5** e
**τ = fração das `inventada` do gabarito preditas como `real`**.

**4. Bônus de calibração:** `b = 0,10 × (1 − Brier)`, limitado a `[0; 0,10]`,
e `score = s × (1 + b)`. O Brier é calculado só sobre **pares casados** que
trazem `confianca`.

**Score final:** `(1 × score_N1 + 2 × score_N2) / 3`.

### A matriz de confusão, que é onde o dinheiro está

| caso | TP | FP | FN |
|---|---|---|---|
| casou, mesma classe, link ok | `tp[c]` | — | — |
| casou, ambos `real`, **link errado** | — | `fp[real]` | — |
| casou, classes diferentes | — | `fp[predita]` | `fn[esperada]` |
| predição sem par (espúria) | — | `fp[predita]` | — |
| gabarito sem par (span não extraído) | — | — | `fn[esperada]` |

Duas consequências que mudam a estratégia:

- **Classe errada custa duas vezes** — recall da esperada e precisão da predita.
  Ter extraído o span não salva o recall.
- **Link errado num par `real`×`real` custa só precisão**, sem FN. Errar o
  `id_canonico` é menos grave do que errar a classe.

### A regra EXTRA (§6), que não tínhamos

Predição sem par que seja **componente** de uma citação do gabarito já casada
(≥ 90% da sua largura contida nela) é **ignorada** — não conta FP. É tolerância
para granularidade a mais: entregar `art. 1.021` e `§4º` onde o gabarito anota
só um dos dois não é punido. Extração espúria que não encosta em gold casado
continua sendo FP.

### Emitir `confianca` não tem risco

`b` é limitado inferiormente a zero, então confiança mal calibrada dá `b = 0` —
o mesmo de não enviar. Não existe cenário em que enviar `confianca` piore o
score, e existe até 10% de upside. **Envie sempre.**

### Erros que invalidam a submissão inteira

O oficial levanta `ParticipantVisibleError` — não é perda de pontos, é rejeição:

- duas citações preditas no mesmo documento com **IoU ≥ 0,5** entre si;
- `classificacao=real` sem `id_canonico`, ou com `id_canonico` não numérico;
- span com `inicio < 0` ou `fim <= inicio`;
- bloco sem exatamente 5 campos;
- documento do gabarito **sem linha** na submissão (use `-` na célula).

## Leaderboard e ranking final

O leaderboard do Kaggle tem duas fases. Agora, enquanto o conjunto de avaliação
final está em construção, ele roda sobre a amostra de treino/desenvolvimento
(gabarito aberto) e é **referencial** — submissões desta fase **não contam**
para o ranking final. Quando o conjunto final for ativado, o leaderboard
**reinicia** e passa a usar a parte pública dele (**40%**); o ranking final é
calculado sobre os **60% privados** restantes, mantidos em sigilo até o
encerramento. Otimizar demais para qualquer um dos dois leaderboards públicos
não garante nada no resultado final.

## Onde o nosso avaliador erra

Comparando [`scripts/avaliar.py`](../scripts/avaliar.py) com o oficial:

| Ponto | Nossa suposição | Oficial |
|---|---|---|
| penalidade do erro grave | peso 2 no FP de `real` e no FN de `inventada` | **`macroF1 × (1 − 0,5·τ)`** — multiplicativa sobre o score do nível |
| bônus de calibração | `f1 × (1 + 0,10 × (1 − Brier))`, teto 1,0 | aplicado sobre `s` (pós-penalidade), **sem teto** no score |
| predições sem par | FP da classe predita; entram no Brier como erro | FP **exceto** pela regra EXTRA; **não** entram no Brier |
| alinhamento guloso | escolha nossa | igual — e é ótimo por causa do IoU ≥ 0,5 |

A primeira linha é a que mais importa. Na nossa versão, uma `inventada` virada
`real` polui duas contagens; na oficial ela reduz **o score inteiro do nível**
proporcionalmente. Com γ = 0,5, prever todas as `inventada` como `real` corta o
nível pela metade.

## Como medir localmente

```bash
make rodar      # gera data/out/
make avaliar    # ainda a métrica nossa — ver o aviso no topo
```

Enquanto o pipeline estiver incompleto, `make rodar` falha com
`NotImplementedError` — é o esperado.

Para usar o oficial é preciso montar o `solution.csv` que ele espera (uma linha
por documento, com `nivel` e as citações empacotadas em
`inicio,fim,classe,doc_ids`) a partir do `goldenset.csv`, e o `submission.csv`
com [`json_to_submission.py`](../data/dev/ferramentas/json_to_submission.py) a
partir de `data/out/`. Feito isso, o número local passa a ser o mesmo do
leaderboard.

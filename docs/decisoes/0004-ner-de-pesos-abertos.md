# 0004 — Não usar NER de pesos abertos na detecção

**Data:** 23/09/2026 · **Situação:** vigente — medido e descartado

## Contexto

A [ADR 0001](0001-baseline-deterministica.md) deixou aberta uma porta: se a
detecção por regras perdesse recall, um NER de pesos abertos **na detecção,
nunca na resolução** seria a resposta. O checkpoint 07 abriu essa porta e mediu.

**O modelo.** LeNER-Br é o corpus jurídico brasileiro cujas etiquetas
`LEGISLACAO` e `JURISPRUDENCIA` são exatamente o campo `tipo` do desafio. Não
existe no HuggingFace modelo aberto treinado para *detecção de citação jurídica*
em português; LeNER-Br é a aproximação disponível. Entre os treinados nele,
escolhemos o de licença explícita e sem pickle:

| | |
|---|---|
| `repo_id` | `Luciano/bertimbau-large-lener_br` |
| revisão | `c515eb0a38f2f464d0fdfd7d27049989aa83e1bc` |
| licença | MIT |
| arquitetura | BERTimbau large, 334M parâmetros, safetensors |

O concorrente com melhores métricas publicadas por entidade,
`pierreguillou/ner-bert-large-cased-pt-lenerbr`, **não declara licença** — risco
direto contra a regra de pesos abertos — e só distribui pickle.

**O desenho medido** foi o mais favorável possível ao modelo: ele só
*acrescenta*. Um span do NER entra apenas se começa depois do cabeçalho, não
sobrepõe nenhum achado das regras, e a resolução determinística consegue
classificá-lo. As regras nunca perdem nada para ele. Janela deslizante de 256
tokens com passo de 192, agregação BIO manual sobre `offset_mapping`
(codepoints), fusão dos fragmentos de subword separados só por pontuação.

## A medição

Contra a métrica oficial, nos corpora do arnês. Primeiro sobre a detecção como
estava no meio do checkpoint 07, depois sobre a versão final.

**Recall bruto nos 26 documentos limpos:** o NER acha **159 de 192** citações; as
regras, 192. Ele não acha nenhuma que as regras percam, e propõe **35 spans fora
do gabarito** — quase todos o número dos autos do próprio documento
(`Autos nº <número CNJ do próprio documento>`), que é o distrator canônico do desafio. O modelo não
tem a noção de cabeçalho: foi treinado em acórdão, onde o número do processo é
entidade.

**O híbrido contra as regras, pela métrica oficial:**

| corpus | regras (meio do cp 07) | + NER | regras (final) | + NER |
|---|---|---|---|---|
| dev limpo | 1,0992 | 1,0992 | 1,0992 | 1,0992 |
| `ocr_numero`, taxa 0,30, semente 1 | 1,0882 | 1,0939 | **1,0961** | 1,0939 |
| `ocr_numero`, taxa 0,30, semente 3 | 1,0692 | 1,0820 | **1,0873** | 1,0820 |
| todas (7), taxa 0,30, semente 3 | 1,0543 | 1,0641 | **1,0714** | 1,0641 |
| taxa 0,15, 5 sementes × 2 classes | — | — | igual ou melhor | +0,0012 em 2 de 10 |

Na primeira coluna o NER ajudava. Mas **cada citação que ele achava e as regras
não era um caso concreto** — número com dois dígitos reais sobreviventes
(`Recl. n° 7G.B4B/ BA`), artigo com o número todo corrompido. Viraram teste, a
regra foi estendida, e a vantagem sumiu: sobre as regras finais, o híbrido
**perde** em todos os corpora a taxa 0,30.

Perde porque o que sobra para o NER acrescentar são spans que a resolução
classifica errado. Os cinco que ele ainda acrescenta:

```
inventada   Reclamação nº Ii.l4s/SP            (é real sob o ruído; número sem dígito real)
inventada   Agravo Interno na Suspensão …      (span cortado no meio do número)
incompleta  artigo iBG do Códlgo Civil          (número sem dígito real, lido como vazio)
```

São exatamente os casos que as regras recusam **de propósito**: sem nenhum
dígito real, não há como distinguir um número corrompido de uma palavra — e
aceitar esses spans é o que produzia `(espúria) → real` antes do checkpoint 07.

**Custo.** 70 a 90 s para os 26 documentos em 4 threads de CPU, contra 0,025 s
das regras. Cabe no envelope de GPU da organização com folga, mas acrescenta
`torch` e `transformers` ao runtime, 1,3 GB de pesos por volume, a declaração no
`MANIFESTO_MODELO.md` e uma fonte de não-determinismo numérico entre CPU e GPU.

## Decisão

Não usar. O pipeline segue 100% determinístico, só biblioteca padrão em runtime,
e o `MANIFESTO_MODELO.md` continua declarando nenhum peso.

O experimento pagou o próprio custo mesmo assim: foi ele que apontou os dois
casos que a regra de dígitos suficientes passou a cobrir.

## Consequências

Mantém a reprodutibilidade trivial da ADR 0001. Em troca, a detecção continua
cega a formas que nenhuma expressão descreve — mas a medição mostra que, no
ruído que sabemos gerar, o modelo não as achava melhor.

## Quando revisitar

- Se o leaderboard sobre o conjunto final cair muito abaixo do arnês **com a
  queda concentrada em recall de span** — o mesmo gatilho da ADR 0001.
- Se houver tempo de fazer **fine-tune** com o gabarito da amostra mais o
  arnês como dado de treino. O modelo pronto erra por não conhecer o desafio
  (cabeçalho, distratores); um ajustado poderia não errar. Os pesos teriam de ser
  publicados, como exige o regulamento.

Os scripts da medição não entraram no repositório — dependem de `torch`, que o
projeto não tem. O desenho está descrito acima com detalhe suficiente para
refazer.

# Referências

Literatura que ajuda neste desafio, com o que cada trabalho entrega e se dá
para usar agora. Não é bibliografia: é lista de decisão.

> **Sem PDF no repositório.** Os artigos são de terceiros e o repositório é
> público. Aqui ficam só os links e o que nos interessa em cada um.

## O reenquadramento que organiza tudo

O desafio é **reconhecimento de entidades seguido de ligação a uma base, com
predição de NIL**. As três classes são os três desfechos possíveis de uma
ligação:

| classe | desfecho da ligação |
|---|---|
| `real` | a menção liga a um registro da cobertura |
| `inventada` | a menção não liga a nada, o caso NIL |
| `incompleta` | a menção liga a muitos, ou a nenhum por falta de dados |

Isso não é preciosismo de vocabulário. A literatura de NIL já mapeou o modo de
falha que é o centro deste desafio, e está descrito em *Predição de NIL* abaixo.

## Usáveis agora, sem custo de envelope

Estes três não exigem pesos, não mexem no tempo de execução e cabem no desenho
determinístico atual.

### Reconhecer constituintes, não a referência inteira

[Citation Data of Czech Apex Courts](https://arxiv.org/pdf/2002.02224) ·
Harašta et al., 2020. Também
[Annotated Corpus of Czech Case Law for Reference Recognition](https://link.springer.com/chapter/10.1007/978-3-030-00794-2_26).

Em vez de casar a referência como um bloco, os autores anotam e reconhecem seus
**constituintes** separadamente: tribunal, classe processual, número, data. Um
corpus de 350 decisões com mais de 50 mil anotações de constituintes.

O que ganhamos: o critério de `incompleta` deixa de ser um repertório de frases
e vira uma **contagem de constituintes encontrados**. Uma citação com tribunal,
ano e relator, mas sem número, é incompleta por construção, não por casar com
uma lista de expressões. Isso é exatamente o que a distribuição de 15/09 tornou
regra — ver [investigacao.md](investigacao.md#as-incompleta-são-hoje-uma-forma-só).

### Predição de NIL: não decidir por limiar

[Reveal the Unknown: Out-of-Knowledge-Base Mention Discovery with Entity Linking](https://www.cs.ox.ac.uk/people/ian.horrocks/Publications/download/2023/DongC0L023.pdf)
· Dong et al., 2023 (BLINKout). E
[Learn to Not Link: Exploring NIL Prediction in Entity Linking](https://aclanthology.org/2023.findings-acl.690.pdf)
· Zhu et al., Findings of ACL 2023.

O achado que mais importa aqui: **limiar fixo de similaridade falha justamente
nos quase-acertos**, e uma decisão aprendida é mais robusta quando a menção NIL
se parece com uma entrada existente da base. Uma citação `inventada` neste
desafio é um quase-acerto por construção — um número de processo plausível que
não está na cobertura.

O que ganhamos: a regra de decisão para `inventada` não pode ser "score de
casamento abaixo de X". Tem de ser o desfecho estruturado da busca por
constituintes: número normalizado ausente do índice é `inventada`; número
presente é `real`; número ausente da citação é `incompleta`. Decisão discreta,
não limiar.

O segundo artigo separa NIL em duas naturezas, entidade ausente e expressão que
não é entidade. Essa separação espelha a evolução do gabarito: o que era
"expressão que não é entidade" saiu nas duas revisões, e sobrou só entidade
ausente.

### Medir a resposta enganosa

[LegalCiteBench](https://arxiv.org/html/2605.10186v1) · 2026.

Traz a métrica *Misleading Answer Rate*: a proporção de respostas que dão uma
citação específica onde caberia abster-se. É o análogo direto de classificar
como `real` o que era `incompleta`.

O que ganhamos: um diagnóstico local barato para somar a
[`scripts/avaliar.py`](../scripts/avaliar.py), que hoje só dá F1 macro. Saber
*em que direção* erramos vale mais do que a nota agregada.

## Contingentes: só se a medição pedir

### Trocar regex por encoder na detecção

[Detecting Legal Citations in United Kingdom Court Judgments](https://aclanthology.org/2025.emnlp-main.1361.pdf)
· Sargeant, Östling e Magnusson, EMNLP 2025.

Primeira comparação sistemática dos três paradigmas na mesma tarefa de detecção
de citação jurídica:

| abordagem | F1 macro |
|---|---|
| melhor baseline de regex | 35,4 |
| GPT-4.1 | 76,6 |
| encoders ajustados (melhor: ModernBERT) | 93,3 |

**Ressalva importante.** O corpus deles é de quatro séculos de estilo real e
heterogêneo de citação. Nossos 26 documentos são sintéticos e bem mais
regulares, então regex vai muito melhor aqui do que esses 35%. Mas o conjunto
oculto "reflete o que aparece no mundo real", e o padrão de erro que eles
descrevem é o que devemos temer: padrão frouxo produz span grande demais, padrão
estrito perde o começo de nomes longos. O alinhamento por `IoU ≥ 0,5` perdoa
borda, não perdoa span truncado.

**Gatilho para adotar:** recall da detecção medido no goldenset. Se a detecção
determinística perder citação, o custo é erro de recall irrecuperável, e aí o
encoder se paga. Antes disso, não.

### Corpora em português, se o encoder entrar

- [LeNER-Br](https://teodecampos.github.io/LeNER-Br/) · Araujo et al., PROPOR
  2018. Corpus jurídico brasileiro anotado com as etiquetas `JURISPRUDENCIA` e
  `LEGISLACAO`, que são literalmente as duas categorias do campo `tipo` daqui.
  Há modelos prontos derivados dele.
- [Labor Lex](https://aclanthology.org/2025.nllp-1.14/) · NLLP 2025. Corpus da
  Justiça do Trabalho brasileira, útil porque o TST está na cobertura e é o
  tribunal que quebra heurística de posição — ver
  [investigacao.md](investigacao.md#onde-o-número-do-processo-aparece-na-base).

O regulamento permite pesos abertos e fine-tuning, desde que publicados e
executáveis offline pela organização. Adotar qualquer um destes exige atualizar
o [MANIFESTO_MODELO.md](../MANIFESTO_MODELO.md), que hoje declara nenhum peso, e
registrar uma decisão em [decisoes/](decisoes/).

### Arquitetura de referência para o pipeline inteiro

[Named Entity Recognition and Linking for Entity Extraction from Italian Civil Judgements](https://boa.unimib.it/retrieve/2b8252fd-3d21-48f4-81b1-2b4d717c0702/Pozzi-2023-AIxIA-AAM.pdf)
· Pozzi et al., AIxIA 2023.

Pipeline de três componentes sobre sentenças cíveis: NER, ligação, e um terceiro
dedicado à **predição de NIL**. É a forma exata do que este desafio pede, e
serve de referência de desenho mesmo sem adotar os modelos deles.

## Para a escrita final, não para o código

- [Large Legal Fictions: Profiling Legal Hallucinations in Large Language Models](https://arxiv.org/abs/2401.01301)
  · Dahl et al., Journal of Legal Analysis, 2024. A referência canônica para a
  tipologia de alucinação jurídica. Serve para situar o problema.
- [Who Checks the Citations? Benchmarking Legal Hallucination Detection](https://arxiv.org/html/2606.21155)
  · 2026. Taxonomia de cinco categorias de alucinação de citação. Mede que
  agentes detectam bem caso inexistente, acima de 80% de recall, e mal os erros
  finos. Confirma que a fronteira difícil não é "existe ou não".
- [Legal Linking: Citation Resolution and Suggestion in Constitutional Law](https://aclanthology.org/W19-2205/)
  · Shaffer e Ma, NLLP 2019. Vincula parágrafos de decisões a cláusulas
  constitucionais, com baselines de regra, linear e neural.

## O que decidimos não usar

- **Busca ao vivo em base externa.** Os trabalhos de verificação de citação
  (*Who Checks the Citations?*, e o de agentes) resolvem existência consultando
  CourtListener ou Westlaw ao vivo. Aqui o container roda **sem rede** e a
  cobertura é fechada por definição: um acórdão que existe no mundo mas não está
  na base é `inventada` para efeito do desafio. Consultar fora não só é proibido
  como daria a resposta errada.
- **LLM proprietário como verificador.** Proibido pelo regulamento, mesmo que a
  chamada parta do código submetido.

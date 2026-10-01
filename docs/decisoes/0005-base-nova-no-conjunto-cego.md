# 0005 — Derivar do .db tudo o que é conteúdo da base

**Data:** 30/09/2026 · **Situação:** vigente

## Contexto

Em 29/09 a organização avisou por e-mail como será a avaliação final: o código
submetido é executado sobre um **`.db` novo e um conjunto novo de documentos**,
no mesmo formato da amostra de desenvolvimento, e a nota sai dessa execução.
Até ali a leitura era que o conjunto cego seria avaliado contra a mesma base do
dev — o README dizia que as propriedades do índice valiam no conjunto cego
"porque a base é a mesma". O e-mail também permite enriquecer o `.db`, desde
que o código que gera o enriquecimento rode sobre o `.db` novo.

O que o código supunha da base do dev, medido em 30/09:

- **O índice dos acórdãos já era do banco.** A CLI o constrói do `.db` a cada
  execução (~1 s), e ele não depende nem do nome do tribunal: com a coluna
  `tribunal` vazia, ou trocada por outro tribunal, o dev segue em 1,1000.
- **Súmulas e dispositivos eram tabelas fixas** em
  [`base_canonica.py`](../../src/verificador/base_canonica.py): cinco súmulas e
  treze artigos, com os ids da base de 15/09, levantados à mão quando o texto
  desses registros era só o enunciado. Num banco alterado — sem uma súmula e um
  dispositivo, e com outro `id` num terceiro registro —, o pipeline continuava
  emitindo `real` com os ids antigos. Quarenta das 192 citações do dev passam
  por esse caminho.
- **A leitura do banco era frágil** num ambiente que não controlamos: um banco
  em modo WAL montado só leitura derrubava o lote inteiro (0 saídas); um
  caminho com caractere especial na URI, ou um registro com campo nulo,
  também derrubava. E, com o `--db` apontando para um arquivo que não existe, a
  CLI caía em silêncio num índice JSON antigo de `data/dev`.

A tabela fixa erra nas duas direções que a métrica pune. Um registro que saiu
da base continua `real`, com um `id_canonico` que não existe — é o erro que o
gabarito chamaria de `inventada` → `real`, o τ, que corta o score do nível
inteiro. E um registro que entrou fica de fora: `real` → `inventada`.

## Decisão

Separar o que é **conteúdo da base** do que é **conhecimento jurídico
público**, e tratar cada um de um jeito.

- **Conteúdo da base sai do `.db` recebido, em cada execução.** O índice de
  números próprios dos acórdãos, como antes. As súmulas e os dispositivos, pela
  primeira linha autodeclarada de cada registro, que a distribuição de 15/09
  acrescentou (`Súmula n. <número> do <tribunal>`, `Artigo <número> da Lei nº
  <número>, de <data>`). Quais registros existem e que `id` cada um tem nunca
  está no código. É esse o enriquecimento do `.db` que a regra permite: feito
  pelo próprio `run.sh`, sobre o banco no formato original, sem passo manual; o
  banco é só lido, e o que se deriva fica em memória.
- **Conhecimento jurídico público fica estático.** Um repertório de diplomas
  federais, por nome e sigla → (tipo, número, ano): CTN, CP, ECA, LEP, LINDB,
  Lei Maria da Penha, Lei das Eleições e outros. É o que liga "art. 121 do
  Código Penal" ao Decreto-Lei nº 2.848/1940, e o `.db` não traz isso: a
  primeira linha dá o número da lei, não o nome pelo qual as citações a chamam.
  Um artigo que exista no `.db` novo resolve para `real`; o que não existir sai
  `inventada`.

Junto com a decisão, quatro guardas que ela exige:

1. **Código estrangeiro não resolve para o brasileiro.** "Código Civil
   Português" casava o marcador do Código Civil. Com a cobertura vinda do banco,
   qualquer diploma que o repertório reconheça por engano vira `real`.
2. **Estatutos e leis citados pelo nome são detectados** ("Estatuto da Criança e
   do Adolescente", "Lei de Execução Penal"), e talvez súmula de tribunal
   regional: com a base nova, o artigo pode estar na cobertura.
3. **Número solto na prosa deixa de virar processo** ("1140 dias", "2.110
   metros", "art. 1.140 do Regimento Interno"). Com índice de outro banco, a
   chance de um número qualquer ser número próprio de algum acórdão muda.
4. **Leitura robusta do banco:** URI escapada; banco em modo WAL montado só
   leitura abre com `immutable=1`; registro com campo nulo não derruba a
   execução; `.db` inexistente é erro claro, não um índice antigo de reserva.

No código: `base_canonica._tabelas_de_sumulas_e_dispositivos` deriva as tabelas; `leis.py` guarda o repertório (`LEIS_NOMEADAS`, `LEIS_POR_NOME`, `SIGLAS_DE_LEI`); `resolucao._codigo_do_diploma` e `_codigo_estrangeiro` fazem as guardas.

## Consequências

**O que melhora.** A saída passa a acompanhar o banco. Súmula ou artigo que sai
da base deixa de ser `real`; o que entra passa a ser reconhecido; o `id` é o que
o banco diz. O banco alterado do diagnóstico é o teste que trava isso. E a
tabela deixa de ser mantida à mão: a última vez que a base mudou (15/09), ela
teve de ser reconferida contra o banco.

**O que continua fixo, e por quê.**

- **O repertório de diplomas.** Número e ano de uma lei federal não mudam com a
  base; são públicos (a Lei nº 13.105/2015 é o CPC em qualquer banco). O que o
  repertório não decide é se o artigo está na cobertura — isso é o banco.
- **O léxico da detecção**: classes processuais, siglas e nomes de tribunal,
  qualificadores de artigo, o repertório de ruído de OCR. É a forma de escrever
  uma citação, não o conteúdo da base.
- **A segmentação por tribunal** de [`estrutura.py`](../../src/verificador/estrutura.py),
  com um parser para cada um dos cinco superiores (STF, STJ, TSE, TST, STM),
  medidos nos 996 acórdãos do dev. Um tribunal fora deles passa pela ordem
  genérica.
- **A confiança por caminho**, medida no arnês e no simulador do sigiloso. Ela
  depende do caminho de decisão, não do conteúdo da base.

**O risco residual.**

- **Diploma fora do repertório citado só pelo nome** sai `inventada`, mesmo que
  o `.db` novo tenha o artigo. Citado pelo número da lei ("art. 10 da Lei nº
  1.234/2000"), ele casa com a primeira linha do registro e não depende do
  repertório. Fora da lista ficam, por exemplo, leis citadas por apelido pouco
  corrente; o repertório cobre os códigos e estatutos mais citados.
- **Tribunal fora dos cinco superiores** usa a segmentação genérica, que nunca
  foi medida em outro tribunal. Se o `.db` novo trouxer acórdãos de TRF ou TJ,
  o número próprio deles pode ficar fora do índice (a citação `real` sai
  `inventada`) ou, pior, um número citado pode entrar como próprio.
- **Primeira linha num formato que não conhecemos.** Se o `.db` novo trouxer
  súmulas ou dispositivos sem a linha autodeclarada, ou numa redação diferente,
  o registro não entra na cobertura, e a citação a ele sai `inventada`. O
  formato é o da distribuição de 15/09, e o e-mail diz que o formato é o mesmo.
- **O custo** é refazer a derivação em cada execução. Súmulas e dispositivos
  são poucos registros; o índice dos acórdãos, que já era refeito, domina o
  tempo (~1 s no dev).

## Quando revisitar

- Se a organização publicar o `.db` do conjunto final depois do ranking (o
  desafio vira benchmark público depois da conferência): medir quantas citações
  de súmula e dispositivo resolvem, quantos diplomas ficaram fora do
  repertório, e se a primeira linha manteve o formato.
- Se a base passar a trazer tribunais fora dos cinco superiores: medir a
  segmentação genérica neles, como o checkpoint 01 mediu os cinco.
- Se aparecer citação de diploma pelo nome, fora do repertório, que o banco
  cubra: a correção é acrescentar o diploma ao repertório, com o número e o ano
  públicos, e nunca o `id` do registro.

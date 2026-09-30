# O desafio

Verificação de citações jurídicas em pareceres gerados por IA — Jusbrasil em
parceria com o BRACIS 2026 (36ª Brazilian Conference on Intelligent Systems).

LLMs generativos já redigem pareceres, petições e memorandos. Um dos riscos mais
documentados é a alucinação de fontes: o modelo cita jurisprudência que não
existe, ou de forma vaga demais para ser verificada. Tribunais no Brasil e no
exterior já sancionaram advogados por protocolar peças com citações inventadas.
A tarefa é construir o verificador automático que falta nesse fluxo.

## A tarefa

Entrada: um `.txt` por parecer e a base canônica em `.db`. Saída: uma linha por
parecer no CSV de submissão, com o span, a classe, o `id_canonico` e a confiança
de cada citação. O JSON do contrato, com uma entrada por citação — o span, o
trecho literal, o tipo e a classe —, continua definido e é gerado sob pedido.
Ver [contrato.md](contrato.md).

| Classe | Definição |
|---|---|
| `real` | resolve a **exatamente um** registro da base canônica; exige `id_canonico` |
| `inventada` | identificadores suficientes para buscar, mas nenhum registro corresponde |
| `incompleta` | informação insuficiente para consultar, ou suficiente para buscar mas insuficiente para identificar um único registro |

A distinção entre `inventada` e `incompleta` importa em produção: a inventada é
alucinação ativa e deve ser bloqueada; a incompleta é evasiva e vai para revisão
humana.

## Níveis de dificuldade

| Nível | Peso | O que caracteriza | O que exige |
|---|---|---|---|
| 1 — formato padrão | 1× | citações canônicas (`REsp 1.234.567/SP`, `Súmula 7 do STJ`) | reconhecer e resolver o `id_canonico` |
| 2 — ruído e variação | 2× | erros de OCR, abreviações não-padrão, pontuação e números mal formatados, quebras no meio do identificador | normalização robusta antes de verificar |

O nível 2 pesa o dobro: é onde as soluções se diferenciam.

## Avaliação

100% automática, por script público de referência contra um gabarito interno.
A nota oficial sai da execução do código submetido, pela organização, sobre o
conjunto final (ver a seção seguinte). Ver [avaliacao.md](avaliacao.md).

## A entrega final (e-mail de 29/09/2026)

Em 29/09 a organização mudou a forma da avaliação final. É isto que vale agora.

**A nota vem da execução do código.** A organização roda o código submetido
sobre um **`.db` novo e um conjunto novo de documentos**, no mesmo formato da
amostra de desenvolvimento, aos quais as equipes não têm acesso. A métrica e os
scripts de avaliação são os mesmos ([avaliacao.md](avaliacao.md)). Não há
comparação entre CSVs, e o leaderboard do Kaggle não entra no ranking final.
Pequenas diferenças em `confianca` por variação de hardware são aceitas; a
organização recomenda fixar seeds e evitar amostragem não determinística.

**O que enviar**, para desafio-bracis@jusbrasil.com.br, até **01/10/2026, 23h59
(Brasília)** — horário em que o repositório com a versão final também precisa
estar disponível para a organização:

- nome da equipe e dos integrantes;
- link do repositório: público, ou privado com acesso de leitura para os
  usuários GitHub `dvianna`, `guardiaum`, `marinaramalhete`, `resendeacm` e
  `vickyaires`;
- o **hash do commit da versão final**, que identifica o que será executado.

**O que o repositório precisa conter**, e onde está neste:

| exigência | neste repositório |
|---|---|
| código completo | [`src/verificador/`](../src/verificador/), só biblioteca padrão em runtime |
| README com a abordagem e o passo a passo de execução | [README](../README.md), seções *Execução da avaliação final* e *Abordagem* |
| ambiente declarado (Docker) | [Dockerfile](../Dockerfile), com Python 3.12 fixado por digest |
| pesos dos modelos, incluídos ou referenciados em revisão fixa | não há pesos — [MANIFESTO_MODELO.md](../MANIFESTO_MODELO.md) |
| ponto de entrada único: recebe o `.db` e a pasta dos `.txt` e gera a saída no formato das submissões | [`run.sh`](../run.sh), na forma que a organização sugeriu: `bash run.sh <caminho_db> <pasta_txt> <arquivo_saida>` |

**Regras de execução**, somadas às da seção seguinte:

- GPU de até 24 GB de VRAM. Modelos usados só no desenvolvimento ficam fora
  desse limite.
- Offline: sem internet nem API externa.
- Do zero, em máquina limpa: sem caminho absoluto, passo manual ou arquivo que
  só exista na máquina da equipe.
- Enriquecer o `.db` é permitido, mas o código que gera o enriquecimento tem de
  rodar sobre o `.db` novo.
- Disco: bom senso, com ~100 GB de referência.

**O que isso mudou aqui.** Até 29/09 a entrega era o CSV enviado ao Kaggle, e o
bundle reproduzível só seria cobrado das finalistas. A leitura era que a base
do conjunto final seria a mesma do dev, e o código a supunha em um ponto:
súmulas e dispositivos eram tabelas fixas, com os ids da base de 15/09. Com um
`.db` novo, uma tabela fixa erra em silêncio. O [checkpoint 11](checkpoints/11-entrega-final.md) mede o problema e
a correção, e a [ADR 0005](decisoes/0005-base-nova-no-conjunto-cego.md)
registra a decisão: tudo o que é conteúdo da base sai do `.db` recebido, em
cada execução, e fixo no código fica só conhecimento jurídico público. O
enriquecimento que a regra permite é esse, feito pelo próprio `run.sh`.

## Regras de modelo e ambiente

- **Só pesos abertos.** Públicos, gratuitos e executáveis pela organização,
  declarados por link HuggingFace + revisão fixa (commit hash). Nada de API
  paga ou proprietária (GPT, Claude, Gemini e similares), mesmo que a chamada
  parta do código submetido. Servir um modelo de pesos abertos por API paga é
  permitido no desenvolvimento, desde que o mesmo modelo e revisão rodem
  offline a partir do repositório submetido.
- **Envelope de execução.** 1 GPU de 24 GB de VRAM (L4 / A10 / RTX 4090), ~8
  vCPUs, 32 GB de RAM. Média ≤ 60 s/documento, teto de 4 h no teste completo.
  Pipeline que não couber é considerado não-reproduzível e desclassificado. O
  e-mail de 29/09 reafirma o limite de 24 GB de VRAM e acrescenta disco de ~100
  GB como referência.
- **Offline.** O container roda sem rede. Nenhuma dependência de chamada externa
  em runtime. Como a base de referência é fechada, consultar sites oficiais ao
  vivo não faz sentido nem é permitido. A base da avaliação final é o `.db`
  novo que a organização monta no momento da execução.
- **Fine-tuning** é permitido, mas os pesos resultantes precisam ser publicados
  e executáveis pela organização.
- **Bibliotecas** de NER, regex e embeddings de pesos abertos são livres.
  Qualquer dataset público pode ser usado no treino.

## Submissão e reprodutibilidade

Submissão ao leaderboard do Kaggle (01 a 30/09): `submission.csv` gerado por
`json_to_submission.py` a partir das saídas. Múltiplas submissões eram
permitidas, respeitando o teto diário por **equipe**. Desde o e-mail de 29/09 o
leaderboard **não entra no ranking final**; ele serviu para validar o pipeline
de ponta a ponta.

**Bundle reproduzível — exigido de todas as equipes.** Pelas regras originais,
só as finalistas precisariam dele. Desde o e-mail de 29/09 ele é a própria
entrega: repositório com o código, README, referência dos modelos (link +
revisão), ambiente (Dockerfile), o ponto de entrada único que gera a saída a
partir do `.db` e dos `.txt`, e configuração de decodificação determinística
quando aplicável (ex.: `temperature=0`, seed fixa). Solução não reprodutível não
entra no ranking.

Verificação: entre 01 e 10/10 a organização executa o código no conjunto final
e confere a reprodutibilidade. As regras originais previam janela de recurso
após a divulgação preliminar do resultado, depois da qual as decisões da
organização são finais. Não rodar ou violar a regra de ferramentas abertas
desclassifica.

Neste repositório o bundle é o [`run.sh`](../run.sh), o
[Dockerfile](../Dockerfile), o [MANIFESTO_MODELO.md](../MANIFESTO_MODELO.md) e
as seções *Execução da avaliação final* e *Abordagem* do
[README](../README.md). A conferência em clone limpo, no container e em quatro
versões de Python está no [checkpoint 11](checkpoints/11-entrega-final.md).

## Cronograma

| Marco | Data |
|---|---|
| Envio dos dados por e-mail aos inscritos | 25/08/2026 |
| Webinar de tira-dúvidas (gravação disponível) | 28/08/2026 |
| Plataforma de submissão (Kaggle), script de avaliação e goldenset atualizado | 01/09/2026 |
| Distribuição final da amostra de desenvolvimento — não haverá novas versões | 15/09/2026 |
| Período de submissões ao Kaggle (leaderboard referencial, fora do ranking) | 01/09 a 30/09/2026 |
| E-mail da organização com as regras da entrega final | 29/09/2026 |
| **Fechamento das submissões: repositório e hash do commit final** | **01/10/2026, 23h59 (Brasília)** |
| Execução no conjunto final, verificação de reprodutibilidade e ranking | 01/10 a 10/10/2026 |
| Apresentação das melhores soluções (BRACIS 2026, Cuiabá-MT) | 19 a 22/10/2026 |

O fechamento era 30/09 no cronograma original; o e-mail de 29/09 o levou para
01/10, 23h59.

## A competição no Kaggle

A plataforma de submissão é o Kaggle:
<https://www.kaggle.com/t/b175ca36f02ce8d3a0422d3f7b339664>.

- **Conta:** uma conta Kaggle por pessoa — contas duplicadas desclassificam a
  equipe.
- **Entrar:** cada integrante acessa o link e clica em *Join Competition*,
  aceitando as regras.
- **Formar equipe (até 4 pessoas):** com todos já inscritos, um integrante abre
  a aba *Team* e convida os demais para o merge (ou aceita os pedidos). O nome
  definido ali é o que aparece no leaderboard.
- **Dados:** ficam na aba *Data* — os documentos (`txt/`), a base canônica, o
  gabarito da amostra de desenvolvimento, o conversor de submissão
  (`json_to_submission.py`) e o script oficial da métrica.
- **Submeter:** gerar `submission.csv` com `json_to_submission.py` a partir das
  saídas do pipeline e enviar em *Submit Prediction*. Qualquer integrante pode
  submeter — o limite é **5 submissões/dia por equipe** (soma de todos os
  integrantes), não por pessoa.
- **Leaderboard referencial, fora do ranking.** O leaderboard rodou sobre a
  amostra de treino/desenvolvimento (gabarito aberto) e serviu para validar o
  pipeline de ponta a ponta; **submissões ao Kaggle não contam para o ranking
  final**. O plano original previa uma segunda fase, com o leaderboard
  reiniciado sobre 40% do conjunto final e o ranking nos 60% privados. O e-mail
  de 29/09 a substituiu: o conjunto final não passa pelo Kaggle, e a nota sai
  da execução do código pela organização (ver
  [A entrega final](#a-entrega-final-e-mail-de-29092026)).

### Distribuição final do dataset (15/09/2026)

A organização publicou a versão final na aba *Data* e avisou que **não haverá
novas modificações** — imperfeições remanescentes fazem parte do cenário com que
a solução precisa lidar. Mudaram as três frentes: gabarito (192 citações), base
canônica (1.014 registros) e três dos 26 `.txt`. Ver
[dados.md § Atualização final](dados.md#atualização-final-15092026) para o diff
completo, levantado pelo próprio `make dados`.

Isso continua valendo para a **amostra de desenvolvimento**. O conjunto final é
outra coisa: vem com um `.db` próprio, que as equipes não veem. A base do dev
é um exemplo do formato, não a base em que a solução será avaliada.

Houve uma revisão anterior em 01/09, que endureceu o critério de `incompleta` —
ver [dados.md § Atualização do goldenset](dados.md#atualização-do-goldenset-01092026).
Qualquer cópia local anterior a 15/09 está desatualizada, inclusive o
`goldenset.xlsx` do e-mail de 25/08.

O dataset **não pode ser redistribuído**: foi liberado só às equipes inscritas e
não tem download público. Cada integrante baixa do Kaggle com a própria
credencial.

## Regras de participação

Individual ou em equipes de até 4 pessoas, apenas estudantes, do Brasil. A
elegibilidade dos integrantes é verificada pela organização — nas equipes
finalistas, só antes da divulgação do resultado, não na inscrição. A inscrição
no BRACIS 2026 não é pré-requisito, mas equipes vencedoras devem comparecer (ou
enviar representante) à sessão de encerramento.

**Desclassifica a equipe:** tentar extrair ou inferir o conjunto de teste
privado, plágio de solução de terceiros sem crédito, ou violar a regra de
ferramentas abertas (pesos/serviços fechados ou pagos em runtime). E, pela regra
de reprodutibilidade, a solução que não roda fica fora do ranking; o e-mail de
29/09 especifica que ela precisa rodar do zero, em máquina limpa.

**Publicação:** as melhores soluções são apresentadas no BRACIS 2026, e o
desafio é liberado como benchmark público depois da conferência — o que
inclui, presumivelmente, este conjunto de dados e o gabarito hoje fechados.

Dúvidas: desafio-bracis@jusbrasil.com.br ·
<https://challenge-bracis.production.jusbrasil.com.br/>

# O desafio

Verificação de citações jurídicas em pareceres gerados por IA — Jusbrasil em
parceria com o BRACIS 2026 (36ª Brazilian Conference on Intelligent Systems).

LLMs generativos já redigem pareceres, petições e memorandos. Um dos riscos mais
documentados é a alucinação de fontes: o modelo cita jurisprudência que não
existe, ou de forma vaga demais para ser verificada. Tribunais no Brasil e no
exterior já sancionaram advogados por protocolar peças com citações inventadas.
A tarefa é construir o verificador automático que falta nesse fluxo.

## A tarefa

Entrada: um `.txt` por parecer. Saída: um JSON por parecer, com uma entrada por
citação — o span, o trecho literal, o tipo e a classe. Ver
[contrato.md](contrato.md).

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
Ver [avaliacao.md](avaliacao.md).

## Regras de modelo e ambiente

- **Só pesos abertos.** Públicos, gratuitos e executáveis pela organização,
  declarados por link HuggingFace + revisão fixa (commit hash). Nada de API
  paga ou proprietária (GPT, Claude, Gemini e similares), mesmo que a chamada
  parta do código submetido. Servir um modelo de pesos abertos por API paga é
  permitido no desenvolvimento, desde que o mesmo modelo e revisão rodem
  offline a partir do repositório submetido.
- **Envelope de execução.** 1 GPU de 24 GB de VRAM (L4 / A10 / RTX 4090), ~8
  vCPUs, 32 GB de RAM. Média ≤ 60 s/documento, teto de 4 h no teste completo.
  Pipeline que não couber é considerado não-reproduzível e desclassificado.
- **Offline.** O container roda sem rede. Nenhuma dependência de chamada externa
  em runtime. Como a base de referência é fechada, consultar sites oficiais ao
  vivo não faz sentido nem é permitido.
- **Fine-tuning** é permitido, mas os pesos resultantes precisam ser publicados
  e executáveis pela organização.
- **Bibliotecas** de NER, regex e embeddings de pesos abertos são livres.
  Qualquer dataset público pode ser usado no treino.

## Submissão e reprodutibilidade

Submissão ao leaderboard: `.zip` com as saídas (via `submission.csv` gerado por
`json_to_submission.py`, ver acima). Múltiplas submissões são permitidas
durante todo o período, respeitando o teto diário por **equipe**.

**Bundle reproduzível — exigido das equipes finalistas** (não de toda
submissão): repositório com o código, README, referência dos modelos (link +
revisão), ambiente (requirements/Dockerfile), o comando exato que reproduz as
saídas submetidas, e configuração de decodificação determinística quando
aplicável (ex.: `temperature=0`, seed fixa). Solução não reprodutível não entra
no ranking.

Verificação: re-execução das top-N mais uma amostra, após o encerramento das
submissões, com janela de recurso após a divulgação preliminar do resultado —
depois dela, as decisões da organização são finais. Não rodar, não bater o
score ou violar a regra de ferramentas abertas desclassifica.

Neste repositório: [../Dockerfile](../Dockerfile),
[../MANIFESTO_MODELO.md](../MANIFESTO_MODELO.md) e a seção *Uso* do
[README](../README.md) — já preparados para servir de bundle reproduzível
quando chegarmos à fase final.

## Cronograma

| Marco | Data |
|---|---|
| Envio dos dados por e-mail aos inscritos | 25/08/2026 |
| Webinar de tira-dúvidas (gravação disponível) | 28/08/2026 |
| Plataforma de submissão (Kaggle), script de avaliação e goldenset atualizado | 01/09/2026 |
| Distribuição final do dataset — não haverá novas versões | 15/09/2026 |
| Período de submissões, leaderboard público ao vivo | 01/09 a 30/09/2026 |
| Fechamento das submissões | 30/09/2026, 23h59 (BRT) |
| Avaliação no conjunto privado, verificação e ranking final | 01/10 a 10/10/2026 |
| Apresentação das melhores soluções (BRACIS 2026, Cuiabá-MT) | 19 a 22/10/2026 |

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
- **Leaderboard em duas fases.** Enquanto o conjunto de avaliação final está em
  construção, o leaderboard roda sobre a amostra de treino/desenvolvimento
  (gabarito aberto) e é **referencial** — serve para validar o pipeline de
  ponta a ponta, e **submissões desta fase não contam para o ranking final**.
  Quando o conjunto final for ativado, o leaderboard **reinicia** e passa a
  usar a parte pública dele (40%); o ranking final é calculado sobre os 60%
  privados restantes, mantidos em sigilo até o encerramento.

### Distribuição final do dataset (15/09/2026)

A organização publicou a versão final na aba *Data* e avisou que **não haverá
novas modificações** — imperfeições remanescentes fazem parte do cenário com que
a solução precisa lidar. Mudaram as três frentes: gabarito (192 citações), base
canônica (1.014 registros) e três dos 26 `.txt`. Ver
[dados.md § Atualização final](dados.md#atualização-final-15092026) para o diff
completo, levantado pelo próprio `make dados`.

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
ferramentas abertas (pesos/serviços fechados ou pagos em runtime).

**Publicação:** as melhores soluções são apresentadas no BRACIS 2026, e o
desafio é liberado como benchmark público depois da conferência — o que
inclui, presumivelmente, este conjunto de dados e o gabarito hoje fechados.

Dúvidas: desafio-bracis@jusbrasil.com.br ·
<https://challenge-bracis.production.jusbrasil.com.br/>

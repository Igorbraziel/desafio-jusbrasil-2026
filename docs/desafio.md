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

Submissão ao leaderboard: `.zip` com as saídas. Toda submissão exige um bundle
reproduzível: repositório com o código, README, referência dos modelos (link +
revisão), ambiente (requirements/Dockerfile), o comando exato que reproduz as
saídas, e configuração de decodificação determinística quando aplicável.

Verificação: re-execução das top-N mais uma amostra. Score reproduzido não pode
cair mais que 5% (relativo). Não rodar, não bater o score ou violar a regra de
modelo desclassifica.

Neste repositório: [../Dockerfile](../Dockerfile),
[../MANIFESTO_MODELO.md](../MANIFESTO_MODELO.md) e a seção *Uso* do
[README](../README.md).

## Cronograma

| Marco | Data |
|---|---|
| Envio dos dados por e-mail aos inscritos | 25/08/2026 |
| Webinar de tira-dúvidas | 28/08/2026 |
| Plataforma de submissão, script de avaliação e detalhes da métrica | 01/09/2026 |
| Período de submissões, leaderboard público ao vivo | 01/09 a 30/09/2026 |
| Fechamento das submissões | 30/09/2026, 23h59 (BRT) |
| Avaliação no conjunto privado, verificação e ranking final | 01/10 a 10/10/2026 |
| Apresentação das melhores soluções (BRACIS 2026, Cuiabá-MT) | 19 a 22/10/2026 |

## Regras de participação

Individual ou em equipes de até 4 pessoas, apenas estudantes, do Brasil. A
inscrição na conferência não é pré-requisito, mas equipes vencedoras devem
comparecer à sessão. Múltiplas submissões são permitidas, respeitando o teto
diário. Tentativas de extrair ou inferir o conjunto de teste privado
desclassificam a equipe. O ranking final usa exclusivamente os 60% privados.

Dúvidas: desafio-bracis@jusbrasil.com.br ·
<https://challenge-bracis.production.jusbrasil.com.br/>

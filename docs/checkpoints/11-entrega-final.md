# 11 — Entrega final: ponto de entrada único e base nova

**Data:** 30/09–01/10/2026 · **Estado:** integrado na branch `entrega-final` (base `main` c7d1d71); verificação de entrega feita sobre o commit 088ade1

## Por que esta etapa existe

Em 29/09 a organização mudou a entrega por e-mail. A nota oficial sai da
**execução do código** sobre um **`.db` novo e documentos novos**, no mesmo
formato da amostra; não há comparação de CSVs, e o leaderboard do Kaggle não
entra no ranking. O repositório precisa de um ponto de entrada único, que
receba o `.db` e a pasta de `.txt` e grave a saída no formato das submissões, e
precisa rodar do zero, em máquina limpa, offline. Prazo: **01/10/2026, 23h59**.
Ver [desafio.md](../desafio.md#a-entrega-final-e-mail-de-29092026).

Duas perguntas, então: o repositório roda como a organização vai rodá-lo? E o
pipeline acompanha um banco que não é o do dev?

## O diagnóstico, antes das mudanças

Medido em 30/09 sobre o `main` c7d1d71.

**O que já estava certo:**

- 591 testes verdes; dev pela métrica oficial em **1,1000** (F1 1,0 nos dois
  níveis, τ = 0).
- 26 documentos em **1,6 s**, dos quais ~1 s é a construção do índice a partir
  do banco (1,4 s nesta máquina); o processamento é de ~2 ms por documento.
- Clone limpo + `docker build` + `--network none`: saída idêntica byte a byte à
  local. Idêntica também com `PYTHONHASHSEED` 1, 12345 e aleatório, e em Python
  3.11, 3.12 e 3.14.
- **O índice dos acórdãos não depende do nome do tribunal.** Com a coluna
  `tribunal` vazia, ou trocada por TRF1 ou TRT2, o dev segue em 1,1000. A
  segmentação cai na inferência pelo texto, que acerta os cinco superiores.

**O que estava quebrado:**

1. **A base era suposta.** Súmulas e dispositivos eram tabelas fixas no
   código, com os ids da base de 15/09. Com um banco alterado — sem uma súmula
   e um dispositivo, e com outro `id` num terceiro registro —, o pipeline
   continuava emitindo `real` com os ids antigos. **Quarenta das 192 citações
   do dev passam por esse caminho.** Num `.db` novo, um registro que saiu vira
   `real` com id inexistente (o erro do τ) e um que entrou vira `inventada`.
2. **Banco em modo WAL montado só leitura derrubava o lote inteiro** (0
   saídas). Num diretório só leitura, como o volume `:ro` do Docker, o SQLite
   não consegue criar os arquivos auxiliares do WAL ao lado do banco, e mesmo
   `mode=ro` falha ("attempt to write a readonly database"). A base do dev não
   está em WAL; a do conjunto final, não sabemos.
3. **Com `--db` inexistente, a CLI caía em silêncio** num índice JSON antigo de
   `data/dev`: a execução "funcionava" com a base errada. Numa máquina limpa não
   haveria JSON, mas o erro seria só "nem índice nem base".
4. **Não havia ponto de entrada que gerasse o CSV.** O container escrevia um
   JSON por documento, e o conversor oficial `json_to_submission.py` só existia
   fora do git, em `data/dev/ferramentas/`.
5. **Dois caminhos de leitura que derrubavam a execução**, medidos com um banco
   sintético. Um `#` no caminho do banco cortava a URI do SQLite: o resto,
   inclusive o `mode=ro`, virava fragmento, e ele abria — e criava — outro
   arquivo, vazio ("no such table: documentos"). E um registro com `texto`
   nulo parava a construção do índice com `TypeError`. Nos dois casos não sai
   nenhum documento, porque o índice é construído antes do lote.

As sondas sintéticas da mesma data acharam mais três formas que dependem da
base (os exemplos são sintéticos, nenhum aparece no dev):

| sonda | antes |
|---|---|
| "art. 186 do Código Civil Português" | `real`, com o id do art. 186 do Código Civil brasileiro |
| "art. 4º do Estatuto da Criança e do Adolescente" · "art. 112 da Lei de Execução Penal" · "art. 5º da LINDB" | nenhum span |
| "cumpriu 1140 dias" · "área de 2.110 metros" · "art. 1.140 do Regimento Interno" | processo `real`, com o id de um acórdão que tem esse número próprio |

A terceira linha é o risco que a base nova agrava: com outro índice, a chance de
um número solto na prosa coincidir com o número próprio de algum acórdão muda.

## As mudanças

Cinco frentes, cada uma com os testes que a motivaram, mais a branch `db-dinamico-e-run-sh` do João (955a538), que derivou súmulas e dispositivos do banco em paralelo e foi a versão adotada para essa parte.

**A — Ponto de entrada único.** `bash run.sh <caminho_db> <pasta_txt>
<arquivo_saida> [pasta_json]`. Grava o CSV no formato da submissão, byte a byte
igual ao do conversor oficial (cabeçalho `documento_id,citacoes`, uma linha por
documento, `-` no id ausente e no documento sem citação, confiança com 4
casas), e opcionalmente os JSONs do schema 1.2. Usa o Python ≥ 3.10 que houver
na máquina, ou `$PYTHON`; sem Python, ou com `VERIFICADOR_DOCKER=1`, roda via
Docker e constrói a imagem se preciso. Para com erro claro se o `.db` não
existir. Confere o CSV antes de terminar, com as checagens do avaliador. A
imagem recebe os mesmos três argumentos. `make entrega` roda o `run.sh` no dev e
pontua; `scripts/avaliar.py --submissao <csv>` pontua um CSV direto.

**B, C e D — Base nova.** A decisão está na
[ADR 0005](../decisoes/0005-base-nova-no-conjunto-cego.md): tudo o que é
conteúdo da base sai do `.db`, e fixo fica só conhecimento jurídico público.

- **Súmulas e dispositivos derivados do `.db`**, em cada execução, pela primeira
  linha autodeclarada de cada registro. A tabela fixa sai do código. É o
  enriquecimento do `.db` que a regra permite, feito pelo próprio `run.sh`.
- **Repertório de diplomas federais**, estático, por nome e sigla → (tipo,
  número, ano): CTN, CP, ECA, LEP, LINDB, Lei Maria da Penha, Lei das Eleições
  e outros. Um artigo que exista no `.db` novo resolve para `real`; o que não
  existir sai `inventada`.
- **Código estrangeiro** ("Código Civil Português") não resolve mais para o
  brasileiro.
- **Estatutos e leis citados pelo nome** passam a ser detectados, e súmula de
  tribunal regional. Entrou: TRF, TRT, TJ, TRE e TJM com a região ou a UF, e a TNU, em sigla ou por extenso, num padrão só da súmula.
- **Número solto na prosa** deixa de virar processo.
- **Leitura robusta do banco:** URI escapada; banco em modo WAL montado só
  leitura abre com `immutable=1`; registro com campo nulo não derruba a
  execução (itens 2 e 5 do diagnóstico).

Onde está cada coisa: `run.sh`, `src/verificador/submissao.py` (CSV e conferência) e o modo `--csv` de `cli.py` (A); `base_canonica._read_with_fallback` e `_normalize_row` (leitura robusta) e `_tabelas_de_sumulas_e_dispositivos`, `sumula_do_registro`, `dispositivo_do_registro` (tabelas do banco); `src/verificador/leis.py` (repertório: `LEIS_NOMEADAS`, `LEIS_POR_NOME`, `SIGLAS_DE_LEI`, `lei_pelo_nome`) e `resolucao._codigo_estrangeiro`; `deteccao._STATUTE_NAMES` e o tribunal regional em `sigla_do_tribunal` (C); `deteccao._is_prose_number` (D). Testes novos: `test_submissao.py`, `test_entrada_unica.py`, `test_base_derivada.py`, `test_db_novo.py`, `test_deteccao_leis.py`, `test_deteccao_processo.py`.

## A medição, depois das mudanças

Os comandos são os dos checkpoints anteriores: arnês com 5 sementes a 0,15 e 3 a
0,30; simulador com 20 sementes; espúrias e cobertura sobre os 996 acórdãos.
A coluna "antes" é o `main` c7d1d71, medido em 30/09 (arnês e simulador:
checkpoint 10).

| medição | comando | antes | depois |
|---|---|---|---|
| dev, métrica oficial | `make entrega` | 1,1000 (F1 1,0 · τ 0) | 1,1000 (F1 1,0 · τ 0) |
| simulador, sem ruído | `simular_sigiloso.py --sementes 20` | 1,1000 | 1,1000 (10 sementes) |
| simulador, ruído 0,05 no N2 | `… --ruido 0.05` | 1,0975 | 1,0949 (10 sementes; ver abaixo) |
| simulador, ruído 0,15 no N2 | `… --ruido 0.15` | 1,0877 | 1,0825 (10 sementes; ver abaixo) |
| arnês 0,15, todas (10) | `medir_robustez.py --taxa 0.15 --sementes 5` | 1,0850 | 1,0850 |
| arnês 0,30, todas (10) | `medir_robustez.py --taxa 0.30 --sementes 3` | 1,0655 | 1,0661 |
| pior semente a 0,30, todas (10) | idem | 1,0411 | 1,0428 |
| espúrias: `processo` | `medir_espurias.py --amostra 996` | 6.456 | 6.373 |
| espúrias: `sumula` | idem | 1.232 | 1.232 |
| espúrias: `tema` | idem | 683 | 683 |
| espúrias: `dispositivo` | idem | 2.147 | 2.165 |
| espúrias: `vaga` | idem | 51 | 51 |
| cobertura: únicos com o registro certo | `medir_cobertura.py` | 820 de 878 | 820 de 878 |
| cobertura: únicos com link errado / `inventada` | idem | 26 / 6 | 26 / 6 |
| cobertura: com cópia exata, registro certo | idem | 57 de 118 | 57 de 118 |
| banco alterado: `real` com id antigo | sonda do diagnóstico | sim, nos três registros | não: os removidos saem `inventada`, o id trocado sai novo |
| banco WAL montado só leitura | idem | lote inteiro derrubado (0 saídas) | abre com `immutable=1`; CSV idêntico (Docker, `--read-only`) |
| `#` no caminho do banco · registro com `texto` nulo | banco sintético | execução derrubada nos dois | URI escapada; registro ignorado com aviso |
| `.db` inexistente | `run.sh` com caminho inválido | CLI caía num índice JSON antigo | `run.sh` sai com código 1 e não grava CSV |
| tempo, 26 documentos | `run.sh` no dev | 1,6 s (~1 s de índice) | 1,5–1,7 s |
| testes | `uv run pytest -q` | 591 | 864 |

**O simulador com ruído caiu 0,003–0,006, e a queda é do instrumento, não do código.** O corpus de 30/09 pontua igual com o código antigo e o novo (1,0975 e 1,0884 nos dois). O que muda é o sorteio: desde 955a538 o simulador lê súmulas e dispositivos da base carregada, e a mesma semente gera outro corpus. Comparar o simulador entre versões exige fixar o corpus.

Na cobertura, "sem citação montada" (24 dos únicos) e "0 spans" são acórdãos em
que a expressão simples do script não monta a citação, não falhas do índice.
Nas cópias exatas, o desempate é uma moeda por construção (ADR 0003).

## A verificação de entrega

O que a organização vai fazer, feito antes por nós, sobre o commit final.
Commit verificado: **088ade1**. CSV do dev: sha256 `f89bcf50fd0142b3…`, o mesmo em todos os caminhos abaixo.

| verificação | como | resultado |
|---|---|---|
| clone limpo | `git clone` do remoto num diretório novo, sem `data/` nem `.venv` | ok — `git clone` local, sem `data/` nem `.venv`; `run.sh` gera o CSV |
| `run.sh` com Python 3.10 | `PYTHON=python3.10 bash run.sh …` | ok, CSV idêntico |
| `run.sh` com Python 3.11 | `PYTHON=python3.11 bash run.sh …` | ok, CSV idêntico |
| `run.sh` com Python 3.12 | `PYTHON=python3.12 bash run.sh …` | ok, CSV idêntico |
| `run.sh` com Python 3.14 | `PYTHON=python3.14 bash run.sh …` | ok, CSV idêntico |
| Docker | `docker build` + `docker run --rm --network none`, banco `:ro` | ok — clone limpo, `--network none --read-only --user`, CSV idêntico |
| `run.sh` sem Python no `PATH` | `VERIFICADOR_DOCKER=1 bash run.sh …` | ok no agente A (8dd2bf4), com imagem própria; não refeito em 088ade1 |
| determinismo | `PYTHONHASHSEED` 1, 12345 e aleatório; CSV comparado com `cmp` | ok, mesmo sha256 nas três sementes |
| mesmo CSV nos caminhos | local × Docker × quatro versões de Python, byte a byte | ok |
| conversor oficial | `json_to_submission.py` sobre a `pasta_json` × CSV do `run.sh` | ok, idêntico byte a byte |
| sem caminho absoluto nem arquivo local | `grep` por `/home`, `data/dev` e `~` no que o `run.sh` executa | ok — o clone limpo roda sem nada de `data/` |
| nada de `data/` no git | `git ls-files data` vazio; `tests/test_sem_gabarito.py` verde | ok, `tests/test_sem_gabarito.py` verde |
| acesso da organização | repositório público, ou leitura para os cinco usuários do e-mail | **PENDENTE** — dar leitura aos cinco usuários (ver o fim deste documento) |

Em 30/09, antes das mudanças, o clone limpo com o container já dava a mesma
saída da execução local, byte a byte, e o mesmo com as três sementes de hash e
em Python 3.11, 3.12 e 3.14. O Python 3.10 entrou na lista porque o `run.sh`
aceita qualquer Python ≥ 3.10 que houver na máquina; a CLI do `main` c7d1d71
já dava em 3.10 os mesmos 26 JSONs que em 3.12.

## O que ficou aberto

1. **Diploma fora do repertório citado só pelo nome** sai `inventada` mesmo que
   o `.db` novo tenha o artigo; citado pelo número da lei, casa com a primeira
   linha do registro. É o risco residual da ADR 0005.
2. **Tribunal fora dos cinco superiores** usa a segmentação genérica, nunca
   medida em outro tribunal. O índice não depende do nome na coluna, mas a
   estrutura de um acórdão de TRF ou TJ não foi vista.
3. **Primeira linha num formato novo.** Se o `.db` novo trouxer súmulas ou
   dispositivos sem a linha autodeclarada, o registro fica fora da cobertura.
4. **Os abertos do checkpoint 10 continuam:** cópias quase idênticas no STM
   (moeda), `inventada_processo` sob ruído extremo, entradas fora da forma do
   gerador e formas sem evidência no gerador.
5. **A nota oficial** sai entre 01 e 10/10, da execução da organização. É a
   primeira medida sobre o conjunto final, e a única que conta.

## O que falta para entregar (01/10/2026, até 23h59)

1. **Revisar e levar `entrega-final` ao `main`** (merge do PR) e fazer push.
2. **Dar leitura no GitHub** a dvianna, guardiaum, marinaramalhete, resendeacm e
   vickyaires (Settings → Collaborators), ou tornar o repositório público.
3. **Refazer a verificação de entrega no commit final do `main`**, a partir de um
   clone do remoto: `bash run.sh <db> <txt> <saida.csv>` e o `docker run` do README.
4. **Enviar o e-mail** para desafio-bracis@jusbrasil.com.br com o nome da equipe,
   os integrantes, o link do repositório e o **hash do commit final**.
5. Opcional: apagar a branch `db-dinamico-e-run-sh`, já incorporada (955a538).

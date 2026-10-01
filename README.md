# Verificador de Citações Jurídicas — Desafio Caça-Alucinações (BRACIS 2026 × Jusbrasil)

Lê pareceres jurídicos em `.txt`, encontra as citações de jurisprudência e de
lei e classifica cada uma contra a base canônica (`.db`):

| Classe | Quando |
|---|---|
| `real` | a citação resolve a **exatamente um** registro da base (`id_canonico` preenchido) |
| `inventada` | tem identificadores suficientes para a busca, mas **nenhum** registro corresponde |
| `incompleta` | não tem informação suficiente para consultar a base, ou sobram vários candidatos sem desempate |

## Execução

```bash
bash run.sh <caminho_db> <pasta_txt> <arquivo_saida>
```

O comando grava em `<arquivo_saida>` o CSV no formato das submissões
(`documento_id,citacoes`), byte a byte igual ao do conversor oficial
`json_to_submission.py`. Antes de terminar, o `run.sh` confere o CSV com as
checagens do avaliador. Um quarto argumento opcional, `[pasta_json]`, grava
também um JSON por documento.

O `run.sh` precisa de Python ≥ 3.10 e usa só a biblioteca padrão. Se a máquina
não tiver Python, ou com `VERIFICADOR_DOCKER=1`, ele roda pelo Docker e
constrói a imagem quando ela não existe.

O uso equivalente via Docker (`$DB`, `$TXT` e `$SAIDA` são caminhos absolutos
no host):

```bash
docker build -t verificador-citacoes .
docker run --rm --network none \
  -v "$DB":/dados/base.db:ro \
  -v "$TXT":/dados/txt:ro \
  -v "$SAIDA":/saida \
  verificador-citacoes /dados/base.db /dados/txt /saida/submission.csv
```

## Conformidade com as regras de execução

| Regra | Situação |
|---|---|
| Ambiente declarado | `Dockerfile` com imagem `python:3.12.3-slim` fixada por digest; sem dependências de runtime |
| Pesos de modelos | **nenhum modelo**: o pipeline é determinístico, então não há pesos para baixar |
| GPU ≤ 24 GB | não usa GPU; roda em CPU, em ~1,5 s para 26 documentos (quase todo o tempo vai na leitura do `.db`) |
| Offline | nenhuma chamada de rede; conferido com `docker run --network none` |
| Máquina limpa, sem caminhos absolutos | conferido com clone limpo e build do zero; os caminhos são os argumentos do `run.sh` |
| Enriquecimento do `.db` | feito pelo próprio `run.sh` em toda execução, sobre o banco no formato original (veja abaixo); o banco só é lido |
| Determinismo | sem amostragem; o `PYTHONHASHSEED` é fixo e todo desempate tem ordem explícita. A confiança é uma constante por caminho de decisão, por isso não varia com o hardware. A saída foi idêntica em Python 3.10–3.14, no container e com sementes de hash diferentes |

## Abordagem

A solução é determinística: usa expressões regulares, normalização e consulta
por chave, sem modelo de linguagem. **A classe não vem de um classificador:
ela é consequência da consulta à base.** O pipeline tem quatro etapas:

```
.txt ─▶ detecção ─▶ normalização ─▶ consulta à base ─▶ resolução ─▶ CSV
        spans de    desfaz ruído    índice derivado    1 registro   → real
        citação     de OCR          do .db recebido    0 registros  → inventada
                                                       vaga/ambígua → incompleta
```

1. **Detecção ancorada no número.** O span nasce no número do processo, da
   súmula, do tema ou do artigo e cresce para a esquerda enquanto houver
   prefixo (classe processual, tribunal, "art.", nome da lei). Assim, uma
   classe processual que nunca vimos ainda é detectada. Regras explícitas
   descartam o que tem cara de número mas não é citação: os autos do próprio
   documento, OAB, datas, folhas, valores e quantidades. Também há detecção de
   citações vagas, que mencionam uma decisão concreta (tribunal, relator, ano)
   sem o número; essas saem `incompleta`.
2. **Normalização do ruído.** Como um dígito nunca vira outro dígito, toda
   confusão de OCR (`0↔O`, `1↔l`, `5↔S`…) é reversível. Números com espaços,
   pontos ou quebras de linha voltam à forma canônica, e as siglas de tribunal
   e de lei são padronizadas.
3. **Base lida do `.db` recebido, em cada execução.** Nada da base fica
   embutido no código:
   - os **acórdãos** são indexados pelo número **próprio** de cada um, tirado
     do cabeçalho e das zonas que o identificam. Os números que o acórdão
     apenas cita ficam de fora;
   - as **súmulas** e os **dispositivos** vêm da primeira linha de cada
     registro (`Súmula n. 83 do STJ`, `Artigo 186 da Lei nº 10.406, de …`).

   No código fica só conhecimento jurídico público: um repertório de diplomas
   federais que liga nome e sigla a número e ano (Código Civil → Lei
   10.406/2002, LEP → Lei 7.210/1984 etc.). Lei fora do repertório resolve
   pelo número.
4. **Resolução pela cardinalidade.** Um candidato dá `real` com o
   `id_canonico` dele; nenhum dá `inventada`. Quando um número aparece em mais
   de um registro, o desempate usa a classe processual e o tribunal. Versões
   revogadas (CC/1916, CPC/73) e diplomas estrangeiros não resolvem contra os
   atuais, o que evita o erro grave da métrica (`inventada` predita como
   `real`).

No conjunto de desenvolvimento, pela métrica oficial, o resultado foi F1 macro
1,0 nos dois níveis, τ = 0, score 1,1000. Os mesmos documentos serviram para
construir a solução, por isso a robustez foi medida à parte:
- um arnês que degrada o texto em dez classes de ruído (score ≥ 1,04 a 30% de
  ruído);
- um simulador que troca as citações por outras da base;
- execuções sobre bancos alterados, com registros removidos, inseridos e com
  id trocado, em que a saída acompanha o banco.

Um NER de pesos abertos foi avaliado e descartado, porque baixava o score em
todos os cenários.

## Desenvolvimento

```bash
uv sync          # Python 3.12 + pytest/ruff (só para desenvolver)
make testar      # suíte de testes (864)
make lint        # ruff
make entrega     # roda o run.sh no conjunto de desenvolvimento e pontua pela métrica oficial
```

Os dados do desafio não podem ser redistribuídos e não estão no repositório.
`make dados` os baixa do Kaggle para `data/dev/` com a credencial de cada
pessoa. Os testes que dependem deles são pulados quando os dados não existem.

```
run.sh            ponto de entrada da avaliação (.db + pasta de .txt → CSV)
Dockerfile        imagem de execução, sem dados e sem pesos
src/verificador/  pipeline: deteccao · normalizacao · base_canonica · resolucao · leis · submissao · cli
scripts/          avaliação e instrumentos de robustez (arnês de ruído, simulador, cobertura)
tests/            especificação executável de cada etapa
```

O histórico do desenvolvimento está na tag
[`historico-desenvolvimento`](../../tree/historico-desenvolvimento/docs):
checkpoints, decisões de projeto e investigação dos dados.

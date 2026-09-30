# 11 — O banco novo da avaliação final e o ponto de entrada

**Data:** 30/09/2026 · **Estado:** branch `db-dinamico-e-run-sh`, sobre o `main` c7d1d71, para revisão antes do merge

## Por que esta etapa existe

O e-mail da organização de 30/09 trouxe duas regras que o repositório não
cumpria:

1. **A avaliação final usa um `.db` novo** e documentos novos, no mesmo formato
   da amostra.
2. **O ponto de entrada é único:** recebe o `.db` e a pasta de `.txt` e gera a
   saída no formato da submissão (o CSV). A sugestão deles é
   `bash run.sh <caminho_db> <pasta_txt> <arquivo_saida>`.

## O defeito: a cobertura de súmulas e dispositivos estava fixa no código

O índice dos acórdãos já era construído do banco em execução, pelo parser
estrutural de cada tribunal. As súmulas e os dispositivos, não: eram tabelas
curadas em `base_canonica.py`, com os ids do banco de dev. Com um banco
modificado (Súmula 83/STJ e art. 14 do CDC retirados; Súmula 7/STJ e art. 927
do CPC incluídos):

| citação | banco novo | antes | agora |
|---|---|---|---|
| Súmula 7 do STJ | tem | `inventada` | `real` (id novo) |
| Súmula 83 do STJ | não tem | **`real` (τ)** | `inventada` |
| art. 927 do CPC | tem | `inventada` | `real` (id novo) |
| art. 14 do CDC | não tem | **`real` (τ)** | `inventada` |

Súmulas e dispositivos eram 21% das citações do dev.

## A correção

- **A tabela sai do banco.** Cada registro abre com a própria identificação
  ("Súmula n. 83 do STJ", "Artigo 186 da Lei nº 10.406, de 10 de janeiro de
  2002"), e `construir_indice` monta a tabela dessa linha. Registro ilegível é
  avisado em stderr e fica fora.
- **O nome do diploma liga-se à lei por fato de direito**
  (`verificador/leis.py`: a Lei 10.406 é o Código Civil, o DL 5.452 é a CLT).
  Isso não depende da base.
- **O número da lei, quando citado, manda.** "Lei nº 9.504/1997" vira
  `LEI_9504` e "LC 135/2010" vira `LC_135`. Qualquer lei pode estar no banco
  novo. O tipo da lei tolera o ruído ("Dccreto-Lei").
- **Artigo com sufixo** ("41-A") tem chave própria. CPPM, CP, CTN, ECA e CTB
  ganham código, e quem decide se estão na cobertura é o banco.
- **Ponto de entrada:**
  - `run.sh` e `verificador/submissao.py`, que reproduz a codificação do
    `json_to_submission.py` oficial;
  - `--csv` no CLI;
  - o Docker com `run.sh` como entrypoint.

## A medição

- **Banco de dev:**
  - a tabela lida é idêntica à curada (que fica em `tests/conftest.py` como
    referência);
  - as 26 saídas são byte a byte iguais às do `main`, com dev 1,1 exato;
  - arnês, espúrias e acórdãos iguais.
- **Simulador:** em dois corpora sorteados, a 0,05 e a 0,15, a saída é idêntica
  à do `main`, arquivo por arquivo. Uma regressão apareceu e foi corrigida
  antes do commit: o decreto-lei corrompido virava uma "lei" de mesmo número.
- **Banco modificado:** `tests/test_db_novo.py` cobre súmula e artigo que
  entram e saem, lei sem nome conhecido, artigo com sufixo e o CPPM, que
  resolve sem vazar para o CPP.
- **CSV:** o do `run.sh` é igual, byte a byte, ao do conversor oficial.
- **Máquina limpa:** clone da branch, `docker build`, `docker run --network
  none`. Com o banco de dev, o CSV tem o mesmo sha256 do CSV submetido
  (`f89bcf50…`). Com o banco modificado, as classes da tabela acima.
- **Testes:** 591 → 626.

## A estratégia hierárquica, medida de novo

A comparação é do índice estrutural (zonas por tribunal) contra o posicional,
citando cada acórdão único da base pelo próprio cabeçalho:

| índice | resolve certo | vira `inventada` |
|---|---|---|
| posicional | 813 | 13 |
| estrutural | 820 | 6 |

Na mesma comparação, os números ambíguos caem de 116 para 97. O ganho é real
e pequeno, e vale igual no banco novo, porque o índice é construído dele.

## O que ficou aberto

1. **O formato do banco novo.** Se a primeira linha dos registros de súmula ou
   dispositivo mudar de forma, eles ficam fora da cobertura. O aviso em stderr
   é o sinal.
2. **Diploma citado por um nome que `DIPLOMAS` não conhece** ("Lei das
   Eleições", "Estatuto do Idoso") sem o número da lei: a citação não resolve
   e sai `inventada`.

# 10 — Validação final: o simulador do sigiloso e a entrega

**Data:** 29–30/09/2026 · **Estado:** branch `validacao-final`, sobre o `main` a93980d, para revisão antes do merge

## Por que esta etapa existe

A entrega é o próprio repositório. A organização o reexecuta no conjunto
sigiloso, e não rodar ou não bater o score desclassifica. Com o dev saturado, o
arnês tem um ponto cego: ele degrada as **mesmas** 192 citações. O sigiloso vem
do mesmo gerador, mas cita outras coisas: outros acórdãos dos 996 da base,
outros números inventados, outros relatores, outros artigos.

Esta etapa fez duas coisas: validou o caminho da entrega de ponta a ponta e
construiu um instrumento para esse ponto cego.

## O caminho da entrega

- **Container.** Um clone limpo da branch, construído com `docker build`, rodado
  com `docker run --network none` e só o banco montado, gera as 26 saídas
  **byte a byte idênticas** às locais.
- **Determinismo.** A saída é idêntica com `PYTHONHASHSEED` 1, 12345 e aleatório,
  e também em Python 3.12 e 3.14. O `.python-version` passa a fixar 3.12, a
  versão da imagem.
- **Fuzz.** Nenhuma queda e nenhum offset inválido pelo validador do contrato em
  arquivo vazio, só espaços, BOM, CRLF, latin-1, NFD, binário, NBSP, zero-width,
  soft hyphen, linha de 157 KB, 10 mil citações e "sopa de tokens".
- **Timeout.** O tempo cresce com o quadrado do tamanho: 0,7 s a 244 KB, e 1,26
  MB estourava o teto de 30 s. Os documentos do gerador têm de 3 a 4 KB e levam
  milissegundos. O teto subiu para 120 s.
- **Instrumentos e testes lendo um índice velho.** O `conftest.py`,
  `medir_robustez.py`, `medir_confianca.py` e `medir_cobertura.py` carregavam
  `data/dev/indice_cabecalhos.json`, e numa cópia local esse JSON era de 24/09
  (2.001 chaves, sem classe). O CLI constrói o índice do banco (1.190 chaves).
  Agora todos carregam pela mesma função do CLI.

## O simulador do sigiloso

`scripts/simular_sigiloso.py` usa os 26 documentos do dev como moldes. Cada
citação do gabarito é trocada por outra da mesma família e da mesma classe,
sorteada de um catálogo tirado da base:

- acórdãos pelo número e pela classe do cabeçalho;
- súmulas e dispositivos da tabela;
- vagas com o relator e o ano da base;
- inventadas fora do índice.

Cada citação sai numa das grafias que o gabarito mostra: sigla, extenso,
abreviação com ponto ou caixa alta; nº, n., No ou N°; número com ponto, sem
ponto, com espaço ou CNJ corrido; a UF em cinco formas; quebra de linha dentro.

O texto em volta é o do dev, então conectores, cabeçalho e ruído de prosa são
reais. A pontuação é a da métrica oficial. Com `--ruido`, o nível 2 passa
também pelo arnês.

**Limite do instrumento:** ele mede a generalização de conteúdo, não de forma.
Só gera as grafias que o catálogo conhece, e onde o dev não mostra a convenção
de borda (o tribunal depois do tema), a do simulador é uma hipótese.

O que ele mostrou na linha de base (20 sementes, 3.840 citações por rodada):

| ruído no nível 2 | F1 nível 1 | F1 nível 2 | score |
|---|---|---|---|
| nenhum | 1,0000 | 0,9995 | 1,0996 |
| 0,05 | 1,0000 | 0,9910 | 1,0932 |
| 0,15 | 1,0000 | 0,9715 | 1,0783 |

τ = 0 em tudo. Com conteúdo novo, o nível 1 é perfeito: 1.560 citações `real` de
processo em todas as grafias, de todos os tribunais. A perda do nível 2 vinha,
em ordem de tamanho:

1. do dispositivo que sumia com uma letra corrompida no qualificador ou no nome
   do diploma: 5% dos dispositivos a 0,05 e 16% a 0,15;
2. da borda e do ruído da vaga;
3. de bordas baratas.

## As correções

Cada correção é um commit, com o teste que a motivou.

| # | defeito | antes | agora |
|---|---|---|---|
| 1 | tribunal por extenso da súmula quebrado por linha ("Superior Tribunal\nde Justiça") | a súmula perdia o tribunal (IoU 0,24) | span inteiro, `real` |
| 2 | tribunal depois do tema ("Tema 1.046 do STF") | IoU 0,53–0,59 | 1,00 |
| 3 | o número engolia a palavra da frase seguinte ("REsp 1.234.567. O recurso") | IoU < 1; nos acórdãos, "2015. II" virava processo | ponto e palavra fora |
| 4 | primeira linha do corpo sem vírgula lida como cabeçalho ("Como decidido no REsp…") | citações da linha perdidas; o número dos autos vazava | corpo |
| 5 | letra corrompida no qualificador ou no diploma ("iriciso", "eaput", "parágraf0 únic0", "Deereto-Lei", "da5 Leis") | dispositivo inteiro sumia | detectado |
| 6 | conector corrompido no nome do diploma ("Defesa d0 Consumidor"), e "Código do Consumidor" | `real` → `inventada` | `real`; CPPM e código estadual continuam recusados |
| 7 | vaga: "Recurso Extraordinário com Agravo", "AgInt no AREsp de 2024", tribunal por extenso, "Rel. Min°", inicial do nome corrompida ("rnAURO") | borda errada ou vaga perdida | span inteiro |

A causa do defeito 4 é a forma "Rótulo nº número" do cabeçalho: o "no" da
preposição tem a forma da marca "nº". O valor depois da marca passa a não
aceitar palavra minúscula de quatro letras ou mais.

## A confiança

Foi recalibrada com o simulador como evidência a mais, somando o arnês nas duas
taxas e o simulador em três:

| caminho | acertos | Laplace |
|---|---|---|
| `real` | 6.643/6.643 | 0,99985 |
| `incompleta_vaga` | 2.239/2.239 | 0,99955 |
| `inventada_tabela` | 1.460/1.461 | 0,9986 |
| `inventada_processo` | 2.936/2.978 | 0,9856 |
| `inventada_tema` | 66/66 | 0,985 |

Com milhares de acertos o teto de 0,99 perde a razão. O teto vira 0,999, e o dev
vai a 1,099990.

Depois, por decisão da equipe, os caminhos que o dev exercita passam a emitir
**1,0**, e o dev fica em **1,1000 exato**. A confiança não muda classe nem span,
então F1 e τ no sigiloso ficam idênticos. Pela acurácia medida, o custo esperado
no Brier de lá é da ordem de −0,00002. Medido: arnês e simulador sob ruído ficam
iguais à versão calibrada ("todas (10)" a 0,30 dá 1,0655 nas duas). A moeda entre
cópias (`real_desempate`) fica em 0,5. O commit é isolado, e revertê-lo devolve
a calibração pela acurácia.

`medir_confianca.py` passou a medir com um valor-sentinela por caminho: separava
os caminhos pelo valor emitido, e caminhos com o mesmo valor saíam como
AMBÍGUO. Com isso, `real_unico` e `real_tabela` aparecem separados pela primeira
vez.

## A medição

**Dev, métrica oficial:** F1 1,0000 nos dois níveis, τ = 0, score
1,099942 → **1,100000**.

**Arnês** (0,15 com 5 sementes; 0,30 com 3):

| classe | 0,15 antes | 0,15 agora | 0,30 antes | 0,30 agora |
|---|---|---|---|---|
| `ocr_palavra` | 1,0999 | 1,1000 | 1,0942 | **1,0986** |
| `ocr_letra_digito` | 1,0950 | 1,0951 | 1,0936 | **1,0965** |
| `ocr_curta` | 1,0846 | **1,0880** | 1,0811 | 1,0815 |
| todas (10) | 1,0825 | **1,0850** | 1,0593 | **1,0655** |
| pior semente, todas (10) | 1,0689 | 1,0702 | 1,0325 | **1,0411** |

As demais classes estão em 1,1000 (1,0993 a 1,0999 antes, só pela confiança).

**Simulador** (20 sementes):

| ruído no nível 2 | F1 nível 2 antes | F1 nível 2 agora | score antes | score agora |
|---|---|---|---|---|
| nenhum | 0,9995 | **1,0000** | 1,0996 | **1,1000** |
| 0,05 | 0,9910 | **0,9969** | 1,0932 | **1,0975** |
| 0,15 | 0,9715 | **0,9843** | 1,0783 | **1,0877** |

**Diferencial nos 996 acórdãos** (os primeiros 30 mil caracteres de cada um):

- de 78.005 para 77.843 spans, sem **nenhuma** mudança de classe ou de link;
- 193 spans espúrios saem (ano que engolia "II" ou "O");
- 313 bordas ficam mais justas: 184 temas ganham o tribunal, 129 processos
  perdem a palavra da frase seguinte;
- entram 25 dispositivos com alínea entre aspas, todos `inventada` e corretos.

**Volume** (`medir_espurias.py --amostra 996`): `processo` 6.509 → 6.456, as
demais famílias iguais.

**Testes:** 556 → 591.

## O que ficou aberto

1. **Cópias quase idênticas no STM.** Em 10 dos 191 acórdãos do STM, dois
   registros têm o mesmo cabeçalho e a mesma classe, e o desempate é uma moeda
   (ADR 0003).
2. **`inventada_processo` sob ruído extremo.** Os 8 erros do arnês a 0,30 são
   números sem quase nenhum dígito real ("0G0lZ3S-q1.2O2O.b.0S.0Oo0", um número sintético no mesmo estado), o resíduo
   do cp 07.
3. **Entradas fora da forma do gerador:** CRLF no meio de um número parte a
   citação em duas; arquivo em latin-1 perde os acentos; documento todo em caixa
   alta. Os arquivos do gerador são UTF-8 com LF.
4. **Formas sem evidência no gerador, não tratadas:** plurais ("arts. 5º e 7º",
   "Súmulas 83 e 211"), ordem inversa ("CF, art. 5º"), "Segundo AgR" (IoU 0,74),
   "art. 276 do CE", relator com "DESEMBARGADOR CONVOCADO DO TJSC" (IoU
   0,77–0,95) e vaga sem relator.
5. **Revisão independente por subagentes:** três revisores, um por família,
   foram lançados e interrompidos pelo limite de uso antes de reportar. O
   simulador e as sondas cobriram o mesmo terreno.

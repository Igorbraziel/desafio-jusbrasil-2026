# 09 — Revisão final: τ, índice, desempate e o ruído que o arnês não gerava

**Data:** 24–25/09/2026 · **Estado:** sete etapas na branch `revisao-final`, sobre a `pente-fino-prefixo-e-constituicao`

## Por que esta etapa existe

Com o dev saturado em 1,1000 e o arnês saturado a 0,15, medir acerto no dev não
informava mais nada. Esta etapa procurou erro onde o conjunto cego pode ter e a
amostra não tem, com quatro instrumentos novos:

1. **Sondas sintéticas** passadas pelo pipeline, uma forma por vez.
2. **Autocitação** (`scripts/medir_cobertura.py`): cada um dos 996 acórdãos é
   citado pelo próprio cabeçalho, e o script mede se ele volta resolvido. É o
   índice visto do lado de quem cita, sobre a base inteira.
3. **Auditoria das chaves do índice**: cada chave faz um acórdão responder como
   `real`, e uma chave que não é o número do próprio processo torna `real` uma
   citação `inventada`.
4. **Três classes novas no arnês** para formas que o nível 2 da amostra mostra e
   que o arnês não gerava: letra trocada por dígito ("5úmula", "C0NTROVÉRSIA"),
   sigla de tribunal corrompida ("5TJ") e palavra curta corrompida ("dc", "d0").

Quanto custa cada erro no score final, pela função oficial, num nível 2 do
tamanho do dev: `inventada` → `real` (τ) −0,0187; `incompleta` não detectada
−0,0074; `real` → `inventada` −0,0073; span espúrio −0,0038; link errado
−0,0035; `real` não detectada −0,0028. Um τ vale mais que cinco links errados, e
a ordem das etapas seguiu isso.

## As etapas

**0. A branch do colega.** Boa e usada como base: lote que sobrevive a um
documento ruim, órgão julgador fora do prefixo, tribunal da súmula em outras
grafias, regressão da CF do cp 07 desfeita. Três correções: "Federal" saiu do
léxico que para a cadeia (cortava "Intervenção Federal nº"), "Cidadã" entrou na
CF/88, e a tabela do cp 08 atribuía à branch um ganho que já estava no `main`.
Números de citação do gabarito tinham voltado a comentários e testes;
`tests/test_sem_gabarito.py` passa a travar isso.

**1. Caminhos de τ.** "CPPM" casava "CPP"; o nome longo ou corrompido do CPPM
perdia o "Militar"; "Constituição da República Portuguesa" virava a CF/88;
"art. 896-A" virava o art. 896; "Súmula Vinculante 10 do STJ" virava a SV 10;
tema com a espécie no meio caía na família processo; lei com ano de dois
dígitos virava processo `real`; "LC nº 64/90" saía `inventada`.

**2. Higiene do índice.** A âncora da fórmula do TST casava "destes autos" na
ementa (nove acórdãos sem o próprio número no índice). Saíram datas, OAB, lei
com ano curto, a ementa do cabeçalho do TST, o rol de partes, os números com
rótulo de artigo, tema ou súmula, os pedaços de número partido por espaço e os
anos soltos. Número longo passou a contar textos distintos no corte de donos.

| | chaves | ambíguas | sem número | recall gabarito | falso positivo |
|---|---|---|---|---|---|
| antes | 2.001 | 239 | 25 | 77/77 | 0 |
| depois | 1.190 | 97 | 1 | 77/77 | 0 |

Vinte e uma sondas de chave-lixo (`AR 2.019`, `ADI 1.717`, `Rcl 22.271`, `HC nº
604.005`, `Lei Federal nº 9.504/97`…) passaram de `real` para `inventada`.

**3. Desempate pela classe processual.** Os acórdãos que dividem um número
próprio são cópias ou incidentes do mesmo processo (o recurso e o agravo interno
nele). O índice guarda a classe do cabeçalho, e a resolução escolhe pela
concordância com o prefixo da citação: 16 de 19 pares de incidentes, contra 10
do desempate por tamanho. ADR 0003 revista.

**4. Ruído de OCR em palavra-chave, sigla e conector curto.** `_tolerante`
aceita o dígito no lugar da letra; a sigla do tribunal aceita o `5`; um conector
único aceita "d0", "dc", "dã"; o pedaço final do número que é palavra
corrompida sai ("2020 5ob"); Goiás corrompido ("/G0") é lido como UF.

**5. Formas correntes, borda da `vaga` e coordenadas.** "SV 10", "Enunciado 331
do TST", "Súmula 331, item IV", "do C. STJ", "novo CPC", "Lei Maior", "art. 5º,
LV, CF". O nome do relator deixou de engolir a frase seguinte — as 192 citações
do dev passam a casar com IoU 1,000 (o mínimo era 0,854). Citação coordenada
("art. 5º da CF e REsp …") deixou de sumir. Inscrição na OAB colada à UF
("SP254779") deixou de virar processo: 892 spans a menos nos acórdãos reais.

**6. Operação e entrega.** Timeout por documento (30 s); `.TXT` aceito; CRLF
lido sem traduzir; o CLI constrói o índice do banco quando ele existe (como na
reexecução da organização); imagem Docker fixada em `python:3.12.3-slim` por
digest; `make submissao` confere o CSV contra o `sample_submission.csv`. Título
do cabeçalho corrompido ("MErn0RIAL") voltou a ser cabeçalho; `fls.` corrompido
("f1s.") voltou a ser distrator; o nome do diploma é desfeito antes do reparo
do número ("Mi1itar" virava `m111tar` e o CPPM passava por CPP).

## A medição

**Dev, métrica oficial:** F1 1,0000 nos dois níveis, τ = 0, IoU mínimo 1,000.
Score 1,0999: a confiança recalibrada custa 0,0001 num corpus em que tudo
acerta, e é o valor que minimiza o Brier onde há erro.

**Container** (`docker run --network none`, só o banco montado): saídas
idênticas às locais, 26 documentos em 1,65 s.

**Arnês, média por classe** (0,15 com 5 sementes · 0,30 com 3):

| classe | 0,15 início | 0,15 agora | 0,30 início | 0,30 agora |
|---|---|---|---|---|
| `ocr_numero` | 1,0993 | 1,0992 | 1,0942 | 1,0942 |
| `ocr_palavra` | 1,1000 | 1,0999 | 1,0915 | 1,0942 |
| `quebra_identificador` | 1,1000 | 1,0999 | 1,0949 | 1,0948 |
| `ocr_letra_digito` (nova) | 1,0474 | 1,0950 | 0,9991 | 1,0935 |
| `sigla_tribunal` (nova) | 1,0957 | 1,0999 | 1,0921 | 1,0999 |
| `ocr_curta` (nova) | 1,0724 | 1,0846 | 1,0449 | 1,0811 |
| todas (7) | 1,0969 | — | 1,0854 | — |
| todas (10) | — | 1,0825 | — | 1,0593 |

"Início" é a branch do colega, re-medida; nas três classes novas, é o código da
etapa 3, antes de a etapa 4 mexer no ruído de OCR. "Todas (10)" não tem início
porque a combinação só existe depois das classes novas. As classes que já
estavam imunes seguem imunes (1,0999 é o custo da confiança recalibrada).

**Confiança**, por `make confianca` nas duas taxas, só pares casados (como o
Brier oficial; o script contava a predição sem par como erro e deixou de
contar): `real` 913/913; `inventada_processo` 416/432 (0,98 → 0,96);
`inventada_tabela` 206/208 (0,98); `incompleta_vaga` 319/319;
`real_desempate_classe` 10/10 (0,91); `real_desempate` 0,5 (moeda entre cópias).

**Volume nos 996 acórdãos** (janela de 4.000): `processo` 7.916 → 6.509 (lei,
ato normativo, tema, inscrição na OAB e folha corrompida que viravam processo); `dispositivo`
2.078 → 2.147 e `sumula` 1.208 → 1.232 (formas correntes, conferidas por
amostra); `tema` 609 → 683.

**Testes:** 361 → 556.

## O que ficou aberto

1. **`ocr_curta` e "todas (10)" a 0,30** são o pior caso agora (1,0738 e 1,0325
   na pior semente): palavra curta corrompida fora das âncoras e o número de
   `real` que o reparo ainda não desfaz, que cai em `inventada_processo`.
2. **O número sem nenhum dígito real** (`Rcl BB.gbG/RJ`), como no cp 07.
3. **O leaderboard do conjunto final** continua sendo a única medida honesta.

## Revisão independente

Um revisor com contexto novo leu a branch inteira e sondou cada regra nova.
Achou um defeito crítico e cinco importantes, todos corrigidos com teste:

1. **O reparo do número de lei perdia a caixa** (`G`→6 virava `g`→9): "Lei
   Complementar nº G4/1990" saía `inventada` e "LC nº B4/1990" — a lei 84 —
   saía `real`. O nome e o número do diploma passaram a ser reparados em
   separado, o número sobre o texto original.
2. **Lei estadual ou municipal** com o número de uma lei federal da cobertura
   resolvia para ela; agora é outro diploma.
3. **Os apelidos da CF** ("Lei Maior", "Carta Política", "Carta Magna") aceitavam
   ano e qualificador de outra carta; agora passam pela regra de inclusão.
4. **O último grupo de um número separado por espaços** era cortado quando
   tinha mais letra que dígito; agora só sai depois de ano ou página.
5. **Palavra capitalizada depois da CF** sem pontuação no meio — a âncora de
   outra citação ou o nome do relator — entrava no diploma.
6. **O filtro de OAB colada à UF** apagava `MS12345/DF`; agora exige o
   travessão do rol de advogados ou o rótulo "OAB".

Depois das correções: dev igual, arnês igual nas dez classes e nas duas taxas,
e `ocr_numero` com 20 sementes a 0,15 sobe de 1,0963 (pior 1,0848) para 1,0972
(pior 1,0881). Nenhum par com IoU ≥ 0,5 nem trecho desalinhado nos 1.022 textos
do dev e da base (173 mil spans).

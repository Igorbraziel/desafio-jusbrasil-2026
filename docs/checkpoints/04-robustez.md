# 04 — Endurecimento contra ruído fora da amostra

**Data:** 16/09/2026 · **Estado:** três correções em produção

## O que foi feito

Três lugares onde o código exigia **forma limpa** de algo que o nível 2
corrompe. Nenhuma era limite do método; as três eram a mesma classe de erro,
cometida em pontos diferentes.

## O ganho, medido com 3 sementes a taxa 0,15

| classe de ruído | antes | depois | Δ |
|---|---|---|---|
| **as sete juntas** | 0,8022 | **0,9537** | **+0,152** |
| **OCR no número** | 0,8908 | **1,0269** | **+0,136** |
| quebra no identificador | 1,0468 | **1,0988** | +0,052 |
| OCR na prosa | 1,0125 | 1,0274 | +0,015 |
| ordem do padrão `incompleta` | 1,0737 | 1,0737 | 0,000 |
| marca de número | 1,0943 | 1,0943 | 0,000 |
| separador de UF | 1,0988 | 1,0988 | **0,000 (imune)** |
| sigla processual não vista | 1,0988 | 1,0988 | **0,000 (imune)** |
| **média das isoladas** | 1,0451 | **1,0741** | **+0,029** |

**Score limpo preservado em 1,0988** e as duas propriedades imunes seguem
imunes — era portão da fase, e a mudança só entra se passar nos dois.

## As correções

### 1. Os filtros de distrator comparavam o texto bruto

`_ANO_SOLTO`, `_PAGINAS` e `_TERMINA_EM_ANO` descrevem **formas**, e forma não
sobrevive ao nível 2. Um ano partido por quebra de linha escapava de todos e
virava citação `processo`; uma referência de página com `\n` no meio, idem.

Agora o número passa por `_forma_canonica` antes do teste — desfaz a troca de
dígito por letra e remove o espaço, mantendo a pontuação que estrutura o número.

### 2. O padrão `vaga` exigia ano de quatro dígitos limpos

O ano é o **único** número da família, então corrompê-lo apagava a citação
inteira: `20\n24` virava família `processo` (classe errada **e** span espúrio) e
`2O24` não era detectado. Era a causa de 25 das 32 `incompleta` sumirem sob
ruído de OCR em número.

O ano passa a aceitar dígito ou confusão de OCR, com quebra de linha entre os
dígitos.

### 3. A fronteira do cabeçalho vinha de lista de rótulos exatos

Uma letra trocada em `Autos` derrubava o corte de 90 para 28, e **o número do
próprio processo — o distrator canônico do desafio — virava citação**. Era a
pior das três, porque produz falso positivo garantido.

A linha passa a ser reconhecida pela **estrutura** (`<rótulo> nº <número>`) em
vez do léxico. O rótulo admite dígito no meio, porque o OCR também troca letra
por dígito (`Protocolo` → `Prot0colo`).

### 4. O núcleo terminava dentro de palavra

Descoberto ao escrever o teste da correção 1: em "de 2024 sem outras", o `s` de
"sem" é um caractere digitoide e entrava no número, fazendo a forma canônica
virar `2024s` e escapar do filtro de ano. Um lookahead impede o núcleo de
terminar colado a uma letra — simétrico ao lookbehind que já existia do outro
lado, e que fora posto pelo mesmo motivo.

## Uma decisão de escopo

Um dos casos de teste que escrevi (`2Q24`) falhava porque `0→Q` **não está entre
as confusões documentadas** — eu o inventei. Corrigir o código para cobri-lo
aumentaria a superfície de falso positivo sem nenhuma medição que justificasse.
O teste passou a usar só o ruído que `docs/investigacao.md` descreve.

Vale como regra: o arnês existe para medir ruído documentado com intensidade
maior, não para inventar classes novas de ruído.

## O que ficou aberto

1. `ocr_palavra` ainda gera espúrias (+0,015 foi ganho pequeno): prosa corrompida
   virando citação. O caminho provável é o mesmo das outras — algum filtro
   comparando forma bruta.
2. A confiança em `resolucao.CONFIANCA` continua sendo palpite. Medir a acurácia
   real por caminho de decisão sob perturbação é a próxima frente.
3. As duas classes de ruído que o arnês ainda não gera: corrupção de rótulo de
   cabeçalho (hoje só acontece por acaso dentro de `ocr_palavra`) e corrupção da
   sigla do tribunal.

# 06 — As perdas de recall, e o ponto cego que as escondia

**Data:** 21/09/2026 · **Estado:** quatro correções em produção

## O que esta etapa atacou

Recall é o erro que não se recupera: o span não extraído é FN, e nenhuma
classificação correta adiante o salva. As três correções abaixo perdiam a citação
inteira — e **nenhuma aparecia em qualquer medição que tínhamos**.

Antes de projetar, li os dois artigos que [referencias.md](../referencias.md)
lista como "usáveis agora". A leitura mudou uma decisão e matou uma ideia.

## O que a literatura deu, e o que ela tirou

### Harašta et al., 2020 — segmentar antes de reconhecer

O artigo não é sobre "contar constituintes", como a nossa `referencias.md`
resumia: é um pipeline de **segmentação do documento** seguido de reconhecimento
de referência só dentro do segmento de argumentação. A tabela 1 é o que serve:

| modelo | F1 (estrito) | F1 (sobreposição) |
|---|---|---|
| reconhecimento sozinho | 0,652 | 0,709 |
| pipeline (segmentação → reconhecimento) | **0,724** | **0,815** |

Sete pontos de F1 vindos da segmentação. É o papel de `texto.fim_do_cabecalho`
aqui — e era exatamente ali que estávamos errando (lacuna 2 abaixo).

### Zhu et al., ACL 2023 — a ideia que morreu na medição

O artigo separa NIL em *Missing Entity* e *Non-Entity Phrase*, e ganha
comparando o **tipo** da menção com o do candidato, além da similaridade
semântica. O análogo óbvio aqui seria conferir o tribunal: a citação diz "REsp …
do STJ", o registro é do TST, logo não casa.

Fui medir antes de implementar:

| medição | resultado |
|---|---|
| citações `inventada` cujo número está no índice | **0 de 64** |
| citações `real` que nomeiam tribunal e divergem do registro | **0 de 11** |
| números do índice em mais de um tribunal | 9 de 2.001 |

**A base nunca contém o número de uma citação inventada.** O lookup exato já é
perfeitamente discriminativo; a verificação de tipo não teria o que corrigir e só
somaria superfície de erro. Não foi implementada. Fica registrada porque é a
sugestão natural de quem lê o artigo.

## As correções

### 1. O primeiro dígito corrompido — 79% das falhas de `ocr_numero`

O núcleo abria com `\d` literal, e o OCR corrompe a primeira posição como
qualquer outra. Em `REsp l.234.567/PR` o casamento começava no `5` e devolvia
`234567` — **um número diferente**, que não resolve na base.

É a pior forma de erro porque é silenciosa: o span existe, o IoU passa de 0,5, a
citação vira `inventada` com confiança alta. Não há sintoma.

Medindo 4.000 perturbações de um identificador sintético a taxa 0,4:

| desfecho | ocorrências |
|---|---|
| número recuperado corretamente | 49,1% |
| não detectado | 28,7% |
| **detectado com número errado** | 22,2% |
| **dos erros, com o 1º dígito corrompido** | **79,3%** |

Não é limitação de `_corrigir_ocr` — a função repara esses casos perfeitamente
quando recebe o trecho inteiro. É a ordem detecção→normalização com uma âncora
intolerante.

**Esta mudança tinha sido rejeitada** no [checkpoint 02](02-arnes-de-perturbacao.md).
Não a apliquei por discordar do registro: remedi. O que mudou desde então foi o
lookbehind que rejeita letra precedida de letra — que o próprio checkpoint 02
apontava como a correção faltante —, mais `_DATA`, a janela de rótulo de 40
caracteres e `_PAGINAS` comparando a forma canônica, todos da v2.

### 2. A fronteira do cabeçalho engolia a primeira linha do corpo

`_ROTULOS` era testado com `startswith`, então `"Recurso especial interposto…"` e
`"Refere-se à decisão…"` viravam cabeçalho. Como `fim_do_cabecalho` para na
primeira linha que **não** é cabeçalho, uma dessas abrindo o corpo empurrava a
fronteira para depois dela e a citação sumia.

| medição nos 26 documentos | resultado |
|---|---|
| linhas do corpo classificadas como cabeçalho pelo `startswith` | **7** |
| dessas, quantas eram cabeçalho de verdade | **0** |
| cortes que mudam se a regra for removida por completo | **0** |
| spans com e sem a regra | **192 = 192** |

A regra não pagava o próprio custo. Mas `"Autos"` sozinho numa linha é cabeçalho
legítimo e pode aparecer no cego, então ela fica — exigindo agora que a linha
**seja** o rótulo, não apenas comece com ele.

### 3. `i` e `q` não atravessavam o núcleo

`OCR_PARA_DIGITO` mapeia 14 letras; a classe do núcleo era literal e listava 12:

```
classe do _NUCLEO : BGIOSZbglosz
OCR_PARA_DIGITO   : BGIOSZbgiloqsz
FALTAM            : i q
```

`REsp 1737i8/SP` não casava o núcleo e o span sumia — mesmo com
`digitos_do_identificador` sabendo devolver `173718`. A normalização consertava;
a detecção nunca lhe entregava o trecho.

`_ANO_TOLERANTE` já derivava a classe da tabela; era a assimetria entre as duas
construções que deixava a divergência passar. Agora as duas derivam.

### 4. O arnês tinha o mesmo ponto cego que o código

O gerador produzia **uma** letra por dígito, nunca `i` nem `q`. Foi assim que a
lacuna 3 sobreviveu a todos os checkpoints anteriores: o instrumento era cego
para exatamente o que o código errava.

Agora sorteia entre as variantes, e um teste confere que o reparo cobre tudo que
o gerador produz. A tabela continua escrita **à parte** de `OCR_PARA_DIGITO` de
propósito: derivá-la tornaria a medição circular por construção — o arnês só
produziria o ruído que o normalizador já sabe desfazer, e um buraco novo ficaria
de novo invisível. O teste é que torna a divergência barulhenta.

## O ganho, 5 sementes a taxa 0,15

Todas as comparações contra o **mesmo** arnês. A comparação contra os números dos
checkpoints anteriores não vale: aquele arnês era mais fácil.

| classe de ruído | antes | depois | Δ |
|---|---|---|---|
| **as sete juntas** | 0,9917 | **1,0093** | **+0,018** |
| **pior semente de todas (7)** | 0,9461 | **0,9764** | **+0,030** |
| `ocr_numero` | 1,0266 | **1,0455** | **+0,019** |
| `ocr_palavra` | 1,0384 | 1,0384 | 0,000 |
| `separador_uf` · `sigla_nao_vista` · `ordem_incompleta` | 1,0992 | 1,0992 | imunes |

A ausência de regressão em `ocr_palavra` é o portão que importa: prosa corrompida
é onde a versão rejeitada em 02 quebrava, com 31 falsos positivos. Hoje, zero.

Score limpo **1,0992**, IoU mínimo **0,8125**, 161 testes passando.

## `incompleta_sem_numero` é inalcançável, não incalibrado

Os três caminhos que o retornam exigem uma citação detectada **sem** número, e
nenhuma família produz isso: `_SUMULA` exige `(?P<numero>\d+)`, `_DISPOSITIVO`
exige `(?P<artigo>\d+…)`, e `processo` só nasce depois de quatro dígitos, que a
normalização nunca remove. Fica como defesa em profundidade, e o código passa a
dizer isso — em vez de o valor parecer calibração pendente.

## O que ficou aberto

1. **`quebra_identificador` perdeu a imunidade numa das cinco sementes** (1,0916).
   É **pré-existente**: o código anterior dá o mesmo valor na mesma semente. As
   varreduras de 3 sementes nunca a alcançaram — o que é, por si, um recado sobre
   o número de sementes que usamos para declarar imunidade.
2. **`A→4` e `E→3`** continuam fora do reparo: não estão documentados em
   `investigacao.md`, e a regra de escopo do checkpoint 04 vale.
3. `ocr_numero` segue sendo a classe mais fraca (1,0455 contra 1,0992 limpo),
   mesmo com o maior ganho desta rodada.

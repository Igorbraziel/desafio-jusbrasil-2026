# 0002 — Índice de números próprios em vez do FTS

**Data:** 31/08/2026 · **Situação:** vigente

## Contexto

A base traz uma tabela virtual `documentos_fts` (FTS5) sobre o inteiro teor.
Usá-la para resolver citações tem dois problemas:

1. O tokenizador `unicode61` quebra em qualquer caractere não alfanumérico, então
   `MATCH '1741784'` não encontra o documento que escreve `1.741.784`. É preciso
   reconstruir a pontuação canônica antes de consultar.
2. Pior: o FTS devolve **qualquer** documento que mencione o número, e acórdãos
   citam uns aos outros o tempo todo. Uma busca por `"1.276.977"` devolve seis
   documentos do STF, nenhum dos quais *é* o RE 1.276.977.

Medimos o problema: das citações `real` do gabarito, a busca por contenção
devolve mais de um candidato em vários casos, e há citações `inventada` cujo
número aparece em nove lugares da base — todos citando um processo que não está
na cobertura sob aquela classe.

## Decisão

Construir, uma vez e offline, um índice `número → documentos que o têm como
número próprio`, e consultar por chave em runtime.

"Número próprio" é definido pela posição:

- **STF, STJ, TSE, STM:** os primeiros 400 caracteres do documento.
- **TST:** o tribunal não põe o número no cabeçalho. Ele aparece na fórmula
  `… estes autos de <classe> nº TST-RR-…`, por volta do caractere 1.000, e de
  novo no rodapé. Ancoramos em `Nº TST-` e pegamos uma janela de 150 caracteres.

Ambos os lados — a citação e o índice — são normalizados para dígitos puros,
o que dispensa reconstruir a pontuação e torna o problema (1) irrelevante.

## Consequências

- Índice de 998 acórdãos construído em **0,53 s**, ocupando 136 KB em JSON.
  Consulta em runtime é acesso a dicionário.
- Nos 120 casos do gabarito que dependem dessa resolução (82 `real` e 38
  `inventada` de acórdão), acerta **120/120**, incluindo o `id_canonico`.
- O limiar de 400 caracteres e a janela de 150 são números calibrados nesta base.
  Um tribunal com outro layout de cabeçalho exigiria uma nova âncora.
- A tabela `documentos_fts` fica sem uso. Se um dia precisarmos de busca
  semântica ou por relator, ela continua lá.

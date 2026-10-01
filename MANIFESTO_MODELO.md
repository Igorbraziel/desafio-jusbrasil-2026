# Manifesto do modelo

A submissão exige que os pesos usados estejam incluídos no repositório ou
referenciados em revisão fixa, para que a organização consiga baixá-los e
executá-los offline.

## Modelos usados

**Nenhum.**

Esta solução não carrega pesos de modelo de linguagem, de embedding ou de NER.
O pipeline é inteiramente determinístico: expressões regulares para detectar os
spans, normalização de superfície para desfazer o ruído de OCR, e uma consulta
por chave a um índice construído, em cada execução, a partir da base canônica
que a organização fornece — na avaliação final, o `.db` novo. Não há nada a
baixar: o repositório no hash enviado é tudo o que o `run.sh` precisa.

Um NER de pesos abertos foi medido durante o desenvolvimento e descartado; ele
não está no repositório nem no runtime
([ADR 0004](docs/decisoes/0004-ner-de-pesos-abertos.md)).

## Consequências

| Exigência do regulamento | Situação |
|---|---|
| Pesos públicos, gratuitos, executáveis pela organização | não se aplica — não há pesos |
| Pesos incluídos ou referenciados em revisão fixa (link HF + commit hash) | não se aplica |
| Modelo gated | não se aplica |
| Fine-tune com pesos publicados | não se aplica |
| GPU de até 24 GB de VRAM (envelope: 8 vCPUs, 32 GB RAM) | **não usa GPU**; roda em CPU, com uso de memória dominado pelo índice (da ordem de 130 KB, se gravado em JSON) |
| Média ≤ 60 s/documento | ≈ **1,5 s para os 26 documentos de desenvolvimento**, dos quais ~1,4 s são a preparação da base a partir do `.db` (uma vez por execução) e ~2 ms por documento |
| Teto de 4 h no teste completo | folga de três ordens de grandeza, mesmo contando a preparação da base |
| Disco (~100 GB de referência) | o código e a imagem de Python 3.12 slim; a base entra por volume |
| Execução offline, sem rede | nenhuma chamada externa em runtime; o container é conferido com `--network none` |
| Decodificação determinística (seed, temperature=0) | não se aplica — não há amostragem. O `run.sh` fixa `PYTHONHASHSEED`, a imagem também, e todo desempate tem ordenação explícita. A saída é a mesma byte a byte com outras sementes de hash, em Python 3.10, 3.11, 3.12 e 3.14, e no container — ver o [checkpoint 11](docs/checkpoints/11-entrega-final.md) |
| Diferenças de `confianca` por hardware | não ocorrem: a confiança é uma constante por caminho de decisão, sem cálculo em ponto flutuante que dependa da máquina |

Medido em 01/10 no commit 088ade1: 1,5–1,7 s para os 26 documentos do dev, quase todo no preparo da base.

## Se um modelo for adicionado

Registre aqui, antes de enviar o hash da versão final: o `repo_id` do
HuggingFace, a revisão (commit hash completo), o tamanho em VRAM sob o limite de
24 GB, e a configuração de decodificação. O `run.sh` teria de obter os pesos sem
rede — incluídos no repositório ou na imagem —, porque a execução é offline e em
máquina limpa. Se for um modelo com fine-tune, os pesos resultantes precisam
estar publicados e acessíveis — solução cujo modelo ajustado não seja
publicamente executável pela organização é desclassificada.

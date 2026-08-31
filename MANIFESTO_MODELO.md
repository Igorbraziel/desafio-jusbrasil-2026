# Manifesto do modelo

A submissão exige declarar os pesos usados, por link e revisão fixa, para que a
organização consiga baixá-los e executá-los offline.

## Modelos usados

**Nenhum.**

Esta solução não carrega pesos de modelo de linguagem, de embedding ou de NER.
O pipeline é inteiramente determinístico: expressões regulares para detectar os
spans, normalização de superfície para desfazer o ruído de OCR, e uma consulta
por chave a um índice construído a partir da base canônica fornecida pela
organização.

## Consequências

| Exigência do regulamento | Situação |
|---|---|
| Pesos públicos, gratuitos, executáveis pela organização | não se aplica — não há pesos |
| Link HF + revisão fixa (commit hash) | não se aplica |
| Modelo gated | não se aplica |
| Fine-tune com pesos publicados | não se aplica |
| Envelope: 1 GPU 24 GB, 8 vCPUs, 32 GB RAM | **não usa GPU**; roda em CPU, com uso de memória dominado pelo índice (≈ 140 KB em JSON) |
| Média ≤ 60 s/documento | ≈ **9 ms/documento** medidos nos 26 documentos de desenvolvimento |
| Teto de 4 h no teste completo | folga de três ordens de grandeza |
| Execução offline, sem rede | nenhuma chamada externa em runtime |
| Decodificação determinística (seed, temperature=0) | não se aplica — não há amostragem. `PYTHONHASHSEED=0` fixado no Dockerfile e ordenação explícita em todo desempate |

## Se um modelo for adicionado

Registre aqui, antes de submeter: o `repo_id` do HuggingFace, a revisão (commit
hash completo), o tamanho em VRAM sob o envelope de 24 GB, e a configuração de
decodificação. Se for um modelo com fine-tune, os pesos resultantes precisam
estar publicados e acessíveis — solução cujo modelo ajustado não seja
publicamente executável pela organização é desclassificada.

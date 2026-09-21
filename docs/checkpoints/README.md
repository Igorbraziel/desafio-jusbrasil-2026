# Checkpoints

Registro corrido do que foi feito, em ordem cronológica, com o número que cada
etapa mediu. Um arquivo por etapa, numerado.

O ponto não é narrar o trabalho — o `git log` já faz isso — mas deixar
**medições comparáveis** e as decisões que elas provocaram, para retomar o
trabalho sem reconstruir o raciocínio.

Cada checkpoint traz:

- **O que foi feito**, em uma linha.
- **A medição**, com o comando que a produz.
- **O que mudou de decisão** por causa dela, se mudou.
- **O que ficou aberto.**

| # | Etapa | Resultado |
|---|---|---|
| [00](00-linha-de-base.md) | Linha de base do pipeline | score 1,0988 · 47 testes |
| [01](01-parser-de-zonas.md) | Parser de zonas dos acórdãos | órfãos 26→25 · ambíguos 282→239 · score preservado |
| [02](02-arnes-de-perturbacao.md) | Arnês de perturbação | `ocr_numero` é o ponto fraco (−0,259) · `sigla_nao_vista` imune |
| [03](03-integracao.md) | Integração com a `main` | política de não redistribuir o gabarito · ADR 0003 refutada |
| [04](04-robustez.md) | Endurecimento contra ruído | pior caso 0,8022 → 0,9537 · score limpo preservado |

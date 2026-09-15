"""Da citação detectada à classe, consultando a base canônica.

**A IMPLEMENTAR.**

A classe não precisa ser predita por um classificador — ela é consequência da
cardinalidade da consulta, como descreve o material do desafio:

===========================================  ============  ==========================
candidatos encontrados                        classe        saída
===========================================  ============  ==========================
exatamente 1                                  real          ``id_canonico`` do registro
0                                             inventada     ``resolucao: null``
2 ou mais, sem critério de desempate          incompleta    ``resolucao: null``
===========================================  ============  ==========================

Uma citação sem identificadores para sequer formular a consulta é ``incompleta``
sem passar pelo banco. E uma referência como "acórdão do STF de 2024, relatado
pelo Ministro Fulano" é buscável, mas casa com dezenas de candidatos: também
``incompleta``, por falta de critério de desempate.

Cuidado com ``lei``: o número do artigo sozinho não identifica o dispositivo. O
gabarito traz o mesmo número de artigo sob dois códigos diferentes, um dentro e
outro fora da cobertura — só o código decide entre ``real`` e ``inventada``.

``confianca`` é opcional, mas alimenta o bônus de calibração de até 10%. Vale
atribuí-la por caminho de decisão e medir o Brier na amostra de desenvolvimento
— um caminho que acertou tudo em 26 documentos ainda não merece 1,0.
"""

from __future__ import annotations

from .base_canonica import BaseCanonica
from .deteccao import Achado


def resolver(achado: Achado, base: BaseCanonica) -> tuple[str, int | None, float]:
    """Classifica um achado e, quando ``real``, devolve o ``id_canonico``.

    Returns:
        ``(classificacao, id_canonico, confianca)`` — ``id_canonico`` é ``None``
        em tudo que não for ``real``.
    """
    raise NotImplementedError

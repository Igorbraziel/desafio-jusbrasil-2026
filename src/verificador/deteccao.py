"""Detecção dos spans de citação no texto do parecer.

**A IMPLEMENTAR.**

Quem não entrega o span de uma citação não consegue classificá-la, e isso conta
como erro de recall. O alinhamento com o gabarito é por sobreposição com
IoU ≥ 0,5, então a borda exata não precisa ser perfeita — mas a citação inteira
precisa aparecer.

Uma organização possível é por família, porque a família determina contra o quê
a citação é resolvida:

``processo``     sigla ou classe processual + número (``AgInt no REsp 1.599.910/PR``)
``sumula``       ``Súmula <n> do <tribunal>``, ``Súmula Vinculante <n>``
``tema``         ``Tema 2.680 da repercussão geral``
``dispositivo``  ``art. <n>, <inciso>, do <código>``
``vaga``         sem identificador suficiente para consultar a base

**A família ``vaga`` tem uma forma só.** Depois da revisão de 15/09/2026 as 32
citações ``incompleta`` do gabarito são todas do padrão tribunal + ano +
relator — ``julgado do <tribunal> proferido em <ano> pela relatoria de
<nome>``. As 32 nomeiam um relator, o único dígito é o ano e nenhuma traz
número de processo. As frases genéricas ("normas de regência da matéria") e as sem número
("reiterados precedentes do STJ") saíram do gabarito nas duas revisões. O sinal
a procurar é **menção a relator sem número de processo**, não um repertório de
frase vaga. Ver ``docs/investigacao.md``.

**Distratores.** Os cabeçalhos trazem números que parecem citação e não são:
número dos autos do próprio documento, protocolo, inscrição na OAB, ``fls.
234/567``, valor da causa. Nenhum está no gabarito, e extraí-los conta como
falso positivo. Note que o mesmo formato CNJ é distrator no cabeçalho e citação
no corpo — ver :func:`verificador.texto.fim_do_cabecalho`.

**Ruído nas palavras.** As citações vagas são frases, e o nível 2 corrompe letras
isoladas dentro delas (``entendirnento``, ``jurisprudêneia``, ``recentc``).
Comparação exata perde todas as versões corrompidas.

Os testes em ``tests/test_deteccao.py`` são a especificação desta etapa.
"""

from __future__ import annotations

from dataclasses import dataclass

TRIBUNAIS = ("STF", "STJ", "TSE", "TST", "STM")

FAMILIAS = ("processo", "sumula", "tema", "dispositivo", "vaga")


@dataclass(frozen=True)
class Achado:
    """Um span candidato a citação, antes de ser resolvido.

    ``dados`` leva os grupos que a detecção já isolou — número do artigo,
    diploma legal, número da súmula. Reaproveitá-los evita que a resolução tenha
    de reparsear o trecho e erre onde a detecção acertou (``5úmula 211`` tem dois
    números; só um deles é o da súmula).
    """

    inicio: int
    fim: int
    trecho: str
    familia: str  # um de FAMILIAS
    tipo: str  # jurisprudencia · lei
    dados: tuple[tuple[str, str], ...] = ()


def detectar(texto: str) -> list[Achado]:
    """Encontra todas as citações candidatas no documento.

    Devolve os achados ordenados por posição, sem sobreposição entre si.
    """
    raise NotImplementedError

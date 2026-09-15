"""A base canônica: cobertura congelada de 1.014 registros.

É contra ela que uma citação é ``real`` ou ``inventada``. Se um acórdão existe no
mundo mas não está aqui, para efeito do desafio ele não existe.

Três estruturas de resolução, uma por natureza de registro:

``acordao`` (996)
    Índice de números **próprios** — a construir. O ponto delicado, e a
    armadilha que mais custa precisão: o texto de um acórdão cita outros
    acórdãos o tempo todo, e uma busca por contenção devolve todos eles. O que
    separa "este documento *é* o processo" de "este documento apenas o *cita*" é
    a posição. Ver ``docs/investigacao.md``.

``sumula`` (5) e ``dispositivo`` (13)
    Poucos demais para indexar por texto. Resolvemos por tabela curada,
    conferida contra o banco em ``tests/test_base_canonica.py``.

    A distribuição de 15/09/2026 mudou o terreno aqui: esses mesmos 18
    registros ganharam uma primeira linha que se autodeclara — ``Súmula n. 331
    do TST``, ``Artigo 14 da Lei nº 8.078, de 11 de setembro de 1990``. Antes o
    texto era só o enunciado, e a tabela abaixo teve de ser levantada à mão. Ela
    continua correta e continua sendo o caminho de resolução, mas agora é
    **derivável da base**, e o cabeçalho também dá o número da lei por extenso,
    que o repertório de siglas não tinha. Ver ``docs/dados.md``.

Não confunda as duas colunas de id: ``documento_id`` (``doc_0201``) é a chave
interna do acervo; ``id`` é o doc_id do Jusbrasil, e é ele que vai em
``resolucao.id_canonico``.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .normalizacao import numeros_do_texto

# Abaixo de 4 dígitos um número não identifica processo nenhum — só gera ruído.
MINIMO_DIGITOS = 4

# ---------------------------------------------------------------------------
# Súmulas e dispositivos: tabelas curadas.
#
# O mapeamento abaixo foi levantado à mão quando o texto desses registros era só
# o enunciado, sem "Súmula 331" nem "CLT". Desde 15/09/2026 cada um abre com a
# própria identificação, então a tabela virou derivável da base — continua
# correta, e os testes a conferem contra o banco. Como a cobertura é congelada,
# ela é completa: qualquer súmula ou artigo fora dela é, por definição, inventada.
# ---------------------------------------------------------------------------

# (tribunal, é_vinculante, número) -> id canônico
SUMULAS: dict[tuple[str, bool, int], int] = {
    ("STJ", False, 83): 1289710642,
    ("STJ", False, 211): 1289710776,
    ("STJ", False, 443): 1289711022,
    ("STF", True, 10): 1289712966,
    ("TST", False, 331): 1431369957,
}

# (código, artigo) -> id canônico
DISPOSITIVOS: dict[tuple[str, int], int] = {
    ("CF", 5): 10641516,
    ("CF", 7): 10641213,
    ("CF", 93): 10626510,
    ("CPC", 373): 28893055,
    ("CC", 186): 10718759,
    ("CPP", 312): 10652044,
    ("CPM", 290): 10590194,
    ("CDC", 14): 10606184,
    ("CLT", 477): 10710324,
    ("CLT", 818): 10647746,
    ("CLT", 896): 10637358,
    ("ELEITORAL", 276): 10577194,
    ("LC64", 1): 11304039,
}


@dataclass(frozen=True)
class Registro:
    """Um registro da base canônica, no mínimo necessário para resolver."""

    documento_id: str
    id_canonico: int
    tribunal: str | None
    texto_len: int


def regiao_de_identificacao(texto: str) -> str:
    """Os pedaços do documento onde o número do *próprio* processo aparece.

    **A IMPLEMENTAR.** Recebe o inteiro teor de um acórdão e devolve só os
    trechos que identificam o processo — não os que citam outros. Cada tribunal
    põe essa informação num lugar; ver ``docs/investigacao.md``.
    """
    raise NotImplementedError


def construir_indice(caminho_db: Path) -> dict:
    """Varre a base uma vez e devolve o índice de números próprios.

    Feito offline: em runtime só carregamos o JSON. O material do desafio
    recomenda explicitamente esse caminho em vez de varrer o FTS a cada citação.
    """
    conexao = sqlite3.connect(f"file:{caminho_db}?mode=ro", uri=True)
    numeros: dict[str, list[str]] = {}
    registros: dict[str, dict] = {}

    consulta = (
        "SELECT documento_id, id, tribunal, texto, texto_len "
        "FROM documentos WHERE natureza = 'acordao'"
    )
    for documento_id, id_canonico, tribunal, texto, texto_len in conexao.execute(consulta):
        registros[documento_id] = {
            "id": id_canonico,
            "tribunal": tribunal,
            "texto_len": texto_len,
        }
        for numero in numeros_do_texto(regiao_de_identificacao(texto)):
            if len(numero) >= MINIMO_DIGITOS:
                numeros.setdefault(numero, []).append(documento_id)

    conexao.close()
    return {"numeros": numeros, "registros": registros}


def salvar_indice(indice: dict, caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(indice, ensure_ascii=False), encoding="utf-8")


class BaseCanonica:
    """Interface de consulta à cobertura congelada."""

    def __init__(self, indice: dict) -> None:
        self._numeros: dict[str, list[str]] = indice["numeros"]
        self._registros: dict[str, Registro] = {
            documento_id: Registro(
                documento_id=documento_id,
                id_canonico=dados["id"],
                tribunal=dados["tribunal"],
                texto_len=dados["texto_len"],
            )
            for documento_id, dados in indice["registros"].items()
        }

    @classmethod
    def de_arquivo(cls, caminho: Path) -> BaseCanonica:
        return cls(json.loads(caminho.read_text(encoding="utf-8")))

    @classmethod
    def de_banco(cls, caminho_db: Path) -> BaseCanonica:
        return cls(construir_indice(caminho_db))

    def candidatos_por_numero(self, numero: str) -> list[Registro]:
        """Registros que têm esse número como número próprio.

        Quando há mais de um, são duplicatas do mesmo julgado indexadas duas
        vezes — ver ``docs/investigacao.md``. A ordem é determinística.

        ⚠ **Não leia o primeiro da lista como "a resposta".** A ordenação por
        ``texto_len`` decrescente vem de uma observação do gabarito de 04/09, em
        que os três pares ambíguos resolviam para o registro mais longo. A
        distribuição de 15/09 apagou dois desses pares da base e **inverteu o
        terceiro**: ``25823-78.2015.5.24.0091`` agora resolve para doc_0729
        (60.988 chars) e não para doc_0710 (95.681). A heurística está refutada;
        a ordem aqui é só estabilidade, não preferência. Quem implementar a
        resolução precisa decidir o desempate com outro critério.
        """
        if len(numero) < MINIMO_DIGITOS:
            return []
        candidatos = [self._registros[d] for d in self._numeros.get(numero, [])]
        return sorted(candidatos, key=lambda r: (-r.texto_len, r.documento_id))

    def sumula(self, tribunal: str | None, vinculante: bool, numero: int) -> int | None:
        if vinculante:
            return SUMULAS.get(("STF", True, numero))
        if tribunal is None:
            return None
        return SUMULAS.get((tribunal, False, numero))

    def dispositivo(self, codigo: str | None, artigo: int | None) -> int | None:
        if codigo is None or artigo is None:
            return None
        return DISPOSITIVOS.get((codigo, artigo))

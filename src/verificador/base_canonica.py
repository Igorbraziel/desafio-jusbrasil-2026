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
    registros ganharam uma primeira linha que se autodeclara, no formato
    ``Súmula n. <número> do <tribunal>`` e ``Artigo <número> da <lei por
    extenso>``. Antes o texto era só o enunciado, e a tabela abaixo teve de ser
    levantada à mão. Ela continua correta e continua sendo o caminho de
    resolução, mas agora é **derivável da base**, e o cabeçalho também dá o
    número da lei por extenso, que o repertório de siglas não tinha. Ver
    ``docs/dados.md``.

Não confunda as duas colunas de id: ``documento_id`` (``doc_0201``) é a chave
interna do acervo; ``id`` é o doc_id do Jusbrasil, e é ele que vai em
``resolucao.id_canonico``.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .estrutura import zonas_de_identificacao
from .normalizacao import numeros_do_texto

# Abaixo de 4 dígitos um número não identifica processo nenhum — só gera ruído.
MINIMO_DIGITOS = 4

# ---------------------------------------------------------------------------
# Súmulas e dispositivos: tabelas curadas.
#
# O mapeamento abaixo foi levantado à mão quando o texto desses registros era só
# o enunciado, sem dizer qual súmula era nem de que código vinha o artigo. Desde
# 15/09/2026 cada um abre com a própria identificação, então a tabela virou
# derivável da base — continua correta, e os testes a conferem contra o banco.
# Como a cobertura é congelada, ela é completa: qualquer súmula ou artigo fora
# dela é, por definição, inventada.
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


# O cabeçalho basta para STF, STJ, TSE e STM: medindo as 82 citações reais do
# gabarito, a primeira ocorrência do número próprio cai entre os caracteres 19 e
# 123 nesses quatro. A folga até 400 cobre o número inteiro e os casos longos.
LIMITE_CABECALHO = 400

# O TST é a exceção: o número não está no cabeçalho, e sim na fórmula de
# abertura do voto, por volta do caractere 1.000. A âncora é a frase, não o
# prefixo "TST-" — "estes autos" quer dizer *estes*, o que separa o processo
# próprio dos que o acórdão apenas cita. Ancorar em "TST-" pegaria os dois e
# reintroduziria a armadilha 5.
_ANCORAS = re.compile(r"(?:est[eo]s\s+autos|Vistos,?\s+relatados)", re.IGNORECASE)

# A partir da âncora até passar do número. No exemplo medido, a distância entre
# "estes autos de" e o número é de ~110 caracteres; 360 cobre classes
# processuais mais longas sem alcançar a lista de partes.
JANELA_ANCORA = 360

# Referência a lei, não a processo. Medindo, era a origem de *todos* os falsos
# positivos caros: Lei 13.467/2017 entrava no índice como `134672017` e fazia 42
# registros responderem por ela, o que transforma uma citação `inventada` em
# `real` — o erro que a métrica pune com τ.
#
# Exige a palavra-chave antes do número. Casar só pelo sufixo de ano parece
# tentador e quebra tudo: em `7000380- 08.2023.7.00.0000` o trecho `08.2023`
# tem exatamente essa forma, e removê-lo parte o número CNJ ao meio — medido,
# derruba o recall de 77/77 para 46/77.
# O abreviador de "número" aparece como nº, n°, n., No e n — este último porque
# o próprio texto da base tem ruído de OCR, e `Nº` aparece como `No` nele.
_NUMERO_ABREVIADO = r"(?:\s*n[.ºo°]?)?"

_REFERENCIA_A_LEI = re.compile(
    r"(?:lei|lc|decreto(?:[-\s]lei)?|medida\s+provis[óo]ria|mp|emenda\s+constitucional|ec)"
    rf"(?:\s+complementar)?{_NUMERO_ABREVIADO}\s*\d{{1,3}}(?:\.\d{{3}})*\s*[/.]\s*(?:19|20)\d{{2}}",
    re.IGNORECASE,
)

# Um número que muitos registros reivindicam como próprio não é identificador —
# é texto de fórmula. Os pares de duplicata conhecidos da base compartilham um
# número entre *dois* registros; acima disso é vazamento da região, e deixar
# entrar custa τ. Este corte é independente de reconhecer sintaxe de lei, então
# pega também o que a regex acima não descreve.
MAXIMO_REGISTROS_POR_NUMERO = 2


# Método padrão de extração da região. Trocável por `--metodo` em
# `scripts/medir_regiao.py`, que mede os dois lado a lado.
#
# O estrutural é o padrão desde 16/09: com o mesmo recall (77/77) e o mesmo zero
# de falso positivo, entrega 25 órfãos contra 26 e 239 números ambíguos contra
# 282. A baseline fica no código porque comparação exige os dois — ver
# docs/checkpoints/01-parser-de-zonas.md.
METODOS = ("baseline", "estrutural")
METODO_PADRAO = "estrutural"


def _regiao_baseline(texto: str) -> str:
    """Janela de offset fixo mais a primeira âncora da fórmula de abertura.

    Não conhece a estrutura do documento: aposta que o número próprio está nos
    primeiros caracteres e, para o TST, na fórmula ``estes autos``.
    """
    pedacos = [texto[:LIMITE_CABECALHO]]
    for casamento in _ANCORAS.finditer(texto):
        inicio = casamento.start()
        if inicio < LIMITE_CABECALHO:
            continue  # já coberto pelo cabeçalho
        pedacos.append(texto[inicio : inicio + JANELA_ANCORA])
        # Só a primeira ocorrência. A fórmula de abertura do voto aparece uma
        # vez; as repetições seguintes são o acórdão citando outras decisões, e
        # indexar os números delas é exatamente a armadilha 5.
        break
    return "\n".join(pedacos)


def _regiao_estrutural(texto: str, tribunal: str | None) -> str:
    """As zonas identificadoras da segmentação, por espécie de tribunal.

    Em vez de supor onde o número está, segmenta o documento e pega as zonas em
    que ele *pode* estar — ver :mod:`verificador.estrutura`.
    """
    zonas = zonas_de_identificacao(texto, tribunal)
    return "\n".join(z.texto for z in zonas)


def regiao_de_identificacao(
    texto: str,
    tribunal: str | None = None,
    metodo: str = METODO_PADRAO,
) -> str:
    """Os pedaços do documento onde o número do *próprio* processo aparece.

    Recebe o inteiro teor de um acórdão e devolve só os trechos que identificam
    o processo — não os que citam outros. Cada tribunal põe essa informação num
    lugar; ver ``docs/investigacao.md``.

    Os trechos são separados por ``\\n`` para não colar o fim de um número no
    começo de outro. A remoção de referência a lei vale para os dois métodos:
    é ortogonal à segmentação e cada uma das duas resolve um problema diferente.
    """
    if metodo not in METODOS:
        raise ValueError(f"método desconhecido: {metodo!r} (use um de {METODOS})")
    bruto = (
        _regiao_estrutural(texto, tribunal) if metodo == "estrutural" else _regiao_baseline(texto)
    )
    return _REFERENCIA_A_LEI.sub(" ", bruto)


def construir_indice(caminho_db: Path, metodo: str = METODO_PADRAO) -> dict:
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
        regiao = regiao_de_identificacao(texto, tribunal, metodo)
        for numero in numeros_do_texto(regiao):
            if len(numero) >= MINIMO_DIGITOS:
                numeros.setdefault(numero, []).append(documento_id)

    conexao.close()

    # Descarta o que muitos registros reivindicam: é fórmula, não identificador.
    # Ver MAXIMO_REGISTROS_POR_NUMERO.
    numeros = {
        numero: documentos
        for numero, documentos in numeros.items()
        if len(documentos) <= MAXIMO_REGISTROS_POR_NUMERO
    }
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
        terceiro**, que passou a resolver para o candidato mais curto (cerca de
        61 mil caracteres contra 96 mil). A heurística está refutada;
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

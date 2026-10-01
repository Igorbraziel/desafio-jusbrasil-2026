"""Base canônica: a cobertura fechada contra a qual uma citação é ``real`` ou ``inventada``.

Acórdãos são resolvidos por um índice de números próprios; súmulas e dispositivos,
por tabelas montadas da primeira linha de cada registro. ``documento_id`` é a chave
interna do acervo; ``id`` é o doc_id do Jusbrasil, que vai em ``resolucao.id_canonico``.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ..deteccao.detector import _e_numero_de_processo
from ..juridico.classes import marcas
from ..juridico.leis import codigo_da_lei
from ..normalizacao import _ESPACOS, _NUCLEO, _NUCLEO_LIMPO, sem_acento
from .estrutura import tribunal_do_texto, zonas_de_identificacao

# Abaixo de 4 dígitos um número não identifica processo nenhum.
MINIMO_DIGITOS = 4

# Súmulas e dispositivos são lidos do banco recebido, nunca de tabela fixa: o banco
# da avaliação é outro, e uma tabela fixa faria sair `real` o que ele não tem.
# Cada registro abre com a própria identificação ("Súmula n. <número> do <tribunal>",
# "Artigo <número> da <lei>"); o que não estiver na tabela é `inventada`.

_SUMULA_DO_REGISTRO = re.compile(
    r"^\s*S[úu]mula\s+(?P<vinculante>Vinculante\s+)?(?:n\s*[º°o.]?\s*)?(?P<numero>\d+)"
    r"(?:\s*,?\s*d[oa]\s+(?P<tribunal>STF|STJ|TST|TSE|STM)\b)?",
    re.IGNORECASE,
)
_ARTIGO_DO_REGISTRO = re.compile(
    r"^\s*Art(?:igo|\.)\s+(?P<artigo>\d+(?:\.\d{3})*)\s*[º°o]?\s*(?:[-‐]\s*(?P<sufixo>[A-Z])\b)?"
    r"\s+d[aoe]s?\s+(?P<diploma>[^\n]+)",
    re.IGNORECASE,
)
_LEI_DO_REGISTRO = re.compile(
    r"(?P<tipo>Lei\s+Complementar|Decreto[-‐\s]*Lei|Lei)\s+n\s*[º°o.]?\s*(?P<numero>\d+(?:\.\d{3})*)"
    r"(?:[^\n]*?\b(?P<ano>(?:18|19|20)\d{2})\b)?",
    re.IGNORECASE,
)
_CF_DO_REGISTRO = re.compile(
    r"Constitui[çc][ãa]o\s+(?:Federal|da\s+Rep[úu]blica)(?:[^\n]*?\b(?P<ano>(?:18|19|20)\d{2})\b)?",
    re.IGNORECASE,
)


def chave_de_artigo(numero: str, sufixo: str | None = None) -> str:
    """Chave do artigo na tabela: "5", "5-A"; o milhar sai ("1.021" -> "1021")."""
    base = str(int(numero.replace(".", "")))
    return f"{base}-{sufixo.upper()}" if sufixo else base


def sumula_do_registro(texto: str, tribunal: str | None) -> tuple[str, bool, int] | None:
    """(tribunal, vinculante, número) da primeira linha do registro, ou None."""
    m = _SUMULA_DO_REGISTRO.match(texto)
    if m is None:
        return None
    vinculante = bool(m.group("vinculante"))
    sigla = (m.group("tribunal") or tribunal or ("STF" if vinculante else "")).upper()
    if not sigla:
        return None
    return sigla, vinculante, int(m.group("numero"))


def dispositivo_do_registro(texto: str) -> tuple[str, str, str | None, int | None] | None:
    """(código, artigo, número da lei, ano) da primeira linha do registro, ou None.

    Só a Constituição Federal de 1988 entra como `CF`; outra constituição fica fora.
    """
    m = _ARTIGO_DO_REGISTRO.match(texto)
    if m is None:
        return None
    artigo = chave_de_artigo(m.group("artigo"), m.group("sufixo"))
    diploma = m.group("diploma")
    if (cf := _CF_DO_REGISTRO.match(diploma)) is not None:
        ano = int(cf.group("ano")) if cf.group("ano") else None
        if ano not in (None, 1988):
            return None
        return "CF", artigo, None, 1988
    lei = _LEI_DO_REGISTRO.match(diploma)
    if lei is None:
        return None
    tipo = re.sub(r"[-‐\s]+", " ", lei.group("tipo").lower()).replace("decreto lei", "decreto-lei")
    numero = lei.group("numero").replace(".", "")
    ano = int(lei.group("ano")) if lei.group("ano") else None
    return codigo_da_lei(tipo, numero), artigo, numero, ano


@dataclass(frozen=True)
class Registro:
    """Um registro da base canônica, no mínimo necessário para resolver.

    ``classe`` (marcas da classe processual) só desempata registros com o mesmo número.
    """

    documento_id: str
    id_canonico: int
    tribunal: str | None
    texto_len: int
    classe: frozenset[str] = frozenset()


# Janela de cabeçalho do método baseline: cobre o número próprio de STF, STJ, TSE e STM.
LIMITE_CABECALHO = 400

# No TST o número próprio fica na fórmula de abertura do voto. A âncora é a frase,
# não o prefixo "TST-": "estes autos" separa o processo próprio dos apenas citados.
_ANCORAS = re.compile(r"(?:est[eo]s\s+autos|Vistos,?\s+relatados)", re.IGNORECASE)

# Da âncora até passar do número, sem alcançar a lista de partes.
JANELA_ANCORA = 360

# Referência a lei, não a processo: indexada, faria uma citação `inventada` sair `real`.
# Exige a palavra-chave antes do número; casar só pelo sufixo de ano partiria números
# CNJ como `7000380- 08.2023.7.00.0000`. "No" e "n" cobrem o ruído de OCR de "Nº".
_NUMERO_ABREVIADO = r"(?:\s*n[.ºo°]?)?"

_REFERENCIA_A_LEI = re.compile(
    r"(?:lei|lc|decreto(?:[-\s]lei)?|medida\s+provis[óo]ria|mp|emenda\s+constitucional|ec)"
    rf"(?:\s+complementar)?{_NUMERO_ABREVIADO}\s*\d{{1,3}}(?:\.\d{{3}})*\s*[/.]\s*(?:19|20)\d{{2}}",
    re.IGNORECASE,
)

# A mesma referência com ano em dois dígitos ("Lei nº 8.112/90"). Só com barra: com
# ponto, o trecho seria o começo de outro número.
_LEI_COM_ANO_CURTO = re.compile(
    r"\b(?:lei|lc|decreto(?:[-\s]lei)?|medida\s+provis[óo]ria|mp|emenda\s+constitucional|ec)"
    rf"(?:\s+(?:complementar|federal))?{_NUMERO_ABREVIADO}\s*\d{{1,3}}(?:\.\d{{3}})*"
    r"\s*/\s*\d{2}(?!\d)",
    re.IGNORECASE,
)

# Data da sessão no cabeçalho ("27/11/2024"). Data com ponto fica de propósito:
# `7.00.0000`, dentro do número CNJ do STM, tem essa forma.
_DATA_COM_BARRA = re.compile(r"\b\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}\b")

# Inscrição na OAB, nas duas grafias da base: "OAB: 12345/SP" e "SP123456".
_OAB = re.compile(
    r"OAB\s*[:/]?\s*[A-Z]{0,2}\s*[:/]?\s*\d[\d.\-]*(?:\s*/\s*[A-Z]{2})?|\b[A-Z]{2}\d{3,7}\b"
)

# Número próprio do TST (`TST-<classe>-<número>`); os demais números do começo da
# ementa ("ADI 1717-DF", "Tema 1046") são citação.
_NUMERO_DO_TST = re.compile(r"TST\s*-\s*[A-Za-z]+(?:\s*-\s*[A-Za-z]+)*\s*-\s*\d[\d.\-\s]*\d")

# Nos demais tribunais o número próprio vem antes do relator; depois vem o rol de partes.
_RELATOR = re.compile(r"\bRELATOR[A]?\s*:|\bRelator[a]?\s*:")

# Rótulo que marca o número seguinte como artigo, tema, súmula ou inciso.
_ROTULO_NAO_PROPRIO = re.compile(
    r"(?:(?<!\w)(?:arts?\.?|artigos?|temas?|s[úu]mulas?|incisos?)|§+)\s*(?:n[.ºo°]?\s*)?$",
    re.IGNORECASE,
)

# Número reivindicado por muitos registros é texto de fórmula, não identificador.
# Duplicatas legítimas dividem um número entre dois registros.
MAXIMO_REGISTROS_POR_NUMERO = 2

# Para número longo o corte conta textos distintos, não registros: a base tem o mesmo
# acórdão indexado várias vezes, e contar registros tiraria o número próprio de todos.
DIGITOS_NUMERO_LONGO = 10
LIMITE_ASSINATURA = 3000


# A baseline fica no código para comparação com o método estrutural (o padrão).
METODOS = ("baseline", "estrutural")
METODO_PADRAO = "estrutural"


def _regiao_baseline(texto: str) -> str:
    """Janela de offset fixo mais a primeira âncora da fórmula de abertura."""
    pedacos = [texto[:LIMITE_CABECALHO]]
    for casamento in _ANCORAS.finditer(texto):
        inicio = casamento.start()
        if inicio < LIMITE_CABECALHO:
            continue  # já coberto pelo cabeçalho
        pedacos.append(texto[inicio : inicio + JANELA_ANCORA])
        # Só a primeira: as repetições seguintes são o acórdão citando outras decisões.
        break
    return "\n".join(pedacos)


def _cabecalho_proprio(cabecalho: str, tribunal: str) -> str:
    """Só a parte do cabeçalho onde o número próprio pode estar."""
    if tribunal == "TST":
        return "\n".join(m.group() for m in _NUMERO_DO_TST.finditer(cabecalho))
    relator = _RELATOR.search(cabecalho)
    return cabecalho[: relator.start()] if relator else cabecalho


def _regiao_estrutural(texto: str, tribunal: str | None) -> str:
    """As zonas identificadoras da segmentação estrutural do documento."""
    tribunal = (tribunal or tribunal_do_texto(texto) or "").upper()
    pedacos = []
    for zona in zonas_de_identificacao(texto, tribunal or None):
        pedaco = zona.texto
        if zona.tipo == "cabecalho":
            pedaco = _cabecalho_proprio(pedaco, tribunal)
        pedacos.append(pedaco)
    return "\n".join(pedacos)


def regiao_de_identificacao(
    texto: str,
    tribunal: str | None = None,
    metodo: str = METODO_PADRAO,
) -> str:
    """Os trechos do acórdão que identificam o *próprio* processo, não os que citam outros.

    Separados por ``\\n`` para não colar o fim de um número no começo de outro.
    """
    if metodo not in METODOS:
        raise ValueError(f"método desconhecido: {metodo!r} (use um de {METODOS})")
    bruto = (
        _regiao_estrutural(texto, tribunal) if metodo == "estrutural" else _regiao_baseline(texto)
    )
    for nao_proprio in (_DATA_COM_BARRA, _OAB, _LEI_COM_ANO_CURTO, _REFERENCIA_A_LEI):
        bruto = nao_proprio.sub(" ", bruto)
    return bruto


def numeros_proprios(regiao: str) -> set[str]:
    """Os números da região que podem ser o número do próprio processo.

    Descarta o que a detecção recusaria como processo, o que segue rótulo de artigo,
    tema, súmula ou inciso, e a leitura conservadora que é só o começo da permissiva
    no mesmo ponto ("Nº 111-66. 2016…" não pode gerar a chave `11166`).
    """
    permissivos = {m.start(): re.sub(r"\D", "", m.group()) for m in _NUCLEO.finditer(regiao)}
    saida = set()
    for expressao in (_NUCLEO_LIMPO, _NUCLEO):
        for casamento in expressao.finditer(regiao):
            numero = re.sub(r"\D", "", casamento.group())
            if len(numero) < MINIMO_DIGITOS or _ANO.fullmatch(numero):
                continue
            antes = regiao[: casamento.start()]
            if _ROTULO_NAO_PROPRIO.search(antes[-20:]):
                continue
            if not _e_numero_de_processo(casamento.group(), antes, regiao[casamento.end() :]):
                continue
            inteiro = permissivos.get(casamento.start(), "")
            if (
                expressao is _NUCLEO_LIMPO
                and len(inteiro) > len(numero)
                and inteiro.startswith(numero)
            ):
                continue
            saida.add(numero)
    return saida


# Ano solto não é número próprio de processo nenhum da base.
_ANO = re.compile(r"(?:19|20)\d{2}")

# Classe do próprio processo: o que vem antes do número no cabeçalho; no TST, a
# classe da fórmula "estes autos de <Classe> nº TST-".
_FIM_DA_CLASSE = re.compile(r"\s(?:N\s?[º°o.]|\d)")
_CLASSE_DO_TST = re.compile(r"est[eo]s\s+autos\s+de\s+(.{3,220}?)\s+n?\s*[º°o.]?\s*TST", re.I)
JANELA_CLASSE = 260


def classe_do_cabecalho(texto: str, tribunal: str | None) -> str:
    """O nome da classe processual do próprio acórdão, como o cabeçalho o escreve."""
    if (tribunal or "").upper() == "TST":
        formula = _CLASSE_DO_TST.search(_ESPACOS.sub(" ", texto[:12000]))
        return formula.group(1) if formula else ""
    inicio = _ESPACOS.sub(" ", texto[:JANELA_CLASSE])
    fim = _FIM_DA_CLASSE.search(inicio, 12)
    return inicio[: fim.start()] if fim else inicio


# Leitura do banco. Uma falha aqui acontece antes do laço por documento e derrubaria
# o lote inteiro; por isso a leitura tolera banco somente leitura e dados sujos.

# Sem `ORDER BY` de propósito: a ordem do arquivo é determinística, e ordenar o texto
# no SQLite pediria arquivo temporário, que um volume somente leitura pode não ter.
_CONSULTA_DOCUMENTOS = (
    "SELECT documento_id, id, tribunal, natureza, texto, texto_len FROM documentos"
)


@dataclass(frozen=True)
class _Row:
    """Uma linha da tabela `documentos`, já normalizada e utilizável."""

    document_id: str
    canonical_id: int
    court: str | None
    nature: str
    text: str
    text_len: int


def _decode_text(valor: bytes) -> str:
    """Decodifica UTF-8 trocando byte inválido, em vez de abortar a varredura inteira."""
    return valor.decode("utf-8", errors="replace")


def _as_int(valor: object) -> int | None:
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    if isinstance(valor, str) and valor.strip().isdigit():
        return int(valor.strip())
    return None


def _normalize_nature(valor: object) -> str:
    return re.sub(r"\s", "", sem_acento(str(valor or ""))).lower()


def _normalize_row(linha: tuple) -> _Row | None:
    """A linha pronta para indexar, ou ``None`` sem texto ou sem ``id``.

    Linha descartada faz a citação sair ``inventada``, nunca ``real`` com id vazio.
    """
    documento_id, id_canonico, tribunal, natureza, texto, texto_len = linha
    id_canonico = _as_int(id_canonico)
    if id_canonico is None or not isinstance(texto, str) or not texto.strip():
        return None
    tribunal = str(tribunal).strip().upper() if tribunal is not None else ""
    tamanho = _as_int(texto_len)
    return _Row(
        document_id=str(documento_id) if documento_id is not None else str(id_canonico),
        canonical_id=id_canonico,
        court=tribunal or None,
        nature=_normalize_nature(natureza),
        text=texto,
        text_len=tamanho if tamanho is not None else len(texto),
    )


def _iter_rows(caminho_db: Path, immutable: bool) -> Iterator[_Row]:
    """As linhas utilizáveis do banco, aberto só para leitura via URI escapada."""
    uri = Path(caminho_db).resolve().as_uri() + "?mode=ro" + ("&immutable=1" if immutable else "")
    conexao = sqlite3.connect(uri, uri=True)
    conexao.text_factory = _decode_text
    descartadas = 0
    try:
        for linha in conexao.execute(_CONSULTA_DOCUMENTOS):
            normalizada = _normalize_row(linha)
            if normalizada is None:
                descartadas += 1
                continue
            yield normalizada
    finally:
        conexao.close()
    if descartadas:
        print(
            f"aviso: {descartadas} registro(s) sem texto ou sem id ignorados em {caminho_db}",
            file=sys.stderr,
        )


def _read_with_fallback(caminho_db: Path, consumir):
    """Aplica ``consumir`` às linhas do banco; se a leitura falhar, repete imutável.

    Banco WAL em volume somente leitura falha por não poder criar o ``-shm``.
    ``immutable=1`` contorna isso mas ignora um ``-wal`` presente, então só é usado
    depois que a leitura normal falhou.
    """
    try:
        return consumir(_iter_rows(caminho_db, immutable=False))
    except sqlite3.OperationalError as erro:
        print(
            f"aviso: leitura de {caminho_db} falhou ({erro}); repetindo com immutable=1",
            file=sys.stderr,
        )
        return consumir(_iter_rows(caminho_db, immutable=True))


def construir_indice(caminho_db: Path, metodo: str = METODO_PADRAO) -> dict:
    """Varre a base uma vez e devolve o índice de números próprios (feito offline)."""
    return _read_with_fallback(caminho_db, lambda linhas: _build_index(linhas, metodo))


def _build_index(linhas: Iterator[_Row], metodo: str) -> dict:
    numeros: dict[str, list[str]] = {}
    registros: dict[str, dict] = {}
    assinaturas: dict[str, str] = {}

    # Súmulas e dispositivos saem da mesma varredura, para passar pelo mesmo retry.
    outras: list[_Row] = []
    for linha in linhas:
        if linha.nature != "acordao":
            outras.append(linha)
            continue
        documento_id, texto, tribunal = linha.document_id, linha.text, linha.court
        registros[documento_id] = {
            "id": linha.canonical_id,
            "tribunal": tribunal,
            "texto_len": linha.text_len,
            "classe": sorted(marcas(classe_do_cabecalho(texto, tribunal))),
        }
        assinaturas[documento_id] = _ESPACOS.sub(" ", texto[:LIMITE_ASSINATURA])
        regiao = regiao_de_identificacao(texto, tribunal, metodo)
        for numero in numeros_proprios(regiao):
            numeros.setdefault(numero, []).append(documento_id)

    tabelas = _tabelas_de_sumulas_e_dispositivos(outras)

    def donos(numero: str, documentos: list[str]) -> int:
        if len(numero) >= DIGITOS_NUMERO_LONGO:
            return len({assinaturas[d] for d in documentos})
        return len(documentos)

    numeros = {
        numero: documentos
        for numero, documentos in numeros.items()
        if donos(numero, documentos) <= MAXIMO_REGISTROS_POR_NUMERO
    }
    return {"numeros": numeros, "registros": registros, **tabelas}


def _tabelas_de_sumulas_e_dispositivos(linhas: list[_Row]) -> dict:
    """As súmulas e os dispositivos do banco, lidos da primeira linha de cada um.

    Registro ilegível fica fora da tabela e é avisado em stderr; repetido fica com o
    primeiro na ordem de `documento_id`.
    """
    sumulas: dict[tuple[str, bool, int], int] = {}
    dispositivos: dict[tuple[str, str], int] = {}
    leis: dict[str, list[str | int | None]] = {}
    ilegiveis = []
    for linha in sorted(linhas, key=lambda r: r.document_id):
        if linha.nature == "sumula":
            chave = sumula_do_registro(linha.text, linha.court)
            if chave is None:
                ilegiveis.append(linha.document_id)
                continue
            sumulas.setdefault(chave, linha.canonical_id)
        elif linha.nature == "dispositivo":
            lido = dispositivo_do_registro(linha.text)
            if lido is None:
                ilegiveis.append(linha.document_id)
                continue
            codigo, artigo, numero, ano = lido
            dispositivos.setdefault((codigo, artigo), linha.canonical_id)
            leis.setdefault(codigo, [numero, ano])
    if ilegiveis:
        print(
            f"aviso: {len(ilegiveis)} súmula(s) ou dispositivo(s) sem identificação legível "
            f"ficam fora da cobertura: {', '.join(ilegiveis[:5])}",
            file=sys.stderr,
        )
    return {
        "sumulas": [[t, v, n, i] for (t, v, n), i in sorted(sumulas.items())],
        "dispositivos": [[c, a, i] for (c, a), i in sorted(dispositivos.items())],
        "leis": leis,
    }


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
                classe=frozenset(dados.get("classe", ())),
            )
            for documento_id, dados in indice["registros"].items()
        }
        # Índice sem tabelas não tem súmula nem dispositivo: tudo sai `inventada`.
        self._sumulas: dict[tuple[str, bool, int], int] = {
            (t, bool(v), int(n)): int(i) for t, v, n, i in indice.get("sumulas", [])
        }
        self._dispositivos: dict[tuple[str, str], int] = {
            (c, str(a)): int(i) for c, a, i in indice.get("dispositivos", [])
        }
        self._leis: dict[str, tuple[str | None, int | None]] = {
            c: (n, a) for c, (n, a) in indice.get("leis", {}).items()
        }

    @classmethod
    def de_arquivo(cls, caminho: Path) -> BaseCanonica:
        return cls(json.loads(caminho.read_text(encoding="utf-8")))

    @classmethod
    def de_banco(cls, caminho_db: Path) -> BaseCanonica:
        return cls(construir_indice(caminho_db))

    def candidatos_por_numero(self, numero: str) -> list[Registro]:
        """Registros que têm esse número como número próprio, em ordem determinística.

        A ordem é só estabilidade, não preferência: o primeiro da lista não é a resposta.
        """
        if len(numero) < MINIMO_DIGITOS:
            return []
        candidatos = [self._registros[d] for d in self._numeros.get(numero, [])]
        return sorted(candidatos, key=lambda r: (-r.texto_len, r.documento_id))

    def sumula(self, tribunal: str | None, vinculante: bool, numero: int) -> int | None:
        if vinculante:
            # Súmula vinculante só existe no STF; com outro tribunal é outra súmula.
            if tribunal not in (None, "STF"):
                return None
            return self._sumulas.get(("STF", True, numero))
        if tribunal is None:
            return None
        return self._sumulas.get((tribunal, False, numero))

    def dispositivo(self, codigo: str | None, artigo: str | None) -> int | None:
        if codigo is None or artigo is None:
            return None
        return self._dispositivos.get((codigo, artigo))

    def lei(self, codigo: str) -> tuple[str | None, int | None] | None:
        """(número, ano) do diploma como o banco o declara, se ele tiver algum artigo."""
        return self._leis.get(codigo)

    @property
    def sumulas(self) -> dict[tuple[str, bool, int], int]:
        return dict(self._sumulas)

    @property
    def dispositivos(self) -> dict[tuple[str, str], int]:
        return dict(self._dispositivos)

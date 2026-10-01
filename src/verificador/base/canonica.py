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
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ..deteccao.detector import _e_numero_de_processo
from ..juridico.classes import marcas
from ..juridico.leis import codigo_da_lei
from ..normalizacao import _ESPACOS, _NUCLEO, _NUCLEO_LIMPO, sem_acento
from .estrutura import tribunal_do_texto, zonas_de_identificacao

# Abaixo de 4 dígitos um número não identifica processo nenhum — só gera ruído.
MINIMO_DIGITOS = 4

# ---------------------------------------------------------------------------
# Súmulas e dispositivos: lidos do banco recebido.
#
# Até 30/09/2026 esta era uma tabela curada à mão, com os ids do banco de
# desenvolvimento. A avaliação final usa **outro** banco, e uma tabela fixa erra
# nas duas direções: a súmula que o banco novo tem e a tabela não sai
# `inventada`, e a que a tabela tem e o banco novo não sai `real` — o erro grave
# da métrica. Medido com um banco modificado: Súmula 83/STJ e art. 14 do CDC,
# retirados do banco, continuavam saindo `real`.
#
# Cada registro dessas naturezas abre com a própria identificação ("Súmula n. 83
# do STJ", "Artigo 186 da Lei nº 10.406, de 10 de janeiro de 2002"), e a tabela
# é montada dessa linha. A cobertura continua fechada: fora da tabela, é
# `inventada`. O que liga a lei ao nome do diploma na prosa está em
# :mod:`verificador.leis`, que é fato de direito e não depende da base.
# ---------------------------------------------------------------------------

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
    """A chave do artigo na tabela: "896", "896-A". O milhar sai: "1.021" -> "1021"."""
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

    Só a Constituição **Federal** entra como `CF`; constituição estadual ou de
    outro ano não é identificada e fica fora da tabela — é o lado seguro.
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

    ``classe`` são as marcas da classe processual do cabeçalho (ver
    :mod:`verificador.classe`), usadas só para desempatar registros que dividem
    o mesmo número próprio. Índice construído antes dela não a tem, e aí o
    desempate cai na ordem estável.
    """

    documento_id: str
    id_canonico: int
    tribunal: str | None
    texto_len: int
    classe: frozenset[str] = frozenset()


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

# A mesma referência com o ano em dois dígitos ("Lei nº 9.504/97", "Lei Federal
# nº 8.112/90"), que a expressão acima não pega: o número entrava no índice como
# `950497` e a citação `inventada` que o usasse resolvia para o acórdão. Só com
# barra: com ponto, "13.467.20…" seria o começo de outro número.
_LEI_COM_ANO_CURTO = re.compile(
    r"\b(?:lei|lc|decreto(?:[-\s]lei)?|medida\s+provis[óo]ria|mp|emenda\s+constitucional|ec)"
    rf"(?:\s+(?:complementar|federal))?{_NUMERO_ABREVIADO}\s*\d{{1,3}}(?:\.\d{{3}})*"
    r"\s*/\s*\d{2}(?!\d)",
    re.IGNORECASE,
)

# Data com barra: a data da sessão abre o cabeçalho do STF ("27/11/2024") e o do
# STM ("SESSÃO VIRTUAL DE 16/03/2026"), e entrava no índice como `27112024`. A
# data com ponto fica de propósito: `7.00.0000`, dentro do número CNJ do STM,
# tem essa forma.
_DATA_COM_BARRA = re.compile(r"\b\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}\b")

# Inscrição na OAB, nas duas grafias da base: "OAB: 12345/SP" (TSE) e o número
# colado à UF no rol de advogados do STJ ("SP123456").
_OAB = re.compile(
    r"OAB\s*[:/]?\s*[A-Z]{0,2}\s*[:/]?\s*\d[\d.\-]*(?:\s*/\s*[A-Z]{2})?|\b[A-Z]{2}\d{3,7}\b"
)

# O número próprio do TST, na forma em que ele aparece: `TST-<classe>-<número>`.
# O "cabeçalho" do TST é o começo da ementa, e os demais números dele são
# citação — "ADI 1717-DF", "Tema 1046" — que faziam o acórdão responder por um
# processo que ele só menciona.
_NUMERO_DO_TST = re.compile(r"TST\s*-\s*[A-Za-z]+(?:\s*-\s*[A-Za-z]+)*\s*-\s*\d[\d.\-\s]*\d")

# No cabeçalho dos demais tribunais, o número próprio vem antes do relator; o
# que vem depois é o rol de partes, com seus números ("COATOR: RELATOR DO HC Nº
# 604.005", a inscrição dos advogados).
_RELATOR = re.compile(r"\bRELATOR[A]?\s*:|\bRelator[a]?\s*:")

# Rótulo que marca o número seguinte como artigo, tema, súmula ou inciso, e não
# como processo: "art. 1.021", "Tema 1046". Os rótulos de distrator e de ato
# normativo já vêm de `deteccao._e_numero_de_processo`, aplicada aqui também.
_ROTULO_NAO_PROPRIO = re.compile(
    r"(?:(?<!\w)(?:arts?\.?|artigos?|temas?|s[úu]mulas?|incisos?)|§+)\s*(?:n[.ºo°]?\s*)?$",
    re.IGNORECASE,
)

# Um número que muitos registros reivindicam como próprio não é identificador —
# é texto de fórmula. Os pares de duplicata conhecidos da base compartilham um
# número entre *dois* registros; acima disso é vazamento da região, e deixar
# entrar custa τ. Este corte é independente de reconhecer sintaxe de lei, então
# pega também o que a regex acima não descreve.
MAXIMO_REGISTROS_POR_NUMERO = 2

# Para número longo (CNJ, número único do STJ), o corte conta **textos
# distintos**, não registros: a base tem acórdãos indexados três e quatro vezes
# com o mesmo texto, e contar registros tirava do índice o número próprio de
# todos eles. Número longo não é fórmula; o curto continua contado por registro.
DIGITOS_NUMERO_LONGO = 10
LIMITE_ASSINATURA = 3000


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


def _cabecalho_proprio(cabecalho: str, tribunal: str) -> str:
    """Só a parte do cabeçalho onde o número próprio pode estar."""
    if tribunal == "TST":
        return "\n".join(m.group() for m in _NUMERO_DO_TST.finditer(cabecalho))
    relator = _RELATOR.search(cabecalho)
    return cabecalho[: relator.start()] if relator else cabecalho


def _regiao_estrutural(texto: str, tribunal: str | None) -> str:
    """As zonas identificadoras da segmentação, por espécie de tribunal.

    Em vez de supor onde o número está, segmenta o documento e pega as zonas em
    que ele *pode* estar — ver :mod:`verificador.estrutura`.
    """
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
    for nao_proprio in (_DATA_COM_BARRA, _OAB, _LEI_COM_ANO_CURTO, _REFERENCIA_A_LEI):
        bruto = nao_proprio.sub(" ", bruto)
    return bruto


def numeros_proprios(regiao: str) -> set[str]:
    """Os números da região que podem ser o número do próprio processo.

    Parte das duas leituras de :func:`numeros_do_texto` e descarta três coisas:

    * o que a detecção também recusaria como processo — página, data, ano,
      inscrição, ato normativo —, com a mesma regra dos dois lados
      (`deteccao._e_numero_de_processo`);
    * o que vem depois de rótulo de artigo, tema, súmula ou inciso;
    * a leitura conservadora que é só o começo da permissiva no mesmo ponto: em
      "Nº 111-66. 2016.6.26…" o espaço parte o número, e o pedaço `11166` virava
      chave sem ser número de nada — a `Rcl nº 11.166` inventada resolvia por ele.
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


# Ano solto não é número próprio de processo nenhum da base (conferido).
_ANO = re.compile(r"(?:19|20)\d{2}")

# O trecho do cabeçalho que nomeia a classe do próprio processo: o que vem antes
# do número, até onde o cabeçalho dos quatro tribunais regulares o põe (a folga
# cobre "EMB.DECL. NO AG.REG. NOS EMB.DECL. NO RECURSO EXTRAORDINÁRIO COM
# AGRAVO"). No TST, a classe está na fórmula "estes autos de <Classe> nº TST-".
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


# ---------------------------------------------------------------------------
# Leitura do banco.
#
# A avaliação final roda o nosso código sobre um banco que não vimos, montado
# num volume que pode ser somente leitura. Tudo aqui existe porque uma falha na
# leitura acontece **antes** do laço por documento, onde não há proteção: uma
# exceção derruba o lote inteiro e nenhum JSON é escrito.
# ---------------------------------------------------------------------------

# Todas as naturezas de uma vez, e a comparação fica em Python: sem caixa, sem
# espaço e sem acento ("Acordao ", "acórdão"). Sem `ORDER BY` de propósito: a
# varredura segue a ordem do arquivo, que é determinística e é a mesma da
# consulta antiga, e ordenar ~90 MB de texto no SQLite pediria arquivo temporário
# — que um container somente leitura pode não ter.
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
    """Texto do banco com byte inválido trocado, em vez de exceção.

    O `sqlite3` decodifica TEXT como UTF-8 estrito e, num registro com byte
    inválido, levanta `OperationalError` no meio da varredura — o índice inteiro
    se perdia por um registro. Para UTF-8 válido o resultado é o mesmo.
    """
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
    """A linha pronta para indexar, ou ``None`` se ela não tiver como responder.

    Sem texto não há o que indexar nem de onde tirar a identificação, e sem
    ``id`` não há o que pôr em ``id_canonico``: a linha fica de fora, e a citação
    que a buscaria sai ``inventada`` — nunca ``real`` com um id vazio.
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
    """As linhas utilizáveis do banco, abrindo-o só para leitura.

    O caminho vai numa URI escapada: com o caminho cru interpolado, um diretório
    com espaço, ``?`` ou ``#`` no nome mudava o significado da URI.
    """
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

    Banco em modo WAL num volume somente leitura dá "attempt to write a readonly
    database" na primeira leitura: o SQLite precisa criar o ``-shm`` ao lado, e
    não pode. Reproduzido, derrubava o lote inteiro. ``immutable=1`` dispensa o
    ``-shm``, mas também **ignora** um ``-wal`` presente — o que ainda não foi
    consolidado no arquivo principal sumiria em silêncio —, então só entra
    depois que a leitura normal falhou. A varredura recomeça do zero: nada do
    que a primeira tentativa acumulou é reaproveitado.
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
    """Varre a base uma vez e devolve o índice de números próprios.

    Feito offline: em runtime só carregamos o JSON. O material do desafio
    recomenda explicitamente esse caminho em vez de varrer o FTS a cada citação.
    """
    return _read_with_fallback(caminho_db, lambda linhas: _build_index(linhas, metodo))


def _build_index(linhas: Iterator[_Row], metodo: str) -> dict:
    numeros: dict[str, list[str]] = {}
    registros: dict[str, dict] = {}
    assinaturas: dict[str, str] = {}

    # Súmulas e dispositivos saem da mesma varredura: a leitura robusta é uma só,
    # e uma segunda consulta ao banco não passaria pelo retry imutável.
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

    # Descarta o que muitos registros reivindicam: é fórmula, não identificador.
    # Ver MAXIMO_REGISTROS_POR_NUMERO e DIGITOS_NUMERO_LONGO.
    numeros = {
        numero: documentos
        for numero, documentos in numeros.items()
        if donos(numero, documentos) <= MAXIMO_REGISTROS_POR_NUMERO
    }
    return {"numeros": numeros, "registros": registros, **tabelas}


def _tabelas_de_sumulas_e_dispositivos(linhas: list[_Row]) -> dict:
    """As súmulas e os dispositivos do banco, lidos da primeira linha de cada um.

    Registro que não se deixa ler fica fora da tabela — a citação dele sai
    `inventada` — e é avisado em stderr, porque é perda silenciosa de cobertura.
    Registro repetido fica com o primeiro na ordem de `documento_id`.
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
        # Índice sem as tabelas (JSON antigo, ou a base vazia dos testes) não
        # tem súmula nem dispositivo: tudo o que citar um deles é `inventada`.
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
            # Súmula vinculante só existe no STF. Com outro tribunal nomeado
            # ("Súmula Vinculante 10 do STJ") a citação é de outra súmula, e
            # ignorar o tribunal a resolvia para a SV 10 — `inventada` → `real`.
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

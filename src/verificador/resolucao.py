"""Da citação detectada à classe, consultando a base canônica.

A classe decorre da cardinalidade da consulta: um candidato é ``real``, nenhum é
``inventada`` e citação sem identificador suficiente é ``incompleta``.
"""

from __future__ import annotations

import re

from .base import BaseCanonica, chave_de_artigo
from .deteccao import Achado, sigla_do_tribunal
from .juridico.classes import afinidade, marcas
from .juridico.leis import ANO_DA_LEI, NUMERO_DA_LEI, codigo_da_lei, lei_pelo_nome
from .normalizacao import (
    CONFUSOES_DE_LETRA,
    OCR_PARA_DIGITO,
    _corrigir_ocr,
    chave_textual,
    digitos_do_identificador,
)

# Confiança por caminho de decisão, que alimenta o bônus de calibração (Brier).
# A moeda entre cópias idênticas fica em 0,5, que minimiza o Brier de um chute
# honesto entre dois candidatos.
CONFIANCA = {
    "real_unico": 1.0,
    "real_desempate_classe": 1.0,
    "real_desempate": 0.50,
    "real_tabela": 1.0,
    "inventada_processo": 1.0,
    "inventada_tabela": 1.0,
    "inventada_tema": 1.0,
    "incompleta_vaga": 1.0,
    # Inalcançável por invariante: nenhuma família detecta citação sem número.
    # Fica como defesa caso a detecção afrouxe.
    "incompleta_sem_numero": 0.70,
}

# Diploma citado -> código da tabela de dispositivos. A ordem importa: a entrada
# mais específica vem antes da que a contém ("processo penal militar" antes de
# "processo penal", CPPM/CPP/CPM antes de CP), senão o CPPM resolveria para o CPP.
# O segundo elemento são exclusões que impedem o marcador genérico de capturar
# outro diploma. O casamento é por conteúdo porque o ruído corrompe letras.
DIPLOMAS: tuple[tuple[tuple[str, ...], tuple[str, ...], str], ...] = (
    (("processo penal militar", "cppm"), (), "CPPM"),
    (("processo civil", "13.105", "13105", "cpc", "ncpc"), (), "CPC"),
    (("processo penal", "3.689", "3689", "cpp"), ("militar",), "CPP"),
    (("penal militar", "1.001", "1001", "cpm"), (), "CPM"),
    (("defesa do consumidor", "codigo do consumidor", "8.078", "8078", "cdc"), (), "CDC"),
    (("consolidacao das leis", "clt", "5.452", "5452"), (), "CLT"),
    (
        (
            "constituic",
            "carta magna",
            "lei maior",
            "carta politica",
            "carta da republica",
            "cf",
            "crfb",
        ),
        (),
        "CF",
    ),
    (("lei complementar", "lc", "64/1990"), (), "LC64"),
    (("eleitoral", "4.737", "4737"), (), "ELEITORAL"),
    (("civil", "cc", "10.406", "10406"), (), "CC"),
    (("codigo penal", "cp", "2.848", "2848"), ("militar", "processo"), "CP"),
    (("tributario nacional", "ctn", "5.172", "5172"), (), "CTN"),
    (("crianca e do adolescente", "eca", "8.069", "8069"), (), "ECA"),
    (("transito brasileiro", "ctb", "9.503", "9503"), (), "CTB"),
)

# Número da lei citada ("lei no 13.105/2015", "lc 64/90"), com ano opcional. A
# âncora em "lei"/"lc"/"decreto" evita confundir o ano de versão com o número.
_LEI_NUMERADA = re.compile(r"\b(?:lei|lc|decreto)\b\D{0,24}?(\d(?:[\d.]*\d)?)(?:\s*/\s*(\d{2,4}))?")

# O ano de versão depois do nome ou da sigla: "de 1916", "cpc/73", "cf/88".
_ANO_DE_VERSAO = re.compile(r"(?:\bde\s+|/\s*)(\d{2,4})\b")

# Qualificadores que identificam a CF/88. A lista é de inclusão: qualquer outro
# (Estadual, Portuguesa) é outro diploma. A de 1967 "do Brasil" é barrada pelo ano.
_QUALIFICADORES_DA_CF = ("federal", "republica", "federativa", "brasileira", "brasil", "cidada")
_CONECTORES = frozenset({"da", "do", "de", "das", "dos"})


def _ano(texto: str) -> int | None:
    """Ano com quatro dígitos, ou com dois como em "CPC/73". Outra forma não é ano."""
    if len(texto) == 4:
        return int(texto)
    if len(texto) == 2:
        ano = int(texto)
        return ano + (2000 if ano <= 30 else 1900)
    return None


def _distancia(a: str, b: str) -> int:
    """Distância de edição, para o qualificador corrompido pelo nível 2."""
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        atual = [i]
        for j, cb in enumerate(b, start=1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (ca != cb)))
        anterior = atual
    return anterior[-1]


def _qualificador_da_cf_confere(chave: str) -> bool:
    """A Constituição citada é a de 1988?

    O qualificador é comparado com tolerância de edição por causa do ruído de
    letra; os qualificadores perigosos (Estadual, Portuguesa) ficam longe dos aceitos.
    """
    if re.fullmatch(r"(?:cf|crfb)(?:\s*/\s*\d{2,4})?", chave):
        return True
    # Remove o nome ou apelido; o resto passa pela regra dos qualificadores
    # (senão "Carta da República Portuguesa" viraria a CF).
    resto = re.sub(
        r"^(?:constitui\w*|cf|carta magna|lei maior|carta politica|carta da republica)\b",
        "",
        chave,
    )
    resto = _ANO_DE_VERSAO.sub(" ", resto)  # o ano já foi conferido
    palavras = [p for p in resto.split() if p not in _CONECTORES]
    # Toda palavra restante precisa ser qualificador da CF/88.
    return all(
        any(_distancia(p, q) <= (2 if len(q) >= 7 else 1) for q in _QUALIFICADORES_DA_CF)
        for p in palavras
    )


# Vocabulário fechado contra o qual o ruído de letra é desfeito. `militar` e
# `estadual` estão aqui para que `Mllitar` volte a `militar` e o CPPM não passe
# por CPP; os conectores entram porque também sofrem ruído ("d0", "da5").
_VOCABULARIO_DE_DIPLOMA = frozenset(
    """
    codigo processo civil penal militar defesa consumidor consolidacao leis
    trabalho constituicao federal republica federativa brasil brasileira
    estadual estado eleitoral lei complementar decreto carta magna
    de do da das dos
    """.split()
)

# Inverso de `CONFUSOES_DE_LETRA` e das trocas de letra por dígito (`Civi1`):
# cada forma corrompida e a letra minúscula que ela pode ter substituído.
_DESFAZER = (
    [(corrompida, original) for original, corrompida in CONFUSOES_DE_LETRA.items()]
    + [("ri", "n"), ("ii", "u"), ("rn", "m")]
    + [(digito, letra.lower()) for letra, digito in OCR_PARA_DIGITO.items()]
)


def _variantes(palavra: str) -> set[str]:
    """Todas as palavras a uma confusão de letra de distância, desfeita."""
    saida = set()
    for corrompida, original in _DESFAZER:
        inicio = palavra.find(corrompida)
        while inicio != -1:
            saida.add(palavra[:inicio] + original + palavra[inicio + len(corrompida) :])
            inicio = palavra.find(corrompida, inicio + 1)
    return saida


def _desfazer_ruido_de_letra(chave: str) -> str:
    """Desfaz o ruído de letra no nome do diploma, pois os marcadores são literais.

    Só palavra fora do vocabulário é corrigida, e só para uma palavra dentro dele.
    """
    palavras = []
    for palavra in chave.split():
        if palavra not in _VOCABULARIO_DE_DIPLOMA:
            # Até duas confusões por palavra (`Fcdcral`); o vocabulário fechado
            # impede que a segunda rodada abra casamentos espúrios.
            vizinhas = _variantes(palavra)
            candidatas = vizinhas & _VOCABULARIO_DE_DIPLOMA
            if not candidatas:
                segundas = {v2 for v in vizinhas for v2 in _variantes(v)}
                candidatas = segundas & _VOCABULARIO_DE_DIPLOMA
            if len(candidatas) == 1:
                palavra = candidatas.pop()
        palavras.append(palavra)
    return " ".join(palavras)


def _contem_marcador(chave: str, marcador: str) -> bool:
    """O marcador aparece na chave como palavra, e não dentro de outra?

    Só marcadores curtos exigem fronteira (`cdc` não pode casar em `fcdcral`).
    """
    if len(marcador) > 4:
        return marcador in chave
    return re.search(rf"(?<![a-z0-9]){re.escape(marcador)}(?![a-z0-9])", chave) is not None


_LEI_DE_OUTRO_ENTE = re.compile(r"\blei\s+(?:complementar\s+)?(?:estadual|municipal|distrital)\b")

# Nacionalidade estrangeira tira o código da cobertura ("Código Civil Português");
# "brasileiro" e "nacional" continuam valendo.
_NACIONALIDADE_ESTRANGEIRA = re.compile(
    r"\b(?:portugu[eê]s|francesa?|frances|italian[oa]|alem[aã]o?|espanhol|argentin[oa]|"
    r"chilen[oa]|uruguai[oa]|paraguai[oa]|american[oa]|norte-american[oa]|estrangeir[oa]|"
    r"suic[oa]|japon[eê]s|ingl[eê]s|mexican[oa]|colombian[oa]|peruan[oa]|"
    r"napole[oô]nico|europeu|canon(?:ico)?)\b"
)


def _codigo_estrangeiro(chave: str) -> bool:
    """O diploma citado é um código, mas de outro país?"""
    return chave.startswith("codigo") and _NACIONALIDADE_ESTRANGEIRA.search(chave) is not None


def _chave_do_diploma(diploma: str) -> str:
    """O nome do diploma com o ruído de letra desfeito e o número reparado.

    O nome é desfeito antes do reparo de OCR (senão "Mi1itar" vira `m111tar`); o
    número é reparado no texto original, pois o OCR depende da caixa (`G`→6, `g`→9).
    """
    nomes = _desfazer_ruido_de_letra(chave_textual(diploma)).split()
    numeros = chave_textual(_corrigir_ocr(diploma)).split()
    if len(nomes) != len(numeros):
        return " ".join(numeros)

    def e_numero(palavra: str) -> bool:
        # Número tem mais dígito que letra; palavra com dígito perdido, o contrário.
        return sum(c.isdigit() for c in palavra) > sum(c.isalpha() for c in palavra)

    return " ".join(
        numero if e_numero(numero) else nome for nome, numero in zip(nomes, numeros, strict=True)
    )


def _codigo_do_diploma(diploma: str | None, base: BaseCanonica | None = None) -> str | None:
    """Reduz o nome citado do diploma ao código da tabela de dispositivos.

    Devolve ``None`` (tratado como `inventada`) quando o diploma não é
    identificável ou é outro. O número da lei, quando citado, prevalece sobre o nome.
    """
    if not diploma:
        return None
    chave = _chave_do_diploma(diploma)
    # Lei estadual ou municipal com número de lei federal é outro diploma.
    if _LEI_DE_OUTRO_ENTE.search(chave):
        return None
    lei = _LEI_NUMERADA.search(chave)
    if lei is not None:
        codigo = codigo_da_lei(_tipo_da_lei(chave[: lei.start(1)]), lei.group(1))
        ano = lei.group(2)
        if ano is None:
            versao = _ANO_DE_VERSAO.search(chave, lei.end(1))
            ano = versao.group(1) if versao else None
        return codigo if _ano_confere(ano, codigo, base) else None
    # Antes dos marcadores genéricos: "Lei da Ação Civil Pública" contém "civil".
    if (pelo_nome := lei_pelo_nome(chave)) is not None:
        codigo, ano_da_lei = pelo_nome
        versao = _ANO_DE_VERSAO.search(chave)
        if versao is not None and _ano(versao.group(1)) != ano_da_lei:
            return None
        return codigo
    if _codigo_estrangeiro(chave):
        return None
    for marcadores, exclusoes, codigo in DIPLOMAS:
        if not any(_contem_marcador(chave, marcador) for marcador in marcadores):
            continue
        if any(exclusao in chave for exclusao in exclusoes):
            return None
        return codigo if _diploma_confere(chave, codigo) else None
    return None


# Tipo da lei tolerante a ruído de letra ("Dccreto-Lei", "Lci Complementar"): a
# palavra com hífen não passa por `_desfazer_ruido_de_letra`.
_DECRETO_LEI = re.compile(r"\bd[eco][eco]r[eco]t[o0]\b")
_LEI_COMPLEMENTAR = re.compile(r"\b(?:l[eci1][il1]\s+c[o0]mpl[eco]m[eco]nt[aã]r|lc)\b")


def _tipo_da_lei(antes_do_numero: str) -> str:
    """O tipo da lei — lei complementar, decreto-lei ou lei — pelo que vem antes do número."""
    if _LEI_COMPLEMENTAR.search(antes_do_numero):
        return "lei complementar"
    if _DECRETO_LEI.search(antes_do_numero):
        return "decreto-lei"
    return "lei"


def _ano_confere(ano: str | None, codigo: str, base: BaseCanonica | None) -> bool:
    """O ano citado, se houver, é o do diploma — pelo fato de direito ou pelo banco?"""
    if ano is None:
        return True
    esperado = ANO_DA_LEI.get(codigo)
    if esperado is None and base is not None and (declarado := base.lei(codigo)):
        esperado = declarado[1]
    return esperado is None or _ano(ano) == esperado


def _diploma_confere(chave: str, codigo: str) -> bool:
    """O número e o ano citados, quando houver, são os do diploma da cobertura?

    Na dúvida recusa: `inventada` → `real` é o erro grave da métrica.
    """
    ano: str | None = None
    lei = _LEI_NUMERADA.search(chave)
    if lei is not None:
        if lei.group(1).replace(".", "") != NUMERO_DA_LEI.get(codigo):
            return False
        ano = lei.group(2)
    if ano is None:
        versao = _ANO_DE_VERSAO.search(chave)
        ano = versao.group(1) if versao else None
    if ano is not None and _ano(ano) != ANO_DA_LEI.get(codigo):
        return False
    if codigo == "CF":
        return _qualificador_da_cf_confere(chave)
    return True


def _inteiro(valor: str | None) -> int | None:
    """O número da súmula ou do artigo, com o ruído de OCR desfeito.

    O reparo vem antes de extrair os dígitos, senão `3l73` encolheria para 373.
    """
    if not valor:
        return None
    digitos = "".join(c for c in _corrigir_ocr(valor) if c.isdigit())
    return int(digitos) if digitos else None


# Ordinal de artigo (1 a 9): "5º", "5o", "1°". O "o" minúsculo é ordinal, não
# zero; o "O" maiúsculo fica de fora porque é confusão de OCR comum.
_ORDINAL = re.compile(rf"^([1-9])\s*[ºo°ª](?![\d{''.join(sorted(set(OCR_PARA_DIGITO)))}])")


# Artigo com sufixo de letra (`896-A`) é outro artigo; a chave preserva o sufixo.
_SUFIXO_DE_ARTIGO = re.compile(r"^(?P<numero>.*?\d)\s*[-‐]\s*(?P<letra>[A-Za-z])\s*$")


def _chave_de_artigo(valor: str | None) -> str | None:
    """A chave do artigo citado na tabela de dispositivos: "5", "896", "896-A"."""
    if not valor:
        return None
    sufixo = None
    if (com_sufixo := _SUFIXO_DE_ARTIGO.match(valor)) is not None:
        valor, sufixo = com_sufixo.group("numero"), com_sufixo.group("letra")
    if (ordinal := _ORDINAL.match(valor)) is not None:
        numero: int | None = int(ordinal.group(1))
    else:
        numero = _inteiro(valor)
    return None if numero is None else chave_de_artigo(str(numero), sufixo)


def _tribunal_da_sumula(dados: dict[str, str]) -> str | None:
    """A sigla do tribunal, venha como sigla ou por extenso (grupo `ext_<SIGLA>`)."""
    for grupo in ("tribunal", "tribunal_par", "tribunal_do"):
        if dados.get(grupo):
            return sigla_do_tribunal(dados[grupo])
    for grupo in dados:
        if grupo.startswith("ext_"):
            return grupo.removeprefix("ext_")
    return None


def _resolver_sumula(dados: dict[str, str], base: BaseCanonica) -> tuple[str, int | None, float]:
    numero = _inteiro(dados.get("numero"))
    if numero is None:
        return "incompleta", None, CONFIANCA["incompleta_sem_numero"]
    vinculante = bool(dados.get("vinculante") or dados.get("sv"))
    tribunal = _tribunal_da_sumula(dados)
    if dados.get("enunciado") and tribunal != "TST":
        # "Enunciado" só identifica súmula quando é do TST.
        return "inventada", None, CONFIANCA["inventada_tabela"]
    id_canonico = base.sumula(tribunal, vinculante, numero)
    if id_canonico is None:
        return "inventada", None, CONFIANCA["inventada_tabela"]
    return "real", id_canonico, CONFIANCA["real_tabela"]


def _resolver_dispositivo(
    dados: dict[str, str], base: BaseCanonica
) -> tuple[str, int | None, float]:
    artigo = _chave_de_artigo(dados.get("artigo"))
    diploma = dados.get("diploma") or dados.get("diploma_sigla")
    # O ano por extenso só é conferido na lei citada pelo número ("Lei nº 9.999, de
    # 2000"); depois de um nome ("Código Civil, de 2002 em diante") pode ser prosa.
    ano = dados.get("ano_da_lei")
    if ano and _LEI_NUMERADA.search(_chave_do_diploma(diploma)) and "/" not in diploma:
        diploma = f"{diploma}/{ano}"
    codigo = _codigo_do_diploma(diploma, base)

    if artigo is None or not diploma:
        return "incompleta", None, CONFIANCA["incompleta_sem_numero"]
    if codigo is None:
        # Diploma nomeado mas fora da cobertura: é refutável, logo `inventada`.
        return "inventada", None, CONFIANCA["inventada_tabela"]

    id_canonico = base.dispositivo(codigo, artigo)
    if id_canonico is None:
        return "inventada", None, CONFIANCA["inventada_tabela"]
    return "real", id_canonico, CONFIANCA["real_tabela"]


def _resolver_processo(achado: Achado, base: BaseCanonica) -> tuple[str, int | None, float]:
    numero = digitos_do_identificador(achado.trecho)
    if not numero:
        return "incompleta", None, CONFIANCA["incompleta_sem_numero"]

    candidatos = base.candidatos_por_numero(numero)
    if not candidatos:
        return "inventada", None, CONFIANCA["inventada_processo"]
    if len(candidatos) == 1:
        return "real", candidatos[0].id_canonico, CONFIANCA["real_unico"]

    # Empate: incidentes do mesmo processo, separados pela classe. Com margem,
    # vence a classe mais afim à citação; sem margem fica o primeiro, porque
    # chutar um `real` custa menos que rebaixar para `incompleta`.
    da_citacao = marcas(achado.trecho)
    pontos = [afinidade(da_citacao, c.classe) for c in candidatos]
    melhor = max(range(len(candidatos)), key=lambda i: pontos[i])
    segundo = max(p for i, p in enumerate(pontos) if i != melhor)
    if pontos[melhor] > segundo:
        return "real", candidatos[melhor].id_canonico, CONFIANCA["real_desempate_classe"]
    return "real", candidatos[0].id_canonico, CONFIANCA["real_desempate"]


def resolver(achado: Achado, base: BaseCanonica) -> tuple[str, int | None, float]:
    """Classifica um achado e, quando ``real``, devolve o ``id_canonico``.

    Returns:
        ``(classificacao, id_canonico, confianca)`` — ``id_canonico`` é ``None``
        em tudo que não for ``real``.
    """
    dados = dict(achado.dados)

    if achado.familia == "vaga":
        # Tribunal + ano + relator nunca chega a um registro único.
        return "incompleta", None, CONFIANCA["incompleta_vaga"]

    if achado.familia == "sumula":
        return _resolver_sumula(dados, base)

    if achado.familia == "dispositivo":
        return _resolver_dispositivo(dados, base)

    if achado.familia == "tema":
        # A cobertura não tem registros de tema de repercussão geral.
        return "inventada", None, CONFIANCA["inventada_tema"]

    return _resolver_processo(achado, base)

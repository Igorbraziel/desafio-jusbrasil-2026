"""Contrato de saída: um JSON por documento processado, schema 1.2.

Formato publicado pela organização::

    {
      "schema_version": "1.2",
      "documento_id": "doc_0042",
      "citacoes": [
        {
          "id": "c1",
          "inicio": 1284,
          "fim": 1302,
          "trecho": "REsp 1.234.567/SP",
          "tipo": "jurisprudencia",
          "classificacao": "real",
          "resolucao": {"fonte": "jusbrasil", "id_canonico": "2106313729"},
          "confianca": 0.91
        }
      ]
    }

Na entrega final o JSON completo é obrigatório, com todos os campos — inclusive
``trecho`` e ``tipo``, que não entram na métrica.

``confianca`` é opcional, mas alimenta o bônus de calibração de até 10%; quem
não a envia não ganha nem perde por isso.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = "1.2"
FONTE = "jusbrasil"

TIPOS = {"jurisprudencia", "lei"}
CLASSIFICACOES = {"real", "inventada", "incompleta"}


@dataclass
class Citacao:
    """Uma citação detectada, classificada e (quando `real`) resolvida."""

    id: str
    inicio: int
    fim: int
    trecho: str
    tipo: str
    classificacao: str
    id_canonico: int | None = None
    confianca: float | None = None

    def para_dicionario(self) -> dict:
        # O exemplo oficial do contrato traz id_canonico como string; emitimos
        # no mesmo formato. Ver docs/contrato.md.
        resolucao = (
            {"fonte": FONTE, "id_canonico": str(self.id_canonico)}
            if self.classificacao == "real" and self.id_canonico is not None
            else None
        )
        saida = {
            "id": self.id,
            "inicio": self.inicio,
            "fim": self.fim,
            "trecho": self.trecho,
            "tipo": self.tipo,
            "classificacao": self.classificacao,
            "resolucao": resolucao,
        }
        if self.confianca is not None:
            saida["confianca"] = round(self.confianca, 4)
        return saida


@dataclass
class SaidaDocumento:
    documento_id: str
    citacoes: list[Citacao]

    def para_dicionario(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "documento_id": self.documento_id,
            "citacoes": [c.para_dicionario() for c in self.citacoes],
        }

    def escrever(self, pasta: Path) -> Path:
        pasta.mkdir(parents=True, exist_ok=True)
        caminho = pasta / f"{self.documento_id}.json"
        caminho.write_text(
            json.dumps(self.para_dicionario(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return caminho


def validar(saida: dict, texto: str | None = None) -> list[str]:
    """Confere um JSON de saída contra o contrato. Devolve a lista de problemas.

    Passando ``texto``, também confere que ``trecho == texto[inicio:fim]``.
    """
    problemas: list[str] = []

    if saida.get("schema_version") != SCHEMA_VERSION:
        problemas.append(f"schema_version deve ser {SCHEMA_VERSION!r}")
    if not isinstance(saida.get("documento_id"), str) or not saida["documento_id"]:
        problemas.append("documento_id ausente ou vazio")
    citacoes = saida.get("citacoes")
    if not isinstance(citacoes, list):
        return problemas + ["citacoes deve ser uma lista"]

    vistos: set[str] = set()
    for i, c in enumerate(citacoes):
        onde = f"citacoes[{i}]"
        for campo in ("id", "inicio", "fim", "trecho", "tipo", "classificacao"):
            if campo not in c:
                problemas.append(f"{onde}: campo obrigatório ausente: {campo}")
        if problemas and f"{onde}: campo obrigatório ausente" in problemas[-1]:
            continue
        if c.get("id") in vistos:
            problemas.append(f"{onde}: id repetido: {c['id']}")
        vistos.add(c.get("id"))
        if c.get("tipo") not in TIPOS:
            problemas.append(f"{onde}: tipo inválido: {c.get('tipo')!r}")
        if c.get("classificacao") not in CLASSIFICACOES:
            problemas.append(f"{onde}: classificacao inválida: {c.get('classificacao')!r}")
        inicio, fim = c.get("inicio"), c.get("fim")
        if not isinstance(inicio, int) or not isinstance(fim, int) or inicio < 0 or fim <= inicio:
            problemas.append(f"{onde}: span inválido ({inicio}, {fim}) — fim é exclusivo")
        elif texto is not None and c.get("trecho") != texto[inicio:fim]:
            problemas.append(f"{onde}: trecho não corresponde a texto[{inicio}:{fim}]")

        resolucao = c.get("resolucao")
        if c.get("classificacao") == "real":
            if not isinstance(resolucao, dict) or not resolucao.get("id_canonico"):
                problemas.append(f"{onde}: classe real exige resolucao com id_canonico")
        elif resolucao is not None:
            problemas.append(f"{onde}: resolucao deve ser null quando a classe não é real")

        confianca = c.get("confianca")
        if confianca is not None and not (0.0 <= float(confianca) <= 1.0):
            problemas.append(f"{onde}: confianca fora de [0, 1]: {confianca}")

    return problemas

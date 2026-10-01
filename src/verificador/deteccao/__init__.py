"""Detecção dos spans de citação no texto dos pareceres."""

from .detector import FAMILIAS, Achado, detectar, sigla_do_tribunal

__all__ = ["FAMILIAS", "Achado", "detectar", "sigla_do_tribunal"]

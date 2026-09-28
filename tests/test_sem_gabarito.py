"""O repositório é público e o gabarito não pode ser redistribuído.

O commit que tirou o conteúdo derivado do gabarito da documentação e dos testes
não deixou guarda, e números de citação do gabarito voltaram a aparecer em
comentários, testes e checkpoints. Este teste é a guarda: nenhum número de
cinco dígitos ou mais que identifica uma citação do gabarito pode estar nos
arquivos versionados. Os exemplos usam números sintéticos.

Números de **lei** ficam de fora: são públicos, e o código precisa deles para
conferir o diploma (o CPC é a Lei nº 13.105/2015).
"""

import csv
import re
import subprocess

from conftest import GOLDENSET, RAIZ, sem_dados

from verificador.normalizacao import OCR_PARA_DIGITO

pytestmark = sem_dados

# Número de processo com cinco ou mais dígitos, com a pontuação que o estrutura.
# Aceita a letra que o OCR põe no lugar do dígito (`1.23g.456`, `1G.234`): o
# nível 2 do gabarito traz números assim, e sem isto eles escapavam da guarda.
_DIGITOIDE = rf"[\d{''.join(sorted(OCR_PARA_DIGITO))}]"
_NUMERO = re.compile(rf"(?<![A-Za-z]){_DIGITOIDE}(?:[.\-]?{_DIGITOIDE}){{4,}}(?![A-Za-z])")

# Os diplomas da cobertura e os fora dela que o gabarito cita pelo número.
_NUMERO_DE_LEI = re.compile(r"(?i)\b(?:lei|lc|decreto)\b[^\n]{0,24}$")


def _digitos(texto: str) -> str:
    """Os dígitos do número, com a letra de OCR lida como o dígito que ela imita.

    Exige dois dígitos reais: sem isso, palavras feitas só de letras
    confundíveis ("Gols", "Isso") virariam números.
    """
    if sum(c.isdigit() for c in texto) < 2:
        return ""
    return "".join(OCR_PARA_DIGITO.get(c, c) for c in texto if c.isalnum())


def _numeros_do_gabarito() -> set[str]:
    numeros = set()
    with GOLDENSET.open(encoding="utf-8-sig") as f:
        for linha in csv.DictReader(f):
            trecho = linha["trecho"].replace("\\n", " ")
            for casamento in _NUMERO.finditer(trecho):
                if _NUMERO_DE_LEI.search(trecho[: casamento.start()]):
                    continue
                if len(digitos := _digitos(casamento.group())) >= 5:
                    numeros.add(digitos)
    return numeros


def _arquivos_versionados() -> list[str]:
    saida = subprocess.run(
        ["git", "ls-files", "src", "tests", "docs", "scripts", "README.md"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=True,
    )
    return [p for p in saida.stdout.split() if p.endswith((".py", ".md"))]


def test_nenhum_numero_de_citacao_do_gabarito_no_repositorio():
    proibidos = _numeros_do_gabarito()
    achados = []
    for caminho in _arquivos_versionados():
        texto = (RAIZ / caminho).read_text(encoding="utf-8")
        for casamento in _NUMERO.finditer(texto):
            if _digitos(casamento.group()) in proibidos:
                linha = texto.count("\n", 0, casamento.start()) + 1
                achados.append(f"{caminho}:{linha}: {casamento.group()}")
    assert not achados, "números do gabarito no repositório:\n" + "\n".join(achados)

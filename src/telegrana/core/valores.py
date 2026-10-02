"""Valores ditos do jeito da pessoa → centavos (PLANO 5.2: a IA extrai, o código calcula).

Exemplos: "45,90", "1.500", "15.90", "87,3", "R$ 1.800,00", "50 conto", "20 pila",
"1,2k", "2k", "52 mil", "mil e duzentos", "trinta e cinco e noventa" (R$ 35,90),
"1 milhão". Valor vago ("uns 30 e poucos") não vira número: o bot pergunta (D028).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

LIMITE_CENTAVOS = 100_000_000_000  # mesmo teto da tabela transactions

_VAGOS = ("e poucos", "e pouco", "e tantos", "e tanto", "e pouquinho", "e alguma coisa")
_RUIDO = re.compile(
    r"\b(r\$|rs|reais|real|conto|contos|pila|pilas|paus|pau|mangos|uns|umas|um total de|"
    r"cerca de|tipo|valor de|valor|deu|ficou|foi|mais ou menos|aproximadamente)\b"
)
_UNIDADES = {
    "zero": 0,
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    "onze": 11,
    "doze": 12,
    "treze": 13,
    "catorze": 14,
    "quatorze": 14,
    "quinze": 15,
    "dezesseis": 16,
    "dezessete": 17,
    "dezoito": 18,
    "dezenove": 19,
}
_DEZENAS = {
    "vinte": 20,
    "trinta": 30,
    "quarenta": 40,
    "cinquenta": 50,
    "sessenta": 60,
    "setenta": 70,
    "oitenta": 80,
    "noventa": 90,
}
_CENTENAS = {
    "cem": 100,
    "cento": 100,
    "duzentos": 200,
    "duzentas": 200,
    "trezentos": 300,
    "trezentas": 300,
    "quatrocentos": 400,
    "quatrocentas": 400,
    "quinhentos": 500,
    "quinhentas": 500,
    "seiscentos": 600,
    "seiscentas": 600,
    "setecentos": 700,
    "setecentas": 700,
    "oitocentos": 800,
    "oitocentas": 800,
    "novecentos": 900,
    "novecentas": 900,
}
_ORDEM = {"centena": 3, "dezena": 2, "unidade": 1}


@dataclass(frozen=True, slots=True)
class Valor:
    centavos: int | None
    vago: bool = False  # "e poucos": precisa perguntar


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def _numero_com_digitos(texto: str) -> float | None:
    """ "1.234,56", "1234,56", "45,9", "15.90", "1.500", "1,2" (com sufixo k/mil depois)."""
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d{1,2})?", texto):
        return float(texto.replace(".", "").replace(",", "."))
    if re.fullmatch(r"\d+,\d{1,2}", texto):
        return float(texto.replace(",", "."))
    if re.fullmatch(r"\d+\.\d{1,2}", texto):  # ponto decimal (15.90)
        return float(texto)
    if re.fullmatch(r"\d+", texto):
        return float(texto)
    if re.fullmatch(r"\d+,\d+", texto):  # 1,25 (antes de k/mil)
        return float(texto.replace(",", "."))
    return None


def _grupo_por_extenso(palavras: list[str]) -> tuple[int, list[str]] | None:
    """Lê "cento e trinta e cinco" (até 999) do início; devolve (valor, resto)."""
    total, ultima, consumidas = 0, 4, 0
    for i, palavra in enumerate(palavras):
        if palavra == "e":
            continue
        if palavra in _CENTENAS:
            ordem, valor = 3, _CENTENAS[palavra]
        elif palavra in _DEZENAS:
            ordem, valor = 2, _DEZENAS[palavra]
        elif palavra in _UNIDADES:
            ordem, valor = (2 if _UNIDADES[palavra] >= 10 else 1), _UNIDADES[palavra]
        else:
            break
        if ordem >= ultima:  # "trinta e cinco e noventa": a ordem voltou a subir
            break
        total += valor
        ultima = 1 if ordem == 2 and valor >= 10 and palavra in _UNIDADES else ordem
        consumidas = i + 1
    if consumidas == 0:
        return None
    return total, palavras[consumidas:]


def _por_extenso(texto: str) -> int | None:
    """Reais e centavos por extenso → centavos ("mil e duzentos", "trinta e cinco e noventa")."""
    palavras = [p for p in texto.split() if p]
    reais, achou = 0, False
    resto = palavras
    while resto:
        if resto[0] == "e":
            resto = resto[1:]
            continue
        if resto[0] in {"mil"}:
            reais = max(reais, 1) * 1000
            resto, achou = resto[1:], True
            continue
        if resto[0] in {"milhao", "milhoes"}:
            reais = max(reais, 1) * 1_000_000
            resto, achou = resto[1:], True
            continue
        grupo = _grupo_por_extenso(resto)
        if grupo is None:
            break
        valor, novo = grupo
        if novo and novo[0] in {"mil", "milhao", "milhoes"}:
            fator = 1000 if novo[0] == "mil" else 1_000_000
            reais += valor * fator
            resto, achou = novo[1:], True
            continue
        if achou and reais and valor < 1000 and reais % 1000 == 0 and _continua_reais(resto):
            reais += valor
            resto, achou = novo, True
            continue
        if not achou:
            reais, resto, achou = valor, novo, True
            continue
        # Um segundo grupo depois dos reais: centavos ("e noventa").
        if valor < 100 and not novo:
            return reais * 100 + valor
        return None
    if not achou or (resto and any(p not in {"e", "centavos"} for p in resto)):
        return None
    return reais * 100


def _continua_reais(palavras: list[str]) -> bool:
    """Depois de "mil", o próximo grupo ainda é de reais se vier "e" + centena/dezena."""
    return bool(palavras) and (palavras[0] == "e" or palavras[0] in _CENTENAS)


def interpreta(texto: str | None) -> Valor:
    if not texto:
        return Valor(None)
    bruto = _sem_acento(texto.lower()).strip()
    if any(v in bruto for v in _VAGOS):
        return Valor(None, vago=True)
    limpo = _RUIDO.sub(" ", bruto.replace("r$", " "))
    limpo = re.sub(r"[^\w\s.,]", " ", limpo)
    limpo = " ".join(limpo.split())

    # Dígitos com sufixo: "1,2k", "2k", "52 mil", "1,5 mil", "1 milhao".
    achado = re.fullmatch(r"(\d[\d.,]*)\s*(k|mil|milhao|milhoes)?", limpo) or re.search(
        r"(\d[\d.,]*)\s*(k|mil|milhao|milhoes)?", limpo
    )
    if achado:
        numero = _numero_com_digitos(achado.group(1).rstrip(".,"))
        if numero is None:
            return Valor(None)
        fator = {"k": 1000, "mil": 1000, "milhao": 1_000_000, "milhoes": 1_000_000}.get(
            achado.group(2) or "", 1
        )
        centavos = round(numero * fator * 100)
    else:
        centavos_ou_none = _por_extenso(limpo)
        if centavos_ou_none is None:
            return Valor(None)
        centavos = centavos_ou_none
    if not 0 < centavos < LIMITE_CENTAVOS:
        return Valor(None)
    return Valor(centavos)


def em_reais(centavos: int) -> str:
    """12345 → "R$ 123,45"; 150000 → "R$ 1.500,00"."""
    reais, cents = divmod(centavos, 100)
    return f"R$ {reais:,}".replace(",", ".") + f",{cents:02d}"

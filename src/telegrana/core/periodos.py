"""Períodos ditos do jeito da pessoa → datas (S6, PLANO 5.2: a IA copia, o código calcula).

"este mês", "mês passado", "últimos 3 meses", "últimos 15 dias", "esta semana", "semana
passada", "hoje", "ontem", "setembro", "setembro de 2025", "este ano", "2025", "ano
passado", "de 01/09 a 15/09", "desde 01/09". Sem período: o mês atual.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

from telegrana.core import datas
from telegrana.core.interpretacao import normaliza

MESES = (
    "janeiro",
    "fevereiro",
    "marco",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)
ABREV = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
_NUMEROS = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5,
            "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10, "doze": 12, "quinze": 15,
            "trinta": 30}  # fmt: skip
_DATA = r"(\d{1,2}/\d{1,2}(?:/\d{2,4})?)"


@dataclass(frozen=True, slots=True)
class Periodo:
    inicio: date
    fim: date
    rotulo: str


def _mes(ano: int, mes: int) -> tuple[date, date]:
    return date(ano, mes, 1), date(ano, mes, calendar.monthrange(ano, mes)[1])


def _soma_meses(ano: int, mes: int, k: int) -> tuple[int, int]:
    total = ano * 12 + mes - 1 + k
    return total // 12, total % 12 + 1


def nome_do_mes(ano: int, mes: int, curto: bool = False) -> str:
    nome = ABREV[mes - 1] if curto else MESES[mes - 1].replace("marco", "março")
    return f"{nome}/{ano}"


def _faixa(inicio: date, fim: date) -> str:
    if inicio.year == fim.year:
        return f"{inicio:%d/%m} a {fim:%d/%m/%Y}"
    return f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"


def mes_atual(hoje: date) -> Periodo:
    inicio, _ = _mes(hoje.year, hoje.month)
    return Periodo(inicio, hoje, nome_do_mes(hoje.year, hoje.month))


def mes_inteiro(ano: int, mes: int) -> Periodo:
    inicio, fim = _mes(ano, mes)
    return Periodo(inicio, fim, nome_do_mes(ano, mes))


def resolve(texto: str | None, hoje: date, *, futuro: bool = False) -> Periodo | None:
    """Período citado no texto; None se havia um período e não deu para entender.

    `futuro`: para compromissos ("este mês" vai até o fim do mês, não até hoje).
    """
    if not texto or not texto.strip():
        return mes_atual(hoje) if not futuro else mes_inteiro(hoje.year, hoje.month)
    t = normaliza(texto)
    t = re.sub(r"\b(ultimas|ultimos)\b", "ultimos", t)
    t = re.sub(r"\b(esse|nesse|neste|desse|deste)\b", "este", t)

    # Faixa explícita: "de 01/09 a 15/09", "entre 01/09 e 15/09", "desde 01/09"
    bruto = texto.lower()
    faixa = re.search(rf"{_DATA}\s*(?:a|ate|até|e)\s*{_DATA}", bruto)
    if faixa:
        ini = datas.resolve(faixa.group(1), hoje).dia
        fim = datas.resolve(faixa.group(2), hoje).dia
        if ini and fim and ini <= fim:
            return Periodo(ini, fim, _faixa(ini, fim))
    desde = re.search(rf"\b(?:desde|a partir de)\s*(?:o dia\s*)?{_DATA}", bruto)
    if desde:
        ini = datas.resolve(desde.group(1), hoje).dia
        if ini and ini <= hoje:
            return Periodo(ini, hoje, _faixa(ini, hoje))

    ultimos = re.search(r"\bultimos (\d{1,3}|\w+) (dias|semanas|meses)\b", t)
    if ultimos:
        n = int(ultimos.group(1)) if ultimos.group(1).isdigit() else _NUMEROS.get(ultimos.group(1))
        if not n or n > 400:
            return None
        if ultimos.group(2) == "dias":
            ini = hoje - timedelta(days=n - 1)
        elif ultimos.group(2) == "semanas":
            ini = hoje - timedelta(days=7 * n - 1)
        else:  # meses: o atual e os n-1 anteriores, inteiros
            ini = date(*_soma_meses(hoje.year, hoje.month, -(n - 1)), 1)
        return Periodo(ini, hoje, _faixa(ini, hoje))
    if re.search(r"\b(ultimo mes|mes passado)\b", t):
        return mes_inteiro(*_soma_meses(hoje.year, hoje.month, -1))
    if re.search(r"\bultima semana\b", t):
        ini = hoje - timedelta(days=6)
        return Periodo(ini, hoje, _faixa(ini, hoje))
    if re.search(r"\bsemana passada\b", t):
        ini = hoje - timedelta(days=hoje.weekday() + 7)
        return Periodo(
            ini,
            ini + timedelta(days=6),
            "semana passada (" + _faixa(ini, ini + timedelta(days=6)) + ")",
        )
    if re.search(r"\b(esta|essa|nesta|nessa|desta|dessa|este) semana\b", t):
        ini = hoje - timedelta(days=hoje.weekday())
        return Periodo(ini, hoje, "esta semana (" + _faixa(ini, hoje) + ")")
    if re.search(r"\bhoje\b", t):
        return Periodo(hoje, hoje, f"hoje, {hoje:%d/%m}")
    if re.search(r"\bontem\b", t):
        ontem = hoje - timedelta(days=1)
        return Periodo(ontem, ontem, f"ontem, {ontem:%d/%m}")
    if re.search(r"\bano passado\b", t):
        return Periodo(date(hoje.year - 1, 1, 1), date(hoje.year - 1, 12, 31), str(hoje.year - 1))
    if re.search(r"\beste ano\b|\bno ano\b", t):
        return Periodo(date(hoje.year, 1, 1), hoje, str(hoje.year))

    nomes = "|".join(MESES)
    mes = re.search(rf"\b({nomes})\b(?: (?:de )?(\d{{4}}))?", t)
    if mes:
        numero = MESES.index(mes.group(1)) + 1
        ano = int(mes.group(2)) if mes.group(2) else hoje.year
        if not mes.group(2) and numero > hoje.month:
            ano -= 1  # "dezembro" em outubro = o dezembro que passou
        if mes_atual(hoje).inicio == date(ano, numero, 1) and not futuro:
            return mes_atual(hoje)
        return mes_inteiro(ano, numero)
    if re.search(r"\b(este mes|mes atual|no mes)\b", t):
        return mes_atual(hoje) if not futuro else mes_inteiro(hoje.year, hoje.month)
    achado = re.search(r"\b(20\d{2})\b", t)
    if achado:
        a = int(achado.group(1))
        fim = hoje if a == hoje.year else date(a, 12, 31)
        return Periodo(date(a, 1, 1), fim, str(a))
    return None

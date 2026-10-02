"""Datas ditas do jeito da pessoa → data no fuso de São Paulo (PLANO 5.2).

"hoje", "hj", "agora", "ontem", "anteontem", "sexta passada", "sábado", "dia 5",
"vence dia 10", "05/09". Sem expressão de data = hoje. Expressão que o código não
entende = None (o bot pergunta; nunca chuta).
"""

from __future__ import annotations

import calendar
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

_DIAS_DA_SEMANA = {
    "segunda": 0,
    "terca": 1,
    "quarta": 2,
    "quinta": 3,
    "sexta": 4,
    "sabado": 5,
    "domingo": 6,
}
_HOJE = (
    "hoje",
    "hj",
    "agora",
    "agr",
    "agorinha",
    "esse mes",
    "este mes",
    "desse mes",
    "deste mes",
    "de manha",
    "cedo",
    "hoje cedo",
    "a tarde",
    "a noite",
)


@dataclass(frozen=True, slots=True)
class Data:
    dia: date | None
    futura: bool = False  # vencimento ainda por vir: o lançamento nasce "previsto"


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def _dia_valido(ano: int, mes: int, dia: int) -> date:
    """Dia 31 em mês curto vira o último dia do mês (PLANO 4.3)."""
    return date(ano, mes, min(dia, calendar.monthrange(ano, mes)[1]))


def _mes_anterior(hoje: date) -> tuple[int, int]:
    return (hoje.year - 1, 12) if hoje.month == 1 else (hoje.year, hoje.month - 1)


def _mes_seguinte(hoje: date) -> tuple[int, int]:
    return (hoje.year + 1, 1) if hoje.month == 12 else (hoje.year, hoje.month + 1)


def resolve(texto: str | None, hoje: date) -> Data:
    if not texto or not texto.strip():
        return Data(hoje)
    t = " ".join(_sem_acento(texto.lower()).replace("-feira", "").split())
    vencimento = "venc" in t or "vai vencer" in t

    if "anteontem" in t:
        return Data(hoje - timedelta(days=2))
    if "ontem" in t:
        return Data(hoje - timedelta(days=1))
    if "amanha" in t:
        return Data(hoje + timedelta(days=1), futura=True)

    explicita = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
    if explicita:
        dia, mes = int(explicita.group(1)), int(explicita.group(2))
        ano = int(explicita.group(3)) if explicita.group(3) else hoje.year
        ano = ano + 2000 if ano < 100 else ano
        if not (1 <= mes <= 12 and 1 <= dia <= 31):
            return Data(None)
        data = _dia_valido(ano, mes, dia)
        return Data(data, futura=data > hoje)

    dia_do_mes = re.search(r"\bdia (\d{1,2})\b", t)
    if dia_do_mes:
        dia = int(dia_do_mes.group(1))
        if not 1 <= dia <= 31:
            return Data(None)
        neste_mes = _dia_valido(hoje.year, hoje.month, dia)
        if vencimento:  # próximo vencimento: hoje ou depois
            if neste_mes >= hoje:
                return Data(neste_mes, futura=neste_mes > hoje)
            return Data(_dia_valido(*_mes_seguinte(hoje), dia), futura=True)
        if neste_mes <= hoje:  # já aconteceu: o mais recente
            return Data(neste_mes)
        return Data(_dia_valido(*_mes_anterior(hoje), dia))

    for nome, numero in _DIAS_DA_SEMANA.items():
        if re.search(rf"\b{nome}\b", t):
            atras = (hoje.weekday() - numero) % 7 or 7  # o mais recente, antes de hoje
            return Data(hoje - timedelta(days=atras))

    if any(expressao in t for expressao in _HOJE):
        return Data(hoje)
    return Data(None)


_EXPRESSAO = re.compile(
    r"\b(anteontem|ontem|amanha|(?:segunda|terca|quarta|quinta|sexta|sabado|domingo)"
    r"(?:-feira)?(?: passad[oa])?|dia \d{1,2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b"
)


def expressao_em(texto: str) -> str | None:
    """A expressão de data explícita numa frase livre (ou None). Com "vence", ela vem junto."""
    t = " ".join(_sem_acento(texto.lower()).split())
    achada = _EXPRESSAO.search(t)
    if achada is None:
        return None
    return f"vence {achada.group(1)}" if "venc" in t else achada.group(1)

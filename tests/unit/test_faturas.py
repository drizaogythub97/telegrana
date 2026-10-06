"""Regras puras da fatura (S5.2, D046): fechamento, rateio do parcial e avisos."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import date

import pytest

from telegrana.core import faturas
from telegrana.core.cartoes import Cartao

NUBANK = Cartao(uuid.uuid4(), uuid.uuid4(), "Nubank", 3, 10, None, True)
INTER = Cartao(uuid.uuid4(), uuid.uuid4(), "Inter", 25, 5, None, True)


@pytest.mark.parametrize(
    ("vencimento", "cartao", "esperado"),
    [
        (date(2026, 11, 10), NUBANK, date(2026, 11, 3)),
        (date(2026, 11, 5), INTER, date(2026, 10, 25)),  # vence no mês seguinte ao fechamento
        (date(2027, 1, 5), INTER, date(2026, 12, 25)),  # virada de ano
    ],
)
def test_fechamento(vencimento: date, cartao: Cartao, esperado: date) -> None:
    assert faturas.fechamento(vencimento, cartao.fecha, cartao.vence) == esperado


def test_seguinte() -> None:
    assert faturas.seguinte(date(2026, 12, 10), 10) == date(2027, 1, 10)
    assert faturas.seguinte(date(2027, 1, 31), 31) == date(2027, 2, 28)


@pytest.mark.parametrize(
    ("itens", "pago", "esperado"),
    [
        ([100000, 50000, 50000], 150000, [75000, 37500, 37500]),  # 75% de cada
        ([30000, 30000, 30000], 90000, [30000, 30000, 30000]),  # total
        ([30000, 30000, 30000], 100000, [30000, 30000, 30000]),  # acima: itens inteiros
        ([1001, 1001, 1001], 1000, [334, 333, 333]),  # centavos fecham a conta
        ([5000, 1], 2500, [2500, 0]),
    ],
)
def test_rateio(itens: list[int], pago: int, esperado: list[int]) -> None:
    partes = faturas.rateio(itens, pago)
    assert partes == esperado
    assert sum(partes) == min(pago, sum(itens))
    assert all(0 <= a <= b for a, b in zip(partes, itens, strict=True))


@pytest.mark.parametrize(
    ("hoje", "horario", "esperado"),
    [
        (date(2026, 11, 3), "morning", "closed"),
        (date(2026, 11, 9), "morning", "before"),
        (date(2026, 11, 10), "morning", "on_day"),
        (date(2026, 11, 11), "morning", "after"),
        (date(2026, 12, 9), "morning", "after"),
        (date(2026, 12, 10), "morning", None),  # chegou a fatura seguinte
        (date(2026, 11, 5), "morning", None),
        (date(2026, 11, 10), "evening", None),  # só de manhã (padrão)
    ],
)
def test_regra_dos_avisos(hoje: date, horario: str, esperado: str | None) -> None:
    assert faturas.regra(NUBANK, date(2026, 11, 10), hoje, horario) == esperado


def test_avisos_desligados() -> None:
    sem = replace(NUBANK, antes=False, no_dia=False, depois=False)
    assert faturas.regra(sem, date(2026, 11, 10), date(2026, 11, 9), "morning") is None
    assert faturas.regra(sem, date(2026, 11, 10), date(2026, 11, 12), "morning") is None
    # O aviso de fatura fechada continua (decisão do Adriano, D046).
    assert faturas.regra(sem, date(2026, 11, 10), date(2026, 11, 3), "morning") == "closed"

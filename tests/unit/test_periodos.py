"""Períodos ditos do jeito da pessoa → datas (S6, D047)."""

from __future__ import annotations

from datetime import date

import pytest

from telegrana.core import periodos

HOJE = date(2026, 10, 6)  # terça-feira


@pytest.mark.parametrize(
    ("texto", "inicio", "fim"),
    [
        (None, date(2026, 10, 1), HOJE),
        ("este mês", date(2026, 10, 1), HOJE),
        ("nesse mês", date(2026, 10, 1), HOJE),
        ("mês passado", date(2026, 9, 1), date(2026, 9, 30)),
        ("últimos 3 meses", date(2026, 8, 1), HOJE),
        ("nos últimos 15 dias", date(2026, 9, 22), HOJE),
        ("últimas 2 semanas", date(2026, 9, 23), HOJE),
        ("esta semana", date(2026, 10, 5), HOJE),
        ("semana passada", date(2026, 9, 28), date(2026, 10, 4)),
        ("hoje", HOJE, HOJE),
        ("ontem", date(2026, 10, 5), date(2026, 10, 5)),
        ("setembro", date(2026, 9, 1), date(2026, 9, 30)),
        ("outubro", date(2026, 10, 1), HOJE),  # o mês atual vai até hoje
        ("dezembro", date(2025, 12, 1), date(2025, 12, 31)),  # o dezembro que passou
        ("março de 2026", date(2026, 3, 1), date(2026, 3, 31)),
        ("este ano", date(2026, 1, 1), HOJE),
        ("ano passado", date(2025, 1, 1), date(2025, 12, 31)),
        ("2025", date(2025, 1, 1), date(2025, 12, 31)),
        ("de 01/09 a 15/09", date(2026, 9, 1), date(2026, 9, 15)),
        ("desde 20/09", date(2026, 9, 20), HOJE),
    ],
)
def test_resolve(texto: str | None, inicio: date, fim: date) -> None:
    p = periodos.resolve(texto, HOJE)
    assert p is not None, texto
    assert (p.inicio, p.fim) == (inicio, fim)


def test_compromissos_olham_o_mes_inteiro_e_texto_estranho() -> None:
    p = periodos.resolve("este mês", HOJE, futuro=True)
    assert p is not None
    assert p.fim == date(2026, 10, 31)
    assert periodos.resolve("na época das cruzadas", HOJE) is None
    assert periodos.resolve("últimos 900 dias", HOJE) is None


def test_rotulos() -> None:
    assert periodos.resolve("mês passado", HOJE).rotulo == "setembro/2026"  # type: ignore[union-attr]
    assert periodos.resolve("março de 2026", HOJE).rotulo == "março/2026"  # type: ignore[union-attr]
    assert periodos.nome_do_mes(2026, 10, curto=True) == "out/2026"

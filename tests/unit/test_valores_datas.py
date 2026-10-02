"""Normalização de valores e datas (a IA extrai o texto; o código calcula)."""

from __future__ import annotations

from datetime import date

import pytest

from telegrana.core import datas, valores

HOJE = date(2026, 10, 1)  # quinta-feira


@pytest.mark.parametrize(
    ("texto", "centavos"),
    [
        ("45,90", 4590),
        ("30", 3000),
        ("uns 50 conto", 5000),
        ("1.500", 150000),
        ("15.90", 1590),
        ("87,3", 8730),
        ("12,34", 1234),
        ("1.980", 198000),
        ("R$ 1.800,00", 180000),
        ("R$ 187,00", 18700),
        ("20 pila", 2000),
        ("45 reais", 4500),
        ("1,2k", 120000),
        ("2k", 200000),
        ("52 mil reais", 5200000),
        ("1,5 mil", 150000),
        ("mil e duzentos", 120000),
        ("trinta e cinco e noventa", 3590),
        ("cento e trinta e cinco", 13500),
        ("vinte e um mil", 2100000),
        ("1 milhao", 100000000),
        ("um milhão", 100000000),
        ("quinze", 1500),
        ("45,90 no pix", 4590),
        ("1.234,56", 123456),
    ],
)
def test_valores(texto: str, centavos: int) -> None:
    assert valores.interpreta(texto) == valores.Valor(centavos)


@pytest.mark.parametrize("texto", ["uns 30 e poucos", "50 e pouco", "vinte e tantos"])
def test_valor_vago_pede_pergunta(texto: str) -> None:
    assert valores.interpreta(texto) == valores.Valor(None, vago=True)


@pytest.mark.parametrize("texto", [None, "", "muito", "0", "0,00", "1000000000000"])
def test_sem_valor(texto: str | None) -> None:
    assert valores.interpreta(texto).centavos is None


@pytest.mark.parametrize(
    ("centavos", "texto"),
    [(4590, "R$ 45,90"), (150000, "R$ 1.500,00"), (5, "R$ 0,05"), (123456789, "R$ 1.234.567,89")],
)
def test_em_reais(centavos: int, texto: str) -> None:
    assert valores.em_reais(centavos) == texto


@pytest.mark.parametrize(
    ("texto", "esperado", "futura"),
    [
        (None, date(2026, 10, 1), False),
        ("hj cedo", date(2026, 10, 1), False),
        ("agr", date(2026, 10, 1), False),
        ("ontem", date(2026, 9, 30), False),
        ("anteontem", date(2026, 9, 29), False),
        ("sexta passada", date(2026, 9, 25), False),
        ("sábado", date(2026, 9, 26), False),
        ("quinta-feira", date(2026, 9, 24), False),  # hoje é quinta: a anterior
        ("dia 5", date(2026, 9, 5), False),
        ("dia 1", date(2026, 10, 1), False),
        ("vence dia 10", date(2026, 10, 10), True),
        ("vence dia 1", date(2026, 10, 1), False),
        ("05/09", date(2026, 9, 5), False),
        ("15/10/2026", date(2026, 10, 15), True),
        ("amanhã", date(2026, 10, 2), True),
    ],
)
def test_datas(texto: str | None, esperado: date, futura: bool) -> None:
    assert datas.resolve(texto, HOJE) == datas.Data(esperado, futura)


def test_dia_31_em_mes_curto() -> None:
    assert datas.resolve("dia 31", date(2026, 3, 15)) == datas.Data(date(2026, 2, 28))
    assert datas.resolve("vence dia 31", date(2026, 2, 10)) == datas.Data(date(2026, 2, 28), True)


@pytest.mark.parametrize("texto", ["semana que vem talvez", "dia 45", "32/13"])
def test_data_que_o_codigo_nao_entende(texto: str) -> None:
    assert datas.resolve(texto, HOJE).dia is None

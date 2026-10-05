"""Regras puras dos cartões (S5.1, PLANO 4.5): fatura de cada parcela, divisão e nomes."""

from __future__ import annotations

from datetime import date

import pytest

from telegrana.core import cartoes


@pytest.mark.parametrize(
    ("compra", "fecha", "vence", "esperado"),
    [
        (date(2026, 10, 2), 3, 10, date(2026, 10, 10)),  # antes do fechamento
        (date(2026, 10, 3), 3, 10, date(2026, 11, 10)),  # NO dia do fechamento: a seguinte
        (date(2026, 10, 31), 3, 10, date(2026, 11, 10)),
        (date(2026, 10, 10), 25, 5, date(2026, 11, 5)),  # vence no mês seguinte ao fechamento
        (date(2026, 10, 25), 25, 5, date(2026, 12, 5)),
        (date(2027, 2, 27), 31, 7, date(2027, 3, 7)),  # fecha 31 → 28/02
        (date(2027, 2, 28), 31, 7, date(2027, 4, 7)),
        (date(2026, 12, 20), 15, 31, date(2027, 1, 31)),  # virada de ano
        (date(2027, 1, 20), 15, 31, date(2027, 2, 28)),  # vence 31 em fevereiro
    ],
)
def test_fatura_da_compra(compra: date, fecha: int, vence: int, esperado: date) -> None:
    assert cartoes.fatura(compra, fecha, vence) == esperado


def test_doze_parcelas_atravessam_o_ano() -> None:
    datas = cartoes.faturas(date(2026, 12, 15), 3, 10, 12)
    assert datas[0] == date(2027, 1, 10)
    assert datas[-1] == date(2027, 12, 10)
    assert len(set(datas)) == 12


@pytest.mark.parametrize(
    ("total", "n", "esperado"),
    [
        (60000, 3, [20000, 20000, 20000]),
        (10000, 3, [3334, 3333, 3333]),  # centavos da divisão na 1ª parcela
        (1, 1, [1]),
        (100, 7, [16, 14, 14, 14, 14, 14, 14]),
    ],
)
def test_divide(total: int, n: int, esperado: list[int]) -> None:
    partes = cartoes.divide(total, n)
    assert partes == esperado
    assert sum(partes) == total


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("fecha 3, vence 10", (3, 10)),
        ("vence dia 10 e fecha dia 3", (3, 10)),
        ("Fecha dia três e vence dia dez.", (3, 10)),
        ("fechamento 25 vencimento 5", (25, 5)),
        ("3 e 10", (3, 10)),
        ("fecha 3", None),
        ("fecha 40, vence 10", None),
        ("oi", None),
    ],
)
def test_dois_dias(texto: str, esperado: tuple[int, int] | None) -> None:
    assert cartoes.dois_dias(texto) == esperado


@pytest.mark.parametrize(
    ("cartao", "citado", "bate"),
    [
        ("Nubank", "no nu", True),
        ("Nubank", "cartão do Nubank", True),
        ("Nubank", "nubank", True),
        ("Inter", "Itaú", False),
        ("C6", "c6", True),
        ("Banco do Brasil", "banco do brasil", True),
        ("Nubank", "cartão", False),
    ],
)
def test_nome_bate(cartao: str, citado: str, bate: bool) -> None:
    assert cartoes.nome_bate(cartao, citado) is bate


def test_nome_para_cartao_novo() -> None:
    assert cartoes.nome_para("nu") == "Nubank"
    assert cartoes.nome_para("cartão do inter") == "Inter"
    assert cartoes.nome_para("cartão de crédito") is None
    assert cartoes.nome_para(None) is None
    assert cartoes.nome_valido("123") is None
    assert cartoes.nome_valido("x" * 31) is None

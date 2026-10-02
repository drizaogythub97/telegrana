"""Atalho sem IA: só o que é claramente simples; o resto vai para a IA."""

from __future__ import annotations

from datetime import date

import pytest

from telegrana.core import atalho
from telegrana.core.interpretacao import CategoriaConta, interpreta

HOJE = date(2026, 10, 1)
CATEGORIAS = [
    CategoriaConta("mercado", "Mercado", "🛒", "expense"),
    CategoriaConta("alimentacao", "Alimentação fora", "🍽️", "expense"),
    CategoriaConta("transporte", "Transporte", "🚗", "expense"),
    CategoriaConta("combustivel", "Combustível", "⛽", "expense"),
    CategoriaConta("saude", "Saúde", "💊", "expense"),
    CategoriaConta("contas_casa", "Contas da casa", "💡", "expense"),
    CategoriaConta("salario", "Salário", "💼", "income"),
]


def proposta(texto: str):  # type: ignore[no-untyped-def]
    extracao = atalho.tenta(texto)
    assert extracao is not None, texto
    (p,) = interpreta(extracao, texto, CATEGORIAS, [], HOJE).propostas
    return p


@pytest.mark.parametrize(
    ("texto", "centavos", "categoria", "forma"),
    [
        ("supermercado 123,45 no pix", 12345, "mercado", "pix"),
        ("uber 22", 2200, "transporte", None),
        ("almoço 38,50 deb", 3850, "alimentacao", "debito"),
        ("farmácia 64 no cred", 6400, "saude", "credito"),
        ("gasolina 150 no nubank", 15000, "combustivel", "credito"),
        ("conta de luz 210,30 boleto", 21030, "contas_casa", "boleto"),
        ("R$ 1.250,00 aluguel", None, None, None),  # aluguel → moradia, que não está na lista
    ],
)
def test_frases_simples(
    texto: str, centavos: int | None, categoria: str | None, forma: str | None
) -> None:
    p = proposta(texto)
    if centavos is not None:
        assert (p.centavos, p.categoria, p.forma, p.tipo) == (centavos, categoria, forma, "expense")


def test_ganho() -> None:
    p = proposta("caiu o salário 4.500")
    assert (p.tipo, p.centavos, p.categoria) == ("income", 450000, "salario")


def test_parcelas_viram_credito() -> None:
    extracao = atalho.tenta("tênis 480 em 4x")
    assert extracao is not None
    item = extracao.lancamentos[0]
    assert (item.parcelas, item.forma_pagamento, item.valor_texto) == (4, "credito", "480")


def test_data_da_frase() -> None:
    assert proposta("gasolina 100 ontem").data == date(2026, 9, 30)


def test_dia_do_mes_nao_vira_valor() -> None:
    extracao = atalho.tenta("internet 99,90 dia 5")
    assert extracao is not None
    assert extracao.lancamentos[0].valor_texto == "99,90"
    assert extracao.lancamentos[0].pode_ser_fixo


def test_ambiguo_vai_pelo_atalho_e_pergunta() -> None:
    p = proposta("padaria 18")
    assert p.categoria is None
    assert "categoria" in p.pendencias


@pytest.mark.parametrize(
    "texto",
    [
        "40 de uber e 25 de almoço",  # dois valores
        "na verdade foi 54,90",  # correção
        "quanto gastei de mercado?",  # consulta
        "guardei 500 na poupança",  # transferência
        "mil e duzentos de mercado",  # valor por extenso
        "1,2k de iptu",  # valor com k
        "comprei um negócio 30",  # sem palavra-chave
        "mercado e farmácia 80",  # duas categorias
        "uma frase muito longa com muitas palavras sobre o mercado de hoje 30",
        "50 reais",  # sem o que foi
    ],
)
def test_vai_para_a_ia(texto: str) -> None:
    assert atalho.tenta(texto) is None

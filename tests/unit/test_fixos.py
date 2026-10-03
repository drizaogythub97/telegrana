"""Regras puras dos fixos: calendário, recorrência, fixo x estimado, nomes e lembretes."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from telegrana.core import fixos


@pytest.mark.parametrize(
    ("dia", "ano", "mes", "esperado"),
    [
        (10, 2026, 10, date(2026, 10, 10)),
        (31, 2026, 11, date(2026, 11, 30)),  # mês de 30 dias
        (31, 2027, 2, date(2027, 2, 28)),  # fevereiro comum
        (30, 2028, 2, date(2028, 2, 29)),  # fevereiro bissexto
        (29, 2027, 2, date(2027, 2, 28)),
        (31, 2026, 12, date(2026, 12, 31)),
    ],
)
def test_vencimento_em_meses_curtos(dia: int, ano: int, mes: int, esperado: date) -> None:
    assert fixos.vencimento(dia, ano, mes) == esperado


@pytest.mark.parametrize(
    ("frase", "repete", "dia", "so_cadastro"),
    [
        ("aluguel 1500 todo dia 10", True, 10, True),
        ("salário 3.500 todo mês dia 5", True, 5, True),
        ("netflix 55,90 mensal", True, None, True),
        ("internet 120 por mês", True, None, True),
        ("paguei a internet 120, é fixo", True, None, False),
        ("paguei o aluguel 1500, todo dia 10", True, 10, False),
        ("café 10 todo dia", False, None, True),  # diário, não mensal
        ("telefone fixo 80", False, None, True),
        ("gastei 1200 de mercado esse mês já", False, None, False),
        ("todo dia 45", True, None, True),  # dia inválido não vale
    ],
)
def test_recorrencia(frase: str, repete: bool, dia: int | None, so_cadastro: bool) -> None:
    assert fixos.recorrencia(frase) == (repete, dia)
    assert fixos.so_cadastro(frase) is so_cadastro


@pytest.mark.parametrize(
    ("codigo", "texto", "esperado"),
    [
        ("moradia", "aluguel 1500", "fixed"),
        ("assinaturas", "netflix 55,90", "fixed"),
        ("salario", "salário 3500", "fixed"),
        ("contas_casa", "luz 200", "estimated"),
        ("moradia", "condomínio uns 600", "estimated"),  # "uns": a pessoa disse que varia
        (None, "algo 10", "fixed"),
    ],
)
def test_valor_tipo(codigo: str | None, texto: str, esperado: str) -> None:
    assert fixos.valor_tipo(codigo, texto) == esperado


def test_nome_e_lembretes() -> None:
    assert fixos.nome_para("netflix", "Assinaturas") == "Netflix"
    assert fixos.nome_para(None, "Moradia") == "Moradia"
    base = fixos.Fixo(
        uuid.uuid4(), "expense", "Luz", None, 20000, "estimated", 10, None,
        True, True, True, "morning", True,
    )  # fmt: skip
    assert fixos.descreve_lembretes(base) == (
        "🔔 Lembrete na véspera, no dia e todo dia depois, às 09:00"
    )
    so_dia = fixos.Fixo(*[*base.__getstate__()][:8], False, True, False, "both", True)  # type: ignore[misc]
    assert fixos.descreve_lembretes(so_dia) == "🔔 Lembrete no dia, às 09:00 e às 20:00"
    nenhum = fixos.Fixo(*[*base.__getstate__()][:8], False, False, False, "evening", True)  # type: ignore[misc]
    assert fixos.descreve_lembretes(nenhum) == "🔕 Sem lembretes"

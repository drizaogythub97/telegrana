"""Motor dos lembretes (S4.2, PLANO 4.4): calendário, regras, horário e resolução do mês."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import date, datetime

import pytest

from telegrana.core import lembretes
from telegrana.core import textos as t
from telegrana.core.contexto import FUSO
from telegrana.core.fixos import Fixo

ALUGUEL = Fixo(
    uuid.uuid4(), "expense", "Aluguel", None, 150000, "fixed", 10, None,
    True, True, True, "morning", True, date(2026, 10, 1),
)  # fmt: skip


def regra(f: Fixo, hoje: date, horario: str = "morning", **kw: object) -> tuple[str, date] | None:
    lb = lembretes.devido(f, hoje, horario, **kw)  # type: ignore[arg-type]
    return (lb.regra, lb.vencimento) if lb else None


@pytest.mark.parametrize(
    ("hoje", "esperado"),
    [
        (date(2026, 10, 8), None),  # dois dias antes: nada
        (date(2026, 10, 9), ("before", date(2026, 10, 10))),
        (date(2026, 10, 10), ("on_day", date(2026, 10, 10))),
        (date(2026, 10, 11), ("after", date(2026, 10, 10))),
        (date(2026, 11, 8), ("after", date(2026, 10, 10))),  # ainda não pagou outubro
        (date(2026, 11, 9), ("before", date(2026, 11, 10))),  # a véspera de novembro manda
        (date(2026, 11, 10), ("on_day", date(2026, 11, 10))),  # outubro sai de cena
    ],
)
def test_vespera_no_dia_e_todo_dia_depois(hoje: date, esperado: tuple[str, date] | None) -> None:
    assert regra(ALUGUEL, hoje) == esperado


@pytest.mark.parametrize(
    ("dia", "hoje", "esperado"),
    [
        (31, date(2026, 11, 29), ("before", date(2026, 11, 30))),  # 31 em mês de 30 dias
        (31, date(2026, 11, 30), ("on_day", date(2026, 11, 30))),
        (31, date(2027, 2, 27), ("before", date(2027, 2, 28))),  # fevereiro
        (30, date(2028, 2, 29), ("on_day", date(2028, 2, 29))),  # bissexto
        (1, date(2026, 12, 31), ("before", date(2027, 1, 1))),  # virada de ano
        (1, date(2027, 1, 2), ("after", date(2027, 1, 1))),
        (31, date(2026, 12, 1), ("after", date(2026, 11, 30))),
    ],
)
def test_meses_curtos_e_viradas(dia: int, hoje: date, esperado: tuple[str, date] | None) -> None:
    assert regra(replace(ALUGUEL, dia=dia), hoje) == esperado


def test_regras_desligadas_horario_e_pausado() -> None:
    sem_vespera = replace(ALUGUEL, antes=False)
    assert regra(sem_vespera, date(2026, 10, 9)) is None
    sem_no_dia = replace(ALUGUEL, no_dia=False)
    # No dia do vencimento só cabe o "vence hoje": desligado, não cobra o mês passado.
    assert regra(sem_no_dia, date(2026, 10, 10)) is None
    assert regra(replace(ALUGUEL, depois=False), date(2026, 10, 11)) is None
    assert regra(ALUGUEL, date(2026, 10, 9), "evening") is None  # só de manhã
    noite = replace(ALUGUEL, horario="evening")
    assert regra(noite, date(2026, 10, 9), "evening") == ("before", date(2026, 10, 10))
    ambos = replace(ALUGUEL, horario="both")
    assert regra(ambos, date(2026, 10, 9), "morning") == regra(ambos, date(2026, 10, 9), "evening")
    assert regra(replace(ALUGUEL, ativo=False), date(2026, 10, 10)) is None


def test_cadastrado_depois_do_vencimento_nao_cobra_o_passado() -> None:
    novo = replace(ALUGUEL, desde=date(2026, 10, 20))
    assert regra(novo, date(2026, 10, 21)) is None
    assert regra(novo, date(2026, 11, 9)) == ("before", date(2026, 11, 10))
    no_dia = replace(ALUGUEL, desde=date(2026, 10, 10))  # cadastrado no próprio dia
    assert regra(no_dia, date(2026, 10, 11)) == ("after", date(2026, 10, 10))


def test_pago_ou_pulado_para_de_lembrar() -> None:
    assert regra(ALUGUEL, date(2026, 10, 12), resolvidos={date(2026, 10, 10)}) is None
    assert regra(ALUGUEL, date(2026, 10, 9), resolvidos={date(2026, 10, 10)}) is None
    # Lançamento ligado ao fixo no mesmo mês, ou até 7 dias antes, conta como pago.
    assert regra(ALUGUEL, date(2026, 10, 12), pagamentos=[date(2026, 10, 2)]) is None
    assert regra(ALUGUEL, date(2026, 10, 12), pagamentos=[date(2026, 9, 30)]) == (
        "after",
        date(2026, 10, 10),
    )
    dia1 = replace(ALUGUEL, dia=1)
    assert regra(dia1, date(2026, 11, 1), pagamentos=[date(2026, 10, 29)]) is None


def test_horario_da_rotina() -> None:
    assert lembretes.horario_de(datetime(2026, 10, 9, 9, 0, 3, tzinfo=FUSO)) == "morning"
    assert lembretes.horario_de(datetime(2026, 10, 9, 20, 1, tzinfo=FUSO)) == "evening"


def test_mensagem_do_lembrete() -> None:
    luz = replace(ALUGUEL, nome="Luz", valor_tipo="estimated", centavos=18000)
    s = lembretes.saida(lembretes.Lembrete(luz, date(2026, 10, 10), "on_day"), "💡", "123")
    assert s.texto == "💡 **Luz** vence hoje\nValor estimado: R$ 180,00"
    assert s.destino == "123"
    assert [b.rotulo for linha in s.botoes for b in linha] == [
        "✅ Paguei",
        "✏️ Outro valor",
        "⏭️ Pular este mês",
    ]
    assert all(len((b.acao or "").encode()) <= 64 for linha in s.botoes for b in linha)
    salario = replace(ALUGUEL, tipo="income", nome="Salário")
    s = lembretes.saida(lembretes.Lembrete(salario, date(2026, 10, 5), "after"), "💰", "1")
    assert s.texto.startswith(
        t.LEMBRETE[("income", "after")].format(nome="Salário", data="05/10", emoji="")
    )
    assert s.botoes[0][0].rotulo == "✅ Recebi"

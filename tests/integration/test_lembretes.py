"""Lembretes dos fixos (S4.2, PLANO 4.4) contra Postgres real: rotina, botões e isolamento."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

import pytest

from telegrana.core import lembretes
from telegrana.core import textos as t
from telegrana.core.contexto import FUSO
from telegrana.core.mensagens import Resultado, Saida
from telegrana.infra import db
from tests.conftest import Banco
from tests.integration.test_cadastro import CTX, Bot, conn
from tests.integration.test_fixos import acao
from tests.integration.test_lancamentos import IAFalsa, conta, lancamentos_de

pytestmark = pytest.mark.integration
__all__ = ["conn"]


@pytest.fixture
def bot(conn: db.Connection) -> Bot:
    return Bot(conn, replace(CTX, extrator=IAFalsa()))


def momento(dia: str, hora: int = 9) -> datetime:
    return datetime.fromisoformat(f"{dia}T{hora:02d}:00").replace(tzinfo=FUSO)


def rotina(conn: db.Connection, de: str, dia: str, hora: int = 9) -> list[Saida]:
    saidas, falhas = lembretes.da_rotina(conn, "telegram", momento(dia, hora))
    assert falhas == 0
    return [s for s in saidas if s.destino == de]  # o banco é compartilhado com outros testes


def fixos_cadastrados_em_setembro(banco: Banco, de: str) -> None:
    with db.connect(banco.migrator) as m, m.transaction():
        m.execute(
            "update telegrana.fixed_items set created_at = '2026-09-20 12:00-03'"
            " where user_id = (select user_id from telegrana.user_channels where external_id = %s)",
            (de,),
        )


def toca(bot: Bot, de: str, s: Saida, prefixo: str) -> Resultado:
    return bot(de, acao=acao(Resultado(saidas=[s]), prefixo))


@pytest.fixture
def hoje(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    """Os botões validam o vencimento contra "hoje": fixa o relógio no meio de outubro."""

    def em(dia: str) -> None:
        monkeypatch.setattr(lembretes, "agora", lambda: momento(dia, 10))

    em("2026-10-10")
    return em


def test_vespera_no_dia_paguei_e_nao_repete(
    bot: Bot, conn: db.Connection, banco: Banco, hoje: Callable[[str], None]
) -> None:
    de = conta(bot)
    bot(de, texto="aluguel 1500 todo dia 10")
    bot(de, texto="luz 200 todo dia 15")
    fixos_cadastrados_em_setembro(banco, de)

    [vespera] = rotina(conn, de, "2026-10-09")
    assert vespera.texto == "🏠 **Aluguel** vence amanhã (10/10)\nValor: R$ 1.500,00"
    assert rotina(conn, de, "2026-10-09") == []  # rotina repetida: nada de novo
    assert rotina(conn, de, "2026-10-09", 20) == []  # só de manhã (padrão)

    [no_dia] = rotina(conn, de, "2026-10-10")
    assert no_dia.texto.startswith("🏠 **Aluguel** vence hoje")
    r = toca(bot, de, no_dia, "lm:pg:")
    assert r.saidas[0].texto.startswith(t.REGISTRADO["expense"])
    assert "📝 Aluguel" in r.saidas[0].texto
    assert r.saidas[0].ref  # o recibo continua corrigível respondendo a ele
    # Toque duplo (ou o botão do lembrete da véspera): não lança de novo.
    assert toca(bot, de, vespera, "lm:pg:").saidas[0].texto == t.LEMBRETE_JA_RESOLVIDO.format(
        nome="Aluguel", mes="outubro"
    )
    assert [x[:3] + x[6:7] for x in lancamentos_de(banco, de)] == [
        ("expense", 150000, "moradia", True)
    ]
    assert rotina(conn, de, "2026-10-11") == []  # pago: para de lembrar

    # Luz: venceu e ninguém pagou → todo dia depois, até o "Outro valor".
    rotina(conn, de, "2026-10-14")
    rotina(conn, de, "2026-10-15")
    [atrasada] = rotina(conn, de, "2026-10-16")
    assert atrasada.texto == (
        "⏰ **Luz** venceu em 15/10 e ainda não está marcado como pago\nValor estimado: R$ 200,00"
    )
    hoje("2026-10-16")
    pergunta = toca(bot, de, atrasada, "lm:ov:").saidas[0]
    assert pergunta.pergunta == "lm_valor"
    contexto = pergunta.texto.splitlines()[1]
    assert contexto == "🔔 Luz · 15/10/2026"
    r = bot(de, pergunta="lm_valor", contexto=contexto, texto="não sei")
    assert r.saidas[0].pergunta == "lm_valor"  # pergunta de novo
    r = bot(de, pergunta="lm_valor", contexto=contexto, texto="187,40")
    assert "R$ 187,40" in r.saidas[0].texto
    assert lancamentos_de(banco, de)[1][:3] == ("expense", 18740, "contas_casa")
    assert rotina(conn, de, "2026-10-17") == []


def test_pular_este_mes_e_volta_no_seguinte(
    bot: Bot, conn: db.Connection, banco: Banco, hoje: Callable[[str], None]
) -> None:
    de = conta(bot)
    bot(de, texto="netflix 55,90 todo dia 10")
    fixos_cadastrados_em_setembro(banco, de)
    [lembrete] = rotina(conn, de, "2026-10-10")
    r = toca(bot, de, lembrete, "lm:pl:")
    assert r.saidas[0].texto == t.LEMBRETE_PULADO.format(nome="Netflix", mes="outubro")
    assert toca(bot, de, lembrete, "lm:ov:").saidas[0].texto.startswith("👍 Netflix de outubro")
    assert rotina(conn, de, "2026-10-11") == []
    assert lancamentos_de(banco, de) == []  # pular não lança nada
    assert len(rotina(conn, de, "2026-11-09")) == 1  # novembro: lembra de novo


def test_pagamento_ja_lancado_e_ganho(bot: Bot, conn: db.Connection, banco: Banco) -> None:
    de = conta(bot)
    bot(de, texto="paguei a internet 120 todo dia 5")  # lança E cadastra o fixo
    bot(de, texto="salário 3500 todo dia 5")
    fixos_cadastrados_em_setembro(banco, de)
    with db.connect(banco.migrator) as m, m.transaction():
        m.execute(
            "update telegrana.transactions set cash_on = '2026-10-05', occurred_on = '2026-10-05'"
            " where user_id = (select user_id from telegrana.user_channels where external_id = %s)",
            (de,),
        )
    [salario] = rotina(conn, de, "2026-10-05")  # a internet de outubro já está paga
    assert salario.texto.startswith("💼 **Salário** cai hoje")
    assert salario.botoes[0][0].rotulo == "✅ Recebi"


def test_pausado_sem_lembretes_e_outra_conta(
    bot: Bot, conn: db.Connection, banco: Banco, hoje: Callable[[str], None]
) -> None:
    a, b = conta(bot), conta(bot)
    r = bot(a, texto="aluguel 1500 todo dia 10")
    fixos_cadastrados_em_setembro(banco, a)
    [lembrete] = rotina(conn, a, "2026-10-10")
    # O botão do lembrete de A, tocado por B: o fixo não existe para B (RLS).
    assert toca(bot, b, lembrete, "lm:pg:").saidas[0].texto == t.FIXO_SUMIU
    assert lancamentos_de(banco, b) == []
    # Botão forjado com data fora da janela.
    forjado = acao(Resultado(saidas=[lembrete]), "lm:pg:")[:-8] + "20200110"
    assert bot(a, acao=forjado).saidas[0].texto == t.LEMBRETE_INVALIDO
    # Pausado: nada.
    cartao = bot(a, acao=acao(r, "fi:ed:"))
    bot(a, acao=acao(cartao, "fi:pa:"))
    assert rotina(conn, a, "2026-10-11") == []

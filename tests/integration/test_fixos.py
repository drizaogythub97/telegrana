"""Fixos (S4.1, D043) contra Postgres real: cadastro, /fixos, edição e isolamento."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from telegrana.core import seguranca as seg
from telegrana.core import textos as t
from telegrana.core.mensagens import Resultado
from telegrana.infra import db
from tests.conftest import Banco
from tests.integration.test_cadastro import CTX, Bot, acoes, conn
from tests.integration.test_lancamentos import IAFalsa, conta, lancamentos_de

pytestmark = pytest.mark.integration
__all__ = ["conn"]


@pytest.fixture
def bot(conn: db.Connection) -> Bot:
    return Bot(conn, replace(CTX, extrator=IAFalsa()))


def fixos_de(banco: Banco, de: str) -> list[tuple[Any, ...]]:
    with db.connect(banco.migrator) as m, m.transaction():
        return m.execute(
            "select f.name, f.kind, f.amount_cents, f.amount_kind, f.day_of_month,"
            " coalesce(c.code, c.name), f.remind_before, f.remind_on_day, f.remind_after,"
            " f.remind_slot, f.active"
            " from telegrana.fixed_items f"
            " join telegrana.user_channels u on u.user_id = f.user_id"
            " left join telegrana.categories c on c.id = f.category_id"
            " where u.external_id = %s order by f.created_at",
            (de,),
        ).fetchall()


def acao(r: Resultado, prefixo: str) -> str:
    return next(a for a in acoes(r) if a.startswith(prefixo))


def test_frase_com_recorrencia_cadastra_o_fixo_sem_lancar(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, texto="aluguel 1500 todo dia 10")
    assert r.saidas[0].texto.startswith(t.FIXO_CRIADO)
    assert "🏠 **Aluguel** · R$ 1.500,00 · dia 10" in r.saidas[0].texto
    assert "🔔 Lembrete na véspera, no dia e todo dia depois, às 09:00" in r.saidas[0].texto
    assert lancamentos_de(banco, de) == []  # o fixo gera lembrete, não lançamento
    bot(de, texto="luz 200 todo dia 15")
    assert fixos_de(banco, de) == [
        ("Aluguel", "expense", 150000, "fixed", 10, "moradia", True, True, True, "morning", True),
        (
            "Luz",
            "expense",
            20000,
            "estimated",
            15,
            "contas_casa",
            True,
            True,
            True,
            "morning",
            True,
        ),
    ]
    lista = bot(de, comando="fixos")
    assert lista.saidas[0].texto.startswith(t.FIXOS_TITULO)
    assert "💡 **Luz** · R$ 200,00 (estimado) · dia 15" in lista.saidas[0].texto
    # Nome repetido não duplica.
    assert bot(de, texto="aluguel 1600 todo dia 10").saidas[0].texto.startswith(t.FIXO_JA_EXISTE)
    assert len(fixos_de(banco, de)) == 2


def test_sim_todo_mes_e_pagamento_com_recorrencia_criam_o_fixo(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, texto="netflix 55,90")
    r = bot(de, acao=acao(r, "fx:s:"))
    assert r.saidas[0].texto.startswith(t.FIXO_CRIADO)
    r = bot(de, texto="paguei a internet 120 todo dia 5")
    assert r.saidas[0].texto.startswith(t.REGISTRADO["expense"])  # o pagamento entra...
    assert r.saidas[1].texto.startswith(t.FIXO_CRIADO)  # ...e o fixo também
    assert t.PERGUNTA_FIXO not in r.saidas[0].texto  # não pergunta "é fixo?" de novo
    nomes = [(f[0], f[2], f[3], f[4]) for f in fixos_de(banco, de)]
    hoje = lancamentos_de(
        banco, de
    )  # (kind, centavos, categoria, forma, status, apagado, recorrente, parcelas)
    assert nomes[0][:3] == ("Netflix", 5590, "fixed")
    assert nomes[1] == ("Internet", 12000, "estimated", 5)
    assert [x[6] for x in hoje] == [True, True]  # os dois lançamentos ficaram ligados
    with db.connect(banco.migrator) as m, m.transaction():
        ligados = m.execute(
            "select count(*) from telegrana.transactions where fixed_item_id is not null"
            " and user_id = (select user_id from telegrana.user_channels where external_id = %s)",
            (de,),
        ).fetchone()
    assert ligados == (2,)


def test_editar_valor_dia_tipo_lembretes_pausar_e_apagar(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, texto="aluguel 1500 todo dia 10")
    ajustar = acao(r, "fi:ed:")
    cartao = bot(de, acao=ajustar)
    assert [b.rotulo for linha in cartao.saidas[0].botoes for b in linha][:2] == [
        "💰 Valor",
        "📅 Dia",
    ]

    pergunta = bot(de, acao=acao(cartao, "fi:va:")).saidas[0]
    assert pergunta.pergunta == "fi_valor"
    contexto = pergunta.texto.splitlines()[1]
    assert contexto == "🔁 Aluguel"
    r = bot(de, pergunta="fi_valor", contexto=contexto, texto="mil e seiscentos")
    assert r.saidas[0].texto.startswith(t.FIXO_ATUALIZADO)
    assert bot(de, pergunta="fi_dia", contexto=contexto, texto="35").saidas[0].pergunta == "fi_dia"
    bot(de, pergunta="fi_dia", contexto=contexto, texto="dia 31")

    bot(de, acao=acao(cartao, "fi:vt:"))  # fixo → estimado
    lembretes = bot(de, acao=acao(cartao, "fi:lb:"))
    lembretes = bot(de, acao=acao(lembretes, "fi:tb:"))  # tira a véspera
    lembretes = bot(de, acao=acao(lembretes, "fi:hb:"))  # manhã e noite
    assert "🔔 Lembrete no dia e todo dia depois, às 09:00 e às 20:00" in lembretes.saidas[0].texto
    bot(de, acao=acao(cartao, "fi:pa:"))
    assert fixos_de(banco, de) == [
        ("Aluguel", "expense", 160000, "estimated", 31, "moradia", False, True, True, "both", False)
    ]
    confirma = bot(de, acao=acao(cartao, "fi:ap:"))
    assert bot(de, acao=acao(confirma, "fi:ok:")).saidas[0].texto == t.FIXO_APAGADO
    assert fixos_de(banco, de) == []


def test_desfazer_mantem_o_lancamento(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, texto="paguei a internet 120 todo dia 5")
    r = bot(de, acao=acao(r, "fi:un:"))
    assert r.saidas[0].texto == t.FIXO_DESFEITO
    assert fixos_de(banco, de) == []
    assert len(lancamentos_de(banco, de)) == 1


def test_fixo_de_outra_conta_nao_e_visto_nem_alterado(bot: Bot, banco: Banco) -> None:
    a, b = conta(bot), conta(bot)
    r = bot(a, texto="aluguel 1500 todo dia 10")
    fixo_a = acao(r, "fi:ed:").split(":")[2]
    for prefixo in ("ed", "pa", "ok", "tb", "hb", "vt"):
        r = bot(b, acao=f"fi:{prefixo}:{fixo_a}")
        assert r.saidas[0].texto == t.FIXO_SUMIU, prefixo
    # Pergunta forjada com o nome do fixo de A: por RLS, B não o encontra.
    r = bot(b, pergunta="fi_valor", contexto="🔁 Aluguel", texto="1")
    assert r.saidas[0].texto == t.FIXO_SUMIU
    assert bot(b, comando="fixos").saidas[0].texto == t.FIXOS_VAZIO
    assert fixos_de(banco, a)[0][2] == 150000
    assert seg.longo(fixo_a) is not None

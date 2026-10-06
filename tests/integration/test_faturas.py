"""Faturas de cartão (S5.2, D046) contra Postgres real: pagamento, avisos e estorno."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any

import pytest

from telegrana.core import cartoes, faturas, lembretes
from telegrana.core import textos as t
from telegrana.core.contexto import FUSO, agora
from telegrana.core.mensagens import Resultado
from telegrana.infra import db
from tests.conftest import Banco
from tests.integration.test_cadastro import CTX, Bot, acoes, conn
from tests.integration.test_cartoes import com_nubank
from tests.integration.test_lancamentos import IAFalsa, conta

pytestmark = pytest.mark.integration
__all__ = ["conn"]


@pytest.fixture
def bot(conn: db.Connection) -> Bot:
    return Bot(conn, replace(CTX, extrator=IAFalsa()))


def linhas_de(banco: Banco, de: str) -> list[tuple[Any, ...]]:
    """(centavos, status, caixa, fatura, categoria, descrição) de cada linha não apagada."""
    with db.connect(banco.migrator) as m, m.transaction():
        return m.execute(
            "select x.amount_cents, x.status, x.cash_on, x.invoice_on,"
            " coalesce(c.code, c.name), x.description"
            " from telegrana.transactions x"
            " join telegrana.user_channels u on u.user_id = x.user_id"
            " left join telegrana.categories c on c.id = x.category_id"
            " where u.external_id = %s and x.deleted_at is null order by x.id",
            (de,),
        ).fetchall()


def acao(r: Resultado, prefixo: str) -> str:
    return next(a for a in acoes(r) if a.startswith(prefixo))


def primeira_fatura() -> date:
    return cartoes.fatura(agora().date(), 3, 10)


def test_pagar_a_fatura_toda(bot: Bot, banco: Banco) -> None:
    de = com_nubank(bot)  # tênis 600 em 3x
    bot(de, texto="mercado 100 no crédito")
    r = bot(de, texto="paguei a fatura do nubank")
    assert r.rotulo == "fatura.pagar"
    tela = r.saidas[0].texto
    assert f"Fatura do Nubank** · vence {primeira_fatura():%d/%m}" in tela
    assert "Total: **R$ 300,00**" in tela
    assert "(1/3)" in tela
    r = bot(de, acao=acao(r, "fa:pg:"))
    assert r.saidas[0].texto == t.FATURA_PAGA.format(nome="Nubank", pago="R$ 300,00", n=2)
    hoje = agora().date()
    linhas = linhas_de(banco, de)
    assert [x[:3] for x in linhas if x[1] == "done"] == [
        (20000, "done", hoje),
        (10000, "done", hoje),
    ]
    assert len([x for x in linhas if x[1] == "planned"]) == 2  # parcelas 2 e 3 continuam
    r = bot(de, acao=acao(bot(de, texto="paguei a fatura do nubank"), "fa:pg:"))
    assert r.saidas[0].texto.startswith("✅") or "já está paga" in r.saidas[0].texto


def test_parcial_proporcional_e_saldo_anterior(bot: Bot, banco: Banco) -> None:
    de = com_nubank(bot)  # 200 na 1ª fatura
    bot(de, texto="mercado 200 no crédito")  # +200
    r = bot(de, texto="paguei a fatura")  # só um cartão: ele
    pergunta = bot(de, acao=acao(r, "fa:ov:")).saidas[0]
    assert pergunta.pergunta == "fa_valor"
    contexto = pergunta.texto.splitlines()[1]
    assert contexto == f"🧾 Nubank · {primeira_fatura():%d/%m/%Y}"
    r = bot(de, pergunta="fa_valor", contexto=contexto, texto="300")
    seguinte = faturas.seguinte(primeira_fatura(), 10)
    assert r.saidas[0].texto == t.FATURA_PAGA_PARCIAL.format(
        nome="Nubank", pago="R$ 300,00", resto="R$ 100,00", data=f"{seguinte:%d/%m}"
    )
    linhas = linhas_de(banco, de)
    assert sorted(x[0] for x in linhas if x[1] == "done") == [15000, 15000]
    saldos = [x for x in linhas if (x[5] or "").startswith("Saldo anterior")]
    assert [(x[0], x[3]) for x in saldos] == [(5000, seguinte), (5000, seguinte)]
    assert {x[4] for x in saldos} == {"vestuario", "mercado"}  # cada um na sua categoria


def test_pagou_a_mais_vira_encargos(bot: Bot, banco: Banco) -> None:
    de = com_nubank(bot)
    r = bot(de, texto="paguei a fatura do nubank 250")
    assert [b.rotulo for linha in r.saidas[0].botoes for b in linha][:2] == [
        "✅ Paguei R$ 250,00",
        "✅ Paguei R$ 200,00",
    ]
    r = bot(de, acao=acao(r, "fa:pv:"))
    assert "Os R$ 50,00 a mais entraram como 💸 Encargos e juros." in r.saidas[0].texto
    encargos = [x for x in linhas_de(banco, de) if x[4] == "encargos"]
    assert [(x[0], x[1]) for x in encargos] == [(5000, "done")]


def test_avisos_da_rotina(bot: Bot, conn: db.Connection, banco: Banco) -> None:
    de = com_nubank(bot)
    vencimento = primeira_fatura()
    fecha = faturas.fechamento(vencimento, 3, 10)

    def rotina(dia: date) -> list[str]:
        momento = datetime(dia.year, dia.month, dia.day, 9, tzinfo=FUSO)
        saidas, falhas = lembretes.da_rotina(conn, "telegram", momento)
        assert falhas == 0
        return [s.texto.splitlines()[0] for s in saidas if s.destino == de]

    if fecha >= agora().date():
        assert rotina(fecha) == [t.FATURA_FECHOU.format(nome="Nubank", data=f"{vencimento:%d/%m}")]
    assert rotina(vencimento - timedelta(days=1)) == [
        t.FATURA_VENCE_AMANHA.format(nome="Nubank", data=f"{vencimento:%d/%m}")
    ]
    assert rotina(vencimento - timedelta(days=1)) == []  # rotina repetida
    r = bot(de, texto="paguei a fatura do nubank")
    bot(de, acao=acao(r, "fa:pg:"))
    assert rotina(vencimento) == []  # paga: para de avisar


def test_estorno_abate_da_compra(bot: Bot, banco: Banco) -> None:
    de = com_nubank(bot)  # tênis 600 em 3x
    r = bot(de, texto="estorno de 600 no nubank")  # bate com uma compra só
    assert r.saidas[0].texto == t.ESTORNO_FEITO.format(valor="R$ 600,00", descricao="tênis")
    assert [x for x in linhas_de(banco, de) if x[1] == "planned"] == []
    bot(de, texto="mercado 80 no crédito")
    bot(de, texto="farmácia 120 no crédito")
    r = bot(de, texto="estorno de 50")  # nenhuma compra de 50: pergunta qual
    assert r.saidas[0].texto == t.ESTORNO_QUAL.format(valor="R$ 50,00")
    escolha = next(a for a in acoes(r) if a.startswith("fa:es:"))
    r = bot(de, acao=escolha)
    assert r.saidas[0].texto.startswith("↩️ Estorno de R$ 50,00")
    assert sorted(x[0] for x in linhas_de(banco, de) if x[1] == "planned") in (
        [3000, 12000],
        [8000, 7000],
    )


def test_fatura_de_outra_conta_e_conta_de_luz(bot: Bot, banco: Banco) -> None:
    a, b = com_nubank(bot), conta(bot)
    r = bot(a, texto="paguei a fatura do nubank")
    assert bot(b, acao=acao(r, "fa:pg:")).saidas[0].texto == t.CARTAO_SUMIU  # RLS
    assert all(x[1] == "planned" for x in linhas_de(banco, a))
    r = bot(a, texto="estorno de 50")
    assert bot(b, acao=acao(r, "fa:es:")).saidas[0].texto == t.RASCUNHO_SUMIU
    # "fatura da luz" é conta de consumo, não fatura de cartão.
    assert not bot(a, texto="paguei a fatura da luz").rotulo.startswith("fatura")

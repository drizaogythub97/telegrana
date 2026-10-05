"""Cartões e compras parceladas (S5.1, D045) contra Postgres real."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Any

import pytest

from telegrana.core import cartoes
from telegrana.core import lancamentos_repo as lrepo
from telegrana.core import textos as t
from telegrana.core.contexto import agora
from telegrana.core.mensagens import Resultado
from telegrana.infra import db
from tests.conftest import Banco
from tests.integration.test_cadastro import CTX, Bot, acoes, conn
from tests.integration.test_lancamentos import IAFalsa, conta, ref_do_recibo

pytestmark = pytest.mark.integration
__all__ = ["conn"]


@pytest.fixture
def bot(conn: db.Connection) -> Bot:
    return Bot(conn, replace(CTX, extrator=IAFalsa()))


def parcelas_de(banco: Banco, de: str) -> list[tuple[Any, ...]]:
    """(nº, centavos, status, fatura, cartão, categoria, apagada) de cada linha da pessoa."""
    with db.connect(banco.migrator) as m, m.transaction():
        return m.execute(
            "select x.installment_no, x.amount_cents, x.status, x.invoice_on, p.name,"
            " coalesce(c.code, c.name), x.deleted_at is not null"
            " from telegrana.transactions x"
            " join telegrana.user_channels u on u.user_id = x.user_id"
            " left join telegrana.payment_methods p on p.id = x.payment_method_id"
            " left join telegrana.categories c on c.id = x.category_id"
            " where u.external_id = %s order by x.id",
            (de,),
        ).fetchall()


def acao(r: Resultado, prefixo: str) -> str:
    return next(a for a in acoes(r) if a.startswith(prefixo))


def com_nubank(bot: Bot) -> str:
    de = conta(bot)
    r = bot(de, texto="tênis 600 em 3x no nubank")
    pergunta = r.saidas[0]
    assert pergunta.pergunta == "lc_cartao_dias"
    assert pergunta.texto.splitlines()[1] == "💳 Nubank"
    r = bot(de, pergunta="lc_cartao_dias", contexto="💳 Nubank", texto="fecha 3, vence 10")
    assert r.saidas[0].texto.startswith(t.COMPRA_CREDITO)
    return de


def test_primeira_compra_cadastra_o_cartao_e_grava_as_parcelas(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    bot(de, texto="tênis 600 em 3x no nubank")
    r = bot(de, pergunta="lc_cartao_dias", contexto="💳 Nubank", texto="fecha 3, vence 10")
    recibo = r.saidas[0].texto
    hoje = agora().date()
    datas = cartoes.faturas(hoje, 3, 10, 3)
    assert "R$ 600,00" in recibo
    assert "💳 Nubank · 3x de R$ 200,00" in recibo
    assert f"🧾 1ª parcela na fatura que vence {datas[0]:%d/%m}" in recibo
    assert parcelas_de(banco, de) == [
        (k + 1, 20000, "planned", datas[k], "Nubank", "vestuario", False) for k in range(3)
    ]


def test_unico_cartao_e_usado_e_dois_cartoes_perguntam(bot: Bot, banco: Banco) -> None:
    de = com_nubank(bot)
    r = bot(de, texto="mercado 100 no crédito")  # só um cartão: vai nele
    assert "💳 Nubank" in r.saidas[0].texto
    assert "🧾 Entra na fatura" in r.saidas[0].texto
    # Segundo cartão pelo /cartoes.
    r = bot(de, acao="ct:nv")
    assert r.saidas[0].pergunta == "ct_nome"
    r = bot(de, pergunta="ct_nome", texto="inter")
    assert r.saidas[0].texto.splitlines()[1] == "💳 Inter"
    r = bot(de, pergunta="ct_dias", contexto="💳 Inter", texto="fecha 25 vence 5")
    assert r.saidas[0].texto.startswith(t.CARTAO_CRIADO)
    assert "fecha dia 25 · vence dia 5" in r.saidas[0].texto
    # Com dois, "no crédito" pergunta qual.
    r = bot(de, texto="farmácia 80 no crédito")
    assert r.saidas[0].texto == t.PERGUNTA_CARTAO.format(resumo="R$ 80,00 · 💊 Saúde")
    rotulos = [b.rotulo for linha in r.saidas[0].botoes for b in linha]
    assert rotulos == ["💳 Nubank", "💳 Inter", "➕ Outro cartão", "✖️ Cancelar"]
    inter = next(a for a in acoes(r) if a.startswith("lc:k:") and a != acao(r, "lc:k:"))
    r = bot(de, acao=inter)
    assert "💳 Inter" in r.saidas[0].texto
    # Resposta solta (sem "Responder"): o nome do cartão vale.
    bot(de, texto="farmácia 50 no crédito")
    r = bot(de, texto="Nubank")
    assert r.rotulo.endswith(".solta")
    assert "💳 Nubank" in r.saidas[0].texto
    assert [x[4] for x in parcelas_de(banco, de)][-3:] == ["Nubank", "Inter", "Nubank"]


def test_outro_cartao_pelo_nome_e_dias_soltos(bot: Bot, banco: Banco) -> None:
    de = com_nubank(bot)
    r = bot(de, acao="ct:nv")
    bot(de, pergunta="ct_nome", texto="Inter")
    bot(de, pergunta="ct_dias", contexto="💳 Inter", texto="fecha 25 vence 5")
    r = bot(de, texto="tênis 300 no crédito")
    r = bot(de, acao=acao(r, "lc:kn:"))  # ➕ Outro cartão
    assert r.saidas[0].pergunta == "lc_cartao"
    r = bot(de, pergunta="lc_cartao", texto="C6")
    assert r.saidas[0].pergunta == "lc_cartao_dias"
    r = bot(de, texto="fecha 5 vence 12")  # sem "Responder"
    assert r.saidas[0].texto.startswith(t.COMPRA_CREDITO)
    assert parcelas_de(banco, de)[-1][4] == "C6"


def test_correcoes_valem_para_a_compra_inteira(bot: Bot, conn: db.Connection, banco: Banco) -> None:
    de = com_nubank(bot)
    r = bot(de, texto="tênis 600 em 3x no nubank")
    assert r.conta is not None
    lrepo.guarda_refs(conn, r.conta, "telegram", [(ref_do_recibo(r), "c1")])
    r = bot(de, resposta_a="c1", texto="foi 900")
    assert "3x de R$ 300,00" in r.saidas[0].texto
    assert [x[1] for x in parcelas_de(banco, de)][-3:] == [30000, 30000, 30000]
    r = bot(de, acao=acao(r, "tx:cat:"))
    lazer = next(a for a in acoes(r) if a.startswith("tx:sc:"))
    bot(de, acao=lazer)
    assert len({x[5] for x in parcelas_de(banco, de)[-3:]}) == 1  # mesma categoria nas 3
    r = bot(de, resposta_a="c1", texto="na verdade foi no pix")
    assert t.COMPRA_CREDITO not in r.saidas[0].texto
    assert parcelas_de(banco, de)[-3:] == [
        (None, 90000, "done", None, "Pix", parcelas_de(banco, de)[-3][5], False),
        (
            None,
            30000,
            "planned",
            parcelas_de(banco, de)[-2][3],
            "Nubank",
            parcelas_de(banco, de)[-2][5],
            True,
        ),
        (
            None,
            30000,
            "planned",
            parcelas_de(banco, de)[-1][3],
            "Nubank",
            parcelas_de(banco, de)[-1][5],
            True,
        ),
    ]
    # Apagar e desfazer numa compra parcelada valem para todas as parcelas.
    r = bot(de, texto="tênis 300 em 3x no nubank")
    apagar = acao(r, "tx:del:")
    r = bot(de, acao=apagar)
    assert all(x[6] for x in parcelas_de(banco, de)[-3:])
    bot(de, acao=acao(r, "tx:un:"))
    assert not any(x[6] for x in parcelas_de(banco, de)[-3:])


def test_mudar_os_dias_muda_as_faturas_e_apagar_desativa(bot: Bot, banco: Banco) -> None:
    de = com_nubank(bot)
    r = bot(de, comando="cartoes")
    assert "💳 **Nubank** · fecha dia 3 · vence dia 10" in r.saidas[0].texto
    tela = bot(de, acao=acao(r, "ct:ed:"))
    pergunta = bot(de, acao=acao(tela, "ct:di:")).saidas[0]
    assert pergunta.pergunta == "ct_dias"
    r = bot(de, pergunta="ct_dias", contexto="💳 Nubank", texto="fecha 20, vence 28")
    assert r.saidas[0].texto.startswith(t.CARTAO_ATUALIZADO)
    hoje = agora().date()
    assert [x[3] for x in parcelas_de(banco, de)] == cartoes.faturas(hoje, 20, 28, 3)
    confirma = bot(de, acao=acao(tela, "ct:ap:"))
    r = bot(de, acao=acao(confirma, "ct:ok:"))
    assert r.saidas[0].texto == t.CARTAO_DESATIVADO.format(nome="Nubank")
    assert "⏸️ desativado" in bot(de, comando="cartoes").saidas[0].texto


def test_compras_antigas_no_credito_vao_para_o_primeiro_cartao(
    bot: Bot, conn: db.Connection, banco: Banco
) -> None:
    de = conta(bot)
    with db.connect(banco.migrator) as m, m.transaction():
        m.execute(
            "insert into telegrana.transactions (account_id, user_id, kind, amount_cents,"
            " category_id, payment_method_id, occurred_on, cash_on, source, installments)"
            " select x.account_id, x.user_id, 'expense', 60000, c.id, p.id, '2026-09-20',"
            " '2026-09-20', 'text', 3"
            " from telegrana.user_channels u"
            " join telegrana.account_members x on x.user_id = u.user_id"
            " join telegrana.categories c on c.account_id = x.account_id and c.code = 'vestuario'"
            " join telegrana.payment_methods p on p.account_id = x.account_id and p.kind = 'credit'"
            " where u.external_id = %s",
            (de,),
        )
    bot(de, acao="ct:nv")
    bot(de, pergunta="ct_nome", texto="Nubank")
    r = bot(de, pergunta="ct_dias", contexto="💳 Nubank", texto="fecha 3 vence 10")
    oferta = r.saidas[1]
    assert oferta.texto == t.MOVER_ANTIGAS.format(n=1, nome="Nubank")
    r = bot(de, acao=acao(Resultado(saidas=[oferta]), "ct:mv:"))
    assert r.saidas[0].texto == t.ANTIGAS_MOVIDAS.format(n=1, nome="Nubank")
    datas = cartoes.faturas(date(2026, 9, 20), 3, 10, 3)
    assert parcelas_de(banco, de) == [
        (k + 1, 20000, "planned", datas[k], "Nubank", "vestuario", False) for k in range(3)
    ]


def test_cartao_e_rascunho_de_outra_conta(bot: Bot, banco: Banco) -> None:
    a, b = com_nubank(bot), conta(bot)
    tela = bot(a, comando="cartoes")
    assert bot(b, acao=acao(tela, "ct:ed:")).saidas[0].texto == t.CARTAO_SUMIU  # RLS
    bot(a, acao="ct:nv")
    bot(a, pergunta="ct_nome", texto="Inter")
    bot(a, pergunta="ct_dias", contexto="💳 Inter", texto="fecha 25 vence 5")
    r = bot(a, texto="farmácia 80 no crédito")
    assert bot(b, acao=acao(r, "lc:k:")).saidas[0].texto == t.RASCUNHO_SUMIU
    assert parcelas_de(banco, b) == []

"""Resposta solta (sem "Responder"): Telegram Web e Desktop não abrem a resposta sozinhos."""

from __future__ import annotations

from dataclasses import replace

import pytest

from telegrana.core import conta as conta_mod
from telegrana.core import textos as t
from telegrana.infra import db
from tests.conftest import Banco
from tests.integration.test_cadastro import CTX, Bot, conn
from tests.integration.test_fixos import acao, fixos_de
from tests.integration.test_lancamentos import IAFalsa, conta, lancamentos_de

pytestmark = pytest.mark.integration
__all__ = ["conn"]


@pytest.fixture
def bot(conn: db.Connection) -> Bot:
    return Bot(conn, replace(CTX, extrator=IAFalsa()))


def test_cartao_novo_pelo_cartoes_sem_responder(bot: Bot) -> None:
    de = conta(bot)
    bot(de, acao="ct:nv")
    r = bot(de, texto="Inter")
    assert r.rotulo.endswith(".solta")
    assert r.saidas[0].pergunta == "ct_dias"
    r = bot(de, texto="fecha 25, vence 5")
    assert r.saidas[0].texto.startswith(t.CARTAO_CRIADO)


def test_valor_do_fixo_e_do_lancamento_sem_responder(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, texto="aluguel 1500 todo dia 10")
    cartao = bot(de, acao=acao(r, "fi:ed:"))
    bot(de, acao=acao(cartao, "fi:va:"))
    r = bot(de, texto="1600")
    assert r.saidas[0].texto.startswith(t.FIXO_ATUALIZADO)
    assert fixos_de(banco, de)[0][2] == 160000
    bot(de, texto="gastei no mercado")  # pergunta o valor
    r = bot(de, texto="45")
    assert r.saidas[0].texto.startswith(t.REGISTRADO["expense"])
    assert lancamentos_de(banco, de)[0][1:3] == (4500, "mercado")


def test_mensagem_que_nao_e_resposta_segue_e_a_pergunta_fecha(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, texto="aluguel 1500 todo dia 10")
    cartao = bot(de, acao=acao(r, "fi:ed:"))
    bot(de, acao=acao(cartao, "fi:va:"))
    r = bot(de, texto="mercado 50 no pix")  # não é só um valor: gasto novo
    assert r.saidas[0].texto.startswith(t.REGISTRADO["expense"])
    r = bot(de, texto="1600")  # a pergunta valia para UMA mensagem
    assert not r.rotulo.endswith(".solta")
    assert fixos_de(banco, de)[0][2] == 150000


@pytest.mark.parametrize(
    ("pergunta", "texto", "contexto", "cabe"),
    [
        ("lm_valor", "a luz deu 187", "🔔 Luz · 15/10/2026", True),
        ("lm_valor", "mercado 50", "🔔 Luz · 15/10/2026", False),
        ("ct_nome", "Banco do Brasil", "", True),
        ("ct_nome", "uber 12", "", False),
        ("ct_dias", "fecha 3 vence 10", "💳 Nubank", True),
        ("fi_dia", "dia doze", "🔁 Aluguel", True),
        ("fi_dia", "paguei o aluguel ontem no pix", "🔁 Aluguel", False),
        ("lc_data", "ontem", "", True),
        ("nome", "Fulano de Tal", "", False),  # fora da lista: só respondendo
    ],
)
def test_cara_de_resposta(pergunta: str, texto: str, contexto: str, cabe: bool) -> None:
    assert conta_mod.cabe(pergunta, texto, contexto) is cabe

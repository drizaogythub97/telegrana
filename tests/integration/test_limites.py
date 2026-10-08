"""Limites de uso por pessoa (S8, PLANO 8.6, D051)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from telegrana.core import limites
from telegrana.core import textos as t
from telegrana.core.contexto import FUSO, Limites
from telegrana.core.mensagens import Audio
from telegrana.infra import db
from tests.integration.test_cadastro import CTX, Bot, conn
from tests.integration.test_lancamentos import IAFalsa, conta

pytestmark = pytest.mark.integration
__all__ = ["conn"]

PEQUENOS = Limites(por_minuto=3, por_dia=5, ia=1, audio_segundos=60, arquivos=1)
AGORA = datetime(2026, 10, 8, 10, 30, tzinfo=FUSO)


@pytest.fixture(autouse=True)
def relogio(monkeypatch: pytest.MonkeyPatch) -> None:
    """Minuto fixo: o teste não depende da velocidade do banco."""
    monkeypatch.setattr(limites, "agora", lambda: AGORA)


@pytest.fixture
def ia() -> IAFalsa:
    return IAFalsa()


@pytest.fixture
def bot(conn: db.Connection, ia: IAFalsa) -> Bot:
    return Bot(conn, replace(CTX, extrator=ia, limites=PEQUENOS))


def account_id(bot: Bot, de: str) -> object:
    from telegrana.core import repositorio as repo

    ident = repo.identidade(bot.conn, "telegram", de)
    assert ident is not None
    return ident.account_id


def test_mensagens_por_minuto_avisa_uma_vez(bot: Bot) -> None:
    de = conta(bot)
    for _ in range(3):
        assert not bot(de, texto="mercado 10 no pix").rotulo.startswith("limite")
    r = bot(de, texto="mercado 10 no pix")
    assert r.rotulo == "limite.mensagens"
    assert r.saidas[0].texto == t.LIMITE_MINUTO
    r = bot(de, texto="mercado 10 no pix")  # segue acima: silêncio
    assert r.rotulo == "limite.mensagens"
    assert r.saidas == []
    assert not bot(de, acao="cancelar").rotulo.startswith("limite")  # botão não conta


def test_ia_do_dia_acaba_e_o_atalho_continua(conn: db.Connection, ia: IAFalsa) -> None:
    bot = Bot(conn, replace(CTX, extrator=ia, limites=replace(PEQUENOS, por_minuto=50, por_dia=50)))
    de = conta(bot)
    r = bot(de, texto="gastei no mercado")  # atalho: sem IA
    assert ia.chamadas == 0
    bot(de, pergunta="lc_valor", texto="30")
    r = bot(de, texto="qnt gastei de mercado?")  # IA: 1 chamada (o limite)
    assert ia.chamadas == 1
    assert limites.hoje(bot.conn, account_id(bot, de)).ia == 1
    r = bot(de, texto="oi")  # IA bloqueada para esta conta hoje
    assert ia.chamadas == 1
    assert r.saidas[0].texto == t.LIMITE_IA


def test_audio_do_dia(bot: Bot) -> None:
    de = conta(bot)
    longo = Audio(duracao=61, tamanho=1000, formato="ogg", baixar=lambda: b"")
    r = bot(de, audio=longo)
    assert r.rotulo == "limite.audio"
    assert r.saidas[0].texto == t.LIMITE_AUDIO.format(minutos=1)


def test_outra_conta_tem_o_proprio_limite(bot: Bot) -> None:
    a, b = conta(bot), conta(bot)
    for _ in range(4):
        bot(a, texto="mercado 10 no pix")
    assert bot(a, texto="mercado 10 no pix").rotulo == "limite.mensagens"
    assert not bot(b, texto="mercado 10 no pix").rotulo.startswith("limite")


def test_admin_nao_tem_limite(conn: db.Connection) -> None:
    bot = Bot(conn, replace(CTX, extrator=IAFalsa(), limites=PEQUENOS))
    from telegrana.core import repositorio as repo
    from tests.integration.test_cadastro import cadastra, novo_telefone

    if repo.identidade(conn, "telegram", CTX.admin_id) is None:  # outro teste pode ter criado
        cadastra(bot, CTX.admin_id, novo_telefone())
    for _ in range(6):
        assert not bot(CTX.admin_id, texto="mercado 10 no pix").rotulo.startswith("limite")

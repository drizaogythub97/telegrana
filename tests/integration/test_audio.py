"""Lançamentos por áudio (S3.1) contra Postgres real, com transcritor e IA simulados."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from telegrana.core import audio as aud
from telegrana.core import lancamentos_repo as lrepo
from telegrana.core import textos as t
from telegrana.core.audio import Transcricao
from telegrana.core.entendimento import ErroExtracao
from telegrana.core.mensagens import ADMIN, Audio, ErroCanal, Resultado
from telegrana.infra import db
from tests.conftest import Banco
from tests.integration.test_cadastro import CTX, Bot, conn
from tests.integration.test_lancamentos import IAFalsa, conta, lancamentos_de, ref_do_recibo

pytestmark = pytest.mark.integration
__all__ = ["conn"]


class OuvidoFalso:
    """O "áudio" é o próprio texto em bytes; prefixos simulam falhas do provedor."""

    def __init__(self) -> None:
        self.chamadas = 0

    def transcreve(self, dados: bytes, formato: str, duracao: int) -> Transcricao:
        self.chamadas += 1
        texto = dados.decode()
        if texto == "LIMITE":
            raise ErroExtracao("limite", limite=True, espera=30)
        if texto == "FALHA":
            raise ErroExtracao("falhou")
        return Transcricao(texto, "whisper-large-v3", aud.segundos_cobrados(duracao))


def audio(fala: str, duracao: int = 5, tamanho: int | None = 1000) -> Audio:
    return Audio(duracao=duracao, tamanho=tamanho, formato="ogg", baixar=lambda: fala.encode())


@pytest.fixture
def ouvido() -> OuvidoFalso:
    return OuvidoFalso()


@pytest.fixture
def bot(conn: db.Connection, ouvido: OuvidoFalso) -> Bot:
    return Bot(conn, replace(CTX, extrator=IAFalsa(), transcritor=ouvido))


def origem_de(banco: Banco, de: str) -> list[tuple[Any, ...]]:
    with db.connect(banco.migrator) as m, m.transaction():
        return m.execute(
            "select t.source, t.original_text from telegrana.transactions t"
            " join telegrana.user_channels u on u.user_id = t.user_id"
            " where u.external_id = %s order by t.created_at",
            (de,),
        ).fetchall()


def textos_de(r: Resultado) -> list[str]:
    return [s.texto for s in r.saidas if s.destino != ADMIN]


# ---------------------------------------------------------------------------
def test_audio_vira_lancamento_com_transcricao_no_recibo(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, audio=audio("mercado 45,90 no pix"))
    assert r.rotulo == "lancamento.lancamentos.atalho.audio"
    recibo = r.saidas[0]
    assert recibo.texto.startswith(t.REGISTRADO["expense"])
    assert "🛒 Mercado · R$ 45,90" in recibo.texto
    assert "🎙️ «mercado 45,90 no pix»" in recibo.texto
    assert lancamentos_de(banco, de)[0][:4] == ("expense", 4590, "mercado", "pix")
    assert origem_de(banco, de) == [("audio", "mercado 45,90 no pix")]


@pytest.mark.parametrize(
    ("som", "esperado", "rotulo"),
    [
        (audio("x", duracao=121), t.AUDIO_LONGO, "lancamento.audio.longo"),
        (audio("x", tamanho=21 * 1024 * 1024), t.AUDIO_GRANDE, "lancamento.audio.grande"),
        (audio("   "), t.AUDIO_VAZIO, "lancamento.audio.vazio"),
        (audio("LIMITE"), t.SOBRECARREGADO, "lancamento.audio.limite"),
        (audio("FALHA"), t.AUDIO_FALHOU, "lancamento.audio.falhou"),
    ],
)
def test_limites_e_falhas(
    bot: Bot, ouvido: OuvidoFalso, banco: Banco, som: Audio, esperado: str, rotulo: str
) -> None:
    de = conta(bot)
    r = bot(de, audio=som)
    assert (textos_de(r), r.rotulo) == ([esperado], rotulo)
    assert lancamentos_de(banco, de) == []
    if rotulo in {"lancamento.audio.longo", "lancamento.audio.grande"}:
        assert ouvido.chamadas == 0  # recusado antes de baixar e transcrever


def test_download_que_falha_e_sem_transcritor(bot: Bot, conn: db.Connection) -> None:
    de = conta(bot)

    def falha() -> bytes:
        raise ErroCanal("download: HTTP 404")

    r = bot(de, audio=Audio(duracao=5, tamanho=None, formato="ogg", baixar=falha))
    assert textos_de(r) == [t.AUDIO_FALHOU]
    surdo = Bot(conn, replace(CTX, extrator=IAFalsa(), transcritor=None))
    assert textos_de(surdo(de, audio=audio("mercado 10"))) == [t.AUDIO_INDISPONIVEL]


def test_audio_que_nao_e_lancamento_mostra_o_que_ouviu(bot: Bot) -> None:
    de = conta(bot)
    r = bot(de, audio=audio("oi"))
    assert textos_de(r) == [t.OUVI.format(trecho="oi"), t.OI]


def test_audio_responde_pergunta_e_corrige_recibo(
    bot: Bot, conn: db.Connection, banco: Banco
) -> None:
    de = conta(bot)
    r = bot(de, texto="gastei no mercado")
    assert r.saidas[0].pergunta == "lc_valor"
    r = bot(de, pergunta="lc_valor", audio=audio("trinta e sete e cinquenta"))
    assert "🛒 Mercado · R$ 37,50" in r.saidas[0].texto
    assert r.conta is not None
    lrepo.guarda_refs(conn, r.conta, "telegram", [(ref_do_recibo(r), "msg-a1")])
    r = bot(de, resposta_a="msg-a1", audio=audio("foi 40 no débito"))
    assert r.saidas[0].texto.startswith(t.CORRIGIDO)
    assert lancamentos_de(banco, de)[0][1:4] == (4000, "mercado", "debit")


def test_medidor_conta_segundos_e_avisa_o_admin(
    bot: Bot, monkeypatch: pytest.MonkeyPatch, banco: Banco
) -> None:
    with db.connect(banco.migrator) as m, m.transaction():
        m.execute("delete from telegrana.ai_usage")
    monkeypatch.setattr(aud, "LIMITE_DIARIO_SEGUNDOS", 100)
    de = conta(bot)
    r1 = bot(de, audio=audio("oi", duracao=60))  # 60 s: 60%
    r2 = bot(de, audio=audio("oi", duracao=20))  # 80 s: passou de 70% → avisa
    assert not [s for s in r1.saidas if s.destino == ADMIN]
    avisos = [s.texto for s in r2.saidas if s.destino == ADMIN]
    assert avisos == [t.ADM_COTA_IA.format(modelo="whisper-large-v3", pct=80)]
    with db.connect(banco.migrator) as m, m.transaction():
        uso = m.execute(
            "select requests, tokens, audio_seconds from telegrana.ai_usage"
            " where model = 'whisper-large-v3'"
        ).fetchone()
    assert uso == (2, 0, 80)


def test_audio_responde_perguntas_do_fixo_e_do_lembrete(
    bot: Bot, conn: db.Connection, banco: Banco, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Respondendo à pergunta com áudio (o celular abre a resposta sozinho): 05/10/2026."""
    from datetime import datetime

    from telegrana.core import lembretes
    from telegrana.core.contexto import FUSO

    de = conta(bot)
    bot(de, texto="aluguel 1500 todo dia 10")
    r = bot(de, pergunta="fi_dia", contexto="🔁 Aluguel", audio=audio("dia doze"))
    assert textos_de(r)[0] == t.OUVI.format(trecho="dia doze")
    assert "dia 12" in textos_de(r)[1]

    with db.connect(banco.migrator) as m, m.transaction():
        m.execute("update telegrana.fixed_items set created_at = '2026-09-20 12:00-03'")
    monkeypatch.setattr(lembretes, "agora", lambda: datetime(2026, 10, 13, 10, tzinfo=FUSO))
    r = bot(
        de,
        pergunta="lm_valor",
        contexto="🔔 Aluguel · 12/10/2026",
        audio=audio("mil quinhentos e cinquenta"),
    )
    assert "R$ 1.550,00" in textos_de(r)[0]  # o recibo já é a resposta (sem "Ouvi")
    assert lancamentos_de(banco, de)[0][1] == 155000

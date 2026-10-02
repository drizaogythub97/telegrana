"""Correção de lançamentos com a IA interpretando e o código aplicando (D042)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Any

import pytest

from telegrana.core import lancamentos_repo as lrepo
from telegrana.core import textos as t
from telegrana.core.entendimento import ErroExtracao
from telegrana.core.extracao import CorrecaoIA
from telegrana.core.mensagens import Resultado
from telegrana.infra import db
from tests.conftest import Banco
from tests.integration.test_cadastro import CTX, Bot, acoes, conn
from tests.integration.test_lancamentos import (
    IAFalsa,
    Uso,
    conta,
    extracao,
    lancamentos_de,
    ref_do_recibo,
)

pytestmark = pytest.mark.integration
__all__ = ["conn"]


def correcao(**kw: Any) -> CorrecaoIA:
    base: dict[str, Any] = {
        "entendeu": True,
        "valor_texto": None,
        "data_texto": None,
        "categoria": None,
        "termo_categoria": None,
        "categorias_sugeridas": [],
        "nova_categoria_sugerida": None,
        "forma_pagamento": None,
        "descricao": None,
    }
    return CorrecaoIA(**{**base, **kw})


PADARIA = correcao(termo_categoria="padaria", categorias_sugeridas=["mercado", "alimentacao"])


class IACorretora(IAFalsa):
    def __init__(self) -> None:
        super().__init__()
        self.respostas["na verdade foi na padaria"] = extracao(intencao="correcao")
        self.correcoes: dict[str, CorrecaoIA] = {
            "Na verdade, foi na padaria, não foi no mercado.": PADARIA,
            "O valor está correto, só não quero colocar no mercado. Na verdade, foi na padaria.": PADARIA,
            "na verdade foi na padaria": PADARIA,
            "foi 52,80": correcao(valor_texto="52,80"),
            "não foi no pix, foi no débito": correcao(forma_pagamento="debito"),
            "era farmácia": correcao(categoria="saude", termo_categoria="farmácia"),
            "muda a descrição pra compras do mês": correcao(descricao="compras do mês"),
            "a IA inventou": correcao(valor_texto="99"),  # não está na frase
            "tá certo": correcao(entendeu=False),
        }
        self.vistos: list[str] = []

    def corrige(self, texto: str, atual: str, categorias: Any, hoje: date) -> CorrecaoIA:
        self.vistos.append(atual)
        if self.limite:
            raise ErroExtracao("limite", limite=True, espera=30)
        self.ultimo_uso = Uso(800, 150)
        return self.correcoes[texto]


@pytest.fixture
def ia() -> IACorretora:
    return IACorretora()


@pytest.fixture
def bot(conn: db.Connection, ia: IACorretora) -> Bot:
    return Bot(conn, replace(CTX, extrator=ia))


def recibo(bot: Bot, conn: db.Connection, de: str, texto: str, msg: str) -> Resultado:
    r = bot(de, texto=texto)
    assert r.conta is not None
    lrepo.guarda_refs(conn, r.conta, "telegram", [(ref_do_recibo(r), msg)])
    return r


def test_correcao_de_categoria_usa_a_regra_aprendida(
    bot: Bot, conn: db.Connection, ia: IACorretora, banco: Banco
) -> None:
    de = conta(bot)
    # Ensina "padaria → Alimentação fora".
    r = bot(de, texto="padaria 12")
    r = bot(de, acao=acoes(r)[1])
    bot(de, acao=next(a for a in acoes(r) if a.startswith("rg:") and a != "rg:no"))
    recibo(bot, conn, de, "mercado 50 no pix", "m1")
    r = bot(de, resposta_a="m1", texto="Na verdade, foi na padaria, não foi no mercado.")
    assert r.rotulo == "lancamento.correcao.recibo.ia"
    assert r.saidas[0].texto.startswith(t.CORRIGIDO)
    assert "🍽️ Alimentação fora · R$ 50,00" in r.saidas[0].texto
    assert ia.vistos[-1] == "Mercado · R$ 50,00 · Pix · " + ia.vistos[-1].split(" · ")[3]
    assert lancamentos_de(banco, de)[1][1:3] == (5000, "alimentacao")


def test_sem_regra_pergunta_sem_a_categoria_negada_e_cria_a_nova(
    bot: Bot, conn: db.Connection, banco: Banco
) -> None:
    de = conta(bot)
    recibo(bot, conn, de, "mercado 50 no pix", "m2")
    texto = "O valor está correto, só não quero colocar no mercado. Na verdade, foi na padaria."
    r = bot(de, resposta_a="m2", texto=texto)
    pergunta = r.saidas[0]
    assert pergunta.texto == t.PERGUNTA_CATEGORIA_CORRECAO.format(resumo="R$ 50,00")
    rotulos = [b.rotulo for linha in pergunta.botoes for b in linha]
    assert rotulos == ["🍽️ Alimentação fora", "➕ Criar «Padaria»", "🔎 Outra"]  # sem Mercado
    r = bot(de, acao=next(a for a in acoes(r) if a.startswith("tx:nc:")))
    assert "🥖 Padaria · R$ 50,00" in r.saidas[0].texto
    assert lancamentos_de(banco, de)[0][1:3] == (5000, "Padaria")  # o valor ficou


def test_correcao_por_mensagem_sem_responder_ao_recibo(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    bot(de, texto="mercado 30")
    r = bot(de, texto="na verdade foi na padaria")
    assert r.rotulo == "lancamento.correcao.ia.ia"
    assert t.PERGUNTA_CATEGORIA_CORRECAO.format(resumo="R$ 30,00") == r.saidas[0].texto


@pytest.mark.parametrize(
    ("frase", "esperado"),
    [
        ("foi 52,80", (5280, "mercado", "pix")),
        ("não foi no pix, foi no débito", (5000, "mercado", "debit")),
        ("era farmácia", (5000, "saude", "pix")),
    ],
)
def test_valor_forma_e_categoria(
    bot: Bot, conn: db.Connection, banco: Banco, frase: str, esperado: tuple[Any, ...]
) -> None:
    de = conta(bot)
    recibo(bot, conn, de, "mercado 50 no pix", "m3")
    r = bot(de, resposta_a="m3", texto=frase)
    assert r.saidas[0].texto.startswith(t.CORRIGIDO)
    assert lancamentos_de(banco, de)[0][1:4] == esperado


def test_descricao_valor_inventado_e_nada_a_mudar(
    bot: Bot, conn: db.Connection, banco: Banco
) -> None:
    de = conta(bot)
    recibo(bot, conn, de, "mercado 50 no pix", "m4")
    r = bot(de, resposta_a="m4", texto="muda a descrição pra compras do mês")
    assert "📝 compras do mês" in r.saidas[0].texto
    r = bot(de, resposta_a="m4", texto="a IA inventou")  # valor que não está na frase
    assert [s.texto for s in r.saidas] == [t.CORRECAO_IGUAL]
    assert lancamentos_de(banco, de)[0][1] == 5000
    assert [s.texto for s in bot(de, resposta_a="m4", texto="tá certo").saidas] == [
        t.CORRECAO_NAO_ENTENDI
    ]


def test_ia_no_limite_cai_no_leitor_do_codigo(
    bot: Bot, conn: db.Connection, ia: IACorretora, banco: Banco
) -> None:
    de = conta(bot)
    recibo(bot, conn, de, "mercado 50 no pix", "m5")
    ia.limite = True
    r = bot(de, resposta_a="m5", texto="foi 52,80")
    assert r.rotulo == "lancamento.correcao.recibo.ia_limite"
    assert lancamentos_de(banco, de)[0][1] == 5280


def test_criar_categoria_pelo_botao_de_outra_conta_falha(
    bot: Bot, conn: db.Connection, banco: Banco
) -> None:
    a, b = conta(bot), conta(bot)
    recibo(bot, conn, a, "mercado 50", "m6")
    r = bot(a, resposta_a="m6", texto="na verdade foi na padaria")
    criar = next(x for x in acoes(r) if x.startswith("tx:nc:"))
    assert bot(b, acao=criar).saidas[0].texto == t.RASCUNHO_SUMIU  # RLS
    assert lancamentos_de(banco, a)[0][2] == "mercado"

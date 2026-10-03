"""Lançamentos no bot (S2.3) contra Postgres real, com IA simulada."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

import pytest

from telegrana.core import lancamentos
from telegrana.core import lancamentos_repo as lrepo
from telegrana.core import textos as t
from telegrana.core.entendimento import ErroExtracao
from telegrana.core.extracao import ExtracaoIA, LancamentoIA
from telegrana.core.mensagens import ADMIN, Resultado
from telegrana.infra import db
from tests.conftest import Banco
from tests.integration.test_cadastro import (
    CTX,
    Bot,
    acoes,
    cadastra,
    conn,
    novo_id,
    novo_telefone,
)

pytestmark = pytest.mark.integration
__all__ = ["conn"]


@dataclass
class Uso:
    tokens_entrada: int
    tokens_saida: int
    tokens_em_cache: int = 0


def item(**kw: Any) -> LancamentoIA:
    base: dict[str, Any] = {
        "tipo": "gasto",
        "valor_texto": None,
        "data_texto": None,
        "descricao": None,
        "categoria": None,
        "categorias_sugeridas": [],
        "nova_categoria_sugerida": None,
        "forma_pagamento": None,
        "cartao": None,
        "parcelas": None,
        "pode_ser_fixo": False,
        "duvida": None,
    }
    return LancamentoIA(**{**base, **kw})


def extracao(*itens: LancamentoIA, intencao: str = "lancamentos") -> ExtracaoIA:
    return ExtracaoIA(
        intencao=intencao,  # type: ignore[arg-type]
        lancamentos=list(itens),
        correcao_campo=None,
        correcao_texto=None,
        pergunta=None,
    )


class IAFalsa:
    """Responde pela tabela; texto fora dela = IA fora do ar."""

    def __init__(self) -> None:
        self.respostas: dict[str, ExtracaoIA] = {
            "gastei no mercado": extracao(item(categoria="mercado", descricao="mercado")),
            "guardei 52 mil na poupança": extracao(
                item(tipo="transferencia", valor_texto="52 mil", forma_pagamento="poupanca")
            ),
            "qnt gastei de mercado?": extracao(intencao="consulta"),
            "oi": extracao(intencao="conversa"),
        }
        self.limite = False
        self.ultimo_uso: Uso | None = None
        self.chamadas = 0

    def extrai(self, texto: str, categorias: Any, hoje: date) -> ExtracaoIA:
        self.chamadas += 1
        if self.limite:
            raise ErroExtracao("limite", limite=True, espera=30)
        if texto not in self.respostas:
            raise ErroExtracao("resposta desconhecida")
        self.ultimo_uso = Uso(1000, 200)
        return self.respostas[texto]


@pytest.fixture
def ia() -> IAFalsa:
    return IAFalsa()


@pytest.fixture
def bot(conn: db.Connection, ia: IAFalsa) -> Bot:
    return Bot(conn, replace(CTX, extrator=ia))


def conta(bot: Bot) -> str:
    de = novo_id()
    cadastra(bot, de, novo_telefone())
    return de


def lancamentos_de(banco: Banco, de: str) -> list[tuple[Any, ...]]:
    with db.connect(banco.migrator) as m, m.transaction():
        return m.execute(
            "select t.kind, t.amount_cents, coalesce(c.code, c.name), p.kind, t.status,"
            " t.deleted_at is not null, t.recurring, t.installments"
            " from telegrana.transactions t"
            " join telegrana.user_channels u on u.user_id = t.user_id"
            " left join telegrana.categories c on c.id = t.category_id"
            " left join telegrana.payment_methods p on p.id = t.payment_method_id"
            " where u.external_id = %s order by t.created_at",
            (de,),
        ).fetchall()


def ref_do_recibo(r: Resultado) -> str:
    return next(s.ref for s in r.saidas if s.ref)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
def test_atalho_registra_sem_ia(bot: Bot, ia: IAFalsa, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, texto="mercado 45,90 no pix")
    assert r.rotulo == "lancamento.lancamentos.atalho"
    assert ia.chamadas == 0
    recibo = r.saidas[0]
    assert recibo.texto.startswith(t.REGISTRADO["expense"])
    assert "🛒 Mercado · R$ 45,90" in recibo.texto
    assert recibo.ref is not None
    assert recibo.ref.startswith("tx:")
    assert acoes(r)[0].startswith("tx:fix:")
    assert lancamentos_de(banco, de) == [
        ("expense", 4590, "mercado", "pix", "done", False, None, None)
    ]


def test_ambiguo_pergunta_e_aprende_a_regra(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, texto="padaria 18")
    pergunta = r.saidas[0]
    assert "Em qual categoria" in pergunta.texto
    rotulos = [b.rotulo for linha in pergunta.botoes for b in linha]
    assert rotulos[:2] == ["🛒 Mercado", "🍽️ Alimentação fora"]
    assert "➕ Criar «Padaria»" in rotulos
    assert "📦 Outros" in rotulos
    assert lancamentos_de(banco, de) == []  # nada gravado antes da resposta

    alimentacao = acoes(r)[1]
    r = bot(de, acao=alimentacao)
    assert "🍽️ Alimentação fora · R$ 18,00" in r.saidas[0].texto
    lembrar = [a for a in acoes(r) if a.startswith("rg:")]
    assert lembrar[1] == "rg:no"
    rr = bot(de, acao=lembrar[0])
    assert rr.saidas[0].texto.startswith("🧠 Pronto")
    # Da próxima vez a regra resolve sem perguntar.
    r = bot(de, texto="padaria 7,50")
    assert "🍽️ Alimentação fora · R$ 7,50" in r.saidas[0].texto


def test_cria_categoria_nova_na_hora(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, texto="padaria 9")
    criar = next(a for a in acoes(r) if a.startswith("lc:n:"))
    r = bot(de, acao=criar)
    assert "🥖 Padaria · R$ 9,00" in r.saidas[0].texto
    assert lancamentos_de(banco, de)[0][2] == "Padaria"


def test_valor_que_faltou_e_perguntado(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, texto="gastei no mercado")
    assert r.rotulo == "lancamento.lancamentos.atalho"  # sem número: o atalho pergunta o valor
    assert r.saidas[0].pergunta == "lc_valor"
    r = bot(de, pergunta="lc_valor", texto="não sei")
    assert r.saidas[0].pergunta == "lc_valor"  # pergunta de novo
    r = bot(de, pergunta="lc_valor", texto="37,50")
    assert "🛒 Mercado · R$ 37,50" in r.saidas[0].texto
    assert lancamentos_de(banco, de)[0][:3] == ("expense", 3750, "mercado")


def test_valor_alto_pede_confirmacao_e_transferencia_vai_para_poupanca(
    bot: Bot, banco: Banco
) -> None:
    de = conta(bot)
    r = bot(de, texto="guardei 52 mil na poupança")
    assert "Valor alto" in r.saidas[0].texto
    r = bot(de, acao=acoes(r)[0])
    assert r.saidas[0].texto.startswith(t.REGISTRADO["transfer"])
    assert "🐷 Poupança · R$ 52.000,00" in r.saidas[0].texto
    assert lancamentos_de(banco, de)[0][:3] == ("transfer", 5200000, None)


def test_cancelar_rascunho_nao_grava(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, texto="padaria 5")
    r = bot(de, acao=next(a for a in acoes(r) if a.startswith("lc:x:")))
    assert r.saidas[0].texto == t.RASCUNHO_CANCELADO
    assert lancamentos_de(banco, de) == []


def test_botoes_do_recibo(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, texto="uber 22")
    fix, cat, apagar = acoes(r)[:3]
    assert bot(de, acao=fix).saidas[0].texto == t.CORRIGIR_COMO
    escolha = bot(de, acao=cat)
    combustivel = next(
        a
        for s in escolha.saidas
        for linha in s.botoes
        for b in linha
        if b.rotulo == "⛽ Combustível" and (a := b.acao)
    )
    r = bot(de, acao=combustivel)
    assert r.saidas[0].texto.startswith(t.CORRIGIDO)
    assert "⛽ Combustível · R$ 22,00" in r.saidas[0].texto
    r = bot(de, acao=apagar)
    assert r.saidas[0].texto.startswith("🗑️ Apagado")
    assert lancamentos_de(banco, de)[0][5] is True
    bot(de, acao=acoes(r)[0])  # desfazer
    assert lancamentos_de(banco, de)[0][5] is False


def test_correcao_respondendo_ao_recibo(bot: Bot, conn: db.Connection, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, texto="mercado 45 no pix")
    assert r.conta is not None
    lrepo.guarda_refs(conn, r.conta, "telegram", [(ref_do_recibo(r), "msg-1")])
    r = bot(de, resposta_a="msg-1", texto="foi 54,90 no débito")
    assert r.saidas[0].texto.startswith(t.CORRIGIDO)
    assert lancamentos_de(banco, de)[0][1:4] == (5490, "mercado", "debit")
    r = bot(de, resposta_a="msg-1", texto="sei lá")
    assert r.saidas[0].texto == t.CORRECAO_NAO_ENTENDI


def test_recibo_de_outra_conta_nao_e_corrigido(bot: Bot, conn: db.Connection, banco: Banco) -> None:
    a, b = conta(bot), conta(bot)
    r = bot(a, texto="mercado 10")
    lrepo.guarda_refs(conn, r.conta, "telegram", [(ref_do_recibo(r), "msg-a")])
    r = bot(b, resposta_a="msg-a", texto="foi 99")
    assert r.saidas[0].texto == t.NADA_PARA_CORRIGIR
    # Botão forjado com o id do lançamento de A, tocado por B.
    tx = ref_do_recibo(bot(a, texto="mercado 20")).removeprefix("tx:")
    from telegrana.core.seguranca import curto

    r = bot(b, acao=f"tx:del:{curto(uuid.UUID(tx))}")
    assert r.saidas[0].texto == t.RASCUNHO_SUMIU
    assert all(not x[5] for x in lancamentos_de(banco, a))


def test_pergunta_se_e_fixo(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, texto="netflix 55,90")
    assert t.PERGUNTA_FIXO in r.saidas[0].texto
    sim = next(a for a in acoes(r) if a.startswith("fx:s:"))
    criado = bot(de, acao=sim).saidas[0].texto
    assert criado.startswith(t.FIXO_CRIADO)
    assert "Netflix" in criado
    assert lancamentos_de(banco, de)[0][6] is True


def test_parcelado_no_credito(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, texto="tenis 480 em 4x")
    assert "💳 Crédito · 4x" in r.saidas[0].texto
    assert lancamentos_de(banco, de)[0][3] == "credit"
    assert lancamentos_de(banco, de)[0][7] == 4


def test_ia_fora_do_ar_e_limite(bot: Bot, ia: IAFalsa) -> None:
    de = conta(bot)
    assert bot(de, texto="algo que a IA não conhece").saidas[0].texto == t.IA_FALHOU
    ia.limite = True
    assert bot(de, texto="guardei 52 mil na poupança").saidas[0].texto == t.SOBRECARREGADO


def test_intencoes_sem_lancamento(bot: Bot) -> None:
    de = conta(bot)
    assert bot(de, texto="qnt gastei de mercado?").saidas[0].texto == t.CONSULTA_EM_BREVE
    assert bot(de, texto="oi").saidas[0].texto == t.OI


def test_medidor_avisa_o_admin_uma_vez(
    bot: Bot, monkeypatch: pytest.MonkeyPatch, conn: db.Connection, banco: Banco
) -> None:
    with db.connect(banco.migrator) as m, m.transaction():
        m.execute("delete from telegrana.ai_usage")
    monkeypatch.setattr(lancamentos, "LIMITE_DIARIO_TOKENS", 2000)
    de = conta(bot)
    r1 = bot(de, texto="oi")  # 1.200 tokens: 60%
    r2 = bot(de, texto="oi")  # 2.400: passou de 70% → avisa
    r3 = bot(de, texto="oi")  # já avisou hoje
    assert not [s for s in r1.saidas if s.destino == ADMIN]
    assert next(s.texto for s in r2.saidas if s.destino == ADMIN) == t.ADM_COTA_IA.format(
        modelo="desconhecido", pct=120
    )
    assert not [s for s in r3.saidas if s.destino == ADMIN]

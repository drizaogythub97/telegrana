"""Relatórios em texto (S6, D047) contra Postgres real: números conferidos contra os dados."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from typing import Any

import pytest

from telegrana.core import relatorios
from telegrana.core import textos as t
from telegrana.core.contexto import FUSO
from telegrana.core.extracao import ConsultaIA
from telegrana.core.mensagens import Resultado
from telegrana.infra import db
from tests.conftest import Banco
from tests.integration.test_cadastro import CTX, Bot, acoes, conn
from tests.integration.test_lancamentos import IAFalsa, Uso, conta

pytestmark = pytest.mark.integration
__all__ = ["conn"]

HOJE = datetime(2026, 10, 6, 10, tzinfo=FUSO)


@pytest.fixture(autouse=True)
def relogio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(relatorios, "agora", lambda: HOJE)


@pytest.fixture
def bot(conn: db.Connection) -> Bot:
    return Bot(conn, replace(CTX, extrator=IAFalsa()))


def lanca(
    banco: Banco,
    de: str,
    kind: str,
    centavos: int,
    codigo: str,
    dia: str,
    *,
    status: str = "done",
    forma: str = "pix",
    fatura: str | None = None,
    descricao: str | None = None,
) -> None:
    with db.connect(banco.migrator) as m, m.transaction():
        m.execute(
            "insert into telegrana.transactions (account_id, user_id, kind, amount_cents,"
            " category_id, payment_method_id, occurred_on, cash_on, source, status, invoice_on,"
            " description)"
            " select x.account_id, x.user_id, %s, %s, c.id, p.id, %s::date, coalesce(%s::date, %s::date), 'text',"
            " %s, %s::date, %s"
            " from telegrana.user_channels u join telegrana.account_members x on x.user_id = u.user_id"
            " join telegrana.categories c on c.account_id = x.account_id and c.code = %s"
            " join telegrana.payment_methods p on p.account_id = x.account_id and p.kind = %s"
            " where u.external_id = %s limit 1",
            (kind, centavos, dia, fatura, dia, status, fatura, descricao, codigo, forma, de),
        )


@pytest.fixture
def com_dados(bot: Bot, banco: Banco) -> str:
    de = conta(bot)
    lanca(banco, de, "expense", 10000, "mercado", "2026-10-01")
    lanca(banco, de, "expense", 5000, "mercado", "2026-10-05", descricao="feira do sabado")
    lanca(banco, de, "expense", 3000, "transporte", "2026-10-03", descricao="uber")
    lanca(banco, de, "income", 300000, "salario", "2026-10-05")
    lanca(banco, de, "expense", 20000, "mercado", "2026-09-15")
    # Compra no cartão ainda não paga (prevista, na fatura de 10/11): fora do realizado.
    lanca(banco, de, "expense", 8000, "mercado", "2026-10-04", status="planned",
          forma="credit", fatura="2026-11-10")  # fmt: skip
    return de


def primeira(r: Resultado) -> str:
    return r.saidas[0].texto


def test_consulta_pelo_leitor_do_codigo(bot: Bot, com_dados: str) -> None:
    de = com_dados
    r = bot(de, texto="quanto gastei de mercado este mês?")
    assert r.rotulo == "relatorio.consulta"
    assert "**Gastos com 🛒 Mercado** · outubro/2026" in primeira(r)
    assert "**Total: R$ 150,00**" in primeira(r)
    assert "Mais R$ 80,00 em compras no cartão" in primeira(r)
    incluir = next(a for a in acoes(r) if a.startswith("rp:cp:"))
    r = bot(de, acao=incluir)
    assert t.VISOES["compra"] in primeira(r)
    assert "**Total: R$ 230,00**" in primeira(r)

    assert "**Total: R$ 200,00**" in primeira(bot(de, texto="meus gastos do mês passado"))
    r = bot(de, texto="quanto gastei nos últimos 3 meses, mês a mês")
    assert "set/2026 · R$ 200,00" in primeira(r)
    assert "out/2026 · R$ 180,00" in primeira(r)
    r = bot(de, texto="quanto sobrou este mês")
    assert "Entrou: R$ 3.000,00" in primeira(r)
    assert "**Saldo: +R$ 2.820,00**" in primeira(r)
    r = bot(de, texto="quanto gastei por categoria este mês")
    assert "🛒 Mercado · R$ 150,00 · 83%" in primeira(r)
    assert "🚗 Transporte · R$ 30,00 · 17%" in primeira(r)
    assert primeira(bot(de, texto="quanto gastei na época das cruzadas")).startswith("📊")


class IAConsulta(IAFalsa):
    def __init__(self, resposta: ConsultaIA) -> None:
        super().__init__()
        self.resposta = resposta

    def consulta(self, texto: str, categorias: Any, hoje: date) -> tuple[ConsultaIA, str]:
        self.ultimo_uso = Uso(900, 100)
        return self.resposta, "openai/gpt-oss-120b"


def consulta_ia(**kw: Any) -> ConsultaIA:
    base: dict[str, Any] = {
        "tipo": "gastos",
        "periodo_texto": None,
        "categorias": [],
        "termo": None,
        "forma_pagamento": None,
        "cartao": None,
        "agrupar": "nenhum",
        "limite": None,
        "visao": "realizado",
    }
    return ConsultaIA(**{**base, **kw})


def test_consulta_pela_ia_e_validada_pelo_codigo(
    conn: db.Connection, bot: Bot, com_dados: str
) -> None:
    de = com_dados
    ia = IAConsulta(consulta_ia(categorias=["mercado", "inventada"], periodo_texto="setembro"))
    com_ia = Bot(conn, replace(CTX, extrator=ia))
    r = com_ia(de, texto="quanto gastei de mercado em setembro?")
    assert r.rotulo == "relatorio.consulta.ia"
    assert "**Gastos com 🛒 Mercado** · setembro/2026" in primeira(r)  # "inventada" ignorada
    assert "**Total: R$ 200,00**" in primeira(r)
    ia.resposta = consulta_ia(termo="uber")
    assert "**Total: R$ 30,00**" in primeira(com_ia(de, texto="quanto gastei de uber?"))
    ia.resposta = consulta_ia(agrupar="categoria", limite=1)
    r = com_ia(de, texto="onde mais gastei este mês?")
    assert "🛒 Mercado · R$ 150,00" in primeira(r)
    assert "…e mais 1" in primeira(r)
    ia.resposta = consulta_ia(tipo="saldo", agrupar="categoria")  # vira o total
    r = com_ia(de, texto="quanto sobrou este mês?")
    assert "🛒 Mercado" not in primeira(r)
    assert "**Saldo: +R$ 2.820,00**" in primeira(r)
    ia.resposta = consulta_ia(periodo_texto="no tempo do onça")
    assert primeira(com_ia(de, texto="quanto gastei no tempo do onça?")).startswith("📊")


def test_resumo_e_preferencias(bot: Bot, com_dados: str, banco: Banco) -> None:
    de = com_dados
    r = bot(de, comando="resumo")
    texto = primeira(r)
    assert texto.startswith(t.RESUMO_TITULO.format(periodo="outubro/2026"))
    assert "Entrou: R$ 3.000,00" in texto
    assert "Saiu: R$ 180,00" in texto
    assert "🛒 Mercado · R$ 150,00 · 83%" in texto
    rotulos = [b.rotulo for linha in r.saidas[0].botoes for b in linha]
    assert rotulos == ["🔕 Resumo semanal: desligado", "🔔 Fechamento do mês: ligado"]
    r = bot(de, acao="rp:ws")
    assert r.saidas[0].substitui
    assert "🔔 Resumo semanal: ligado" in [b.rotulo for linha in r.saidas[0].botoes for b in linha]
    with db.connect(banco.migrator) as m, m.transaction():
        row = m.execute(
            "select a.weekly_summary, a.monthly_summary from telegrana.accounts a"
            " join telegrana.account_members x on x.account_id = a.id"
            " join telegrana.user_channels u on u.user_id = x.user_id where u.external_id = %s",
            (de,),
        ).fetchone()
    assert row == (True, True)


def test_resumos_automaticos(conn: db.Connection, bot: Bot, com_dados: str, banco: Banco) -> None:
    de = com_dados
    bot(de, acao="rp:ws")  # liga o semanal
    bot(de, texto="aluguel 1500 todo dia 15")  # vence na semana seguinte
    bot(de, texto="luz 200 todo dia 14")
    with db.connect(banco.migrator) as m, m.transaction():
        m.execute(
            "update telegrana.fixed_items set created_at = '2026-09-20 12:00-03'"
            " where user_id = (select user_id from telegrana.user_channels where external_id = %s)",
            (de,),
        )
        m.execute(  # a luz de outubro já foi pulada: não aparece em "vence"
            "insert into telegrana.fixed_occurrences (account_id, fixed_item_id, due_date, status)"
            " select account_id, id, '2026-10-14', 'skipped' from telegrana.fixed_items"
            " where name = 'Luz' and user_id = (select user_id from telegrana.user_channels"
            " where external_id = %s)",
            (de,),
        )

    def rotina(momento: datetime) -> list[str]:
        saidas, falhas = relatorios.da_rotina(conn, "telegram", momento)
        assert falhas == 0
        return [s.texto for s in saidas if s.destino == de]

    [semana] = rotina(datetime(2026, 10, 11, 20, tzinfo=FUSO))  # domingo à noite
    assert semana.startswith(t.SEMANAL_TITULO.format(periodo="05/10 a 11/10"))
    assert "Gastos pagos: **R$ 50,00**" in semana
    assert "15/10 · Aluguel · R$ 1.500,00" in semana
    assert "Luz" not in semana
    assert rotina(datetime(2026, 10, 11, 20, tzinfo=FUSO)) == []  # não repete
    assert rotina(datetime(2026, 10, 12, 20, tzinfo=FUSO)) == []  # segunda: nada
    [mes] = rotina(datetime(2026, 11, 1, 9, tzinfo=FUSO))
    assert mes.startswith(t.MENSAL_TITULO.format(periodo="outubro/2026"))
    assert "Saiu: R$ 180,00" in mes
    assert "↓ 10% de gastos em relação a setembro." in mes


def test_fatura_sem_cartao_e_isolamento(bot: Bot, com_dados: str) -> None:
    de = com_dados
    assert primeira(bot(de, comando="fatura")) == t.SEM_CARTOES
    outra = conta(bot)
    r = bot(outra, texto="quanto gastei este mês?")
    assert t.RELATORIO_VAZIO in primeira(r)  # os gastos de `de` não aparecem para outra conta

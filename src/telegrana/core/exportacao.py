"""Exportação em PDF e XLSX (PLANO 6; S7, D048).

Mesmo `Pedido` dos relatórios (período, visão, filtros) → `exports.dados.Dados` montado
pelo SQL → PDF ou planilha, em memória, enviado como anexo da `Saida` (o canal manda o
arquivo). Pedido por `/exportar` (botões de período e formato) ou por frase ("me manda os
gastos de setembro em PDF").
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date
from typing import Any

from psycopg import sql

from telegrana.core import periodos, relatorios
from telegrana.core import textos as t
from telegrana.core.contexto import Contexto, agora
from telegrana.core.interpretacao import normaliza
from telegrana.core.mensagens import Arquivo, Botao, Entrada, Resultado, Saida
from telegrana.core.relatorios import Pedido
from telegrana.core.repositorio import Pessoa
from telegrana.exports.dados import CategoriaTotal, Dados, Linha
from telegrana.infra import db

PREFIXO = "ex:"
MAX_LINHAS = {"pdf": 400, "xlsx": 5000}
_FORMATO = re.compile(r"\b(pdf|planilha|excel|xlsx|exporta\w*|arquivo)\b")
_PLANILHA = re.compile(r"\b(planilha|excel|xlsx)\b")

_LINHAS = sql.SQL(
    "select {coluna}, coalesce(nullif(x.description, ''), ''), coalesce(c.name, ''),"
    " coalesce(m.name, ''), x.kind, x.amount_cents, x.installment_no, x.installments"
    " from telegrana.transactions x"
    " left join telegrana.categories c on c.id = x.category_id"
    " left join telegrana.payment_methods m on m.id = x.payment_method_id"
    " where x.deleted_at is null and x.kind <> 'transfer'"
    " and {coluna} between %(ini)s and %(fim)s{status}{tipo}{filtros}"
    " order by {coluna}, x.created_at limit %(max)s"
)
_COMPROMISSOS = sql.SQL(
    "select x.cash_on, coalesce(nullif(x.description, ''), ''), coalesce(c.name, ''),"
    " coalesce(m.name, ''), x.kind, x.amount_cents, x.installment_no, x.installments"
    " from telegrana.transactions x"
    " left join telegrana.categories c on c.id = x.category_id"
    " left join telegrana.payment_methods m on m.id = x.payment_method_id"
    " where x.deleted_at is null and x.status = 'planned' and x.kind <> 'transfer'"
    " and x.cash_on >= %(hoje)s order by x.cash_on, x.created_at limit 1000"
)


def _linha(r: tuple[Any, ...]) -> Linha:
    parcela = f"{r[6]}/{r[7]}" if r[6] and (r[7] or 1) > 1 else ""
    return Linha(
        r[0], r[1] or r[2], r[2], r[3], "Ganho" if r[4] == "income" else "Gasto", int(r[5]), parcela
    )


def dados(cur: Any, p: Pedido, hoje: date, formato: str) -> Dados:
    """Tudo calculado pelo SQL (regra de ouro 2)."""
    totais = relatorios.linhas(cur, replace(p, agrupar="nenhum"))
    por_categoria = relatorios.linhas(cur, replace(p, agrupar="categoria"))
    col = relatorios._COLUNA[p.visao]
    filtros, params = relatorios._filtros(p)
    maximo = MAX_LINHAS[formato]
    rows = cur.execute(
        _LINHAS.format(
            coluna=sql.SQL(col),
            status=sql.SQL(relatorios._STATUS[p.visao]),
            tipo=sql.SQL(relatorios._TIPO[p.tipo]),
            filtros=filtros,
        ),
        {**params, "max": maximo + 1},
    ).fetchall()
    compromissos = (
        cur.execute(_COMPROMISSOS, {"hoje": hoje}).fetchall() if formato == "xlsx" else []
    )
    return Dados(
        titulo=f"Relatório de {p.rotulo}",
        periodo=p.rotulo,
        visao=t.VISOES[p.visao].split(" ", 1)[1],  # sem o emoji
        gerado=hoje,
        entrou=sum(x.ganhos for x in totais),
        saiu=sum(x.gastos for x in totais),
        categorias=tuple(
            CategoriaTotal(x.grupo.split(" ", 1)[-1], x.gastos, x.ganhos) for x in por_categoria
        ),
        lancamentos=tuple(_linha(r) for r in rows[:maximo]),
        compromissos=tuple(_linha(r) for r in compromissos),
        truncado=len(rows) > maximo,
    )


def gera(d: Dados, p: Pedido, formato: str) -> Arquivo:
    """Desenha o arquivo FORA da transação do banco: gerar leva segundos, e o papel do app
    tem 10 s de limite para transação parada (bootstrap)."""
    if formato == "xlsx":
        from telegrana.exports import xlsx  # só aqui: openpyxl não pesa na partida do bot

        return Arquivo(d.nome_arquivo("xlsx", p.inicio), xlsx.TIPO, xlsx.gera(d))
    from telegrana.exports import pdf  # idem para o fpdf2

    return Arquivo(d.nome_arquivo("pdf", p.inicio), pdf.TIPO, pdf.gera(d))


def saida(d: Dados, p: Pedido, formato: str, destino: str | None = None) -> Saida:
    legenda = t.EXPORTACAO_LEGENDA.format(
        nome={"pdf": "PDF", "xlsx": "Planilha"}[formato], periodo=p.rotulo
    )
    return Saida(legenda, destino=destino, arquivo=gera(d, p, formato))


# ---------------------------------------------------------------------------
# Pedidos: /exportar (botões) e frase ("me manda os gastos de setembro em PDF")
# ---------------------------------------------------------------------------
def pede_arquivo(frase: str) -> bool:
    return bool(_FORMATO.search(normaliza(frase)))


def formato_da_frase(frase: str) -> str:
    return "xlsx" if _PLANILHA.search(normaliza(frase)) else "pdf"


_PERIODOS = {"ma": "este mês", "mp": "mês passado", "an": "este ano"}


def tela() -> Saida:
    linhas = []
    for chave, rotulo in (("ma", "Este mês"), ("mp", "Mês passado"), ("an", "Este ano")):
        linhas.append(
            (
                Botao(f"📄 {rotulo} · PDF", f"ex:{chave}:pdf"),
                Botao(f"📊 {rotulo} · Planilha", f"ex:{chave}:xlsx"),
            )
        )
    return Saida(t.EXPORTAR_TITULO, botoes=tuple(linhas))


def _completo(periodo: periodos.Periodo) -> Pedido:
    return Pedido("saldo", periodo.inicio, periodo.fim, periodo.rotulo, agrupar="nenhum")


def trata(conn: db.Connection, ctx: Contexto, e: Entrada, p: Pessoa) -> Resultado:
    r = Resultado(rotulo="exportacao", conta=p.account_id)
    if e.comando == "exportar":
        r.saidas.append(tela())
        return r
    partes = (e.acao or "").split(":")
    if len(partes) != 3 or partes[1] not in _PERIODOS or partes[2] not in MAX_LINHAS:
        return r.diz(t.USE_OS_BOTOES)
    hoje = agora().date()
    periodo = periodos.resolve(_PERIODOS[partes[1]], hoje)
    if periodo is None:  # não acontece: os textos são fixos
        return r.diz(t.USE_OS_BOTOES)
    r.rotulo = f"exportacao.{partes[1]}.{partes[2]}"
    pedido = _completo(periodo)
    with db.account_context(conn, p.account_id) as cur:
        d = dados(cur, pedido, hoje, partes[2])
    r.saidas.append(saida(d, pedido, partes[2]))  # já fora da transação
    return r


def por_frase(conn: db.Connection, ctx: Contexto, p: Pessoa, frase: str) -> Resultado:
    """ "Me manda os gastos de setembro em PDF": o pedido sai como nos relatórios (IA validada
    ou leitor do código); sem dizer gastos/ganhos, vai tudo (entradas e saídas)."""
    pedido, r = relatorios.interpreta(conn, ctx, p, frase)
    r.rotulo = r.rotulo.replace("relatorio.consulta", "exportacao.frase")
    if pedido is None:
        return r.diz(t.PERIODO_NAO_ENTENDI)
    n = normaliza(frase)
    if not re.search(r"\b(gast\w*|despesa\w*|ganh\w*|receb\w*|receita\w*)\b", n):
        pedido = replace(pedido, tipo="saldo")
    pedido = replace(pedido, agrupar="nenhum", limite=None)
    formato = formato_da_frase(frase)
    with db.account_context(conn, p.account_id) as cur:
        d = dados(cur, pedido, agora().date(), formato)
    r.saidas.append(saida(d, pedido, formato))  # já fora da transação
    return r

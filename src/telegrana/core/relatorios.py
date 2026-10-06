"""Relatórios em texto (PLANO 6; D047).

Pedido em linguagem natural → a IA devolve `ConsultaIA` (ou o leitor do código, sem IA) →
o código valida (período por `core.periodos`, categorias e cartões DA CONTA, listas fixas)
e monta o SQL só com fragmentos fixos e parâmetros (a IA nunca escreve SQL). Visões
(regime de caixa, PLANO 4.5): realizado = pago (`status = 'done'`, por `cash_on`); compra =
pela data da compra (`occurred_on`, pago ou não); compromissos = a pagar (`status =
'planned'`). Transferências nunca são gasto nem ganho; apagados nunca entram.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta
from typing import Any

import psycopg
from psycopg import sql

from telegrana.core import cartoes, faturas, fixos, lembretes, periodos, valores
from telegrana.core import lancamentos_repo as lrepo
from telegrana.core import seguranca as seg
from telegrana.core import textos as t
from telegrana.core.atalho import PALAVRAS, forma_em
from telegrana.core.contexto import Contexto, agora
from telegrana.core.entendimento import ErroExtracao, para_prompt
from telegrana.core.extracao import ConsultaIA
from telegrana.core.interpretacao import normaliza
from telegrana.core.mensagens import Botao, Entrada, Resultado, Saida, seguro
from telegrana.core.periodos import Periodo
from telegrana.core.repositorio import Pessoa
from telegrana.infra import db

log = logging.getLogger("telegrana.relatorios")

PREFIXO = "rp:"
COMANDOS = frozenset({"resumo", "fatura"})
TOP_CATEGORIAS = 5
LINHAS_MAX = 12
_FORMAS = {"pix": "pix", "debito": "debit", "dinheiro": "cash", "credito": "credit",
           "boleto": "boleto", "poupanca": "savings"}  # fmt: skip
LISTA_MAX = 25
MINUTOS_RELATORIO = 30  # "liste compra a compra" logo depois de um relatório detalha ESSE
_PEDE_LISTA = re.compile(
    r"\b(list\w*|detalh\w*|quais (foram|sao)|item a item|compra a compra|gasto a gasto"
    r"|um a um|uma a uma|um por um|uma por uma|cada (compra|gasto|lancamento))\b"
)
_PARECE_CONSULTA = re.compile(
    r"\b(quanto|qto|qnto|quantos) (que )?(eu )?(ja )?(gastei|ganhei|recebi|paguei|sobrou|entrou"
    r"|saiu|foi|gasto)\b|\b(meus|minhas) (gastos|ganhos|despesas|receitas)\b"
    r"|\brelatorio\b|\bextrato\b|\bonde (eu )?(mais )?gastei\b|\bem que (eu )?gastei\b"
    r"|\b(list\w*|detalh\w*) (os |as |meus |minhas )?(gastos|compras|lancamentos|ganhos)\b"
)


@dataclass(frozen=True, slots=True)
class Pedido:
    tipo: str  # gastos | ganhos | saldo
    inicio: date
    fim: date
    rotulo: str
    categorias: tuple[str, ...] = ()  # ids (texto) das categorias da conta
    nomes: tuple[str, ...] = ()  # "🛒 Mercado" (para o título)
    forma_kind: str | None = None
    cartao_forma: str | None = None  # id (texto) da forma de pagamento do cartão
    cartao_nome: str | None = None
    termo: str | None = None
    agrupar: str = "categoria"
    limite: int | None = None
    visao: str = "realizado"  # realizado | compra | compromissos

    def guarda(self) -> dict[str, Any]:
        d = asdict(self)
        d["inicio"], d["fim"] = self.inicio.isoformat(), self.fim.isoformat()
        return d

    @classmethod
    def de(cls, d: dict[str, Any]) -> Pedido:
        d = dict(d)
        d["inicio"], d["fim"] = date.fromisoformat(d["inicio"]), date.fromisoformat(d["fim"])
        for chave in ("categorias", "nomes"):
            d[chave] = tuple(d.get(chave) or ())
        return cls(**d)


@dataclass(frozen=True, slots=True)
class Linha:
    grupo: str
    ganhos: int
    gastos: int
    quantidade: int


# ---------------------------------------------------------------------------
# Pedido: da IA ou do leitor do código
# ---------------------------------------------------------------------------
def _periodo(texto: str | None, frase: str, hoje: date, visao: str) -> Periodo | None:
    futuro = visao == "compromissos"
    if texto:
        return periodos.resolve(texto, hoje, futuro=futuro)
    return periodos.resolve(frase, hoje, futuro=futuro) or periodos.resolve(
        None, hoje, futuro=futuro
    )


def do_codigo(
    texto: str, cats: list[lrepo.Categoria], cards: list[cartoes.Cartao], hoje: date
) -> Pedido | None:
    """Leitor sem IA (reserva): tipo, período, categoria, cartão/forma e agrupamento."""
    t_ = normaliza(texto)
    tipo = "gastos"
    if re.search(r"\b(ganhei|recebi|ganhos|receitas|entrou|salario)\b", t_):
        tipo = "ganhos"
    if re.search(r"\b(saldo|sobrou|sobra|entrou e saiu)\b", t_):
        tipo = "saldo"
    visao = (
        "compromissos"
        if re.search(r"\b(a pagar|vou pagar|parcelas futuras|vence|vencem)\b", t_)
        else "realizado"
    )
    if re.search(r"\bdata da compra\b|\bincluindo o cartao\b", t_):
        visao = "compra"
    agrupar = "lancamento" if _PEDE_LISTA.search(t_) else "nenhum"
    for padrao, grupo in (
        (r"\bmes a mes\b|\bpor mes\b", "mes"),
        (r"\bpor semana\b", "semana"),
        (r"\bpor dia\b|\bdia a dia\b", "dia"),
        (r"\bpor (cartao|forma)\b", "forma"),
        (r"\bpor categoria\b|\bonde\b|\bem que\b|\bem qu\b", "categoria"),
    ):
        if agrupar == "nenhum" and re.search(padrao, t_):
            agrupar = grupo
            break
    validas = [c for c in cats if c.ativa]
    escolhidas = [c for c in validas if f" {normaliza(c.nome)} " in f" {t_} "]
    if not escolhidas:
        chaves = {PALAVRAS[p] for p in t_.split() if p in PALAVRAS}
        escolhidas = [c for c in validas if c.code in chaves]
    if agrupar == "nenhum" and not escolhidas and tipo != "saldo":
        agrupar = "categoria"
    periodo = _periodo(None, texto, hoje, visao)
    if periodo is None:
        return None
    cartao = next((c for c in cards if f" {normaliza(c.nome)} " in f" {t_} "), None)
    forma, _ = forma_em(texto)
    return Pedido(
        tipo=tipo,
        inicio=periodo.inicio,
        fim=periodo.fim,
        rotulo=periodo.rotulo,
        categorias=tuple(str(c.id) for c in escolhidas),
        nomes=tuple(c.rotulo for c in escolhidas),
        forma_kind=None if cartao else (_FORMAS.get(forma or "") if forma else None),
        cartao_forma=str(cartao.forma_id) if cartao else None,
        cartao_nome=cartao.nome if cartao else None,
        agrupar=agrupar,
        visao=visao,
    )


def da_ia(
    c: ConsultaIA, texto: str, cats: list[lrepo.Categoria], cards: list[cartoes.Cartao], hoje: date
) -> Pedido | None:
    """Valida o que a IA devolveu: só categorias e cartões da conta; período pelo código."""
    periodo = _periodo(c.periodo_texto, texto, hoje, c.visao)
    if periodo is None:
        return None
    validas = {cat.chave: cat for cat in cats if cat.ativa}
    escolhidas = [validas[k] for k in c.categorias if k in validas]
    cartao = next((k for k in cards if c.cartao and cartoes.nome_bate(k.nome, c.cartao)), None)
    termo = normaliza(c.termo)[:30] if c.termo else None
    if termo and any(normaliza(cat.nome) == termo for cat in escolhidas):
        termo = None
    return Pedido(
        tipo=c.tipo,
        inicio=periodo.inicio,
        fim=periodo.fim,
        rotulo=periodo.rotulo,
        categorias=tuple(str(x.id) for x in escolhidas),
        nomes=tuple(x.rotulo for x in escolhidas),
        forma_kind=None if cartao else _FORMAS.get(c.forma_pagamento or ""),
        cartao_forma=str(cartao.forma_id) if cartao else None,
        cartao_nome=cartao.nome if cartao else None,
        termo=termo or None,
        agrupar=_agrupar_saldo(c.tipo, c.agrupar),
        limite=c.limite,
        visao=c.visao,
    )


def _agrupar_saldo(tipo: str, agrupar: str) -> str:
    """Saldo por categoria ou forma não faz sentido (só tem saída): vira o total."""
    return "nenhum" if tipo == "saldo" and agrupar in {"categoria", "forma"} else agrupar


# ---------------------------------------------------------------------------
# SQL (só fragmentos fixos; tudo que vem da pessoa vai como parâmetro)
# ---------------------------------------------------------------------------
_COLUNA = {"realizado": "x.cash_on", "compra": "x.occurred_on", "compromissos": "x.cash_on"}
_STATUS = {
    "realizado": " and x.status = 'done'",
    "compra": "",
    "compromissos": " and x.status = 'planned'",
}
_TIPO = {
    "gastos": " and x.kind = 'expense'",
    "ganhos": " and x.kind = 'income'",
    "saldo": " and x.kind in ('expense', 'income')",
}
_GRUPO = {
    "categoria": "coalesce(c.emoji || ' ' || c.name, '🏷️ Sem categoria')",
    "mes": "to_char({col}, 'YYYY-MM')",
    "semana": "to_char(date_trunc('week', {col}), 'YYYY-MM-DD')",
    "dia": "to_char({col}, 'YYYY-MM-DD')",
    "forma": "coalesce(m.emoji || ' ' || m.name, '—')",
    "lancamento": "''",  # a lista sai de `lancamentos()`; aqui só o total
    "nenhum": "''",
}
_ORDEM = {
    "categoria": "3 desc, 2 desc",
    "forma": "3 desc, 2 desc",
    "mes": "1",
    "semana": "1",
    "dia": "1",
    "lancamento": "1",
    "nenhum": "1",
}


def _filtros(p: Pedido) -> tuple[sql.Composed, dict[str, Any]]:
    partes: list[sql.SQL] = []
    params: dict[str, Any] = {"ini": p.inicio, "fim": p.fim}
    if p.categorias:
        partes.append(sql.SQL(" and x.category_id = any(%(cats)s::uuid[])"))
        params["cats"] = list(p.categorias)
    if p.cartao_forma:
        partes.append(sql.SQL(" and x.payment_method_id = %(cartao)s::uuid"))
        params["cartao"] = p.cartao_forma
    elif p.forma_kind:
        partes.append(sql.SQL(" and m.kind = %(kind)s"))
        params["kind"] = p.forma_kind
    if p.termo:
        partes.append(
            sql.SQL(
                " and (x.description ilike %(termo)s escape '\\'"
                " or x.original_text ilike %(termo)s escape '\\')"
            )
        )
        escapado = p.termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params["termo"] = f"%{escapado}%"
    return sql.Composed(partes), params


_LINHAS = sql.SQL(
    "select {grupo},"
    " coalesce(sum(x.amount_cents) filter (where x.kind = 'income'), 0)::bigint,"
    " coalesce(sum(x.amount_cents) filter (where x.kind = 'expense'), 0)::bigint,"
    " count(*)"
    " from telegrana.transactions x"
    " left join telegrana.categories c on c.id = x.category_id"
    " left join telegrana.payment_methods m on m.id = x.payment_method_id"
    " where x.deleted_at is null and x.kind <> 'transfer'"
    " and {coluna} between %(ini)s and %(fim)s{status}{tipo}{filtros}"
    " group by 1 order by {ordem}"
)
_EM_ABERTO = sql.SQL(
    "select coalesce(sum(x.amount_cents), 0)::bigint from telegrana.transactions x"
    " left join telegrana.payment_methods m on m.id = x.payment_method_id"
    " where x.deleted_at is null and x.kind = 'expense' and x.status = 'planned'"
    " and x.invoice_on is not null and x.occurred_on between %(ini)s and %(fim)s{filtros}"
)


def linhas(cur: Any, p: Pedido) -> list[Linha]:
    col = _COLUNA[p.visao]
    filtros, params = _filtros(p)
    consulta = _LINHAS.format(
        grupo=sql.SQL(_GRUPO[p.agrupar].format(col=col)),  # lista fixa
        coluna=sql.SQL(col),
        status=sql.SQL(_STATUS[p.visao]),
        tipo=sql.SQL(_TIPO[p.tipo]),
        filtros=filtros,
        ordem=sql.SQL(_ORDEM[p.agrupar]),
    )
    rows = cur.execute(consulta, params).fetchall()
    return [Linha(str(r[0]), int(r[1]), int(r[2]), int(r[3])) for r in rows]


_LANCAMENTOS = sql.SQL(
    "select {coluna}, coalesce(nullif(x.description, ''), c.name, ''), x.amount_cents, x.kind,"
    " coalesce(c.emoji, '🏷️'), coalesce(m.emoji || ' ' || m.name, ''), x.installment_no,"
    " x.installments"
    " from telegrana.transactions x"
    " left join telegrana.categories c on c.id = x.category_id"
    " left join telegrana.payment_methods m on m.id = x.payment_method_id"
    " where x.deleted_at is null and x.kind <> 'transfer'"
    " and {coluna} between %(ini)s and %(fim)s{status}{tipo}{filtros}"
    " order by {coluna} desc, x.created_at desc limit %(max)s"
)


@dataclass(frozen=True, slots=True)
class Item:
    dia: date
    descricao: str
    centavos: int
    tipo: str  # expense | income
    emoji: str
    forma: str
    parcela: int | None
    parcelas: int | None


def lancamentos(cur: Any, p: Pedido, maximo: int = LISTA_MAX) -> list[Item]:
    """Cada lançamento que forma o total do pedido (mais recentes primeiro)."""
    col = _COLUNA[p.visao]
    filtros, params = _filtros(p)
    consulta = _LANCAMENTOS.format(
        coluna=sql.SQL(col),
        status=sql.SQL(_STATUS[p.visao]),
        tipo=sql.SQL(_TIPO[p.tipo]),
        filtros=filtros,
    )
    rows = cur.execute(consulta, {**params, "max": maximo}).fetchall()
    return [Item(*r) for r in rows]


def cartao_em_aberto(cur: Any, p: Pedido) -> int:
    """Compras no cartão do período (data da compra) ainda não pagas: não entram no realizado."""
    if p.visao != "realizado" or p.tipo == "ganhos":
        return 0
    filtros, params = _filtros(p)
    row = cur.execute(_EM_ABERTO.format(filtros=filtros), params).fetchone()
    return int(row[0]) if row else 0


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------
def _grupo(p: Pedido, g: str) -> str:
    if p.agrupar == "mes":
        ano, mes = g.split("-")
        return periodos.nome_do_mes(int(ano), int(mes), curto=True)
    if p.agrupar == "semana":
        return f"semana de {date.fromisoformat(g):%d/%m}"
    if p.agrupar == "dia":
        return f"{date.fromisoformat(g):%d/%m}"
    return g


def titulo(p: Pedido) -> str:
    nome = {"gastos": "Gastos", "ganhos": "Ganhos", "saldo": "Saldo"}[p.tipo]
    detalhes = []
    if p.nomes:
        detalhes.append("com " + ", ".join(p.nomes))
    if p.termo:
        detalhes.append(f"em «{seguro(p.termo, 30)}»")
    if p.cartao_nome:
        detalhes.append(f"no 💳 {seguro(p.cartao_nome, 30)}")
    elif p.forma_kind:
        detalhes.append("no " + {v: k for k, v in _FORMAS.items()}.get(p.forma_kind, p.forma_kind))
    extra = (" " + " ".join(detalhes)) if detalhes else ""
    return f"📊 **{nome}{extra}** · {p.rotulo}"


def texto_lista(p: Pedido, ls: list[Linha], itens: list[Item], em_aberto: int = 0) -> str:
    """O relatório item a item: data · descrição · valor · forma."""
    cab = [titulo(p), t.VISOES[p.visao], ""]
    if not itens:
        return "\n".join([*cab, t.RELATORIO_VAZIO])
    corpo = []
    for i in itens:
        sinal = "+" if i.tipo == "income" and p.tipo == "saldo" else ""
        parcela = f" ({i.parcela}/{i.parcelas})" if i.parcela and (i.parcelas or 1) > 1 else ""
        forma = f" · {i.forma}" if i.forma else ""
        descricao = seguro(i.descricao, 40)
        corpo.append(
            f"{i.dia:%d/%m} · {i.emoji} {descricao}{parcela} · {sinal}{valores.em_reais(i.centavos)}{forma}"
        )
    quantidade = sum(x.quantidade for x in ls)
    if quantidade > len(itens):
        corpo.append(t.LISTA_MAIS.format(n=quantidade - len(itens)))
    ganhos = sum(x.ganhos for x in ls)
    gastos = sum(x.gastos for x in ls)
    if p.tipo == "saldo":
        total = f"**Saldo: {_sinal(ganhos - gastos)}**"
    else:
        total = f"**Total: {valores.em_reais(ganhos if p.tipo == 'ganhos' else gastos)}**"
    rodape = (
        [t.RELATORIO_CARTAO_ABERTO.format(valor=valores.em_reais(em_aberto))] if em_aberto else []
    )
    return "\n".join([*cab, *corpo, "", total, *(["", *rodape] if rodape else [])])


def texto(p: Pedido, ls: list[Linha], em_aberto: int = 0) -> str:
    cab = [titulo(p), t.VISOES[p.visao]]
    ganhos = sum(x.ganhos for x in ls)
    gastos = sum(x.gastos for x in ls)
    if not ls or (ganhos == 0 and gastos == 0):
        corpo = [t.RELATORIO_VAZIO]
    elif p.tipo == "saldo":
        corpo = []
        if p.agrupar != "nenhum" and len(ls) > 1:
            for x in ls[:LINHAS_MAX]:
                corpo.append(f"{_grupo(p, x.grupo)} · {_sinal(x.ganhos - x.gastos)}")
            corpo.append("")
        corpo += [
            f"Entrou: {valores.em_reais(ganhos)}",
            f"Saiu: {valores.em_reais(gastos)}",
            f"**Saldo: {_sinal(ganhos - gastos)}**",
        ]
    else:

        def valor(x: Linha) -> int:
            return x.ganhos if p.tipo == "ganhos" else x.gastos

        total = ganhos if p.tipo == "ganhos" else gastos
        corpo = []
        if p.agrupar != "nenhum":
            limite = p.limite or LINHAS_MAX
            mostrar = [x for x in ls if valor(x)][:limite]
            porcento = p.agrupar in {"categoria", "forma"}
            for x in mostrar:
                pct = f" · {round(100 * valor(x) / total)}%" if porcento and total else ""
                corpo.append(f"{_grupo(p, x.grupo)} · {valores.em_reais(valor(x))}{pct}")
            resto = len([x for x in ls if valor(x)]) - len(mostrar)
            if resto > 0:
                corpo.append(t.RELATORIO_MAIS.format(n=resto))
            corpo.append("")
        corpo.append(f"**Total: {valores.em_reais(total)}**")
    rodape = (
        [t.RELATORIO_CARTAO_ABERTO.format(valor=valores.em_reais(em_aberto))] if em_aberto else []
    )
    return "\n".join([*cab, "", *corpo, *(["", *rodape] if rodape else [])])


def _sinal(centavos: int) -> str:
    return ("-" if centavos < 0 else "+") + valores.em_reais(abs(centavos))


# ---------------------------------------------------------------------------
# Consulta (mensagem livre)
# ---------------------------------------------------------------------------
def parece_consulta(frase: str) -> bool:
    return bool(_PARECE_CONSULTA.search(normaliza(frase)))


def consulta(conn: db.Connection, ctx: Contexto, p: Pessoa, frase: str) -> Resultado:
    r = Resultado(rotulo="relatorio.consulta", conta=p.account_id)
    hoje = agora().date()
    with db.account_context(conn, p.account_id) as cur:
        cats = lrepo.categorias(cur)
        cards = cartoes.lista(cur)
    pedido: Pedido | None = None
    pergunta = getattr(ctx.extrator, "consulta", None)
    if pergunta is not None:  # IA fora da transação do banco
        try:
            ativas = [c.para_ia() for c in cats if c.ativa]
            ia, modelo = pergunta(frase, para_prompt(ativas), hoje)
            pedido = da_ia(ia, frase, cats, cards, hoje)
            r.rotulo += ".ia"
            _conta_uso(conn, ctx, hoje, modelo, r)
        except ErroExtracao as exc:
            r.rotulo += ".ia_limite" if exc.limite else ".ia_falhou"
    if pedido is None:
        pedido = do_codigo(frase, cats, cards, hoje)
    if pedido is None:
        return r.diz(t.PERIODO_NAO_ENTENDI)
    with db.account_context(conn, p.account_id) as cur:
        return _responde(cur, p, pedido, r)


def _conta_uso(
    conn: db.Connection, ctx: Contexto, hoje: date, modelo: str | None, r: Resultado
) -> None:
    from telegrana.core import lancamentos  # import tardio: lancamentos usa este módulo

    uso = getattr(ctx.extrator, "ultimo_uso", None)
    if uso is not None:
        tokens = max(0, uso.tokens_entrada - uso.tokens_em_cache) + uso.tokens_saida
        lancamentos._conta_uso(conn, hoje, modelo, tokens, r)


def _responde(cur: Any, p: Pessoa, pedido: Pedido, r: Resultado) -> Resultado:
    """Responde e guarda o pedido: "liste compra a compra" logo depois detalha ESTE (e os
    botões 📋 Ver lançamentos / 💳 Incluir compras no cartão usam o mesmo rascunho)."""
    ls = linhas(cur, pedido)
    aberto = cartao_em_aberto(cur, pedido)
    cur.execute(
        "delete from telegrana.pending_entries where user_id = %s and pendencia = 'consulta'",
        (p.user_id,),
    )
    rascunho = seg.curto(
        lrepo.cria_rascunho(cur, p.account_id, p.user_id, pedido.guarda(), "consulta")
    )
    botoes: list[Botao] = []
    tem_valor = any(x.ganhos or x.gastos for x in ls)
    if pedido.agrupar == "lancamento":
        corpo = texto_lista(pedido, ls, lancamentos(cur, pedido), aberto)
    else:
        corpo = texto(pedido, ls, aberto)
        if tem_valor:
            botoes.append(Botao(t.BOTAO_VER_LANCAMENTOS, f"rp:it:{rascunho}"))
    if aberto:
        botoes.append(Botao("💳 Incluir compras no cartão", f"rp:cp:{rascunho}"))
    return r.diz(corpo, botoes=tuple((b,) for b in botoes))


def ultimo_pedido(cur: Any, user_id: uuid.UUID) -> Pedido | None:
    row = cur.execute(
        "select data from telegrana.pending_entries where user_id = %s and pendencia = 'consulta'"
        " and created_at > now() - make_interval(mins => %s) order by created_at desc limit 1",
        (user_id, MINUTOS_RELATORIO),
    ).fetchone()
    try:
        return Pedido.de(dict(row[0])) if row else None
    except KeyError, TypeError, ValueError:
        return None


def pede_lista(frase: str) -> bool:
    """Pedido de detalhe SEM números ("liste compra a compra", "quais foram?"). Com número
    ("lista de compras 50 no mercado") é lançamento ou um relatório novo, não o detalhe."""
    return bool(_PEDE_LISTA.search(normaliza(frase))) and not any(c.isdigit() for c in frase)


def detalha_ultimo(conn: db.Connection, p: Pessoa) -> Resultado | None:
    """ "Liste compra a compra" logo depois de um relatório: os lançamentos DESSE relatório."""
    with db.account_context(conn, p.account_id) as cur:
        anterior = ultimo_pedido(cur, p.user_id)
        if anterior is None:
            return None
        r = Resultado(rotulo="relatorio.lista", conta=p.account_id)
        return _responde(cur, p, replace(anterior, agrupar="lancamento"), r)


# ---------------------------------------------------------------------------
# /resumo, /fatura e botões
# ---------------------------------------------------------------------------
def _preferencias(cur: Any, account_id: uuid.UUID) -> tuple[bool, bool]:
    row = cur.execute(
        "select weekly_summary, monthly_summary from telegrana.accounts where id = %s",
        (account_id,),
    ).fetchone()
    return (bool(row[0]), bool(row[1])) if row else (False, True)


def _bloco_mes(cur: Any, periodo: Periodo) -> list[str]:
    base = Pedido("gastos", periodo.inicio, periodo.fim, periodo.rotulo)
    todos = linhas(cur, replace(base, tipo="saldo", agrupar="nenhum"))
    ganhos = sum(x.ganhos for x in todos)
    gastos = sum(x.gastos for x in todos)
    linhas_ = [
        f"Entrou: {valores.em_reais(ganhos)}",
        f"Saiu: {valores.em_reais(gastos)}",
        f"**Saldo: {_sinal(ganhos - gastos)}**",
    ]
    cats = [x for x in linhas(cur, base) if x.gastos][:TOP_CATEGORIAS]
    if cats and gastos:
        linhas_ += ["", t.RESUMO_TOP]
        linhas_ += [
            f"{x.grupo} · {valores.em_reais(x.gastos)} · {round(100 * x.gastos / gastos)}%"
            for x in cats
        ]
    return linhas_


def tela_resumo(cur: Any, account_id: uuid.UUID, hoje: date, *, substitui: bool = False) -> Saida:
    periodo = periodos.mes_atual(hoje)
    semanal, mensal = _preferencias(cur, account_id)
    corpo = [t.RESUMO_TITULO.format(periodo=periodo.rotulo), t.VISOES["realizado"], ""]
    corpo += _bloco_mes(cur, periodo)
    botoes = (
        (
            Botao(
                ("🔔" if semanal else "🔕")
                + " Resumo semanal: "
                + ("ligado" if semanal else "desligado"),
                "rp:ws",
            ),
        ),
        (
            Botao(
                ("🔔" if mensal else "🔕")
                + " Fechamento do mês: "
                + ("ligado" if mensal else "desligado"),
                "rp:ms",
            ),
        ),
    )
    return Saida("\n".join(corpo), botoes=botoes, substitui=substitui)


def trata(conn: db.Connection, ctx: Contexto, e: Entrada, p: Pessoa) -> Resultado:
    r = Resultado(
        rotulo=f"relatorio.{e.comando or (e.acao or '').replace(':', '.')}", conta=p.account_id
    )
    hoje = agora().date()
    with db.account_context(conn, p.account_id) as cur:
        if e.comando == "resumo":
            r.saidas.append(tela_resumo(cur, p.account_id, hoje))
            return r
        if e.comando == "fatura":
            todos = cartoes.lista(cur)
            if not todos:
                return r.diz(t.SEM_CARTOES)
            for c in todos:
                vencimento = faturas.a_pagar(cur, c, hoje)
                if vencimento is not None:
                    r.saidas.append(faturas.tela(cur, c, vencimento))
            return r if r.saidas else r.diz(t.SEM_FATURA_ABERTA)
        partes = (e.acao or "").split(":")
        if partes in (["rp", "ws"], ["rp", "ms"]):
            coluna = "weekly_summary" if partes[1] == "ws" else "monthly_summary"
            cur.execute(
                sql.SQL("update telegrana.accounts set {c} = not {c} where id = %s").format(
                    c=sql.Identifier(coluna)
                ),
                (p.account_id,),
            )
            r.saidas.append(tela_resumo(cur, p.account_id, hoje, substitui=True))
            return r
        if len(partes) == 3 and partes[1] in {"cp", "it"}:
            rascunho_id = seg.longo(partes[2])
            achado = lrepo.rascunho(cur, rascunho_id) if rascunho_id else None
            if (
                achado is None or achado[1] != "consulta"
            ):  # RLS: rascunho de outra conta não aparece
                return r.diz(t.RASCUNHO_SUMIU)
            pedido = Pedido.de(achado[0])
            if partes[1] == "cp":
                pedido = replace(pedido, visao="compra")
            else:
                pedido = replace(pedido, agrupar="lancamento")
            return _responde(cur, p, pedido, r)
    return r.diz(t.USE_OS_BOTOES)


# ---------------------------------------------------------------------------
# Resumos automáticos (rotina): semanal (domingo, noite) e fechamento do mês (dia 1, manhã)
# ---------------------------------------------------------------------------
def semanal(cur: Any, hoje: date) -> str:
    inicio = hoje - timedelta(days=hoje.weekday())
    periodo = Periodo(inicio, hoje, f"{inicio:%d/%m} a {hoje:%d/%m}")
    base = Pedido("gastos", periodo.inicio, periodo.fim, periodo.rotulo)
    ls = [x for x in linhas(cur, base) if x.gastos]
    total = sum(x.gastos for x in ls)
    corpo = [
        t.SEMANAL_TITULO.format(periodo=periodo.rotulo),
        f"Gastos pagos: **{valores.em_reais(total)}**",
    ]
    if ls:
        corpo += [f"{x.grupo} · {valores.em_reais(x.gastos)}" for x in ls[:3]]
    proximos = _vencimentos(cur, hoje + timedelta(days=1), hoje + timedelta(days=7))
    corpo += ["", t.SEMANAL_PROXIMOS if proximos else t.SEMANAL_NADA_VENCE, *proximos]
    return "\n".join(corpo)


def _vencimentos(cur: Any, inicio: date, fim: date) -> list[str]:
    itens: list[tuple[date, str]] = []
    desde = inicio - timedelta(days=70)
    resolvidos = lembretes._resolvidos(cur, desde)
    pagamentos = lembretes._pagamentos(cur, desde)
    for f in fixos.lista(cur):
        if not f.ativo:
            continue
        _, proximo = lembretes.vencimentos_perto(f.dia, inicio)
        feito = lembretes.resolvido(proximo, resolvidos.get(f.id, set()), pagamentos.get(f.id, []))
        if inicio <= proximo <= fim and not feito:  # pago ou pulado não aparece
            itens.append(
                (
                    proximo,
                    f"{proximo:%d/%m} · {seguro(f.nome, 30)} · {valores.em_reais(f.centavos)}",
                )
            )
    for c in cartoes.lista(cur):
        for v in faturas.abertas(cur, c):
            if inicio <= v <= fim:
                total = sum(i.centavos for i in faturas.itens(cur, c, v))
                itens.append(
                    (
                        v,
                        f"{v:%d/%m} · 🧾 Fatura do {seguro(c.nome, 30)} · {valores.em_reais(total)}",
                    )
                )
    return [texto for _, texto in sorted(itens)]


def mensal(cur: Any, hoje: date) -> str:
    ano, mes = periodos._soma_meses(hoje.year, hoje.month, -1)
    periodo = periodos.mes_inteiro(ano, mes)
    corpo = [t.MENSAL_TITULO.format(periodo=periodo.rotulo), ""]
    corpo += _bloco_mes(cur, periodo)
    anterior = periodos.mes_inteiro(*periodos._soma_meses(ano, mes, -1))
    gasto = sum(
        x.gastos
        for x in linhas(cur, Pedido("gastos", periodo.inicio, periodo.fim, "", agrupar="nenhum"))
    )
    antes = sum(
        x.gastos
        for x in linhas(cur, Pedido("gastos", anterior.inicio, anterior.fim, "", agrupar="nenhum"))
    )
    if antes and gasto:
        variacao = round(100 * (gasto - antes) / antes)
        seta = "↑" if variacao > 0 else "↓" if variacao < 0 else "="
        corpo += [
            "",
            t.MENSAL_COMPARA.format(
                seta=seta, pct=abs(variacao), mes=anterior.rotulo.split("/")[0]
            ),
        ]
    return "\n".join(corpo)


def da_rotina(conn: db.Connection, canal: str, momento: datetime) -> tuple[list[Saida], int]:
    """Resumo semanal (domingo, 20:00) e fechamento do mês (dia 1, 09:00), um por período."""
    hoje, horario = momento.date(), lembretes.horario_de(momento)
    tarefas = []
    if hoje.weekday() == 6 and horario == "evening":
        tarefas.append(("weekly", hoje - timedelta(days=6), semanal))
    if hoje.day == 1 and horario == "morning":
        ano, mes = periodos._soma_meses(hoje.year, hoje.month, -1)
        tarefas.append(("monthly", date(ano, mes, 1), mensal))
    saidas: list[Saida] = []
    falhas = 0
    for tipo, inicio, gera in tarefas:
        with conn.transaction():
            contas = [r[0] for r in conn.execute(
                "select o_account_id from telegrana.accounts_for_summaries(%s)", (tipo,)
            ).fetchall()]  # fmt: skip
        for account_id in contas:
            try:
                with db.account_context(conn, account_id) as cur:
                    destino = lembretes.destino(cur, canal)
                    if destino is None:
                        continue
                    row = cur.execute(
                        "insert into telegrana.summary_sends (account_id, kind, period_start)"
                        " values (%s, %s, %s) on conflict do nothing returning id",
                        (account_id, tipo, inicio),
                    ).fetchone()
                    if row is not None:  # gravado antes de enviar: nunca repete
                        saidas.append(Saida(gera(cur, hoje), destino=destino))
            except psycopg.Error as exc:
                falhas += 1
                log.error("relatorios.conta_falhou", extra={"erro": type(exc).__name__})
    return saidas, falhas

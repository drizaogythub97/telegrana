"""Faturas de cartão: avisos, pagamento e estorno (PLANO 4.5; D045, D046).

A fatura é (cartão, vencimento): as parcelas previstas com aquele `invoice_on`. Pagar a
fatura faz as parcelas virarem gasto REALIZADO na data do pagamento, cada uma com a própria
categoria (regime de caixa). Pagamento parcial: cada item é pago na mesma proporção e o
resto de cada um vai para a fatura seguinte ("Saldo anterior", mesma categoria). Pagamento
acima do total: a diferença é um gasto em Encargos e juros. Estorno: abate da compra.
Tudo dentro de `db.account_context` (RLS forçado).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from telegrana.core import cartoes, fixos, valores
from telegrana.core import seguranca as seg
from telegrana.core import textos as t
from telegrana.core.cartoes import Cartao
from telegrana.core.contexto import Contexto, agora
from telegrana.core.mensagens import Botao, Entrada, Resultado, Saida, seguro
from telegrana.core.repositorio import Pessoa
from telegrana.infra import db

PREFIXO = "fa:"
PERGUNTAS = frozenset({"fa_valor"})
MARCA = "🧾"  # 2ª linha da pergunta de valor: "🧾 <cartão> · dd/mm/aaaa"
ITENS_NA_TELA = 6
JANELA = 800  # dias: fatura de compra em 12x ou mais pode vencer daqui a um ano


@dataclass(frozen=True, slots=True)
class Item:
    id: uuid.UUID
    centavos: int
    categoria_id: uuid.UUID | None
    descricao: str | None
    parcela: int | None
    parcelas: int | None
    compra: date


# ---------------------------------------------------------------------------
# Regras (puras)
# ---------------------------------------------------------------------------
def fechamento(vencimento: date, fecha: int, vence: int) -> date:
    """Dia em que fecha a fatura que vence em `vencimento`."""
    ano, mes = vencimento.year, vencimento.month
    if vence <= fecha:
        ano, mes = cartoes._soma_meses(ano, mes, -1)
    return fixos.vencimento(fecha, ano, mes)


def seguinte(vencimento: date, vence: int) -> date:
    """Vencimento da fatura do mês seguinte."""
    return fixos.vencimento(vence, *cartoes._soma_meses(vencimento.year, vencimento.month, 1))


def rateio(itens: list[int], pago: int) -> list[int]:
    """Quanto de cada item foi pago, na proporção, somando exatamente `pago` (D046)."""
    total = sum(itens)
    if pago >= total:
        return list(itens)
    base = [v * pago // total for v in itens]
    sobra = pago - sum(base)
    ordem = sorted(
        range(len(itens)), key=lambda i: (itens[i] * pago % total, itens[i]), reverse=True
    )
    for i in ordem[:sobra]:
        base[i] += 1
    return base


def regra(c: Cartao, vencimento: date, hoje: date, horario: str) -> str | None:
    """Que aviso cabe hoje para a fatura que vence em `vencimento` (no máximo um)."""
    if c.horario not in {horario, "both"}:
        return None
    if hoje == vencimento:
        return "on_day" if c.no_dia else None
    if hoje == fechamento(vencimento, c.fecha, c.vence):
        return "closed"
    if hoje == vencimento - timedelta(days=1):
        return "before" if c.antes else None
    if vencimento < hoje < seguinte(vencimento, c.vence):
        return "after" if c.depois else None
    return None


# ---------------------------------------------------------------------------
# SQL (fixo, parametrizado)
# ---------------------------------------------------------------------------
def itens(cur: Any, c: Cartao, vencimento: date) -> list[Item]:
    rows = cur.execute(
        "select id, amount_cents, category_id, description, installment_no, installments,"
        " occurred_on from telegrana.transactions"
        " where payment_method_id = %s and invoice_on = %s and status = 'planned'"
        " and deleted_at is null order by occurred_on, created_at",
        (c.forma_id, vencimento),
    ).fetchall()
    return [Item(*r) for r in rows]


def abertas(cur: Any, c: Cartao) -> list[date]:
    rows = cur.execute(
        "select distinct invoice_on from telegrana.transactions"
        " where payment_method_id = %s and status = 'planned' and deleted_at is null"
        " and invoice_on is not null order by invoice_on",
        (c.forma_id,),
    ).fetchall()
    return [r[0] for r in rows]


def a_pagar(cur: Any, c: Cartao, hoje: date) -> date | None:
    """A fatura que a pessoa quer pagar: a mais antiga já fechada; senão, a aberta."""
    todas = abertas(cur, c)
    fechadas = [v for v in todas if fechamento(v, c.fecha, c.vence) <= hoje]
    escolhidas = fechadas or todas
    return escolhidas[0] if escolhidas else None


def _paga_em(cur: Any, c: Cartao, vencimento: date) -> date | None:
    row = cur.execute(
        "select paid_on from telegrana.card_invoices where card_id = %s and due_date = %s",
        (c.id, vencimento),
    ).fetchone()
    return row[0] if row else None


def _emojis(cur: Any) -> dict[uuid.UUID, tuple[str, str]]:
    return {
        r[0]: (r[1], r[2]) for r in cur.execute("select id, emoji, name from telegrana.categories")
    }


def _encargos(cur: Any) -> uuid.UUID | None:
    row = cur.execute("select id from telegrana.categories where code = 'encargos'").fetchone()
    return row[0] if row else None


def paga(cur: Any, p: Pessoa, c: Cartao, vencimento: date, valor: int | None, hoje: date) -> str:
    """Paga a fatura (total, parcial ou acima do total). Uma vez só por cartão e vencimento."""
    lista = itens(cur, c, vencimento)
    if not lista:
        return t.FATURA_VAZIA.format(nome=seguro(c.nome, 30))
    total = sum(i.centavos for i in lista)
    pago = valor or total
    row = cur.execute(
        "insert into telegrana.card_invoices (account_id, card_id, due_date, total_cents,"
        " paid_cents, paid_on) values (%s, %s, %s, %s, %s, %s)"
        " on conflict (account_id, card_id, due_date) do nothing returning id",
        (p.account_id, c.id, vencimento, total, pago, hoje),
    ).fetchone()
    if row is None:
        return t.FATURA_JA_PAGA.format(nome=seguro(c.nome, 30), data=f"{vencimento:%d/%m}")
    proxima = seguinte(vencimento, c.vence)
    for item, parte in zip(lista, rateio([i.centavos for i in lista], pago), strict=True):
        resto = item.centavos - parte
        if parte == 0:  # nada pago deste item: ele inteiro vai para a próxima fatura
            cur.execute(
                "update telegrana.transactions set invoice_on = %s, cash_on = %s,"
                " updated_at = now() where id = %s",
                (proxima, proxima, item.id),
            )
            continue
        cur.execute(
            "update telegrana.transactions set amount_cents = %s, status = 'done', cash_on = %s,"
            " updated_at = now() where id = %s",
            (parte, hoje, item.id),
        )
        if resto > 0:
            descricao = f"Saldo anterior · {item.descricao or ''}".rstrip(" ·")[:200]
            _insere(cur, p, c, resto, item.categoria_id, descricao, item.compra, proxima, "planned")
    if pago > total:  # pagou a mais: juros, multa, encargos
        _insere(cur, p, c, pago - total, _encargos(cur), t.DESCRICAO_ENCARGOS, hoje, hoje, "done")
    nome = seguro(c.nome, 30)
    if pago < total:
        return t.FATURA_PAGA_PARCIAL.format(
            nome=nome,
            pago=valores.em_reais(pago),
            resto=valores.em_reais(total - pago),
            data=f"{proxima:%d/%m}",
        )
    extra = t.FATURA_ENCARGOS.format(valor=valores.em_reais(pago - total)) if pago > total else ""
    return t.FATURA_PAGA.format(nome=nome, pago=valores.em_reais(pago), n=len(lista)) + extra


def _insere(
    cur: Any,
    p: Pessoa,
    c: Cartao,
    centavos: int,
    categoria_id: uuid.UUID | None,
    descricao: str,
    compra: date,
    caixa: date,
    status: str,
) -> None:
    cur.execute(
        "insert into telegrana.transactions (account_id, user_id, kind, amount_cents,"
        " category_id, payment_method_id, occurred_on, cash_on, description, source,"
        " original_text, status, invoice_on)"
        " values (%s, %s, 'expense', %s, %s, %s, %s, %s, %s, 'invoice', '', %s, %s)",
        (
            p.account_id,
            p.user_id,
            centavos,
            categoria_id,
            c.forma_id,
            compra,
            caixa,
            descricao,
            status,
            caixa if status == "planned" else None,
        ),
    )


# ---------------------------------------------------------------------------
# Telas
# ---------------------------------------------------------------------------
def _chave(c: Cartao, vencimento: date) -> str:
    return f"{seg.curto(c.id)}:{vencimento:%Y%m%d}"


def _linha(i: Item, emojis: dict[uuid.UUID, tuple[str, str]]) -> str:
    emoji, nome = (
        emojis.get(i.categoria_id, ("🏷️", "Sem categoria")) if i.categoria_id else ("🏷️", "")
    )
    texto = seguro(i.descricao or nome, 40)
    parcela = f" ({i.parcela}/{i.parcelas})" if i.parcela and (i.parcelas or 1) > 1 else ""
    return f"{emoji} {valores.em_reais(i.centavos)} · {texto}{parcela}"


def tela(
    cur: Any,
    c: Cartao,
    vencimento: date,
    *,
    titulo: str | None = None,
    todos: bool = False,
    valor: int | None = None,
    destino: str | None = None,
) -> Saida:
    lista = itens(cur, c, vencimento)
    total = sum(i.centavos for i in lista)
    emojis = _emojis(cur)
    nome = seguro(c.nome, 30)
    cabecalho = titulo or t.FATURA_TITULO.format(nome=nome, data=f"{vencimento:%d/%m}")
    mostrar = lista if todos else lista[:ITENS_NA_TELA]
    linhas = [cabecalho, f"Total: **{valores.em_reais(total)}**", ""]
    linhas += [_linha(i, emojis) for i in mostrar]
    if len(lista) > len(mostrar):
        linhas.append(t.FATURA_MAIS.format(n=len(lista) - len(mostrar)))
    chave = _chave(c, vencimento)
    if valor and valor != total:
        pagar = (
            Botao(f"✅ Paguei {valores.em_reais(valor)}", f"fa:pv:{chave}:{valor}"),
            Botao(f"✅ Paguei {valores.em_reais(total)}", f"fa:pg:{chave}"),
        )
    else:
        pagar = (
            Botao(f"✅ Paguei {valores.em_reais(total)}", f"fa:pg:{chave}"),
            Botao("✏️ Outro valor", f"fa:ov:{chave}"),
        )
    botoes: list[tuple[Botao, ...]] = [pagar]
    if len(lista) > len(mostrar):
        botoes.append((Botao("📋 Ver todos os itens", f"fa:it:{chave}"),))
    return Saida("\n".join(linhas), destino=destino, botoes=tuple(botoes))


# ---------------------------------------------------------------------------
# Avisos da rotina (fechou, véspera, no dia, atrasada)
# ---------------------------------------------------------------------------
_TITULOS = {
    "closed": t.FATURA_FECHOU,
    "before": t.FATURA_VENCE_AMANHA,
    "on_day": t.FATURA_VENCE_HOJE,
    "after": t.FATURA_ATRASADA,
}


def da_conta(
    cur: Any, account_id: uuid.UUID, destino: str, hoje: date, horario: str
) -> list[Saida]:
    saidas = []
    for c in cartoes.lista(cur):
        for vencimento in abertas(cur, c):
            qual = regra(c, vencimento, hoje, horario)
            if qual is None or _paga_em(cur, c, vencimento) is not None:
                continue
            row = cur.execute(
                "insert into telegrana.invoice_notices (account_id, card_id, due_date, rule,"
                " sent_on, slot) values (%s, %s, %s, %s, %s, %s)"
                " on conflict (account_id, card_id, sent_on, slot) do nothing returning id",
                (account_id, c.id, vencimento, qual, hoje, horario),
            ).fetchone()
            if row is not None:  # gravado antes de enviar: nunca repete
                titulo = _TITULOS[qual].format(nome=seguro(c.nome, 30), data=f"{vencimento:%d/%m}")
                saidas.append(tela(cur, c, vencimento, titulo=titulo, destino=destino))
            break  # um aviso por cartão por vez
    return saidas


# ---------------------------------------------------------------------------
# Texto: "paguei a fatura do nubank (1.500)" e "estorno de 80 no inter"
# ---------------------------------------------------------------------------
def pede_pagamento(conn: db.Connection, p: Pessoa, texto: str) -> Resultado:
    """Mostra a fatura com os botões de pagamento (nada é pago sem o toque)."""
    r = Resultado(rotulo="fatura.pagar", conta=p.account_id)
    hoje = agora().date()
    valor = valores.interpreta(re.sub(r"\b\d{1,2}/\d{1,2}\b", " ", texto)).centavos
    with db.account_context(conn, p.account_id) as cur:
        todos = cartoes.lista(cur)
        c = cartoes.no_texto(cur, texto) or (todos[0] if len(todos) == 1 else None)
        if not todos:
            return r.diz(t.SEM_CARTOES)
        if c is None:
            botoes = [
                Botao(f"{cartoes.EMOJI} {x.nome[:24]}", f"fa:pc:{seg.curto(x.id)}") for x in todos
            ]
            return r.diz(
                t.QUAL_FATURA,
                botoes=tuple(tuple(botoes[k : k + 2]) for k in range(0, len(botoes), 2)),
            )
        vencimento = a_pagar(cur, c, hoje)
        if vencimento is None:
            return r.diz(t.FATURA_VAZIA.format(nome=seguro(c.nome, 30)))
        r.saidas.append(tela(cur, c, vencimento, valor=valor))
    return r


_ESTORNO = re.compile(r"\bestorn\w*|\breembols\w*|\bdevolv\w* (o )?dinheiro")


def parece_estorno(texto: str) -> bool:
    from telegrana.core.interpretacao import normaliza

    return bool(_ESTORNO.search(normaliza(texto)))


def _candidatas(cur: Any, c: Cartao | None, valor: int) -> list[tuple[uuid.UUID, int, str]]:
    """Compras no cartão com parcelas ainda previstas: (compra, total, descrição)."""
    rows = cur.execute(
        "select x.purchase_id, sum(x.amount_cents)::bigint,"
        " max(coalesce(x.description, '')), max(x.occurred_on)"
        " from telegrana.transactions x"
        " join telegrana.cards k on k.payment_method_id = x.payment_method_id"
        " where x.purchase_id is not null and x.deleted_at is null"
        " and (%(forma)s::uuid is null or x.payment_method_id = %(forma)s::uuid)"
        " group by x.purchase_id"
        " having bool_or(x.status = 'planned')"
        " order by (sum(x.amount_cents) = %(valor)s) desc, max(x.occurred_on) desc limit 5",
        {"forma": c.forma_id if c else None, "valor": valor},
    ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def estorno(conn: db.Connection, p: Pessoa, texto: str) -> Resultado:
    r = Resultado(rotulo="fatura.estorno", conta=p.account_id)
    valor = valores.interpreta(texto).centavos
    if not valor:
        return r.diz(t.ESTORNO_SEM_VALOR)
    with db.account_context(conn, p.account_id) as cur:
        c = cartoes.no_texto(cur, texto)
        candidatas = _candidatas(cur, c, valor)
        exatas = [x for x in candidatas if x[1] == valor]
        if len(exatas) == 1:
            return r.diz(_abate(cur, exatas[0][0], valor))
        if not candidatas:
            return r.diz(t.ESTORNO_SEM_COMPRA.format(valor=valores.em_reais(valor)))
        botoes = [
            (
                Botao(
                    f"{valores.em_reais(total)} · {seguro(desc, 20) or 'compra'}",
                    f"fa:es:{seg.curto(compra)}:{valor}",
                ),
            )
            for compra, total, desc in candidatas
        ]
        return r.diz(
            t.ESTORNO_QUAL.format(valor=valores.em_reais(valor)),
            botoes=(*botoes, (Botao("Nenhuma destas", "fa:en"),)),
        )


def _abate(cur: Any, compra: uuid.UUID, valor: int) -> str:
    """Abate o estorno das parcelas ainda previstas, da última para a primeira."""
    rows = cur.execute(
        "select id, amount_cents, coalesce(description, '') from telegrana.transactions"
        " where purchase_id = %s and status = 'planned' and deleted_at is null"
        " order by installment_no desc",
        (compra,),
    ).fetchall()
    if not rows:
        return t.ESTORNO_SEM_COMPRA.format(valor=valores.em_reais(valor))
    falta = valor
    for tx_id, centavos, _ in rows:
        if falta <= 0:
            break
        if centavos <= falta:
            cur.execute(
                "update telegrana.transactions set deleted_at = now(), updated_at = now()"
                " where id = %s",
                (tx_id,),
            )
            falta -= centavos
        else:
            cur.execute(
                "update telegrana.transactions set amount_cents = %s, updated_at = now()"
                " where id = %s",
                (centavos - falta, tx_id),
            )
            falta = 0
    abatido = valor - falta
    return t.ESTORNO_FEITO.format(
        valor=valores.em_reais(abatido), descricao=seguro(rows[0][2], 40) or "a compra"
    )


# ---------------------------------------------------------------------------
# Botões e resposta do "Outro valor"
# ---------------------------------------------------------------------------
def _data(texto: str, hoje: date) -> date | None:
    if not re.fullmatch(r"\d{8}", texto):
        return None
    try:
        d = date(int(texto[:4]), int(texto[4:6]), int(texto[6:]))
    except ValueError:
        return None
    return d if abs((d - hoje).days) <= JANELA else None


def trata(conn: db.Connection, ctx: Contexto, e: Entrada, p: Pessoa) -> Resultado:
    r = Resultado(rotulo="fatura", conta=p.account_id)
    hoje = agora().date()
    if e.pergunta in PERGUNTAS:
        return _resposta(conn, e, p, hoje, r)
    partes = (e.acao or "").split(":")
    acao = partes[1] if len(partes) > 1 else ""
    r.rotulo = f"fatura.{acao}"
    with db.account_context(conn, p.account_id) as cur:
        if acao == "en":
            return r.diz(t.ESTORNO_NENHUMA)
        if acao == "es" and len(partes) == 4 and partes[3].isdigit():
            compra = seg.longo(partes[2])
            existe = (
                compra
                and cur.execute(
                    "select 1 from telegrana.transactions where id = %s", (compra,)
                ).fetchone()
            )
            if not existe or compra is None:  # RLS: compra de outra conta não aparece
                return r.diz(t.RASCUNHO_SUMIU)
            return r.diz(_abate(cur, compra, int(partes[3])))
        cartao_id = seg.longo(partes[2]) if len(partes) > 2 else None
        c = cartoes.por_id(cur, cartao_id) if cartao_id else None
        if c is None:
            return r.diz(t.CARTAO_SUMIU)
        if acao == "pc":  # escolheu o cartão para pagar
            vencimento = a_pagar(cur, c, hoje)
            if vencimento is None:
                return r.diz(t.FATURA_VAZIA.format(nome=seguro(c.nome, 30)))
            r.saidas.append(tela(cur, c, vencimento))
            return r
        if acao == "ab":  # faturas em aberto do cartão (/cartoes)
            todas = abertas(cur, c)
            if not todas:
                return r.diz(t.FATURA_VAZIA.format(nome=seguro(c.nome, 30)))
            botoes = [
                (
                    Botao(
                        f"🧾 vence {v:%d/%m} · {valores.em_reais(sum(i.centavos for i in itens(cur, c, v)))}",
                        f"fa:it:{_chave(c, v)}",
                    ),
                )
                for v in todas[:6]
            ]
            return r.diz(t.FATURAS_DO_CARTAO.format(nome=seguro(c.nome, 30)), botoes=tuple(botoes))
        vencimento = _data(partes[3], hoje) if len(partes) > 3 else None
        if vencimento is None:
            return r.diz(t.USE_OS_BOTOES)
        if acao == "it":
            r.saidas.append(tela(cur, c, vencimento, todos=True))
        elif acao == "pg":
            r.diz(paga(cur, p, c, vencimento, None, hoje))
        elif acao == "pv" and len(partes) == 5 and partes[4].isdigit():
            r.diz(paga(cur, p, c, vencimento, int(partes[4]), hoje))
        elif acao == "ov":
            if _paga_em(cur, c, vencimento) is not None:
                return r.diz(
                    t.FATURA_JA_PAGA.format(nome=seguro(c.nome, 30), data=f"{vencimento:%d/%m}")
                )
            r.diz(
                f"{t.PERGUNTAS['fa_valor']}\n{MARCA} {c.nome} · {vencimento:%d/%m/%Y}",
                pergunta="fa_valor",
            )
        else:
            r.diz(t.USE_OS_BOTOES)
    return r


def _resposta(conn: db.Connection, e: Entrada, p: Pessoa, hoje: date, r: Resultado) -> Resultado:
    r.rotulo = "fatura.valor"
    nome, _, quando = e.contexto.removeprefix(MARCA).strip().rpartition(" · ")
    achado = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", quando)
    vencimento = _data(f"{achado[3]}{achado[2]}{achado[1]}", hoje) if achado else None
    if not nome or vencimento is None:
        return r.diz(t.USE_OS_BOTOES)
    with db.account_context(conn, p.account_id) as cur:
        c = cartoes.pelo_nome(cur, nome)
        if c is None:
            return r.diz(t.CARTAO_SUMIU)
        valor = valores.interpreta(e.texto).centavos
        if not valor:
            return r.diz(
                f"{t.PERGUNTAS['fa_valor']}\n{MARCA} {c.nome} · {vencimento:%d/%m/%Y}",
                pergunta="fa_valor",
            )
        return r.diz(paga(cur, p, c, vencimento, valor, hoje))

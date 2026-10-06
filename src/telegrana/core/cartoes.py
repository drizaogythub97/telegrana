"""Cartões de crédito e compras parceladas (PLANO 4.5; D045).

Regime de caixa: a compra no crédito é compromisso. Cada parcela é um lançamento PREVISTO
(`status = 'planned'`) na fatura certa — vencimento em `invoice_on` e em `cash_on` — ligado
à compra pela 1ª parcela (`purchase_id`). Vira gasto realizado quando a fatura é paga (S5.2).
O cartão é uma forma de pagamento (`payment_methods`, kind `credit`) com os dias em `cards`.
Tudo dentro de `db.account_context` (RLS forçado).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from psycopg import errors

from telegrana.core import fixos
from telegrana.core import seguranca as seg
from telegrana.core import textos as t
from telegrana.core.contexto import Contexto
from telegrana.core.interpretacao import normaliza
from telegrana.core.mensagens import Botao, Entrada, Resultado, Saida, seguro
from telegrana.core.repositorio import Pessoa
from telegrana.infra import db

PREFIXO = "ct:"
PERGUNTAS = frozenset({"ct_nome", "ct_dias", "ct_renomear"})
MARCA = "💳"  # 2ª linha das perguntas: "💳 <nome do cartão>"
EMOJI = "💳"
_SOBRAS_DO_NOME = frozenset({"cartao", "credito", "do", "da", "de", "no", "na", "meu", "o", "a"})
_APELIDOS = {"nu": "nubank", "roxinho": "nubank"}
_PALAVRA_FECHA = re.compile(r"\bfech\w*")
_PALAVRA_VENCE = re.compile(r"\bvenc\w*")


@dataclass(frozen=True, slots=True)
class Cartao:
    id: uuid.UUID
    forma_id: uuid.UUID
    nome: str
    fecha: int  # dia do fechamento
    vence: int  # dia do vencimento
    limite: int | None
    ativo: bool
    antes: bool = True  # lembretes da fatura (como nos fixos)
    no_dia: bool = True
    depois: bool = True
    horario: str = "morning"  # morning | evening | both


# ---------------------------------------------------------------------------
# Regras (puras)
# ---------------------------------------------------------------------------
def _soma_meses(ano: int, mes: int, k: int) -> tuple[int, int]:
    total = ano * 12 + mes - 1 + k
    return total // 12, total % 12 + 1


def fatura(compra: date, fecha: int, vence: int, deslocamento: int = 0) -> date:
    """Vencimento da fatura em que cai a compra (`deslocamento` = parcela seguinte).

    Compra NO dia do fechamento ou depois já cai na fatura seguinte (como nos bancos). O
    vencimento vem depois do fechamento: no mesmo mês se o dia for maior, senão no seguinte.
    Dia 31 em mês curto = último dia (mesma regra dos fixos).
    """
    fechamento = fixos.vencimento(fecha, compra.year, compra.month)
    ano, mes = _soma_meses(compra.year, compra.month, (compra >= fechamento) + deslocamento)
    if vence <= fecha:
        ano, mes = _soma_meses(ano, mes, 1)
    return fixos.vencimento(vence, ano, mes)


def faturas(compra: date, fecha: int, vence: int, parcelas: int) -> list[date]:
    return [fatura(compra, fecha, vence, k) for k in range(parcelas)]


def divide(total: int, parcelas: int) -> list[int]:
    """Centavos da divisão ficam na 1ª parcela: 100,00 em 3x = 33,34 + 33,33 + 33,33."""
    base = total // parcelas
    return [total - base * (parcelas - 1)] + [base] * (parcelas - 1)


def _dia(trecho: str) -> int:
    limpo = re.sub(r"\b(dia|no|todo|e)\b", " ", trecho)
    dia = fixos.dia_dito(" ".join(limpo.split()))
    return dia if 1 <= dia <= 31 else 0


def dois_dias(texto: str) -> tuple[int, int] | None:
    """(fecha, vence) de "fecha 3, vence 10", "fecha dia três e vence dia dez" ou "3 e 10"."""
    n = normaliza(texto)
    fecha = _PALAVRA_FECHA.search(n)
    vence = _PALAVRA_VENCE.search(n)
    if fecha and vence:
        if fecha.start() < vence.start():
            dias = (_dia(n[fecha.end() : vence.start()]), _dia(n[vence.end() :]))
        else:
            dias = (_dia(n[fecha.end() :]), _dia(n[vence.end() : fecha.start()]))
        return dias if all(dias) else None
    numeros = [int(x) for x in re.findall(r"\b\d{1,2}\b", n)]
    if len(numeros) == 2 and all(1 <= x <= 31 for x in numeros):
        return numeros[0], numeros[1]
    return None


def chave(nome: str) -> str:
    palavras = [p for p in normaliza(nome).split() if p not in _SOBRAS_DO_NOME]
    chave = "".join(_APELIDOS.get(p, p) for p in palavras)
    return _APELIDOS.get(chave, chave)


def nome_para(citado: str | None) -> str | None:
    """Nome de cartão novo a partir do que a pessoa disse ("no nu" → "Nubank")."""
    if not citado:
        return None
    palavras = [p for p in normaliza(citado).split() if p not in _SOBRAS_DO_NOME]
    nome = " ".join(_APELIDOS.get(p, p) for p in palavras)
    return nome_valido(nome) if nome else None


def nome_bate(cartao: str, citado: str) -> bool:
    """O cartão "Nubank" bate com "no nu", "cartão do Nubank", "nubank"."""
    a, b = chave(cartao), chave(citado)
    return bool(a and b) and (a == b or (len(b) >= 3 and (b in a or a in b)))


def nome_valido(texto: str) -> str | None:
    nome = " ".join(seguro(texto, 60).split())
    if not 1 <= len(nome) <= 30 or not re.search(r"[^\W\d_]", nome):
        return None
    return nome[:1].upper() + nome[1:]


# ---------------------------------------------------------------------------
# SQL (fixo, parametrizado)
# ---------------------------------------------------------------------------
_SELECT = (
    "select c.id, c.payment_method_id, m.name, c.closing_day, c.due_day, c.limit_cents, m.active,"
    " c.remind_before, c.remind_on_day, c.remind_after, c.remind_slot"
    " from telegrana.cards c join telegrana.payment_methods m on m.id = c.payment_method_id"
)


def lista(cur: Any, *, ativos: bool = True) -> list[Cartao]:
    filtro = " where m.active" if ativos else ""
    return [Cartao(*r) for r in cur.execute(_SELECT + filtro + " order by m.created_at")]


def por_id(cur: Any, cartao_id: uuid.UUID) -> Cartao | None:
    row = cur.execute(_SELECT + " where c.id = %s", (cartao_id,)).fetchone()
    return Cartao(*row) if row else None


def da_forma(cur: Any, forma_id: uuid.UUID | None) -> Cartao | None:
    if forma_id is None:
        return None
    row = cur.execute(_SELECT + " where c.payment_method_id = %s", (forma_id,)).fetchone()
    return Cartao(*row) if row else None


def no_texto(cur: Any, texto: str) -> Cartao | None:
    """O cartão citado numa frase ("paguei a fatura do nu", "estorno de 80 no Inter")."""
    palavras = [_APELIDOS.get(p, p) for p in normaliza(texto).split()]
    frase = f" {' '.join(palavras)} "
    return next(
        (
            c
            for c in lista(cur)
            if f" {' '.join(_APELIDOS.get(x, x) for x in normaliza(c.nome).split())} " in frase
        ),
        None,
    )


def citado(cur: Any, nome: str | None) -> Cartao | None:
    if not nome:
        return None
    return next((c for c in lista(cur) if nome_bate(c.nome, nome)), None)


def cria(cur: Any, p: Pessoa, nome: str, fecha: int, vence: int) -> tuple[Cartao | None, bool]:
    """(cartão, criado?). Nome de cartão que já existe devolve o existente; nome de outra
    forma de pagamento ("Pix") devolve (None, False)."""
    try:
        with cur.connection.transaction():
            forma = cur.execute(
                "insert into telegrana.payment_methods (account_id, kind, name, emoji)"
                " values (%s, 'credit', %s, %s) returning id",
                (p.account_id, nome, EMOJI),
            ).fetchone()[0]
            cartao = cur.execute(
                "insert into telegrana.cards (account_id, payment_method_id, closing_day, due_day)"
                " values (%s, %s, %s, %s) returning id",
                (p.account_id, forma, fecha, vence),
            ).fetchone()[0]
    except errors.UniqueViolation:
        row = cur.execute(
            "select id from telegrana.payment_methods where lower(name) = lower(%s)", (nome,)
        ).fetchone()
        existente = da_forma(cur, row[0]) if row else None
        return existente, False
    return por_id(cur, cartao), True


def renomeia(cur: Any, c: Cartao, nome: str) -> bool:
    try:
        with cur.connection.transaction():
            cur.execute(
                "update telegrana.payment_methods set name = %s where id = %s", (nome, c.forma_id)
            )
    except errors.UniqueViolation:
        return False
    return True


def muda_dias(cur: Any, c: Cartao, fecha: int, vence: int) -> None:
    """Novos dias: as parcelas ainda previstas mudam de fatura junto."""
    cur.execute(
        "update telegrana.cards set closing_day = %s, due_day = %s, updated_at = now()"
        " where id = %s",
        (fecha, vence, c.id),
    )
    rows = cur.execute(
        "select id, occurred_on, installment_no from telegrana.transactions"
        " where payment_method_id = %s and purchase_id is not null and status = 'planned'",
        (c.forma_id,),
    ).fetchall()
    for tx_id, compra, numero in rows:
        nova = fatura(compra, fecha, vence, numero - 1)
        _muda_fatura(cur, tx_id, nova)


def _muda_fatura(cur: Any, tx_id: uuid.UUID, vencimento: date) -> None:
    cur.execute(
        "update telegrana.transactions set invoice_on = %s, cash_on = %s, updated_at = now()"
        " where id = %s",
        (vencimento, vencimento, tx_id),
    )


def apaga(cur: Any, c: Cartao) -> bool:
    """True = apagado; False = tinha lançamentos e só foi desativado."""
    usado = cur.execute(
        "select 1 from telegrana.transactions where payment_method_id = %s limit 1", (c.forma_id,)
    ).fetchone()
    if usado:
        cur.execute(
            "update telegrana.payment_methods set active = false where id = %s", (c.forma_id,)
        )
        return False
    cur.execute("delete from telegrana.payment_methods where id = %s", (c.forma_id,))
    return True


def grava_compra(
    cur: Any,
    p: Pessoa,
    c: Cartao,
    *,
    total: int,
    parcelas: int,
    compra: date,
    categoria_id: uuid.UUID | None,
    descricao: str | None,
    origem: str,
    texto_original: str,
) -> uuid.UUID:
    """Uma linha por parcela (prevista), na fatura de cada uma. Devolve a 1ª (a compra)."""
    ids = [
        uuid.UUID(str(r[0]))
        for r in cur.execute("select uuidv7() from generate_series(1, %s)", (parcelas,))
    ]
    primeira = ids[0]
    for k, (valor, vencimento) in enumerate(
        zip(divide(total, parcelas), faturas(compra, c.fecha, c.vence, parcelas), strict=True),
        start=1,
    ):
        cur.execute(
            "insert into telegrana.transactions (account_id, id, user_id, kind, amount_cents,"
            " category_id, payment_method_id, occurred_on, cash_on, description, source,"
            " original_text, status, installments, purchase_id, installment_no, invoice_on)"
            " values (%s, %s, %s, 'expense', %s, %s, %s, %s, %s, %s, %s, %s, 'planned', %s,"
            " %s, %s, %s)",
            (
                p.account_id,
                ids[k - 1],
                p.user_id,
                valor,
                categoria_id,
                c.forma_id,
                compra,
                vencimento,
                (descricao or None) and descricao[:200],
                origem,
                texto_original[:1000],
                parcelas,
                primeira,
                k,
                vencimento,
            ),
        )
    return primeira


def converte(cur: Any, tx_id: uuid.UUID, c: Cartao) -> None:
    """Lançamento comum (ex.: crédito antes dos cartões) vira compra no cartão, nas faturas."""
    row = cur.execute(
        "select user_id, amount_cents, category_id, occurred_on, description, source,"
        " original_text, coalesce(installments, 1), recurring, fixed_item_id"
        " from telegrana.transactions where id = %s and purchase_id is null",
        (tx_id,),
    ).fetchone()
    if row is None:
        return
    user_id, total, categoria, compra, descricao, origem, texto, parcelas, recorrente, fixo = row
    partes = divide(total, parcelas)
    datas = faturas(compra, c.fecha, c.vence, parcelas)
    cur.execute(
        "update telegrana.transactions set amount_cents = %s, payment_method_id = %s,"
        " status = 'planned', cash_on = %s, invoice_on = %s, purchase_id = id,"
        " installment_no = 1, installments = %s, updated_at = now() where id = %s",
        (partes[0], c.forma_id, datas[0], datas[0], parcelas, tx_id),
    )
    for k in range(1, parcelas):
        cur.execute(
            "insert into telegrana.transactions (account_id, user_id, kind, amount_cents,"
            " category_id, payment_method_id, occurred_on, cash_on, description, source,"
            " original_text, status, installments, purchase_id, installment_no, invoice_on,"
            " recurring, fixed_item_id)"
            " select account_id, %s, 'expense', %s, %s, %s, %s, %s, %s, %s, %s, 'planned', %s,"
            " %s, %s, %s, %s, %s from telegrana.transactions where id = %s",
            (
                user_id,
                partes[k],
                categoria,
                c.forma_id,
                compra,
                datas[k],
                descricao,
                origem,
                texto,
                parcelas,
                tx_id,
                k + 1,
                datas[k],
                recorrente,
                fixo,
                tx_id,
            ),
        )


def _parcelas_da_compra(cur: Any, compra_id: uuid.UUID) -> list[tuple[uuid.UUID, int]]:
    return [
        (r[0], r[1])
        for r in cur.execute(
            "select id, installment_no from telegrana.transactions where purchase_id = %s"
            " order by installment_no",
            (compra_id,),
        )
    ]


def desfaz(cur: Any, compra_id: uuid.UUID, forma_id: uuid.UUID) -> None:
    """A compra deixa de ser no cartão ("foi no débito"): volta a ser um lançamento comum,
    realizado na data da compra, com o total; as outras parcelas são apagadas (logicamente)."""
    total = cur.execute(
        "select sum(amount_cents)::bigint from telegrana.transactions where purchase_id = %s",
        (compra_id,),
    ).fetchone()[0]
    cur.execute(
        "update telegrana.transactions set deleted_at = now(), purchase_id = null,"
        " installment_no = null, updated_at = now() where purchase_id = %s and id <> %s",
        (compra_id, compra_id),
    )
    cur.execute(
        "update telegrana.transactions set amount_cents = %s, payment_method_id = %s,"
        " status = 'done', cash_on = occurred_on, invoice_on = null, purchase_id = null,"
        " installment_no = null, installments = null, updated_at = now() where id = %s",
        (total, forma_id, compra_id),
    )


_LEMBRETES = {
    "remind_before": "update telegrana.cards set remind_before = %s, updated_at = now() where id = %s",
    "remind_on_day": "update telegrana.cards set remind_on_day = %s, updated_at = now() where id = %s",
    "remind_after": "update telegrana.cards set remind_after = %s, updated_at = now() where id = %s",
    "remind_slot": "update telegrana.cards set remind_slot = %s, updated_at = now() where id = %s",
}


def lembrete(cur: Any, c: Cartao, campo: str, valor: object) -> None:
    cur.execute(_LEMBRETES[campo], (valor, c.id))  # lista fixa: nada vem de fora


_EM_TODAS = {
    "category_id": "update telegrana.transactions set category_id = %s, updated_at = now() where purchase_id = %s",
    "description": "update telegrana.transactions set description = %s, updated_at = now() where purchase_id = %s",
    "recurring": "update telegrana.transactions set recurring = %s, updated_at = now() where purchase_id = %s",
    "deleted": "update telegrana.transactions set deleted_at = case when %s then now() end, updated_at = now() where purchase_id = %s",
}


def atualiza_compra(cur: Any, compra_id: uuid.UUID, campo: str, valor: Any) -> None:
    """Correção numa compra parcelada vale para a compra inteira (todas as parcelas)."""
    if campo in _EM_TODAS:
        cur.execute(_EM_TODAS[campo], (valor, compra_id))
        return
    forma = cur.execute(
        "select payment_method_id, occurred_on from telegrana.transactions where id = %s",
        (compra_id,),
    ).fetchone()
    c = da_forma(cur, forma[0]) if forma else None
    if campo == "payment_method_id":
        novo = da_forma(cur, valor)
        if novo is None:
            desfaz(cur, compra_id, valor)
            return
        cur.execute(
            "update telegrana.transactions set payment_method_id = %s, updated_at = now()"
            " where purchase_id = %s",
            (valor, compra_id),
        )
        c, campo, valor = novo, "cash_on", forma[1]  # mesma data, faturas do outro cartão
    parcelas = _parcelas_da_compra(cur, compra_id)
    if campo == "amount_cents":
        for (tx_id, _), parte in zip(parcelas, divide(valor, len(parcelas)), strict=True):
            cur.execute(
                "update telegrana.transactions set amount_cents = %s, updated_at = now()"
                " where id = %s",
                (parte, tx_id),
            )
    elif campo == "cash_on" and c is not None:
        for tx_id, numero in parcelas:
            vencimento = fatura(valor, c.fecha, c.vence, numero - 1)
            cur.execute(
                "update telegrana.transactions set occurred_on = %s, invoice_on = %s,"
                " cash_on = %s, updated_at = now() where id = %s",
                (valor, vencimento, vencimento, tx_id),
            )
    else:
        raise ValueError(f"campo inválido para compra: {campo}")


def antigas(cur: Any) -> list[uuid.UUID]:
    """Compras no crédito registradas antes dos cartões (forma "Crédito" genérica)."""
    rows = cur.execute(
        "select x.id from telegrana.transactions x"
        " join telegrana.payment_methods m on m.id = x.payment_method_id"
        " where m.kind = 'credit' and x.kind = 'expense' and x.deleted_at is null"
        " and x.purchase_id is null"
        " and not exists (select 1 from telegrana.cards c where c.payment_method_id = m.id)"
        " order by x.occurred_on",
    ).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Telas
# ---------------------------------------------------------------------------
def linha(c: Cartao) -> str:
    pausa = " · ⏸️ desativado" if not c.ativo else ""
    return f"{EMOJI} **{seguro(c.nome, 30)}** · fecha dia {c.fecha} · vence dia {c.vence}{pausa}"


def descreve_lembretes(c: Cartao) -> str:
    quando = [
        nome
        for ligado, nome in (
            (c.antes, "na véspera"),
            (c.no_dia, "no dia"),
            (c.depois, "todo dia depois"),
        )
        if ligado
    ]
    if not quando:
        return "🔕 Sem lembretes do vencimento (o aviso de fatura fechada continua)"
    texto = quando[0] if len(quando) == 1 else ", ".join(quando[:-1]) + " e " + quando[-1]
    return f"🔔 Lembrete {texto}, {fixos.HORARIOS.get(c.horario, '')}".rstrip(", ")


def tela(c: Cartao, titulo: str = t.CARTAO_TITULO) -> Saida:
    i = seg.curto(c.id)
    return Saida(
        f"{titulo}\n{linha(c)}\n{descreve_lembretes(c)}",
        botoes=(
            (Botao("🧾 Faturas", f"fa:ab:{i}"), Botao("🔔 Lembretes", f"ct:lb:{i}")),
            (Botao("✏️ Nome", f"ct:no:{i}"), Botao("📅 Dias da fatura", f"ct:di:{i}")),
            (Botao("🗑️ Apagar", f"ct:ap:{i}"),),
        ),
    )


def _tela_lembretes(c: Cartao) -> Saida:
    i = seg.curto(c.id)

    def marca(ligado: bool) -> str:
        return "✅" if ligado else "⬜"

    def horario(chave: str, rotulo: str) -> Botao:
        return Botao(("● " if c.horario == chave else "") + rotulo, f"ct:h{chave[0]}:{i}")

    return Saida(
        f"🔔 **Lembretes da fatura do {seguro(c.nome, 30)}**\n{descreve_lembretes(c)}",
        botoes=(
            (
                Botao(f"{marca(c.antes)} Véspera", f"ct:tb:{i}"),
                Botao(f"{marca(c.no_dia)} No dia", f"ct:to:{i}"),
                Botao(f"{marca(c.depois)} Depois", f"ct:ta:{i}"),
            ),
            (
                horario("morning", "🌅 Manhã"),
                horario("evening", "🌙 Noite"),
                horario("both", "🌅🌙 Ambos"),
            ),
            (Botao("✔️ Pronto", f"ct:ed:{i}"),),
        ),
        substitui=True,
    )


_ALTERNA = {"tb": "remind_before", "to": "remind_on_day", "ta": "remind_after"}
_HORARIO = {"hm": "morning", "he": "evening", "hb": "both"}


def oferta_antigas(cur: Any, c: Cartao) -> Saida | None:
    """Primeiro cartão: as compras no crédito de antes podem ir para as faturas dele (D045)."""
    n = len(antigas(cur))
    if not n or len(lista(cur, ativos=False)) != 1:
        return None
    i = seg.curto(c.id)
    return Saida(
        t.MOVER_ANTIGAS.format(n=n, nome=seguro(c.nome, 30)),
        botoes=((Botao("✅ Sim, mover", f"ct:mv:{i}"), Botao("Não", f"ct:mn:{i}")),),
    )


def pergunta_dias(nome: str, chave: str = "ct_dias") -> Saida:
    return Saida(f"{t.PERGUNTAS[chave]}\n{MARCA} {nome}", pergunta=chave)


# ---------------------------------------------------------------------------
# Fluxo do /cartoes
# ---------------------------------------------------------------------------
def trata(conn: db.Connection, ctx: Contexto, e: Entrada, p: Pessoa) -> Resultado:
    r = Resultado(rotulo="cartoes", conta=p.account_id)
    if e.pergunta in PERGUNTAS:
        return _resposta(conn, e, p, r)
    partes = (e.acao or "").split(":")
    if e.comando == "cartoes" or partes == ["ct", "lista"]:
        with db.account_context(conn, p.account_id) as cur:
            todos = lista(cur, ativos=False)
        novo = (Botao("➕ Novo cartão", "ct:nv"),)
        if not todos:
            return r.diz(t.CARTOES_VAZIO, botoes=(novo,))
        botoes = [Botao(f"{EMOJI} {c.nome[:24]}", f"ct:ed:{seg.curto(c.id)}") for c in todos]
        linhas = [tuple(botoes[k : k + 2]) for k in range(0, len(botoes), 2)]
        return r.diz(
            t.CARTOES_TITULO + "\n\n" + "\n".join(linha(c) for c in todos),
            botoes=(*linhas, novo),
        )
    if partes == ["ct", "nv"]:
        r.rotulo = "cartoes.nv"
        return r.diz(t.PERGUNTAS["ct_nome"], pergunta="ct_nome")
    if len(partes) != 3:
        return r.diz(t.USE_OS_BOTOES)
    acao, cartao_id = partes[1], seg.longo(partes[2])
    r.rotulo = f"cartoes.{acao}"
    with db.account_context(conn, p.account_id) as cur:
        c = por_id(cur, cartao_id) if cartao_id else None  # RLS: outra conta não acha
        if c is None:
            return r.diz(t.CARTAO_SUMIU)
        if acao == "ed":
            r.saidas.append(tela(c))
        elif acao == "lb":
            r.saidas.append(_tela_lembretes(c))
        elif acao in _ALTERNA or acao in _HORARIO:
            if acao in _ALTERNA:
                atual = {"tb": c.antes, "to": c.no_dia, "ta": c.depois}[acao]
                lembrete(cur, c, _ALTERNA[acao], not atual)
            else:
                lembrete(cur, c, "remind_slot", _HORARIO[acao])
            r.saidas.append(_tela_lembretes(por_id(cur, c.id) or c))
        elif acao == "no":
            r.diz(f"{t.PERGUNTAS['ct_renomear']}\n{MARCA} {c.nome}", pergunta="ct_renomear")
        elif acao == "di":
            r.saidas.append(pergunta_dias(c.nome))
        elif acao == "ap":
            i = seg.curto(c.id)
            r.diz(
                t.CARTAO_APAGAR_CONFIRMA.format(nome=seguro(c.nome, 30)),
                botoes=((Botao("🗑️ Apagar", f"ct:ok:{i}"), Botao("Cancelar", f"ct:ed:{i}")),),
            )
        elif acao == "ok":
            apagado = apaga(cur, c)
            r.diz(t.CARTAO_APAGADO if apagado else t.CARTAO_DESATIVADO.format(nome=c.nome))
        elif acao == "mv":
            movidas = antigas(cur)
            for tx_id in movidas:
                converte(cur, tx_id, c)
            r.diz(t.ANTIGAS_MOVIDAS.format(n=len(movidas), nome=seguro(c.nome, 30)))
        elif acao == "mn":
            r.diz(t.ANTIGAS_FICAM)
        else:
            r.diz(t.USE_OS_BOTOES)
    return r


def _resposta(conn: db.Connection, e: Entrada, p: Pessoa, r: Resultado) -> Resultado:
    nome = e.contexto.removeprefix(MARCA).strip()  # 2ª linha da pergunta: escrita pelo bot
    with db.account_context(conn, p.account_id) as cur:
        if e.pergunta == "ct_nome":
            novo = nome_valido(e.texto)
            if novo is None:
                return r.diz(t.CARTAO_NOME_RUIM).diz(t.PERGUNTAS["ct_nome"], pergunta="ct_nome")
            existente = citado(cur, novo)
            if existente is not None:
                r.saidas.append(tela(existente, titulo=t.CARTAO_JA_EXISTE))
                return r
            r.saidas.append(pergunta_dias(novo))
            return r
        if e.pergunta == "ct_renomear":
            c = pelo_nome(cur, nome)
            novo = nome_valido(e.texto)
            if c is None:
                return r.diz(t.CARTAO_SUMIU)
            if novo is None:
                return r.diz(t.CARTAO_NOME_RUIM)
            if not renomeia(cur, c, novo):
                return r.diz(t.CARTAO_NOME_EXISTE.format(nome=novo))
            r.saidas.append(tela(por_id(cur, c.id) or c, titulo=t.CARTAO_ATUALIZADO))
            return r
        # ct_dias: de um cartão que já existe (mudar) ou de um novo (cadastrar)
        dias = dois_dias(e.texto)
        if dias is None or not nome:
            r.diz(t.DIAS_NAO_ENTENDI)
            if nome:
                r.saidas.append(pergunta_dias(nome))
            return r
        c = pelo_nome(cur, nome)
        if c is not None:
            muda_dias(cur, c, *dias)
            r.saidas.append(tela(por_id(cur, c.id) or c, titulo=t.CARTAO_ATUALIZADO))
            return r
        criado, novo_ok = cria(cur, p, nome, *dias)
        if criado is None:
            return r.diz(t.CARTAO_NOME_EXISTE.format(nome=nome))
        r.saidas.append(tela(criado, titulo=t.CARTAO_CRIADO if novo_ok else t.CARTAO_JA_EXISTE))
        oferta = oferta_antigas(cur, criado)
        if oferta is not None:
            r.saidas.append(oferta)
    return r


def pelo_nome(cur: Any, nome: str) -> Cartao | None:
    return next((c for c in lista(cur, ativos=False) if c.nome.lower() == nome.lower()), None)

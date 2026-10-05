"""Fixos e recorrentes (PLANO 4.3; D043): aluguel, luz, assinaturas, salário...

O fixo gera LEMBRETE, não lançamento (S4.2): o lançamento nasce no "Paguei/Recebi".
Nasce de três jeitos: "é fixo? Sim" no recibo, uma frase com recorrência ("aluguel 1500
todo dia 10") ou depois, pelo `/fixos`. Tudo dentro de `db.account_context` (RLS forçado).
"""

from __future__ import annotations

import calendar
import re
import uuid
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from psycopg import errors

from telegrana.core import seguranca as seg
from telegrana.core import textos as t
from telegrana.core import valores
from telegrana.core.contexto import Contexto
from telegrana.core.interpretacao import normaliza
from telegrana.core.mensagens import Botao, Entrada, Resultado, Saida, seguro
from telegrana.core.repositorio import Pessoa
from telegrana.infra import db

PREFIXO = "fi:"
PERGUNTAS = frozenset({"fi_valor", "fi_dia"})
MARCA = "🔁"  # 2ª linha das perguntas de edição: "🔁 <nome do fixo>"
HORARIOS = {"morning": "às 09:00", "evening": "às 20:00", "both": "às 09:00 e às 20:00"}
# "IA decide pelo tipo" (D043): o que costuma variar de um mês para outro é estimado.
_ESTIMADOS = frozenset({"contas_casa", "encargos", "combustivel", "mercado", "saude"})
_VAGOS = re.compile(r"\b(uns|umas|mais ou menos|em media|media|aproximad\w*|cerca de|varia\w*)\b")
# "todo dia 10", "todo mês", "mensal", "por mês", "conta fixa" (normalizado, sem acento).
# "todo dia" SEM número é diário ("café todo dia"), não mensal: não conta.
_RECORRENCIA = re.compile(
    r"\btodo dia \d{1,2}\b|\btod[oa]s? (os )?mes(es)?\b|\bmensal(mente)?\b|\bpor mes\b"
    r"|\bao mes\b|\b(conta|gasto|ganho|despesa|pagamento|e) fix[oa]\b"
)
_SOBRAS_DE_RECORRENCIA = frozenset(
    {
        "todo",
        "toda",
        "todos",
        "todas",
        "os",
        "mes",
        "meses",
        "mensal",
        "mensalmente",
        "dia",
        "por",
        "ao",
    }
)
_DIA = re.compile(r"\bdia (\d{1,2})\b")
_VERBOS_DE_PAGAMENTO = frozenset(
    {"paguei", "gastei", "comprei", "recebi", "caiu", "entrou", "ganhei", "transferi"}
)


@dataclass(frozen=True, slots=True)
class Fixo:
    id: uuid.UUID
    tipo: str  # expense | income
    nome: str
    categoria_id: uuid.UUID | None
    centavos: int
    valor_tipo: str  # fixed | estimated
    dia: int
    forma_id: uuid.UUID | None
    antes: bool
    no_dia: bool
    depois: bool
    horario: str  # morning | evening | both
    ativo: bool
    desde: date | None = None  # dia em que foi cadastrado (lembrete "depois" não volta antes)


# ---------------------------------------------------------------------------
# Regras de negócio (puras)
# ---------------------------------------------------------------------------
def vencimento(dia: int, ano: int, mes: int) -> date:
    """Dia do vencimento naquele mês; 31 em mês curto (e 29 em fevereiro) = último dia."""
    return date(ano, mes, min(dia, calendar.monthrange(ano, mes)[1]))


def recorrencia(texto: str) -> tuple[bool, int | None]:
    """A frase fala de algo que se repete? E em que dia do mês ("todo dia 10")."""
    t_ = normaliza(texto)
    if not _RECORRENCIA.search(t_):
        return False, None
    achado = _DIA.search(t_)
    dia = int(achado.group(1)) if achado else None
    return True, dia if dia and 1 <= dia <= 31 else None


def so_cadastro(texto: str) -> bool:
    """Sem verbo de pagamento ("aluguel 1500 todo dia 10"): cadastra o fixo e não lança."""
    return not (_VERBOS_DE_PAGAMENTO & set(normaliza(texto).split()))


def valor_tipo(codigo_categoria: str | None, texto: str = "") -> str:
    if _VAGOS.search(normaliza(texto)) or (codigo_categoria or "") in _ESTIMADOS:
        return "estimated"
    return "fixed"


def nome_para(descricao: str | None, categoria: str | None) -> str:
    """Nome curto e legível: a descrição ("netflix" → "Netflix") ou a categoria."""
    palavras = [
        p
        for p in (descricao or "").split()
        if normaliza(p) not in _SOBRAS_DE_RECORRENCIA and not any(c.isdigit() for c in p)
    ]
    base = " ".join(palavras)[:40] or (categoria or "Fixo")
    return base[:1].upper() + base[1:]


def descreve_lembretes(f: Fixo) -> str:
    quando = [
        nome
        for ligado, nome in (
            (f.antes, "na véspera"),
            (f.no_dia, "no dia"),
            (f.depois, "todo dia depois"),
        )
        if ligado
    ]
    if not quando:
        return "🔕 Sem lembretes"
    texto = quando[0] if len(quando) == 1 else ", ".join(quando[:-1]) + " e " + quando[-1]
    return f"🔔 Lembrete {texto}, {HORARIOS.get(f.horario, '')}".rstrip(", ")


# ---------------------------------------------------------------------------
# SQL (fixo, parametrizado)
# ---------------------------------------------------------------------------
_SELECT = (
    "select id, kind, name, category_id, amount_cents, amount_kind, day_of_month,"
    " payment_method_id, remind_before, remind_on_day, remind_after, remind_slot, active,"
    " (created_at at time zone 'America/Sao_Paulo')::date"
    " from telegrana.fixed_items"
)
_CAMPOS = {
    "amount_cents": "update telegrana.fixed_items set amount_cents = %s, updated_at = now() where id = %s",
    "amount_kind": "update telegrana.fixed_items set amount_kind = %s, updated_at = now() where id = %s",
    "day_of_month": "update telegrana.fixed_items set day_of_month = %s, updated_at = now() where id = %s",
    "remind_before": "update telegrana.fixed_items set remind_before = %s, updated_at = now() where id = %s",
    "remind_on_day": "update telegrana.fixed_items set remind_on_day = %s, updated_at = now() where id = %s",
    "remind_after": "update telegrana.fixed_items set remind_after = %s, updated_at = now() where id = %s",
    "remind_slot": "update telegrana.fixed_items set remind_slot = %s, updated_at = now() where id = %s",
    "active": "update telegrana.fixed_items set active = %s, updated_at = now() where id = %s",
}


def lista(cur: Any) -> list[Fixo]:
    rows = cur.execute(_SELECT + " order by active desc, day_of_month, lower(name)").fetchall()
    return [Fixo(*r) for r in rows]


def por_id(cur: Any, fixo_id: uuid.UUID) -> Fixo | None:
    row = cur.execute(_SELECT + " where id = %s", (fixo_id,)).fetchone()
    return Fixo(*row) if row else None


def por_nome(cur: Any, nome: str) -> Fixo | None:
    row = cur.execute(_SELECT + " where lower(name) = lower(%s)", (nome,)).fetchone()
    return Fixo(*row) if row else None


def cria(
    cur: Any,
    p: Pessoa,
    *,
    tipo: str,
    nome: str,
    categoria_id: uuid.UUID | None,
    centavos: int,
    valor_tipo_: str,
    dia: int,
    forma_id: uuid.UUID | None,
) -> tuple[Fixo, bool]:
    """(fixo, criado?). Nome repetido devolve o que já existe (não duplica)."""
    try:
        with cur.connection.transaction():
            row = cur.execute(
                "insert into telegrana.fixed_items (account_id, user_id, kind, name, category_id,"
                " amount_cents, amount_kind, day_of_month, payment_method_id)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning id",
                (
                    p.account_id,
                    p.user_id,
                    tipo,
                    nome,
                    categoria_id,
                    centavos,
                    valor_tipo_,
                    dia,
                    forma_id,
                ),
            ).fetchone()
    except errors.UniqueViolation:
        existente = por_nome(cur, nome)
        if existente is None:
            raise
        return existente, False
    fixo = por_id(cur, uuid.UUID(str(row[0])))
    if fixo is None:
        raise RuntimeError("fixo recém-criado não encontrado")
    return fixo, True


def atualiza(cur: Any, fixo_id: uuid.UUID, campo: str, valor: object) -> None:
    cur.execute(_CAMPOS[campo], (valor, fixo_id))  # lista fixa: nada vem de fora


def apaga(cur: Any, fixo_id: uuid.UUID) -> None:
    cur.execute("delete from telegrana.fixed_items where id = %s", (fixo_id,))


def liga_lancamento(cur: Any, tx_id: uuid.UUID, fixo_id: uuid.UUID) -> None:
    cur.execute(
        "update telegrana.transactions set fixed_item_id = %s, recurring = true,"
        " updated_at = now() where id = %s",
        (fixo_id, tx_id),
    )


# ---------------------------------------------------------------------------
# Telas
# ---------------------------------------------------------------------------
def _rotulos_categorias(cur: Any) -> dict[uuid.UUID, str]:
    rows = cur.execute("select id, emoji from telegrana.categories").fetchall()
    return {r[0]: r[1] for r in rows}


def _linha(f: Fixo, emojis: dict[uuid.UUID, str]) -> str:
    emoji = emojis.get(f.categoria_id, MARCA) if f.categoria_id else MARCA
    valor = valores.em_reais(f.centavos) + (" (estimado)" if f.valor_tipo == "estimated" else "")
    pausa = " · ⏸️ pausado" if not f.ativo else ""
    return f"{emoji} **{seguro(f.nome, 40)}** · {valor} · dia {f.dia}{pausa}"


def cartao(f: Fixo, emojis: dict[uuid.UUID, str], *, titulo: str = t.FIXO_TITULO) -> Saida:
    """Resumo de um fixo com os botões de ajuste (usado ao criar e ao abrir pelo /fixos)."""
    i = seg.curto(f.id)
    tipo = "💸 Gasto" if f.tipo == "expense" else "💰 Ganho"
    texto = "\n".join(
        [
            titulo,
            _linha(f, emojis),
            f"{tipo} · {'valor fixo' if f.valor_tipo == 'fixed' else 'valor estimado'}",
            descreve_lembretes(f),
        ]
    )
    pausar = Botao("⏸️ Pausar", f"fi:pa:{i}") if f.ativo else Botao("▶️ Reativar", f"fi:at:{i}")
    return Saida(
        texto,
        botoes=(
            (Botao("💰 Valor", f"fi:va:{i}"), Botao("📅 Dia", f"fi:di:{i}")),
            (Botao("🔔 Lembretes", f"fi:lb:{i}"), Botao("🔀 Fixo/estimado", f"fi:vt:{i}")),
            (pausar, Botao("🗑️ Apagar", f"fi:ap:{i}")),
        ),
    )


def criado(f: Fixo, emojis: dict[uuid.UUID, str], novo: bool) -> Saida:
    """Mensagem de quando o fixo nasce (com Desfazer) ou já existia."""
    if not novo:
        return cartao(f, emojis, titulo=t.FIXO_JA_EXISTE)
    i = seg.curto(f.id)
    base = cartao(f, emojis, titulo=t.FIXO_CRIADO)
    return Saida(
        base.texto,
        botoes=((Botao("⚙️ Ajustar", f"fi:ed:{i}"), Botao("↩️ Desfazer", f"fi:un:{i}")),),
    )


def _tela_lembretes(f: Fixo) -> Saida:
    i = seg.curto(f.id)

    def marca(ligado: bool) -> str:
        return "✅" if ligado else "⬜"

    def horario(chave: str, rotulo: str) -> Botao:
        return Botao(("● " if f.horario == chave else "") + rotulo, f"fi:h{chave[0]}:{i}")

    return Saida(
        f"🔔 **Lembretes de {seguro(f.nome, 40)}**\n{descreve_lembretes(f)}",
        botoes=(
            (
                Botao(f"{marca(f.antes)} Véspera", f"fi:tb:{i}"),
                Botao(f"{marca(f.no_dia)} No dia", f"fi:to:{i}"),
                Botao(f"{marca(f.depois)} Depois", f"fi:ta:{i}"),
            ),
            (
                horario("morning", "🌅 Manhã"),
                horario("evening", "🌙 Noite"),
                horario("both", "🌅🌙 Ambos"),
            ),
            (Botao("✔️ Pronto", f"fi:pr:{i}"),),
        ),
        substitui=True,
    )


# ---------------------------------------------------------------------------
# Fluxo do /fixos
# ---------------------------------------------------------------------------
_ALTERNA = {"tb": "remind_before", "to": "remind_on_day", "ta": "remind_after"}
_HORARIO = {"hm": "morning", "he": "evening", "hb": "both"}


def trata(conn: db.Connection, ctx: Contexto, e: Entrada, p: Pessoa) -> Resultado:
    r = Resultado(rotulo="fixos", conta=p.account_id)
    if e.pergunta in PERGUNTAS:
        return _resposta(conn, e, p, r)
    partes = (e.acao or "").split(":")
    if e.comando == "fixos" or partes == ["fi", "lista"]:
        with db.account_context(conn, p.account_id) as cur:
            todos = lista(cur)
            emojis = _rotulos_categorias(cur)
        if not todos:
            return r.diz(t.FIXOS_VAZIO)
        botoes = [Botao(f"{MARCA} {f.nome[:24]}", f"fi:ed:{seg.curto(f.id)}") for f in todos]
        return r.diz(
            t.FIXOS_TITULO + "\n\n" + "\n".join(_linha(f, emojis) for f in todos),
            botoes=tuple(tuple(botoes[k : k + 2]) for k in range(0, len(botoes), 2)),
        )
    if len(partes) != 3:
        return r.diz(t.USE_OS_BOTOES)
    fixo_id = seg.longo(partes[2])
    acao = partes[1]
    r.rotulo = f"fixos.{acao}"
    with db.account_context(conn, p.account_id) as cur:
        # RLS: id de outra conta (botão forjado) não é encontrado.
        f = por_id(cur, fixo_id) if fixo_id else None
        if f is None:
            return r.diz(t.FIXO_SUMIU)
        emojis = _rotulos_categorias(cur)
        if acao in {"ed", "pr"}:
            saida = cartao(f, emojis)
            r.saidas.append(replace(saida, substitui=acao == "pr"))  # "Pronto": volta ao cartão
            return r
        if acao == "va":
            return r.diz(f"{t.PERGUNTAS['fi_valor']}\n{MARCA} {f.nome}", pergunta="fi_valor")
        if acao == "di":
            return r.diz(f"{t.PERGUNTAS['fi_dia']}\n{MARCA} {f.nome}", pergunta="fi_dia")
        if acao == "lb":
            r.saidas.append(_tela_lembretes(f))  # substitui=True: o cartão vira a tela
            return r
        if acao in _ALTERNA:
            atual = {"tb": f.antes, "to": f.no_dia, "ta": f.depois}[acao]
            atualiza(cur, f.id, _ALTERNA[acao], not atual)
        elif acao in _HORARIO:
            atualiza(cur, f.id, "remind_slot", _HORARIO[acao])
        if acao in _ALTERNA or acao in _HORARIO:
            novo = por_id(cur, f.id)
            r.saidas.append(_tela_lembretes(novo or f))
            return r
        if acao == "vt":
            atualiza(cur, f.id, "amount_kind", "estimated" if f.valor_tipo == "fixed" else "fixed")
        elif acao in {"pa", "at"}:
            atualiza(cur, f.id, "active", acao == "at")
        elif acao == "ap":
            i = seg.curto(f.id)
            return r.diz(
                t.FIXO_APAGAR_CONFIRMA.format(nome=seguro(f.nome, 40)),
                botoes=((Botao("🗑️ Apagar de vez", f"fi:ok:{i}"), Botao("Cancelar", f"fi:ed:{i}")),),
            )
        elif acao in {"ok", "un"}:
            apaga(cur, f.id)
            return r.diz(t.FIXO_DESFEITO if acao == "un" else t.FIXO_APAGADO)
        else:
            return r.diz(t.USE_OS_BOTOES)
        novo = por_id(cur, f.id)
        atualizado = cartao(novo or f, emojis, titulo=t.FIXO_ATUALIZADO)
        r.saidas.append(replace(atualizado, substitui=True))  # o cartão tocado se atualiza
    return r


def _resposta(conn: db.Connection, e: Entrada, p: Pessoa, r: Resultado) -> Resultado:
    nome = e.contexto.removeprefix(MARCA).strip()  # 2ª linha da pergunta: escrita pelo bot
    with db.account_context(conn, p.account_id) as cur:
        f = por_nome(cur, nome) if nome else None
        if f is None:
            return r.diz(t.FIXO_SUMIU)
        if e.pergunta == "fi_valor":
            valor = valores.interpreta(e.texto)
            if not valor.centavos:
                return r.diz(f"{t.PERGUNTAS['fi_valor']}\n{MARCA} {f.nome}", pergunta="fi_valor")
            atualiza(cur, f.id, "amount_cents", valor.centavos)
        else:
            dia = _dia_dito(e.texto)
            if not 1 <= dia <= 31:
                return r.diz(f"{t.PERGUNTAS['fi_dia']}\n{MARCA} {f.nome}", pergunta="fi_dia")
            atualiza(cur, f.id, "day_of_month", dia)
        novo = por_id(cur, f.id)
        r.saidas.append(cartao(novo or f, _rotulos_categorias(cur), titulo=t.FIXO_ATUALIZADO))
    return r


def _dia_dito(texto: str) -> int:
    """ "10", "dia 10", "dia doze" (áudio) → dia do mês; 0 se não entendeu."""
    achado = re.search(r"\b(\d{1,2})\b", texto)
    if achado:
        return int(achado.group(1))
    palavras = re.sub(r"[^\w\s]|\bdia\b", " ", texto, flags=re.IGNORECASE)  # "Dia doze."
    valor = valores.interpreta(palavras)
    centavos = valor.centavos or 0
    return centavos // 100 if centavos % 100 == 0 else 0

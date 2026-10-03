"""SQL dos lançamentos (S2.3). Tudo dentro de `db.account_context` (RLS forçado), menos o
medidor de uso da IA (tabela global, sem dado pessoal). SQL fixo e parametrizado.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from telegrana.core.interpretacao import CategoriaConta, Regra
from telegrana.infra import db

# forma devolvida pela IA/atalho → kind da tabela payment_methods
FORMAS = {
    "pix": "pix",
    "debito": "debit",
    "dinheiro": "cash",
    "credito": "credit",
    "boleto": "boleto",
    "poupanca": "savings",
}


@dataclass(frozen=True, slots=True)
class Categoria:
    id: uuid.UUID
    chave: str
    nome: str
    emoji: str
    tipo: str  # expense | income
    ativa: bool
    code: str | None

    @property
    def rotulo(self) -> str:
        return f"{self.emoji} {self.nome}"

    def para_ia(self) -> CategoriaConta:
        return CategoriaConta(self.chave, self.nome, self.emoji, self.tipo)


@dataclass(frozen=True, slots=True)
class Forma:
    id: uuid.UUID
    kind: str
    nome: str
    emoji: str


@dataclass(frozen=True, slots=True)
class Lancamento:
    id: uuid.UUID
    tipo: str
    centavos: int
    categoria_id: uuid.UUID | None
    forma_id: uuid.UUID | None
    destino_id: uuid.UUID | None
    data: date
    descricao: str | None
    status: str
    parcelas: int | None
    recorrente: bool | None
    apagado: bool
    criado: datetime
    origem: str = "text"  # text | audio | fixed | invoice
    texto_original: str | None = None  # mensagem ou transcrição (do próprio usuário)


_SELECT_LANC = (
    "select id, kind, amount_cents, category_id, payment_method_id, to_payment_method_id,"
    " cash_on, description, status, installments, recurring, deleted_at is not null,"
    " created_at, source, original_text from telegrana.transactions"
)


def categorias(cur: Any) -> list[Categoria]:
    rows = cur.execute(
        "select id, coalesce(code, name), name, emoji, kind, active, code"
        " from telegrana.categories order by kind, sort, lower(name)"
    ).fetchall()
    return [Categoria(*r) for r in rows]


def regras(cur: Any, todas: list[Categoria]) -> list[Regra]:
    chave = {c.id: c.chave for c in todas}
    rows = cur.execute("select pattern, category_id from telegrana.category_rules").fetchall()
    return [Regra(r[0], chave[r[1]]) for r in rows if r[1] in chave]


def formas(cur: Any) -> dict[str, Forma]:
    rows = cur.execute(
        "select id, kind, name, emoji from telegrana.payment_methods where active"
        " order by created_at"
    ).fetchall()
    resultado: dict[str, Forma] = {}
    for r in rows:
        resultado.setdefault(r[1], Forma(*r))  # a primeira de cada tipo
    return resultado


def forma_por_id(cur: Any, forma_id: uuid.UUID | None) -> Forma | None:
    if forma_id is None:
        return None
    row = cur.execute(
        "select id, kind, name, emoji from telegrana.payment_methods where id = %s", (forma_id,)
    ).fetchone()
    return Forma(*row) if row else None


def grava(
    cur: Any,
    account_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    tipo: str,
    centavos: int,
    categoria_id: uuid.UUID | None,
    forma_id: uuid.UUID | None,
    destino_id: uuid.UUID | None,
    data: date,
    futura: bool,
    descricao: str | None,
    origem: str,
    texto_original: str,
    parcelas: int | None,
) -> uuid.UUID:
    row = cur.execute(
        "insert into telegrana.transactions (account_id, user_id, kind, amount_cents,"
        " category_id, payment_method_id, to_payment_method_id, occurred_on, cash_on,"
        " description, source, original_text, status, installments)"
        " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id",
        (
            account_id,
            user_id,
            tipo,
            centavos,
            categoria_id,
            forma_id,
            destino_id,
            data,
            data,
            (descricao or None) and descricao[:200],
            origem,
            texto_original[:1000],
            "planned" if futura else "done",
            parcelas,
        ),
    ).fetchone()
    return uuid.UUID(str(row[0]))


def lancamento(cur: Any, tx_id: uuid.UUID) -> Lancamento | None:
    row = cur.execute(
        _SELECT_LANC + " where id = %s",
        (tx_id,),
    ).fetchone()
    return Lancamento(*row) if row else None


def ultimo(cur: Any, user_id: uuid.UUID, minutos: int = 24 * 60) -> Lancamento | None:
    row = cur.execute(
        _SELECT_LANC + " where user_id = %s and deleted_at is null"
        " and created_at > now() - make_interval(mins => %s)"
        " order by created_at desc limit 1",
        (user_id, minutos),
    ).fetchone()
    return Lancamento(*row) if row else None


_CAMPOS = {
    "amount_cents": "update telegrana.transactions set amount_cents = %s, updated_at = now() where id = %s",
    "category_id": "update telegrana.transactions set category_id = %s, updated_at = now() where id = %s",
    "payment_method_id": "update telegrana.transactions set payment_method_id = %s, updated_at = now() where id = %s",
    "cash_on": "update telegrana.transactions set cash_on = %s, occurred_on = %s, updated_at = now() where id = %s",
    "recurring": "update telegrana.transactions set recurring = %s, updated_at = now() where id = %s",
    "description": "update telegrana.transactions set description = %s, updated_at = now() where id = %s",
    "deleted": "update telegrana.transactions set deleted_at = case when %s then now() end, updated_at = now() where id = %s",
}


def atualiza(cur: Any, tx_id: uuid.UUID, campo: str, valor: object) -> None:
    sql = _CAMPOS[campo]  # lista fixa: nada vem de fora
    if campo == "cash_on":
        cur.execute(sql, (valor, valor, tx_id))
    else:
        cur.execute(sql, (valor, tx_id))


def cria_categoria(
    cur: Any, account_id: uuid.UUID, tipo: str, nome: str, emoji: str
) -> uuid.UUID | None:
    from psycopg import errors

    try:
        with cur.connection.transaction():
            row = cur.execute(
                "insert into telegrana.categories (account_id, kind, name, emoji)"
                " values (%s, %s, %s, %s) returning id",
                (account_id, tipo, nome, emoji),
            ).fetchone()
    except errors.UniqueViolation:
        row = cur.execute(
            "select id from telegrana.categories where lower(name) = lower(%s)", (nome,)
        ).fetchone()
    return uuid.UUID(str(row[0])) if row else None


def aprende(cur: Any, account_id: uuid.UUID, padrao: str, categoria_id: uuid.UUID) -> None:
    cur.execute(
        "insert into telegrana.category_rules (account_id, pattern, category_id)"
        " values (%s, %s, %s)"
        " on conflict (account_id, pattern) do update set category_id = excluded.category_id",
        (account_id, padrao, categoria_id),
    )


# ---------------------------------------------------------------------------
# Rascunhos (lançamento entendido esperando resposta)
# ---------------------------------------------------------------------------
def cria_rascunho(
    cur: Any, account_id: uuid.UUID, user_id: uuid.UUID, dados: dict[str, Any], pendencia: str
) -> uuid.UUID:
    row = cur.execute(
        "insert into telegrana.pending_entries (account_id, user_id, data, pendencia)"
        " values (%s, %s, %s, %s) returning id",
        (account_id, user_id, json.dumps(dados, ensure_ascii=False), pendencia),
    ).fetchone()
    return uuid.UUID(str(row[0]))


def rascunho(cur: Any, rascunho_id: uuid.UUID) -> tuple[dict[str, Any], str] | None:
    row = cur.execute(
        "select data, pendencia from telegrana.pending_entries"
        " where id = %s and expires_at > now()",
        (rascunho_id,),
    ).fetchone()
    return (dict(row[0]), row[1]) if row else None


def rascunho_mais_recente(
    cur: Any, user_id: uuid.UUID, pendencia: str
) -> tuple[uuid.UUID, dict[str, Any]] | None:
    row = cur.execute(
        "select id, data from telegrana.pending_entries"
        " where user_id = %s and pendencia = %s and expires_at > now()"
        " order by created_at desc limit 1",
        (user_id, pendencia),
    ).fetchone()
    return (uuid.UUID(str(row[0])), dict(row[1])) if row else None


def apaga_rascunho(cur: Any, rascunho_id: uuid.UUID) -> None:
    cur.execute("delete from telegrana.pending_entries where id = %s", (rascunho_id,))


# ---------------------------------------------------------------------------
# Correção pendente (✏️ Corrigir): a próxima mensagem corrige aquele lançamento
# ---------------------------------------------------------------------------
def marca_correcao(cur: Any, account_id: uuid.UUID, user_id: uuid.UUID, tx_id: uuid.UUID) -> None:
    limpa_correcao(cur, user_id)
    cria_rascunho(cur, account_id, user_id, {"tx": str(tx_id)}, "corrigir")


def correcao_pendente(cur: Any, user_id: uuid.UUID, minutos: int = 10) -> uuid.UUID | None:
    row = cur.execute(
        "select data->>'tx' from telegrana.pending_entries"
        " where user_id = %s and pendencia = 'corrigir'"
        " and created_at > now() - make_interval(mins => %s)"
        " order by created_at desc limit 1",
        (user_id, minutos),
    ).fetchone()
    try:
        return uuid.UUID(str(row[0])) if row and row[0] else None
    except ValueError:
        return None


def limpa_correcao(cur: Any, user_id: uuid.UUID) -> None:
    cur.execute(
        "delete from telegrana.pending_entries where user_id = %s and pendencia = 'corrigir'",
        (user_id,),
    )


# ---------------------------------------------------------------------------
# Recibo ↔ lançamento
# ---------------------------------------------------------------------------
def guarda_refs(
    conn: db.Connection, account_id: uuid.UUID, canal: str, refs: list[tuple[str, str]]
) -> None:
    with db.account_context(conn, account_id) as cur:
        for ref, mensagem_id in refs:
            tipo, _, valor = ref.partition(":")
            if tipo != "tx":
                continue
            cur.execute(
                "insert into telegrana.message_refs (account_id, channel, message_id,"
                " transaction_id) values (%s, %s, %s, %s) on conflict do nothing",
                (account_id, canal, mensagem_id, uuid.UUID(valor)),
            )


def lancamento_do_recibo(cur: Any, canal: str, mensagem_id: str) -> uuid.UUID | None:
    row = cur.execute(
        "select transaction_id from telegrana.message_refs where channel = %s and message_id = %s",
        (canal, mensagem_id),
    ).fetchone()
    return uuid.UUID(str(row[0])) if row else None


# ---------------------------------------------------------------------------
# Medidor de uso da IA (global; D038)
# ---------------------------------------------------------------------------
_USO = {
    "tokens": (
        "insert into telegrana.ai_usage (day, model, requests, tokens) values (%s, %s, 1, %s)"
        " on conflict (day, model) do update set requests = ai_usage.requests + 1,"
        " tokens = ai_usage.tokens + excluded.tokens"
        " returning tokens, alerted_at"
    ),
    "segundos": (
        "insert into telegrana.ai_usage (day, model, requests, audio_seconds)"
        " values (%s, %s, 1, %s)"
        " on conflict (day, model) do update set requests = ai_usage.requests + 1,"
        " audio_seconds = ai_usage.audio_seconds + excluded.audio_seconds"
        " returning audio_seconds, alerted_at"
    ),
}


def registra_uso(
    conn: db.Connection,
    dia: date,
    modelo: str,
    quantidade: int,
    limite: int,
    alerta: float,
    medida: str = "tokens",
) -> int | None:
    """Soma o uso do dia (tokens ou segundos de áudio). Devolve o percentual se acabou de
    passar do alerta (uma vez por dia e modelo)."""
    with conn.transaction():
        row = conn.execute(_USO[medida], (dia, modelo, quantidade)).fetchone()
        if row is None or row[1] is not None or row[0] < limite * alerta:
            return None
        conn.execute(
            "update telegrana.ai_usage set alerted_at = now() where day = %s and model = %s",
            (dia, modelo),
        )
    return round(100 * int(row[0]) / limite)

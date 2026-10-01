"""Acesso ao banco do cadastro (S1.4). SQL fixo e parametrizado; nada vem da IA.

Antes de a conta ser conhecida, só as funções SECURITY DEFINER da 0001/0002 e as
tabelas globais. Depois, tudo dentro de `db.account_context` (RLS forçado).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from telegrana.infra import db


@dataclass(frozen=True, slots=True)
class Identidade:
    user_id: uuid.UUID
    account_id: uuid.UUID
    status: str


@dataclass(frozen=True, slots=True)
class Pessoa:
    user_id: uuid.UUID
    account_id: uuid.UUID
    full_name: str | None
    tem_telefone: bool
    adult_declared_at: datetime | None
    onboarding_step: str
    status: str
    conta_status: str
    invite_link_id: uuid.UUID | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Pedido:
    id: uuid.UUID
    channel: str
    external_id: str
    display_name: str
    username: str | None
    message: str
    status: str
    kind: str


# ---------------------------------------------------------------------------
# Identidade (antes da conta)
# ---------------------------------------------------------------------------
def identidade(conn: db.Connection, canal: str, external_id: str) -> Identidade | None:
    with conn.transaction():
        row = conn.execute(
            "select o_user_id, o_account_id, o_user_status from telegrana.resolve_identity(%s, %s)",
            (canal, external_id),
        ).fetchone()
    return Identidade(*row) if row else None


def inicia_cadastro(conn: db.Connection, canal: str, external_id: str) -> Identidade:
    with conn.transaction():
        row = conn.execute(
            "select o_user_id, o_account_id from telegrana.start_onboarding(%s, %s)",
            (canal, external_id),
        ).fetchone()
    if row is None:
        raise RuntimeError("start_onboarding sem retorno")
    return Identidade(row[0], row[1], "onboarding")


def busca_por_telefone(conn: db.Connection, phone_hmac: bytes) -> Identidade | None:
    with conn.transaction():
        row = conn.execute(
            "select o_user_id, o_account_id, o_status from telegrana.find_user_by_phone(%s)",
            (phone_hmac,),
        ).fetchone()
    return Identidade(*row) if row else None


def busca_codigo(conn: db.Connection, seletor: str) -> tuple[Identidade, str] | None:
    with conn.transaction():
        row = conn.execute(
            "select o_user_id, o_account_id, o_verifier_hash from telegrana.recovery_lookup(%s)",
            (seletor,),
        ).fetchone()
    if row is None:
        return None
    return Identidade(row[0], row[1], "active"), row[2]


def religa(
    conn: db.Connection, canal: str, external_id: str, user_id: uuid.UUID
) -> tuple[str, uuid.UUID | None, str | None]:
    """('ok' | 'same' | 'in_use' | 'missing', conta, identidade antiga)."""
    with conn.transaction():
        row = conn.execute(
            "select o_result, o_account_id, o_old_external_id"
            " from telegrana.relink_identity(%s, %s, %s)",
            (canal, external_id, user_id),
        ).fetchone()
    if row is None:
        raise RuntimeError("relink_identity sem retorno")
    return row[0], row[1], row[2]


def lista_pessoas(conn: db.Connection) -> list[tuple[uuid.UUID, uuid.UUID, str, str]]:
    """(conta, pessoa, nome, situação) — só para o admin."""
    with conn.transaction():
        rows = conn.execute(
            "select o_account_id, o_user_id, coalesce(o_full_name, '?'), o_status"
            " from telegrana.admin_list_users()"
        ).fetchall()
    return [(r[0], r[1], r[2], r[3]) for r in rows]


def limpa_cadastros_velhos(conn: db.Connection, dias: int) -> int:
    with conn.transaction():
        row = conn.execute(
            "select telegrana.purge_stale_onboarding(make_interval(days => %s))", (dias,)
        ).fetchone()
    return int(row[0]) if row else 0


# ---------------------------------------------------------------------------
# Dentro da conta (cursor de db.account_context)
# ---------------------------------------------------------------------------
def pessoa(cur: Any, account_id: uuid.UUID) -> Pessoa:
    row = cur.execute(
        "select u.id, m.account_id, u.full_name, u.phone_hmac is not null,"
        " u.adult_declared_at, u.onboarding_step, u.status, a.status, a.invite_link_id,"
        " a.created_at"
        " from telegrana.account_members m"
        " join telegrana.users u on u.id = m.user_id"
        " join telegrana.accounts a on a.id = m.account_id"
        " where m.account_id = %s and m.role = 'owner'",
        (account_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("conta sem dono")
    return Pessoa(*row)


def atualiza_pessoa(cur: Any, user_id: uuid.UUID, **campos: object) -> None:
    permitidos = {"full_name", "phone_hmac", "adult_declared_at", "onboarding_step", "status"}
    if not campos or not set(campos) <= permitidos:
        raise ValueError(f"campos inválidos: {sorted(campos)}")
    cur.execute(
        sql.SQL("update telegrana.users set {}, updated_at = now() where id = %(id)s").format(
            _atribuicoes(campos)
        ),
        {**campos, "id": user_id},
    )


def atualiza_conta(cur: Any, account_id: uuid.UUID, **campos: object) -> None:
    permitidos = {"status", "invite_link_id"}
    if not campos or not set(campos) <= permitidos:
        raise ValueError(f"campos inválidos: {sorted(campos)}")
    cur.execute(
        sql.SQL("update telegrana.accounts set {} where id = %(id)s").format(_atribuicoes(campos)),
        {**campos, "id": account_id},
    )


def _atribuicoes(campos: dict[str, object]) -> sql.Composed:
    """`coluna = %(coluna)s, ...` com identificadores citados (colunas de lista fixa)."""
    return sql.SQL(", ").join(
        sql.SQL("{} = {}").format(sql.Identifier(c), sql.Placeholder(c)) for c in sorted(campos)
    )


def aceites(cur: Any) -> dict[str, tuple[int, datetime]]:
    """Última versão aceita de cada documento: {doc: (versão, data)}."""
    rows = cur.execute(
        "select distinct on (doc) doc, version, accepted_at from telegrana.terms_acceptances"
        " order by doc, version desc"
    ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def registra_aceite(
    cur: Any, account_id: uuid.UUID, user_id: uuid.UUID, doc: str, versao: int, sha: bytes
) -> None:
    cur.execute(
        "insert into telegrana.terms_acceptances"
        " (account_id, user_id, doc, version, content_sha256) values (%s, %s, %s, %s, %s)"
        " on conflict do nothing",
        (account_id, user_id, doc, versao, sha),
    )


def troca_codigo(
    cur: Any, account_id: uuid.UUID, user_id: uuid.UUID, seletor: str, verificador_hash: str
) -> None:
    cur.execute("delete from telegrana.recovery_codes where user_id = %s", (user_id,))
    cur.execute(
        "insert into telegrana.recovery_codes (account_id, user_id, selector, verifier_hash)"
        " values (%s, %s, %s, %s)",
        (account_id, user_id, seletor, verificador_hash),
    )


def tem_codigo(cur: Any) -> datetime | None:
    row = cur.execute("select created_at from telegrana.recovery_codes").fetchone()
    return row[0] if row else None


def semeia_padroes(cur: Any, account_id: uuid.UUID) -> None:
    """Categorias e formas de pagamento padrão (0003; idempotente)."""
    cur.execute("select telegrana.seed_account_defaults(%s)", (account_id,))


def apaga_conta(cur: Any, account_id: uuid.UUID) -> None:
    cur.execute("select telegrana.erase_account(%s)", (account_id,))


def audita(
    conn_ou_cur: Any,
    evento: str,
    *,
    account_id: uuid.UUID | None = None,
    ator: str = "user",
    detalhes: dict[str, str] | None = None,
) -> None:
    """Auditoria sem dado pessoal: só ids técnicos, evento e detalhes fixos."""
    conn_ou_cur.execute(
        "insert into telegrana.audit_log (account_id, actor, event, details)"
        " values (%s, %s, %s, %s)",
        (account_id, ator, evento, Jsonb(detalhes or {})),
    )


# ---------------------------------------------------------------------------
# Convites (tabela global)
# ---------------------------------------------------------------------------
def convite_valido(conn: db.Connection, token_sha: bytes) -> uuid.UUID | None:
    with conn.transaction():
        row = conn.execute(
            "select id from telegrana.invite_links where token_sha256 = %s"
            " and revoked_at is null and uses < max_uses"
            " and (expires_at is null or expires_at > now())",
            (token_sha,),
        ).fetchone()
    return row[0] if row else None


def usa_convite(cur: Any, invite_id: uuid.UUID) -> None:
    cur.execute(
        "update telegrana.invite_links set uses = uses + 1 where id = %s and uses < max_uses",
        (invite_id,),
    )


def convite_ativo(conn: db.Connection) -> tuple[uuid.UUID, int, int, datetime] | None:
    with conn.transaction():
        row = conn.execute(
            "select id, uses, max_uses, created_at from telegrana.invite_links"
            " where revoked_at is null order by created_at desc limit 1"
        ).fetchone()
    return (row[0], row[1], row[2], row[3]) if row else None


def revoga_convites(conn: db.Connection) -> int:
    with conn.transaction():
        n = conn.execute(
            "update telegrana.invite_links set revoked_at = now() where revoked_at is null"
        ).rowcount
        if n:
            audita(conn, "invite.revoked", ator="admin")
    return n


def cria_convite(conn: db.Connection, token_sha: bytes, max_usos: int) -> None:
    with conn.transaction():
        conn.execute(
            "update telegrana.invite_links set revoked_at = now() where revoked_at is null"
        )
        conn.execute(
            "insert into telegrana.invite_links (token_sha256, max_uses) values (%s, %s)",
            (token_sha, max_usos),
        )
        audita(conn, "invite.created", ator="admin")


# ---------------------------------------------------------------------------
# Pedidos de acesso e de recuperação (tabela global)
# ---------------------------------------------------------------------------


def pedido_da_pessoa(conn: db.Connection, canal: str, external_id: str) -> Pedido | None:
    with conn.transaction():
        row = conn.execute(
            "select id, channel, external_id, display_name, username, message, status, kind"
            " from telegrana.access_requests"
            " where channel = %s and external_id = %s and expires_at > now()"
            " order by created_at desc limit 1",
            (canal, external_id),
        ).fetchone()
    return Pedido(*row) if row else None


def pedido(conn: db.Connection, pedido_id: uuid.UUID) -> Pedido | None:
    with conn.transaction():
        row = conn.execute(
            "select id, channel, external_id, display_name, username, message, status, kind"
            " from telegrana.access_requests where id = %s and expires_at > now()",
            (pedido_id,),
        ).fetchone()
    return Pedido(*row) if row else None


def pedidos_na_ultima_hora(conn: db.Connection) -> int:
    with conn.transaction():
        row = conn.execute(
            "select count(*) from telegrana.access_requests"
            " where created_at > now() - interval '1 hour'"
        ).fetchone()
    return int(row[0]) if row else 0


def cria_pedido(
    conn: db.Connection,
    canal: str,
    external_id: str,
    nome: str,
    username: str | None,
    mensagem: str,
    tipo: str,
) -> uuid.UUID | None:
    """None se já houver um pedido pendente desta pessoa (índice único)."""
    with conn.transaction():
        row = conn.execute(
            "insert into telegrana.access_requests"
            " (channel, external_id, display_name, username, message, kind)"
            " values (%s, %s, %s, %s, %s, %s) on conflict do nothing returning id",
            (canal, external_id, nome, username, mensagem, tipo),
        ).fetchone()
    return row[0] if row else None


def decide_pedido(conn: db.Connection, pedido_id: uuid.UUID, situacao: str) -> bool:
    with conn.transaction():
        n = conn.execute(
            "update telegrana.access_requests set status = %s, decided_at = now()"
            " where id = %s and status = 'pending' and expires_at > now()",
            (situacao, pedido_id),
        ).rowcount
    return n == 1


def apaga_pedido(conn: db.Connection, pedido_id: uuid.UUID) -> None:
    with conn.transaction():
        conn.execute("delete from telegrana.access_requests where id = %s", (pedido_id,))


def apaga_pedidos_da_pessoa(cur: Any, canal: str, external_id: str) -> None:
    cur.execute(
        "delete from telegrana.access_requests where channel = %s and external_id = %s",
        (canal, external_id),
    )


# ---------------------------------------------------------------------------
# Travas de tentativas (tabela global)
# ---------------------------------------------------------------------------
def travado_ate(conn: db.Connection, canal: str, external_id: str, tipo: str) -> datetime | None:
    with conn.transaction():
        row = conn.execute(
            "select locked_until from telegrana.auth_attempts"
            " where channel = %s and external_id = %s and kind = %s and locked_until > now()",
            (canal, external_id, tipo),
        ).fetchone()
    return row[0] if row else None


def registra_falha(conn: db.Connection, canal: str, external_id: str, tipo: str) -> int:
    with conn.transaction():
        row = conn.execute(
            "insert into telegrana.auth_attempts (channel, external_id, kind, failures)"
            " values (%s, %s, %s, 1)"
            " on conflict (channel, external_id, kind) do update"
            " set failures = auth_attempts.failures + 1, updated_at = now()"
            " returning failures",
            (canal, external_id, tipo),
        ).fetchone()
    return int(row[0]) if row else 1


def trava(conn: db.Connection, canal: str, external_id: str, tipo: str, segundos: int) -> None:
    with conn.transaction():
        conn.execute(
            "update telegrana.auth_attempts set locked_until = now() + make_interval(secs => %s),"
            " updated_at = now() where channel = %s and external_id = %s and kind = %s",
            (segundos, canal, external_id, tipo),
        )


def zera_falhas(conn: db.Connection, canal: str, external_id: str, tipo: str) -> None:
    with conn.transaction():
        conn.execute(
            "delete from telegrana.auth_attempts"
            " where channel = %s and external_id = %s and kind = %s",
            (canal, external_id, tipo),
        )

"""Conexões com o Postgres e contexto de conta para o RLS (PLANO 8.2).

Toda consulta a dados de uma conta acontece dentro de `account_context`, que define
`app.account_id` só para a transação corrente (`set_config(..., true)`). Sem esse
contexto, as políticas de RLS não deixam o papel `telegrana_app` enxergar nada.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import certifi
import psycopg
from psycopg.conninfo import conninfo_to_dict

# Hosts sem TLS aceitos apenas para o Postgres local/efêmero do CI.
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

type Connection = psycopg.Connection[tuple[Any, ...]]


def connect(
    url: str,
    *,
    autocommit: bool = False,
    application_name: str = "telegrana",
) -> Connection:
    """Abre uma conexão. Fora de localhost, exige TLS com verificação completa."""
    host = str(conninfo_to_dict(url).get("host") or "")  # aceita URL e "chave=valor"
    options: dict[str, Any] = {"connect_timeout": 10, "application_name": application_name}
    if host not in _LOCAL_HOSTS:
        options |= {"sslmode": "verify-full", "sslrootcert": certifi.where()}
    return psycopg.connect(url, autocommit=autocommit, **options)


@contextmanager
def account_context(conn: Connection, account_id: uuid.UUID) -> Iterator[psycopg.Cursor[Any]]:
    """Transação com o RLS apontado para `account_id`.

    O `account_id` precisa vir da identidade verificada do canal (regra de ouro 4),
    nunca de texto do usuário, de botão ou da IA.
    """
    if not isinstance(account_id, uuid.UUID):  # defesa contra chamada com str/int
        raise TypeError("account_id deve ser uuid.UUID")
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("select set_config('app.account_id', %s, true)", (str(account_id),))
        yield cur

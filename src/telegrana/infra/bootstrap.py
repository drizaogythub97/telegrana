"""Criação dos papéis do banco (feita uma vez por banco, com o papel dono).

- `telegrana_migrator`: dono do esquema e das tabelas; só roda migrações (pipeline).
- `telegrana_app`: usado pelo bot. Não é dono de nada, não tem BYPASSRLS e só recebe
  os privilégios concedidos tabela a tabela nas migrações.

Funciona no Neon (papel `neondb_owner`, que tem CREATEROLE) e no Postgres do CI
(superusuário). Não altera atributos como SUPERUSER/BYPASSRLS: os papéis nascem sem
eles (padrão do CREATE ROLE) e os testes de isolamento conferem.
"""

from __future__ import annotations

from psycopg import sql

from telegrana.infra.db import Connection

ROLE_MIGRATOR = "telegrana_migrator"
ROLE_APP = "telegrana_app"
SCHEMA = "telegrana"


def bootstrap_roles(
    admin: Connection, database: str, *, migrator_password: str, app_password: str
) -> None:
    """Cria (ou atualiza a senha de) os papéis e concede acesso ao banco `database`.

    `admin` precisa estar em autocommit e conectado a `database`.
    """
    if len(migrator_password) < 20 or len(app_password) < 20:
        raise ValueError("senhas de papel precisam de pelo menos 20 caracteres aleatórios")

    for role, password in ((ROLE_MIGRATOR, migrator_password), (ROLE_APP, app_password)):
        exists = admin.execute("select 1 from pg_roles where rolname = %s", (role,)).fetchone()
        verb = sql.SQL("ALTER" if exists else "CREATE")
        admin.execute(
            sql.SQL("{} ROLE {} WITH LOGIN PASSWORD {}").format(
                verb, sql.Identifier(role), sql.Literal(password)
            )
        )

    app, migrator = sql.Identifier(ROLE_APP), sql.Identifier(ROLE_MIGRATOR)
    db, schema = sql.Identifier(database), sql.Identifier(SCHEMA)
    statements = [
        # O app tem teto de conexões e de tempo por consulta.
        sql.SQL("ALTER ROLE {} CONNECTION LIMIT 10").format(app),
        sql.SQL("ALTER ROLE {} SET statement_timeout = '5s'").format(app),
        sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '10s'").format(app),
        sql.SQL("ALTER ROLE {} SET search_path = {}").format(app, schema),
        sql.SQL("ALTER ROLE {} SET search_path = {}").format(migrator, schema),
        # O migrator cria o esquema na primeira migração; o app só conecta.
        sql.SQL("GRANT CONNECT, CREATE ON DATABASE {} TO {}").format(db, migrator),
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(db, app),
    ]
    for statement in statements:
        admin.execute(statement)

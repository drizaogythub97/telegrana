"""Executor de migrações SQL versionadas (D030).

- Arquivos em `telegrana/infra/migrations/NNNN_nome.sql`, aplicados em ordem, cada um
  na sua transação.
- `schema_migrations` guarda o SHA-256 de cada arquivo aplicado: mudar uma migração
  que já rodou é erro (crie uma nova).
- Trava consultiva evita duas execuções simultâneas (ex.: dois deploys).
- Roda com o papel `telegrana_migrator`, só no pipeline.

Uso: `TELEGRANA_MIGRATOR_URL=... python -m telegrana.infra.migrate`
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from telegrana.infra.db import Connection, connect

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).with_name("migrations")
_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
_LOCK_KEY = 0x7E1E_62A4  # chave fixa da trava consultiva das migrações


class MigrationError(RuntimeError):
    """Migração inválida, alterada depois de aplicada ou fora de ordem."""


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    sql: str
    checksum: str


def discover(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Lê e valida as migrações: nomes no padrão e versões contínuas a partir de 1."""
    migrations: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        match = _NAME.match(path.name)
        if not match:
            raise MigrationError(f"nome de migração fora do padrão NNNN_nome.sql: {path.name}")
        body = path.read_bytes()
        migrations.append(
            Migration(
                version=int(match.group(1)),
                name=path.name,
                sql=body.decode("utf-8"),
                checksum=hashlib.sha256(body).hexdigest(),
            )
        )
    expected = list(range(1, len(migrations) + 1))
    if [m.version for m in migrations] != expected:
        raise MigrationError("versões de migração precisam ser contínuas: 0001, 0002, ...")
    return migrations


def migrate(
    conn: Connection, directory: Path = MIGRATIONS_DIR, *, ate: int | None = None
) -> list[str]:
    """Aplica as migrações pendentes (até a versão `ate`, se dada — restauração de backup).
    Devolve os nomes aplicados nesta execução."""
    migrations = [m for m in discover(directory) if ate is None or m.version <= ate]
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
        conn.execute("create schema if not exists telegrana")
        conn.execute(
            """
            create table if not exists telegrana.schema_migrations (
                version    integer primary key,
                name       text not null,
                checksum   text not null,
                applied_at timestamptz not null default now()
            )
            """
        )

    applied_now: list[str] = []
    for migration in migrations:
        with conn.transaction():
            conn.execute("select pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
            row = conn.execute(
                "select checksum from telegrana.schema_migrations where version = %s",
                (migration.version,),
            ).fetchone()
            if row is not None:
                if row[0] != migration.checksum:
                    raise MigrationError(
                        f"{migration.name} foi alterada depois de aplicada; crie uma nova migração"
                    )
                continue
            # Arquivo com várias instruções: executado sem parâmetros (protocolo simples).
            conn.execute(migration.sql.encode("utf-8"))
            conn.execute(
                "insert into telegrana.schema_migrations (version, name, checksum) values (%s, %s, %s)",
                (migration.version, migration.name, migration.checksum),
            )
            applied_now.append(migration.name)
            log.info("migração aplicada: %s", migration.name)
    return applied_now


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    url = os.environ.get("TELEGRANA_MIGRATOR_URL", "")
    if not url:
        log.error("defina TELEGRANA_MIGRATOR_URL (papel telegrana_migrator)")
        return 2
    with connect(url, application_name="telegrana-migrate") as conn:
        applied = migrate(conn)
    log.info("%d migração(ões) aplicada(s)", len(applied))
    return 0


if __name__ == "__main__":
    sys.exit(main())

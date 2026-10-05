"""Fixtures compartilhadas.

`banco`: cria um banco descartável, os papéis (migrator e app), aplica as migrações e
apaga o banco no fim da sessão de testes. Precisa de TELEGRANA_TEST_DATABASE_URL com
um papel que possa criar bancos e papéis (superusuário do CI ou o dono de uma branch
de testes do Neon — nunca dev nem produção).
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from telegrana.infra import bootstrap, db, migrate

RAIZ = Path(__file__).resolve().parents[1]


def _url_de_teste() -> str:
    url = os.environ.get("TELEGRANA_TEST_DATABASE_URL", "")
    if url:
        return url
    # Conveniência local: lê do .env.local (nunca exibido).
    arquivo = RAIZ / ".env.local"
    if arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8-sig").splitlines():
            chave, _, valor = linha.partition("=")
            if chave.strip() == "TELEGRANA_TEST_DATABASE_URL":
                return valor.strip()
    return ""


@dataclass(frozen=True)
class Banco:
    # repr=False: uma falha de teste não pode imprimir as URLs (têm senha) na saída do pytest.
    admin: str = field(repr=False)  # dono do banco descartável
    migrator: str = field(repr=False)
    app: str = field(repr=False)


@pytest.fixture(scope="session")
def banco() -> Iterator[Banco]:
    url = _url_de_teste()
    if not url:
        pytest.skip("TELEGRANA_TEST_DATABASE_URL não definida")

    nome = f"telegrana_t_{secrets.token_hex(4)}"
    with db.connect(url, autocommit=True) as adm:
        adm.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    admin_url = make_conninfo(url, dbname=nome)
    try:
        senhas = {papel: secrets.token_urlsafe(24) for papel in ("migrator", "app")}
        with db.connect(admin_url, autocommit=True) as adm:
            bootstrap.bootstrap_roles(
                adm, nome, migrator_password=senhas["migrator"], app_password=senhas["app"]
            )
        migrator_url = make_conninfo(
            admin_url, user=bootstrap.ROLE_MIGRATOR, password=senhas["migrator"]
        )
        app_url = make_conninfo(admin_url, user=bootstrap.ROLE_APP, password=senhas["app"])
        with db.connect(migrator_url) as conn:
            migrate.migrate(conn)
        yield Banco(admin=admin_url, migrator=migrator_url, app=app_url)
    finally:
        with db.connect(url, autocommit=True) as adm:
            adm.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome))
            )

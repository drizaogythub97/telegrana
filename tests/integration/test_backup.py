"""Backup (S8, D052) contra Postgres real: exporta todas as contas com o papel de backup
(só leitura), cifra, abre e restaura num banco novo com as mesmas linhas."""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from dataclasses import replace

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from telegrana.core.contexto import agora
from telegrana.infra import backup, bootstrap, db, migrate
from tests.conftest import Banco
from tests.integration.test_cadastro import CTX, Bot, conn
from tests.integration.test_lancamentos import IAFalsa, conta

pytestmark = pytest.mark.integration
__all__ = ["conn"]


@pytest.fixture(scope="module")
def backup_url(banco: Banco) -> str:
    senha = secrets.token_urlsafe(24)
    nome = str(conninfo_to_dict(banco.admin)["dbname"])
    with db.connect(banco.admin, autocommit=True) as adm:
        bootstrap.bootstrap_backup_role(adm, nome, senha)
    return make_conninfo(banco.admin, user=bootstrap.ROLE_BACKUP, password=senha)


@pytest.fixture
def com_duas_contas(conn: db.Connection) -> tuple[str, str]:
    bot = Bot(conn, replace(CTX, extrator=IAFalsa()))
    a, b = conta(bot), conta(bot)
    bot(a, texto="mercado 45,90 no pix")
    bot(b, texto="uber 18 ontem")
    bot(b, texto="tênis 600 em 3x no credito")
    return a, b


def test_backup_le_todas_as_contas_e_nao_escreve(
    backup_url: str, com_duas_contas: tuple[str, str], banco: Banco
) -> None:
    with db.connect(backup_url) as c:
        pacote = backup.exporta(c, agora())
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            c.execute("create temp table tentativa (x int)")  # toda transação dele é só leitura
    with db.connect(banco.migrator) as m:
        esperado = m.execute("select count(*) from telegrana.transactions").fetchone()
        contas = m.execute("select count(*) from telegrana.accounts").fetchone()
    assert esperado is not None
    assert contas is not None
    assert pacote.tabelas["transactions"] == esperado[0] > 0
    assert pacote.tabelas["accounts"] == contas[0] >= 2
    assert "processed_updates" not in pacote.tabelas


@pytest.fixture
def banco_vazio(banco: Banco) -> Iterator[str]:
    """Banco novo no mesmo servidor, migrado pelos papéis que já existem (sem trocar senha)."""
    nome = f"telegrana_r_{secrets.token_hex(4)}"
    with db.connect(banco.admin, autocommit=True) as adm:
        adm.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    try:
        admin = make_conninfo(banco.admin, dbname=nome)
        with db.connect(admin, autocommit=True) as adm:
            for papel, privilegio in (
                (bootstrap.ROLE_MIGRATOR, "CONNECT, CREATE"),
                (bootstrap.ROLE_APP, "CONNECT"),
                (bootstrap.ROLE_BACKUP, "CONNECT"),
            ):
                adm.execute(
                    sql.SQL("GRANT {} ON DATABASE {} TO {}").format(
                        sql.SQL(privilegio), sql.Identifier(nome), sql.Identifier(papel)
                    )
                )
        yield make_conninfo(banco.migrator, dbname=nome)
    finally:
        with db.connect(banco.admin, autocommit=True) as adm:
            adm.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome))
            )


def test_ida_e_volta_completa(
    backup_url: str, com_duas_contas: tuple[str, str], banco_vazio: str
) -> None:
    privada, publica = backup.gera_chaves()
    with db.connect(backup_url) as c:
        pacote = backup.exporta(c, agora())
    aberto = backup.abre(backup.cifra(pacote.dados, publica), privada)
    with db.connect(banco_vazio) as m:
        migrate.migrate(m, ate=pacote.esquema)
        contagens = backup.restaura(m, aberto)
        with pytest.raises(backup.ErroBackup, match="não está vazio"):
            backup.restaura(m, aberto)  # não restaura por cima de dados
    esperado = {n: q for n, q in pacote.tabelas.items() if n != "schema_migrations"}
    assert contagens == esperado
    with db.connect(banco_vazio) as m:  # o RLS forçado voltou em todas as tabelas
        soltas = m.execute(
            "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace"
            " where n.nspname = 'telegrana' and c.relrowsecurity and not c.relforcerowsecurity"
        ).fetchall()
    assert soltas == []

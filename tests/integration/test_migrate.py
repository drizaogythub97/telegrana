"""Executor de migrações: ordem, checksum, idempotência."""

from __future__ import annotations

from pathlib import Path

import pytest

from telegrana.infra import db, migrate
from tests.conftest import Banco

pytestmark = pytest.mark.integration


def test_migracoes_do_repositorio_sao_validas() -> None:
    migracoes = migrate.discover()
    assert migracoes, "nenhuma migração encontrada (pacote incompleto?)"
    assert migracoes[0].name == "0001_fundacao.sql"


def test_nome_fora_do_padrao(tmp_path: Path) -> None:
    (tmp_path / "1_errada.sql").write_text("select 1;", encoding="utf-8")
    with pytest.raises(migrate.MigrationError, match="padrão"):
        migrate.discover(tmp_path)


def test_versoes_com_buraco(tmp_path: Path) -> None:
    (tmp_path / "0001_a.sql").write_text("select 1;", encoding="utf-8")
    (tmp_path / "0003_c.sql").write_text("select 1;", encoding="utf-8")
    with pytest.raises(migrate.MigrationError, match="contínuas"):
        migrate.discover(tmp_path)


def test_rodar_de_novo_nao_aplica_nada(banco: Banco) -> None:
    with db.connect(banco.migrator) as conn:
        assert migrate.migrate(conn) == []


def test_migracao_alterada_depois_de_aplicada_e_recusada(banco: Banco, tmp_path: Path) -> None:
    original = migrate.MIGRATIONS_DIR / "0001_fundacao.sql"
    (tmp_path / "0001_fundacao.sql").write_bytes(original.read_bytes() + b"\n-- alterada\n")
    with (
        db.connect(banco.migrator) as conn,
        pytest.raises(migrate.MigrationError, match="alterada"),
    ):
        migrate.migrate(conn, tmp_path)

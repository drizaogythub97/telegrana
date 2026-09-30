"""Conexão com o Postgres de testes (container no CI; branch `testes` do Neon localmente)."""

import pytest

from telegrana.infra import db
from tests.conftest import Banco

pytestmark = pytest.mark.integration


def test_postgres_18_disponivel(banco: Banco) -> None:
    with db.connect(banco.admin) as conn:
        row = conn.execute("select current_setting('server_version_num')::int").fetchone()
    assert row is not None
    assert row[0] >= 180000, "o projeto usa Postgres 18 (mesma versão do Neon)"


def test_app_conecta_com_limites(banco: Banco) -> None:
    with db.connect(banco.app) as conn:
        timeout = conn.execute("show statement_timeout").fetchone()
        caminho = conn.execute("show search_path").fetchone()
    assert timeout == ("5s",)
    assert caminho == ("telegrana",)

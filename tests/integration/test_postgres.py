"""Conexão com o Postgres de testes (container no CI; branch dev do Neon localmente — D018)."""

import os

import pytest

pytestmark = pytest.mark.integration

URL = os.environ.get("TELEGRANA_TEST_DATABASE_URL", "")


@pytest.mark.skipif(not URL, reason="TELEGRANA_TEST_DATABASE_URL não definida")
def test_postgres_18_disponivel() -> None:
    import psycopg

    with psycopg.connect(URL, connect_timeout=10) as conn:
        row = conn.execute("select current_setting('server_version_num')::int").fetchone()
    assert row is not None
    assert row[0] >= 180000, "o projeto usa Postgres 18 (mesma versão do Neon)"

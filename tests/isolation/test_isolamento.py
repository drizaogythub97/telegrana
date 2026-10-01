"""Suíte de isolamento entre contas (CLAUDE.md regra de ouro 5; PLANO 8.2).

Duas contas (A e B) são criadas pelo caminho real (start_onboarding). No contexto de A,
o papel do app tenta ler, alterar, apagar e inserir dados de B: tudo precisa falhar.
Um meta-teste obriga toda tabela nova a ser classificada como ISOLADA ou GLOBAL.
Esta suíte bloqueia o deploy (CI obrigatório).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import psycopg
import pytest
from psycopg import errors, sql

from telegrana.infra import db
from tests.conftest import Banco

pytestmark = [pytest.mark.integration, pytest.mark.isolation]

# tabela -> (chave primária, SQL que diz se a linha pertence à conta %(conta)s)
ISOLADAS: dict[str, tuple[str, str]] = {
    "accounts": ("id", "id = %(conta)s"),
    "users": (
        "id",
        "exists (select 1 from telegrana.account_members m where m.user_id = t.id and m.account_id = %(conta)s)",
    ),
    "account_members": ("user_id", "account_id = %(conta)s"),
    "user_channels": (
        "external_id",
        "exists (select 1 from telegrana.account_members m where m.user_id = t.user_id and m.account_id = %(conta)s)",
    ),
    "terms_acceptances": ("id", "account_id = %(conta)s"),
    "recovery_codes": ("selector", "account_id = %(conta)s"),
}
# Sem dados financeiros; acesso controlado por GRANT (ver 0001_fundacao.sql).
GLOBAIS = frozenset(
    {
        "schema_migrations",
        "invite_links",
        "access_requests",
        "processed_updates",
        "audit_log",
        "auth_attempts",
    }
)


@dataclass(frozen=True)
class Conta:
    account_id: uuid.UUID
    user_id: uuid.UUID
    external_id: str


@dataclass(frozen=True)
class Cenario:
    a: Conta
    b: Conta


@pytest.fixture(scope="module")
def app(banco: Banco) -> Iterator[db.Connection]:
    with db.connect(banco.app) as conn:
        yield conn


@pytest.fixture(scope="module")
def migrator(banco: Banco) -> Iterator[db.Connection]:
    with db.connect(banco.migrator) as conn:
        yield conn


def _cria_conta(app: db.Connection, external_id: str) -> Conta:
    with app.transaction():
        row = app.execute(
            "select o_user_id, o_account_id from telegrana.start_onboarding('telegram', %s)",
            (external_id,),
        ).fetchone()
    assert row is not None
    conta = Conta(account_id=row[1], user_id=row[0], external_id=external_id)
    with db.account_context(app, conta.account_id) as cur:
        cur.execute(
            "insert into telegrana.terms_acceptances (account_id, user_id, doc, version, content_sha256)"
            " values (%s, %s, 'termos', 1, %s)",
            (conta.account_id, conta.user_id, hashlib.sha256(b"termos v1").digest()),
        )
        cur.execute(
            "insert into telegrana.recovery_codes (account_id, user_id, selector, verifier_hash)"
            " values (%s, %s, %s, %s)",
            (conta.account_id, conta.user_id, "ABCD" + external_id[-4:], "$argon2id$" + "x" * 40),
        )
        cur.execute(
            "update telegrana.users set status = 'active', onboarding_step = 'done',"
            " phone_hmac = %s where id = %s",
            (hashlib.sha256(external_id.encode()).digest(), conta.user_id),
        )
    return conta


@pytest.fixture(scope="module")
def cenario(app: db.Connection) -> Cenario:
    return Cenario(a=_cria_conta(app, "1000000001"), b=_cria_conta(app, "1000000002"))


def _ids(conn: db.Connection, tabela: str, pk: str, dono: uuid.UUID | None = None) -> set[str]:
    query = sql.SQL("select {pk}::text from telegrana.{t} t").format(
        pk=sql.Identifier(pk), t=sql.Identifier(tabela)
    )
    params: dict[str, object] = {}
    if dono is not None:
        query += sql.SQL(" where ") + sql.SQL(ISOLADAS[tabela][1])  # type: ignore[arg-type]
        params = {"conta": dono}
    return {row[0] for row in conn.execute(query, params).fetchall()}


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tabela", sorted(ISOLADAS))
def test_sem_contexto_o_app_nao_ve_nada(app: db.Connection, cenario: Cenario, tabela: str) -> None:
    with app.transaction():
        assert _ids(app, tabela, ISOLADAS[tabela][0]) == set()


@pytest.mark.parametrize("tabela", sorted(ISOLADAS))
def test_contexto_a_ve_exatamente_os_dados_de_a(
    app: db.Connection, migrator: db.Connection, cenario: Cenario, tabela: str
) -> None:
    pk = ISOLADAS[tabela][0]
    with migrator.transaction():
        esperado_a = _ids(migrator, tabela, pk, cenario.a.account_id)
        de_b = _ids(migrator, tabela, pk, cenario.b.account_id)
    assert esperado_a, f"{tabela}: cenário sem dados da conta A (teste sem sentido)"
    assert de_b, f"{tabela}: cenário sem dados da conta B (teste sem sentido)"
    with db.account_context(app, cenario.a.account_id):
        visto = _ids(app, tabela, pk)
    assert visto == esperado_a
    assert not (visto & de_b)


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------
def _tenta(
    app: db.Connection, conta: uuid.UUID, comando: sql.Composable, params: dict[str, object]
) -> int:
    """Executa no contexto de `conta`; devolve linhas afetadas (0 se o banco recusar)."""
    try:
        with db.account_context(app, conta) as cur:
            cur.execute(comando, params)
            return cur.rowcount
    except errors.InsufficientPrivilege:
        return 0


@pytest.mark.parametrize("tabela", sorted(ISOLADAS))
def test_contexto_a_nao_altera_nem_apaga_dados_de_b(
    app: db.Connection, migrator: db.Connection, cenario: Cenario, tabela: str
) -> None:
    pk = ISOLADAS[tabela][0]
    with migrator.transaction():
        alvos = _ids(migrator, tabela, pk, cenario.b.account_id)
    for alvo in alvos:
        params: dict[str, object] = {"alvo": alvo}
        where = sql.SQL(" where {pk}::text = %(alvo)s").format(pk=sql.Identifier(pk))
        update = sql.SQL("update telegrana.{t} set {pk} = {pk}").format(
            t=sql.Identifier(tabela), pk=sql.Identifier(pk)
        )
        delete = sql.SQL("delete from telegrana.{t}").format(t=sql.Identifier(tabela))
        assert _tenta(app, cenario.a.account_id, update + where, params) == 0
        assert _tenta(app, cenario.a.account_id, delete + where, params) == 0
    with migrator.transaction():
        assert _ids(migrator, tabela, pk, cenario.b.account_id) == alvos, "dados de B mudaram"


def test_contexto_a_nao_insere_termos_na_conta_b(app: db.Connection, cenario: Cenario) -> None:
    with (
        pytest.raises(errors.InsufficientPrivilege),
        db.account_context(app, cenario.a.account_id) as cur,
    ):
        cur.execute(
            "insert into telegrana.terms_acceptances (account_id, user_id, doc, version, content_sha256)"
            " values (%s, %s, 'privacidade', 1, %s)",
            (cenario.b.account_id, cenario.b.user_id, hashlib.sha256(b"x").digest()),
        )


def test_contexto_a_nao_vincula_canal_a_pessoa_de_b(app: db.Connection, cenario: Cenario) -> None:
    with (
        pytest.raises(errors.InsufficientPrivilege),
        db.account_context(app, cenario.a.account_id) as cur,
    ):
        cur.execute(
            "insert into telegrana.user_channels (channel, external_id, user_id)"
            " values ('whatsapp', '5511999990000', %s)",
            (cenario.b.user_id,),
        )


# ---------------------------------------------------------------------------
# Papel do app e funções
# ---------------------------------------------------------------------------
def test_papel_app_sem_privilegios_especiais(app: db.Connection) -> None:
    with app.transaction():
        row = app.execute(
            "select rolsuper, rolbypassrls, rolcreaterole, rolcreatedb"
            " from pg_roles where rolname = current_user"
        ).fetchone()
        assert row == (False, False, False, False)
        membro = app.execute(
            "select pg_has_role(current_user, 'telegrana_migrator', 'member')"
        ).fetchone()
        assert membro == (False,)


@pytest.mark.parametrize(
    "comando",
    [
        "set role telegrana_migrator",
        "alter table telegrana.accounts disable row level security",
        "alter table telegrana.accounts no force row level security",
        "drop policy isolamento on telegrana.accounts",
        "select * from telegrana.audit_log",
        "update telegrana.audit_log set event = 'x'",
        "create table telegrana.intrusa (id int)",
    ],
)
def test_app_nao_contorna_o_isolamento(app: db.Connection, comando: str) -> None:
    with pytest.raises(psycopg.Error), app.transaction():
        app.execute(comando.encode())


def test_start_onboarding_e_idempotente(app: db.Connection, cenario: Cenario) -> None:
    with app.transaction():
        row = app.execute(
            "select o_user_id, o_account_id, o_created from telegrana.start_onboarding('telegram', %s)",
            (cenario.a.external_id,),
        ).fetchone()
    assert row == (cenario.a.user_id, cenario.a.account_id, False)


def test_resolve_identity_so_devolve_a_propria_identidade(
    app: db.Connection, cenario: Cenario
) -> None:
    with app.transaction():
        linhas = app.execute(
            "select o_account_id from telegrana.resolve_identity('telegram', %s)",
            (cenario.b.external_id,),
        ).fetchall()
        desconhecido = app.execute(
            "select * from telegrana.resolve_identity('telegram', '9999999999')"
        ).fetchall()
    assert linhas == [(cenario.b.account_id,)]
    assert desconhecido == []


# ---------------------------------------------------------------------------
# Meta-testes do catálogo: nada novo passa sem ser classificado
# ---------------------------------------------------------------------------
def test_toda_tabela_esta_classificada(migrator: db.Connection) -> None:
    with migrator.transaction():
        tabelas = {
            row[0]
            for row in migrator.execute(
                "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace"
                " where n.nspname = 'telegrana' and c.relkind in ('r', 'p')"
            ).fetchall()
        }
    nao_classificadas = tabelas - set(ISOLADAS) - GLOBAIS
    assert not nao_classificadas, (
        f"tabelas sem classificação no teste de isolamento: {sorted(nao_classificadas)}"
    )


@pytest.mark.parametrize("tabela", sorted(ISOLADAS))
def test_isoladas_tem_rls_forcado_e_politica_do_app(migrator: db.Connection, tabela: str) -> None:
    with migrator.transaction():
        rls = migrator.execute(
            "select c.relrowsecurity, c.relforcerowsecurity from pg_class c"
            " join pg_namespace n on n.oid = c.relnamespace"
            " where n.nspname = 'telegrana' and c.relname = %s",
            (tabela,),
        ).fetchone()
        politicas = migrator.execute(
            "select roles::text[] from pg_policies where schemaname = 'telegrana' and tablename = %s",
            (tabela,),
        ).fetchall()
    assert rls == (True, True), f"{tabela}: RLS precisa estar habilitado e forçado"
    assert any("telegrana_app" in roles for (roles,) in politicas), f"{tabela}: sem política do app"
    # Nenhuma política pode valer para PUBLIC (todas miram papéis específicos).
    assert all("public" not in roles for (roles,) in politicas)


def test_funcoes_security_definer_sao_blindadas(migrator: db.Connection) -> None:
    with migrator.transaction():
        funcoes = migrator.execute(
            "select p.proname, p.proconfig, has_function_privilege('public', p.oid, 'execute')"
            " from pg_proc p join pg_namespace n on n.oid = p.pronamespace"
            " where n.nspname = 'telegrana' and p.prosecdef"
        ).fetchall()
    assert {f[0] for f in funcoes} == {
        "resolve_identity",
        "start_onboarding",
        "recovery_lookup",
        "find_user_by_phone",
        "relink_identity",
        "erase_account",
        "purge_stale_onboarding",
        "admin_list_users",
    }
    for nome, config, publico in funcoes:
        assert config, f"{nome}: sem configuração"
        assert any(c.startswith("search_path=") for c in config), f"{nome}: sem search_path fixo"
        assert not publico, f"{nome}: EXECUTE liberado para PUBLIC"


# ---------------------------------------------------------------------------
# Caminhos de recuperação e exclusão (0002)
# ---------------------------------------------------------------------------
def test_relink_nao_toma_identidade_de_conta_ativa(app: db.Connection, cenario: Cenario) -> None:
    with app.transaction():
        row = app.execute(
            "select o_result from telegrana.relink_identity('telegram', %s, %s)",
            (cenario.b.external_id, cenario.a.user_id),
        ).fetchone()
        dono_b = app.execute(
            "select o_user_id from telegrana.resolve_identity('telegram', %s)",
            (cenario.b.external_id,),
        ).fetchone()
    assert row == ("in_use",)
    assert dono_b == (cenario.b.user_id,)


def test_erase_account_so_apaga_a_conta_do_contexto(app: db.Connection, cenario: Cenario) -> None:
    with (
        pytest.raises(psycopg.errors.RaiseException),
        db.account_context(app, cenario.a.account_id) as cur,
    ):
        cur.execute("select telegrana.erase_account(%s)", (cenario.b.account_id,))
    with app.transaction():
        ainda = app.execute(
            "select count(*) from telegrana.resolve_identity('telegram', %s)",
            (cenario.b.external_id,),
        ).fetchone()
    assert ainda == (1,)


def test_app_nao_executa_a_auxiliar_interna(app: db.Connection, cenario: Cenario) -> None:
    with pytest.raises(errors.InsufficientPrivilege), app.transaction():
        app.execute("select telegrana._erase_person(%s)", (cenario.b.user_id,))


def test_buscas_de_recuperacao_ignoram_cadastro_inacabado(app: db.Connection) -> None:
    with app.transaction():
        row = app.execute(
            "select o_user_id, o_account_id from telegrana.start_onboarding('telegram', '1000000077')"
        ).fetchone()
    assert row is not None
    with db.account_context(app, row[1]) as cur:
        cur.execute(
            "insert into telegrana.recovery_codes (account_id, user_id, selector, verifier_hash)"
            " values (%s, %s, 'ZZZZ0077', %s)",
            (row[1], row[0], "$argon2id$" + "y" * 40),
        )
    with app.transaction():
        achado = app.execute("select * from telegrana.recovery_lookup('ZZZZ0077')").fetchall()
        lista = app.execute("select o_user_id from telegrana.admin_list_users()").fetchall()
    assert achado == []
    assert (row[0],) not in lista

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
    "categories": ("id", "account_id = %(conta)s"),
    "payment_methods": ("id", "account_id = %(conta)s"),
    "transactions": ("id", "account_id = %(conta)s"),
    "category_rules": ("id", "account_id = %(conta)s"),
    "pending_entries": ("id", "account_id = %(conta)s"),
    "message_refs": ("message_id", "account_id = %(conta)s"),
    "fixed_items": ("id", "account_id = %(conta)s"),
    "fixed_occurrences": ("id", "account_id = %(conta)s"),
    "reminder_sends": ("id", "account_id = %(conta)s"),
    "cards": ("id", "account_id = %(conta)s"),
    "card_invoices": ("id", "account_id = %(conta)s"),
    "invoice_notices": ("id", "account_id = %(conta)s"),
    "summary_sends": ("id", "account_id = %(conta)s"),
    "account_usage": ("id", "account_id = %(conta)s"),
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
        "ai_usage",
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
        cur.execute(
            "update telegrana.accounts set status = 'active' where id = %s", (conta.account_id,)
        )
        cur.execute("select telegrana.seed_account_defaults(%s)", (conta.account_id,))
        cur.execute(
            "insert into telegrana.transactions (account_id, user_id, kind, amount_cents,"
            " category_id, payment_method_id, occurred_on, cash_on, source)"
            " select %s, %s, 'expense', 4590, c.id, p.id, current_date, current_date, 'text'"
            " from telegrana.categories c, telegrana.payment_methods p"
            " where c.code = 'mercado' and p.kind = 'pix'",
            (conta.account_id, conta.user_id),
        )
        cur.execute(
            "insert into telegrana.category_rules (account_id, pattern, category_id)"
            " select %s, 'drogasil', id from telegrana.categories where code = 'saude'",
            (conta.account_id,),
        )
        cur.execute(
            "insert into telegrana.pending_entries (account_id, user_id, data, pendencia)"
            " values (%s, %s, '{}'::jsonb, 'categoria')",
            (conta.account_id, conta.user_id),
        )
        cur.execute(
            "insert into telegrana.message_refs (account_id, channel, message_id, transaction_id)"
            " select %s, 'telegram', %s, id from telegrana.transactions limit 1",
            (conta.account_id, "m" + external_id),
        )
        cur.execute(
            "insert into telegrana.fixed_items (account_id, user_id, kind, name, category_id,"
            " amount_cents, amount_kind, day_of_month)"
            " select %s, %s, 'expense', 'Aluguel', id, 150000, 'fixed', 10"
            " from telegrana.categories where code = 'moradia'",
            (conta.account_id, conta.user_id),
        )
        cur.execute(
            "insert into telegrana.fixed_occurrences (account_id, fixed_item_id, due_date, status)"
            " select %s, id, current_date, 'skipped' from telegrana.fixed_items",
            (conta.account_id,),
        )
        cur.execute(
            "insert into telegrana.payment_methods (account_id, kind, name, emoji)"
            " values (%s, 'credit', 'Nubank', '💳')",
            (conta.account_id,),
        )
        cur.execute(
            "insert into telegrana.cards (account_id, payment_method_id, closing_day, due_day)"
            " select %s, id, 3, 10 from telegrana.payment_methods where name = 'Nubank'",
            (conta.account_id,),
        )
        cur.execute(
            "insert into telegrana.card_invoices (account_id, card_id, due_date, total_cents,"
            " paid_cents, paid_on) select %s, id, current_date, 100, 100, current_date"
            " from telegrana.cards",
            (conta.account_id,),
        )
        cur.execute(
            "insert into telegrana.summary_sends (account_id, kind, period_start)"
            " values (%s, 'monthly', date_trunc('month', current_date))",
            (conta.account_id,),
        )
        cur.execute(
            "insert into telegrana.account_usage (account_id, day, messages) values (%s, current_date, 1)",
            (conta.account_id,),
        )
        cur.execute(
            "insert into telegrana.invoice_notices (account_id, card_id, due_date, rule,"
            " sent_on, slot) select %s, id, current_date, 'on_day', current_date, 'morning'"
            " from telegrana.cards",
            (conta.account_id,),
        )
        cur.execute(
            "insert into telegrana.reminder_sends (account_id, fixed_item_id, due_date, rule,"
            " sent_on, slot) select %s, id, current_date, 'on_day', current_date, 'morning'"
            " from telegrana.fixed_items",
            (conta.account_id,),
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
        "purge_account_temporaries",
        "accounts_with_reminders",
        "accounts_for_summaries",
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


# ---------------------------------------------------------------------------
# Lançamentos (0003)
# ---------------------------------------------------------------------------
def _categoria(migrator: db.Connection, conta: uuid.UUID, code: str) -> uuid.UUID:
    with migrator.transaction():
        row = migrator.execute(
            "select id from telegrana.categories where account_id = %s and code = %s",
            (conta, code),
        ).fetchone()
    assert row is not None
    return row[0]


def test_lancamento_nao_aponta_para_categoria_de_outra_conta(
    app: db.Connection, migrator: db.Connection, cenario: Cenario
) -> None:
    categoria_b = _categoria(migrator, cenario.b.account_id, "mercado")
    with (
        pytest.raises(errors.ForeignKeyViolation),
        db.account_context(app, cenario.a.account_id) as cur,
    ):
        cur.execute(
            "insert into telegrana.transactions (account_id, user_id, kind, amount_cents,"
            " category_id, occurred_on, cash_on, source)"
            " values (%s, %s, 'expense', 100, %s, current_date, current_date, 'text')",
            (cenario.a.account_id, cenario.a.user_id, categoria_b),
        )


def test_regra_nao_aponta_para_categoria_de_outra_conta(
    app: db.Connection, migrator: db.Connection, cenario: Cenario
) -> None:
    categoria_b = _categoria(migrator, cenario.b.account_id, "saude")
    with (
        pytest.raises(errors.ForeignKeyViolation),
        db.account_context(app, cenario.a.account_id) as cur,
    ):
        cur.execute(
            "insert into telegrana.category_rules (account_id, pattern, category_id)"
            " values (%s, 'farmacia', %s)",
            (cenario.a.account_id, categoria_b),
        )


def test_padroes_nao_sao_semeados_em_outra_conta(app: db.Connection, cenario: Cenario) -> None:
    with (
        pytest.raises(errors.InsufficientPrivilege),
        db.account_context(app, cenario.a.account_id) as cur,
    ):
        cur.execute("select telegrana.seed_account_defaults(%s)", (uuid.uuid4(),))


def test_padroes_sao_idempotentes(app: db.Connection, cenario: Cenario) -> None:
    with db.account_context(app, cenario.a.account_id) as cur:
        antes = cur.execute("select count(*) from telegrana.categories").fetchone()
        cur.execute("select telegrana.seed_account_defaults(%s)", (cenario.a.account_id,))
        depois = cur.execute("select count(*) from telegrana.categories").fetchone()
    assert antes == depois == (21,)


def test_recibo_nao_aponta_para_lancamento_de_outra_conta(
    app: db.Connection, migrator: db.Connection, cenario: Cenario
) -> None:
    with migrator.transaction():
        row = migrator.execute(
            "select id from telegrana.transactions where account_id = %s limit 1",
            (cenario.b.account_id,),
        ).fetchone()
    assert row is not None
    with (
        pytest.raises(errors.ForeignKeyViolation),
        db.account_context(app, cenario.a.account_id) as cur,
    ):
        cur.execute(
            "insert into telegrana.message_refs (account_id, channel, message_id, transaction_id)"
            " values (%s, 'telegram', 'forjado', %s)",
            (cenario.a.account_id, row[0]),
        )


def test_fixo_nao_aponta_para_categoria_nem_forma_de_outra_conta(
    app: db.Connection, cenario: Cenario
) -> None:
    with db.account_context(app, cenario.b.account_id) as cur:
        categoria_b = cur.execute("select id from telegrana.categories limit 1").fetchone()[0]
        forma_b = cur.execute("select id from telegrana.payment_methods limit 1").fetchone()[0]
    for coluna, alheio in (("category_id", categoria_b), ("payment_method_id", forma_b)):
        with pytest.raises(psycopg.errors.ForeignKeyViolation):  # noqa: SIM117
            with db.account_context(app, cenario.a.account_id) as cur:
                cur.execute(
                    sql.SQL(
                        "insert into telegrana.fixed_items (account_id, user_id, kind, name,"
                        " {coluna}, amount_cents, amount_kind, day_of_month)"
                        " values (%s, %s, 'expense', 'Invasor', %s, 100, 'fixed', 1)"
                    ).format(coluna=sql.Identifier(coluna)),
                    (cenario.a.account_id, cenario.a.user_id, alheio),
                )


def test_lancamento_nao_aponta_para_fixo_de_outra_conta(
    app: db.Connection, cenario: Cenario
) -> None:
    with db.account_context(app, cenario.b.account_id) as cur:
        fixo_b = cur.execute("select id from telegrana.fixed_items limit 1").fetchone()[0]
    with pytest.raises(psycopg.errors.ForeignKeyViolation):  # noqa: SIM117
        with db.account_context(app, cenario.a.account_id) as cur:
            cur.execute("update telegrana.transactions set fixed_item_id = %s", (fixo_b,))


def test_contas_com_lembrete_so_devolve_ids(app: db.Connection, cenario: Cenario) -> None:
    """A rotina atravessa contas só para saber QUEM tem lembrete; o resto é com RLS."""
    with app.transaction():
        cursor = app.execute("select * from telegrana.accounts_with_reminders()")
        colunas = [c.name for c in cursor.description or []]
        ids = {r[0] for r in cursor.fetchall()}
    assert colunas == ["o_account_id"]
    assert {cenario.a.account_id, cenario.b.account_id} <= ids


def test_cartao_e_parcela_nao_apontam_para_outra_conta(
    app: db.Connection, cenario: Cenario
) -> None:
    with db.account_context(app, cenario.b.account_id) as cur:
        forma_b = cur.execute(
            "select id from telegrana.payment_methods where kind = 'credit' limit 1"
        ).fetchone()[0]
        tx_b = cur.execute("select id from telegrana.transactions limit 1").fetchone()[0]
    with pytest.raises(psycopg.errors.ForeignKeyViolation):  # noqa: SIM117
        with db.account_context(app, cenario.a.account_id) as cur:
            cur.execute(
                "insert into telegrana.cards (account_id, payment_method_id, closing_day, due_day)"
                " values (%s, %s, 1, 10)",
                (cenario.a.account_id, forma_b),
            )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):  # noqa: SIM117
        with db.account_context(app, cenario.a.account_id) as cur:
            cur.execute(
                "update telegrana.transactions set purchase_id = %s, installment_no = 1,"
                " invoice_on = current_date",
                (tx_b,),
            )


def test_contas_com_resumo_so_devolve_ids(app: db.Connection, cenario: Cenario) -> None:
    with app.transaction():
        cursor = app.execute("select * from telegrana.accounts_for_summaries('monthly')")
        colunas = [c.name for c in cursor.description or []]
        ids = {r[0] for r in cursor.fetchall()}
        nada = app.execute("select * from telegrana.accounts_for_summaries('outro')").fetchall()
    assert colunas == ["o_account_id"]
    assert {cenario.a.account_id, cenario.b.account_id} <= ids  # mensal ligado por padrão
    assert nada == []


def test_toda_tabela_com_rls_tem_a_politica_de_backup(banco: Banco) -> None:
    """O backup (D052) lê por políticas explícitas: tabela nova sem a sua ficaria de fora."""
    with db.connect(banco.migrator) as m:
        sem = m.execute(
            "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace"
            " where n.nspname = 'telegrana' and c.relkind = 'r' and c.relrowsecurity"
            " and not exists (select 1 from pg_policy p where p.polrelid = c.oid"
            " and p.polname = 'backup')"
        ).fetchall()
    assert sem == []

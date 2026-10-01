"""Fluxos da S1.4 ponta a ponta no núcleo, com Postgres real (sem Telegram).

Cada teste usa identidades novas; o banco é o da sessão (tests/conftest.py).
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Iterator
from dataclasses import replace

import pytest

from telegrana.core import roteador
from telegrana.core import textos as t
from telegrana.core.contexto import Contexto, Documento
from telegrana.core.mensagens import ADMIN, Entrada, Resultado
from telegrana.entrypoints import rotinas
from telegrana.infra import db
from tests.conftest import Banco

pytestmark = pytest.mark.integration

ADMIN_ID = "555000999"
_ids = itertools.count(7_000_000_001)
_telefones = itertools.count(5511900000001)


def novo_id() -> str:
    return str(next(_ids))


def novo_telefone() -> str:
    return str(next(_telefones))


CTX = Contexto(
    canal="telegram",
    admin_id=ADMIN_ID,
    contato_admin="@admin_teste",
    termos=Documento(1, "https://telegra.ph/termos", b"\x01" * 32),
    privacidade=Documento(1, "https://telegra.ph/privacidade", b"\x02" * 32),
    link_convite=lambda token: f"https://t.me/bot_teste?start={token}",
    pepper=b"p" * 32,
)


class Bot:
    def __init__(self, conn: db.Connection, ctx: Contexto = CTX) -> None:
        self.conn = conn
        self.ctx = ctx

    def __call__(self, de: str, **kw: object) -> Resultado:
        entrada = Entrada(canal="telegram", external_id=de, nome="Fulano de Tal", **kw)  # type: ignore[arg-type]
        return roteador.trata(self.conn, self.ctx, entrada)


@pytest.fixture(scope="module")
def conn(banco: Banco) -> Iterator[db.Connection]:
    with db.connect(banco.app) as c:
        yield c


@pytest.fixture
def bot(conn: db.Connection) -> Bot:
    return Bot(conn)


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------
def textos_de(r: Resultado, destino: str | None = None) -> list[str]:
    return [s.texto for s in r.saidas if s.destino == destino]


def acoes(r: Resultado) -> list[str]:
    return [b.acao for s in r.saidas for linha in s.botoes for b in linha if b.acao]


def codigo_em(r: Resultado) -> str:
    for s in r.saidas:
        achado = re.search(r"`([0-9A-Z]{4}(?:-[0-9A-Z]{4}){4})`", s.texto)
        if achado:
            assert s.protegida
            return achado.group(1)
    raise AssertionError("nenhum código na resposta")


def gera_convite(bot: Bot) -> str:
    r = bot(ADMIN_ID, comando="link", argumento="novo")
    achado = re.search(r"start=([A-Za-z0-9_-]{43})", r.saidas[0].texto)
    assert achado
    return achado.group(1)


def cadastra(
    bot: Bot, de: str, telefone: str, token: str | None = None, nome: str = "Maria da Silva"
) -> str:
    """Cadastro completo pelo convite; devolve o código de recuperação."""
    r = bot(de, comando="start", argumento=token or gera_convite(bot))
    assert "termos:aceito" in acoes(r)
    bot(de, acao="termos:aceito")
    r = bot(de, texto=nome)
    assert acoes(r) == ["nome:ok", "nome:corrigir"]
    r = bot(de, acao="nome:ok")
    assert r.saidas[0].pedir_telefone
    r = bot(de, telefone=telefone)
    assert "adulto:sim" in acoes(r)
    r = bot(de, acao="adulto:sim")
    codigo = codigo_em(r)
    r = bot(de, acao="codigo:guardei")
    assert textos_de(r) == [t.PRONTO]
    return codigo


def situacao(banco_conn: db.Connection, de: str) -> str | None:
    with banco_conn.transaction():
        row = banco_conn.execute(
            "select o_user_status from telegrana.resolve_identity('telegram', %s)", (de,)
        ).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------
def test_desconhecido_ve_que_e_privado(bot: Bot) -> None:
    for kw in ({"comando": "start"}, {"texto": "oi"}, {"comando": "start", "argumento": "x" * 43}):
        r = bot(novo_id(), **kw)
        assert r.rotulo == "entrada.privado"
        assert acoes(r) == ["acesso:pedir", "rec:menu"]


def test_cadastro_completo_pelo_convite(bot: Bot, conn: db.Connection) -> None:
    de = novo_id()
    r = bot(de, comando="start", argumento=gera_convite(bot))
    assert r.saidas[0].texto == t.BOAS_VINDAS
    assert situacao(conn, de) == "onboarding"
    # Sem aceitar, nada avança.
    assert bot(de, texto="Maria da Silva").rotulo == "cadastro.termos"
    bot(de, acao="termos:aceito")
    assert textos_de(bot(de, texto="M4ria"))[0] == t.NOME_INVALIDO
    assert textos_de(bot(de, texto="Maria"))[0] == t.NOME_INVALIDO  # falta o sobrenome
    bot(de, texto="Maria  da   Silva")
    r = bot(de, acao="nome:corrigir")
    assert textos_de(r) == [t.PEDIR_NOME]
    r = bot(de, texto="Maria d'Ávila-Souza")
    assert "**Maria d'Ávila-Souza**" in r.saidas[0].texto
    bot(de, acao="nome:ok")
    r = bot(de, contato_alheio=True)
    assert textos_de(r) == [t.SO_PROPRIO_NUMERO]
    bot(de, telefone=novo_telefone())
    r = bot(de, acao="adulto:sim")
    codigo_em(r)
    # Antes de "Guardei", qualquer mensagem gera um código novo (o anterior não pode ser reexibido).
    codigo_em(bot(de, texto="oi"))
    r = bot(de, acao="codigo:guardei")
    assert textos_de(r) == [t.PRONTO]
    aviso = textos_de(r, ADMIN)
    assert aviso == [t.ADM_ENTROU.format(nome="Maria d'Ávila-Souza", via="convite")]
    assert situacao(conn, de) == "active"
    r = bot(ADMIN_ID, comando="link")
    assert "**1/20**" in r.saidas[0].texto


def test_menor_de_idade_tem_os_dados_apagados(bot: Bot, conn: db.Connection) -> None:
    de = novo_id()
    bot(de, comando="start", argumento=gera_convite(bot))
    bot(de, acao="termos:aceito")
    bot(de, texto="Joaozinho Pereira")
    bot(de, acao="nome:ok")
    bot(de, telefone=novo_telefone())
    r = bot(de, acao="adulto:nao")
    assert textos_de(r) == [t.MENOR]
    assert situacao(conn, de) is None


def test_link_revogado_nao_entra(bot: Bot) -> None:
    token = gera_convite(bot)
    gera_convite(bot)  # o novo revoga o anterior
    r = bot(novo_id(), comando="start", argumento=token)
    assert r.rotulo == "entrada.privado"
    bot(ADMIN_ID, comando="link", argumento="revogar")
    assert bot(ADMIN_ID, comando="link").saidas[0].texto == t.ADM_SEM_LINK


def test_comandos_de_admin_so_para_o_admin(bot: Bot) -> None:
    r = bot(novo_id(), comando="link", argumento="novo")
    assert r.rotulo == "entrada.privado"
    assert "start=" not in r.saidas[0].texto


def test_admin_cria_a_propria_conta_sem_convite(bot: Bot) -> None:
    ctx = replace(CTX, admin_id=novo_id())
    admin = Bot(bot.conn, ctx)
    r = admin(ctx.admin_id, comando="start")
    assert r.rotulo == "cadastro.inicio"


# ---------------------------------------------------------------------------
# Pedido de acesso
# ---------------------------------------------------------------------------
def test_pedido_aprovado(bot: Bot, conn: db.Connection) -> None:
    de = novo_id()
    r = bot(de, acao="acesso:pedir")
    assert textos_de(r) == [t.AVISO_PEDIDO, t.PERGUNTAS["acesso"]]
    assert r.saidas[1].pergunta == "acesso"
    r = bot(de, pergunta="acesso", texto="Sou prima **dele**", username="prima")
    assert textos_de(r) == [t.PEDIDO_ENVIADO]
    aviso = r.saidas[0]
    assert aviso.destino == ADMIN
    assert "Sou prima dele" in aviso.texto  # marcação do usuário removida
    assert "@prima" in aviso.texto
    assert textos_de(bot(de, acao="acesso:pedir")) == [t.PEDIDO_PENDENTE]

    aprovar = acoes(r)[0]
    assert aprovar.startswith("adm:ok:")
    # Botão de admin tocado por outra pessoa não faz nada de admin.
    assert bot(de, acao=aprovar).rotulo == "entrada.privado"
    r = bot(ADMIN_ID, acao=aprovar)
    liberado = [s for s in r.saidas if s.destino == de]
    assert liberado[0].texto == t.ACESSO_LIBERADO
    assert situacao(conn, de) == "onboarding"
    # Segundo toque: já resolvido.
    assert textos_de(bot(ADMIN_ID, acao=aprovar)) == [t.ADM_PEDIDO_RESOLVIDO]
    r = bot(de, acao="cad:iniciar")
    assert "termos:aceito" in acoes(r)


def test_pedido_recusado_bloqueia_novo_pedido(bot: Bot) -> None:
    de = novo_id()
    bot(de, acao="acesso:pedir")
    r = bot(de, pergunta="acesso", texto="oi")
    recusar = acoes(r)[1]
    assert recusar.startswith("adm:no:")
    r = bot(ADMIN_ID, acao=recusar)
    assert textos_de(r) == [t.ADM_RECUSADO]
    assert all(s.destino != de for s in r.saidas)  # a pessoa não é avisada
    assert textos_de(bot(de, acao="acesso:pedir")) == [t.PEDIDO_INDISPONIVEL]


def test_pedido_com_resposta_grande_demais(bot: Bot) -> None:
    de = novo_id()
    r = bot(de, pergunta="acesso", texto="x" * 201)
    assert textos_de(r)[0] == t.PEDIDO_TAMANHO
    assert r.saidas[1].pergunta == "acesso"


def test_limite_global_de_pedidos(bot: Bot) -> None:
    apertado = Bot(bot.conn, replace(CTX, max_pedidos_por_hora=0))
    assert textos_de(apertado(novo_id(), acao="acesso:pedir")) == [t.PEDIDO_INDISPONIVEL]


# ---------------------------------------------------------------------------
# Recuperação
# ---------------------------------------------------------------------------
def test_recupera_pelo_mesmo_numero(bot: Bot, conn: db.Connection) -> None:
    antigo, novo, telefone = novo_id(), novo_id(), novo_telefone()
    cadastra(bot, antigo, telefone)
    r = bot(novo, telefone=telefone)
    assert r.saidas[0].texto == t.RECUPERADA
    assert [s.texto for s in r.saidas if s.destino == antigo] == [t.AVISO_CONTA_ANTIGA]
    assert situacao(conn, novo) == "active"
    assert situacao(conn, antigo) is None


def test_numero_sem_conta_conta_tentativa(bot: Bot) -> None:
    de = novo_id()
    for _ in range(5):
        assert textos_de(bot(de, telefone=novo_telefone())) == [t.NUMERO_SEM_CONTA]
    assert bot(de, telefone=novo_telefone()).rotulo == "recuperacao.phone.travado"


def test_cadastro_com_numero_que_ja_tem_conta_religa(bot: Bot, conn: db.Connection) -> None:
    antigo, novo, telefone = novo_id(), novo_id(), novo_telefone()
    cadastra(bot, antigo, telefone)
    bot(novo, comando="start", argumento=gera_convite(bot))
    bot(novo, acao="termos:aceito")
    bot(novo, texto="Outra Pessoa")
    bot(novo, acao="nome:ok")
    r = bot(novo, telefone=telefone)
    assert r.saidas[0].texto == t.RECUPERADA_PELO_CADASTRO
    assert situacao(conn, novo) == "active"
    assert situacao(conn, antigo) is None


def test_recupera_pelo_codigo_e_o_codigo_e_trocado(bot: Bot, conn: db.Connection) -> None:
    antigo, novo, outro = novo_id(), novo_id(), novo_id()
    codigo = cadastra(bot, antigo, novo_telefone())
    r = bot(novo, comando="entrar")
    assert r.saidas[0].pergunta == "codigo"
    r = bot(novo, pergunta="codigo", texto=codigo.lower().replace("-", " "))
    assert r.apagar_entrada
    assert r.saidas[0].texto == t.RECUPERADA
    novo_codigo = codigo_em(r)
    assert novo_codigo != codigo
    assert situacao(conn, novo) == "active"
    # O código usado deixou de valer.
    r = bot(outro, pergunta="codigo", texto=codigo)
    assert textos_de(r) == [t.CODIGO_INVALIDO]


def test_codigo_errado_trava_depois_de_cinco(bot: Bot) -> None:
    de = novo_id()
    for _ in range(5):
        r = bot(de, pergunta="codigo", texto="ABCD-EFGH-JKMN-PQRS-TVWX")
        assert textos_de(r) == [t.CODIGO_INVALIDO]
        assert r.apagar_entrada
    r = bot(de, pergunta="codigo", texto="ABCD-EFGH-JKMN-PQRS-TVWX")
    assert r.rotulo == "recuperacao.code.travado"
    assert textos_de(bot(de, pergunta="codigo", texto="lixo")) != [t.CODIGO_FORMATO]


def test_conta_ativa_nao_e_tomada_por_codigo(bot: Bot, conn: db.Connection) -> None:
    a, b = novo_id(), novo_id()
    codigo_a = cadastra(bot, a, novo_telefone())
    cadastra(bot, b, novo_telefone())
    r = bot(b, pergunta="codigo", texto=codigo_a)
    assert textos_de(r) == [t.JA_TEM_CONTA]
    assert situacao(conn, a) == "active"


def test_recuperacao_manual_pelo_admin(bot: Bot, conn: db.Connection) -> None:
    antigo, novo = novo_id(), novo_id()
    cadastra(bot, antigo, novo_telefone())
    r = bot(novo, acao="rec:adm")
    assert r.saidas[0].pergunta == "rec_nome"
    r = bot(novo, pergunta="rec_nome", texto="Maria da Silva")
    assert textos_de(r) == [t.PEDIDO_RECUPERACAO_ENVIADO]
    with conn.transaction():
        conta_antiga = conn.execute(
            "select o_user_id from telegrana.resolve_identity('telegram', %s)", (antigo,)
        ).fetchone()
    assert conta_antiga is not None
    from telegrana.core.seguranca import curto

    escolha = next(a for a in acoes(r) if a.endswith(curto(conta_antiga[0])))
    r = bot(ADMIN_ID, acao=escolha)
    para_novo = [s for s in r.saidas if s.destino == novo]
    assert para_novo[0].texto == t.RECUPERADA
    assert any(s.protegida for s in para_novo)
    assert any("religada" in s.texto for s in r.saidas if s.destino is None)
    assert situacao(conn, novo) == "active"
    assert situacao(conn, antigo) is None


# ---------------------------------------------------------------------------
# Conta
# ---------------------------------------------------------------------------
def test_comandos_da_conta(bot: Bot) -> None:
    de = novo_id()
    cadastra(bot, de, novo_telefone())
    r = bot(de, comando="meus_dados")
    assert "**Maria da Silva**" in r.saidas[0].texto
    assert "vinculado ✅" in r.saidas[0].texto
    assert "@admin_teste" in r.saidas[0].texto
    r = bot(de, comando="corrigir_nome")
    assert r.saidas[0].pergunta == "nome"
    r = bot(de, pergunta="nome", texto="Maria da Silva Souza")
    assert textos_de(r) == [t.NOME_CORRIGIDO.format(nome="Maria da Silva Souza")]
    r = bot(de, comando="termos")
    assert "v1" in r.saidas[0].texto
    r = bot(de, comando="codigo_novo")
    r = bot(de, acao="cod:novo")
    codigo_em(r)
    assert textos_de(bot(de, texto="gastei 30 no mercado")) == [t.EM_BREVE]


def test_termos_novos_exigem_novo_aceite(bot: Bot) -> None:
    de = novo_id()
    cadastra(bot, de, novo_telefone())
    v2 = Bot(bot.conn, replace(CTX, termos=Documento(2, "https://telegra.ph/v2", b"\x03" * 32)))
    assert v2(de, comando="meus_dados").rotulo == "conta.termos.pendentes"
    assert v2(de, acao="termos:aceito").rotulo == "conta.termos.aceitos"
    assert v2(de, comando="meus_dados").rotulo == "conta.meus_dados"


def test_apagar_conta_com_confirmacao_dupla(bot: Bot, conn: db.Connection, banco: Banco) -> None:
    de = novo_id()
    cadastra(bot, de, novo_telefone())
    assert acoes(bot(de, comando="apagar_conta")) == ["apagar:1", "cancelar"]
    assert textos_de(bot(de, acao="cancelar")) == [t.CANCELADO]
    assert acoes(bot(de, acao="apagar:1")) == ["apagar:2", "cancelar"]
    with conn.transaction():
        row = conn.execute(
            "select o_account_id from telegrana.resolve_identity('telegram', %s)", (de,)
        ).fetchone()
    assert row is not None
    r = bot(de, acao="apagar:2")
    assert textos_de(r) == [t.APAGADA]
    assert situacao(conn, de) is None
    with db.connect(banco.migrator) as m, m.transaction():
        restos = m.execute(
            "select count(*) from telegrana.audit_log where account_id = %s", (row[0],)
        ).fetchone()
        anonimo = m.execute(
            "select count(*) from telegrana.audit_log"
            " where event = 'account.deleted' and account_id is null"
        ).fetchone()
    assert restos == (0,)
    assert anonimo is not None
    assert anonimo[0] >= 1


def test_admin_nao_ve_botao_de_bloquear_a_si_mesmo(bot: Bot) -> None:
    ctx = replace(CTX, admin_id=novo_id())
    admin = Bot(bot.conn, ctx)
    cadastra(admin, ctx.admin_id, novo_telefone(), token="x" * 43, nome="Admin Proprio")
    r = admin(ctx.admin_id, comando="usuarios")
    assert "Admin Proprio" in r.saidas[0].texto
    assert not any("Admin Proprio" in b.rotulo for linha in r.saidas[0].botoes for b in linha)


def test_bloqueio_pelo_admin(bot: Bot) -> None:
    de = novo_id()
    cadastra(bot, de, novo_telefone(), nome="Bruna Bloqueada")
    r = bot(ADMIN_ID, comando="usuarios")
    linhas = r.saidas[0].texto.splitlines()[1:]
    bloquear = next(
        a for linha, a in zip(linhas, acoes(r), strict=True) if "Bruna Bloqueada" in linha
    )
    assert bloquear.startswith("adm:bq:")
    assert textos_de(bot(ADMIN_ID, acao=bloquear)) == [
        t.ADM_BLOQUEADO.format(nome="Bruna Bloqueada")
    ]
    assert bot(de, comando="meus_dados").rotulo == "conta.bloqueada"
    bot(ADMIN_ID, acao="adm:db:" + bloquear.removeprefix("adm:bq:"))
    assert bot(de, comando="meus_dados").rotulo == "conta.meus_dados"


# ---------------------------------------------------------------------------
# Rotinas
# ---------------------------------------------------------------------------
def test_rotinas_apaga_cadastro_incompleto_velho(
    bot: Bot, conn: db.Connection, banco: Banco
) -> None:
    velho, recente = novo_id(), novo_id()
    bot(velho, comando="start", argumento=gera_convite(bot))
    bot(recente, comando="start", argumento=gera_convite(bot))
    with db.connect(banco.migrator) as m, m.transaction():
        m.execute(
            "update telegrana.users set created_at = now() - interval '8 days' where id ="
            " (select o_user_id from telegrana.resolve_identity('telegram', %s))",
            (velho,),
        )
    resultado = rotinas.limpa(conn)
    assert resultado["cadastros_incompletos_apagados"] >= 1
    assert situacao(conn, velho) is None
    assert situacao(conn, recente) == "onboarding"

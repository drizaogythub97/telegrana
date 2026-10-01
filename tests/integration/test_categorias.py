"""/categorias contra Postgres real (S2.1)."""

from __future__ import annotations

import pytest

from telegrana.core import textos as t
from telegrana.infra import db
from tests.integration.test_cadastro import Bot, acoes, cadastra, conn, novo_id, novo_telefone

pytestmark = pytest.mark.integration
__all__ = ["conn"]  # fixture reaproveitada


@pytest.fixture
def bot(conn: db.Connection) -> Bot:
    return Bot(conn)


def _conta(bot: Bot) -> str:
    de = novo_id()
    cadastra(bot, de, novo_telefone())
    return de


def _abre(bot: Bot, de: str, rotulo: str) -> str:
    """Toca em Editar e devolve a ação do botão da categoria `rotulo`."""
    r = bot(de, acao="cat:edit")
    for s in r.saidas:
        for linha in s.botoes:
            for b in linha:
                if b.rotulo == rotulo and b.acao:
                    return b.acao
    raise AssertionError(f"categoria {rotulo} não está na lista")


def test_conta_nova_ja_vem_com_as_categorias_padrao(bot: Bot) -> None:
    de = _conta(bot)
    r = bot(de, comando="categorias")
    texto = r.saidas[0].texto
    assert "🛒 Mercado" in texto
    assert "💼 Salário" in texto
    assert acoes(r) == ["cat:nova", "cat:edit"]


def test_cria_renomeia_troca_emoji_e_desativa(bot: Bot) -> None:
    de = _conta(bot)
    r = bot(de, acao="cat:nova:e")
    assert r.saidas[0].pergunta == "cat_nova_gasto"
    r = bot(de, pergunta="cat_nova_gasto", texto="academia 🏋️")
    assert r.saidas[0].texto == t.CATEGORIA_CRIADA.format(rotulo="🏋️ Academia")
    r = bot(de, pergunta="cat_nova_gasto", texto="🏋️ ACADEMIA")
    assert r.saidas[0].texto == t.CATEGORIA_JA_EXISTE.format(nome="ACADEMIA")

    acao = _abre(bot, de, "🏋️ Academia")
    r = bot(de, acao=acao)
    assert acoes(r)[2].startswith("cat:off:")
    r = bot(de, acao=acoes(r)[0])  # renomear
    assert r.saidas[0].texto.endswith("\n🏋️ Academia")
    r = bot(de, pergunta="cat_renomear", contexto="🏋️ Academia", texto="Crossfit")
    assert r.saidas[0].texto == t.CATEGORIA_RENOMEADA.format(rotulo="🏋️ Crossfit")
    r = bot(de, pergunta="cat_emoji", contexto="🏋️ Crossfit", texto="🤸")
    assert r.saidas[0].texto == t.CATEGORIA_RENOMEADA.format(rotulo="🤸 Crossfit")
    r = bot(de, pergunta="cat_emoji", contexto="🤸 Crossfit", texto="não é emoji")
    assert r.saidas[0].texto == t.CATEGORIA_EMOJI_INVALIDO

    detalhe = bot(de, acao=_abre(bot, de, "🤸 Crossfit"))
    desativar = acoes(detalhe)[2]
    assert bot(de, acao=desativar).saidas[0].texto.startswith("🚫 🤸 Crossfit desativada")
    assert "🚫 Desativadas: 🤸 Crossfit" in bot(de, comando="categorias").saidas[0].texto
    bot(de, acao=desativar.replace("cat:off:", "cat:on:"))
    assert "Desativadas" not in bot(de, comando="categorias").saidas[0].texto


def test_outros_nao_pode_ser_desativada(bot: Bot) -> None:
    de = _conta(bot)
    r = bot(de, acao=_abre(bot, de, "📦 Outros"))
    assert not any(a.startswith("cat:off:") for a in acoes(r))
    # Mesmo com o botão forjado.
    forjado = acoes(r)[0].replace("cat:ren:", "cat:off:")
    r = bot(de, acao=forjado)
    assert r.saidas[0].texto == t.CATEGORIA_FIXA.format(rotulo="📦 Outros")


def test_botao_com_categoria_de_outra_conta_nao_faz_nada(bot: Bot) -> None:
    a, b = _conta(bot), _conta(bot)
    acao_de_b = _abre(bot, b, "🛒 Mercado")
    id_de_b = acao_de_b.removeprefix("cat:ed:")
    for tipo in ("ed", "ren", "emo", "off", "on"):
        r = bot(a, acao=f"cat:{tipo}:{id_de_b}")
        assert r.saidas[0].texto == t.CATEGORIA_SUMIU
    assert "🛒 Mercado" in bot(b, comando="categorias").saidas[0].texto


def test_contexto_desconhecido_nao_altera_nada(bot: Bot) -> None:
    de = _conta(bot)
    r = bot(de, pergunta="cat_renomear", contexto="🧪 Inexistente", texto="Qualquer")
    assert r.saidas[0].texto == t.CATEGORIA_SUMIU

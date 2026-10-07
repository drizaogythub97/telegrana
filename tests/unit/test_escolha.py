"""Pergunta com botões respondida escrevendo (07/10/2026)."""

from __future__ import annotations

from typing import Any

import pytest

from telegrana.core import escolha
from telegrana.core.entendimento import ErroExtracao
from telegrana.core.extracao import EscolhaIA
from telegrana.core.mensagens import Botao, Saida

REGRA = escolha.Aberta(
    "🧠 Quer que eu lembre: «tim» é sempre 📱 Assinaturas?",
    (("✅ Sempre", "rg:abc:tim"), ("Só desta vez", "rg:no")),
)
FIXO = escolha.Aberta(
    "✅ Gasto registrado ... 🔁 Isso se repete todo mês?",
    (
        ("✏️ Corrigir", "tx:fix:1"),
        ("🏷️ Categoria", "tx:cat:1"),
        ("🔁 Sim, todo mês", "fx:s:1"),
        ("Não", "fx:n:1"),
    ),
)
CATEGORIA = escolha.Aberta(
    "🏷️ Qual a categoria certa para R$ 55,00?",
    (("🛒 Mercado", "tx:sc:1:a"), ("📱 Assinaturas", "tx:sc:1:b"), ("📦 Outros", "tx:sc:1:c")),
)


@pytest.mark.parametrize(
    ("aberta", "texto", "indice"),
    [
        (REGRA, "Exato", 0),
        (REGRA, "isso mesmo!", 0),
        (REGRA, "👍", 0),
        (REGRA, "não", 1),
        (REGRA, "só desta vez", 1),
        (REGRA, "sempre", 0),
        (FIXO, "sim", 2),
        (FIXO, "Não", 3),
        (CATEGORIA, "assinaturas", 1),
        (CATEGORIA, "Outros", 2),
        (CATEGORIA, "sim", None),  # nenhuma opção aceita: fica para a IA
        (REGRA, "deixa assim mesmo", None),
    ],
)
def test_rapida(aberta: escolha.Aberta, texto: str, indice: int | None) -> None:
    assert escolha.rapida(texto, aberta) == indice


def pergunta(texto: str, *botoes: tuple[str, str]) -> Saida:
    return Saida(texto, botoes=(tuple(Botao(r, a) for r, a in botoes),))


def test_da_saida_pega_a_ultima_pergunta_com_botoes() -> None:
    recibo = pergunta("✏️ **Corrigido**\n📱 Assinaturas · R$ 55,00", ("✏️ Corrigir", "tx:fix:1"))
    regra = pergunta(
        "🧠 Quer que eu lembre: «tim» é sempre 📱 Assinaturas?",
        ("✅ Sempre", "rg:x:tim"),
        ("Só desta vez", "rg:no"),
    )
    aberta = escolha.da_saida([recibo, regra])
    assert aberta is not None
    assert aberta.opcoes == (("✅ Sempre", "rg:x:tim"), ("Só desta vez", "rg:no"))
    assert escolha.Aberta.le(aberta.guarda()) == aberta
    assert escolha.da_saida([regra, recibo]) is None  # a última com botões não pergunta
    assert escolha.da_saida([recibo]) is None


def test_da_saida_deixa_de_fora_o_que_so_vale_com_toque() -> None:
    assert (
        escolha.da_saida(
            [pergunta("⚠️ Última confirmação. Apagar tudo agora?", ("🗑️ Sim", "apagar:2"))]
        )
        is None
    )
    assert escolha.da_saida([pergunta("Gerar código novo?", ("🔑 Gerar", "cod:novo"))]) is None
    assert escolha.da_saida([pergunta("Qual conta é dela?", ("👤 Ana", "adm:rl:1:2"))]) is None
    assert escolha.da_saida([pergunta("🗑️ Apagar o fixo **Luz**?", ("Apagar", "fi:del:1"))]) is None
    recibo = pergunta(
        "✅ Gasto registrado\n🔁 Isso se repete todo mês?",
        ("🗑️ Apagar", "tx:del:1"),
        ("🔁 Sim, todo mês", "fx:s:1"),
    )
    aberta = escolha.da_saida([recibo])
    assert aberta is not None
    assert aberta.opcoes == (("🔁 Sim, todo mês", "fx:s:1"),)
    assert escolha.da_saida([Saida("Pergunta?", destino="admin", botoes=recibo.botoes)]) is None


@pytest.mark.parametrize(
    ("texto", "plausivel"),
    [("deixa assim mesmo", True), ("uber 20 no pix", False), ("a " * 13, False), ("", False)],
)
def test_plausivel(texto: str, plausivel: bool) -> None:
    assert escolha.plausivel(texto, REGRA) is plausivel


class IA:
    def __init__(self, opcao: int | None, erro: bool = False) -> None:
        self.opcao, self.erro, self.chamadas = opcao, erro, 0
        self.ultimo_uso: Any = None

    def escolha(self, pergunta: str, opcoes: list[str], texto: str) -> tuple[EscolhaIA, str]:
        self.chamadas += 1
        if self.erro:
            raise ErroExtracao("fora do ar")
        return EscolhaIA(opcao=self.opcao), "m"


def test_escolhe() -> None:
    assert escolha.escolhe(IA(2), "exato", REGRA) == escolha.Escolha(0, "codigo")
    assert escolha.escolhe(IA(2), "deixa assim mesmo", REGRA).indice == 1
    assert escolha.escolhe(IA(None), "nem sei", REGRA).indice is None
    assert escolha.escolhe(IA(9), "nem sei", REGRA).indice is None  # fora da lista
    assert escolha.escolhe(IA(1, erro=True), "nem sei", REGRA) == escolha.Escolha(None, "nenhuma")
    ia = IA(1)
    assert escolha.escolhe(ia, "uber 20 no pix", REGRA).indice is None
    assert ia.chamadas == 0  # gasto novo: nem pergunta
    assert escolha.escolhe(None, "nem sei", REGRA).indice is None


@pytest.mark.parametrize(
    ("texto", "jeito"),
    [
        ("Exato", "sim"),
        ("ok", "sim"),
        ("👍", "sim"),
        ("valeu!", "gratidao"),
        ("Obrigada", "gratidao"),
        ("não", "nao"),
        ("oi", None),
        ("mercado 45", None),
    ],
)
def test_concordancia(texto: str, jeito: str | None) -> None:
    assert escolha.concordancia(texto) == jeito

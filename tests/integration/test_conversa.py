"""Conversa (D050): o que não é lançamento nem consulta recebe resposta da IA de conversa.

O caso real (08/10/2026): "Quero cadastrar um gasto fixo." recebia "🤔 Não entendi bem".
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from telegrana.core import conta as conta_mod
from telegrana.core import textos as t
from telegrana.core.entendimento import ErroExtracao
from telegrana.core.extracao import ConversaIA
from telegrana.infra import db
from tests.conftest import Banco
from tests.integration.test_cadastro import CTX, Bot, conn
from tests.integration.test_fixos import acao, fixos_de
from tests.integration.test_lancamentos import IAFalsa, Uso, conta, extracao, item, lancamentos_de

pytestmark = pytest.mark.integration
__all__ = ["conn"]

FIXO = "Quero cadastrar um gasto fixo."
ALUGUEL = "o aluguel é 1500 e vence dia 10"
DEPOIS = "ainda não sei, depois te falo"


class IAQueConversa(IAFalsa):
    def __init__(self) -> None:
        super().__init__()
        self.respostas[FIXO] = extracao(intencao="fora_do_escopo")
        self.respostas["tenho um cartão novo"] = extracao(intencao="conversa")
        self.respostas["me indica um site"] = extracao(intencao="fora_do_escopo")
        self.respostas["sem ia de conversa"] = extracao(intencao="fora_do_escopo")
        self.respostas[DEPOIS] = extracao(intencao="conversa")
        self.respostas[ALUGUEL] = extracao(
            item(valor_texto="1500", data_texto="dia 10", descricao="aluguel", categoria="moradia")
        )
        self.respostas["a internet é 120 e vence dia 5"] = extracao(
            item(
                valor_texto="120", data_texto="dia 5", descricao="internet", categoria="contas_casa"
            )
        )
        self.perguntas_abertas: list[str] = []
        self.conversas: dict[str, ConversaIA] = {
            FIXO: ConversaIA(
                resposta="Claro! Me manda o nome, o valor e o dia, assim: «aluguel 1500 todo dia 10».",
                abrir="fixo_novo",
            ),
            "tenho um cartão novo": ConversaIA(resposta="Vamos cadastrar! 💳", abrir="cartao_novo"),
            DEPOIS: ConversaIA(
                resposta="Tudo bem, quando souber me manda o valor.", abrir="nenhuma"
            ),
            "me indica um site": ConversaIA(
                resposta="Veja **https://exemplo.com** e `www.x.com` aqui.", abrir="nenhuma"
            ),
        }

    def conversa(self, texto: str, pergunta: str = "") -> tuple[ConversaIA, str]:
        self.chamadas += 1
        self.perguntas_abertas.append(pergunta)
        if texto not in self.conversas:
            raise ErroExtracao("fora do ar")
        self.ultimo_uso = Uso(800, 70)
        return self.conversas[texto], "openai/gpt-oss-120b"


@pytest.fixture
def ia() -> IAQueConversa:
    return IAQueConversa()


@pytest.fixture
def bot(conn: db.Connection, ia: IAQueConversa) -> Bot:
    return Bot(conn, replace(CTX, extrator=ia))


def test_quero_cadastrar_um_fixo_e_a_proxima_mensagem_vira_o_fixo(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, texto=FIXO)
    assert r.rotulo == "lancamento.conversa.fixo_novo"
    assert r.saidas[0].texto.startswith("Claro! Me manda o nome")
    r = bot(de, texto=ALUGUEL)  # sem "todo mês": a conversa já combinou que é fixo
    assert r.rotulo.endswith(".solta")
    assert r.saidas[0].texto.startswith(t.FIXO_CRIADO)
    [fixo] = fixos_de(banco, de)
    assert (fixo[2], fixo[4]) == (150000, 10)
    assert lancamentos_de(banco, de) == []  # só cadastrou, não lançou


def test_a_combinacao_do_fixo_vale_para_uma_mensagem(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    bot(de, texto=FIXO)
    bot(de, texto="mercado 45 no pix")  # mudou de assunto: lançamento comum
    r = bot(de, texto=ALUGUEL)
    assert not r.rotulo.endswith(".solta")
    assert fixos_de(banco, de) == []


def test_conversa_abre_a_tela(bot: Bot) -> None:
    de = conta(bot)
    r = bot(de, texto="tenho um cartão novo")
    assert r.saidas[0].texto == "Vamos cadastrar! 💳"
    assert r.saidas[-1].pergunta == "ct_nome"  # a tela do ➕ Novo cartão veio junto
    r = bot(de, texto="Inter")  # e a resposta solta continua valendo
    assert r.saidas[0].pergunta == "ct_dias"


def test_resposta_sem_link_nem_marcacao(bot: Bot) -> None:
    de = conta(bot)
    texto = bot(de, texto="me indica um site").saidas[0].texto
    assert "http" not in texto
    assert "www." not in texto
    assert "*" not in texto
    assert "`" not in texto


def test_sem_ia_de_conversa_volta_o_texto_fixo(bot: Bot) -> None:
    de = conta(bot)
    r = bot(de, texto="sem ia de conversa")
    assert r.saidas[0].texto == t.NAO_ENTENDI


def test_respondeu_a_pergunta_com_outra_coisa(bot: Bot, ia: IAQueConversa, banco: Banco) -> None:
    """Visto no Telegram Web (08/10/2026): respondendo (com "Responder") a "Quanto…?" com
    outra coisa, o bot só repetia a pergunta. Agora a mensagem segue como nova, a IA sabe
    da pergunta, e ela continua aberta para a próxima mensagem."""
    de = conta(bot)
    r = bot(de, texto="aluguel 1500 todo dia 10")
    cartao = bot(de, acao=acao(r, "fi:ed:"))
    pergunta = bot(de, acao=acao(cartao, "fi:va:"))
    contexto = pergunta.saidas[0].texto.splitlines()[1]
    r = bot(de, texto=DEPOIS, pergunta="fi_valor", contexto=contexto)
    assert r.rotulo == "lancamento.conversa.nenhuma"
    assert ia.perguntas_abertas[-1].startswith("💰 Qual é o novo valor deste fixo?")
    r = bot(de, texto="1600")  # a pergunta continuou aberta
    assert r.saidas[0].texto.startswith(t.FIXO_ATUALIZADO)
    assert fixos_de(banco, de)[0][2] == 160000


def test_frase_nao_vira_nome_de_cartao(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    bot(de, acao="ct:nv")
    r = bot(de, texto=FIXO, pergunta="ct_nome")
    assert r.rotulo == "lancamento.conversa.fixo_novo"
    assert not r.saidas[0].texto.startswith(t.CARTAO_CRIADO)
    r = bot(de, texto="Inter", pergunta="ct_nome")  # a resposta de verdade segue valendo
    assert r.saidas[0].pergunta == "ct_dias"


@pytest.mark.parametrize(
    ("pergunta", "texto", "nao"),
    [
        ("fa_valor", "Quero cadastrar um gasto fixo", True),
        ("fa_valor", "uns 50", False),
        ("fa_valor", "cento e oitenta", False),
        ("ct_nome", "Banco do Brasil", False),
        ("ct_nome", "quero ver minhas faturas por favor", True),
        ("ct_dias", "não sei ainda os dias", True),
        ("ct_dias", "fecha dia três vence dia dez", False),
        ("fi_dia", "dia doze", False),
        ("lc_data", "foi semana passada eu acho", False),
        ("nome", "qualquer coisa aqui mesmo", False),
    ],
)
def test_nao_responde(pergunta: str, texto: str, nao: bool) -> None:
    assert conta_mod.nao_responde(pergunta, texto) is nao


def test_assunto_novo_ganha_da_pergunta_antiga(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, texto="aluguel 1500 todo dia 10")
    cartao = bot(de, acao=acao(r, "fi:ed:"))
    pergunta = bot(de, acao=acao(cartao, "fi:va:"))
    contexto = pergunta.saidas[0].texto.splitlines()[1]
    r = bot(de, texto=FIXO, pergunta="fi_valor", contexto=contexto)
    assert r.rotulo == "lancamento.conversa.fixo_novo"
    r = bot(de, texto="a internet é 120 e vence dia 5")
    assert r.saidas[0].texto.startswith(t.FIXO_CRIADO)
    assert [(x[0], x[2]) for x in fixos_de(banco, de)] == [("Aluguel", 150000), ("Internet", 12000)]

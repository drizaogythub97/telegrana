"""Resposta solta (sem "Responder"): Telegram Web e Desktop não abrem a resposta sozinhos."""

from __future__ import annotations

from dataclasses import replace

import pytest

from telegrana.core import conta as conta_mod
from telegrana.core import textos as t
from telegrana.core.entendimento import ErroExtracao
from telegrana.core.extracao import EscolhaIA
from telegrana.core.mensagens import Resultado
from telegrana.infra import db
from tests.conftest import Banco
from tests.integration.test_cadastro import CTX, Bot, conn
from tests.integration.test_fixos import acao, fixos_de
from tests.integration.test_lancamentos import (
    IAFalsa,
    Uso,
    conta,
    extracao,
    item,
    lancamentos_de,
)

pytestmark = pytest.mark.integration
__all__ = ["conn"]


@pytest.fixture
def bot(conn: db.Connection) -> Bot:
    return Bot(conn, replace(CTX, extrator=IAFalsa()))


def test_cartao_novo_pelo_cartoes_sem_responder(bot: Bot) -> None:
    de = conta(bot)
    bot(de, acao="ct:nv")
    r = bot(de, texto="Inter")
    assert r.rotulo.endswith(".solta")
    assert r.saidas[0].pergunta == "ct_dias"
    r = bot(de, texto="fecha 25, vence 5")
    assert r.saidas[0].texto.startswith(t.CARTAO_CRIADO)


def test_valor_do_fixo_e_do_lancamento_sem_responder(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, texto="aluguel 1500 todo dia 10")
    cartao = bot(de, acao=acao(r, "fi:ed:"))
    bot(de, acao=acao(cartao, "fi:va:"))
    r = bot(de, texto="1600")
    assert r.saidas[0].texto.startswith(t.FIXO_ATUALIZADO)
    assert fixos_de(banco, de)[0][2] == 160000
    bot(de, texto="gastei no mercado")  # pergunta o valor
    r = bot(de, texto="45")
    assert r.saidas[0].texto.startswith(t.REGISTRADO["expense"])
    assert lancamentos_de(banco, de)[0][1:3] == (4500, "mercado")


def test_mensagem_que_nao_e_resposta_segue_e_a_pergunta_fecha(bot: Bot, banco: Banco) -> None:
    de = conta(bot)
    r = bot(de, texto="aluguel 1500 todo dia 10")
    cartao = bot(de, acao=acao(r, "fi:ed:"))
    bot(de, acao=acao(cartao, "fi:va:"))
    r = bot(de, texto="mercado 50 no pix")  # não é só um valor: gasto novo
    assert r.saidas[0].texto.startswith(t.REGISTRADO["expense"])
    r = bot(de, texto="1600")  # a pergunta valia para UMA mensagem
    assert not r.rotulo.endswith(".solta")
    assert fixos_de(banco, de)[0][2] == 150000


@pytest.mark.parametrize(
    ("pergunta", "texto", "contexto", "cabe"),
    [
        ("lm_valor", "a luz deu 187", "🔔 Luz · 15/10/2026", True),
        ("lm_valor", "mercado 50", "🔔 Luz · 15/10/2026", False),
        ("ct_nome", "Banco do Brasil", "", True),
        ("ct_nome", "uber 12", "", False),
        ("ct_dias", "fecha 3 vence 10", "💳 Nubank", True),
        ("fi_dia", "dia doze", "🔁 Aluguel", True),
        ("fi_dia", "paguei o aluguel ontem no pix", "🔁 Aluguel", False),
        ("lc_data", "ontem", "", True),
        ("nome", "Fulano de Tal", "", False),  # fora da lista: só respondendo
    ],
)
def test_cara_de_resposta(pergunta: str, texto: str, contexto: str, cabe: bool) -> None:
    assert conta_mod.cabe(pergunta, texto, contexto) is cabe


# ---------------------------------------------------------------------------
# Pergunta com botões respondida escrevendo (07/10/2026: "Exato" virava "Oi!")
# ---------------------------------------------------------------------------
TIM = "a conta da tim deu 55 reais"


class IAQueEscolhe(IAFalsa):
    """IA falsa que também aponta a opção de uma pergunta com botões."""

    def __init__(self) -> None:
        super().__init__()
        self.escolhas: dict[str, int | None] = {"deixa assim mesmo": 2, "nem sei": None}
        self.respostas[TIM] = extracao(
            item(valor_texto="55 reais", descricao="Tim", categoria="outros")
        )
        self.perguntas: list[tuple[str, list[str]]] = []

    def escolha(self, pergunta: str, opcoes: list[str], texto: str) -> tuple[EscolhaIA, str]:
        self.chamadas += 1
        self.perguntas.append((pergunta, opcoes))
        if texto not in self.escolhas:
            raise ErroExtracao("resposta desconhecida")
        self.ultimo_uso = Uso(300, 5)
        return EscolhaIA(opcao=self.escolhas[texto]), "openai/gpt-oss-120b"


@pytest.fixture
def ia_escolhe() -> IAQueEscolhe:
    return IAQueEscolhe()


@pytest.fixture
def bot_escolhe(conn: db.Connection, ia_escolhe: IAQueEscolhe) -> Bot:
    return Bot(conn, replace(CTX, extrator=ia_escolhe))


def toque(r: Resultado, rotulo: str) -> str:
    return next(b.acao for s in r.saidas for li in s.botoes for b in li if rotulo in b.rotulo)


def regras_de(banco: Banco, de: str) -> list[tuple[str, str]]:
    with db.connect(banco.migrator) as c:
        return [
            (str(x[0]), str(x[1]))
            for x in c.execute(
                "select r.pattern, c.name from telegrana.category_rules r"
                " join telegrana.categories c on c.id = r.category_id"
                " join telegrana.account_members m on m.account_id = r.account_id"
                " join telegrana.user_channels u on u.user_id = m.user_id"
                " where u.external_id = %s",
                (de,),
            ).fetchall()
        ]


def ate_o_corrigido(bot: Bot, de: str) -> Resultado:
    """O caminho do print (07/10/2026): a categoria é perguntada, a pessoa toca 📦 Outros,
    depois troca para 🎮 Lazer pelo recibo."""
    pergunta = bot(de, texto=TIM)
    recibo = bot(de, acao=toque(pergunta, "Outros"))
    assert recibo.saidas[-1].texto.startswith("🧠 Quer que eu lembre")
    tela = bot(de, acao=acao(recibo, "tx:cat:"))
    return bot(de, acao=toque(tela, "Lazer"))


def test_trocou_a_categoria_e_respondeu_exato(
    bot_escolhe: Bot, ia_escolhe: IAQueEscolhe, banco: Banco
) -> None:
    """O caso do print: troca a categoria pelo recibo, o bot oferece lembrar a categoria
    NOVA e "Exato" vale como ✅ Sempre (sem IA: o código entende)."""
    bot, de = bot_escolhe, conta(bot_escolhe)
    r = ate_o_corrigido(bot, de)
    assert r.saidas[0].texto.startswith(t.CORRIGIDO)
    assert r.saidas[-1].texto.startswith("🧠 Quer que eu lembre")
    assert "Lazer" in r.saidas[-1].texto
    antes = ia_escolhe.chamadas
    r = bot(de, texto="Exato")
    assert r.rotulo.endswith(".solta")
    assert r.saidas[0].texto.startswith("🧠 Pronto")
    assert ("tim", "Lazer") in regras_de(banco, de)
    assert ia_escolhe.chamadas == antes  # o óbvio sai do código
    r = bot(de, texto="exato")  # sem pergunta aberta: concorda, não cumprimenta
    assert r.saidas[0].texto == t.CONCORDA["sim"]
    assert bot(de, texto="valeu").saidas[0].texto == t.CONCORDA["gratidao"]


def test_resposta_que_so_a_ia_entende(
    bot_escolhe: Bot, ia_escolhe: IAQueEscolhe, banco: Banco
) -> None:
    bot, de = bot_escolhe, conta(bot_escolhe)
    ate_o_corrigido(bot, de)
    r = bot(de, texto="deixa assim mesmo")  # IA: opção 2 = Só desta vez
    assert r.rotulo.endswith(".solta.ia")
    assert r.saidas[0].texto == "👍"
    assert regras_de(banco, de) == []
    pergunta, opcoes = ia_escolhe.perguntas[-1]
    assert pergunta.startswith("🧠 Quer que eu lembre")
    assert opcoes == ["✅ Sempre", "Só desta vez"]


def test_ia_sem_certeza_e_gasto_novo_seguem_como_mensagem(
    bot_escolhe: Bot, ia_escolhe: IAQueEscolhe, banco: Banco
) -> None:
    bot, de = bot_escolhe, conta(bot_escolhe)
    ate_o_corrigido(bot, de)
    antes = ia_escolhe.chamadas
    r = bot(de, texto="uber 20 no pix")  # gasto novo: nem pergunta à IA
    assert r.saidas[0].texto.startswith(t.REGISTRADO["expense"])
    assert ia_escolhe.chamadas == antes
    assert regras_de(banco, de) == []


def test_pergunta_que_apaga_so_com_toque(bot_escolhe: Bot, banco: Banco) -> None:
    bot, de = bot_escolhe, conta(bot_escolhe)
    bot(de, comando="apagar_conta")
    r = bot(de, texto="sim")
    assert not r.rotulo.startswith("conta.apagar")
    with db.connect(banco.migrator) as c:
        assert c.execute(
            "select count(*) from telegrana.user_channels where external_id = %s", (de,)
        ).fetchone() == (1,)

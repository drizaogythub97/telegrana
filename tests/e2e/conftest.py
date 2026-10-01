"""E2E simulado (PLANO 10.1; D034): o handler real da Lambda, banco real, Telegram simulado.

As contas de teste do servidor de testes do Telegram estão desativadas desde 06/2025
(tdlib/td#3370). Aqui cada pessoa é um "aplicativo" que monta updates no formato do
Telegram e os entrega ao `bot.handler` com o segredo do webhook; as respostas passam
pela Bot API simulada, que recusa o que o Telegram recusaria.
Rodar: `uv run pytest -m e2e`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest

from telegrana.channels.telegram.api import TelegramAPI
from telegrana.entrypoints import bot
from telegrana.infra import config
from tests.conftest import Banco
from tests.e2e.telegram_simulado import (
    BOT_ID,
    TOKEN,
    MensagemDoBot,
    RecusaDoTelegram,
    TelegramSimulado,
)
from tests.unit.test_webhook import SEGREDO, evento

ADMIN_ID = 900_000_001


class _Erros(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.ERROR)
        self.registros: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.registros.append(f"{record.getMessage()} {getattr(record, 'erro', '')}")


@dataclass
class Pessoa:
    """O aplicativo de uma pessoa: manda updates e lê o que o bot respondeu."""

    mundo: Mundo
    id: int
    nome: str
    telefone: str
    username: str | None = None
    lidas: int = 0  # id da última mensagem do bot já consumida
    _msg_ids: Any = field(default=None)

    def _de(self) -> dict[str, Any]:
        partes = self.nome.split(" ", 1)
        base: dict[str, Any] = {"id": self.id, "is_bot": False, "first_name": partes[0]}
        if len(partes) > 1:
            base["last_name"] = partes[1]
        if self.username:
            base["username"] = self.username
        return base

    def _mensagem(self, **conteudo: Any) -> None:
        self.mundo.tg.chats.add(self.id)
        self.mundo.entrega(
            {
                "message": {
                    "message_id": self.mundo.tg.proximo_id(),
                    "from": self._de(),
                    "chat": {"id": self.id, "type": "private"},
                    "date": 1_790_000_000,
                    **conteudo,
                }
            }
        )

    # --- ações ---------------------------------------------------------------
    def diz(self, texto: str) -> None:
        self._mensagem(text=texto)

    def responde(self, texto: str) -> None:
        """Responde à última pergunta do bot (o app abre a resposta sozinho: force reply)."""
        pergunta = next(
            (m for m in reversed(self._recebidas()) if m.teclado and m.teclado.get("force_reply")),
            None,
        )
        if pergunta is None:
            raise AssertionError(f"{self.nome}: nenhuma pergunta do bot para responder")
        self._mensagem(
            text=texto,
            reply_to_message={
                "message_id": pergunta.id,
                "from": {"id": BOT_ID, "is_bot": True, "first_name": "Telegrana"},
                "chat": {"id": self.id, "type": "private"},
                "text": pergunta.texto,
            },
        )

    def toca(self, rotulo: str) -> None:
        for msg in reversed(self._recebidas()):
            for botao in msg.botoes():
                if rotulo in botao["text"] and "callback_data" in botao:
                    consulta = f"cb{self.mundo.tg.proximo_id()}"
                    self.mundo.tg.callbacks_abertos.add(consulta)
                    self.mundo.entrega(
                        {
                            "callback_query": {
                                "id": consulta,
                                "from": self._de(),
                                "message": {
                                    "message_id": msg.id,
                                    "chat": {"id": self.id, "type": "private"},
                                },
                                "chat_instance": "1",
                                "data": botao["callback_data"],
                            }
                        }
                    )
                    if consulta in self.mundo.tg.callbacks_abertos:
                        raise RecusaDoTelegram("o bot não respondeu ao toque (answerCallbackQuery)")
                    return
        raise AssertionError(f"{self.nome}: botão {rotulo!r} não está na tela")

    def compartilha_meu_numero(self) -> None:
        """O botão "📱 Compartilhar meu número" só existe se o bot mostrou esse teclado."""
        if not self.mundo.tg.teclado_de_contato.get(self.id):
            raise AssertionError(f"{self.nome}: o teclado de contato não está na tela")
        self._mensagem(
            contact={
                "phone_number": self.telefone,
                "first_name": self.nome,
                "user_id": self.id,
            }
        )

    def anexa_contato_de(self, outra: Pessoa) -> None:
        """Contato de outra pessoa, pelo clipe de anexos (não pelo botão)."""
        self._mensagem(
            contact={
                "phone_number": outra.telefone,
                "first_name": outra.nome,
                "user_id": outra.id,
            }
        )

    # --- leitura ---------------------------------------------------------------
    def _recebidas(self) -> list[MensagemDoBot]:
        return [m for m in self.mundo.tg.mensagens.values() if m.chat == self.id]

    def espera(self, trecho: str) -> MensagemDoBot:
        """A mensagem mais recente, ainda não lida, que contém `trecho`."""
        novas = [m for m in self._recebidas() if m.id > self.lidas]
        for msg in reversed(novas):
            if trecho in msg.texto:
                self.lidas = msg.id
                return msg
        ultimas = [m.texto[:70] for m in novas[-4:]]
        raise AssertionError(f"{self.nome}: nada com {trecho!r}; chegou: {ultimas}")

    def nada_novo(self) -> None:
        novas = [m.texto[:70] for m in self._recebidas() if m.id > self.lidas]
        assert not novas, f"{self.nome} não deveria receber nada, mas recebeu {novas}"


@dataclass
class Mundo:
    tg: TelegramSimulado
    proximo_update: int = 1

    def entrega(self, update: dict[str, Any]) -> None:
        corpo = json.dumps({"update_id": self.proximo_update, **update})
        self.proximo_update += 1
        resposta = bot.handler(evento(corpo=corpo, segredo=SEGREDO), None)
        assert resposta["statusCode"] == 200

    def pessoa(self, id_: int, nome: str, telefone: str, username: str | None = None) -> Pessoa:
        p = Pessoa(self, id_, nome, telefone, username)
        p.lidas = max(self.tg.mensagens, default=0)
        return p


@pytest.fixture(scope="session")
def mundo(banco: Banco) -> Iterator[Mundo]:
    tg = TelegramSimulado()
    mp = pytest.MonkeyPatch()
    settings = config.Settings(
        env="dev",
        admin_telegram_id=ADMIN_ID,
        telegram_bot_token=TOKEN,
        telegram_webhook_secret=SEGREDO,
        database_url=banco.app,
        phone_hmac_pepper="cGVwcGVyLWUyZS1wZXBwZXItZTJlLXBlcHBlci1lMmUtcGVw",
        legal_termos=json.dumps(
            {"versao": 1, "url": "https://telegra.ph/termos-e2e", "sha256": "01" * 32}
        ),
        legal_privacidade=json.dumps(
            {"versao": 1, "url": "https://telegra.ph/privacidade-e2e", "sha256": "02" * 32}
        ),
        admin_contact="@admin_e2e",
    )
    mp.setattr(bot, "_settings", settings)
    mp.setattr(bot, "_api", TelegramAPI(TOKEN, client=tg.cliente()))
    mp.setattr(bot, "_conn", None)
    mp.setattr(bot, "_ctx", None)
    mp.setattr(bot, "_username", None)
    erros = _Erros()
    logging.getLogger("telegrana").addHandler(erros)
    yield Mundo(tg)
    logging.getLogger("telegrana").removeHandler(erros)
    if bot._conn is not None:
        bot._conn.close()
    mp.undo()
    assert not erros.registros, f"o bot registrou erros durante o E2E: {erros.registros}"

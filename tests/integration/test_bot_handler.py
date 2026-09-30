"""Handler da Lambda `bot` com banco real e Telegram falso."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from telegrana.entrypoints import bot, rotinas
from telegrana.infra import config, db
from tests.conftest import Banco
from tests.unit.test_webhook import SEGREDO, evento

pytestmark = pytest.mark.integration
ADMIN = 555000111


class TelegramFalso:
    def __init__(self) -> None:
        self.chamadas: list[tuple[str, Any]] = []

    def send_message(self, chat_id: int, text: str, **_: Any) -> dict[str, int]:
        self.chamadas.append(("sendMessage", chat_id))
        return {"message_id": 1}

    def leave_chat(self, chat_id: int) -> bool:
        self.chamadas.append(("leaveChat", chat_id))
        return True


@pytest.fixture
def telegram(banco: Banco, monkeypatch: pytest.MonkeyPatch) -> Iterator[TelegramFalso]:
    falso = TelegramFalso()
    settings = config.Settings(
        env="dev",
        admin_telegram_id=ADMIN,
        telegram_bot_token="123:falso",
        telegram_webhook_secret=SEGREDO,
        database_url=banco.app,
    )
    monkeypatch.setattr(bot, "_settings", settings)
    monkeypatch.setattr(bot, "_api", falso)
    monkeypatch.setattr(bot, "_conn", None)
    yield falso
    if bot._conn is not None:
        bot._conn.close()


_proximo_id = iter(range(900_000, 1_000_000))


def update(**conteudo: Any) -> tuple[int, dict[str, object]]:
    update_id = next(_proximo_id)
    return update_id, evento(corpo=json.dumps({"update_id": update_id, **conteudo}))


def msg(de: int, texto: str, tipo: str = "private", chat: int | None = None) -> dict[str, Any]:
    return {
        "message": {"from": {"id": de}, "chat": {"id": chat or de, "type": tipo}, "text": texto}
    }


def test_segredo_errado_nao_processa_nem_grava(telegram: TelegramFalso, banco: Banco) -> None:
    update_id, ev = update(**msg(ADMIN, "/start"))
    ev["headers"]["X-Telegram-Bot-Api-Secret-Token"] = "errado"  # type: ignore[index]
    assert bot.handler(ev, None)["statusCode"] == 401
    assert telegram.chamadas == []
    with db.connect(banco.migrator) as conn:
        gravado = conn.execute(
            "select 1 from telegrana.processed_updates where update_id = %s", (update_id,)
        ).fetchone()
    assert gravado is None


def test_admin_start_responde_uma_unica_vez(telegram: TelegramFalso) -> None:
    _, ev = update(**msg(ADMIN, "/start"))
    assert bot.handler(ev, None)["statusCode"] == 200
    assert bot.handler(ev, None)["statusCode"] == 200  # reenvio do Telegram
    assert telegram.chamadas == [("sendMessage", ADMIN)]


def test_desconhecido_nao_recebe_resposta_na_s13(telegram: TelegramFalso) -> None:
    _, ev = update(**msg(777, "/start"))
    assert bot.handler(ev, None)["statusCode"] == 200
    assert telegram.chamadas == []


def test_mensagem_em_grupo_faz_o_bot_sair(telegram: TelegramFalso) -> None:
    _, ev = update(**msg(ADMIN, "/start", tipo="group", chat=-100123))
    bot.handler(ev, None)
    assert telegram.chamadas == [("leaveChat", -100123)]


def test_adicionado_a_grupo_sai(telegram: TelegramFalso) -> None:
    _, ev = update(
        my_chat_member={
            "chat": {"id": -100999, "type": "supergroup"},
            "new_chat_member": {"status": "member"},
        }
    )
    bot.handler(ev, None)
    assert telegram.chamadas == [("leaveChat", -100999)]


def test_update_malformado_e_recusado(telegram: TelegramFalso) -> None:
    ev = evento(corpo='{"sem": "update_id"}')
    assert bot.handler(ev, None)["statusCode"] == 400


def test_rotinas_apaga_so_o_que_venceu(banco: Banco) -> None:
    with db.connect(banco.migrator) as conn, conn.transaction():
        conn.execute(
            "insert into telegrana.processed_updates (channel, update_id, processed_at)"
            " values ('telegram', 1, now() - interval '8 days'), ('telegram', 2, now())"
        )
        conn.execute(
            "insert into telegrana.access_requests (channel, external_id, display_name, message, expires_at)"
            " values ('telegram', '1', 'Velho', 'oi', now() - interval '1 day'),"
            "        ('telegram', '2', 'Novo', 'oi', now() + interval '6 days')"
        )
    with db.connect(banco.app) as conn:
        resultado = rotinas.limpa(conn)
    assert resultado == {"updates_apagados": 1, "pedidos_expirados_apagados": 1}

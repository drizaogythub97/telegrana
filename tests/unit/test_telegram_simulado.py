"""O Telegram simulado do E2E recusa o que o Telegram de verdade recusaria (sabotagem)."""

from __future__ import annotations

import pytest

from telegrana.channels.telegram.api import TelegramAPI, TelegramError
from tests.e2e.telegram_simulado import TOKEN, RecusaDoTelegram, TelegramSimulado, texto_puro


@pytest.fixture
def api() -> tuple[TelegramAPI, TelegramSimulado]:
    tg = TelegramSimulado()
    tg.chats.add(42)
    return TelegramAPI(TOKEN, client=tg.cliente()), tg


def test_html_valido_vira_texto_puro() -> None:
    assert texto_puro("<b>Oi</b> &lt;x&gt; <code>A-1</code>") == "Oi <x> A-1"


@pytest.mark.parametrize("ruim", ["<b>aberto", "<b>x</i>", "<div>x</div>", "<b><i>x</b></i>"])
def test_html_invalido_e_recusado(ruim: str) -> None:
    with pytest.raises(RecusaDoTelegram):
        texto_puro(ruim)


@pytest.mark.parametrize(
    "teclado",
    [
        {"inline_keyboard": [[{"text": "x", "callback_data": "a" * 65}]]},
        {"inline_keyboard": [[{"text": "", "callback_data": "a"}]]},
        {"inline_keyboard": [[{"text": "x", "callback_data": "a", "url": "https://x"}]]},
        {"inline_keyboard": [[{"text": "x", "url": "javascript:alert(1)"}]]},
        {"teclado_inventado": True},
    ],
)
def test_teclado_malformado_e_recusado(
    api: tuple[TelegramAPI, TelegramSimulado], teclado: dict[str, object]
) -> None:
    cliente, _ = api
    with pytest.raises(RecusaDoTelegram):
        cliente.call("sendMessage", chat_id=42, text="x", parse_mode="HTML", reply_markup=teclado)


def test_chat_inexistente_vira_erro_da_api(api: tuple[TelegramAPI, TelegramSimulado]) -> None:
    cliente, _ = api
    with pytest.raises(TelegramError, match="chat not found"):
        cliente.call("sendMessage", chat_id=999, text="x", parse_mode="HTML")


def test_texto_longo_demais_e_recusado(api: tuple[TelegramAPI, TelegramSimulado]) -> None:
    cliente, _ = api
    with pytest.raises(RecusaDoTelegram):
        cliente.call("sendMessage", chat_id=42, text="x" * 4097, parse_mode="HTML")


def test_callback_respondido_duas_vezes_e_recusado(
    api: tuple[TelegramAPI, TelegramSimulado],
) -> None:
    cliente, tg = api
    tg.callbacks_abertos.add("cb1")
    cliente.call("answerCallbackQuery", callback_query_id="cb1")
    with pytest.raises(RecusaDoTelegram):
        cliente.call("answerCallbackQuery", callback_query_id="cb1")

"""Cliente da Bot API: o token nunca aparece em erros nem em logs."""

import json
import logging

import httpx
import pytest

from telegrana.channels.telegram.api import TelegramAPI, TelegramError
from telegrana.infra import logs

TOKEN = "123456789:AAtoken-secreto-de-teste"


def api_com(handler: httpx.MockTransport) -> TelegramAPI:
    client = httpx.Client(base_url="https://api.telegram.org", transport=handler)
    return TelegramAPI(TOKEN, client=client)


def test_chamada_ok_e_parametros_nulos_omitidos() -> None:
    vistos: list[httpx.Request] = []

    def responde(req: httpx.Request) -> httpx.Response:
        vistos.append(req)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})

    api = api_com(httpx.MockTransport(responde))
    assert api.send_message(10, "oi") == {"message_id": 7}
    assert vistos[0].url.path == f"/bot{TOKEN}/sendMessage"
    corpo = json.loads(vistos[0].content)
    assert corpo == {"chat_id": 10, "text": "oi", "parse_mode": "HTML"}


def test_servidor_de_testes_usa_caminho_test() -> None:
    vistos: list[str] = []

    def responde(req: httpx.Request) -> httpx.Response:
        vistos.append(req.url.path)
        return httpx.Response(200, json={"ok": True, "result": True})

    client = httpx.Client(
        base_url="https://api.telegram.org", transport=httpx.MockTransport(responde)
    )
    TelegramAPI(TOKEN, test_server=True, client=client).get_webhook_info()
    assert vistos == [f"/bot{TOKEN}/test/getWebhookInfo"]


def test_erro_de_rede_nao_vaza_token() -> None:
    def falha(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"falhou ao conectar em {req.url}")

    with pytest.raises(TelegramError) as info:
        api_com(httpx.MockTransport(falha)).send_message(1, "x")
    assert TOKEN not in str(info.value)
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__ is True


def test_resposta_de_erro_da_api() -> None:
    def recusa(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403, json={"ok": False, "description": "Forbidden: bot was blocked by the user"}
        )

    with pytest.raises(TelegramError, match="403 Forbidden"):
        api_com(httpx.MockTransport(recusa)).send_message(1, "x")


def test_resposta_nao_json() -> None:
    def html(req: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>bad gateway</html>")

    with pytest.raises(TelegramError, match="falha de comunicação"):
        api_com(httpx.MockTransport(html)).leave_chat(1)


def test_logs_de_http_silenciados(caplog: pytest.LogCaptureFixture) -> None:
    logs.configure()
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    caplog.set_level(logging.INFO)

    def ok(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": True})

    api_com(httpx.MockTransport(ok)).get_webhook_info()
    assert TOKEN not in caplog.text

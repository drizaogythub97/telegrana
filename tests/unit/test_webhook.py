"""Validação da entrada do webhook (PLANO 8.1)."""

import base64
import json

import pytest

from telegrana.channels.telegram import webhook

SEGREDO = "segredo_de_teste-123"


def evento(
    *,
    metodo: str = "POST",
    corpo: str | bytes = '{"update_id": 1}',
    segredo: str | None = SEGREDO,
    tipo: str = "application/json",
    b64: bool = False,
) -> dict[str, object]:
    headers = {"Content-Type": tipo}
    if segredo is not None:
        headers["X-Telegram-Bot-Api-Secret-Token"] = segredo
    bruto = corpo.encode() if isinstance(corpo, str) else corpo
    return {
        "requestContext": {"http": {"method": metodo}},
        "headers": headers,
        "body": base64.b64encode(bruto).decode() if b64 else bruto.decode(),
        "isBase64Encoded": b64,
    }


def motivo(ev: dict[str, object]) -> str | None:
    return webhook.motivo_recusa(webhook.request_from_event(ev), SEGREDO)


def test_requisicao_valida() -> None:
    assert motivo(evento()) is None
    assert motivo(evento(b64=True)) is None
    assert motivo(evento(tipo="application/json; charset=utf-8")) is None


@pytest.mark.parametrize(
    ("ev", "esperado"),
    [
        (evento(metodo="GET"), "metodo"),
        (evento(tipo="text/plain"), "tipo"),
        (evento(corpo="x" * (webhook.MAX_BODY_BYTES + 1)), "tamanho"),
        (evento(segredo=None), "segredo"),
        (evento(segredo="errado"), "segredo"),
        (evento(segredo=SEGREDO + "x"), "segredo"),
        (evento(segredo=""), "segredo"),
    ],
)
def test_recusas(ev: dict[str, object], esperado: str) -> None:
    assert motivo(ev) == esperado


def test_segredo_vazio_na_configuracao_recusa_tudo() -> None:
    req = webhook.request_from_event(evento(segredo=""))
    assert webhook.motivo_recusa(req, "") == "segredo"


def test_cabecalhos_sao_case_insensitive() -> None:
    ev = evento()
    ev["headers"] = {"content-type": "application/json", "x-telegram-bot-api-secret-token": SEGREDO}
    assert motivo(ev) is None


@pytest.mark.parametrize(
    "ev",
    [
        {"headers": {}, "body": ""},
        {"requestContext": {}, "body": ""},
        {"requestContext": {"http": {"method": "POST"}}, "body": "@@@", "isBase64Encoded": True},
        {"requestContext": {"http": {"method": "POST"}}, "body": 123},
    ],
)
def test_evento_malformado(ev: dict[str, object]) -> None:
    with pytest.raises(webhook.RequestInvalida):
        webhook.request_from_event(ev)


@pytest.mark.parametrize(
    "corpo",
    [
        b"nao json",
        b"[1, 2]",
        b"{}",
        b'{"update_id": "1"}',
        b'{"update_id": -1}',
        b'{"update_id": true}',
        b"\xff\xfe",
    ],
)
def test_update_invalido(corpo: bytes) -> None:
    with pytest.raises(webhook.RequestInvalida):
        webhook.parse_update(corpo)


def test_update_valido() -> None:
    assert (
        webhook.parse_update(json.dumps({"update_id": 42, "message": {}}).encode())["update_id"]
        == 42
    )


def test_resposta_nao_detalha_motivo() -> None:
    assert webhook.resposta(401) == {
        "statusCode": 401,
        "headers": {"content-type": "text/plain"},
        "body": "",
    }

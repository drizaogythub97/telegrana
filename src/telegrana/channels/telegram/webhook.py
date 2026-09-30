"""Entrada do webhook pela Function URL (PLANO 8.1).

Ordem das verificações: método → tipo → tamanho → segredo (comparação em tempo
constante) → JSON estrito. Qualquer falha é recusada sem detalhar o motivo ao cliente.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

MAX_BODY_BYTES = 256 * 1024
SECRET_HEADER = "x-telegram-bot-api-secret-token"  # noqa: S105  # nosec B105 — nome do cabeçalho
# Tipos de update que o bot recebe (setWebhook allowed_updates).
ALLOWED_UPDATES = ["message", "callback_query", "my_chat_member"]


class RequestInvalida(ValueError):
    """Evento da Function URL malformado."""


@dataclass(frozen=True, slots=True)
class HttpRequest:
    method: str
    headers: Mapping[str, str]
    body: bytes


def request_from_event(event: Mapping[str, Any]) -> HttpRequest:
    try:
        method = str(event["requestContext"]["http"]["method"]).upper()
    except (KeyError, TypeError) as exc:
        raise RequestInvalida("evento sem método HTTP") from exc
    headers = {str(k).lower(): str(v) for k, v in (event.get("headers") or {}).items()}
    body_raw = event.get("body") or ""
    if not isinstance(body_raw, str):
        raise RequestInvalida("corpo em formato inesperado")
    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body_raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise RequestInvalida("base64 inválido") from exc
    else:
        body = body_raw.encode("utf-8")
    return HttpRequest(method=method, headers=headers, body=body)


def motivo_recusa(req: HttpRequest, secret: str) -> str | None:
    """Devolve o motivo técnico da recusa (só para log) ou None se a requisição é válida."""
    if req.method != "POST":
        return "metodo"
    tipo = req.headers.get("content-type", "").split(";")[0].strip().lower()
    if tipo != "application/json":
        return "tipo"
    if len(req.body) > MAX_BODY_BYTES:
        return "tamanho"
    recebido = req.headers.get(SECRET_HEADER, "")
    if not secret or not hmac.compare_digest(recebido.encode(), secret.encode()):
        return "segredo"
    return None


def parse_update(body: bytes) -> dict[str, Any]:
    try:
        update = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RequestInvalida("JSON inválido") from exc
    if not isinstance(update, dict):
        raise RequestInvalida("update não é objeto")
    update_id = update.get("update_id")
    if isinstance(update_id, bool) or not isinstance(update_id, int) or update_id < 0:
        raise RequestInvalida("update_id ausente ou inválido")
    return update


def resposta(status: int) -> dict[str, Any]:
    return {"statusCode": status, "headers": {"content-type": "text/plain"}, "body": ""}

"""Lambda `bot`: recebe o webhook do Telegram pela Function URL.

S1.3: esqueleto seguro (validação, idempotência, só chat privado, sai de grupos) e
resposta de "no ar" apenas para o admin. Cadastro e fluxos chegam na S1.4.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import psycopg

from telegrana.channels.telegram import webhook
from telegrana.channels.telegram.api import TelegramAPI, TelegramError
from telegrana.infra import config, db, logs

logs.configure()
log = logging.getLogger("telegrana.bot")

_settings: config.Settings | None = None
_conn: db.Connection | None = None
_api: TelegramAPI | None = None


def _config() -> config.Settings:
    global _settings
    if _settings is None:
        _settings = config.load_settings()
    return _settings


def _telegram(settings: config.Settings) -> TelegramAPI:
    global _api
    if _api is None:
        _api = TelegramAPI(settings.telegram_bot_token)
    return _api


def _com_banco[T](settings: config.Settings, operacao: Callable[[db.Connection], T]) -> T:
    """Reaproveita a conexão entre invocações; reconecta uma vez se o Neon a encerrou."""
    global _conn
    for tentativa in (1, 2):
        if _conn is None or _conn.closed:
            _conn = db.connect(settings.database_url, application_name="telegrana-bot")
        try:
            return operacao(_conn)
        except psycopg.OperationalError:
            _conn = None
            if tentativa == 2:
                raise
    raise AssertionError("inalcançável")


def _primeira_vez(conn: db.Connection, update_id: int) -> bool:
    with conn.transaction():
        row = conn.execute(
            "insert into telegrana.processed_updates (channel, update_id) values ('telegram', %s)"
            " on conflict do nothing returning update_id",
            (update_id,),
        ).fetchone()
    return row is not None


def _processa(update: dict[str, Any], settings: config.Settings, api: TelegramAPI) -> str:
    """Devolve um rótulo técnico do que foi feito (para log; sem conteúdo do usuário)."""
    membro = update.get("my_chat_member")
    if isinstance(membro, dict):
        chat = membro.get("chat") or {}
        novo = (membro.get("new_chat_member") or {}).get("status")
        if chat.get("type") != "private" and novo in {"member", "administrator"}:
            api.leave_chat(int(chat["id"]))
            return "grupo.saiu"
        return "membro.ignorado"

    mensagem = update.get("message")
    if not isinstance(mensagem, dict):
        return "tipo.ignorado"
    chat = mensagem.get("chat") or {}
    if chat.get("type") != "private":
        # O bot só opera em conversa privada (PLANO 8.1).
        api.leave_chat(int(chat["id"]))
        return "grupo.saiu"
    remetente = (mensagem.get("from") or {}).get("id")
    texto = mensagem.get("text") or ""
    if remetente == settings.admin_telegram_id and texto.startswith("/start"):
        api.send_message(
            settings.admin_telegram_id,
            f"✅ <b>Telegrana no ar</b> · ambiente <code>{settings.env}</code>\n"
            "🔧 Cadastro e lançamentos chegam nas próximas etapas.",
        )
        return "admin.ping"
    return "mensagem.ignorada"


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    settings = _config()
    try:
        req = webhook.request_from_event(event)
    except webhook.RequestInvalida:
        log.warning("webhook.recusado", extra={"motivo": "evento"})
        return webhook.resposta(400)
    motivo = webhook.motivo_recusa(req, settings.telegram_webhook_secret)
    if motivo is not None:
        log.warning("webhook.recusado", extra={"motivo": motivo})
        return webhook.resposta({"metodo": 405, "segredo": 401}.get(motivo, 400))
    try:
        update = webhook.parse_update(req.body)
    except webhook.RequestInvalida:
        log.warning("webhook.recusado", extra={"motivo": "json"})
        return webhook.resposta(400)

    update_id = int(update["update_id"])
    if not _com_banco(settings, lambda conn: _primeira_vez(conn, update_id)):
        log.info("update.repetido", extra={"update_id": update_id})
        return webhook.resposta(200)
    try:
        acao = _processa(update, settings, _telegram(settings))
        log.info("update.processado", extra={"update_id": update_id, "acao": acao})
    except (TelegramError, KeyError, TypeError, ValueError) as exc:
        # 200 mesmo assim: evita reenvio em laço; o update já foi marcado como processado.
        log.error("update.falhou", extra={"update_id": update_id, "erro": type(exc).__name__})
    return webhook.resposta(200)

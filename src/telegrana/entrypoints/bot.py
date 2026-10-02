"""Lambda `bot`: recebe o webhook do Telegram pela Function URL.

Valida (segredo, método, tamanho), deduplica, sai de grupos e entrega o resto ao
núcleo pelo adaptador do Telegram (S1.4: entrada, cadastro, recuperação e admin).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import psycopg

from telegrana.ai.groq import Groq
from telegrana.channels.telegram import adaptador, webhook
from telegrana.channels.telegram.api import TelegramAPI, TelegramError
from telegrana.core import lancamentos_repo, roteador
from telegrana.core.contexto import Contexto, Documento
from telegrana.core.seguranca import decodifica_pepper
from telegrana.infra import config, db, logs

logs.configure()
log = logging.getLogger("telegrana.bot")

_settings: config.Settings | None = None
_conn: db.Connection | None = None
_api: TelegramAPI | None = None
_ctx: Contexto | None = None
_username: str | None = None


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


def _conexao(settings: config.Settings) -> db.Connection:
    """Conexão viva: reaproveita entre invocações e reconecta se o Neon a encerrou."""
    global _conn
    if _conn is not None and not _conn.closed:
        try:
            with _conn.transaction():
                _conn.execute("select 1")
            return _conn
        except psycopg.OperationalError:
            _conn = None
    _conn = db.connect(settings.database_url, application_name="telegrana-bot")
    return _conn


def _documento(bruto: str) -> Documento:
    dados = json.loads(bruto)
    return Documento(int(dados["versao"]), str(dados["url"]), bytes.fromhex(dados["sha256"]))


def _contexto(settings: config.Settings, api: TelegramAPI) -> Contexto:
    global _ctx
    if _ctx is None:

        def link_convite(token: str) -> str:
            global _username
            if _username is None:
                _username = str(api.call("getMe")["username"])
            return f"https://t.me/{_username}?start={token}"

        _ctx = Contexto(
            canal=adaptador.CANAL,
            admin_id=str(settings.admin_telegram_id),
            contato_admin=settings.admin_contact,
            termos=_documento(settings.legal_termos),
            privacidade=_documento(settings.legal_privacidade),
            link_convite=link_convite,
            pepper=decodifica_pepper(settings.phone_hmac_pepper),
            extrator=Groq(settings.groq_api_key) if settings.groq_api_key else None,
        )
    return _ctx


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
    if isinstance(mensagem, dict) and (mensagem.get("chat") or {}).get("type") != "private":
        # O bot só opera em conversa privada (PLANO 8.1).
        api.leave_chat(int(mensagem["chat"]["id"]))
        return "grupo.saiu"

    convertido = adaptador.para_entrada(update, adaptador.bot_id(settings.telegram_bot_token))
    if convertido is None:
        return "tipo.ignorado"
    entrada, origem = convertido
    conn = _conexao(settings)
    resultado = roteador.trata(conn, _contexto(settings, api), entrada)
    falhas, refs = adaptador.executa(api, resultado, origem, settings.admin_telegram_id)
    if refs and resultado.conta is not None:
        lancamentos_repo.guarda_refs(conn, resultado.conta, adaptador.CANAL, refs)
    return resultado.rotulo + (f".falhas_envio={falhas}" if falhas else "")


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
    if not _primeira_vez(_conexao(settings), update_id):
        log.info("update.repetido", extra={"update_id": update_id})
        return webhook.resposta(200)
    try:
        acao = _processa(update, settings, _telegram(settings))
        log.info("update.processado", extra={"update_id": update_id, "acao": acao})
    except (TelegramError, psycopg.Error, KeyError, TypeError, ValueError) as exc:
        # 200 mesmo assim: evita reenvio em laço; o update já foi marcado como processado.
        # Só o tipo do erro vai para o log (a mensagem pode conter dado do usuário).
        log.error("update.falhou", extra={"update_id": update_id, "erro": type(exc).__name__})
    return webhook.resposta(200)

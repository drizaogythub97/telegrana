"""Adaptador Telegram ⇄ núcleo: update → `Entrada`; `Resultado` → chamadas da Bot API.

Toda a formatação e os teclados do Telegram moram aqui (regra de ouro 10).
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from typing import Any

from telegrana.channels.telegram.api import TelegramAPI, TelegramError
from telegrana.core import textos
from telegrana.core.mensagens import ADMIN, Entrada, Resultado, Saida

log = logging.getLogger("telegrana.telegram")
CANAL = "telegram"
_NEGRITO = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_CODIGO = re.compile(r"`([^`\n]+)`")


@dataclass(frozen=True, slots=True)
class Origem:
    chat_id: int
    message_id: int | None = None
    callback_id: str | None = None


def bot_id(token: str) -> int:
    """O id do bot é a parte antes dos dois-pontos do token (sem chamar a API)."""
    return int(token.split(":", 1)[0])


def _nome(usuario: dict[str, Any]) -> str:
    return " ".join(p for p in (usuario.get("first_name"), usuario.get("last_name")) if p)


def para_entrada(update: dict[str, Any], id_do_bot: int) -> tuple[Entrada, Origem] | None:
    """Só conversa privada com pessoa (não bot). None = nada a fazer."""
    callback = update.get("callback_query")
    if isinstance(callback, dict):
        usuario = callback.get("from") or {}
        mensagem = callback.get("message") or {}
        if usuario.get("is_bot") or (mensagem.get("chat") or {}).get("type") != "private":
            return None
        entrada = Entrada(
            canal=CANAL,
            external_id=str(usuario["id"]),
            nome=_nome(usuario),
            username=usuario.get("username"),
            acao=str(callback.get("data") or "")[:64] or None,
        )
        return entrada, Origem(int(usuario["id"]), mensagem.get("message_id"), str(callback["id"]))

    mensagem = update.get("message")
    if not isinstance(mensagem, dict):
        return None
    usuario = mensagem.get("from") or {}
    if usuario.get("is_bot") or (mensagem.get("chat") or {}).get("type") != "private":
        return None
    texto = str(mensagem.get("text") or "")
    comando, argumento = None, ""
    if texto.startswith("/"):
        primeiro, _, argumento = texto.partition(" ")
        comando = primeiro[1:].split("@", 1)[0].lower()[:32] or None
    telefone, alheio = None, False
    contato = mensagem.get("contact")
    if isinstance(contato, dict):
        # Só o contato do próprio remetente vale (PLANO 3.3).
        if contato.get("user_id") == usuario.get("id"):
            telefone = str(contato.get("phone_number") or "")
        else:
            alheio = True
    pergunta = None
    respondida = mensagem.get("reply_to_message")
    if isinstance(respondida, dict) and (respondida.get("from") or {}).get("id") == id_do_bot:
        pergunta = textos.pergunta_respondida(str(respondida.get("text") or ""))
    entrada = Entrada(
        canal=CANAL,
        external_id=str(usuario["id"]),
        nome=_nome(usuario),
        username=usuario.get("username"),
        texto=texto,
        comando=comando,
        argumento=argumento,
        telefone=telefone,
        contato_alheio=alheio,
        pergunta=pergunta,
    )
    return entrada, Origem(int(usuario["id"]), mensagem.get("message_id"))


def html_de(texto: str) -> str:
    """Marcação do núcleo → HTML do Telegram, com todo o resto escapado."""
    seguro = html.escape(texto, quote=False)
    seguro = _NEGRITO.sub(r"<b>\1</b>", seguro)
    return _CODIGO.sub(r"<code>\1</code>", seguro)


def teclado(saida: Saida) -> dict[str, Any] | None:
    if saida.botoes:
        return {
            "inline_keyboard": [
                [
                    {"text": b.rotulo, "url": b.url}
                    if b.url
                    else {"text": b.rotulo, "callback_data": b.acao}
                    for b in linha
                ]
                for linha in saida.botoes
            ]
        }
    if saida.pedir_telefone:
        return {
            "keyboard": [[{"text": saida.pedir_telefone, "request_contact": True}]],
            "one_time_keyboard": True,
            "resize_keyboard": True,
        }
    if saida.pergunta:
        return {"force_reply": True, "input_field_placeholder": "Responda aqui"}
    if saida.tirar_teclado:
        return {"remove_keyboard": True}
    return None


def destino(saida: Saida, origem: Origem, admin_id: int) -> int:
    if saida.destino is None:
        return origem.chat_id
    if saida.destino == ADMIN:
        return admin_id
    return int(saida.destino)


def executa(api: TelegramAPI, resultado: Resultado, origem: Origem, admin_id: int) -> int:
    """Envia tudo; uma falha (ex.: pessoa bloqueou o bot) não impede as outras. Devolve falhas."""
    falhas = 0
    if origem.callback_id:
        try:
            api.call(
                "answerCallbackQuery", callback_query_id=origem.callback_id, text=resultado.aviso
            )
            if origem.message_id is not None:
                # Tira os botões já usados (evita toque duplo).
                api.call(
                    "editMessageReplyMarkup",
                    chat_id=origem.chat_id,
                    message_id=origem.message_id,
                    reply_markup={"inline_keyboard": []},
                )
        except TelegramError as exc:
            falhas += 1
            log.warning("telegram.callback_falhou", extra={"erro": str(exc)[:120]})
    elif resultado.apagar_entrada and origem.message_id is not None:
        try:
            api.call("deleteMessage", chat_id=origem.chat_id, message_id=origem.message_id)
        except TelegramError as exc:
            falhas += 1
            log.warning("telegram.apagar_falhou", extra={"erro": str(exc)[:120]})
    for saida in resultado.saidas:
        try:
            api.call(
                "sendMessage",
                chat_id=destino(saida, origem, admin_id),
                text=html_de(saida.texto),
                parse_mode="HTML",
                reply_markup=teclado(saida),
                protect_content=saida.protegida or None,
                link_preview_options={"is_disabled": True},
            )
        except TelegramError as exc:
            falhas += 1
            log.warning("telegram.envio_falhou", extra={"erro": str(exc)[:120]})
    return falhas

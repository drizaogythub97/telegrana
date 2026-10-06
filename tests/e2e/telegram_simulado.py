"""Telegram simulado para o E2E (D034).

Faz o papel da Bot API (por um `httpx.MockTransport` no cliente da Lambda) e dos
aplicativos das pessoas (que montam updates no formato exato do Telegram). Recusa o
que o Telegram de verdade recusaria, para o E2E pegar erros que só apareceriam em
produção: HTML inválido, texto longo demais, botões malformados, `callback_data` acima
de 64 bytes, chat inexistente, contato compartilhado sem o teclado de contato.
"""

from __future__ import annotations

import email
import email.policy
import html
import itertools
import json
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

import httpx

BOT_ID = 777000111
BOT_USERNAME = "telegrana_e2e_bot"
TOKEN = f"{BOT_ID}:" + "e2e" * 12
_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre", "a"}


class RecusaDoTelegram(AssertionError):
    """O Telegram de verdade devolveria 400 para esta chamada."""


class _ValidaHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pilha: list[str] = []
        self.texto: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _TAGS:
            raise RecusaDoTelegram(f"tag HTML não suportada pelo Telegram: <{tag}>")
        self.pilha.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.pilha or self.pilha.pop() != tag:
            raise RecusaDoTelegram(f"HTML desbalanceado em </{tag}>")

    def handle_data(self, data: str) -> None:
        self.texto.append(data)


def _multipart(tipo: str, conteudo: bytes) -> dict[str, Any]:
    """multipart/form-data → {campo: texto} e {arquivo: (nome, tipo, bytes)}."""
    mensagem = email.message_from_bytes(
        f"Content-Type: {tipo}\r\n\r\n".encode() + conteudo, policy=email.policy.HTTP
    )
    campos: dict[str, Any] = {}
    for parte in mensagem.iter_parts():  # type: ignore[attr-defined]
        nome = parte.get_param("name", header="content-disposition")
        arquivo = parte.get_filename()
        dados = parte.get_payload(decode=True) or b""
        if arquivo:
            campos[nome] = (arquivo, parte.get_content_type(), dados)
        else:
            campos[nome] = dados.decode()
    return campos


def texto_puro(texto_html: str) -> str:
    """O que o aplicativo mostra (e o que volta em reply_to_message.text)."""
    validador = _ValidaHTML()
    validador.feed(texto_html)
    validador.close()
    if validador.pilha:
        raise RecusaDoTelegram(f"HTML com tags abertas: {validador.pilha}")
    return html.unescape("".join(validador.texto))


def _valida_teclado(teclado: dict[str, Any] | None) -> None:
    if teclado is None:
        return
    if "inline_keyboard" in teclado:
        for linha in teclado["inline_keyboard"]:
            for botao in linha:
                if not botao.get("text"):
                    raise RecusaDoTelegram("botão sem texto")
                tipos = [k for k in ("callback_data", "url") if k in botao]
                if len(tipos) != 1:
                    raise RecusaDoTelegram(f"botão precisa de exatamente um tipo: {botao}")
                if "callback_data" in botao and not 1 <= len(botao["callback_data"].encode()) <= 64:
                    raise RecusaDoTelegram(f"callback_data com tamanho inválido: {botao}")
                if "url" in botao and not botao["url"].startswith(("https://", "http://", "tg://")):
                    raise RecusaDoTelegram(f"url inválida no botão: {botao}")
    elif not ({"keyboard", "force_reply", "remove_keyboard"} & set(teclado)):
        raise RecusaDoTelegram(f"reply_markup desconhecido: {teclado}")


@dataclass
class MensagemDoBot:
    id: int
    chat: int
    html: str
    texto: str
    teclado: dict[str, Any] | None
    protegida: bool
    documento: tuple[str, str, bytes] | None = None  # (nome, tipo MIME, conteúdo)

    def botoes(self) -> list[dict[str, str]]:
        if not self.teclado or "inline_keyboard" not in self.teclado:
            return []
        return [b for linha in self.teclado["inline_keyboard"] for b in linha]


@dataclass
class TelegramSimulado:
    chats: set[int] = field(default_factory=set)  # quem já abriu conversa com o bot
    mensagens: dict[int, MensagemDoBot] = field(default_factory=dict)
    teclado_de_contato: dict[int, bool] = field(default_factory=dict)
    callbacks_abertos: set[str] = field(default_factory=set)
    chamadas: list[str] = field(default_factory=list)
    arquivos: dict[str, bytes] = field(default_factory=dict)  # file_id → conteúdo (áudios)
    acoes_de_chat: list[tuple[int, str]] = field(default_factory=list)
    _ids: itertools.count[int] = field(default_factory=lambda: itertools.count(50_000))

    def proximo_id(self) -> int:
        return next(self._ids)

    def cliente(self) -> httpx.Client:
        return httpx.Client(
            base_url="https://api.telegram.org", transport=httpx.MockTransport(self._responde)
        )

    def _responde(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/file/bot"):
            # Download: /file/bot<token>/voice/<file_id>.oga
            file_id = request.url.path.rsplit("/", 1)[-1].removesuffix(".oga")
            if request.method != "GET" or file_id not in self.arquivos:
                return httpx.Response(404)
            self.chamadas.append("download")
            return httpx.Response(200, content=self.arquivos[file_id])
        metodo = request.url.path.rsplit("/", 1)[-1]
        tipo = request.headers.get("content-type", "")
        corpo = (
            _multipart(tipo, request.content)
            if tipo.startswith("multipart/")
            else json.loads(request.content or b"{}")
        )
        self.chamadas.append(metodo)
        try:
            resultado = getattr(self, f"_{metodo}")(corpo)
        except RecusaDoTelegram as exc:
            if "chat not found" in str(exc) or "not modified" in str(exc):
                return httpx.Response(400, json={"ok": False, "description": str(exc)})
            raise
        return httpx.Response(200, json={"ok": True, "result": resultado})

    # --- métodos da Bot API usados pelo bot ---------------------------------
    def _sendMessage(self, c: dict[str, Any]) -> dict[str, Any]:
        chat = int(c["chat_id"])
        if chat not in self.chats:
            raise RecusaDoTelegram("Bad Request: chat not found")
        if c.get("parse_mode") != "HTML":
            raise RecusaDoTelegram("o bot deveria mandar HTML")
        texto = texto_puro(c["text"])
        if not 1 <= len(texto) <= 4096:
            raise RecusaDoTelegram(f"texto com {len(texto)} caracteres")
        teclado = c.get("reply_markup")
        _valida_teclado(teclado)
        if teclado and "keyboard" in teclado:
            self.teclado_de_contato[chat] = any(
                b.get("request_contact") for linha in teclado["keyboard"] for b in linha
            )
        elif teclado and "remove_keyboard" in teclado:
            self.teclado_de_contato[chat] = False
        msg = MensagemDoBot(
            self.proximo_id(), chat, c["text"], texto, teclado, bool(c.get("protect_content"))
        )
        self.mensagens[msg.id] = msg
        return {"message_id": msg.id, "chat": {"id": chat, "type": "private"}, "text": texto}

    def _sendDocument(self, c: dict[str, Any]) -> dict[str, Any]:
        chat = int(c["chat_id"])
        if chat not in self.chats:
            raise RecusaDoTelegram("Bad Request: chat not found")
        nome, tipo, conteudo = c["document"]
        if not conteudo or len(conteudo) > 50 * 1024 * 1024:
            raise RecusaDoTelegram("arquivo vazio ou acima de 50 MB")
        legenda = c.get("caption", "")
        if legenda and c.get("parse_mode") != "HTML":
            raise RecusaDoTelegram("o bot deveria mandar HTML")
        texto = texto_puro(legenda) if legenda else ""
        if len(texto) > 1024:
            raise RecusaDoTelegram(f"legenda com {len(texto)} caracteres")
        teclado = json.loads(c["reply_markup"]) if c.get("reply_markup") else None
        _valida_teclado(teclado)
        msg = MensagemDoBot(
            self.proximo_id(), chat, legenda, texto, teclado, False, (nome, tipo, conteudo)
        )
        self.mensagens[msg.id] = msg
        return {"message_id": msg.id, "chat": {"id": chat, "type": "private"}}

    def _answerCallbackQuery(self, c: dict[str, Any]) -> bool:
        if c["callback_query_id"] not in self.callbacks_abertos:
            raise RecusaDoTelegram("query is too old or already answered")
        self.callbacks_abertos.discard(c["callback_query_id"])
        return True

    def _editMessageReplyMarkup(self, c: dict[str, Any]) -> bool:
        msg = self.mensagens.get(int(c["message_id"]))
        if msg is None or msg.chat != int(c["chat_id"]):
            raise RecusaDoTelegram("message to edit not found")
        _valida_teclado(c.get("reply_markup"))
        msg.teclado = c.get("reply_markup") or None
        return True

    def _editMessageText(self, c: dict[str, Any]) -> dict[str, Any]:
        msg = self.mensagens.get(int(c["message_id"]))
        if msg is None or msg.chat != int(c["chat_id"]):
            raise RecusaDoTelegram("Bad Request: message to edit not found")
        if c.get("parse_mode") != "HTML":
            raise RecusaDoTelegram("o bot deveria mandar HTML")
        texto = texto_puro(c["text"])
        teclado = c.get("reply_markup")
        _valida_teclado(teclado)
        if texto == msg.texto and teclado == msg.teclado:
            raise RecusaDoTelegram("Bad Request: message is not modified")
        self.mensagens[msg.id] = MensagemDoBot(
            msg.id, msg.chat, c["text"], texto, teclado, msg.protegida
        )
        return {"message_id": msg.id, "chat": {"id": msg.chat, "type": "private"}, "text": texto}

    def _deleteMessage(self, c: dict[str, Any]) -> bool:
        return True

    def _getFile(self, c: dict[str, Any]) -> dict[str, Any]:
        file_id = str(c["file_id"])
        if file_id not in self.arquivos:
            raise RecusaDoTelegram("Bad Request: invalid file_id")
        return {
            "file_id": file_id,
            "file_size": len(self.arquivos[file_id]),
            "file_path": f"voice/{file_id}.oga",
        }

    def _sendChatAction(self, c: dict[str, Any]) -> bool:
        chat = int(c["chat_id"])
        if chat not in self.chats:
            raise RecusaDoTelegram("Bad Request: chat not found")
        if c.get("action") not in {"typing", "record_voice", "upload_document"}:
            raise RecusaDoTelegram("Bad Request: wrong chat action")
        self.acoes_de_chat.append((chat, str(c["action"])))
        return True

    def _getMe(self, c: dict[str, Any]) -> dict[str, Any]:
        return {"id": BOT_ID, "is_bot": True, "username": BOT_USERNAME}

    def _leaveChat(self, c: dict[str, Any]) -> bool:
        return True

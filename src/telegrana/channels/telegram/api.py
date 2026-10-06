"""Cliente mínimo da Bot API do Telegram (httpx, sem biblioteca de bot — PLANO 2).

Erros nunca carregam a URL (que contém o token): as exceções do httpx são convertidas
em `TelegramError` com `from None`.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

BASE_URL = "https://api.telegram.org"


class TelegramError(RuntimeError):
    """Falha ao chamar a Bot API (sem token na mensagem)."""


class TelegramAPI:
    def __init__(
        self, token: str, *, test_server: bool = False, client: httpx.Client | None = None
    ) -> None:
        # Servidor de testes do Telegram: /bot<token>/test/<método> (PLANO 10.1).
        self._prefix = f"/bot{token}/test/" if test_server else f"/bot{token}/"
        self._arquivos = f"/file/bot{token}/test/" if test_server else f"/file/bot{token}/"
        self._client = client or httpx.Client(
            base_url=BASE_URL, timeout=httpx.Timeout(10.0, connect=5.0)
        )

    def call(self, method: str, **params: Any) -> Any:
        payload = {k: v for k, v in params.items() if v is not None}
        try:
            resposta = self._client.post(self._prefix + method, json=payload)
            dados = resposta.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TelegramError(f"{method}: falha de comunicação ({type(exc).__name__})") from None
        if not isinstance(dados, dict) or not dados.get("ok"):
            descricao = str(dados.get("description", ""))[:200] if isinstance(dados, dict) else ""
            raise TelegramError(f"{method}: HTTP {resposta.status_code} {descricao}".strip())
        return dados.get("result")

    def upload(self, method: str, campos: dict[str, Any], arquivos: dict[str, bytes]) -> Any:
        """multipart/form-data (ex.: setMyProfilePhoto com "attach://<nome>")."""
        dados = {
            k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in campos.items()
        }
        try:
            resposta = self._client.post(
                self._prefix + method,
                data=dados,
                files={nome: (nome, conteudo) for nome, conteudo in arquivos.items()},
            )
            corpo = resposta.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TelegramError(f"{method}: falha de comunicação ({type(exc).__name__})") from None
        if not isinstance(corpo, dict) or not corpo.get("ok"):
            descricao = str(corpo.get("description", ""))[:200] if isinstance(corpo, dict) else ""
            raise TelegramError(f"{method}: HTTP {resposta.status_code} {descricao}".strip())
        return corpo.get("result")

    def envia_documento(
        self,
        chat_id: int,
        nome: str,
        conteudo: bytes,
        tipo: str,
        *,
        legenda: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> Any:
        """sendDocument (multipart), com legenda em HTML."""
        campos: dict[str, str] = {"chat_id": str(chat_id), "parse_mode": "HTML"}
        if legenda:
            campos["caption"] = legenda
        if reply_markup:
            campos["reply_markup"] = json.dumps(reply_markup)
        try:
            resposta = self._client.post(
                self._prefix + "sendDocument",
                data=campos,
                files={"document": (nome, conteudo, tipo)},
                timeout=httpx.Timeout(30.0, connect=5.0),
            )
            corpo = resposta.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TelegramError(
                f"sendDocument: falha de comunicação ({type(exc).__name__})"
            ) from None
        if not isinstance(corpo, dict) or not corpo.get("ok"):
            descricao = str(corpo.get("description", ""))[:200] if isinstance(corpo, dict) else ""
            raise TelegramError(f"sendDocument: HTTP {resposta.status_code} {descricao}".strip())
        return corpo.get("result")

    def baixa_arquivo(self, file_id: str, limite: int) -> bytes:
        """getFile + download em memória, parando se passar de `limite` bytes.

        O link do arquivo contém o token: nunca sai daqui (nem em erro, nem em log).
        """
        info = self.call("getFile", file_id=file_id)
        caminho = str(info.get("file_path") or "") if isinstance(info, dict) else ""
        if not caminho or ".." in caminho or caminho.startswith("/"):
            raise TelegramError("getFile: sem caminho válido")
        tamanho = info.get("file_size")
        if isinstance(tamanho, int) and tamanho > limite:
            raise TelegramError("getFile: arquivo acima do limite")
        partes: list[bytes] = []
        total = 0
        try:
            with self._client.stream("GET", self._arquivos + caminho) as resposta:
                if resposta.status_code != 200:
                    raise TelegramError(f"download: HTTP {resposta.status_code}")
                for pedaco in resposta.iter_bytes():
                    total += len(pedaco)
                    if total > limite:
                        raise TelegramError("download: arquivo acima do limite")
                    partes.append(pedaco)
        except httpx.HTTPError as exc:
            raise TelegramError(f"download: falha de comunicação ({type(exc).__name__})") from None
        return b"".join(partes)

    def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        parse_mode: str | None = "HTML",
        reply_markup: dict[str, Any] | None = None,
        protect_content: bool | None = None,
    ) -> Any:
        return self.call(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            protect_content=protect_content,
        )

    def leave_chat(self, chat_id: int) -> Any:
        return self.call("leaveChat", chat_id=chat_id)

    def set_webhook(
        self,
        url: str,
        *,
        secret_token: str,
        allowed_updates: list[str],
        max_connections: int,
        drop_pending_updates: bool,
    ) -> Any:
        return self.call(
            "setWebhook",
            url=url,
            secret_token=secret_token,
            allowed_updates=allowed_updates,
            max_connections=max_connections,
            drop_pending_updates=drop_pending_updates,
        )

    def get_webhook_info(self) -> Any:
        return self.call("getWebhookInfo")

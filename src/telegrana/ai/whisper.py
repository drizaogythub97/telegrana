"""Transcrição de áudio pelo Whisper no Groq (PLANO 5.1; D041).

Cadeia `whisper-large-v3` (mais preciso) → `whisper-large-v3-turbo` (limites próprios),
idioma `pt`, temperatura 0 e um prompt com o vocabulário de finanças. O áudio vai em
memória (multipart) e não é guardado em lugar nenhum; a retenção zero do Groq vale para
ele. Nunca usar o parâmetro `url` da API: o link do arquivo no Telegram contém o token.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from telegrana.ai.cadeia import Cadeia, ErroIA, erro_http
from telegrana.core.audio import Transcricao, segundos_cobrados

URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODELOS = ("whisper-large-v3", "whisper-large-v3-turbo")
FORMATOS = frozenset({"flac", "mp3", "mp4", "mpeg", "mpga", "m4a", "ogg", "wav", "webm"})
LIMITE_TEXTO = 2000
# Estilo e vocabulário (o Groq aceita até 224 tokens de prompt).
VOCABULARIO = (
    "Gastos e ganhos do dia a dia, em reais. Paguei R$ 45,90 no Pix. Gastei 50 conto no "
    "mercado, no débito. Comprei no crédito do Nubank, parcelado em 3x. Conta de luz no "
    "boleto. Uber, iFood, padaria, farmácia, aluguel, condomínio. Recebi o salário. "
    "Cartão do Inter, Itaú, C6, Bradesco, Santander, Caixa, PicPay."
)


class Whisper:
    def __init__(
        self,
        api_key: str,
        *,
        modelos: tuple[str, ...] = MODELOS,
        client: httpx.Client | None = None,
        relogio: Any = time.monotonic,
        dorme: Any = time.sleep,
    ) -> None:
        self._headers = {"Authorization": f"Bearer {api_key}"}
        # 15 s: um áudio de 2 min leva 1 a 2 s no Groq; sobra folga na Lambda de 30 s.
        self._client = client or httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0))
        self._cadeia = Cadeia(modelos, relogio, dorme)

    def transcreve(self, dados: bytes, formato: str, duracao: int) -> Transcricao:
        formato = formato if formato in FORMATOS else "ogg"
        texto, modelo = self._cadeia.executa(lambda m: self._chama(m, dados, formato))
        return Transcricao(texto, modelo, segundos_cobrados(duracao))

    def _chama(self, modelo: str, dados: bytes, formato: str) -> str:
        try:
            resposta = self._client.post(
                URL,
                headers=self._headers,
                data={
                    "model": modelo,
                    "language": "pt",
                    "prompt": VOCABULARIO,
                    "temperature": "0",
                    "response_format": "json",
                },
                files={"file": (f"audio.{formato}", dados)},
            )
        except httpx.HTTPError as exc:
            raise ErroIA(f"falha de comunicação ({type(exc).__name__})") from None
        if resposta.status_code >= 400:
            raise erro_http(resposta) from None
        try:
            texto = resposta.json()["text"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ErroIA(f"resposta inválida ({type(exc).__name__})") from None
        if not isinstance(texto, str):
            raise ErroIA("resposta inválida (texto)")
        return " ".join(texto.split())[:LIMITE_TEXTO]

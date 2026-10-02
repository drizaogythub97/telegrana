"""Áudio: limites, contrato do transcritor e resumo da transcrição (PLANO 5.1, 8.3, 8.5; D041).

O canal entrega um `mensagens.Audio`; o núcleo confere os limites ANTES de baixar,
transcreve e segue pelo mesmo caminho do texto. O áudio nunca é guardado: só a
transcrição, junto do lançamento.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

DURACAO_MAXIMA = 120  # segundos (PLANO 8.3)
TAMANHO_MAXIMO = 20 * 1024 * 1024  # bytes (PLANO 8.3; também o limite do getFile)
COBRANCA_MINIMA = 10  # o Groq cobra no mínimo 10 s por áudio
LIMITE_DIARIO_SEGUNDOS = 28_800  # por modelo do Whisper, no plano gratuito (D041)
LIMITE_TEXTO = 1000  # a transcrição segue como texto: mesmo limite (PLANO 8.3)


@dataclass(frozen=True, slots=True)
class Transcricao:
    texto: str
    modelo: str | None = None
    segundos: int = 0  # contados no limite do provedor


class Transcritor(Protocol):
    """Provedor de transcrição (Whisper no Groq hoje). Erros sobem como `ErroExtracao`."""

    def transcreve(self, dados: bytes, formato: str, duracao: int) -> Transcricao: ...


def segundos_cobrados(duracao: int) -> int:
    return max(COBRANCA_MINIMA, math.ceil(max(0, duracao)))


def resumo(texto: str, limite: int = 90) -> str:
    """Trecho curto da transcrição para o recibo (corta na palavra)."""
    limpo = " ".join(texto.split())
    if len(limpo) <= limite:
        return limpo
    corte = limpo[:limite].rsplit(" ", 1)[0] or limpo[:limite]
    return corte.rstrip(" ,.;:") + "…"

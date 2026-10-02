"""Cadeia de modelos do Groq (D040): no plano gratuito o limite diário é POR MODELO.

O pedido vai ao primeiro modelo; limite (429), bloqueio na organização (403/404), queda
(5xx) ou resposta inválida passam para o seguinte. O modelo esgotado fica de fora até o
`retry-after` (a instância da Lambda lembra entre mensagens). Só com todos de fora sobe
um erro de limite, que o bot traduz em "muita demanda, manda de novo".
Usada pela extração (`ai/groq.py`) e pela transcrição (`ai/whisper.py`).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, TypeVar

import httpx

from telegrana.core.entendimento import ErroExtracao

FORA_SEM_PRAZO = 60.0  # 429 sem retry-after
# Todos no limite POR MINUTO, liberando em poucos segundos: espera uma vez e tenta de novo
# (cabe na Lambda de 30 s) em vez de responder "muita demanda" (02/10/2026).
ESPERA_CURTA = 6.0
FORA_INDISPONIVEL = 600.0  # 403/404: modelo bloqueado na organização ou retirado

T = TypeVar("T")


class ErroIA(ErroExtracao):
    """Falha do Groq (sem chave nem conteúdo do usuário na mensagem)."""


def erro_http(resposta: httpx.Response) -> ErroIA:
    if resposta.status_code == 429:
        espera = resposta.headers.get("retry-after")
        return ErroIA("limite do Groq", limite=True, espera=float(espera) if espera else None)
    return ErroIA(f"HTTP {resposta.status_code}")


class Cadeia:
    def __init__(
        self,
        modelos: tuple[str, ...],
        relogio: Any = time.monotonic,
        dorme: Callable[[float], None] = time.sleep,
    ) -> None:
        if not modelos:
            raise ValueError("cadeia sem modelos")
        self.modelos = modelos
        self._relogio = relogio
        self._dorme = dorme
        self._fora_ate: dict[str, float] = {}

    def executa(self, chamada: Callable[[str], T]) -> tuple[T, str]:
        """Devolve (resultado, modelo que respondeu)."""
        try:
            return self._percorre(chamada)
        except ErroIA as exc:
            if not exc.limite or exc.espera is None or exc.espera > ESPERA_CURTA:
                raise
            self._dorme(exc.espera)
            return self._percorre(chamada)

    def _percorre(self, chamada: Callable[[str], T]) -> tuple[T, str]:
        agora = self._relogio()
        ultimo_erro: ErroIA | None = None
        for modelo in self.modelos:
            if self._fora_ate.get(modelo, 0.0) > agora:
                continue
            try:
                return chamada(modelo), modelo
            except ErroIA as exc:
                ultimo_erro = exc
                if exc.limite:
                    self._fora_ate[modelo] = agora + (exc.espera or FORA_SEM_PRAZO)
                elif "HTTP 403" in str(exc) or "HTTP 404" in str(exc):
                    self._fora_ate[modelo] = agora + FORA_INDISPONIVEL
        disponiveis = [m for m in self.modelos if self._fora_ate.get(m, 0.0) <= agora]
        if ultimo_erro is not None and not ultimo_erro.limite and disponiveis:
            raise ultimo_erro  # falha comum (ex.: HTTP 500) num modelo que segue na cadeia
        # Todos de fora (limite ou bloqueio): para a pessoa, é "muita demanda agora".
        restante = [t - agora for m, t in self._fora_ate.items() if m in self.modelos]
        espera = max(1.0, min(restante)) if restante else None
        raise ErroIA("limite do Groq em todos os modelos", limite=True, espera=espera)

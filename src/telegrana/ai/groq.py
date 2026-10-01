"""Provedor Groq da extração (PLANO 5.1; D019, D036).

`openai/gpt-oss-20b` com `response_format` JSON Schema **estrito** e raciocínio baixo
(economiza a cota diária). A resposta passa pelo Pydantic antes de qualquer uso.
Erros nunca carregam a chave nem o texto do usuário.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx
from pydantic import ValidationError

from telegrana.ai.prompt import CategoriaPrompt, mensagens
from telegrana.core.extracao import ExtracaoIA, esquema_json

URL = "https://api.groq.com/openai/v1/chat/completions"
MODELO = "openai/gpt-oss-20b"


class ErroIA(RuntimeError):
    """Falha da IA. `limite`: cota ou ritmo estourado (o bot avisa e tenta depois)."""

    def __init__(self, motivo: str, *, limite: bool = False, espera: float | None = None) -> None:
        super().__init__(motivo)
        self.limite = limite
        self.espera = espera


@dataclass(frozen=True, slots=True)
class Uso:
    tokens_entrada: int
    tokens_saida: int
    tokens_em_cache: int  # não contam para os limites do Groq (prompt caching)


class Groq:
    def __init__(
        self,
        api_key: str,
        *,
        modelo: str = MODELO,
        esforco: str = "low",
        client: httpx.Client | None = None,
    ) -> None:
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._modelo = modelo
        self._esforco = esforco
        self._client = client or httpx.Client(timeout=httpx.Timeout(25.0, connect=5.0))
        self.ultimo_uso: Uso | None = None

    def corpo(self, texto: str, categorias: list[CategoriaPrompt], hoje: date) -> dict[str, Any]:
        return {
            "model": self._modelo,
            "messages": mensagens(texto, categorias, hoje),
            "temperature": 0,
            "reasoning_effort": self._esforco,
            "include_reasoning": False,
            "max_completion_tokens": 2000,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "extracao", "strict": True, "schema": esquema_json()},
            },
        }

    def extrai(self, texto: str, categorias: list[CategoriaPrompt], hoje: date) -> ExtracaoIA:
        try:
            resposta = self._client.post(
                URL, headers=self._headers, json=self.corpo(texto, categorias, hoje)
            )
        except httpx.HTTPError as exc:
            raise ErroIA(f"falha de comunicação ({type(exc).__name__})") from None
        if resposta.status_code == 429:
            espera = resposta.headers.get("retry-after")
            raise ErroIA(
                "limite do Groq", limite=True, espera=float(espera) if espera else None
            ) from None
        if resposta.status_code >= 400:
            raise ErroIA(f"HTTP {resposta.status_code}") from None
        try:
            dados = resposta.json()
            uso = dados.get("usage") or {}
            detalhes = uso.get("prompt_tokens_details") or {}
            self.ultimo_uso = Uso(
                int(uso.get("prompt_tokens", 0)),
                int(uso.get("completion_tokens", 0)),
                int(detalhes.get("cached_tokens", 0)),
            )
            conteudo = dados["choices"][0]["message"]["content"]
            return ExtracaoIA.model_validate(json.loads(conteudo))
        except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
            raise ErroIA(f"resposta inválida ({type(exc).__name__})") from None

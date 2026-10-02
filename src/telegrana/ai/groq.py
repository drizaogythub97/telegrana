"""Provedor Groq da extração (PLANO 5.1; D019, D036, D040).

JSON Schema **estrito** e raciocínio baixo (economiza a cota diária). A resposta passa
pelo Pydantic antes de qualquer uso. Erros nunca carregam a chave nem o texto do usuário.

Cadeia de modelos (D040): no plano gratuito do Groq o limite diário é **por modelo**. Se
o primeiro bate o limite (ou está fora do ar), o pedido vai para o seguinte, e o modelo
esgotado fica de fora até o `retry-after` (a instância da Lambda lembra entre mensagens).
Todos aceitam saída estrita; cada um passa pela mesma avaliação antes de entrar.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx
from pydantic import ValidationError

from telegrana.ai.cadeia import Cadeia, ErroIA, erro_http
from telegrana.ai.prompt import CategoriaPrompt, mensagens
from telegrana.core.extracao import ExtracaoIA, esquema_json

__all__ = ["MODELOS", "PARAMETROS", "ErroIA", "Groq", "Uso"]

URL = "https://api.groq.com/openai/v1/chat/completions"
# Parâmetros de raciocínio de cada modelo (verificados em 02/10/2026 na documentação).
PARAMETROS: dict[str, dict[str, Any]] = {
    "openai/gpt-oss-20b": {"reasoning_effort": "low", "include_reasoning": False},
    "openai/gpt-oss-120b": {"reasoning_effort": "low", "include_reasoning": False},
    # Sem raciocínio, o qwen às vezes repete até estourar o limite de saída (02/10/2026).
    "qwen/qwen3.8-27b": {"reasoning_effort": "low", "reasoning_format": "hidden"},
}
# Ordem da cadeia (D040): os avaliados com o código atual primeiro (120b e qwen: 100% em
# 02/10/2026); o 20b fica por último até completar uma rodada com o código atual.
MODELOS = ("openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b")
MODELO = MODELOS[0]


@dataclass(frozen=True, slots=True)
class Uso:
    tokens_entrada: int
    tokens_saida: int
    tokens_em_cache: int  # não contam para os limites do Groq (prompt caching)
    modelo: str = MODELO


class Groq:
    def __init__(
        self,
        api_key: str,
        *,
        modelos: tuple[str, ...] = MODELOS,
        client: httpx.Client | None = None,
        relogio: Any = time.monotonic,
    ) -> None:
        desconhecidos = [m for m in modelos if m not in PARAMETROS]
        if not modelos or desconhecidos:
            raise ValueError(f"modelos sem parâmetros conhecidos: {desconhecidos}")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._modelos = modelos
        # 15 s: folga dentro da Lambda de 30 s mesmo se o primeiro modelo falhar.
        self._client = client or httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0))
        self._cadeia = Cadeia(modelos, relogio)
        self.ultimo_uso: Uso | None = None

    def corpo(
        self, texto: str, categorias: list[CategoriaPrompt], hoje: date, modelo: str = ""
    ) -> dict[str, Any]:
        modelo = modelo or self._modelos[0]
        return {
            "model": modelo,
            "messages": mensagens(texto, categorias, hoje),
            "temperature": 0,
            **PARAMETROS[modelo],
            "max_completion_tokens": 2000,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "extracao", "strict": True, "schema": esquema_json()},
            },
        }

    def extrai(self, texto: str, categorias: list[CategoriaPrompt], hoje: date) -> ExtracaoIA:
        self.ultimo_uso = None
        extracao, _modelo = self._cadeia.executa(
            lambda modelo: self._chama(modelo, texto, categorias, hoje)
        )
        return extracao

    def _chama(
        self, modelo: str, texto: str, categorias: list[CategoriaPrompt], hoje: date
    ) -> ExtracaoIA:
        try:
            resposta = self._client.post(
                URL, headers=self._headers, json=self.corpo(texto, categorias, hoje, modelo)
            )
        except httpx.HTTPError as exc:
            raise ErroIA(f"falha de comunicação ({type(exc).__name__})") from None
        if resposta.status_code >= 400:
            raise erro_http(resposta) from None
        try:
            dados = resposta.json()
            uso = dados.get("usage") or {}
            detalhes = uso.get("prompt_tokens_details") or {}
            self.ultimo_uso = Uso(
                int(uso.get("prompt_tokens", 0)),
                int(uso.get("completion_tokens", 0)),
                int(detalhes.get("cached_tokens", 0)),
                modelo,
            )
            conteudo = dados["choices"][0]["message"]["content"]
            return ExtracaoIA.model_validate(json.loads(conteudo))
        except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
            raise ErroIA(f"resposta inválida ({type(exc).__name__})") from None

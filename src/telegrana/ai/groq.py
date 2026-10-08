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
from typing import Any, TypeVar

import httpx
from pydantic import ValidationError

from telegrana.ai.cadeia import Cadeia, ErroIA, erro_http
from telegrana.ai.prompt import (
    CategoriaPrompt,
    mensagens,
    mensagens_consulta,
    mensagens_conversa,
    mensagens_correcao,
    mensagens_escolha,
)
from telegrana.core.extracao import (
    ConsultaIA,
    ConversaIA,
    CorrecaoIA,
    EscolhaIA,
    ExtracaoIA,
    esquema_consulta,
    esquema_conversa,
    esquema_correcao,
    esquema_escolha,
    esquema_json,
)

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
Saida = TypeVar("Saida", ExtracaoIA, CorrecaoIA, ConsultaIA, EscolhaIA, ConversaIA)


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
        dorme: Any = time.sleep,
    ) -> None:
        desconhecidos = [m for m in modelos if m not in PARAMETROS]
        if not modelos or desconhecidos:
            raise ValueError(f"modelos sem parâmetros conhecidos: {desconhecidos}")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._modelos = modelos
        # 15 s: folga dentro da Lambda de 30 s mesmo se o primeiro modelo falhar.
        self._client = client or httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0))
        self._cadeia = Cadeia(modelos, relogio, dorme)
        self.ultimo_uso: Uso | None = None

    def corpo(
        self, texto: str, categorias: list[CategoriaPrompt], hoje: date, modelo: str = ""
    ) -> dict[str, Any]:
        return self._corpo(modelo, mensagens(texto, categorias, hoje), "extracao", esquema_json())

    def corpo_correcao(
        self,
        texto: str,
        atual: str,
        categorias: list[CategoriaPrompt],
        hoje: date,
        modelo: str = "",
    ) -> dict[str, Any]:
        msgs = mensagens_correcao(texto, atual, categorias, hoje)
        return self._corpo(modelo, msgs, "correcao", esquema_correcao())

    def corpo_consulta(
        self, texto: str, categorias: list[CategoriaPrompt], hoje: date, modelo: str = ""
    ) -> dict[str, Any]:
        msgs = mensagens_consulta(texto, categorias, hoje)
        return self._corpo(modelo, msgs, "consulta", esquema_consulta())

    def corpo_conversa(self, texto: str, modelo: str = "") -> dict[str, Any]:
        return self._corpo(modelo, mensagens_conversa(texto), "conversa", esquema_conversa())

    def corpo_escolha(
        self, pergunta: str, opcoes: list[str], texto: str, modelo: str = ""
    ) -> dict[str, Any]:
        msgs = mensagens_escolha(pergunta, opcoes, texto)
        return self._corpo(modelo, msgs, "escolha", esquema_escolha())

    def _corpo(
        self, modelo: str, msgs: list[dict[str, str]], nome: str, esquema: dict[str, Any]
    ) -> dict[str, Any]:
        modelo = modelo or self._modelos[0]
        return {
            "model": modelo,
            "messages": msgs,
            "temperature": 0,
            **PARAMETROS[modelo],
            "max_completion_tokens": 2000,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": nome, "strict": True, "schema": esquema},
            },
        }

    def extrai(self, texto: str, categorias: list[CategoriaPrompt], hoje: date) -> ExtracaoIA:
        self.ultimo_uso = None
        extracao, _modelo = self._cadeia.executa(
            lambda modelo: self._chama(
                modelo, self.corpo(texto, categorias, hoje, modelo), ExtracaoIA
            )
        )
        return extracao

    def corrige(
        self, texto: str, atual: str, categorias: list[CategoriaPrompt], hoje: date
    ) -> CorrecaoIA:
        """Correção de um lançamento existente (D042): devolve só o que a pessoa quer mudar."""
        self.ultimo_uso = None
        correcao, _modelo = self._cadeia.executa(
            lambda modelo: self._chama(
                modelo, self.corpo_correcao(texto, atual, categorias, hoje, modelo), CorrecaoIA
            )
        )
        return correcao

    def consulta(
        self, texto: str, categorias: list[CategoriaPrompt], hoje: date
    ) -> tuple[ConsultaIA, str]:
        """Pedido de relatório (S6): (campos, modelo que respondeu)."""
        self.ultimo_uso = None
        return self._cadeia.executa(
            lambda modelo: self._chama(
                modelo, self.corpo_consulta(texto, categorias, hoje, modelo), ConsultaIA
            )
        )

    def conversa(self, texto: str) -> tuple[ConversaIA, str]:
        """Mensagem que não é lançamento nem consulta: resposta curta + tela a abrir."""
        self.ultimo_uso = None
        return self._cadeia.executa(
            lambda modelo: self._chama(modelo, self.corpo_conversa(texto, modelo), ConversaIA)
        )

    def escolha(self, pergunta: str, opcoes: list[str], texto: str) -> tuple[EscolhaIA, str]:
        """Resposta escrita a uma pergunta com botões: (opção escolhida, modelo)."""
        self.ultimo_uso = None
        return self._cadeia.executa(
            lambda modelo: self._chama(
                modelo, self.corpo_escolha(pergunta, opcoes, texto, modelo), EscolhaIA
            )
        )

    def _chama(self, modelo: str, corpo: dict[str, Any], tipo: type[Saida]) -> Saida:
        try:
            resposta = self._client.post(URL, headers=self._headers, json=corpo)
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
            return tipo.model_validate(json.loads(conteudo))
        except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
            raise ErroIA(f"resposta inválida ({type(exc).__name__})") from None

"""Cliente do Groq com HTTP simulado (sem rede)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import httpx
import pytest

from telegrana.ai.groq import ErroIA, Groq
from telegrana.ai.prompt import CategoriaPrompt

CHAVE = "gsk_segredo_de_teste"
CATS = [CategoriaPrompt("mercado", "Mercado", "gasto")]
VALIDA = {
    "intencao": "lancamentos",
    "lancamentos": [
        {
            "tipo": "gasto",
            "valor_texto": "45,90",
            "data_texto": None,
            "descricao": "mercado",
            "categoria": "mercado",
            "categorias_sugeridas": [],
            "nova_categoria_sugerida": None,
            "forma_pagamento": "pix",
            "cartao": None,
            "parcelas": None,
            "pode_ser_fixo": False,
            "duvida": None,
        }
    ],
    "correcao_campo": None,
    "correcao_texto": None,
    "pergunta": None,
}


def cliente(
    status: int, corpo: Any, cabecalhos: dict[str, str] | None = None
) -> tuple[Groq, list[Any]]:
    pedidos: list[Any] = []

    def responde(request: httpx.Request) -> httpx.Response:
        pedidos.append(request)
        return httpx.Response(status, json=corpo, headers=cabecalhos or {})

    return Groq(CHAVE, client=httpx.Client(transport=httpx.MockTransport(responde))), pedidos


def resposta(conteudo: Any, uso: dict[str, Any] | None = None) -> dict[str, Any]:
    texto = conteudo if isinstance(conteudo, str) else json.dumps(conteudo)
    return {"choices": [{"message": {"content": texto}}], "usage": uso or {}}


def test_extrai_e_envia_pedido_estrito() -> None:
    groq, pedidos = cliente(
        200,
        resposta(
            VALIDA,
            {
                "prompt_tokens": 1350,
                "completion_tokens": 200,
                "prompt_tokens_details": {"cached_tokens": 1280},
            },
        ),
    )
    r = groq.extrai("mercado 45,90 no pix", CATS, date(2026, 10, 1))
    assert r.lancamentos[0].valor_texto == "45,90"
    assert groq.ultimo_uso is not None
    assert groq.ultimo_uso.tokens_em_cache == 1280
    enviado = json.loads(pedidos[0].content)
    assert enviado["model"] == "openai/gpt-oss-20b"
    assert enviado["temperature"] == 0
    assert enviado["response_format"]["json_schema"]["strict"] is True
    assert pedidos[0].headers["authorization"] == f"Bearer {CHAVE}"


def test_limite_vira_erro_com_espera() -> None:
    groq, _ = cliente(429, {"error": {"message": "rate limit"}}, {"retry-after": "7"})
    with pytest.raises(ErroIA) as info:
        groq.extrai("x", CATS, date(2026, 10, 1))
    assert info.value.limite
    assert info.value.espera == 7.0


@pytest.mark.parametrize(
    "corpo",
    [
        resposta("isso não é json"),
        resposta({**VALIDA, "campo_extra": "drop table"}),
        resposta({**VALIDA, "intencao": "apagar_tudo"}),
        {"sem": "choices"},
    ],
)
def test_resposta_invalida_e_recusada(corpo: Any) -> None:
    groq, _ = cliente(200, corpo)
    with pytest.raises(ErroIA, match="resposta inválida") as info:
        groq.extrai("x", CATS, date(2026, 10, 1))
    assert not info.value.limite


def test_erro_http_nao_vaza_chave_nem_texto() -> None:
    groq, _ = cliente(500, {"error": "boom"})
    with pytest.raises(ErroIA) as info:
        groq.extrai("minha mensagem secreta", CATS, date(2026, 10, 1))
    assert CHAVE not in str(info.value)
    assert "secreta" not in str(info.value)

"""Cliente do Groq com HTTP simulado (sem rede)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import httpx
import pytest

from telegrana.ai.groq import MODELOS, ErroIA, Groq
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
    assert enviado["model"] == MODELOS[0]
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


# ---------------------------------------------------------------------------
# Cadeia de modelos (D040)
# ---------------------------------------------------------------------------
class Relogio:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def cadeia(
    por_modelo: dict[str, tuple[int, Any, dict[str, str]]],
) -> tuple[Groq, list[str], Relogio]:
    chamados: list[str] = []

    def responde(request: httpx.Request) -> httpx.Response:
        modelo = json.loads(request.content)["model"]
        chamados.append(modelo)
        status, corpo, cabecalhos = por_modelo[modelo]
        return httpx.Response(status, json=corpo, headers=cabecalhos)

    relogio = Relogio()
    groq = Groq(
        CHAVE,
        modelos=("openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"),
        client=httpx.Client(transport=httpx.MockTransport(responde)),
        relogio=relogio,
    )
    return groq, chamados, relogio


LIMITE = (429, {"error": {"message": "rate limit"}}, {"retry-after": "300"})
OK = (200, resposta(VALIDA, {"prompt_tokens": 1000, "completion_tokens": 100}), {})


def test_modelo_esgotado_passa_para_o_seguinte_e_fica_de_fora() -> None:
    groq, chamados, relogio = cadeia(
        {"openai/gpt-oss-20b": LIMITE, "openai/gpt-oss-120b": OK, "qwen/qwen3.8-27b": OK}
    )
    groq.extrai("x", CATS, date(2026, 10, 1))
    assert chamados == ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]
    assert groq.ultimo_uso is not None
    assert groq.ultimo_uso.modelo == "openai/gpt-oss-120b"
    groq.extrai("y", CATS, date(2026, 10, 1))  # o 20b continua de fora
    assert chamados[2:] == ["openai/gpt-oss-120b"]
    relogio.t += 301  # passou o retry-after: o principal volta a ser tentado
    groq.extrai("z", CATS, date(2026, 10, 1))
    assert chamados[3:] == ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]


def test_modelo_bloqueado_na_organizacao_e_pulado() -> None:
    bloqueado = (403, {"error": {"message": "blocked at the organization level"}}, {})
    groq, chamados, _ = cadeia(
        {"openai/gpt-oss-20b": LIMITE, "openai/gpt-oss-120b": LIMITE, "qwen/qwen3.8-27b": bloqueado}
    )
    with pytest.raises(ErroIA) as info:
        groq.extrai("x", CATS, date(2026, 10, 1))
    assert info.value.limite  # dois no limite e um bloqueado: "muita demanda"
    assert info.value.espera == 300.0
    with pytest.raises(ErroIA) as info:
        groq.extrai("y", CATS, date(2026, 10, 1))
    assert info.value.limite
    assert len(chamados) == 3  # nada foi chamado de novo


def test_resposta_invalida_de_um_modelo_tenta_o_seguinte() -> None:
    groq, chamados, _ = cadeia(
        {
            "openai/gpt-oss-20b": (200, resposta("não é json"), {}),
            "openai/gpt-oss-120b": OK,
            "qwen/qwen3.8-27b": OK,
        }
    )
    assert groq.extrai("x", CATS, date(2026, 10, 1)).intencao == "lancamentos"
    assert chamados == ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]


def test_parametros_de_cada_modelo() -> None:
    groq, _, _ = cadeia({})
    qwen = groq.corpo("x", CATS, date(2026, 10, 1), "qwen/qwen3.8-27b")
    assert qwen["reasoning_effort"] == "low"
    assert qwen["reasoning_format"] == "hidden"
    assert "include_reasoning" not in qwen
    oss = groq.corpo("x", CATS, date(2026, 10, 1), "openai/gpt-oss-120b")
    assert oss["include_reasoning"] is False
    with pytest.raises(ValueError, match="modelos sem parâmetros"):
        Groq(CHAVE, modelos=("modelo/inventado",))


def test_limite_por_minuto_curto_espera_e_tenta_de_novo() -> None:
    respostas = iter(
        [
            (429, {"error": {}}, {"retry-after": "2"}),  # 20b
            (429, {"error": {}}, {"retry-after": "3"}),  # 120b
            (429, {"error": {}}, {"retry-after": "2"}),  # qwen
            OK,  # 20b de novo, depois da espera
        ]
    )
    esperas: list[float] = []

    def responde(request: httpx.Request) -> httpx.Response:
        status, corpo, cabecalhos = next(respostas)
        return httpx.Response(status, json=corpo, headers=cabecalhos)

    relogio = Relogio()

    def dorme(segundos: float) -> None:
        esperas.append(segundos)
        relogio.t += segundos

    groq = Groq(
        CHAVE,
        modelos=("openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"),
        client=httpx.Client(transport=httpx.MockTransport(responde)),
        relogio=relogio,
        dorme=dorme,
    )
    assert groq.extrai("x", CATS, date(2026, 10, 1)).intencao == "lancamentos"
    assert esperas == [2.0]


def test_limite_longo_nao_espera() -> None:
    groq, _, _ = cadeia(
        {"openai/gpt-oss-20b": LIMITE, "openai/gpt-oss-120b": LIMITE, "qwen/qwen3.8-27b": LIMITE}
    )
    with pytest.raises(ErroIA) as info:
        groq.extrai("x", CATS, date(2026, 10, 1))
    assert info.value.limite
    assert info.value.espera == 300.0

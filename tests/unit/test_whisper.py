"""Transcrição pelo Whisper com HTTP simulado (sem rede)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from telegrana.ai.whisper import MODELOS, Whisper
from telegrana.core.audio import resumo, segundos_cobrados
from telegrana.core.entendimento import ErroExtracao

CHAVE = "gsk_segredo_whisper"


def cliente(*respostas: tuple[int, Any, dict[str, str]]) -> tuple[Whisper, list[httpx.Request]]:
    pedidos: list[httpx.Request] = []
    fila = list(respostas)

    def responde(request: httpx.Request) -> httpx.Response:
        pedidos.append(request)
        status, corpo, cabecalhos = fila.pop(0) if len(fila) > 1 else fila[0]
        return httpx.Response(status, json=corpo, headers=cabecalhos)

    transporte = httpx.Client(transport=httpx.MockTransport(responde))
    return Whisper(CHAVE, client=transporte), pedidos


def test_transcreve_em_portugues_com_vocabulario() -> None:
    whisper, pedidos = cliente((200, {"text": "  gastei 30 reais\nde pão hoje "}, {}))
    t = whisper.transcreve(b"OggS-audio", "ogg", 4)
    assert t.texto == "gastei 30 reais de pão hoje"
    assert t.modelo == MODELOS[0]
    assert t.segundos == 10  # cobrança mínima do Groq
    corpo = pedidos[0].content
    assert b'name="language"' in corpo
    assert b"\r\n\r\npt\r\n" in corpo
    assert b'filename="audio.ogg"' in corpo
    assert b"Nubank" in corpo  # vocabulário vai no prompt
    assert pedidos[0].headers["authorization"] == f"Bearer {CHAVE}"


def test_limite_no_v3_passa_para_o_turbo() -> None:
    whisper, pedidos = cliente(
        (429, {"error": {}}, {"retry-after": "120"}), (200, {"text": "uber 18"}, {})
    )
    t = whisper.transcreve(b"x", "ogg", 30)
    assert (t.texto, t.modelo, t.segundos) == ("uber 18", "whisper-large-v3-turbo", 30)
    assert len(pedidos) == 2


def test_todos_no_limite_e_erro_sem_vazar_chave() -> None:
    whisper, _ = cliente((429, {"error": {}}, {"retry-after": "60"}))
    with pytest.raises(ErroExtracao) as info:
        whisper.transcreve(b"x", "ogg", 5)
    assert info.value.limite
    assert CHAVE not in str(info.value)


def test_formato_desconhecido_vira_ogg_e_resposta_invalida() -> None:
    whisper, pedidos = cliente((200, {"sem": "texto"}, {}))
    with pytest.raises(ErroExtracao, match="resposta inválida"):
        whisper.transcreve(b"x", "exe", 5)
    assert b'filename="audio.ogg"' in pedidos[0].content


def test_segundos_cobrados_e_resumo() -> None:
    assert segundos_cobrados(0) == 10
    assert segundos_cobrados(61) == 61
    assert resumo("curto") == "curto"
    longo = "acabei de pagar a conta de água e também a de luz, deu tudo uns trezentos reais"
    corte = resumo(longo, 40)
    assert corte.endswith("…")
    assert len(corte) <= 41

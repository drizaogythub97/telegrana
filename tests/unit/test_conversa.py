"""Conversa (D050): limpeza da resposta e falhas da IA."""

from __future__ import annotations

from typing import Any

from telegrana.core import conversa
from telegrana.core.entendimento import ErroExtracao
from telegrana.core.extracao import ConversaIA


def test_limpa() -> None:
    assert conversa.limpa("Veja https://x.com/a?b=1 e www.y.com.br  ok") == "Veja e ok"
    assert conversa.limpa("**Oi**\n\n  tudo `bem`?  ") == "Oi\ntudo bem?"
    assert conversa.limpa("t.me/outro_bot fala") == "fala"
    assert len(conversa.limpa("a" * 2000)) == conversa.LIMITE


class IA:
    def __init__(self, resposta: ConversaIA | None) -> None:
        self.resposta = resposta
        self.ultimo_uso: Any = None

    def conversa(self, texto: str, pergunta: str = "") -> tuple[ConversaIA, str]:
        if self.resposta is None:
            raise ErroExtracao("limite", limite=True)
        return self.resposta, "m"


def test_gera() -> None:
    c = conversa.gera(IA(ConversaIA(resposta="Claro!", abrir="fixos")), "x")
    assert (c.texto, c.abrir, c.modelo) == ("Claro!", "fixos", "m")
    assert conversa.gera(IA(None), "x") == conversa.Conversa(None)
    assert conversa.gera(None, "x") == conversa.Conversa(None)
    so_link = conversa.gera(IA(ConversaIA(resposta="https://x.com", abrir="nenhuma")), "x")
    assert so_link.texto is None  # nada sobrou: vale o texto fixo


def test_telas_so_abrem_o_que_a_pessoa_abriria() -> None:
    for comando, acao in conversa.TELAS.values():
        alvo = comando or acao or ""
        assert alvo
        assert "apagar" not in alvo

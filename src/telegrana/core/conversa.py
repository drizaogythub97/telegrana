"""Conversa (D050): a mensagem que não é lançamento, consulta nem concordância.

Antes, tudo isso caía num texto fixo ("🤔 Não entendi bem…"), mesmo quando a pessoa só
avisava o que ia fazer ("quero cadastrar um gasto fixo"). Agora uma segunda chamada à IA —
só nesses casos, com o guia do que o bot faz — responde em texto curto e natural e aponta,
se ajudar, UMA tela de uma lista fixa (`extracao.Abrir`), que o roteador abre como se a
pessoa tivesse mandado o comando. "fixo_novo" prepara a próxima mensagem para virar fixo.

A IA de conversa não vê nenhum dado da pessoa (só a mensagem) e não executa nada; a
resposta vai só para quem mandou, sem links e sem marcação. Falhou → o texto fixo de antes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from telegrana.core.entendimento import ErroExtracao
from telegrana.core.mensagens import seguro

FIXO_NOVO = "fixo_novo"
# Tela → (comando, ação) da `Entrada` que a abre (só o que a pessoa abriria sozinha).
TELAS: dict[str, tuple[str | None, str | None]] = {
    "fixos": ("fixos", None),
    "cartoes": ("cartoes", None),
    "cartao_novo": (None, "ct:nv"),
    "categorias": ("categorias", None),
    "resumo": ("resumo", None),
    "fatura": ("fatura", None),
    "exportar": ("exportar", None),
    "ajuda": ("ajuda", None),
    "meus_dados": ("meus_dados", None),
}
LIMITE = 700
_LINK = re.compile(r"(https?://|www\.|t\.me/)\S*", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Conversa:
    texto: str | None  # None = sem IA ou ela falhou: vale o texto fixo
    abrir: str = "nenhuma"
    modelo: str | None = None
    tokens: int = 0


def limpa(texto: str) -> str:
    """Sem links nem marcação; espaços e quebras normalizados; no máximo `LIMITE`."""
    sem_link = _LINK.sub("", texto)
    linhas = [" ".join(x.split()) for x in sem_link.splitlines()]
    return seguro("\n".join(x for x in linhas if x), LIMITE)


def gera(extrator: Any, texto: str, pergunta_aberta: str = "") -> Conversa:
    """`pergunta_aberta`: a pergunta do bot que a mensagem deixou sem resposta (escrita pelo
    bot; a IA a usa para lembrar a pessoa)."""
    chama = getattr(extrator, "conversa", None)
    if chama is None:
        return Conversa(None)
    try:
        ia, modelo = chama(texto, pergunta_aberta)
    except ErroExtracao:
        return Conversa(None)
    uso = getattr(extrator, "ultimo_uso", None)
    tokens = max(0, uso.tokens_entrada - uso.tokens_em_cache) + uso.tokens_saida if uso else 0
    resposta = limpa(ia.resposta)
    return Conversa(resposta or None, ia.abrir, modelo, tokens)

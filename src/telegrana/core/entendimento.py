"""Entender uma mensagem: atalho sem IA primeiro, IA só quando precisa (D038).

É o MESMO caminho no bot e na avaliação (scripts/avaliar_ia.py): o que a avaliação mede é
o que o bot faz.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from telegrana.core import atalho
from telegrana.core.extracao import CategoriaPrompt, ExtracaoIA
from telegrana.core.interpretacao import CategoriaConta, Interpretacao, Regra, interpreta


class Extrator(Protocol):
    """Provedor de IA (Groq hoje). Erros de limite sobem para quem chamou."""

    ultimo_uso: Any

    def extrai(self, texto: str, categorias: list[CategoriaPrompt], hoje: date) -> ExtracaoIA: ...


@dataclass(frozen=True, slots=True)
class Entendimento:
    interpretacao: Interpretacao
    usou_ia: bool
    tokens: int  # contados no limite do provedor (entrada sem cache + saída)


def para_prompt(categorias: list[CategoriaConta]) -> list[CategoriaPrompt]:
    tipos = {"expense": "gasto", "income": "ganho"}
    return [CategoriaPrompt(c.chave, c.nome, tipos[c.tipo]) for c in categorias]


def entende(
    texto: str,
    categorias: list[CategoriaConta],
    regras: list[Regra],
    hoje: date,
    extrator: Extrator,
) -> Entendimento:
    rapido = atalho.tenta(texto)
    if rapido is not None:
        return Entendimento(interpreta(rapido, texto, categorias, regras, hoje), False, 0)
    extracao = extrator.extrai(texto, para_prompt(categorias), hoje)
    uso = getattr(extrator, "ultimo_uso", None)
    tokens = 0
    if uso is not None:
        tokens = max(0, uso.tokens_entrada - uso.tokens_em_cache) + uso.tokens_saida
    return Entendimento(interpreta(extracao, texto, categorias, regras, hoje), True, tokens)

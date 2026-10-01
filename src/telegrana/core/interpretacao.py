"""Da extração da IA para lançamentos propostos (PLANO 4.1, 5.2; D028, D035, D037).

Aqui o CÓDIGO decide: converte valores e datas, confere se a categoria existe na conta,
aplica as regras aprendidas da pessoa (que valem mais que a IA) e lista as pendências
que viram pergunta. A IA nunca grava nada: ela só sugere.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from telegrana.core import datas, valores
from telegrana.core.extracao import ExtracaoIA, LancamentoIA

CONFIRMAR_ACIMA_DE = 1_000_000  # R$ 10.000,00: valor alto pede confirmação
GENERICAS = frozenset({"outros", "outros_ganhos"})  # D028: nunca sem perguntar
_TOTAL_ACUMULADO = re.compile(r"\b(esse|este|no|nesse|neste) mes (ja|todo|inteiro)\b")
_TIPO = {"gasto": "expense", "ganho": "income", "transferencia": "transfer"}


@dataclass(frozen=True, slots=True)
class CategoriaConta:
    chave: str  # o `code` das padrão ou o nome das criadas: é o que a IA vê e devolve
    nome: str
    emoji: str
    tipo: str  # "expense" | "income"


@dataclass(frozen=True, slots=True)
class Regra:
    padrao: str  # normalizado, minúsculo, sem acento
    chave: str


@dataclass(frozen=True, slots=True)
class Proposta:
    tipo: str  # expense | income | transfer
    centavos: int | None
    data: date | None
    futura: bool
    categoria: str | None  # chave
    sugestoes: tuple[str, ...]
    nova_sugerida: str | None
    forma: str | None
    cartao: str | None
    parcelas: int | None
    descricao: str | None
    pode_ser_fixo: bool
    duvida: str | None
    pendencias: tuple[str, ...]  # valor, categoria, data, confirmar_valor, duvida

    @property
    def completa(self) -> bool:
        return not self.pendencias


@dataclass(frozen=True, slots=True)
class Interpretacao:
    intencao: str
    propostas: tuple[Proposta, ...]
    correcao_campo: str | None
    correcao_texto: str | None
    pergunta: str | None


def normaliza(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto.lower()) if not unicodedata.combining(c)
    )
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", sem_acento).split())


def _chave(valor: str | None, validas: dict[str, CategoriaConta]) -> str | None:
    """Aceita o código ou o nome (a IA às vezes devolve "saúde" em vez de "saude")."""
    if not valor:
        return None
    if valor in validas:
        return valor
    alvo = normaliza(valor)
    return next((k for k, c in validas.items() if normaliza(c.nome) == alvo), None)


def _regra_que_casa(texto: str, regras: list[Regra]) -> Regra | None:
    alvo = f" {normaliza(texto)} "
    # A regra mais específica (mais longa) ganha.
    for regra in sorted(regras, key=lambda r: len(r.padrao), reverse=True):
        if f" {regra.padrao} " in alvo:
            return regra
    return None


def _proposta(
    item: LancamentoIA,
    mensagem: str,
    categorias: dict[str, CategoriaConta],
    regras: list[Regra],
    hoje: date,
) -> Proposta:
    tipo = _TIPO[item.tipo]
    pendencias: list[str] = []

    valor = valores.interpreta(item.valor_texto)
    if valor.centavos is None:
        pendencias.append("valor")
    elif valor.centavos >= CONFIRMAR_ACIMA_DE:
        pendencias.append("confirmar_valor")

    # A IA às vezes perde a data ou o "vence": o código procura na frase inteira.
    expressao = item.data_texto
    no_texto = datas.expressao_em(mensagem)
    if no_texto and (
        expressao is None or (no_texto.startswith("vence") and "venc" not in expressao)
    ):
        expressao = no_texto
    quando = datas.resolve(expressao, hoje)
    if quando.dia is None:
        pendencias.append("data")

    validas = {k: c for k, c in categorias.items() if c.tipo == tipo}
    categoria = _chave(item.categoria, validas)
    sugeridas = (_chave(s, validas) for s in item.categorias_sugeridas)
    sugestoes = tuple(dict.fromkeys(s for s in sugeridas if s and s != categoria))
    if categoria in GENERICAS:  # "Outros" só com a pessoa escolhendo
        sugestoes, categoria = (*sugestoes, categoria), None
    if tipo != "transfer":
        regra = _regra_que_casa(f"{item.descricao or ''} {mensagem}", regras)
        if regra and regra.chave in validas:
            categoria, sugestoes = regra.chave, ()  # o que a pessoa ensinou vale mais
        if categoria is None:
            pendencias.append("categoria")
    else:
        categoria, sugestoes = None, ()

    acumulado = bool(_TOTAL_ACUMULADO.search(normaliza(mensagem)))
    if (item.duvida or acumulado) and "categoria" not in pendencias and "valor" not in pendencias:
        pendencias.append("duvida")

    return Proposta(
        tipo=tipo,
        centavos=valor.centavos,
        data=quando.dia,
        futura=quando.futura,
        categoria=categoria,
        sugestoes=sugestoes,
        nova_sugerida=(item.nova_categoria_sugerida or None) if categoria is None else None,
        forma=item.forma_pagamento,
        cartao=item.cartao,
        parcelas=item.parcelas,
        descricao=item.descricao,
        pode_ser_fixo=item.pode_ser_fixo,
        duvida=item.duvida,
        pendencias=tuple(pendencias),
    )


def interpreta(
    extracao: ExtracaoIA,
    mensagem: str,
    categorias: list[CategoriaConta],
    regras: list[Regra],
    hoje: date,
) -> Interpretacao:
    por_chave = {c.chave: c for c in categorias}
    propostas: tuple[Proposta, ...] = ()
    if extracao.intencao == "lancamentos":
        propostas = tuple(
            _proposta(item, mensagem, por_chave, regras, hoje) for item in extracao.lancamentos
        )
    return Interpretacao(
        intencao=extracao.intencao,
        propostas=propostas,
        correcao_campo=extracao.correcao_campo,
        correcao_texto=extracao.correcao_texto,
        pergunta=extracao.pergunta,
    )

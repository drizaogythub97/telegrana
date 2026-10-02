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
# Ambíguos (D037): o bot SEMPRE pergunta, mesmo com a IA "certa". termo → (opções, nova)
AMBIGUOS: dict[str, tuple[tuple[str, ...], str]] = {
    "padaria": (("mercado", "alimentacao"), "Padaria"),
    "pao": (("mercado", "alimentacao"), "Padaria"),
    "paes": (("mercado", "alimentacao"), "Padaria"),
    "bar": (("lazer", "alimentacao"), "Bar"),
    "boteco": (("lazer", "alimentacao"), "Bar"),
    "academia": (("saude", "lazer"), "Academia"),
    "escola": (("educacao", "filhos"), "Escola"),
    "colegio": (("educacao", "filhos"), "Escola"),
    "creche": (("educacao", "filhos"), "Escola"),
}
# Regras de fábrica: abaixo das regras da pessoa, acima da IA.
REGRAS_PADRAO: tuple[tuple[str, str], ...] = (
    ("botijao", "contas_casa"),
    ("gas de cozinha", "contas_casa"),
    ("gas", "contas_casa"),
    ("seguro do carro", "transporte"),
    ("seguro da moto", "transporte"),
    ("seguro do veiculo", "transporte"),
)
_COMBUSTIVEL = ("gasolina", "etanol", "alcool", "diesel", "posto", "gnv")
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


def _menciona_data(texto: str) -> bool:
    t = normaliza(texto)
    return any(p in t.split() for p in ("dia", "ontem", "anteontem", "amanha", "semana", "mes"))


def _ambiguo(texto: str) -> tuple[tuple[str, ...], str] | None:
    palavras = set(normaliza(texto).split())
    return next((AMBIGUOS[p] for p in AMBIGUOS if p in palavras), None)


def _regras_padrao(texto: str) -> list[Regra]:
    t = normaliza(texto)
    if any(c in t.split() for c in _COMBUSTIVEL):  # "gás" do carro é combustível
        return []
    return [Regra(padrao, chave) for padrao, chave in REGRAS_PADRAO]


def _junta_valor_partido(itens: list[LancamentoIA], mensagem: str) -> list[LancamentoIA]:
    """ "trinta e cinco e noventa" é UM valor (R$ 35,90): desfaz a divisão da IA."""
    texto = normaliza(mensagem)
    saida: list[LancamentoIA] = []
    for item in itens:
        anterior = saida[-1] if saida else None
        if (
            anterior is not None
            and anterior.valor_texto
            and item.valor_texto
            and not any(c.isdigit() for c in anterior.valor_texto + item.valor_texto)
        ):
            junto = f"{normaliza(anterior.valor_texto)} e {normaliza(item.valor_texto)}"
            if junto in texto and valores.interpreta(junto).centavos is not None:
                saida[-1] = anterior.model_copy(update={"valor_texto": junto})
                continue
        saida.append(item)
    return saida


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
    *,
    sozinho: bool = True,
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
    copiado = bool(item.data_texto) and normaliza(item.data_texto or "") in normaliza(mensagem)
    if quando.dia is None and no_texto is None and not (copiado and _menciona_data(mensagem)):
        quando = datas.Data(hoje)  # a IA pôs lixo na data e a frase não fala de data: hoje
    if quando.dia is None:
        pendencias.append("data")

    validas = {k: c for k, c in categorias.items() if c.tipo == tipo}
    categoria = _chave(item.categoria, validas)
    sugeridas = (_chave(s, validas) for s in item.categorias_sugeridas)
    sugestoes = tuple(dict.fromkeys(s for s in sugeridas if s and s != categoria))
    if categoria in GENERICAS:  # "Outros" só com a pessoa escolhendo
        sugestoes, categoria = (*sugestoes, categoria), None
    nova = (item.nova_categoria_sugerida or None) if categoria is None else None
    if tipo != "transfer":
        alvo = f"{item.descricao or ''} {mensagem if sozinho else ''}"
        regra = _regra_que_casa(alvo, regras)
        if regra and regra.chave in validas:
            categoria, sugestoes, nova = regra.chave, (), None  # o que a pessoa ensinou vale mais
        else:
            ambiguo = _ambiguo(alvo)
            fabrica = _regra_que_casa(alvo, _regras_padrao(alvo))
            if ambiguo:
                opcoes, nome = ambiguo
                sugestoes = tuple(o for o in opcoes if o in validas)
                categoria, nova = None, nome
            elif fabrica and fabrica.chave in validas:
                categoria, sugestoes, nova = fabrica.chave, (), None
        if categoria is None:
            pendencias.append("categoria")
    else:
        categoria, sugestoes, nova = None, (), None

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
        nova_sugerida=nova,
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
        itens = _junta_valor_partido(list(extracao.lancamentos), mensagem)
        propostas = tuple(
            _proposta(item, mensagem, por_chave, regras, hoje, sozinho=len(itens) == 1)
            for item in itens
        )
    return Interpretacao(
        intencao=extracao.intencao,
        propostas=propostas,
        correcao_campo=extracao.correcao_campo,
        correcao_texto=extracao.correcao_texto,
        pergunta=extracao.pergunta,
    )

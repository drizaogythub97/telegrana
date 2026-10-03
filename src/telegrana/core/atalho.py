"""Atalho sem IA para mensagens simples (D038): "mercado 45,90 no pix", "uber 18".

Monta a MESMA estrutura que a IA devolveria (`ExtracaoIA`), para passar pelas mesmas
regras de `core.interpretacao` (categorias da conta, regras da pessoa, ambíguos que
perguntam, valores e datas no código). Na dúvida, devolve None e a IA decide.
"""

from __future__ import annotations

import re
import unicodedata

from telegrana.core import datas, valores
from telegrana.core.extracao import ExtracaoIA, LancamentoIA
from telegrana.core.interpretacao import _TOTAL_ACUMULADO, AMBIGUOS, normaliza

# Palavra → código da categoria padrão. Só termos sem ambiguidade (os ambíguos ficam em
# interpretacao.AMBIGUOS e viram pergunta).
PALAVRAS: dict[str, str] = {
    **dict.fromkeys(
        ("mercado", "supermercado", "acougue", "sacolao", "hortifruti", "feira", "atacadao"),
        "mercado",
    ),
    **dict.fromkeys(
        ("ifood", "lanche", "almoco", "jantar", "restaurante", "pizza", "hamburguer", "cafe"),
        "alimentacao",
    ),
    **dict.fromkeys(("aluguel", "condominio", "iptu"), "moradia"),
    **dict.fromkeys(("luz", "agua", "internet", "energia", "gas", "botijao"), "contas_casa"),
    **dict.fromkeys(
        ("uber", "onibus", "metro", "estacionamento", "pedagio", "taxi", "passagem"),
        "transporte",
    ),
    **dict.fromkeys(
        ("gasolina", "etanol", "posto", "abasteci", "abastecer", "combustivel", "diesel"),
        "combustivel",
    ),
    **dict.fromkeys(
        ("farmacia", "remedio", "medico", "dentista", "consulta", "exame", "drogaria"), "saude"
    ),
    **dict.fromkeys(("curso", "livro", "faculdade", "mensalidade"), "educacao"),
    **dict.fromkeys(("cinema", "show", "teatro", "ingresso"), "lazer"),
    **dict.fromkeys(("roupa", "tenis", "blusa", "calca", "camisa", "sapato"), "vestuario"),
    **dict.fromkeys(
        ("netflix", "spotify", "disney", "hbo", "youtube", "prime", "assinatura"),
        "assinaturas",
    ),
    **dict.fromkeys(
        ("racao", "veterinario", "petshop", "pet", "dog", "cachorro", "gato", "cao"), "pets"
    ),
    **dict.fromkeys(("presente",), "presentes"),
    **dict.fromkeys(("juros", "multa", "tarifa"), "encargos"),
}
GANHOS: dict[str, str] = {
    "salario": "salario",
    "freela": "servicos",
    "freelance": "servicos",
    "rendimento": "rendimentos",
    "rendimentos": "rendimentos",
    "reembolso": "reembolso",
}
_VERBO_GANHO = {"recebi", "caiu", "ganhei", "entrou", "recebido"}
_VERBO_GASTO = {"gastei", "comprei", "paguei"}
_PERGUNTA = re.compile(
    r"\b(quanto|quanta|quantos|quantas|qnt|qto|qual|quais|como|relatorio|resumo|saldo|sobrou)\b"
)
_RECORRENTES = {
    "aluguel",
    "condominio",
    "escola",
    "internet",
    "luz",
    "agua",
    "netflix",
    "spotify",
    "disney",
    "hbo",
    "assinatura",
    "salario",
    "mensalidade",
    "seguro",
}
# Qualquer uma destas manda para a IA (correção, consulta, transferência, frase longa...).
_FORA = re.compile(
    r"\b(vdd|verdade|nao era|errado|errei|apaga|apague|corrig|quanto|qnt|qto|quantos|relatorio|"
    r"pdf|planilha|fatura|sobrou|saldo|gastei com|poupanca|guardei|guardar|investi|aplicar|"
    r"transferi|dividido|minha parte|parcel|vaquinha|devolv|mil|milhao|k|"
    r"e pouco|e poucos|e tanto|e tantos|mercado livre|amazon|shopee|magalu|aliexpress)\b"
)
_VALOR = re.compile(r"(?<![\w/])(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)(?![\w/%])")
_PARCELAS = re.compile(r"\b(?:em\s+)?(\d{1,2})\s*x\b")
_FORMAS = (
    (re.compile(r"\bpix\b"), "pix", None),
    (re.compile(r"\b(deb|debito)\b"), "debito", None),
    (re.compile(r"\b(dinheiro|especie)\b"), "dinheiro", None),
    (re.compile(r"\bboleto\b"), "boleto", None),
    (re.compile(r"\b(cred|credito)\b"), "credito", None),
    (re.compile(r"\bno (nu|nubank)\b"), "credito", "nubank"),
    (re.compile(r"\b(inter|itau|c6|bradesco|santander|caixa|picpay)\b"), "credito", "_banco"),
)
LIMITE_PALAVRAS = 9
_VAZIAS = frozenset(
    {"no", "na", "de", "do", "da", "em", "o", "a", "um", "uma", "reais", "real", "r", "rs"}
    | {"hoje", "hj", "ontem", "anteontem", "dia", "agora", "agr"}
)
_PAGAMENTO = re.compile(
    r"pix|deb|debito|dinheiro|especie|boleto|cred|credito|cartao|nu|nubank|inter|itau|c6|"
    r"bradesco|santander|caixa|picpay"
)
LIMITE_RESGATE = 12


def forma_em(texto: str) -> tuple[str | None, str | None]:
    """(forma, cartão) citados na frase, ou (None, None)."""
    t = normaliza(texto)
    for padrao, nome, banco in _FORMAS:
        achado = padrao.search(t)
        if achado:
            return nome, (achado.group(1) if banco == "_banco" else banco)
    return None, None


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def _valores_em_digitos(texto: str) -> list[str]:
    bruto = " ".join(_sem_acento(texto.lower()).replace("r$", " ").split())  # mantém , e .
    # Parcelas ("3x") e datas ("dia 5", "05/09") não podem ser confundidas com o valor.
    sem_ruido = _PARCELAS.sub(" ", bruto)
    sem_ruido = re.sub(r"\bdia \d{1,2}\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", " ", sem_ruido)
    return list(_VALOR.findall(sem_ruido))


def valor_por_extenso(texto: str) -> str | None:
    """O maior trecho só de palavras que vira valor ("mil e duzentos"), se houver."""
    palavras = [p for p in normaliza(texto).split() if not any(c.isdigit() for c in p)]
    melhor: str | None = None
    for i in range(len(palavras)):
        for j in range(min(len(palavras), i + 8), i, -1):
            trecho = " ".join(palavras[i:j])
            if valores.interpreta(trecho).centavos:
                if melhor is None or len(trecho) > len(melhor):
                    melhor = trecho
                break
    return melhor


def tenta(texto: str) -> ExtracaoIA | None:
    t = normaliza(texto)
    palavras = t.split()
    bruto = " ".join(_sem_acento(texto.lower()).replace("r$", " ").split())
    if (
        not palavras
        or len(palavras) > LIMITE_PALAVRAS
        or "?" in texto
        or _FORA.search(t)
        or re.search(r"\d\s*k\b", bruto)
    ):
        return None
    achados = _valores_em_digitos(texto)
    if len(achados) > 1:
        return None
    if not achados:
        # Sem número nenhum: só "gastei no mercado" (pergunta o valor). Valor por extenso
        # ("gastei trinta no mercado") fica com a IA.
        verbo = (_VERBO_GASTO | _VERBO_GANHO) & set(palavras)
        if not verbo or valor_por_extenso(texto) is not None:
            return None
    return _monta(texto, palavras, achados[0] if achados else None)


def resgata(texto: str) -> ExtracaoIA | None:
    """Depois da IA: frase de gasto que ela não virou lançamento.

    Ex.: "gastei no mercado" (sem valor) ou "mil e duzentos de mercado esse mês já" lido
    como consulta. Só com UMA palavra-chave e sem cara de pergunta; o lançamento resgatado
    passa pelas mesmas pendências (valor, total acumulado → pergunta antes de registrar).
    """
    t = normaliza(texto)
    palavras = t.split()
    if not palavras or len(palavras) > LIMITE_RESGATE or "?" in texto or _PERGUNTA.search(t):
        return None
    if not (_VERBO_GASTO & set(palavras) or _TOTAL_ACUMULADO.search(t)):
        return None
    achados = _valores_em_digitos(texto)
    if len(achados) > 1:
        return None
    return _monta(texto, palavras, achados[0] if achados else valor_por_extenso(texto))


def _monta(texto: str, palavras: list[str], valor_texto: str | None) -> ExtracaoIA | None:
    t = " ".join(palavras)
    ganho = bool(_VERBO_GANHO & set(palavras)) or any(p in GANHOS for p in palavras)
    tabela = GANHOS if ganho else PALAVRAS
    achadas = {tabela[p] for p in palavras if p in tabela}
    ambiguo = any(p in AMBIGUOS for p in palavras)
    if len(achadas) > 1 or (not achadas and not ambiguo):
        return None  # sem palavra-chave (ou com duas): a IA entende melhor

    forma, cartao = forma_em(texto)
    parcelas_achadas = _PARCELAS.search(t)
    parcelas = int(parcelas_achadas.group(1)) if parcelas_achadas else None
    if parcelas is not None:
        forma = "credito"

    # Descrição só com o que o recibo ainda não mostra: sem valor, forma, parcelas e sem
    # repetir a categoria ("mercado 45 no pix" não vira "📝 mercado pix").
    sem_parcelas = _PARCELAS.sub(" ", t).split()
    categoria = next(iter(achadas)) if achadas and not ambiguo else None
    descartar = _VAZIAS | _VERBO_GASTO | _VERBO_GANHO | {categoria or ""}
    uteis = [
        p
        for p in sem_parcelas
        if p not in descartar and not _PAGAMENTO.fullmatch(p) and not p[0].isdigit()
    ]
    descricao = " ".join(uteis)[:40] or None
    item = LancamentoIA(
        tipo="ganho" if ganho else "gasto",
        valor_texto=valor_texto,
        data_texto=datas.expressao_em(texto),
        descricao=descricao,
        categoria=categoria,
        categorias_sugeridas=[],
        nova_categoria_sugerida=None,
        forma_pagamento=forma,  # type: ignore[arg-type]
        cartao=cartao,
        parcelas=parcelas if parcelas and 1 <= parcelas <= 72 else None,
        pode_ser_fixo=bool(_RECORRENTES & set(palavras)),
        duvida=None,
    )
    return ExtracaoIA(
        intencao="lancamentos",
        lancamentos=[item],
        correcao_campo=None,
        correcao_texto=None,
        pergunta=None,
    )

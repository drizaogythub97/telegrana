"""Atalho sem IA para mensagens simples (D038): "mercado 45,90 no pix", "uber 18".

Monta a MESMA estrutura que a IA devolveria (`ExtracaoIA`), para passar pelas mesmas
regras de `core.interpretacao` (categorias da conta, regras da pessoa, ambíguos que
perguntam, valores e datas no código). Na dúvida, devolve None e a IA decide.
"""

from __future__ import annotations

import re
import unicodedata

from telegrana.core import datas
from telegrana.core.extracao import ExtracaoIA, LancamentoIA
from telegrana.core.interpretacao import AMBIGUOS, normaliza

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


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def tenta(texto: str) -> ExtracaoIA | None:
    t = normaliza(texto)
    palavras = t.split()
    bruto = " ".join(_sem_acento(texto.lower()).replace("r$", " ").split())  # mantém , e .
    if (
        not palavras
        or len(palavras) > LIMITE_PALAVRAS
        or "?" in texto
        or _FORA.search(t)
        or re.search(r"\d\s*k\b", bruto)
    ):
        return None
    # Parcelas ("3x") e datas ("dia 5", "05/09") não podem ser confundidas com o valor.
    sem_ruido = _PARCELAS.sub(" ", bruto)
    sem_ruido = re.sub(r"\bdia \d{1,2}\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", " ", sem_ruido)
    valores = _VALOR.findall(sem_ruido)
    if len(valores) != 1:
        return None
    valor_texto = valores[0]

    ganho = bool(_VERBO_GANHO & set(palavras)) or any(p in GANHOS for p in palavras)
    tabela = GANHOS if ganho else PALAVRAS
    achadas = {tabela[p] for p in palavras if p in tabela}
    ambiguo = any(p in AMBIGUOS for p in palavras)
    if len(achadas) > 1 or (not achadas and not ambiguo):
        return None  # sem palavra-chave (ou com duas): a IA entende melhor

    forma, cartao = None, None
    for padrao, nome, banco in _FORMAS:
        achado = padrao.search(t)
        if achado:
            forma = nome
            cartao = achado.group(1) if banco == "_banco" else banco
            break
    parcelas_achadas = _PARCELAS.search(t)
    parcelas = int(parcelas_achadas.group(1)) if parcelas_achadas else None
    if parcelas is not None:
        forma = "credito"

    sem_vazias = " ".join(
        p for p in palavras if p not in {"no", "na", "de", "do", "da", "em", "o", "a", "reais"}
    )
    descricao = re.sub(r"\d[\d.,]*", "", sem_vazias).strip()[:40] or None
    item = LancamentoIA(
        tipo="ganho" if ganho else "gasto",
        valor_texto=valor_texto,
        data_texto=datas.expressao_em(texto),
        descricao=descricao,
        categoria=next(iter(achadas)) if achadas and not ambiguo else None,
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

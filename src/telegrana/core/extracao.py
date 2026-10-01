"""Contrato da IA de extração (PLANO 5, 8.3; D036, D037).

A IA só preenche ESTES campos, validados pelo Pydantic com `extra="forbid"`. Ela copia
os trechos de valor e de data como a pessoa falou; quem converte é o código
(`core.valores`, `core.datas`). Nada aqui vira SQL, comando ou decisão de acesso.
"""

from __future__ import annotations

from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

Intencao = Literal[
    "lancamentos",
    "correcao",
    "apagar_ultimo",
    "consulta",
    "pagar_fatura",
    "conversa",
    "fora_do_escopo",
]
Tipo = Literal["gasto", "ganho", "transferencia"]
Forma = Literal["pix", "debito", "dinheiro", "credito", "boleto", "poupanca"]
CampoCorrecao = Literal["valor", "data", "categoria", "forma_pagamento", "descricao"]


class LancamentoIA(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tipo: Tipo
    valor_texto: str | None = Field(max_length=60)
    data_texto: str | None = Field(max_length=60)
    descricao: str | None = Field(max_length=80)
    categoria: str | None = Field(max_length=40)
    categorias_sugeridas: list[str] = Field(max_length=3)
    nova_categoria_sugerida: str | None = Field(max_length=40)
    forma_pagamento: Forma | None
    cartao: str | None = Field(max_length=30)
    parcelas: int | None = Field(ge=1, le=72)
    pode_ser_fixo: bool
    duvida: str | None = Field(max_length=200)


class ExtracaoIA(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intencao: Intencao
    lancamentos: list[LancamentoIA] = Field(max_length=10)
    correcao_campo: CampoCorrecao | None
    correcao_texto: str | None = Field(max_length=80)
    pergunta: str | None = Field(max_length=200)


# ---------------------------------------------------------------------------
# JSON Schema para a saída estrita do provedor (Groq `strict: true`)
# Escrito à mão: todo campo obrigatório, `additionalProperties: false` em todo objeto,
# anuláveis como `["tipo", "null"]`; os limites (tamanhos, faixas) ficam no Pydantic.
# ---------------------------------------------------------------------------
def _texto_ou_nulo() -> dict[str, Any]:
    return {"type": ["string", "null"]}


def _enum_ou_nulo(tipo: Any) -> dict[str, Any]:
    return {"type": ["string", "null"], "enum": [*get_args(tipo), None]}


def _objeto(propriedades: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": propriedades,
        "required": list(propriedades),
        "additionalProperties": False,
    }


def esquema_json() -> dict[str, Any]:
    lancamento = _objeto(
        {
            "tipo": {"type": "string", "enum": list(get_args(Tipo))},
            "valor_texto": _texto_ou_nulo(),
            "data_texto": _texto_ou_nulo(),
            "descricao": _texto_ou_nulo(),
            "categoria": _texto_ou_nulo(),
            "categorias_sugeridas": {"type": "array", "items": {"type": "string"}},
            "nova_categoria_sugerida": _texto_ou_nulo(),
            "forma_pagamento": _enum_ou_nulo(Forma),
            "cartao": _texto_ou_nulo(),
            "parcelas": {"type": ["integer", "null"]},
            "pode_ser_fixo": {"type": "boolean"},
            "duvida": _texto_ou_nulo(),
        }
    )
    return _objeto(
        {
            "intencao": {"type": "string", "enum": list(get_args(Intencao))},
            "lancamentos": {"type": "array", "items": lancamento},
            "correcao_campo": _enum_ou_nulo(CampoCorrecao),
            "correcao_texto": _texto_ou_nulo(),
            "pergunta": _texto_ou_nulo(),
        }
    )

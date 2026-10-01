"""Conversão dos textos legais para o Telegraph."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from telegrana.infra import telegraph

LEGAL = Path(__file__).resolve().parents[2] / "legal"
TAGS_PERMITIDAS = {"h3", "h4", "p", "ul", "li", "blockquote", "b", "i", "code", "br", "a"}


def _tags(nos: list[Any]) -> set[str]:
    achadas: set[str] = set()
    for no in nos:
        if isinstance(no, dict):
            achadas.add(no["tag"])
            achadas |= _tags(no.get("children", []))
    return achadas


def _texto(nos: list[Any]) -> str:
    return "".join(no if isinstance(no, str) else _texto(no.get("children", [])) for no in nos)


def test_inline() -> None:
    assert telegraph.inline("a **b** *c* `d`") == [
        "a ",
        {"tag": "b", "children": ["b"]},
        " ",
        {"tag": "i", "children": ["c"]},
        " ",
        {"tag": "code", "children": ["d"]},
    ]


def test_tabela_vira_lista_com_rotulos() -> None:
    _, nos = telegraph.converte("# T\n\n| Dado | Para quê |\n|---|---|\n| Nome | **Avisos** |\n")
    assert nos == [
        {
            "tag": "ul",
            "children": [
                {
                    "tag": "li",
                    "children": [
                        {"tag": "b", "children": ["Nome"]},
                        {"tag": "br"},
                        {"tag": "i", "children": ["Para quê: "]},
                        {"tag": "b", "children": ["Avisos"]},
                    ],
                }
            ],
        }
    ]


@pytest.mark.parametrize("arquivo", ["termos-v1.md", "privacidade-v1.md"])
def test_textos_legais_convertem_dentro_dos_limites(arquivo: str) -> None:
    modelo = (LEGAL / arquivo).read_text(encoding="utf-8")
    assert "{{data_vigencia}}" in modelo
    assert "{{contato_admin}}" in modelo
    preenchido = modelo.replace("{{data_vigencia}}", "01/10/2026").replace(
        "{{contato_admin}}", "@exemplo"
    )
    titulo, nos = telegraph.converte(preenchido)
    assert titulo.endswith("versão 1")
    assert _tags(nos) <= TAGS_PERMITIDAS
    texto = _texto(nos)
    assert "**" not in texto
    assert "{{" not in texto
    assert "@exemplo" in texto
    assert len(json.dumps(nos, ensure_ascii=False).encode()) < telegraph.LIMITE_BYTES


def test_sem_titulo_e_recusado() -> None:
    with pytest.raises(ValueError, match="título"):
        telegraph.converte("só texto")

"""Entrada de emoji e nome de categoria."""

from __future__ import annotations

import pytest

from telegrana.core import categorias


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("🏋️ Academia", ("🏋️", "Academia")),
        ("Academia 🏋️", ("🏋️", "Academia")),
        ("  🐶🐱  Bichos   de casa ", ("🐶🐱", "Bichos de casa")),
        ("Academia", (None, "Academia")),
        ("👨‍👩‍👧 Família", ("👨‍👩‍👧", "Família")),
    ],
)
def test_separa_emoji(texto: str, esperado: tuple[str | None, str]) -> None:
    assert categorias.separa_emoji(texto) == esperado


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("academia", "Academia"),
        ("Pão de açúcar", "Pão de açúcar"),
        ("Casa/Reforma", "Casa/Reforma"),
        ("**negrito**", "Negrito"),
        ("", None),
        ("x" * 41, None),
        ("<script>", None),
        ("-começa com hífen", None),
    ],
)
def test_nome_valido(texto: str, esperado: str | None) -> None:
    assert categorias.nome_valido(texto) == esperado


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("🏋️", "🏋️"), (" 🍕 ", "🍕"), ("a", None), ("🍕 pizza", None), ("", None)],
)
def test_emoji_valido(texto: str, esperado: str | None) -> None:
    assert categorias.emoji_valido(texto) == esperado


def test_padroes_em_python_iguais_aos_da_migracao() -> None:
    import re
    from pathlib import Path

    sql = (
        Path(__file__).resolve().parents[2] / "src/telegrana/infra/migrations/0003_lancamentos.sql"
    ).read_text(encoding="utf-8")
    da_migracao = re.findall(r"\('(expense|income)',\s*'(\w+)',\s*'([^']+)',\s*'([^']+)'", sql)
    assert tuple(da_migracao) == categorias.PADROES

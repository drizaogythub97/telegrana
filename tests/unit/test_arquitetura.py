"""Regras de arquitetura verificadas no código (CLAUDE.md, regra de ouro 10).

O núcleo é agnóstico de canal: o Telegram (e, na S9, o WhatsApp) são adaptadores.
Estes testes leem os imports de cada módulo (sem executá-los) e falham se uma
camada depender de outra que não deveria.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "telegrana"

# camada -> prefixos de import proibidos nela
PROIBIDOS: dict[str, tuple[str, ...]] = {
    "core": ("telegrana.channels", "telegrana.ai", "telegram", "telethon", "httpx"),
    "ai": ("telegrana.channels", "telegram", "telethon"),
    "exports": ("telegrana.channels", "telegram", "telethon"),
}


def _imports(arquivo: Path) -> list[str]:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
    nomes: list[str] = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes.extend(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            nomes.append(no.module)
    return nomes


@pytest.mark.parametrize("camada", sorted(PROIBIDOS))
def test_camada_nao_importa_o_que_nao_deve(camada: str) -> None:
    violacoes = [
        f"{arquivo.relative_to(SRC)} importa {nome}"
        for arquivo in (SRC / camada).rglob("*.py")
        for nome in _imports(arquivo)
        if nome.startswith(PROIBIDOS[camada])
    ]
    assert not violacoes, "Violação de arquitetura:\n" + "\n".join(violacoes)


def test_camadas_existem() -> None:
    # Se uma camada for renomeada, o teste acima passaria sem verificar nada.
    for camada in PROIBIDOS:
        assert (SRC / camada / "__init__.py").is_file(), f"camada {camada} sumiu"

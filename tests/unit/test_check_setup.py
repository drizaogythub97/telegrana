"""Testes do scripts/check_setup.py — principalmente: nenhum segredo pode sair na tela."""

import importlib.util
import struct
import sys
import zlib
from pathlib import Path
from types import ModuleType

import pytest

RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def cs() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_setup", RAIZ / "scripts" / "check_setup.py"
    )
    assert spec is not None
    assert spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["check_setup"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def test_redact_mascara_todos_os_segredos(cs: ModuleType) -> None:
    rep = cs.Reporter()
    rep.add_secret("gsk_segredo_muito_longo_123")
    rep.add_secret("gsk_segredo")  # prefixo de outro segredo: o mais longo precisa sair inteiro
    texto = rep.redact("chave=gsk_segredo_muito_longo_123 e outra=gsk_segredo")
    assert "gsk_segredo" not in texto
    assert texto.count("«oculto»") == 2


def test_redact_ignora_valores_curtos(cs: ModuleType) -> None:
    rep = cs.Reporter()
    rep.add_secret("abc")  # curto demais: mascarar causaria falsos positivos em qualquer texto
    rep.add_secret(None)
    assert rep.redact("abc") == "abc"


def test_saida_do_reporter_nunca_mostra_segredo(
    cs: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    rep = cs.Reporter()
    rep.add_secret("123456789:AAsegredo-do-bot")
    rep.fail("token 123456789:AAsegredo-do-bot recusado", "dica com 123456789:AAsegredo-do-bot")
    saida = capsys.readouterr().out
    assert "AAsegredo" not in saida
    assert rep.counts["falha"] == 1


def test_load_env(cs: ModuleType, tmp_path: Path) -> None:
    arquivo = tmp_path / ".env.local"
    arquivo.write_text(
        "# comentário\n\nA=1\nB = dois \nC=\"com aspas\"\nD='simples'\nSEM_IGUAL\nE=\n",
        encoding="utf-8",
    )
    env = cs.load_env(arquivo)
    assert env == {"A": "1", "B": "dois", "C": "com aspas", "D": "simples", "E": ""}


def test_segredos_do_modelo_estao_na_lista_de_mascaramento(cs: ModuleType) -> None:
    # Toda variável marcada "SEGREDO" no .env.local.example precisa ser mascarada.
    linhas = (RAIZ / ".env.local.example").read_text(encoding="utf-8").splitlines()
    segredos: set[str] = set()
    marcado = False
    for linha in linhas:
        if linha.startswith("#"):
            marcado = marcado or "SEGREDO" in linha
            continue
        if "=" in linha and marcado:
            segredos.add(linha.split("=", 1)[0])
        if not linha.strip() or "=" in linha:
            marcado = False
    assert segredos, "nenhuma variável marcada como SEGREDO: o teste perdeu o sentido"
    assert segredos <= set(cs.SECRET_KEYS), (
        f"faltam em SECRET_KEYS: {segredos - set(cs.SECRET_KEYS)}"
    )


def test_png_size(cs: ModuleType, tmp_path: Path) -> None:
    def chunk(tipo: bytes, dados: bytes) -> bytes:
        return (
            struct.pack(">I", len(dados))
            + tipo
            + dados
            + struct.pack(">I", zlib.crc32(tipo + dados))
        )

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 640, 480, 8, 2, 0, 0, 0))
    (tmp_path / "a.png").write_bytes(png)
    (tmp_path / "b.png").write_bytes(b"nao e png" * 4)
    assert cs.png_size(tmp_path / "a.png") == (640, 480)
    assert cs.png_size(tmp_path / "b.png") is None

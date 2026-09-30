#!/usr/bin/env python3
"""Monta o pacote das Lambdas em .build/lambda para Linux arm64 / Python 3.14 (D031).

Funciona em qualquer máquina (inclusive Windows): o uv instala os wheels da plataforma
de destino (`--python-platform`), só binários, conferindo os hashes do uv.lock.

Uso: uv run python scripts/build_lambda.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BUILD = RAIZ / ".build"
DESTINO = BUILD / "lambda"
PLATAFORMA = "aarch64-manylinux_2_28"  # Lambda arm64 (Amazon Linux 2023, glibc 2.34)
PYTHON = "3.14"


def _uv(*args: str) -> None:
    # Dentro de `uv run`, a variável UV aponta para o executável do próprio uv.
    uv = os.environ.get("UV") or shutil.which("uv")
    if not uv:
        raise SystemExit("uv não encontrado: rode com `uv run python scripts/build_lambda.py`")
    subprocess.run([uv, *args], check=True, cwd=RAIZ)


def main() -> int:
    shutil.rmtree(DESTINO, ignore_errors=True)
    DESTINO.mkdir(parents=True)
    requisitos = BUILD / "requirements-lambda.txt"
    _uv(
        "export", "--locked", "--no-dev", "--no-emit-project",
        "--format", "requirements-txt", "--output-file", str(requisitos), "--quiet",
    )  # fmt: skip
    _uv(
        "pip", "install", "--requirement", str(requisitos), "--target", str(DESTINO),
        "--python-platform", PLATAFORMA, "--python-version", PYTHON,
        "--only-binary", ":all:", "--require-hashes", "--no-deps", "--quiet",
    )  # fmt: skip
    shutil.copytree(
        RAIZ / "src" / "telegrana",
        DESTINO / "telegrana",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    tamanho = sum(f.stat().st_size for f in DESTINO.rglob("*") if f.is_file())
    print(f"pacote pronto em {DESTINO.relative_to(RAIZ)} ({tamanho / 1_048_576:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

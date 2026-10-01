#!/usr/bin/env python3
"""Envia ou baixa o conjunto de avaliação do bucket privado (D016, D036).

    uv run python scripts/avaliacao_dados.py enviar   # tests/eval/data/ → bucket
    uv run python scripts/avaliacao_dados.py baixar   # bucket → tests/eval/data/

Bucket: saída `EvalBucketName` da stack telegrana-bootstrap. Nada deste conjunto entra
no Git; o script lista só nomes de arquivos e tamanhos.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import boto3

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "tests" / "eval" / "data"
REGIAO = "us-east-1"
ARQUIVOS = ("gabarito.jsonl", "mensagens.txt", "audios.txt")


def _sessao() -> object:
    return boto3.Session(
        profile_name=os.environ.get("AWS_PROFILE", "telegrana-sdk"), region_name=REGIAO
    )


def _bucket(sessao: object) -> str:
    cf = sessao.client("cloudformation")  # type: ignore[attr-defined]
    saidas = cf.describe_stacks(StackName="telegrana-bootstrap")["Stacks"][0]["Outputs"]
    return str(next(s["OutputValue"] for s in saidas if s["OutputKey"] == "EvalBucketName"))


def _locais() -> list[Path]:
    arquivos = [PASTA / nome for nome in ARQUIVOS if (PASTA / nome).exists()]
    audios = PASTA / "audios"
    if audios.is_dir():
        arquivos += sorted(p for p in audios.iterdir() if p.is_file())
    return arquivos


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("acao", choices=["enviar", "baixar"])
    args = parser.parse_args()
    sessao = _sessao()
    bucket = _bucket(sessao)
    s3 = sessao.client("s3")  # type: ignore[attr-defined]
    if args.acao == "enviar":
        for arquivo in _locais():
            chave = arquivo.relative_to(PASTA).as_posix()
            s3.upload_file(str(arquivo), bucket, chave)
            print(f"  enviado: {chave} ({arquivo.stat().st_size} bytes)")
        return 0
    paginas = s3.get_paginator("list_objects_v2").paginate(Bucket=bucket)
    for pagina in paginas:
        for objeto in pagina.get("Contents", []):
            destino = PASTA / objeto["Key"]
            destino.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, objeto["Key"], str(destino))
            print(f"  baixado: {objeto['Key']} ({objeto['Size']} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

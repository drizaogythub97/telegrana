#!/usr/bin/env python3
"""Gera o par de chaves do backup (S8, D052). QUEM RODA É O ADRIANO.

Uso (na raiz do projeto, depois do `aws login --profile telegrana`):
    uv run python scripts/backup_chave.py "D:\\pendrive\\telegrana-backup-chave-privada.txt"

- A CHAVE PRIVADA vai só para o arquivo indicado (fora do repositório). Guarde-a offline
  (pendrive, gerenciador de senhas) e apague a cópia do computador. Sem ela, nenhum backup
  abre — nem por você, nem pelo agente. Perdeu = os backups antigos ficam ilegíveis
  (gere outra e os próximos voltam a funcionar).
- A chave PÚBLICA (não é segredo) vai para o SSM em /telegrana/{dev,prod}/backup/public_key,
  de onde a Lambda de backup cifra os arquivos.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import boto3

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from telegrana.infra import backup  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    destino = Path(sys.argv[1]).expanduser().resolve()
    if RAIZ in destino.parents:
        print("Grave a chave privada FORA da pasta do projeto (ex.: num pendrive).")
        return 2
    if destino.exists():
        print(f"{destino} já existe: escolha outro nome (não sobrescrevo chave).")
        return 2
    privada, publica = backup.gera_chaves()
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        f"Telegrana — chave PRIVADA do backup (X25519, base64). Guarde offline.\n{privada}\n",
        encoding="utf-8",
    )
    sessao = boto3.Session(profile_name=os.environ.get("AWS_PROFILE", "telegrana-sdk"))
    ssm = sessao.client("ssm", region_name="us-east-1")
    for env in ("dev", "prod"):
        ssm.put_parameter(
            Name=f"/telegrana/{env}/backup/public_key",
            Value=publica,
            Type="String",
            Overwrite=True,
            Tier="Standard",
        )
    print(f"Chave privada gravada em: {destino}")
    print("Chave pública gravada no SSM (dev e prod).")
    print("Agora: copie o arquivo da chave privada para um lugar offline e apague esta cópia.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

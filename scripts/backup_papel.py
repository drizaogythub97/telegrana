#!/usr/bin/env python3
"""Liga o login do papel `telegrana_backup` e grava a URL dele no SSM (S8, D052).

Uso (na raiz do projeto):
    uv run python scripts/backup_papel.py dev
    uv run python scripts/backup_papel.py prod

- Usa NEON_OWNER_URL_<ENV> do .env.local (papel dono) só para criar/rotacionar o papel.
- Senha nova a cada execução (rotação); a URL vai para /telegrana/<env>/neon/backup_url
  (SecureString). Nada é exibido.
- Rode ANTES do deploy da migração 0015 nos bancos que já existem (dev e prod): a
  migração concede leitura a um papel que precisa existir.
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit

import boto3

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "scripts"))

from db_bootstrap import _com_usuario, _le_env  # noqa: E402
from telegrana.infra import bootstrap, db  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"dev", "prod"}:
        print("uso: scripts/backup_papel.py {dev|prod}")
        return 2
    env = sys.argv[1]
    owner_url = _le_env().get(f"NEON_OWNER_URL_{env.upper()}", "")
    if not owner_url:
        print(f"NEON_OWNER_URL_{env.upper()} em branco no .env.local")
        return 1
    database = urlsplit(owner_url).path.lstrip("/") or "neondb"
    senha = secrets.token_urlsafe(32)
    with db.connect(owner_url, autocommit=True, application_name="telegrana-bootstrap") as adm:
        bootstrap.bootstrap_backup_role(adm, database, senha)
    sessao = boto3.Session(profile_name=os.environ.get("AWS_PROFILE", "telegrana-sdk"))
    sessao.client("ssm", region_name="us-east-1").put_parameter(
        Name=f"/telegrana/{env}/neon/backup_url",
        Value=_com_usuario(owner_url, bootstrap.ROLE_BACKUP, senha),
        Type="SecureString",
        Overwrite=True,
        Tier="Standard",
    )
    print(f"papel de backup pronto em {env}; URL gravada no SSM (valor não exibido)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Grava os segredos do Telegrana no SSM Parameter Store (SecureString, chave aws/ssm).

Uso (na raiz, com `aws login --profile telegrana` ativo):
    uv run python scripts/ssm_setup.py
    uv run python scripts/ssm_setup.py --rotacionar-webhook      # novo segredo do webhook
    uv run python scripts/ssm_setup.py --rotacionar-banco-prod   # novas senhas dos papéis em prod

Parâmetros (nunca exibidos):
    /telegrana/admin_telegram_id                  String
    /telegrana/<env>/telegram/bot_token           SecureString  (do .env.local)
    /telegrana/<env>/telegram/webhook_secret      SecureString  (gerado; mantido se já existir)
    /telegrana/<env>/neon/app_url                 SecureString  (dev: do .env.local; prod: bootstrap)
    /telegrana/<env>/neon/migrator_url            SecureString
    /telegrana/<env>/phone/hmac_pepper            SecureString  (gerado uma vez; NUNCA rotacionar:
                                                  invalidaria a recuperação por telefone)

Produção: os papéis do banco são criados aqui com o dono (NEON_OWNER_URL_PROD, só nesta
máquina) e as senhas vão direto para o SSM, sem passar pelo .env.local nem pela tela.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "scripts"))

import boto3  # noqa: E402

from db_bootstrap import _com_usuario, _le_env  # noqa: E402
from telegrana.infra import bootstrap, db  # noqa: E402

REGIAO = "us-east-1"


def _ssm() -> object:
    sessao = boto3.Session(
        profile_name=os.environ.get("AWS_PROFILE", "telegrana-sdk"), region_name=REGIAO
    )
    return sessao.client("ssm")


def _existe(ssm: object, nome: str) -> bool:
    try:
        ssm.get_parameter(Name=nome)  # type: ignore[attr-defined]
    except ssm.exceptions.ParameterNotFound:  # type: ignore[attr-defined]
        return False
    return True


def _grava(ssm: object, nome: str, valor: str, *, segredo: bool = True) -> None:
    ssm.put_parameter(  # type: ignore[attr-defined]
        Name=nome,
        Value=valor,
        Type="SecureString" if segredo else "String",
        Overwrite=True,
        Tier="Standard",
    )
    print(f"  gravado: {nome}")


def _banco_prod(ssm: object, env: dict[str, str], rotacionar: bool) -> None:
    base = "/telegrana/prod/neon"
    if not rotacionar and _existe(ssm, f"{base}/app_url") and _existe(ssm, f"{base}/migrator_url"):
        print(
            "  banco prod: papéis já configurados (use --rotacionar-banco-prod para trocar as senhas)"
        )
        return
    owner_url = env.get("NEON_OWNER_URL_PROD", "")
    if not owner_url:
        raise SystemExit("NEON_OWNER_URL_PROD em branco no .env.local")
    database = urlsplit(owner_url).path.lstrip("/") or "neondb"
    senhas = {"migrator": secrets.token_urlsafe(32), "app": secrets.token_urlsafe(32)}
    with db.connect(owner_url, autocommit=True, application_name="telegrana-bootstrap") as adm:
        bootstrap.bootstrap_roles(
            adm, database, migrator_password=senhas["migrator"], app_password=senhas["app"]
        )
    print("  banco prod: papéis criados/rotacionados")
    _grava(
        ssm,
        f"{base}/migrator_url",
        _com_usuario(owner_url, bootstrap.ROLE_MIGRATOR, senhas["migrator"]),
    )
    _grava(ssm, f"{base}/app_url", _com_usuario(owner_url, bootstrap.ROLE_APP, senhas["app"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rotacionar-webhook", action="store_true")
    parser.add_argument("--rotacionar-banco-prod", action="store_true")
    args = parser.parse_args()

    env = _le_env()
    ssm = _ssm()

    admin = env.get("ADMIN_TELEGRAM_ID", "")
    if not admin.isdigit():
        raise SystemExit("ADMIN_TELEGRAM_ID inválido no .env.local")
    print("geral")
    _grava(ssm, "/telegrana/admin_telegram_id", admin, segredo=False)

    for ambiente in ("dev", "prod"):
        print(ambiente)
        base = f"/telegrana/{ambiente}"
        token = env.get(f"TELEGRAM_BOT_TOKEN_{ambiente.upper()}", "")
        if not token:
            raise SystemExit(f"TELEGRAM_BOT_TOKEN_{ambiente.upper()} em branco")
        _grava(ssm, f"{base}/telegram/bot_token", token)

        nome_segredo = f"{base}/telegram/webhook_secret"
        if args.rotacionar_webhook or not _existe(ssm, nome_segredo):
            _grava(
                ssm, nome_segredo, secrets.token_urlsafe(48)
            )  # A-Z a-z 0-9 _ - (aceito pelo Telegram)
        else:
            print(f"  mantido: {nome_segredo}")

        nome_pepper = f"{base}/phone/hmac_pepper"
        if _existe(ssm, nome_pepper):
            print(f"  mantido: {nome_pepper}")
        else:
            _grava(ssm, nome_pepper, secrets.token_urlsafe(32))  # 32 bytes em base64url

        if ambiente == "dev":
            for chave, nome in (
                ("NEON_APP_URL_DEV", "app_url"),
                ("NEON_MIGRATOR_URL_DEV", "migrator_url"),
            ):
                if not env.get(chave):
                    raise SystemExit(f"{chave} em branco: rode antes scripts/db_bootstrap.py dev")
                _grava(ssm, f"{base}/neon/{nome}", env[chave])
        else:
            _banco_prod(ssm, env, args.rotacionar_banco_prod)
    return 0


if __name__ == "__main__":
    sys.exit(main())

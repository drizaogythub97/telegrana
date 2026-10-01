#!/usr/bin/env python3
"""Tarefas de deploy que leem segredos do SSM sem exibi-los (usadas localmente e no CI).

    uv run python scripts/deploy_tasks.py migrar --env dev
    uv run python scripts/deploy_tasks.py webhook --env dev     # registra a Function URL no Telegram
    uv run python scripts/deploy_tasks.py webhook-info --env dev

Credenciais AWS: no CI, as do OIDC (variáveis de ambiente); localmente, o perfil
`telegrana-sdk` (AWS_PROFILE).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import boto3  # noqa: E402

from telegrana.channels.telegram import webhook  # noqa: E402
from telegrana.channels.telegram.api import TelegramAPI  # noqa: E402
from telegrana.infra import db, migrate  # noqa: E402

REGIAO = "us-east-1"
# Teto de conexões simultâneas do Telegram (a conta só tem 5 Lambdas simultâneas — D023).
MAX_CONNECTIONS = 3


def _sessao() -> Any:
    perfil = os.environ.get("AWS_PROFILE")
    if not perfil and not os.environ.get("AWS_ACCESS_KEY_ID"):
        perfil = "telegrana-sdk"
    return boto3.Session(profile_name=perfil, region_name=REGIAO)


def _segredo(sessao: Any, nome: str) -> str:
    valor = sessao.client("ssm").get_parameter(Name=nome, WithDecryption=True)["Parameter"]["Value"]
    return str(valor)


def _url_do_bot(sessao: Any, env: str) -> str:
    saidas = sessao.client("cloudformation").describe_stacks(StackName=f"telegrana-{env}")[
        "Stacks"
    ][0]["Outputs"]
    return str(next(s["OutputValue"] for s in saidas if s["OutputKey"] == "BotFunctionUrl"))


def migrar(sessao: Any, env: str) -> None:
    url = _segredo(sessao, f"/telegrana/{env}/neon/migrator_url")
    with db.connect(url, application_name="telegrana-deploy") as conn:
        aplicadas = migrate.migrate(conn)
    print(f"[{env}] migrações aplicadas: {aplicadas or 'nenhuma (em dia)'}")


def registrar_webhook(sessao: Any, env: str) -> None:
    api = TelegramAPI(_segredo(sessao, f"/telegrana/{env}/telegram/bot_token"))
    api.set_webhook(
        _url_do_bot(sessao, env),
        secret_token=_segredo(sessao, f"/telegrana/{env}/telegram/webhook_secret"),
        allowed_updates=webhook.ALLOWED_UPDATES,
        max_connections=MAX_CONNECTIONS,
        drop_pending_updates=True,
    )
    print(f"[{env}] webhook registrado (max_connections={MAX_CONNECTIONS}, pendentes descartados)")


def info_webhook(sessao: Any, env: str) -> None:
    info = TelegramAPI(_segredo(sessao, f"/telegrana/{env}/telegram/bot_token")).get_webhook_info()
    esperado = _url_do_bot(sessao, env)
    print(f"[{env}] URL confere com a stack: {info.get('url') == esperado}")
    print(
        f"[{env}] pendentes: {info.get('pending_update_count')} | max_connections: {info.get('max_connections')}"
    )
    print(
        f"[{env}] tipos: {info.get('allowed_updates')} | último erro: {info.get('last_error_message') or 'nenhum'}"
    )


def verificar(sessao: Any, env: str) -> None:
    """Invoca as Lambdas publicadas: prova que o código importa e a configuração carrega.

    O bot recebe uma requisição sem o segredo e precisa recusar com 401; a rotina roda a
    limpeza (idempotente). Qualquer erro de import ou de configuração derruba o deploy.
    """
    cliente = sessao.client("lambda")
    evento = {
        "requestContext": {"http": {"method": "POST"}},
        "headers": {"Content-Type": "application/json"},
        "body": '{"update_id": 0}',
        "isBase64Encoded": False,
    }
    for funcao, entrada, confere in (
        (f"telegrana-{env}-bot", evento, lambda r: r.get("statusCode") == 401),
        (f"telegrana-{env}-rotinas", {}, lambda r: isinstance(r, dict)),
    ):
        resposta = cliente.invoke(FunctionName=funcao, Payload=json.dumps(entrada).encode())
        corpo = json.loads(resposta["Payload"].read() or b"null")
        if resposta.get("FunctionError") or not confere(corpo):
            tipo = corpo.get("errorType") if isinstance(corpo, dict) else None
            raise SystemExit(
                f"[{env}] {funcao} falhou na verificação ({tipo or 'resposta inesperada'})"
            )
        print(f"[{env}] {funcao}: ok")


def main() -> int:
    parser = argparse.ArgumentParser(description="Tarefas de deploy do Telegrana.")
    parser.add_argument("tarefa", choices=["migrar", "webhook", "webhook-info", "verificar"])
    parser.add_argument("--env", choices=["dev", "prod"], required=True)
    args = parser.parse_args()
    sessao = _sessao()
    tarefas = {
        "migrar": migrar,
        "webhook": registrar_webhook,
        "webhook-info": info_webhook,
        "verificar": verificar,
    }
    tarefas[args.tarefa](sessao, args.env)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Configuração da Lambda: variáveis de ambiente + segredos do SSM (PLANO 8.4).

Os segredos são lidos uma vez por ambiente de execução (cold start) e ficam só em
memória. `repr=False` impede que apareçam em logs ou mensagens de erro.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

# nome do campo -> caminho do parâmetro dentro de /telegrana/<env>/
PARAMETROS = {
    "telegram_bot_token": "telegram/bot_token",  # nosec B105 — caminho no SSM, não o valor
    "telegram_webhook_secret": "telegram/webhook_secret",  # nosec B105 — caminho no SSM
    "database_url": "neon/app_url",
    "phone_hmac_pepper": "phone/hmac_pepper",
    "legal_termos": "legal/termos",  # JSON {versao, url, sha256} (scripts/publicar_legal.py)
    "legal_privacidade": "legal/privacidade",
    "admin_contact": "admin/contact",
}
AMBIENTES = frozenset({"dev", "prod"})

type Fetcher = Callable[[list[str]], dict[str, str]]


class ConfigError(RuntimeError):
    """Configuração ausente ou inválida (a mensagem nunca contém valores)."""


@dataclass(frozen=True, slots=True)
class Settings:
    env: str
    admin_telegram_id: int
    telegram_bot_token: str = field(repr=False)
    telegram_webhook_secret: str = field(repr=False)
    database_url: str = field(repr=False)
    phone_hmac_pepper: str = field(repr=False)
    legal_termos: str = ""
    legal_privacidade: str = ""
    admin_contact: str = ""


def ssm_fetch(nomes: list[str]) -> dict[str, str]:
    """Lê SecureStrings do SSM (boto3 do runtime da Lambda)."""
    import boto3  # importado aqui: só existe no runtime da Lambda e no ambiente de dev

    resposta = boto3.client("ssm").get_parameters(Names=nomes, WithDecryption=True)
    if resposta.get("InvalidParameters"):
        raise ConfigError(f"parâmetros ausentes no SSM: {sorted(resposta['InvalidParameters'])}")
    return {p["Name"]: p["Value"] for p in resposta["Parameters"]}


def load_settings(fetch: Fetcher = ssm_fetch, environ: Mapping[str, str] = os.environ) -> Settings:
    env = environ.get("TELEGRANA_ENV", "")
    if env not in AMBIENTES:
        raise ConfigError("TELEGRANA_ENV precisa ser dev ou prod")
    admin = environ.get("ADMIN_TELEGRAM_ID", "")
    if not admin.isdigit():
        raise ConfigError("ADMIN_TELEGRAM_ID ausente ou inválido")
    nomes = {campo: f"/telegrana/{env}/{caminho}" for campo, caminho in PARAMETROS.items()}
    valores = fetch(list(nomes.values()))
    faltando = [nome for nome in nomes.values() if not valores.get(nome)]
    if faltando:
        raise ConfigError(f"parâmetros vazios no SSM: {faltando}")
    return Settings(
        env=env,
        admin_telegram_id=int(admin),
        **{campo: valores[nome] for campo, nome in nomes.items()},
    )

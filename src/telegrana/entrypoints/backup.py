"""Lambda `backup`: domingo, 03:00 (São Paulo), só em produção (S8, D052).

Lê o banco com o papel `telegrana_backup` (só leitura), cifra com a chave pública do
backup e manda o arquivo para o chat do admin. Lê do SSM só o que usa: a URL do papel de
backup, o token do bot e a chave pública. O log tem só números (tabelas, linhas, bytes).
"""

from __future__ import annotations

import html
import logging
import os
from typing import Any

from telegrana.channels.telegram.api import TelegramAPI
from telegrana.core.contexto import agora
from telegrana.infra import backup, config, db, logs

logs.configure()
log = logging.getLogger("telegrana.backup")

PARAMETROS = {
    "url": "neon/backup_url",
    "token": "telegram/bot_token",  # nosec B105 — caminho no SSM, não o valor
    "publica": "backup/public_key",
}


def _segredos(env: str, fetch: config.Fetcher) -> dict[str, str]:
    nomes = {campo: f"/telegrana/{env}/{caminho}" for campo, caminho in PARAMETROS.items()}
    valores = fetch(list(nomes.values()))
    faltando = [nome for nome in nomes.values() if not valores.get(nome)]
    if faltando:
        raise config.ConfigError(f"parâmetros vazios no SSM: {faltando}")
    return {campo: valores[nome] for campo, nome in nomes.items()}


def legenda(env: str, pacote: backup.Pacote, tamanho: int) -> str:
    linhas = sum(pacote.tabelas.values())
    return (
        f"🗄️ <b>Backup semanal</b> ({html.escape(env)}) · esquema {pacote.esquema}\n"
        f"{len(pacote.tabelas)} tabelas · {linhas} linhas · {tamanho / 1024:.0f} KB\n"
        "Cifrado: só abre com a sua chave privada (scripts/backup_abre.py)."
    )


def handler(
    event: dict[str, Any], context: object, fetch: config.Fetcher = config.ssm_fetch
) -> dict[str, Any]:
    env = os.environ.get("TELEGRANA_ENV", "")
    admin = os.environ.get("ADMIN_TELEGRAM_ID", "")
    if env not in config.AMBIENTES or not admin.isdigit():
        raise config.ConfigError("TELEGRANA_ENV ou ADMIN_TELEGRAM_ID inválidos")
    segredos = _segredos(env, fetch)
    momento = agora()
    with db.connect(segredos["url"], application_name="telegrana-backup") as conn:
        pacote = backup.exporta(conn, momento)
    cifrado = backup.cifra(pacote.dados, segredos["publica"])
    nome = f"telegrana-{env}-backup-{momento:%Y-%m-%d}.tgbk"
    TelegramAPI(segredos["token"]).envia_documento(
        int(admin),
        nome,
        cifrado,
        "application/octet-stream",
        legenda=legenda(env, pacote, len(cifrado)),
    )
    resumo = {
        "tabelas": len(pacote.tabelas),
        "linhas": sum(pacote.tabelas.values()),
        "bytes": len(cifrado),
        "esquema": pacote.esquema,
    }
    log.info("backup.enviado", extra=resumo)
    return resumo

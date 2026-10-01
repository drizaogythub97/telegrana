"""Lambda `rotinas`: disparada pelo EventBridge Scheduler às 09:00 e 20:00 (São Paulo).

Limpeza de retenção (PLANO 3.2, 3.3 e 8.5; Política de Privacidade, seção 8). Lembretes e resumos chegam na S4/S6.
"""

from __future__ import annotations

import logging
from typing import Any

from telegrana.core import repositorio
from telegrana.infra import config, db, logs

logs.configure()
log = logging.getLogger("telegrana.rotinas")

RETENCAO_UPDATES = "7 days"
RETENCAO_TENTATIVAS = "1 day"
DIAS_CADASTRO_INCOMPLETO = 7


def limpa(conn: db.Connection) -> dict[str, int]:
    with conn.transaction():
        updates = conn.execute(
            "delete from telegrana.processed_updates where processed_at < now() - %s::interval",
            (RETENCAO_UPDATES,),
        ).rowcount
        pedidos = conn.execute(
            "delete from telegrana.access_requests where expires_at < now()"
        ).rowcount
        tentativas = conn.execute(
            "delete from telegrana.auth_attempts where updated_at < now() - %s::interval"
            " and (locked_until is null or locked_until < now())",
            (RETENCAO_TENTATIVAS,),
        ).rowcount
    cadastros = repositorio.limpa_cadastros_velhos(conn, DIAS_CADASTRO_INCOMPLETO)
    return {
        "updates_apagados": updates,
        "pedidos_expirados_apagados": pedidos,
        "tentativas_apagadas": tentativas,
        "cadastros_incompletos_apagados": cadastros,
    }


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    settings = config.load_settings()
    with db.connect(settings.database_url, application_name="telegrana-rotinas") as conn:
        resultado = limpa(conn)
    log.info("rotinas.limpeza", extra=resultado)
    return resultado

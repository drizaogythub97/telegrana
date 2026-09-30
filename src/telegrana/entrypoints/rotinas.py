"""Lambda `rotinas`: disparada pelo EventBridge Scheduler às 09:00 e 20:00 (São Paulo).

S1.3: limpeza de retenção (PLANO 3.2 e 8.5). Lembretes e resumos chegam na S4/S6.
"""

from __future__ import annotations

import logging
from typing import Any

from telegrana.infra import config, db, logs

logs.configure()
log = logging.getLogger("telegrana.rotinas")

RETENCAO_UPDATES = "7 days"


def limpa(conn: db.Connection) -> dict[str, int]:
    with conn.transaction():
        updates = conn.execute(
            "delete from telegrana.processed_updates where processed_at < now() - %s::interval",
            (RETENCAO_UPDATES,),
        ).rowcount
        pedidos = conn.execute(
            "delete from telegrana.access_requests where expires_at < now()"
        ).rowcount
    return {"updates_apagados": updates, "pedidos_expirados_apagados": pedidos}


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    settings = config.load_settings()
    with db.connect(settings.database_url, application_name="telegrana-rotinas") as conn:
        resultado = limpa(conn)
    log.info("rotinas.limpeza", extra=resultado)
    return resultado

"""Lambda `rotinas`: disparada pelo EventBridge Scheduler às 09:00 e 20:00 (São Paulo).

Lembretes dos fixos (S4.2, PLANO 4.4) e limpeza de retenção (PLANO 3.2, 3.3 e 8.5;
Política de Privacidade, seção 8). Resumos chegam na S6.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from telegrana.channels.telegram import adaptador
from telegrana.channels.telegram.api import TelegramAPI
from telegrana.core import lembretes, repositorio
from telegrana.core.contexto import FUSO, agora
from telegrana.core.mensagens import Resultado
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
    with conn.transaction():
        row = conn.execute(
            "select o_drafts, o_refs, o_sends from telegrana.purge_account_temporaries()"
        ).fetchone()
    rascunhos, refs, envios = (row[0], row[1], row[2]) if row else (0, 0, 0)
    return {
        "updates_apagados": updates,
        "pedidos_expirados_apagados": pedidos,
        "tentativas_apagadas": tentativas,
        "cadastros_incompletos_apagados": cadastros,
        "rascunhos_vencidos_apagados": rascunhos,
        "vinculos_de_recibo_apagados": refs,
        "lembretes_antigos_apagados": envios,
    }


def lembra(
    conn: db.Connection, api: TelegramAPI, momento: datetime, admin_id: int
) -> dict[str, int]:
    """Calcula e envia os lembretes do horário. Cada envio é independente (quem bloqueou o
    bot não impede os outros); o registro do envio já foi gravado antes (nunca repete)."""
    saidas, contas_com_falha = lembretes.da_rotina(conn, adaptador.CANAL, momento)
    falhas = 0
    for saida in saidas:
        origem = adaptador.Origem(chat_id=int(saida.destino or 0))
        falhas += adaptador.executa(api, Resultado(saidas=[saida]), origem, admin_id)[0]
    return {
        "lembretes": len(saidas),
        "lembretes_nao_entregues": falhas,
        "contas_com_falha": contas_com_falha,
    }


def _momento(event: dict[str, Any], env: str) -> datetime:
    """Agora, em São Paulo. Só em dev dá para simular outro momento (roteiro de testes):
    `{"momento": "2026-10-09T09:00"}`."""
    simulado = event.get("momento") if isinstance(event, dict) else None
    if env == "dev" and isinstance(simulado, str):
        return datetime.fromisoformat(simulado).replace(tzinfo=FUSO)
    return agora()


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    settings = config.load_settings()
    api = TelegramAPI(settings.telegram_bot_token)
    momento = _momento(event, settings.env)
    with db.connect(settings.database_url, application_name="telegrana-rotinas") as conn:
        enviados = lembra(conn, api, momento, settings.admin_telegram_id)
        log.info("rotinas.lembretes", extra={**enviados, "horario": lembretes.horario_de(momento)})
        resultado = limpa(conn)
    log.info("rotinas.limpeza", extra=resultado)
    return {**enviados, **resultado}

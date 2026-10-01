"""Porta de entrada do núcleo: decide quem trata cada `Entrada`.

A identidade vem sempre do canal (from.id verificado), nunca do texto, de botão ou da
IA (regra de ouro 4). Admin = `Contexto.admin_id`.
"""

from __future__ import annotations

from telegrana.core import admin, cadastro, conta
from telegrana.core import repositorio as repo
from telegrana.core import textos as t
from telegrana.core.contexto import Contexto
from telegrana.core.mensagens import Entrada, Resultado
from telegrana.infra import db


def trata(conn: db.Connection, ctx: Contexto, e: Entrada) -> Resultado:
    eh_admin = e.external_id == ctx.admin_id
    if eh_admin and (e.comando in admin.COMANDOS or (e.acao or "").startswith("adm:")):
        return admin.trata(conn, ctx, e)

    ident = repo.identidade(conn, e.canal, e.external_id)
    if ident is None:
        return cadastro.sem_conta(conn, ctx, e, admin=eh_admin)

    with db.account_context(conn, ident.account_id) as cur:
        pessoa = repo.pessoa(cur, ident.account_id)
    if "blocked" in {pessoa.status, pessoa.conta_status}:
        return Resultado(rotulo="conta.bloqueada").diz(
            t.BLOQUEADA.format(contato=ctx.contato_admin)
        )
    if e.comando == "apagar_conta" or e.acao in conta.ACOES_APAGAR or e.acao == "cancelar":
        if pessoa.status == "onboarding" and e.acao == "cancelar":
            return Resultado(rotulo="cadastro.cancelar").diz(t.CANCELADO)
        if pessoa.status == "onboarding":
            return conta.apagar(conn, ctx, e, pessoa)
    if pessoa.status == "onboarding":
        return cadastro.passo(conn, ctx, e, pessoa)
    return conta.trata(conn, ctx, e, pessoa)

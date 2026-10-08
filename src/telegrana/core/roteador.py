"""Porta de entrada do núcleo: decide quem trata cada `Entrada`.

A identidade vem sempre do canal (from.id verificado), nunca do texto, de botão ou da
IA (regra de ouro 4). Admin = `Contexto.admin_id`.
"""

from __future__ import annotations

from dataclasses import replace

from telegrana.core import admin, cadastro, conta, conversa, escolha
from telegrana.core import lancamentos_repo as lrepo
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
    r = conta.trata(conn, ctx, e, pessoa)
    if r.abrir in conversa.TELAS:
        # A conversa sugeriu uma tela (D050): abre como se a pessoa mandasse o comando.
        comando, acao = conversa.TELAS[r.abrir]
        tela = replace(e, texto="", audio=None, resposta_a=None, comando=comando, acao=acao)
        r.saidas.extend(conta.trata(conn, ctx, tela, pessoa).saidas)
    pergunta = next((s for s in reversed(r.saidas) if s.pergunta in conta.SOLTAS), None)
    if pergunta is not None and pergunta.pergunta is not None:
        # No Telegram Web/Desktop a resposta não abre sozinha: a próxima mensagem solta com
        # cara de resposta também vale (conta._resposta_solta).
        linhas = pergunta.texto.replace("**", "").splitlines()
        contexto = linhas[1].strip() if len(linhas) > 1 else ""
        with db.account_context(conn, pessoa.account_id) as cur:
            lrepo.marca_pergunta(
                cur, pessoa.account_id, pessoa.user_id, pergunta.pergunta, contexto
            )
    elif (aberta := escolha.da_saida(r.saidas)) is not None:
        # Pergunta com botões: "exato", "pode ser" ou o nome de uma opção, escrito ou falado,
        # valem como o toque (conta._escolha_solta, 07/10/2026).
        with db.account_context(conn, pessoa.account_id) as cur:
            lrepo.marca_pergunta(
                cur, pessoa.account_id, pessoa.user_id, escolha.PERGUNTA, aberta.guarda(), 8000
            )
    return r

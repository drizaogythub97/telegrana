"""Comandos e botões do administrador (PLANO 3.2 e 3.5).

Só chega aqui quem é o admin (`Contexto.admin_id`, vindo do SSM, nunca do texto).
Todo botão é revalidado: dados de callback podem ser forjados por clientes modificados.
"""

from __future__ import annotations

import uuid

from telegrana.core import repositorio as repo
from telegrana.core import seguranca as seg
from telegrana.core import textos as t
from telegrana.core.cadastro import religa
from telegrana.core.contexto import Contexto, data_br
from telegrana.core.mensagens import Botao, Entrada, Resultado, seguro
from telegrana.infra import db

COMANDOS = frozenset({"admin", "link", "usuarios"})


def trata(conn: db.Connection, ctx: Contexto, e: Entrada) -> Resultado:
    if e.comando == "admin":
        return Resultado(rotulo="admin.ajuda").diz(t.ADM_AJUDA)
    if e.comando == "link":
        return _link(conn, ctx, e.argumento.strip().lower())
    if e.comando == "usuarios":
        return _usuarios(conn)
    partes = (e.acao or "").split(":")
    r = Resultado(rotulo=f"admin.{partes[1] if len(partes) > 1 else '?'}")
    if len(partes) == 3 and partes[1] in {"ok", "no"}:
        pedido_id = seg.longo(partes[2])
        return _decide(conn, ctx, pedido_id, aprovar=partes[1] == "ok", r=r) if pedido_id else r
    if len(partes) == 4 and partes[1] == "rl":
        pedido_id, user_id = seg.longo(partes[2]), seg.longo(partes[3])
        if pedido_id is None or user_id is None:
            return r
        pedido = repo.pedido(conn, pedido_id)
        if pedido is None or pedido.status != "pending" or pedido.kind != "recovery":
            return r.diz(t.ADM_PEDIDO_RESOLVIDO)
        resultado = religa(
            conn,
            ctx,
            pedido.channel,
            pedido.external_id,
            user_id,
            via="admin",
            para=pedido.external_id,
        )
        repo.apaga_pedido(conn, pedido_id)
        # Para o admin, a confirmação no lugar do aviso genérico de recuperação.
        resultado.saidas = [s for s in resultado.saidas if s.destino != "admin"]
        if resultado.rotulo.endswith(".ok"):
            nome = next((n for _, u, n, _ in repo.lista_pessoas(conn) if u == user_id), "?")
            resultado.diz(t.ADM_RELIGADO.format(nome=seguro(nome)))
        else:
            resultado.diz(t.ADM_PEDIDO_RESOLVIDO)
        return resultado
    if len(partes) == 3 and partes[1] in {"bq", "db"}:
        conta = seg.longo(partes[2])
        return _bloqueio(conn, ctx, conta, bloquear=partes[1] == "bq", r=r) if conta else r
    return r


def _decide(
    conn: db.Connection, ctx: Contexto, pedido_id: uuid.UUID, *, aprovar: bool, r: Resultado
) -> Resultado:
    pedido = repo.pedido(conn, pedido_id)
    if pedido is None or pedido.status != "pending":
        return r.diz(t.ADM_PEDIDO_RESOLVIDO)
    if not aprovar:
        repo.decide_pedido(conn, pedido.id, "rejected")
        with conn.transaction():
            repo.audita(conn, "access.rejected", ator="admin")
        return r.diz(t.ADM_RECUSADO)
    if pedido.kind != "access":
        return r.diz(t.ADM_PEDIDO_RESOLVIDO)
    ident = repo.inicia_cadastro(conn, pedido.channel, pedido.external_id)
    with db.account_context(conn, ident.account_id) as cur:
        repo.apaga_pedidos_da_pessoa(cur, pedido.channel, pedido.external_id)
        repo.audita(cur, "access.approved", account_id=ident.account_id, ator="admin")
    return r.diz(
        t.ACESSO_LIBERADO,
        destino=pedido.external_id,
        botoes=((Botao("📝 Criar minha conta", "cad:iniciar"),),),
    ).diz(t.ADM_APROVADO.format(nome=seguro(pedido.display_name)))


def _bloqueio(
    conn: db.Connection, ctx: Contexto, conta: uuid.UUID, *, bloquear: bool, r: Resultado
) -> Resultado:
    alvo = next((x for x in repo.lista_pessoas(conn) if x[0] == conta), None)
    if alvo is None:
        return r.diz(t.ADM_PEDIDO_RESOLVIDO)
    account_id, user_id, nome, _ = alvo
    with db.account_context(conn, account_id) as cur:
        ids = cur.execute(
            "select c.external_id from telegrana.user_channels c where c.user_id = %s",
            (user_id,),
        ).fetchall()
        if bloquear and any(x[0] == ctx.admin_id for x in ids):
            return r.diz("Você não pode bloquear a própria conta.")
        situacao = "blocked" if bloquear else "active"
        repo.atualiza_pessoa(cur, user_id, status=situacao)
        repo.atualiza_conta(cur, account_id, status=situacao)
        repo.audita(
            cur,
            "account.blocked" if bloquear else "account.unblocked",
            account_id=account_id,
            ator="admin",
        )
    return r.diz((t.ADM_BLOQUEADO if bloquear else t.ADM_DESBLOQUEADO).format(nome=seguro(nome)))


def _link(conn: db.Connection, ctx: Contexto, argumento: str) -> Resultado:
    r = Resultado(rotulo=f"admin.link.{argumento or 'status'}")
    if argumento == "novo":
        token = seg.novo_token_convite()
        repo.cria_convite(conn, seg.hash_token(token), ctx.max_usos_convite)
        return r.diz(
            t.ADM_LINK_NOVO.format(usos=ctx.max_usos_convite, link=ctx.link_convite(token))
        )
    if argumento == "revogar":
        repo.revoga_convites(conn)
        return r.diz(t.ADM_LINK_REVOGADO)
    ativo = repo.convite_ativo(conn)
    if ativo is None:
        return r.diz(t.ADM_SEM_LINK)
    _, usados, maximo, criado = ativo
    return r.diz(t.ADM_LINK_STATUS.format(criado=data_br(criado), usados=usados, maximo=maximo))


def _usuarios(conn: db.Connection) -> Resultado:
    r = Resultado(rotulo="admin.usuarios")
    pessoas = repo.lista_pessoas(conn)
    if not pessoas:
        return r.diz(t.ADM_USUARIOS_VAZIO)
    linhas = [
        f"• {seguro(nome, 60)} — {'🚫 bloqueada' if situacao == 'blocked' else 'ativa'}"
        for _, _, nome, situacao in pessoas
    ]
    botoes = tuple(
        (
            Botao(
                f"{'✅ Desbloquear' if situacao == 'blocked' else '🚫 Bloquear'} {seguro(nome, 30)}",
                f"adm:{'db' if situacao == 'blocked' else 'bq'}:{seg.curto(conta)}",
            ),
        )
        for conta, _, nome, situacao in pessoas
    )
    return r.diz("👥 **Contas**\n" + "\n".join(linhas), botoes=botoes)

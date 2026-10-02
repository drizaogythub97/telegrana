"""Comandos de quem já tem conta: privacidade e manutenção (PLANO 3.5 e 3.6)."""

from __future__ import annotations

from datetime import datetime

from telegrana.core import categorias, lancamentos
from telegrana.core import repositorio as repo
from telegrana.core import seguranca as seg
from telegrana.core import textos as t
from telegrana.core.cadastro import registra_aceites, saida_codigo, tela_termos, valida_nome
from telegrana.core.contexto import Contexto, data_br
from telegrana.core.mensagens import ADMIN, Botao, Entrada, Resultado, seguro
from telegrana.infra import db

_CANCELAR = Botao("Cancelar", "cancelar")
ACOES_APAGAR = frozenset({"apagar:1", "apagar:2"})


def apagar(conn: db.Connection, ctx: Contexto, e: Entrada, p: repo.Pessoa) -> Resultado:
    """/apagar_conta com confirmação dupla (vale também no meio do cadastro)."""
    r = Resultado(rotulo="conta.apagar")
    if e.acao == "apagar:2":
        with db.account_context(conn, p.account_id) as cur:
            repo.apaga_conta(cur, p.account_id)
        r.rotulo = "conta.apagada"
        r.diz(t.APAGADA, tirar_teclado=True)
        if e.external_id != ctx.admin_id:
            r.diz(t.ADM_APAGOU, destino=ADMIN)
        return r
    if e.acao == "apagar:1":
        return r.diz(t.APAGAR_2, botoes=((Botao("🗑️ Sim, apagar tudo", "apagar:2"), _CANCELAR),))
    return r.diz(
        t.APAGAR_1.format(contato=ctx.contato_admin),
        botoes=((Botao("🗑️ Apagar minha conta", "apagar:1"), _CANCELAR),),
    )


def trata(conn: db.Connection, ctx: Contexto, e: Entrada, p: repo.Pessoa) -> Resultado:
    with db.account_context(conn, p.account_id) as cur:
        aceitos = repo.aceites(cur)
    termos = aceitos.get("termos")
    privacidade = aceitos.get("privacidade")
    if e.comando == "apagar_conta" or e.acao in ACOES_APAGAR:
        return apagar(conn, ctx, e, p)
    if (
        termos is None
        or privacidade is None
        or termos[0] < ctx.termos.versao
        or privacidade[0] < ctx.privacidade.versao
    ):
        if e.acao == "termos:aceito":
            with db.account_context(conn, p.account_id) as cur:
                registra_aceites(cur, ctx, p)
            return Resultado(rotulo="conta.termos.aceitos").diz("✅ Obrigado! Tudo certo.")
        return Resultado(saidas=[tela_termos(ctx, mudaram=True)], rotulo="conta.termos.pendentes")

    r = Resultado(rotulo=f"conta.{e.comando or e.acao or e.pergunta or 'mensagem'}")
    if e.contato_alheio:
        return r.diz(t.SO_PROPRIO_NUMERO)
    if e.telefone is not None:
        return _atualiza_telefone(conn, ctx, e, p, r)
    if e.pergunta == "nome":
        nome = valida_nome(e.texto)
        if nome is None:
            return r.diz(t.NOME_INVALIDO).diz(t.PERGUNTAS["nome"], pergunta="nome")
        with db.account_context(conn, p.account_id) as cur:
            repo.atualiza_pessoa(cur, p.user_id, full_name=nome)
        return r.diz(t.NOME_CORRIGIDO.format(nome=nome))
    if (
        e.comando == "categorias"
        or (e.acao or "").startswith("cat:")
        or e.pergunta in categorias.PERGUNTAS
    ):
        return categorias.trata(conn, ctx, e, p)
    match e.comando or e.acao:
        case "start" | "entrar":
            return r.diz(t.JA_TEM_CONTA)
        case "ajuda":
            return r.diz(t.AJUDA)
        case "meus_dados":
            return _meus_dados(conn, ctx, p, termos, privacidade, r)
        case "corrigir_nome":
            return r.diz(t.PERGUNTAS["nome"], pergunta="nome")
        case "termos":
            return r.diz(
                t.TERMOS_INFO.format(
                    termos=termos[0], privacidade=privacidade[0], aceite=data_br(termos[1])
                ),
                botoes=(
                    (
                        Botao(t.BOTAO_TERMOS, url=ctx.termos.url),
                        Botao(t.BOTAO_PRIVACIDADE, url=ctx.privacidade.url),
                    ),
                ),
            )
        case "codigo_novo":
            return r.diz(
                t.CODIGO_NOVO_CONFIRMA, botoes=((Botao(t.BOTAO_GERAR, "cod:novo"), _CANCELAR),)
            )
        case "cod:novo":
            with db.account_context(conn, p.account_id) as cur:
                saida = saida_codigo(cur, p, com_botao=False)
                repo.audita(cur, "recovery_code.rotated", account_id=p.account_id)
            r.saidas.append(saida)
            return r
        case "cancelar":
            return r.diz(t.CANCELADO)
        case "codigo:guardei":
            return r.diz("👍")
    if e.pergunta is not None and e.pergunta not in lancamentos.PERGUNTAS:
        return r.diz(t.JA_TEM_CONTA)  # resposta a pergunta de quem ainda não tinha conta
    if e.comando is not None:
        return r.diz(t.AJUDA)
    return lancamentos.trata(conn, ctx, e, p)


def _atualiza_telefone(
    conn: db.Connection, ctx: Contexto, e: Entrada, p: repo.Pessoa, r: Resultado
) -> Resultado:
    e164 = seg.normaliza_telefone(e.telefone or "")
    if e164 is None:
        return r.diz(t.NUMERO_INVALIDO, tirar_teclado=True)
    h = seg.hmac_telefone(e164, ctx.pepper)
    outro = repo.busca_por_telefone(conn, h)
    if outro is not None and outro.user_id != p.user_id:
        return r.diz(t.TELEFONE_DE_OUTRA_CONTA, tirar_teclado=True)
    with db.account_context(conn, p.account_id) as cur:
        repo.atualiza_pessoa(cur, p.user_id, phone_hmac=h)
        repo.audita(cur, "phone.updated", account_id=p.account_id)
    return r.diz(t.TELEFONE_ATUALIZADO, tirar_teclado=True)


def _meus_dados(
    conn: db.Connection,
    ctx: Contexto,
    p: repo.Pessoa,
    termos: tuple[int, datetime],
    privacidade: tuple[int, datetime],
    r: Resultado,
) -> Resultado:
    with db.account_context(conn, p.account_id) as cur:
        codigo = repo.tem_codigo(cur)
    return r.diz(
        t.MEUS_DADOS.format(
            nome=seguro(p.full_name or "?"),
            telefone="vinculado ✅" if p.tem_telefone else "não vinculado",
            maioridade=data_br(p.adult_declared_at) if p.adult_declared_at else "—",
            termos=termos[0],
            privacidade=privacidade[0],
            aceite=data_br(termos[1]),
            codigo=f"ativo desde {data_br(codigo)}" if codigo else "nenhum (gere com /codigo_novo)",
            criada=data_br(p.created_at),
            contato=ctx.contato_admin,
        )
    )

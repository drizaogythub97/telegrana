"""Entrada, cadastro e recuperação (PLANO 3.2, 3.3 e 3.5; D032, D033).

Quem ainda não tem conta só chega aqui. Nada de IA, arquivo ou consulta pesada.
"""

from __future__ import annotations

import re
import uuid
from functools import cache

from telegrana.core import repositorio as repo
from telegrana.core import seguranca as seg
from telegrana.core import textos as t
from telegrana.core.contexto import Contexto, agora
from telegrana.core.mensagens import ADMIN, Botao, Entrada, Resultado, Saida, seguro
from telegrana.infra import db

_NOME = re.compile(r"[^\W\d_]+(?:['-][^\W\d_]+)*(?: [^\W\d_]+(?:['-][^\W\d_]+)*)+")


# ---------------------------------------------------------------------------
# Telas reaproveitadas
# ---------------------------------------------------------------------------
def tela_termos(ctx: Contexto, *, mudaram: bool = False) -> Saida:
    return Saida(
        t.TERMOS_MUDARAM if mudaram else t.RESUMO_TERMOS,
        botoes=(
            (
                Botao(t.BOTAO_TERMOS, url=ctx.termos.url),
                Botao(t.BOTAO_PRIVACIDADE, url=ctx.privacidade.url),
            ),
            (Botao(t.BOTAO_ACEITO, "termos:aceito"),),
        ),
    )


def _tela_privado() -> Resultado:
    return Resultado(rotulo="entrada.privado").diz(
        t.PRIVADO,
        botoes=(
            (Botao("🙋 Pedir acesso", "acesso:pedir"),),
            (Botao("🔄 Já tenho conta", "rec:menu"),),
        ),
    )


def valida_nome(texto: str) -> str | None:
    nome = " ".join(texto.split())
    if not 2 <= len(nome) <= 120 or not _NOME.fullmatch(nome):
        return None
    return nome


def registra_aceites(cur: object, ctx: Contexto, p: repo.Pessoa) -> None:
    repo.registra_aceite(
        cur, p.account_id, p.user_id, "termos", ctx.termos.versao, ctx.termos.sha256
    )
    repo.registra_aceite(
        cur, p.account_id, p.user_id, "privacidade", ctx.privacidade.versao, ctx.privacidade.sha256
    )
    repo.audita(cur, "terms.accepted", account_id=p.account_id)


def saida_codigo(
    cur: object, p: repo.Pessoa, *, com_botao: bool, destino: str | None = None
) -> Saida:
    """Gera, guarda (Argon2id) e devolve a mensagem com o código: mostrado uma vez só."""
    codigo = seg.novo_codigo()
    repo.troca_codigo(
        cur, p.account_id, p.user_id, codigo.seletor, seg.hash_verificador(codigo.verificador)
    )
    botoes = ((Botao(t.BOTAO_GUARDEI, "codigo:guardei"),),) if com_botao else ()
    return Saida(
        t.CODIGO_RECUPERACAO.format(codigo=codigo.exibicao),
        destino=destino,
        botoes=botoes,
        protegida=True,
    )


# ---------------------------------------------------------------------------
# Sem conta
# ---------------------------------------------------------------------------
def sem_conta(conn: db.Connection, ctx: Contexto, e: Entrada, *, admin: bool) -> Resultado:
    if e.contato_alheio:
        return Resultado(rotulo="recuperacao.alheio").diz(
            t.SO_PROPRIO_NUMERO, pedir_telefone=t.BOTAO_NUMERO
        )
    if e.telefone is not None:
        return _recupera_por_telefone(conn, ctx, e)
    if e.comando == "start":
        convite = None
        token = e.argumento.strip()
        if token and seg.token_valido(token):
            convite = repo.convite_valido(conn, seg.hash_token(token))
        if convite is not None or admin:
            return _comeca(conn, ctx, e, convite)
        return _tela_privado()
    if e.comando == "entrar" or e.acao == "rec:cod":
        return Resultado(rotulo="recuperacao.codigo.pergunta").diz(
            t.PERGUNTAS["codigo"], pergunta="codigo"
        )
    if e.pergunta == "codigo":
        return _recupera_por_codigo(conn, ctx, e)
    if e.pergunta in {"acesso", "rec_nome"}:
        return _registra_pedido(conn, ctx, e, "access" if e.pergunta == "acesso" else "recovery")
    if e.acao == "acesso:pedir":
        return _pede(conn, ctx, e, t.AVISO_PEDIDO, "acesso")
    if e.acao == "rec:adm":
        return _pede(conn, ctx, e, None, "rec_nome")
    if e.acao == "rec:menu":
        return Resultado(rotulo="recuperacao.menu").diz(
            t.JA_TENHO_CONTA,
            botoes=(
                (Botao("📱 Pelo meu número", "rec:tel"),),
                (Botao("🔑 Tenho o código", "rec:cod"),),
                (Botao("🆘 Perdi os dois", "rec:adm"),),
            ),
        )
    if e.acao == "rec:tel":
        return Resultado(rotulo="recuperacao.telefone.pergunta").diz(
            t.PEDIR_NUMERO, pedir_telefone=t.BOTAO_NUMERO
        )
    if admin:  # o admin sempre pode criar a própria conta
        return _comeca(conn, ctx, e, None)
    return _tela_privado()


def _comeca(conn: db.Connection, ctx: Contexto, e: Entrada, convite: uuid.UUID | None) -> Resultado:
    ident = repo.inicia_cadastro(conn, e.canal, e.external_id)
    with db.account_context(conn, ident.account_id) as cur:
        if convite is not None:
            repo.atualiza_conta(cur, ident.account_id, invite_link_id=convite)
        repo.apaga_pedidos_da_pessoa(cur, e.canal, e.external_id)
    r = Resultado(rotulo="cadastro.inicio").diz(t.BOAS_VINDAS)
    r.saidas.append(tela_termos(ctx))
    return r


def _pede(
    conn: db.Connection, ctx: Contexto, e: Entrada, aviso: str | None, pergunta: str
) -> Resultado:
    r = Resultado(rotulo=f"pedido.{pergunta}.pergunta")
    bloqueio = _pedido_bloqueado(conn, ctx, e)
    if bloqueio:
        return r.diz(bloqueio)
    if aviso:
        r.diz(aviso)
    return r.diz(t.PERGUNTAS[pergunta], pergunta=pergunta)


def _pedido_bloqueado(conn: db.Connection, ctx: Contexto, e: Entrada) -> str | None:
    existente = repo.pedido_da_pessoa(conn, e.canal, e.external_id)
    if existente is not None:
        return t.PEDIDO_PENDENTE if existente.status == "pending" else t.PEDIDO_INDISPONIVEL
    if repo.pedidos_na_ultima_hora(conn) >= ctx.max_pedidos_por_hora:
        return t.PEDIDO_INDISPONIVEL
    return None


def _registra_pedido(conn: db.Connection, ctx: Contexto, e: Entrada, tipo: str) -> Resultado:
    r = Resultado(rotulo=f"pedido.{tipo}")
    mensagem = seguro(e.texto, 400)
    if not 1 <= len(mensagem) <= 200:
        pergunta = "acesso" if tipo == "access" else "rec_nome"
        return r.diz(t.PEDIDO_TAMANHO).diz(t.PERGUNTAS[pergunta], pergunta=pergunta)
    bloqueio = _pedido_bloqueado(conn, ctx, e)
    if bloqueio:
        return r.diz(bloqueio)
    nome = seguro(e.nome, 128) or "Sem nome"
    username = seguro(e.username, 64) if e.username else None
    pedido_id = repo.cria_pedido(conn, e.canal, e.external_id, nome, username, mensagem, tipo)
    if pedido_id is None:
        return r.diz(t.PEDIDO_PENDENTE)
    arroba = f"@{username}" if username else "sem @"
    if tipo == "access":
        r.diz(
            t.ADM_PEDIDO.format(nome=nome, username=arroba, mensagem=mensagem),
            destino=ADMIN,
            botoes=(
                (
                    Botao("✅ Aprovar", f"adm:ok:{seg.curto(pedido_id)}"),
                    Botao("❌ Recusar", f"adm:no:{seg.curto(pedido_id)}"),
                ),
            ),
        )
        return r.diz(t.PEDIDO_ENVIADO)
    contas = [
        (Botao(f"👤 {seguro(n, 40)}", f"adm:rl:{seg.curto(pedido_id)}:{seg.curto(u)}"),)
        for _, u, n, situacao in repo.lista_pessoas(conn)
        if situacao != "onboarding"
    ]
    r.diz(
        t.ADM_PEDIDO_RECUPERACAO.format(nome=nome, username=arroba, mensagem=mensagem),
        destino=ADMIN,
        botoes=(*contas, (Botao("❌ Recusar", f"adm:no:{seg.curto(pedido_id)}"),)),
    )
    return r.diz(t.PEDIDO_RECUPERACAO_ENVIADO)


# ---------------------------------------------------------------------------
# Recuperação
# ---------------------------------------------------------------------------
def _travado(conn: db.Connection, e: Entrada, tipo: str) -> Resultado | None:
    ate = repo.travado_ate(conn, e.canal, e.external_id, tipo)
    if ate is None:
        return None
    minutos = max(1, int((ate - agora()).total_seconds() // 60) + 1)
    return Resultado(rotulo=f"recuperacao.{tipo}.travado").diz(t.TRAVADO.format(minutos=minutos))


def _falhou(conn: db.Connection, e: Entrada, tipo: str) -> None:
    falhas = repo.registra_falha(conn, e.canal, e.external_id, tipo)
    trava = seg.trava_para(falhas)
    if trava is not None:
        repo.trava(conn, e.canal, e.external_id, tipo, int(trava.total_seconds()))


def _recupera_por_telefone(conn: db.Connection, ctx: Contexto, e: Entrada) -> Resultado:
    travado = _travado(conn, e, "phone")
    if travado:
        return travado
    e164 = seg.normaliza_telefone(e.telefone or "")
    if e164 is None:
        return Resultado(rotulo="recuperacao.telefone.invalido").diz(
            t.NUMERO_INVALIDO, pedir_telefone=t.BOTAO_NUMERO
        )
    alvo = repo.busca_por_telefone(conn, seg.hmac_telefone(e164, ctx.pepper))
    if alvo is None or alvo.status == "onboarding":
        _falhou(conn, e, "phone")
        return Resultado(rotulo="recuperacao.telefone.sem_conta").diz(
            t.NUMERO_SEM_CONTA, tirar_teclado=True
        )
    return religa(conn, ctx, e.canal, e.external_id, alvo.user_id, via="telefone")


@cache
def _hash_falso() -> str:
    # Mesmo custo de conferir um código que existe: o tempo de resposta não revela
    # se o seletor está no banco.
    return seg.hash_verificador(seg.novo_codigo().verificador)


def _recupera_por_codigo(conn: db.Connection, ctx: Contexto, e: Entrada) -> Resultado:
    travado = _travado(conn, e, "code")
    if travado:
        travado.apagar_entrada = True
        return travado
    partes = seg.separa_codigo(e.texto)
    if partes is None:
        r = Resultado(rotulo="recuperacao.codigo.formato").diz(t.CODIGO_FORMATO)
        r.apagar_entrada = True
        return r
    seletor, verificador = partes
    achado = repo.busca_codigo(conn, seletor)
    certo = seg.confere_verificador(achado[1] if achado else _hash_falso(), verificador)
    if achado is None or not certo:
        _falhou(conn, e, "code")
        r = Resultado(rotulo="recuperacao.codigo.errado").diz(t.CODIGO_INVALIDO)
        r.apagar_entrada = True
        return r
    r = religa(conn, ctx, e.canal, e.external_id, achado[0].user_id, via="codigo")
    r.apagar_entrada = True
    return r


def religa(
    conn: db.Connection,
    ctx: Contexto,
    canal: str,
    external_id: str,
    user_id: uuid.UUID,
    *,
    via: str,
    para: str | None = None,
) -> Resultado:
    """Liga a pessoa a esta identidade. `para`: destino das mensagens ao recuperado
    (None quando é ele mesmo quem pede; o external_id quando o admin aprova)."""
    situacao, conta, antigo = repo.religa(conn, canal, external_id, user_id)
    r = Resultado(rotulo=f"recuperacao.{via}.{situacao}")
    if situacao == "in_use":
        return r.diz(t.RECUPERACAO_EM_USO, destino=para, tirar_teclado=True)
    if situacao == "missing" or conta is None:
        return r.diz(t.NUMERO_SEM_CONTA, destino=para, tirar_teclado=True)
    with db.account_context(conn, conta) as cur:
        p = repo.pessoa(cur, conta)
        repo.audita(
            cur,
            "account.recovered",
            account_id=conta,
            ator="admin" if via == "admin" else "user",
            detalhes={"via": via},
        )
        repo.apaga_pedidos_da_pessoa(cur, canal, external_id)
        codigo = saida_codigo(cur, p, com_botao=False, destino=para) if via != "telefone" else None
    for tipo in ("code", "phone"):
        repo.zera_falhas(conn, canal, external_id, tipo)
    r.diz(t.RECUPERADA, destino=para, tirar_teclado=True)
    if codigo is not None:  # o código é trocado a cada uso (PLANO 3.5)
        r.saidas.append(codigo)
        r.diz(t.PEDIR_NUMERO_NOVO, destino=para, pedir_telefone=t.BOTAO_NUMERO)
    if antigo and antigo != external_id:
        r.diz(t.AVISO_CONTA_ANTIGA, destino=antigo)
    if external_id != ctx.admin_id:
        r.diz(t.ADM_RECUPEROU.format(nome=seguro(p.full_name or "?"), via=via), destino=ADMIN)
    return r


# ---------------------------------------------------------------------------
# Cadastro em andamento (máquina de estados em users.onboarding_step)
# ---------------------------------------------------------------------------
def passo(conn: db.Connection, ctx: Contexto, e: Entrada, p: repo.Pessoa) -> Resultado:
    etapa = p.onboarding_step
    if etapa == "terms":
        return _etapa_termos(conn, ctx, e, p)
    if etapa == "name":
        return _etapa_nome(conn, e, p)
    if etapa == "phone":
        return _etapa_telefone(conn, ctx, e, p)
    if etapa == "adult":
        return _etapa_maioridade(conn, e, p)
    if e.acao == "codigo:guardei":
        return _finaliza(conn, ctx, e, p)
    # recovery_code (ou etapa inesperada): gera de novo, porque o anterior não pode
    # ser mostrado outra vez.
    with db.account_context(conn, p.account_id) as cur:
        if etapa != "recovery_code":
            repo.atualiza_pessoa(cur, p.user_id, onboarding_step="recovery_code")
        saida = saida_codigo(cur, p, com_botao=True)
    return Resultado(saidas=[saida], rotulo="cadastro.codigo")


def _etapa_termos(conn: db.Connection, ctx: Contexto, e: Entrada, p: repo.Pessoa) -> Resultado:
    if e.acao != "termos:aceito":
        return Resultado(saidas=[tela_termos(ctx)], rotulo="cadastro.termos")
    with db.account_context(conn, p.account_id) as cur:
        registra_aceites(cur, ctx, p)
        repo.atualiza_pessoa(cur, p.user_id, onboarding_step="name")
    return Resultado(rotulo="cadastro.termos.aceitos").diz(t.PEDIR_NOME)


def _etapa_nome(conn: db.Connection, e: Entrada, p: repo.Pessoa) -> Resultado:
    r = Resultado(rotulo="cadastro.nome")
    if e.acao == "nome:ok" and p.full_name:
        with db.account_context(conn, p.account_id) as cur:
            repo.atualiza_pessoa(cur, p.user_id, onboarding_step="phone")
        return r.diz(t.PEDIR_TELEFONE, pedir_telefone=t.BOTAO_NUMERO)
    if e.acao == "nome:corrigir":
        with db.account_context(conn, p.account_id) as cur:
            repo.atualiza_pessoa(cur, p.user_id, full_name=None)
        return r.diz(t.PEDIR_NOME)
    if e.texto and e.comando is None and e.acao is None:
        nome = valida_nome(e.texto)
        if nome is None:
            return r.diz(t.NOME_INVALIDO)
        with db.account_context(conn, p.account_id) as cur:
            repo.atualiza_pessoa(cur, p.user_id, full_name=nome)
        return r.diz(t.CONFIRMAR_NOME.format(nome=nome), botoes=_BOTOES_NOME)
    if p.full_name:
        return r.diz(t.CONFIRMAR_NOME.format(nome=p.full_name), botoes=_BOTOES_NOME)
    return r.diz(t.PEDIR_NOME)


_BOTOES_NOME = ((Botao("✅ Sim", "nome:ok"), Botao("✏️ Corrigir", "nome:corrigir")),)


def _etapa_telefone(conn: db.Connection, ctx: Contexto, e: Entrada, p: repo.Pessoa) -> Resultado:
    r = Resultado(rotulo="cadastro.telefone")
    if e.contato_alheio:
        return r.diz(t.SO_PROPRIO_NUMERO, pedir_telefone=t.BOTAO_NUMERO)
    if e.telefone is None:
        return r.diz(t.PEDIR_TELEFONE, pedir_telefone=t.BOTAO_NUMERO)
    e164 = seg.normaliza_telefone(e.telefone)
    if e164 is None:
        return r.diz(t.NUMERO_INVALIDO, pedir_telefone=t.BOTAO_NUMERO)
    h = seg.hmac_telefone(e164, ctx.pepper)
    outro = repo.busca_por_telefone(conn, h)
    if outro is not None and outro.user_id != p.user_id:
        if outro.status == "onboarding":  # outro cadastro inacabado com o mesmo número
            return r.diz(t.TELEFONE_DE_OUTRA_CONTA, tirar_teclado=True)
        # O Telegram atesta que o número é do remetente: é a mesma prova da recuperação.
        recuperado = religa(conn, ctx, e.canal, e.external_id, outro.user_id, via="telefone")
        recuperado.saidas[0] = Saida(t.RECUPERADA_PELO_CADASTRO, tirar_teclado=True)
        return recuperado
    with db.account_context(conn, p.account_id) as cur:
        repo.atualiza_pessoa(cur, p.user_id, phone_hmac=h, onboarding_step="adult")
    return r.diz("✅ Número recebido.", tirar_teclado=True).diz(
        t.PEDIR_MAIORIDADE,
        botoes=(
            (
                Botao("✅ Tenho 18 anos ou mais", "adulto:sim"),
                Botao("Não tenho", "adulto:nao"),
            ),
        ),
    )


def _etapa_maioridade(conn: db.Connection, e: Entrada, p: repo.Pessoa) -> Resultado:
    r = Resultado(rotulo="cadastro.maioridade")
    if e.acao == "adulto:nao":
        with db.account_context(conn, p.account_id) as cur:
            repo.apaga_conta(cur, p.account_id)
        return r.diz(t.MENOR)
    if e.acao != "adulto:sim":
        return r.diz(
            t.PEDIR_MAIORIDADE,
            botoes=(
                (
                    Botao("✅ Tenho 18 anos ou mais", "adulto:sim"),
                    Botao("Não tenho", "adulto:nao"),
                ),
            ),
        )
    with db.account_context(conn, p.account_id) as cur:
        repo.atualiza_pessoa(
            cur, p.user_id, adult_declared_at=agora(), onboarding_step="recovery_code"
        )
        saida = saida_codigo(cur, p, com_botao=True)
    r.saidas.append(saida)
    return r


def _finaliza(conn: db.Connection, ctx: Contexto, e: Entrada, p: repo.Pessoa) -> Resultado:
    via = (
        "convite" if p.invite_link_id else ("admin" if e.external_id == ctx.admin_id else "pedido")
    )
    with db.account_context(conn, p.account_id) as cur:
        repo.atualiza_pessoa(cur, p.user_id, onboarding_step="done", status="active")
        repo.atualiza_conta(cur, p.account_id, status="active")
        if p.invite_link_id is not None:
            repo.usa_convite(cur, p.invite_link_id)
        repo.audita(cur, "account.created", account_id=p.account_id, detalhes={"via": via})
    r = Resultado(rotulo="cadastro.concluido").diz(t.PRONTO)
    if e.external_id != ctx.admin_id:
        r.diz(
            t.ADM_ENTROU.format(nome=seguro(p.full_name or "?"), via=via),
            destino=ADMIN,
            botoes=((Botao("🚫 Bloquear", f"adm:bq:{seg.curto(p.account_id)}"),),),
        )
    return r

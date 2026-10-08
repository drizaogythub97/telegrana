"""Comandos de quem já tem conta: privacidade e manutenção (PLANO 3.5 e 3.6)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from telegrana.core import (
    cartoes,
    categorias,
    conversa,
    datas,
    escolha,
    exportacao,
    faturas,
    fixos,
    lancamentos,
    lembretes,
    relatorios,
    valores,
)
from telegrana.core import lancamentos_repo as lrepo
from telegrana.core import repositorio as repo
from telegrana.core import seguranca as seg
from telegrana.core import textos as t
from telegrana.core.cadastro import registra_aceites, saida_codigo, tela_termos, valida_nome
from telegrana.core.contexto import Contexto, agora, data_br
from telegrana.core.interpretacao import normaliza
from telegrana.core.mensagens import ADMIN, Botao, Entrada, Resultado, Saida, seguro
from telegrana.infra import db

_CANCELAR = Botao("Cancelar", "cancelar")
ACOES_APAGAR = frozenset({"apagar:1", "apagar:2"})
_VALORES = frozenset({"lc_valor", "fi_valor", "lm_valor", "fa_valor"})
_NOMES = frozenset({"lc_cartao", "ct_nome", "ct_renomear"})
_DIAS_DA_FATURA = frozenset({"lc_cartao_dias", "ct_dias"})
# Perguntas que aceitam a resposta solta (sem "Responder"), se ela tiver a cara da resposta.
SOLTAS = _VALORES | _NOMES | _DIAS_DA_FATURA | {"lc_data", "fi_dia"}


def cabe(pergunta: str, texto: str, contexto: str = "") -> bool:
    """A mensagem solta tem a cara da resposta a esta pergunta? Na dúvida, não: segue como
    mensagem nova (um gasto mandado logo depois de uma pergunta não pode virar resposta)."""
    palavras = texto.split()
    if pergunta in _VALORES:
        return valores.so_valor(texto, frozenset(normaliza(contexto).split())) is not None
    if pergunta in _NOMES:
        return (
            0 < len(palavras) <= 3
            and not any(c.isdigit() for c in texto)
            and bool(cartoes.chave(texto))
            and cartoes.nome_valido(texto) is not None
        )
    if pergunta in _DIAS_DA_FATURA:
        return cartoes.dois_dias(texto) is not None
    if pergunta == "lc_data":
        return 0 < len(palavras) <= 4 and datas.expressao_em(texto) is not None
    if pergunta == "fi_dia":
        return 0 < len(palavras) <= 4 and 1 <= fixos.dia_dito(texto) <= 31
    return False


def nao_responde(pergunta: str, texto: str) -> bool:
    """Mesmo respondendo à pergunta (com "Responder"), a mensagem claramente é outra coisa?
    ("Quero cadastrar um gasto fixo" para "Quanto você pagou?"). Na dúvida, não: o
    tratador da pergunta decide, como antes."""
    palavras = texto.split()
    if pergunta in _VALORES:
        valor = valores.interpreta(texto)
        return valor.centavos is None and not valor.vago
    if pergunta in _NOMES:
        return len(palavras) > 4 or "?" in texto
    if pergunta in _DIAS_DA_FATURA:
        return cartoes.dois_dias(texto) is None and not any(c.isdigit() for c in texto)
    if pergunta == "lc_data":  # datas vagas ("semana passada") ficam com o tratador
        return len(palavras) > 5 and datas.expressao_em(texto) is None
    if pergunta == "fi_dia":
        return len(palavras) > 3 and fixos.dia_dito(texto) == 0
    return False


def _texto_da_pergunta(pergunta: str, contexto: str) -> str:
    base = t.primeira_linha(t.PERGUNTAS[pergunta])
    return f"{base} ({contexto})" if contexto else base


def _como_mensagem_nova(
    conn: db.Connection,
    ctx: Contexto,
    e: Entrada,
    p: repo.Pessoa,
    texto: str,
    pergunta: str,
    contexto: str,
) -> Resultado:
    """A mensagem não respondeu à pergunta: segue como mensagem nova (lançamento, consulta,
    conversa). Se virar conversa, a IA sabe da pergunta, e ela continua aberta para a
    próxima mensagem (D050)."""
    nova = replace(
        e,
        texto=texto,
        audio=None,
        pergunta=None,
        contexto="",
        resposta_a=None,
        pergunta_aberta=_texto_da_pergunta(pergunta, contexto),
    )
    r = trata(conn, ctx, nova, p)
    if r.rotulo == "lancamento.conversa.nenhuma":  # conversa sem assunto novo
        with db.account_context(conn, p.account_id) as cur:
            lrepo.marca_pergunta(cur, p.account_id, p.user_id, pergunta, contexto)
    return r


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
    if (
        e.audio is None
        and e.pergunta in SOLTAS
        and e.texto.strip()
        and nao_responde(e.pergunta, e.texto)
    ):  # respondeu à pergunta (com "Responder") com outra coisa
        return _como_mensagem_nova(conn, ctx, e, p, e.texto, e.pergunta, e.contexto)
    solta = _resposta_solta(conn, ctx, e, p)
    if solta is not None:
        return solta
    if e.audio is not None and e.pergunta is not None and e.pergunta not in lancamentos.PERGUNTAS:
        # Resposta por áudio a uma pergunta de fora dos lançamentos (valor do lembrete, valor
        # e dia do fixo...): ouve primeiro e segue como se fosse texto (05/10/2026).
        transcrito = lancamentos._transcreve(conn, ctx, e, p)
        if isinstance(transcrito, Resultado):
            return transcrito
        ouvido, avisos = transcrito
        r = trata(conn, ctx, replace(e, texto=ouvido, audio=None), p)
        return lancamentos._com_eco(r, ouvido, avisos)

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
        e.comando == "fixos"
        or (e.acao or "").startswith(fixos.PREFIXO)
        or e.pergunta in fixos.PERGUNTAS
    ):
        return fixos.trata(conn, ctx, e, p)
    if (
        e.comando == "cartoes"
        or (e.acao or "").startswith(cartoes.PREFIXO)
        or e.pergunta in cartoes.PERGUNTAS
    ):
        return cartoes.trata(conn, ctx, e, p)
    if e.comando == "exportar" or (e.acao or "").startswith(exportacao.PREFIXO):
        return exportacao.trata(conn, ctx, e, p)
    if e.comando in relatorios.COMANDOS or (e.acao or "").startswith(relatorios.PREFIXO):
        return relatorios.trata(conn, ctx, e, p)
    if (e.acao or "").startswith(faturas.PREFIXO) or e.pergunta in faturas.PERGUNTAS:
        return faturas.trata(conn, ctx, e, p)
    if (e.acao or "").startswith(lembretes.PREFIXO) or e.pergunta in lembretes.PERGUNTAS:
        return lembretes.trata(conn, ctx, e, p)
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


def _resposta_solta(
    conn: db.Connection, ctx: Contexto, e: Entrada, p: repo.Pessoa
) -> Resultado | None:
    """Pergunta aberta + mensagem solta com cara de resposta = resposta (05/10/2026)."""
    with db.account_context(conn, p.account_id) as cur:
        aberta = lrepo.abre_pergunta(cur, p.user_id)  # some a cada mensagem: vale para uma
    solta = e.pergunta is None and not e.resposta_a and e.comando is None and e.acao is None
    if aberta is None or not solta or e.telefone is not None:
        return None
    pergunta, contexto = aberta
    ouvido: str | None = None
    avisos: list[Saida] = []
    texto = e.texto
    if e.audio is not None:
        transcrito = lancamentos._transcreve(conn, ctx, e, p)
        if isinstance(transcrito, Resultado):
            return transcrito
        ouvido, avisos = transcrito
        texto = ouvido
    if pergunta == escolha.PERGUNTA:
        return _escolha_solta(conn, ctx, e, p, texto, contexto, ouvido, avisos)
    if pergunta == conversa.FIXO_NOVO:  # "quero cadastrar um fixo" → "aluguel 1500 dia 10"
        r = lancamentos.trata(conn, ctx, replace(e, texto=texto, audio=None), p, fixo=True)
        r.rotulo += ".solta"
        return lancamentos._com_eco(r, ouvido, avisos)
    if cabe(pergunta, texto, contexto):
        resposta = replace(e, pergunta=pergunta, contexto=contexto, texto=texto, audio=None)
        r = trata(conn, ctx, resposta, p)
        r.rotulo += ".solta"
    elif texto.strip():  # não tem a cara da resposta: mensagem nova, com a pergunta de contexto
        r = _como_mensagem_nova(conn, ctx, e, p, texto, pergunta, contexto)
    else:
        return None
    return lancamentos._com_eco(r, ouvido, avisos)


def _escolha_solta(
    conn: db.Connection,
    ctx: Contexto,
    e: Entrada,
    p: repo.Pessoa,
    texto: str,
    contexto: str,
    ouvido: str | None,
    avisos: list[Saida],
) -> Resultado:
    """Pergunta com botões respondida escrevendo (ou falando): a opção entendida vira o toque
    no botão; nenhuma → a mensagem segue como nova (a pergunta já fechou)."""
    aberta = escolha.Aberta.le(contexto)
    achou = escolha.escolhe(ctx.extrator, texto, aberta) if aberta else None
    if aberta is not None and achou is not None and achou.indice is not None:
        acao = aberta.opcoes[achou.indice][1]
        r = trata(conn, ctx, replace(e, acao=acao, texto="", audio=None), p)
        r.rotulo += ".solta" + (".ia" if achou.via == "ia" else "")
    else:
        r = trata(conn, ctx, replace(e, texto=texto, audio=None), p)
    if achou is not None and achou.tokens:
        lancamentos._conta_uso(conn, agora().date(), achou.modelo, achou.tokens, r)
    return lancamentos._com_eco(r, ouvido, avisos)


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

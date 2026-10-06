"""Lançamentos no bot (PLANO 4.1; D028, D035, D037, D038, D039).

Mensagem → entendimento (atalho sem IA ou IA) → lançamento completo vira recibo com
botões; com pendência, vira rascunho + pergunta. Correção respondendo ao recibo, apagar
com desfazer, regra aprendida e "é fixo?". O bot só mostra textos escritos pelo código:
a pergunta livre da IA é só um sinal de dúvida (nunca é exibida).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import replace
from datetime import date, timedelta
from typing import Any

from telegrana.core import atalho, cartoes, datas, faturas, fixos, valores
from telegrana.core import audio as aud
from telegrana.core import lancamentos_repo as repo
from telegrana.core import seguranca as seg
from telegrana.core import textos as t
from telegrana.core.contexto import Contexto, agora
from telegrana.core.entendimento import ErroExtracao, entende, para_prompt
from telegrana.core.extracao import CorrecaoIA
from telegrana.core.interpretacao import (
    AMBIGUOS,
    GENERICAS,
    Proposta,
    Regra,
    _ambiguo,
    _chave,
    _regra_que_casa,
    normaliza,
)
from telegrana.core.mensagens import ADMIN, Botao, Entrada, ErroCanal, Resultado, Saida, seguro
from telegrana.core.repositorio import Pessoa
from telegrana.infra import db

ORDEM = ("valor", "categoria", "data", "confirmar_valor", "duvida", "cartao", "cartao_dias")
PERGUNTAS = frozenset({"lc_valor", "lc_data", "lc_cartao", "lc_cartao_dias"})
_PERGUNTA_DA_PENDENCIA = {
    "valor": "lc_valor",
    "data": "lc_data",
    "cartao": "lc_cartao",
    "cartao_dias": "lc_cartao_dias",
}
MINUTOS_RESPOSTA_SOLTA = 10
# "paguei a fatura do nubank", "quero pagar a fatura": vai direto para a fatura (sem IA).
_PAGA_FATURA = re.compile(r"\b(paguei|pagar|paga|pago|quitei|quitar)\b.*\bfatura\b")
# "paguei a fatura da luz" é conta de consumo (lançamento comum), não fatura de cartão.
_FATURA_DE_CONSUMO = re.compile(
    r"\bfatura (da|de|do) (luz|agua|energia|internet|net|celular|telefone|gas|tv|claro|vivo"
    r"|tim|oi|condominio|escola|faculdade|academia)\b"
)
# Frase que só pode ser correção ("na verdade foi ontem"): vai direto para a correção do
# último lançamento, sem depender de a IA classificar a intenção (03/10/2026).
_PARECE_CORRECAO = re.compile(
    r"\b(na verdade|na vdd|nao era|errei|corrig\w*|o certo e|era pra ser|era para ser)\b"
)
PREFIXOS = ("lc:", "tx:", "rg:", "fx:")
LIMITE_DIARIO_TOKENS = 200_000  # por modelo, por organização, no plano gratuito (D038, D040)
ALERTA_COTA = 0.7
MODELO = "desconhecido"  # provedor que não informa o modelo
EMOJI_NOVA = {"padaria": "🥖", "bar": "🍺", "academia": "🏋️", "escola": "🏫", "beleza": "💇"}
_GENERICAS = {"expense": "outros", "income": "outros_ganhos"}


# ---------------------------------------------------------------------------
# Porta de entrada
# ---------------------------------------------------------------------------
def trata(conn: db.Connection, ctx: Contexto, e: Entrada, p: Pessoa) -> Resultado:
    if (e.acao or "").startswith(PREFIXOS):
        return _botao(conn, e, p)
    ouvido: str | None = None
    avisos: list[Saida] = []
    if e.audio is not None:
        transcrito = _transcreve(conn, ctx, e, p)
        if isinstance(transcrito, Resultado):
            return transcrito
        ouvido, avisos = transcrito
        e = replace(e, texto=ouvido, audio=None)  # daqui em diante, igual ao texto
    if e.pergunta is None and not e.resposta_a and e.texto.strip():
        # Tocou ✏️ Outro valor num lembrete e mandou só o valor, sem responder.
        from telegrana.core import lembretes  # import tardio: lembretes usa o recibo daqui

        pago = lembretes.valor_sem_responder(conn, p, e.texto)
        if pago is not None:
            return _com_eco(pago, ouvido, avisos)
    pendente = None
    if e.pergunta not in PERGUNTAS and e.texto.strip():
        with db.account_context(conn, p.account_id) as cur:
            pendente = repo.correcao_pendente(cur, p.user_id)
            if pendente is not None:
                repo.limpa_correcao(cur, p.user_id)  # vale para UMA mensagem
    if e.pergunta in PERGUNTAS:
        r = _resposta(conn, e, p)
    elif e.resposta_a:
        r = _corrige_pelo_recibo(conn, ctx, e, p)
    elif not e.texto.strip():
        return Resultado(rotulo="lancamento.sem_texto").diz(t.SO_TEXTO_OU_AUDIO)
    elif pendente is not None:
        # Tocou ✏️ Corrigir e mandou a correção sem responder: corrige AQUELE lançamento.
        r = _corrige(
            conn,
            ctx,
            p,
            pendente,
            e.texto,
            Resultado(rotulo="lancamento.correcao.pendente", conta=p.account_id),
        )
    elif (solta := _resposta_solta(conn, e, p)) is not None:
        r = solta
    else:
        r = _mensagem(conn, ctx, e, p, origem="audio" if ouvido else "text")
    return _com_eco(r, ouvido, avisos)


def _resposta_solta(conn: db.Connection, e: Entrada, p: Pessoa) -> Resultado | None:
    """Resposta a uma pergunta do bot mandada SEM "Responder" (no Telegram Web a resposta não
    abre sozinha): vale se veio em até 10 min e tem a cara da resposta (só um valor; só um
    nome de cartão; os dois dias da fatura). Senão, segue como mensagem nova."""
    with db.account_context(conn, p.account_id) as cur:
        pendencia = repo.pendencia_recente(cur, p.user_id, MINUTOS_RESPOSTA_SOLTA)
    texto = e.texto.strip()
    if pendencia == "valor":
        cabe = valores.so_valor(texto) is not None
    elif pendencia == "cartao":
        cabe = (
            len(texto.split()) <= 3
            and not re.search(r"\d", texto)
            and bool(cartoes.chave(texto))
            and cartoes.nome_valido(texto) is not None
        )
    elif pendencia == "cartao_dias":
        cabe = cartoes.dois_dias(texto) is not None
    else:
        cabe = False
    if not cabe or pendencia is None:
        return None
    r = _resposta(conn, replace(e, pergunta=_PERGUNTA_DA_PENDENCIA[pendencia]), p)
    r.rotulo += ".solta"
    return r


def _transcreve(
    conn: db.Connection, ctx: Contexto, e: Entrada, p: Pessoa
) -> tuple[str, list[Saida]] | Resultado:
    """Limites ANTES de baixar; o áudio fica só em memória e é descartado (PLANO 8.3, 8.5)."""
    audio = e.audio
    r = Resultado(rotulo="lancamento.audio", conta=p.account_id)
    if audio is None:
        return r.diz(t.AUDIO_FALHOU)
    if audio.duracao > aud.DURACAO_MAXIMA:
        r.rotulo += ".longo"
        return r.diz(t.AUDIO_LONGO)
    if audio.tamanho is not None and audio.tamanho > aud.TAMANHO_MAXIMO:
        r.rotulo += ".grande"
        return r.diz(t.AUDIO_GRANDE)
    if ctx.transcritor is None:
        r.rotulo += ".sem_transcritor"
        return r.diz(t.AUDIO_INDISPONIVEL)
    try:
        transcricao = ctx.transcritor.transcreve(audio.baixar(), audio.formato, audio.duracao)
    except ErroCanal:
        r.rotulo += ".download_falhou"
        return r.diz(t.AUDIO_FALHOU)
    except ErroExtracao as exc:
        r.rotulo += ".limite" if exc.limite else ".falhou"
        return r.diz(t.SOBRECARREGADO if exc.limite else t.AUDIO_FALHOU)
    avisos: list[Saida] = []
    if transcricao.modelo:
        modelo = transcricao.modelo.rsplit("/", 1)[-1][:40]
        pct = repo.registra_uso(
            conn,
            agora().date(),
            modelo,
            transcricao.segundos,
            aud.LIMITE_DIARIO_SEGUNDOS,
            ALERTA_COTA,
            medida="segundos",
        )
        if pct is not None:
            avisos.append(Saida(t.ADM_COTA_IA.format(pct=pct, modelo=modelo), destino=ADMIN))
    texto = " ".join(transcricao.texto.split())[: aud.LIMITE_TEXTO]
    if not texto:
        r.rotulo += ".vazio"
        r.saidas.extend(avisos)
        return r.diz(t.AUDIO_VAZIO)
    return texto, avisos


def _com_eco(r: Resultado, ouvido: str | None, avisos: list[Saida]) -> Resultado:
    """Áudio que não virou recibo: mostra o que foi ouvido (o recibo já traz a transcrição)."""
    if ouvido is None:
        return r
    r.rotulo += ".audio"
    if not any(s.ref for s in r.saidas):
        r.saidas.insert(0, Saida(t.OUVI.format(trecho=seguro(aud.resumo(ouvido), 120))))
    r.saidas.extend(avisos)
    return r


def _mensagem(
    conn: db.Connection, ctx: Contexto, e: Entrada, p: Pessoa, *, origem: str = "text"
) -> Resultado:
    hoje = agora().date()
    frase = normaliza(e.texto)
    if _PAGA_FATURA.search(frase) and not _FATURA_DE_CONSUMO.search(frase):
        return faturas.pede_pagamento(conn, p, e.texto)
    if faturas.parece_estorno(e.texto):
        return faturas.estorno(conn, p, e.texto)
    from telegrana.core import exportacao, relatorios  # tardio: → lembretes → este módulo

    if exportacao.pede_arquivo(e.texto) and (
        relatorios.parece_consulta(e.texto)
        or not any(c.isdigit() for c in e.texto)
        or re.search(r"\b(20\d{2})\b", e.texto)
    ):  # "me manda os gastos de setembro em PDF", "planilha do ano"
        return exportacao.por_frase(conn, ctx, p, e.texto)

    # "liste compra a compra" logo depois de um relatório detalha ESSE relatório; "liste meus
    # gastos de transporte" traz assunto novo e é um relatório novo (abaixo).
    if relatorios.pede_lista(e.texto) and not relatorios.parece_consulta(e.texto):
        detalhe = relatorios.detalha_ultimo(conn, p)
        if detalhe is not None:
            return detalhe
    if relatorios.parece_consulta(e.texto):  # "quanto gastei…": direto para o relatório
        return relatorios.consulta(conn, ctx, p, e.texto)
    if _PARECE_CORRECAO.search(normaliza(e.texto)):
        with db.account_context(conn, p.account_id) as cur:
            alvo = repo.ultimo(cur, p.user_id)
        r = Resultado(rotulo="lancamento.correcao.frase", conta=p.account_id)
        return _corrige(conn, ctx, p, alvo.id if alvo else None, e.texto, r)
    with db.account_context(conn, p.account_id) as cur:
        cats = repo.categorias(cur)
        regras = repo.regras(cur, cats)
    ativas = [c.para_ia() for c in cats if c.ativa]
    r = Resultado(rotulo="lancamento", conta=p.account_id)
    try:
        entendido = entende(e.texto, ativas, regras, hoje, ctx.extrator)
    except ErroExtracao as exc:
        r.rotulo = "lancamento.ia_limite" if exc.limite else "lancamento.ia_falhou"
        return r.diz(t.SOBRECARREGADO if exc.limite else t.IA_FALHOU)
    if entendido.usou_ia:
        _conta_uso(conn, hoje, entendido.modelo, entendido.tokens, r)
    interp = entendido.interpretacao
    r.rotulo = f"lancamento.{interp.intencao}" + (".ia" if entendido.usou_ia else ".atalho")
    if interp.intencao == "correcao":
        with db.account_context(conn, p.account_id) as cur:
            ultimo = repo.ultimo(cur, p.user_id)
        # A frase inteira vai para a correção (o resumo da extração perde contexto).
        return _corrige(conn, ctx, p, ultimo.id if ultimo else None, e.texto, r)
    with db.account_context(conn, p.account_id) as cur:
        if interp.intencao == "lancamentos" and interp.propostas:
            formas = repo.formas(cur)
            repete, dia = fixos.recorrencia(e.texto)
            unico = len(interp.propostas) == 1
            for prop in interp.propostas:
                dados = _dados(prop, e.texto, origem)
                if repete and unico and prop.tipo != "transfer":
                    _vira_fixo(dados, dia, so_cadastro=fixos.so_cadastro(e.texto))
                _processa(cur, p, dados, cats, formas, hoje, r)
            return r
        if interp.intencao == "apagar_ultimo":
            ultimo = repo.ultimo(cur, p.user_id)
            if ultimo is None:
                return r.diz(t.NADA_PARA_APAGAR)
            return _apaga(cur, ultimo, cats, hoje, r)
    if interp.intencao == "pagar_fatura":
        return faturas.pede_pagamento(conn, p, e.texto)
    if interp.intencao == "consulta":
        return relatorios.consulta(conn, ctx, p, e.texto)
    mensagem = {
        "conversa": t.OI,
    }.get(interp.intencao, t.NAO_ENTENDI)
    return r.diz(mensagem)


def _conta_uso(
    conn: db.Connection, hoje: date, modelo: str | None, tokens: int, r: Resultado
) -> None:
    nome = (modelo or MODELO).rsplit("/", 1)[-1][:40]
    pct = repo.registra_uso(conn, hoje, nome, tokens, LIMITE_DIARIO_TOKENS, ALERTA_COTA)
    if pct is not None:
        r.diz(t.ADM_COTA_IA.format(pct=pct, modelo=nome), destino=ADMIN)


# ---------------------------------------------------------------------------
# Proposta → lançamento ou rascunho
# ---------------------------------------------------------------------------
def _dados(prop: Proposta, texto: str, origem: str = "text") -> dict[str, Any]:
    termo = next(
        (x for x in normaliza(f"{prop.descricao or ''} {texto}").split() if x in AMBIGUOS), None
    )
    if termo is None and prop.descricao:
        curto = normaliza(prop.descricao)
        termo = curto if 0 < len(curto) <= 30 and len(curto.split()) <= 3 else None
    return {
        "tipo": prop.tipo,
        "centavos": prop.centavos,
        "data": prop.data.isoformat() if prop.data else None,
        "futura": prop.futura,
        "categoria": prop.categoria,
        "sugestoes": list(prop.sugestoes),
        "nova": prop.nova_sugerida,
        "forma": prop.forma,
        "cartao": prop.cartao,
        "parcelas": prop.parcelas,
        "descricao": seguro(prop.descricao or "", 80) or None,
        "fixo": prop.pode_ser_fixo,
        "pendencias": [x for x in ORDEM if x in prop.pendencias],
        "texto": texto[:1000],
        "origem": origem,
        "termo": termo,
        "perguntou_categoria": False,
    }


def _vira_fixo(dados: dict[str, Any], dia: int | None, *, so_cadastro: bool) -> None:
    """Frase com recorrência (D043): "aluguel 1500 todo dia 10" só cadastra o fixo;
    "paguei o aluguel 1500, todo dia 10" lança o pagamento E cadastra o fixo."""
    dados["fixo_dia"] = dia
    dados["fixo"] = False  # não pergunta "é fixo?": a pessoa já disse
    if so_cadastro:
        dados["destino"] = "fixo"
        dados["pendencias"] = [x for x in dados["pendencias"] if x != "data"]
    else:
        dados["vira_fixo"] = True


def _processa(
    cur: Any,
    p: Pessoa,
    dados: dict[str, Any],
    cats: list[repo.Categoria],
    formas: dict[str, repo.Forma],
    hoje: date,
    r: Resultado,
) -> None:
    if not dados["pendencias"]:
        falta = _falta_cartao(cur, dados)
        if falta is not None:
            dados["pendencias"] = [falta]
    if not dados["pendencias"]:
        _registra(cur, p, dados, cats, formas, hoje, r)
        return
    pendencia = dados["pendencias"][0]
    rascunho_id = repo.cria_rascunho(cur, p.account_id, p.user_id, dados, pendencia)
    if pendencia in {"cartao", "cartao_dias"}:
        r.saidas.append(_pergunta_cartao(cur, rascunho_id, pendencia, dados, cats))
    else:
        r.saidas.append(_pergunta(rascunho_id, pendencia, dados, cats))


def _falta_cartao(cur: Any, dados: dict[str, Any]) -> str | None:
    """Gasto no crédito: em qual cartão (D045)? Citado e cadastrado → ele; citado e novo →
    pergunta os dias da fatura; não citado → o único cartão, ou pergunta qual."""
    if (
        dados["tipo"] != "expense"
        or dados.get("forma") != "credito"
        or dados.get("cartao_id")
        or dados.get("destino") == "fixo"
    ):
        return None
    achado = cartoes.citado(cur, dados.get("cartao"))
    if achado is not None:
        dados["cartao_id"] = str(achado.id)
        return None
    nome = cartoes.nome_para(dados.get("cartao"))
    if nome is not None:
        dados["cartao_nome"] = nome
        return "cartao_dias"
    todos = cartoes.lista(cur)
    if len(todos) == 1:
        dados["cartao_id"] = str(todos[0].id)
        return None
    return "cartao"


def _pergunta_cartao(
    cur: Any,
    rascunho_id: uuid.UUID,
    pendencia: str,
    dados: dict[str, Any],
    cats: list[repo.Categoria],
) -> Saida:
    if pendencia == "cartao_dias":
        return cartoes.pergunta_dias(dados["cartao_nome"], "lc_cartao_dias")
    todos = cartoes.lista(cur)
    if not todos:
        return Saida(t.PERGUNTAS["lc_cartao"], pergunta="lc_cartao")
    d = seg.curto(rascunho_id)
    botoes = [Botao(f"{cartoes.EMOJI} {c.nome[:24]}", f"lc:k:{d}:{seg.curto(c.id)}") for c in todos]
    linhas: list[tuple[Botao, ...]] = [tuple(botoes[i : i + 2]) for i in range(0, len(botoes), 2)]
    linhas.append((Botao("➕ Outro cartão", f"lc:kn:{d}"), Botao("✖️ Cancelar", f"lc:x:{d}")))
    return Saida(t.PERGUNTA_CARTAO.format(resumo=_resumo(dados, cats)), botoes=tuple(linhas))


def _por_chave(cats: list[repo.Categoria], chave: str | None) -> repo.Categoria | None:
    return next((c for c in cats if c.chave == chave), None)


def _resumo(dados: dict[str, Any], cats: list[repo.Categoria]) -> str:
    cat = _por_chave(cats, dados.get("categoria"))
    partes = []
    if dados.get("centavos"):
        partes.append(valores.em_reais(dados["centavos"]))
    if cat is not None:
        partes.append(cat.rotulo)
    elif dados.get("descricao"):
        partes.append(seguro(dados["descricao"], 60))
    return " · ".join(partes) or "esse lançamento"


def _pergunta(
    rascunho_id: uuid.UUID, pendencia: str, dados: dict[str, Any], cats: list[repo.Categoria]
) -> Saida:
    d = seg.curto(rascunho_id)
    detalhe = f"\n📝 {seguro(dados['descricao'], 60)}" if dados.get("descricao") else ""
    if pendencia == "valor":
        return Saida(t.PERGUNTAS["lc_valor"] + detalhe, pergunta="lc_valor")
    if pendencia == "data":
        return Saida(t.PERGUNTAS["lc_data"] + detalhe, pergunta="lc_data")
    resumo = _resumo(dados, cats)
    if pendencia in {"confirmar_valor", "duvida"}:
        texto = t.PERGUNTA_CONFIRMAR if pendencia == "confirmar_valor" else t.PERGUNTA_DUVIDA
        rotulo = "✅ Confirmo" if pendencia == "confirmar_valor" else "✅ Registrar"
        return Saida(
            texto.format(resumo=resumo),
            botoes=((Botao(rotulo, f"lc:ok:{d}"), Botao("✖️ Cancelar", f"lc:x:{d}")),),
        )
    # categoria
    tipo = dados["tipo"]
    ativas = [c for c in cats if c.ativa and c.tipo == tipo]
    sugeridas = [c for c in (_por_chave(ativas, s) for s in dados.get("sugestoes", [])) if c]
    generica = _por_chave(ativas, _GENERICAS.get(tipo)) or next(
        (c for c in ativas if c.code == _GENERICAS.get(tipo)), None
    )
    opcoes = sugeridas or [c for c in ativas if c is not generica]
    botoes = [Botao(c.rotulo, f"lc:c:{d}:{seg.curto(c.id)}") for c in opcoes]
    linhas: list[tuple[Botao, ...]] = [tuple(botoes[i : i + 2]) for i in range(0, len(botoes), 2)]
    extras = []
    if dados.get("nova"):
        extras.append(Botao(f"➕ Criar «{seguro(dados['nova'], 25)}»", f"lc:n:{d}"))
    if generica is not None and generica not in opcoes:
        extras.append(Botao(generica.rotulo, f"lc:c:{d}:{seg.curto(generica.id)}"))
    if extras:
        linhas.append(tuple(extras))
    linhas.append((Botao("✖️ Cancelar", f"lc:x:{d}"),))
    sem_valor = {**dados, "categoria": None}
    return Saida(t.PERGUNTA_CATEGORIA.format(resumo=_resumo(sem_valor, cats)), botoes=tuple(linhas))


def _registra(
    cur: Any,
    p: Pessoa,
    dados: dict[str, Any],
    cats: list[repo.Categoria],
    formas: dict[str, repo.Forma],
    hoje: date,
    r: Resultado,
) -> uuid.UUID | None:
    tipo = dados["tipo"]
    cat = _por_chave(cats, dados.get("categoria")) if tipo != "transfer" else None
    if dados.get("destino") == "fixo":
        forma_fixo = formas.get(repo.FORMAS.get(dados.get("forma") or "", ""))
        fixo, novo = fixos.cria(
            cur,
            p,
            tipo=tipo,
            nome=fixos.nome_para(dados.get("descricao"), cat.nome if cat else None),
            categoria_id=cat.id if cat else None,
            centavos=dados["centavos"],
            valor_tipo_=fixos.valor_tipo(cat.code if cat else None, dados.get("texto", "")),
            dia=dados.get("fixo_dia") or hoje.day,
            forma_id=forma_fixo.id if forma_fixo else None,
        )
        r.saidas.append(fixos.criado(fixo, {c.id: c.emoji for c in cats}, novo))
        return None
    forma = formas.get(repo.FORMAS.get(dados.get("forma") or "", ""))
    destino = None
    if tipo == "transfer":
        destino = formas.get("savings")
        forma = forma if forma is not None and forma.kind != "savings" else None
    data = date.fromisoformat(dados["data"]) if dados.get("data") else hoje
    cartao = cartoes.por_id(cur, uuid.UUID(dados["cartao_id"])) if dados.get("cartao_id") else None
    if cartao is not None and tipo == "expense":
        tx_id = cartoes.grava_compra(
            cur,
            p,
            cartao,
            total=dados["centavos"],
            parcelas=dados.get("parcelas") or 1,
            compra=data,
            categoria_id=cat.id if cat else None,
            descricao=dados.get("descricao"),
            origem=dados.get("origem") or "text",
            texto_original=dados.get("texto", ""),
        )
    else:
        tx_id = _grava_comum(cur, p, dados, cat, forma, destino, data)
    tx = repo.lancamento(cur, tx_id)
    if tx is None:
        raise RuntimeError("lançamento recém-gravado não encontrado")
    return _depois_de_gravar(cur, p, dados, cats, tx, cat, hoje, r)


def _grava_comum(
    cur: Any,
    p: Pessoa,
    dados: dict[str, Any],
    cat: repo.Categoria | None,
    forma: repo.Forma | None,
    destino: repo.Forma | None,
    data: date,
) -> uuid.UUID:
    return repo.grava(
        cur,
        p.account_id,
        p.user_id,
        tipo=dados["tipo"],
        centavos=dados["centavos"],
        categoria_id=cat.id if cat else None,
        forma_id=forma.id if forma else None,
        destino_id=destino.id if destino else None,
        data=data,
        futura=bool(dados.get("futura")),
        descricao=dados.get("descricao"),
        origem=dados.get("origem") or "text",
        texto_original=dados.get("texto", ""),
        parcelas=dados.get("parcelas"),
    )


def _depois_de_gravar(
    cur: Any,
    p: Pessoa,
    dados: dict[str, Any],
    cats: list[repo.Categoria],
    tx: repo.Lancamento,
    cat: repo.Categoria | None,
    hoje: date,
    r: Resultado,
) -> uuid.UUID:
    tx_id = tx.id
    r.saidas.append(_recibo(cur, tx, cats, hoje, perguntar_fixo=bool(dados.get("fixo"))))
    if dados.get("vira_fixo") and tx.tipo != "transfer":
        r.saidas.append(_fixo_do_lancamento(cur, p, tx, cats, dados.get("fixo_dia")))
    termo = dados.get("termo")
    if dados.get("perguntou_categoria") and termo and cat is not None and len(termo) <= 30:
        r.diz(
            t.LEMBRAR_REGRA.format(termo=termo, rotulo=cat.rotulo),
            botoes=(
                (
                    Botao("✅ Sempre", f"rg:{seg.curto(cat.id)}:{termo}"),
                    Botao("Só desta vez", "rg:no"),
                ),
            ),
        )
    return tx_id


def _parcelas(tx: repo.Lancamento) -> str:
    n = tx.parcelas or 1
    if tx.compra is None:
        return f"{n}x"
    partes = cartoes.divide(tx.centavos, n)
    texto = f"{n}x de {valores.em_reais(partes[-1])}"
    return texto if partes[0] == partes[-1] else f"{texto} (1ª {valores.em_reais(partes[0])})"


def _quando(d: date, hoje: date) -> str:
    if d == hoje:
        return f"hoje, {d:%d/%m}"
    if d == hoje - timedelta(days=1):
        return f"ontem, {d:%d/%m}"
    return f"{d:%d/%m}" if d.year == hoje.year else f"{d:%d/%m/%Y}"


def _recibo(
    cur: Any,
    tx: repo.Lancamento,
    cats: list[repo.Categoria],
    hoje: date,
    *,
    titulo: str | None = None,
    perguntar_fixo: bool = False,
) -> Saida:
    cat = next((c for c in cats if c.id == tx.categoria_id), None)
    forma = repo.forma_por_id(cur, tx.forma_id)
    destino = repo.forma_por_id(cur, tx.destino_id)
    if titulo is None:
        if tx.compra is not None:
            titulo = t.COMPRA_CREDITO
        else:
            titulo = t.PREVISTO if tx.status == "planned" else t.REGISTRADO[tx.tipo]
    valor = valores.em_reais(tx.centavos)
    if tx.tipo == "transfer":
        linha_principal = f"{destino.emoji} {destino.nome} · {valor}" if destino else valor
    else:
        linha_principal = f"{cat.rotulo} · {valor}" if cat else valor
    detalhes = [f"{forma.emoji} {forma.nome}"] if forma else []
    if tx.parcelas and tx.parcelas > 1:
        detalhes.append(_parcelas(tx))
    detalhes.append(_quando(tx.data, hoje))
    linhas = [titulo, linha_principal, " · ".join(detalhes)]
    if tx.compra is not None and tx.fatura is not None:
        qual = "1ª parcela" if (tx.parcelas or 1) > 1 else "Entra"
        linhas.append(f"🧾 {qual} na fatura que vence {tx.fatura:%d/%m}")
    if tx.origem == "audio" and tx.texto_original:
        linhas.append(f"🎙️ «{seguro(aud.resumo(tx.texto_original), 120)}»")
    elif tx.descricao:
        linhas.append(f"📝 {seguro(tx.descricao, 80)}")
    i = seg.curto(tx.id)
    botoes: list[tuple[Botao, ...]] = [
        (
            Botao("✏️ Corrigir", f"tx:fix:{i}"),
            *((Botao("🏷️ Categoria", f"tx:cat:{i}"),) if tx.tipo != "transfer" else ()),
            Botao("🗑️ Apagar", f"tx:del:{i}"),
        )
    ]
    if perguntar_fixo and tx.recorrente is None and tx.tipo != "transfer":
        linhas.append(t.PERGUNTA_FIXO)
        botoes.append((Botao("🔁 Sim, todo mês", f"fx:s:{i}"), Botao("Não", f"fx:n:{i}")))
    return Saida("\n".join(linhas), botoes=tuple(botoes), ref=f"tx:{tx.id}")


# ---------------------------------------------------------------------------
# Botões
# ---------------------------------------------------------------------------
def _botao(conn: db.Connection, e: Entrada, p: Pessoa) -> Resultado:
    partes = (e.acao or "").split(":")
    tipo = partes[0] if partes[0] == "rg" else ":".join(partes[:2])  # rg:<id>:<termo> fica "rg"
    r = Resultado(rotulo=f"lancamento.botao.{tipo}", conta=p.account_id)
    hoje = agora().date()
    with db.account_context(conn, p.account_id) as cur:
        cats = repo.categorias(cur)
        if partes[0] == "rg":
            return _regra(cur, p, partes, cats, r)
        alvo = seg.longo(partes[2]) if len(partes) >= 3 else None
        if alvo is None:
            return r.diz(t.USE_OS_BOTOES)
        if partes[0] == "lc":
            return _botao_rascunho(cur, p, partes, alvo, cats, hoje, r)
        tx = repo.lancamento(cur, alvo)  # RLS: id de outra conta não é encontrado
        if tx is None:
            return r.diz(t.RASCUNHO_SUMIU)
        acao = f"{partes[0]}:{partes[1]}"
        if acao == "tx:fix":
            # A resposta a ESTA mensagem corrige o lançamento (como a do recibo); e, por
            # 10 minutos, a próxima mensagem também, mesmo sem responder.
            repo.marca_correcao(cur, p.account_id, p.user_id, tx.id)
            r.saidas.append(Saida(t.CORRIGIR_COMO, ref=f"tx:{tx.id}", responder=True))
            return r
        if acao == "tx:cat":
            ativas = [c for c in cats if c.ativa and c.tipo == tx.tipo]
            botoes = [Botao(c.rotulo, f"tx:sc:{partes[2]}:{seg.curto(c.id)}") for c in ativas]
            return r.diz(
                t.ESCOLHA_CATEGORIA.format(resumo=valores.em_reais(tx.centavos)),
                botoes=tuple(tuple(botoes[k : k + 2]) for k in range(0, len(botoes), 2)),
            )
        if acao == "tx:sc" and len(partes) == 4:
            nova = seg.longo(partes[3])
            cat = next((c for c in cats if c.id == nova and c.tipo == tx.tipo), None)
            if cat is None:
                return r.diz(t.CATEGORIA_SUMIU)
            repo.atualiza(cur, tx.id, "category_id", cat.id)
            return _recibo_atualizado(cur, tx.id, cats, hoje, r)
        if acao == "tx:nc" and len(partes) == 4:
            return _cria_categoria_do_recibo(cur, p, tx, partes[3], hoje, r)
        if acao == "tx:del":
            return _apaga(cur, tx, cats, hoje, r)
        if acao == "tx:un":
            repo.atualiza(cur, tx.id, "deleted", False)
            r.diz(t.DESFEITO)
            return _recibo_atualizado(cur, tx.id, cats, hoje, r, titulo=t.REGISTRADO[tx.tipo])
        if acao == "fx:n":
            repo.atualiza(cur, tx.id, "recurring", False)
            return r.diz(t.FIXO_NAO)
        if acao == "fx:s":
            if tx.tipo == "transfer":
                return r.diz(t.USE_OS_BOTOES)
            r.saidas.append(_fixo_do_lancamento(cur, p, tx, cats, None))
            return r
    return r.diz(t.USE_OS_BOTOES)


def _fixo_do_lancamento(
    cur: Any, p: Pessoa, tx: repo.Lancamento, cats: list[repo.Categoria], dia: int | None
) -> Saida:
    """Cria o fixo a partir de um lançamento (nome, valor, categoria, forma, dia) e liga os dois."""
    cat = next((c for c in cats if c.id == tx.categoria_id), None)
    fixo, novo = fixos.cria(
        cur,
        p,
        tipo=tx.tipo,
        nome=fixos.nome_para(tx.descricao, cat.nome if cat else None),
        categoria_id=tx.categoria_id,
        centavos=tx.centavos,
        valor_tipo_=fixos.valor_tipo(cat.code if cat else None, tx.texto_original or ""),
        dia=dia or tx.data.day,
        forma_id=tx.forma_id,
    )
    fixos.liga_lancamento(cur, tx.id, fixo.id)
    return fixos.criado(fixo, {c.id: c.emoji for c in cats}, novo)


def _recibo_atualizado(
    cur: Any,
    tx_id: uuid.UUID,
    cats: list[repo.Categoria],
    hoje: date,
    r: Resultado,
    *,
    titulo: str = t.CORRIGIDO,
) -> Resultado:
    tx = repo.lancamento(cur, tx_id)
    if tx is not None:
        r.saidas.append(_recibo(cur, tx, cats, hoje, titulo=titulo))
    return r


def _apaga(
    cur: Any, tx: repo.Lancamento, cats: list[repo.Categoria], hoje: date, r: Resultado
) -> Resultado:
    repo.atualiza(cur, tx.id, "deleted", True)
    cat = next((c for c in cats if c.id == tx.categoria_id), None)
    resumo = valores.em_reais(tx.centavos) + (f" · {cat.rotulo}" if cat else "")
    return r.diz(
        t.APAGADO.format(resumo=resumo),
        botoes=((Botao("↩️ Desfazer", f"tx:un:{seg.curto(tx.id)}"),),),
    )


def _regra(
    cur: Any, p: Pessoa, partes: list[str], cats: list[repo.Categoria], r: Resultado
) -> Resultado:
    if partes[1:] == ["no"] or len(partes) != 3:
        return r.diz("👍")
    cat_id = seg.longo(partes[1])
    termo = partes[2]
    cat = next((c for c in cats if c.id == cat_id), None)
    if cat is None or not re.fullmatch(r"[a-z0-9][a-z0-9 ]{1,29}", termo):
        return r.diz(t.CATEGORIA_SUMIU)
    repo.aprende(cur, p.account_id, termo, cat.id)
    return r.diz(t.REGRA_APRENDIDA.format(termo=termo, rotulo=cat.rotulo))


def _botao_rascunho(
    cur: Any,
    p: Pessoa,
    partes: list[str],
    rascunho_id: uuid.UUID,
    cats: list[repo.Categoria],
    hoje: date,
    r: Resultado,
) -> Resultado:
    achado = repo.rascunho(cur, rascunho_id)
    if achado is None:
        return r.diz(t.RASCUNHO_SUMIU)
    dados, pendencia = achado
    tipo = partes[1]
    if tipo == "x":
        repo.apaga_rascunho(cur, rascunho_id)
        return r.diz(t.RASCUNHO_CANCELADO)
    if tipo == "c" and len(partes) == 4:
        cat_id = seg.longo(partes[3])
        cat = next((c for c in cats if c.id == cat_id and c.tipo == dados["tipo"]), None)
        if cat is None or pendencia != "categoria":
            return r.diz(t.CATEGORIA_SUMIU)
        dados["categoria"], dados["perguntou_categoria"] = cat.chave, True
    elif tipo == "n" and pendencia == "categoria" and dados.get("nova"):
        nome = seguro(dados["nova"], 40)
        emoji = EMOJI_NOVA.get(normaliza(nome), "🏷️")
        novo_id = repo.cria_categoria(cur, p.account_id, dados["tipo"], nome, emoji)
        cats = repo.categorias(cur)
        cat = next((c for c in cats if c.id == novo_id), None)
        if cat is None:
            return r.diz(t.CATEGORIA_SUMIU)
        dados["categoria"], dados["perguntou_categoria"] = cat.chave, True
    elif tipo == "ok" and pendencia in {"confirmar_valor", "duvida"}:
        pass
    elif tipo == "k" and len(partes) == 4 and pendencia == "cartao":
        escolhido = cartoes.por_id(cur, seg.longo(partes[3]) or uuid.UUID(int=0))
        if escolhido is None:
            return r.diz(t.CARTAO_SUMIU)
        dados["cartao_id"] = str(escolhido.id)
    elif tipo == "kn" and pendencia == "cartao":
        return r.diz(t.PERGUNTAS["lc_cartao"], pergunta="lc_cartao")
    else:
        return r.diz(t.USE_OS_BOTOES)
    return _avanca(cur, p, rascunho_id, dados, pendencia, cats, hoje, r)


def _avanca(
    cur: Any,
    p: Pessoa,
    rascunho_id: uuid.UUID,
    dados: dict[str, Any],
    resolvida: str,
    cats: list[repo.Categoria],
    hoje: date,
    r: Resultado,
) -> Resultado:
    repo.apaga_rascunho(cur, rascunho_id)
    dados["pendencias"] = [x for x in dados["pendencias"] if x != resolvida]
    _processa(cur, p, dados, cats, repo.formas(cur), hoje, r)
    return r


def _resposta(conn: db.Connection, e: Entrada, p: Pessoa) -> Resultado:
    pendencia = {v: k for k, v in _PERGUNTA_DA_PENDENCIA.items()}[e.pergunta or "lc_data"]
    r = Resultado(rotulo=f"lancamento.resposta.{pendencia}", conta=p.account_id)
    if pendencia in {"cartao", "cartao_dias"}:
        return _resposta_cartao(conn, e, p, pendencia, r)
    hoje = agora().date()
    with db.account_context(conn, p.account_id) as cur:
        achado = repo.rascunho_mais_recente(cur, p.user_id, pendencia)
        if achado is None:
            return r.diz(t.RASCUNHO_SUMIU)
        rascunho_id, dados = achado
        cats = repo.categorias(cur)
        if pendencia == "valor":
            valor = valores.interpreta(e.texto)
            if valor.centavos is None:
                return r.diz(t.PERGUNTAS["lc_valor"], pergunta="lc_valor")
            dados["centavos"] = valor.centavos
            if valor.centavos >= 1_000_000 and "confirmar_valor" not in dados["pendencias"]:
                dados["pendencias"].append("confirmar_valor")
        else:
            quando = datas.resolve(e.texto, hoje)
            if quando.dia is None:
                return r.diz(t.PERGUNTAS["lc_data"], pergunta="lc_data")
            dados["data"], dados["futura"] = quando.dia.isoformat(), quando.futura
        return _avanca(cur, p, rascunho_id, dados, pendencia, cats, hoje, r)


def _resposta_cartao(
    conn: db.Connection, e: Entrada, p: Pessoa, pendencia: str, r: Resultado
) -> Resultado:
    hoje = agora().date()
    with db.account_context(conn, p.account_id) as cur:
        achado = repo.rascunho_mais_recente(cur, p.user_id, pendencia)
        if achado is None:
            return r.diz(t.RASCUNHO_SUMIU)
        rascunho_id, dados = achado
        cats = repo.categorias(cur)
        if pendencia == "cartao":
            nome = cartoes.nome_valido(e.texto)
            if nome is None or not cartoes.chave(nome):
                return r.diz(t.CARTAO_NOME_RUIM).diz(t.PERGUNTAS["lc_cartao"], pergunta="lc_cartao")
            dados["cartao"] = nome  # cadastrado → usa; novo → pergunta os dias (_falta_cartao)
            return _avanca(cur, p, rascunho_id, dados, pendencia, cats, hoje, r)
        dias = cartoes.dois_dias(e.texto)
        if dias is None:
            r.diz(t.DIAS_NAO_ENTENDI)
            r.saidas.append(cartoes.pergunta_dias(dados["cartao_nome"], "lc_cartao_dias"))
            return r
        cartao, _novo = cartoes.cria(cur, p, dados["cartao_nome"], *dias)
        if cartao is None:
            return r.diz(t.CARTAO_NOME_EXISTE.format(nome=dados["cartao_nome"]))
        dados["cartao_id"] = str(cartao.id)
        _avanca(cur, p, rascunho_id, dados, pendencia, cats, hoje, r)
        oferta = cartoes.oferta_antigas(cur, cartao)
        if oferta is not None:
            r.saidas.append(oferta)
        return r


# ---------------------------------------------------------------------------
# Correções
# ---------------------------------------------------------------------------
def _corrige_pelo_recibo(conn: db.Connection, ctx: Contexto, e: Entrada, p: Pessoa) -> Resultado:
    r = Resultado(rotulo="lancamento.correcao.recibo", conta=p.account_id)
    with db.account_context(conn, p.account_id) as cur:
        tx_id = repo.lancamento_do_recibo(cur, e.canal, e.resposta_a or "")
    return _corrige(conn, ctx, p, tx_id, e.texto, r)


def _corrige(
    conn: db.Connection,
    ctx: Contexto,
    p: Pessoa,
    tx_id: uuid.UUID | None,
    texto: str,
    r: Resultado,
) -> Resultado:
    """A IA interpreta a correção (D042); o código valida e aplica. Sem IA: só o código."""
    hoje = agora().date()
    if tx_id is None:
        return r.diz(t.NADA_PARA_CORRIGIR)
    with db.account_context(conn, p.account_id) as cur:
        tx = repo.lancamento(cur, tx_id)  # RLS: lançamento de outra conta não aparece
        if tx is None:
            return r.diz(t.NADA_PARA_CORRIGIR)
        cats = repo.categorias(cur)
        regras = repo.regras(cur, cats)
        atual = _descreve(cur, tx, cats)
    correcao: CorrecaoIA | None = None
    corrige = getattr(ctx.extrator, "corrige", None)
    if corrige is not None:  # chamada à IA fora da transação do banco
        try:
            correcao = corrige(
                texto, atual, para_prompt([c.para_ia() for c in cats if c.ativa]), hoje
            )
        except ErroExtracao as exc:
            r.rotulo += ".ia_limite" if exc.limite else ".ia_falhou"  # segue pelo código
        uso = getattr(ctx.extrator, "ultimo_uso", None)
        if uso is not None:
            tokens = max(0, uso.tokens_entrada - uso.tokens_em_cache) + uso.tokens_saida
            _conta_uso(conn, hoje, getattr(uso, "modelo", None), tokens, r)
    with db.account_context(conn, p.account_id) as cur:
        if correcao is not None:
            r.rotulo += ".ia"
            return _aplica_correcao_ia(cur, tx, correcao, texto, cats, regras, hoje, r)
        return _aplica_correcao(cur, tx, texto, cats, regras, hoje, r)


def _descreve(cur: Any, tx: repo.Lancamento, cats: list[repo.Categoria]) -> str:
    """Resumo do lançamento para a IA, escrito pelo código (a descrição vai como dado)."""
    cat = next((c for c in cats if c.id == tx.categoria_id), None)
    forma = repo.forma_por_id(cur, tx.forma_id)
    partes = [
        cat.nome if cat else "sem categoria",
        valores.em_reais(tx.centavos),
        forma.nome if forma else "forma não informada",
        f"{tx.data:%d/%m/%Y}",
    ]
    if tx.descricao:
        partes.append(f"descrição: {tx.descricao[:80]}")
    return " · ".join(partes)


def _aplica_correcao_ia(
    cur: Any,
    tx: repo.Lancamento,
    c: CorrecaoIA,
    texto: str,
    cats: list[repo.Categoria],
    regras: list[Regra],
    hoje: date,
    r: Resultado,
) -> Resultado:
    if not c.entendeu:
        return r.diz(t.CORRECAO_NAO_ENTENDI)
    mudou = False
    frase = normaliza(texto)
    # Valor e data: só o que estiver escrito na frase (a IA copia; o código converte).
    if c.valor_texto and normaliza(c.valor_texto) in frase:
        valor = valores.interpreta(c.valor_texto)
        if valor.centavos and valor.centavos != tx.centavos:
            repo.atualiza(cur, tx.id, "amount_cents", valor.centavos)
            mudou = True
    if c.data_texto and normaliza(c.data_texto) in frase:
        quando = datas.resolve(c.data_texto, hoje)
        if quando.dia is not None and quando.dia != tx.data:
            repo.atualiza(cur, tx.id, "cash_on", quando.dia)
            mudou = True
    if c.forma_pagamento and tx.tipo != "transfer":
        destino = repo.formas(cur).get(repo.FORMAS[c.forma_pagamento])
        if destino is not None and destino.id != tx.forma_id:
            repo.atualiza(cur, tx.id, "payment_method_id", destino.id)
            mudou = True
    if c.descricao:
        descricao = seguro(c.descricao, 80)
        if descricao and descricao != tx.descricao:
            repo.atualiza(cur, tx.id, "description", descricao)
            mudou = True
    pergunta = None
    if tx.tipo != "transfer":
        escolhida, pergunta = _categoria_da_correcao(c, tx, cats, regras)
        if escolhida is not None and escolhida.id != tx.categoria_id:
            repo.atualiza(cur, tx.id, "category_id", escolhida.id)
            mudou = True
    if mudou:
        _recibo_atualizado(cur, tx.id, cats, hoje, r)
    if pergunta is not None:
        r.saidas.append(pergunta)
    if not mudou and pergunta is None:
        return r.diz(t.CORRECAO_IGUAL)
    return r


def _categoria_da_correcao(
    c: CorrecaoIA, tx: repo.Lancamento, cats: list[repo.Categoria], regras: list[Regra]
) -> tuple[repo.Categoria | None, Saida | None]:
    """Regra da pessoa > ambíguo (pergunta) > categoria da IA > sugestões (pergunta)."""
    validas = {x.chave: x for x in cats if x.ativa and x.tipo == tx.tipo}
    para_ia = {k: x.para_ia() for k, x in validas.items()}  # aceita código ou nome
    termo = normaliza(c.termo_categoria or "")
    if termo:
        regra = _regra_que_casa(termo, regras)
        if regra is not None and regra.chave in validas:
            return validas[regra.chave], None
    ambiguo = _ambiguo(termo) if termo else None
    chave = _chave(c.categoria, para_ia)
    if chave is not None and chave not in GENERICAS and ambiguo is None:
        return validas[chave], None
    opcoes = ambiguo[0] if ambiguo else tuple(c.categorias_sugeridas)
    nova = ambiguo[1] if ambiguo else c.nova_categoria_sugerida
    sugestoes = [
        validas[k]
        for k in dict.fromkeys(_chave(o, para_ia) for o in opcoes)
        if k is not None and validas[k].id != tx.categoria_id  # "não foi no mercado"
    ]
    if chave in GENERICAS and validas[chave] not in sugestoes:
        sugestoes.append(validas[chave])
    if not sugestoes and not nova:
        return None, None  # a correção não fala de categoria
    return None, _pergunta_categoria_tx(tx, sugestoes, nova)


_NOME_CATEGORIA = re.compile(r"[^\W\d_][\w ]{1,23}")


def _pergunta_categoria_tx(
    tx: repo.Lancamento, sugestoes: list[repo.Categoria], nova: str | None
) -> Saida:
    i = seg.curto(tx.id)
    botoes = [Botao(c.rotulo, f"tx:sc:{i}:{seg.curto(c.id)}") for c in sugestoes]
    linhas: list[tuple[Botao, ...]] = [tuple(botoes[k : k + 2]) for k in range(0, len(botoes), 2)]
    extras = []
    nome = " ".join((nova or "").split())[:24]
    acao = f"tx:nc:{i}:{nome}"
    if nome and _NOME_CATEGORIA.fullmatch(nome) and len(acao.encode()) <= 64:
        extras.append(Botao(f"➕ Criar «{seguro(nome, 24)}»", acao))
    extras.append(Botao("🔎 Outra", f"tx:cat:{i}"))
    linhas.append(tuple(extras))
    return Saida(
        t.PERGUNTA_CATEGORIA_CORRECAO.format(resumo=valores.em_reais(tx.centavos)),
        botoes=tuple(linhas),
    )


def _cria_categoria_do_recibo(
    cur: Any, p: Pessoa, tx: repo.Lancamento, nome: str, hoje: date, r: Resultado
) -> Resultado:
    nome = " ".join(nome.split())
    if tx.tipo == "transfer" or not _NOME_CATEGORIA.fullmatch(nome):
        return r.diz(t.CATEGORIA_SUMIU)
    emoji = EMOJI_NOVA.get(normaliza(nome), "🏷️")
    novo_id = repo.cria_categoria(cur, p.account_id, tx.tipo, nome, emoji)
    cats = repo.categorias(cur)
    cat = next((c for c in cats if c.id == novo_id and c.tipo == tx.tipo), None)
    if cat is None:  # já existia com o mesmo nome, mas de outro tipo
        return r.diz(t.CATEGORIA_SUMIU)
    repo.atualiza(cur, tx.id, "category_id", cat.id)
    return _recibo_atualizado(cur, tx.id, cats, hoje, r)


def _aplica_correcao(
    cur: Any,
    tx: repo.Lancamento,
    texto: str,
    cats: list[repo.Categoria],
    regras: list[Regra],
    hoje: date,
    r: Resultado,
) -> Resultado:
    """Reserva sem IA: só o código lê a correção (valor, data, forma, categoria)."""
    mudou = False
    expressao = datas.expressao_em(texto)
    sem_data = texto
    if expressao:
        quando = datas.resolve(expressao, hoje)
        if quando.dia is not None:
            repo.atualiza(cur, tx.id, "cash_on", quando.dia)
            mudou = True
        sem_data = re.sub(r"\bdia \d{1,2}\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", " ", texto)
    forma, _cartao = atalho.forma_em(texto)
    if forma:
        destino = repo.formas(cur).get(repo.FORMAS[forma])
        if destino is not None:
            repo.atualiza(cur, tx.id, "payment_method_id", destino.id)
            mudou = True
    if re.search(r"\d", sem_data):
        valor = valores.interpreta(sem_data)
        if valor.centavos is not None:
            repo.atualiza(cur, tx.id, "amount_cents", valor.centavos)
            mudou = True
    if tx.tipo != "transfer":
        validas = {c.chave: c for c in cats if c.ativa and c.tipo == tx.tipo}
        regra = _regra_que_casa(texto, regras)  # o que a pessoa ensinou vale primeiro
        cat = validas.get(regra.chave) if regra else None
        if cat is None:
            alvo = f" {normaliza(texto)} "
            cat = next((c for c in validas.values() if f" {normaliza(c.nome)} " in alvo), None)
        if cat is None:
            chave = next(
                (atalho.PALAVRAS[x] for x in normaliza(texto).split() if x in atalho.PALAVRAS),
                None,
            )
            cat = next((c for c in validas.values() if c.code == chave), None)
        if cat is not None and cat.id != tx.categoria_id:
            repo.atualiza(cur, tx.id, "category_id", cat.id)
            mudou = True
    if not mudou:
        return r.diz(t.CORRECAO_NAO_ENTENDI)
    return _recibo_atualizado(cur, tx.id, cats, hoje, r)

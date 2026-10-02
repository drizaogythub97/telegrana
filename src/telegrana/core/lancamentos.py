"""Lançamentos no bot (PLANO 4.1; D028, D035, D037, D038, D039).

Mensagem → entendimento (atalho sem IA ou IA) → lançamento completo vira recibo com
botões; com pendência, vira rascunho + pergunta. Correção respondendo ao recibo, apagar
com desfazer, regra aprendida e "é fixo?". O bot só mostra textos escritos pelo código:
a pergunta livre da IA é só um sinal de dúvida (nunca é exibida).
"""

from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from typing import Any

from telegrana.core import atalho, datas, valores
from telegrana.core import lancamentos_repo as repo
from telegrana.core import seguranca as seg
from telegrana.core import textos as t
from telegrana.core.contexto import Contexto, agora
from telegrana.core.entendimento import ErroExtracao, entende
from telegrana.core.interpretacao import AMBIGUOS, Proposta, normaliza
from telegrana.core.mensagens import ADMIN, Botao, Entrada, Resultado, Saida, seguro
from telegrana.core.repositorio import Pessoa
from telegrana.infra import db

ORDEM = ("valor", "categoria", "data", "confirmar_valor", "duvida")
PERGUNTAS = frozenset({"lc_valor", "lc_data"})
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
    if e.pergunta in PERGUNTAS:
        return _resposta(conn, e, p)
    if e.resposta_a:
        return _corrige_pelo_recibo(conn, e, p)
    if not e.texto.strip():
        return Resultado(rotulo="lancamento.sem_texto").diz(t.AUDIO_EM_BREVE)
    return _mensagem(conn, ctx, e, p)


def _mensagem(conn: db.Connection, ctx: Contexto, e: Entrada, p: Pessoa) -> Resultado:
    hoje = agora().date()
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
        modelo = (entendido.modelo or MODELO).rsplit("/", 1)[-1][:40]
        pct = repo.registra_uso(
            conn, hoje, modelo, entendido.tokens, LIMITE_DIARIO_TOKENS, ALERTA_COTA
        )
        if pct is not None:
            r.diz(t.ADM_COTA_IA.format(pct=pct, modelo=modelo), destino=ADMIN)
    interp = entendido.interpretacao
    r.rotulo = f"lancamento.{interp.intencao}" + (".ia" if entendido.usou_ia else ".atalho")
    with db.account_context(conn, p.account_id) as cur:
        if interp.intencao == "lancamentos" and interp.propostas:
            formas = repo.formas(cur)
            for prop in interp.propostas:
                _processa(cur, p, _dados(prop, e.texto), cats, formas, hoje, r)
            return r
        if interp.intencao == "correcao":
            return _corrige_ultimo(cur, p, interp.correcao_texto or e.texto, cats, hoje, r)
        if interp.intencao == "apagar_ultimo":
            ultimo = repo.ultimo(cur, p.user_id)
            if ultimo is None:
                return r.diz(t.NADA_PARA_APAGAR)
            return _apaga(cur, ultimo, cats, hoje, r)
    mensagem = {
        "consulta": t.CONSULTA_EM_BREVE,
        "pagar_fatura": t.FATURA_EM_BREVE,
        "conversa": t.OI,
    }.get(interp.intencao, t.NAO_ENTENDI)
    return r.diz(mensagem)


# ---------------------------------------------------------------------------
# Proposta → lançamento ou rascunho
# ---------------------------------------------------------------------------
def _dados(prop: Proposta, texto: str) -> dict[str, Any]:
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
        "parcelas": prop.parcelas,
        "descricao": seguro(prop.descricao or "", 80) or None,
        "fixo": prop.pode_ser_fixo,
        "pendencias": [x for x in ORDEM if x in prop.pendencias],
        "texto": texto[:1000],
        "termo": termo,
        "perguntou_categoria": False,
    }


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
        _registra(cur, p, dados, cats, formas, hoje, r)
        return
    pendencia = dados["pendencias"][0]
    rascunho_id = repo.cria_rascunho(cur, p.account_id, p.user_id, dados, pendencia)
    r.saidas.append(_pergunta(rascunho_id, pendencia, dados, cats))


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
) -> uuid.UUID:
    tipo = dados["tipo"]
    cat = _por_chave(cats, dados.get("categoria")) if tipo != "transfer" else None
    forma = formas.get(repo.FORMAS.get(dados.get("forma") or "", ""))
    destino = None
    if tipo == "transfer":
        destino = formas.get("savings")
        forma = forma if forma is not None and forma.kind != "savings" else None
    data = date.fromisoformat(dados["data"]) if dados.get("data") else hoje
    tx_id = repo.grava(
        cur,
        p.account_id,
        p.user_id,
        tipo=tipo,
        centavos=dados["centavos"],
        categoria_id=cat.id if cat else None,
        forma_id=forma.id if forma else None,
        destino_id=destino.id if destino else None,
        data=data,
        futura=bool(dados.get("futura")),
        descricao=dados.get("descricao"),
        origem="text",
        texto_original=dados.get("texto", ""),
        parcelas=dados.get("parcelas"),
    )
    tx = repo.lancamento(cur, tx_id)
    if tx is None:
        raise RuntimeError("lançamento recém-gravado não encontrado")
    r.saidas.append(_recibo(cur, tx, cats, hoje, perguntar_fixo=bool(dados.get("fixo"))))
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
        titulo = t.PREVISTO if tx.status == "planned" else t.REGISTRADO[tx.tipo]
    valor = valores.em_reais(tx.centavos)
    if tx.tipo == "transfer":
        linha_principal = f"{destino.emoji} {destino.nome} · {valor}" if destino else valor
    else:
        linha_principal = f"{cat.rotulo} · {valor}" if cat else valor
    detalhes = [f"{forma.emoji} {forma.nome}"] if forma else []
    if tx.parcelas and tx.parcelas > 1:
        detalhes.append(f"{tx.parcelas}x")
    detalhes.append(_quando(tx.data, hoje))
    linhas = [titulo, linha_principal, " · ".join(detalhes)]
    if tx.descricao:
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
            return r.diz(t.CORRIGIR_COMO)
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
        if acao == "tx:del":
            return _apaga(cur, tx, cats, hoje, r)
        if acao == "tx:un":
            repo.atualiza(cur, tx.id, "deleted", False)
            r.diz(t.DESFEITO)
            return _recibo_atualizado(cur, tx.id, cats, hoje, r, titulo=t.REGISTRADO[tx.tipo])
        if acao in {"fx:s", "fx:n"}:
            repo.atualiza(cur, tx.id, "recurring", acao == "fx:s")
            return r.diz(t.FIXO_SIM if acao == "fx:s" else t.FIXO_NAO)
    return r.diz(t.USE_OS_BOTOES)


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
    pendencia = "valor" if e.pergunta == "lc_valor" else "data"
    r = Resultado(rotulo=f"lancamento.resposta.{pendencia}", conta=p.account_id)
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


# ---------------------------------------------------------------------------
# Correções
# ---------------------------------------------------------------------------
def _corrige_pelo_recibo(conn: db.Connection, e: Entrada, p: Pessoa) -> Resultado:
    r = Resultado(rotulo="lancamento.correcao.recibo", conta=p.account_id)
    hoje = agora().date()
    with db.account_context(conn, p.account_id) as cur:
        tx_id = repo.lancamento_do_recibo(cur, e.canal, e.resposta_a or "")
        tx = repo.lancamento(cur, tx_id) if tx_id else None
        if tx is None:
            return r.diz(t.NADA_PARA_CORRIGIR)
        cats = repo.categorias(cur)
        return _aplica_correcao(cur, tx, e.texto, cats, hoje, r)


def _corrige_ultimo(
    cur: Any, p: Pessoa, texto: str, cats: list[repo.Categoria], hoje: date, r: Resultado
) -> Resultado:
    tx = repo.ultimo(cur, p.user_id)
    if tx is None:
        return r.diz(t.NADA_PARA_CORRIGIR)
    return _aplica_correcao(cur, tx, texto, cats, hoje, r)


def _aplica_correcao(
    cur: Any,
    tx: repo.Lancamento,
    texto: str,
    cats: list[repo.Categoria],
    hoje: date,
    r: Resultado,
) -> Resultado:
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
        alvo = f" {normaliza(texto)} "
        cat = next(
            (c for c in cats if c.ativa and c.tipo == tx.tipo and f" {normaliza(c.nome)} " in alvo),
            None,
        )
        if cat is None:
            chave = next(
                (atalho.PALAVRAS[x] for x in normaliza(texto).split() if x in atalho.PALAVRAS),
                None,
            )
            cat = next((c for c in cats if c.code == chave and c.tipo == tx.tipo), None)
        if cat is not None and cat.id != tx.categoria_id:
            repo.atualiza(cur, tx.id, "category_id", cat.id)
            mudou = True
    if not mudou:
        return r.diz(t.CORRECAO_NAO_ENTENDI)
    return _recibo_atualizado(cur, tx.id, cats, hoje, r)

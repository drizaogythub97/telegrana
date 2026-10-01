"""Categorias da conta: /categorias (PLANO 4.2; D035, D036).

Criar, renomear, trocar emoji, desativar e reativar. Categoria nunca é apagada (os
lançamentos antigos continuam apontando para ela). "Outros" e "Outros ganhos" não podem
ser desativadas: são o destino quando a pessoa escolhe "nenhuma destas".
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any

from psycopg import errors

from telegrana.core import repositorio as repo
from telegrana.core import seguranca as seg
from telegrana.core import textos as t
from telegrana.core.contexto import Contexto
from telegrana.core.mensagens import Botao, Entrada, Resultado, seguro
from telegrana.infra import db

FIXAS = frozenset({"outros", "outros_ganhos"})
EMOJI_PADRAO = "🏷️"
_NOME = re.compile(r"[\w][\w .,/&+()-]{0,39}")
PERGUNTAS = frozenset({"cat_nova_gasto", "cat_nova_ganho", "cat_renomear", "cat_emoji"})


@dataclass(frozen=True, slots=True)
class Categoria:
    id: uuid.UUID
    kind: str
    code: str | None
    name: str
    emoji: str
    active: bool

    @property
    def rotulo(self) -> str:
        return f"{self.emoji} {self.name}"


# ---------------------------------------------------------------------------
# Banco (dentro de db.account_context)
# ---------------------------------------------------------------------------
def lista(cur: Any) -> list[Categoria]:
    rows = cur.execute(
        "select id, kind, code, name, emoji, active from telegrana.categories"
        " order by kind, active desc, sort, lower(name)"
    ).fetchall()
    return [Categoria(*r) for r in rows]


def por_id(cur: Any, categoria_id: uuid.UUID) -> Categoria | None:
    row = cur.execute(
        "select id, kind, code, name, emoji, active from telegrana.categories where id = %s",
        (categoria_id,),
    ).fetchone()
    return Categoria(*row) if row else None


def por_rotulo(cur: Any, rotulo: str) -> Categoria | None:
    return next((c for c in lista(cur) if c.rotulo == rotulo.strip()), None)


def _cria(cur: Any, account_id: uuid.UUID, kind: str, nome: str, emoji: str) -> bool:
    try:
        with cur.connection.transaction():  # savepoint: nome repetido não derruba a transação
            cur.execute(
                "insert into telegrana.categories (account_id, kind, name, emoji)"
                " values (%s, %s, %s, %s)",
                (account_id, kind, nome, emoji),
            )
    except errors.UniqueViolation:
        return False
    return True


def _atualiza(cur: Any, categoria_id: uuid.UUID, campo: str, valor: object) -> bool:
    if campo not in {"name", "emoji", "active"}:
        raise ValueError(campo)
    sql = {
        "name": "update telegrana.categories set name = %s where id = %s",
        "emoji": "update telegrana.categories set emoji = %s where id = %s",
        "active": "update telegrana.categories set active = %s where id = %s",
    }[campo]
    try:
        with cur.connection.transaction():
            cur.execute(sql, (valor, categoria_id))
    except errors.UniqueViolation:
        return False
    return True


# ---------------------------------------------------------------------------
# Entrada de texto: emoji + nome
# ---------------------------------------------------------------------------
def _eh_emoji(caractere: str) -> bool:
    if caractere in {"‍", "️", "⃣"}:  # ZWJ, seletor de variação, tecla
        return True
    return unicodedata.category(caractere) in {"So", "Sk"} or 0x1F000 <= ord(caractere) <= 0x1FAFF


def separa_emoji(texto: str) -> tuple[str | None, str]:
    """("🏋️", "Academia") de "🏋️ Academia", "Academia 🏋️" ou "Academia" (emoji None)."""
    limpo = " ".join(texto.split())
    inicio = 0
    while inicio < len(limpo) and _eh_emoji(limpo[inicio]):
        inicio += 1
    if inicio:
        return limpo[:inicio], limpo[inicio:].strip()
    fim = len(limpo)
    while fim > 0 and _eh_emoji(limpo[fim - 1]):
        fim -= 1
    if fim < len(limpo):
        return limpo[fim:], limpo[:fim].strip()
    return None, limpo


def emoji_valido(texto: str) -> str | None:
    emoji = texto.strip()
    if not 1 <= len(emoji) <= 8 or not all(_eh_emoji(c) for c in emoji):
        return None
    return emoji


def nome_valido(texto: str) -> str | None:
    nome = seguro(" ".join(texto.split()), 60)
    if not _NOME.fullmatch(nome):
        return None
    return nome[0].upper() + nome[1:]


# ---------------------------------------------------------------------------
# Telas
# ---------------------------------------------------------------------------
def _tela(categorias: list[Categoria]) -> str:
    def linha(kind: str) -> str:
        ativas = [c.rotulo for c in categorias if c.kind == kind and c.active]
        return " · ".join(ativas) or "—"

    desativadas = [c.rotulo for c in categorias if not c.active]
    texto = (
        "🏷️ **Suas categorias**\n\n"
        f"🔴 **Gastos**\n{linha('expense')}\n\n"
        f"🟢 **Ganhos**\n{linha('income')}"
    )
    if desativadas:
        texto += "\n\n🚫 Desativadas: " + " · ".join(desativadas)
    return texto


def _botoes_de(categorias: list[Categoria]) -> tuple[tuple[Botao, ...], ...]:
    botoes = [
        Botao(c.rotulo if c.active else f"🚫 {c.name}", f"cat:ed:{seg.curto(c.id)}")
        for c in categorias
    ]
    return tuple(tuple(botoes[i : i + 2]) for i in range(0, len(botoes), 2))


def _detalhe(c: Categoria) -> tuple[str, tuple[tuple[Botao, ...], ...]]:
    tipo = "gasto" if c.kind == "expense" else "ganho"
    situacao = "ativa" if c.active else "desativada"
    linha = [
        Botao("✏️ Renomear", f"cat:ren:{seg.curto(c.id)}"),
        Botao("🎨 Emoji", f"cat:emo:{seg.curto(c.id)}"),
    ]
    if c.code not in FIXAS:
        linha.append(
            Botao("🚫 Desativar", f"cat:off:{seg.curto(c.id)}")
            if c.active
            else Botao("✅ Reativar", f"cat:on:{seg.curto(c.id)}")
        )
    return f"{c.emoji} **{seguro(c.name)}** · categoria de {tipo}, {situacao}", (tuple(linha),)


# ---------------------------------------------------------------------------
# Fluxo
# ---------------------------------------------------------------------------
def trata(conn: db.Connection, ctx: Contexto, e: Entrada, p: repo.Pessoa) -> Resultado:
    r = Resultado(rotulo="categorias")
    if e.comando == "categorias":
        with db.account_context(conn, p.account_id) as cur:
            todas = lista(cur)
        return r.diz(
            _tela(todas),
            botoes=((Botao("➕ Nova categoria", "cat:nova"), Botao("✏️ Editar", "cat:edit")),),
        )
    if e.pergunta in PERGUNTAS:
        return _resposta(conn, e, p, r)
    partes = (e.acao or "").split(":")
    if partes[:2] == ["cat", "nova"] and len(partes) == 2:
        return r.diz(
            "Que tipo de categoria?",
            botoes=((Botao("🔴 De gasto", "cat:nova:e"), Botao("🟢 De ganho", "cat:nova:i")),),
        )
    if partes[:2] == ["cat", "nova"] and len(partes) == 3:
        pergunta = "cat_nova_gasto" if partes[2] == "e" else "cat_nova_ganho"
        return r.diz(t.PERGUNTAS[pergunta], pergunta=pergunta)
    if partes == ["cat", "edit"]:
        with db.account_context(conn, p.account_id) as cur:
            todas = lista(cur)
        return r.diz("Qual categoria você quer editar?", botoes=_botoes_de(todas))
    if len(partes) != 3 or partes[1] not in {"ed", "ren", "emo", "off", "on"}:
        return r.diz(t.USE_OS_BOTOES)
    categoria_id = seg.longo(partes[2])
    with db.account_context(conn, p.account_id) as cur:
        # RLS: um id de outra conta (botão forjado) simplesmente não é encontrado.
        c = por_id(cur, categoria_id) if categoria_id else None
        if c is None:
            return r.diz(t.CATEGORIA_SUMIU)
        if partes[1] == "ed":
            texto, botoes = _detalhe(c)
            return r.diz(texto, botoes=botoes)
        if partes[1] == "ren":
            return r.diz(f"{t.PERGUNTAS['cat_renomear']}\n{c.rotulo}", pergunta="cat_renomear")
        if partes[1] == "emo":
            return r.diz(f"{t.PERGUNTAS['cat_emoji']}\n{c.rotulo}", pergunta="cat_emoji")
        if c.code in FIXAS:
            return r.diz(t.CATEGORIA_FIXA.format(rotulo=c.rotulo))
        ativa = partes[1] == "on"
        _atualiza(cur, c.id, "active", ativa)
    return r.diz(
        (t.CATEGORIA_REATIVADA if ativa else t.CATEGORIA_DESATIVADA).format(rotulo=c.rotulo)
    )


def _resposta(conn: db.Connection, e: Entrada, p: repo.Pessoa, r: Resultado) -> Resultado:
    if e.pergunta in {"cat_nova_gasto", "cat_nova_ganho"}:
        emoji, resto = separa_emoji(e.texto)
        nome = nome_valido(resto)
        if nome is None:
            return r.diz(t.CATEGORIA_NOME_INVALIDO).diz(
                t.PERGUNTAS[e.pergunta or ""], pergunta=e.pergunta
            )
        kind = "expense" if e.pergunta == "cat_nova_gasto" else "income"
        emoji = emoji or EMOJI_PADRAO
        with db.account_context(conn, p.account_id) as cur:
            criada = _cria(cur, p.account_id, kind, nome, emoji)
        if not criada:
            return r.diz(t.CATEGORIA_JA_EXISTE.format(nome=nome))
        return r.diz(t.CATEGORIA_CRIADA.format(rotulo=f"{emoji} {nome}"))

    with db.account_context(conn, p.account_id) as cur:
        c = por_rotulo(cur, e.contexto)  # a 2ª linha da pergunta: escrita pelo próprio bot
        if c is None:
            return r.diz(t.CATEGORIA_SUMIU)
        if e.pergunta == "cat_renomear":
            _, resto = separa_emoji(e.texto)
            nome = nome_valido(resto)
            if nome is None:
                return r.diz(t.CATEGORIA_NOME_INVALIDO)
            if not _atualiza(cur, c.id, "name", nome):
                return r.diz(t.CATEGORIA_JA_EXISTE.format(nome=nome))
            return r.diz(t.CATEGORIA_RENOMEADA.format(rotulo=f"{c.emoji} {nome}"))
        emoji = emoji_valido(e.texto)
        if emoji is None:
            return r.diz(t.CATEGORIA_EMOJI_INVALIDO)
        _atualiza(cur, c.id, "emoji", emoji)
    return r.diz(t.CATEGORIA_RENOMEADA.format(rotulo=f"{emoji} {c.name}"))


# Espelho das categorias padrão da migração 0003 (seed_account_defaults). Usado pela
# avaliação da IA; um teste garante que as duas listas são iguais.
PADROES: tuple[tuple[str, str, str, str], ...] = (
    ("expense", "mercado", "Mercado", "🛒"),
    ("expense", "alimentacao", "Alimentação fora", "🍽️"),
    ("expense", "moradia", "Moradia", "🏠"),
    ("expense", "contas_casa", "Contas da casa", "💡"),
    ("expense", "transporte", "Transporte", "🚗"),
    ("expense", "combustivel", "Combustível", "⛽"),
    ("expense", "saude", "Saúde", "💊"),
    ("expense", "educacao", "Educação", "📚"),
    ("expense", "lazer", "Lazer", "🎮"),
    ("expense", "vestuario", "Vestuário", "👕"),
    ("expense", "assinaturas", "Assinaturas", "📱"),
    ("expense", "pets", "Pets", "🐾"),
    ("expense", "filhos", "Filhos", "👶"),
    ("expense", "presentes", "Presentes", "🎁"),
    ("expense", "encargos", "Encargos e juros", "💸"),
    ("expense", "outros", "Outros", "📦"),
    ("income", "salario", "Salário", "💼"),
    ("income", "servicos", "Serviços/Freela", "🧾"),
    ("income", "rendimentos", "Rendimentos", "📈"),
    ("income", "reembolso", "Reembolso", "↩️"),
    ("income", "outros_ganhos", "Outros ganhos", "🎉"),
)

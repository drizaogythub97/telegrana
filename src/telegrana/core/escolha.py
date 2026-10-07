"""Resposta escrita (ou falada) a uma pergunta com botões (07/10/2026).

O bot pergunta com botões ("Quer que eu lembre…? [✅ Sempre] [Só desta vez]", a categoria,
"Isso se repete todo mês?"). Quem responde escrevendo — "exato", "pode ser", "assinatura" —
tem de ser entendido como quem toca no botão. A pergunta fica guardada (pendência `pergunta`
= "escolha", com o texto e as opções) e vale para a próxima mensagem solta:

  1. o código resolve o óbvio (sim/não, o nome exato de uma opção);
  2. o resto vai para a IA com a pergunta e as opções (ela só aponta um número);
  3. nada escolhido → a mensagem segue como mensagem nova.

A opção escolhida vira a mesma `Entrada.acao` do botão: os tratadores revalidam tudo, como
num toque (dado de botão já é tratado como não confiável). Perguntas que apagam, geram
código, aceitam termos ou são do admin ficam de fora: essas só com toque.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from telegrana.core.entendimento import ErroExtracao
from telegrana.core.interpretacao import normaliza
from telegrana.core.mensagens import Saida

PERGUNTA = "escolha"
MAX_OPCOES = 40
MAX_PALAVRAS = 12
# Só com toque: a pergunta inteira fica de fora se tiver um botão destes.
_SO_TOQUE = ("apagar", "cod:", "adm:", "termos:", "cad:", "rec:")

SIM = frozenset(
    {
        "sim", "s", "ss", "isso", "isso mesmo", "isso ai", "exato", "exatamente", "claro",
        "claro que sim", "com certeza", "certeza", "pode", "pode sim", "pode ser", "ok", "okay",
        "certo", "correto", "beleza", "blz", "perfeito", "confirmo", "confirma", "quero",
        "sim quero", "uhum", "aham", "yes", "bora", "fechado", "show", "top", "isso msm",
        "sim por favor", "por favor", "manda", "pode mandar",
    }
)  # fmt: skip
NAO = frozenset(
    {
        "nao", "n", "nao quero", "nao obrigado", "nao obrigada", "negativo", "deixa",
        "deixa pra la", "nem", "agora nao", "melhor nao", "cancela", "cancelar", "nope",
    }
)  # fmt: skip
GRATIDAO = frozenset(
    {
        "obrigado", "obrigada", "obg", "brigado", "brigada", "valeu", "vlw", "muito obrigado",
        "muito obrigada", "obrigadao", "agradecido", "agradecida", "valeu mesmo", "tmj",
    }
)  # fmt: skip
_ACEITA = ("sim", "sempre", "pronto", "confirmar", "paguei", "recebi", "quero")
_RECUSA = ("nao", "so desta vez", "cancelar", "agora nao")


@dataclass(frozen=True, slots=True)
class Aberta:
    """A pergunta com botões que ficou sem toque: texto e opções (rótulo, ação)."""

    pergunta: str
    opcoes: tuple[tuple[str, str], ...]

    def guarda(self) -> str:
        return json.dumps({"q": self.pergunta, "o": self.opcoes}, ensure_ascii=False)

    @staticmethod
    def le(contexto: str) -> Aberta | None:
        try:
            dados = json.loads(contexto)
            opcoes = tuple((str(r), str(a)) for r, a in dados["o"])
            return Aberta(str(dados["q"]), opcoes) if opcoes else None
        except ValueError, KeyError, TypeError:
            return None


@dataclass(frozen=True, slots=True)
class Escolha:
    indice: int | None  # posição em `Aberta.opcoes`
    via: str  # "codigo" | "ia" | "nenhuma"
    modelo: str | None = None
    tokens: int = 0


def da_saida(saidas: Iterable[Saida]) -> Aberta | None:
    """A última mensagem com botões da resposta, se ela for uma pergunta ("…?")."""
    for s in reversed(list(saidas)):
        if s.destino is not None or not s.botoes:
            continue
        opcoes = [(b.rotulo, b.acao) for linha in s.botoes for b in linha if b.acao]
        if not opcoes:
            continue
        linhas = [x.strip() for x in s.texto.replace("**", "").splitlines() if x.strip()]
        if not linhas or not linhas[-1].endswith("?"):
            return None
        pergunta = " ".join(linhas)
        if any(a.startswith(_SO_TOQUE) for _, a in opcoes) or "apagar" in normaliza(pergunta):
            return None
        opcoes = [(r, a) for r, a in opcoes if "🗑" not in r]  # apagar o lançamento: só tocando
        if not opcoes or len(opcoes) > MAX_OPCOES:
            return None
        return Aberta(pergunta[:500], tuple(opcoes))
    return None


def _primeira(rotulo: str, inicios: tuple[str, ...]) -> bool:
    n = normaliza(rotulo)
    return any(n == x or n.startswith(f"{x} ") for x in inicios)


def rapida(texto: str, aberta: Aberta) -> int | None:
    """O óbvio, sem IA: o nome exato de uma opção, ou sim/não com UMA opção que aceita/recusa."""
    n = normaliza(texto)
    rotulos = [normaliza(r) for r, _ in aberta.opcoes]
    iguais = [i for i, x in enumerate(rotulos) if x and x == n]
    if len(iguais) == 1:
        return iguais[0]
    if n in SIM or (not n and "👍" in texto):
        alvo = [
            i
            for i, (r, _) in enumerate(aberta.opcoes)
            if r.lstrip().startswith("✅") or _primeira(r, _ACEITA)
        ]
    elif n in NAO:
        alvo = [
            i
            for i, (r, _) in enumerate(aberta.opcoes)
            if r.lstrip().startswith(("✖️", "❌")) or _primeira(r, _RECUSA)
        ]
    else:
        return None
    return alvo[0] if len(alvo) == 1 else None


def plausivel(texto: str, aberta: Aberta) -> bool:
    """Vale perguntar à IA? Mensagem longa ou com número que nenhuma opção tem (um gasto
    novo, "uber 20") segue direto como mensagem nova."""
    palavras = normaliza(texto).split()
    if not palavras or len(palavras) > MAX_PALAVRAS:
        return False
    tem_numero = any(c.isdigit() for c in texto)
    return not tem_numero or any(any(c.isdigit() for c in r) for r, _ in aberta.opcoes)


def escolhe(extrator: Any, texto: str, aberta: Aberta) -> Escolha:
    indice = rapida(texto, aberta)
    if indice is not None:
        return Escolha(indice, "codigo")
    pergunta = getattr(extrator, "escolha", None)
    if pergunta is None or not plausivel(texto, aberta):
        return Escolha(None, "nenhuma")
    try:  # a IA aponta um número; quem executa é o código
        ia, modelo = pergunta(aberta.pergunta, [r for r, _ in aberta.opcoes], texto)
    except ErroExtracao:
        return Escolha(None, "nenhuma")
    uso = getattr(extrator, "ultimo_uso", None)
    tokens = max(0, uso.tokens_entrada - uso.tokens_em_cache) + uso.tokens_saida if uso else 0
    ok = ia.opcao is not None and 1 <= ia.opcao <= len(aberta.opcoes)
    return Escolha(ia.opcao - 1 if ok and ia.opcao else None, "ia", modelo, tokens)


def concordancia(texto: str) -> str | None:
    """Sem pergunta aberta: "exato", "ok", "valeu" não são lançamento nem cumprimento."""
    n = normaliza(texto)
    if n in GRATIDAO:
        return "gratidao"
    if n in SIM or (not n and "👍" in texto):
        return "sim"
    if n in NAO:
        return "nao"
    return None

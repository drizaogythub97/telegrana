"""Limites de uso por pessoa (S8, PLANO 8.6, D051).

Para que ninguém (nem algo automatizado) esgote a cota gratuita do Groq de todos. Decisão
do Adriano (08/10/2026), valores "folgados" em `contexto.Limites`. Um contador por conta e
dia (`account_usage`, fuso de São Paulo), só com números.

- Mensagens (texto, áudio, comando): por minuto e por dia. Botão não conta.
- Chamadas à IA: contadas por um invólucro do provedor (`Contador`) durante o tratamento;
  passou do limite → a IA fica fora até o dia seguinte (o atalho sem IA continua valendo).
- Áudio: segundos por dia, conferidos ANTES de transcrever.
- Arquivos exportados: por dia.

Ao bater um limite, o bot avisa uma vez (o primeiro excesso); os seguintes, no mesmo minuto
ou dia, são ignorados em silêncio. O administrador não tem limite.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from telegrana.core import textos as t
from telegrana.core.contexto import Contexto, agora
from telegrana.core.entendimento import ErroLimiteConta
from telegrana.core.mensagens import Entrada, Resultado
from telegrana.core.repositorio import Pessoa
from telegrana.infra import db

# Chamadas do provedor de IA que contam (core.entendimento.Extrator e os pedidos à parte).
_CHAMADAS = frozenset({"extrai", "corrige", "consulta", "escolha", "conversa"})

_REGISTRA = (
    "insert into telegrana.account_usage (account_id, day, messages, minute, minute_messages)"
    " values (%(conta)s, %(dia)s, 1, %(minuto)s, 1)"
    " on conflict (account_id, day) do update set"
    " messages = account_usage.messages + 1,"
    " minute_messages = case when account_usage.minute = %(minuto)s"
    " then account_usage.minute_messages + 1 else 1 end,"
    " minute = %(minuto)s"
    " returning messages, minute_messages, ai_calls, audio_seconds, exports"
)
_LE = (
    "select messages, minute_messages, ai_calls, audio_seconds, exports"
    " from telegrana.account_usage where day = %(dia)s"
)
_SOMA = (
    "insert into telegrana.account_usage (account_id, day, ai_calls, audio_seconds, exports)"
    " values (%(conta)s, %(dia)s, %(ia)s, %(audio)s, %(arquivos)s)"
    " on conflict (account_id, day) do update set"
    " ai_calls = account_usage.ai_calls + excluded.ai_calls,"
    " audio_seconds = account_usage.audio_seconds + excluded.audio_seconds,"
    " exports = account_usage.exports + excluded.exports"
)


@dataclass(frozen=True, slots=True)
class Uso:
    mensagens: int = 0
    no_minuto: int = 0
    ia: int = 0
    audio: int = 0
    arquivos: int = 0


class Contador:
    """O provedor de IA desta mensagem, contando as chamadas. Bloqueado = limite do dia
    batido: toda chamada falha como limite (quem chamou cai no caminho sem IA)."""

    def __init__(self, base: Any, *, bloqueado: bool) -> None:
        self._base = base
        self._bloqueado = bloqueado
        self.chamadas = 0

    def __getattr__(self, nome: str) -> Any:
        alvo = getattr(self._base, nome)
        if nome not in _CHAMADAS or not callable(alvo):
            return alvo

        def chama(*args: Any, **kwargs: Any) -> Any:
            if self._bloqueado:
                raise ErroLimiteConta("limite de IA da conta")
            self.chamadas += 1
            return alvo(*args, **kwargs)

        return chama


def _eh_mensagem(e: Entrada) -> bool:
    return e.acao is None and bool(e.texto.strip() or e.audio is not None or e.comando)


def _pede_arquivo(e: Entrada) -> bool:
    from telegrana.core import exportacao  # tardio: exportacao puxa relatórios e lançamentos

    if (e.acao or "").startswith(exportacao.PREFIXO):
        return True
    return e.acao is None and bool(e.texto) and exportacao.pede_arquivo(e.texto)


def _uso(row: Any) -> Uso:
    return Uso(*(int(x) for x in row)) if row else Uso()


def antes(
    conn: db.Connection, ctx: Contexto, p: Pessoa, e: Entrada, *, admin: bool
) -> tuple[Resultado | None, Contexto, Contador | None]:
    """Conta a mensagem e confere os limites. Devolve (resposta que encerra aqui ou None,
    contexto com a IA contada, contador)."""
    if admin:
        return None, ctx, None
    lim = ctx.limites
    momento = agora()
    minuto = momento.replace(second=0, microsecond=0)
    params = {"conta": p.account_id, "dia": momento.date(), "minuto": minuto}
    mensagem = _eh_mensagem(e)
    with db.account_context(conn, p.account_id) as cur:
        uso = _uso(cur.execute(_REGISTRA if mensagem else _LE, params).fetchone())
    if mensagem and (uso.no_minuto > lim.por_minuto or uso.mensagens > lim.por_dia):
        r = Resultado(rotulo="limite.mensagens", conta=p.account_id)
        if uso.no_minuto > lim.por_minuto:
            return (r.diz(t.LIMITE_MINUTO) if uso.no_minuto == lim.por_minuto + 1 else r), ctx, None
        aviso = t.LIMITE_DIA.format(n=lim.por_dia)
        return (r.diz(aviso) if uso.mensagens == lim.por_dia + 1 else r), ctx, None
    if e.audio is not None and uso.audio + e.audio.duracao > lim.audio_segundos:
        texto = t.LIMITE_AUDIO.format(minutos=lim.audio_segundos // 60)
        return Resultado(rotulo="limite.audio", conta=p.account_id).diz(texto), ctx, None
    if uso.arquivos >= lim.arquivos and _pede_arquivo(e):
        texto = t.LIMITE_ARQUIVOS.format(n=lim.arquivos)
        return Resultado(rotulo="limite.arquivos", conta=p.account_id).diz(texto), ctx, None
    if ctx.extrator is None:
        return None, ctx, None
    contador = Contador(ctx.extrator, bloqueado=uso.ia >= lim.ia)
    return None, replace(ctx, extrator=contador), contador


def depois(
    conn: db.Connection, p: Pessoa, e: Entrada, r: Resultado, contador: Contador | None
) -> None:
    """Soma o que a mensagem gastou: chamadas à IA, segundos de áudio e arquivos."""
    ia = contador.chamadas if contador else 0
    audio = e.audio.duracao if e.audio is not None else 0
    arquivos = sum(1 for s in r.saidas if s.arquivo is not None)
    if not (ia or audio or arquivos):
        return
    params = {
        "conta": p.account_id,
        "dia": agora().date(),
        "ia": ia,
        "audio": audio,
        "arquivos": arquivos,
    }
    with db.account_context(conn, p.account_id) as cur:
        cur.execute(_SOMA, params)


def hoje(conn: db.Connection, account_id: Any, dia: date | None = None) -> Uso:
    """O uso do dia (para testes e para o /meus_dados no futuro)."""
    with db.account_context(conn, account_id) as cur:
        row = cur.execute(_LE, {"dia": dia or agora().date()}).fetchone()
    return _uso(row)

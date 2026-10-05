"""Lembretes dos fixos (PLANO 4.3 e 4.4; D043, D044).

A rotina roda às 09:00 e às 20:00 (São Paulo). Para cada fixo ativo, no horário que a
pessoa escolheu, cabe no máximo UM lembrete por vez:
  * no dia do vencimento ("vence hoje");
  * na véspera ("vence amanhã");
  * todo dia depois do vencimento, até ✅ Paguei/Recebi ou ⏭️ Pular — e só até o próximo
    vencimento chegar.
O fixo não gera lançamento sozinho: o lançamento nasce no ✅ Paguei (valor do fixo) ou no
✏️ Outro valor (valor informado). Um vencimento só se resolve uma vez (`fixed_occurrences`)
e um lembrete só sai uma vez por dia e horário (`reminder_sends`): toque duplo e rotina
repetida não duplicam nada.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import psycopg

from telegrana.core import fixos, valores
from telegrana.core import lancamentos_repo as lrepo
from telegrana.core import seguranca as seg
from telegrana.core import textos as t
from telegrana.core.contexto import Contexto, agora
from telegrana.core.fixos import Fixo
from telegrana.core.lancamentos import _recibo
from telegrana.core.mensagens import Botao, Entrada, Resultado, Saida, seguro
from telegrana.core.repositorio import Pessoa
from telegrana.infra import db

log = logging.getLogger("telegrana.lembretes")

PREFIXO = "lm:"
PERGUNTAS = frozenset({"lm_valor"})
MARCA = "🔔"  # 2ª linha da pergunta de valor: "🔔 <nome> · dd/mm/aaaa"
ANTECEDENCIA_PAGAMENTO = 7  # pagamento ligado ao fixo até 7 dias antes conta para o mês
JANELA_BOTAO = 62  # dias: botão de lembrete mais velho que isso não vale
MESES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


@dataclass(frozen=True, slots=True)
class Lembrete:
    fixo: Fixo
    vencimento: date
    regra: str  # before | on_day | after


# ---------------------------------------------------------------------------
# Regras (puras)
# ---------------------------------------------------------------------------
def horario_de(momento: datetime) -> str:
    """A rotina das 09:00 é a da manhã; a das 20:00, a da noite (com folga para atrasos)."""
    return "morning" if momento.hour < 14 else "evening"


def _mes(d: date, deslocamento: int) -> tuple[int, int]:
    total = d.year * 12 + d.month - 1 + deslocamento
    return total // 12, total % 12 + 1


def vencimentos_perto(dia: int, hoje: date) -> tuple[date | None, date]:
    """(último vencimento antes de hoje, próximo vencimento a partir de hoje)."""
    datas = [fixos.vencimento(dia, *_mes(hoje, k)) for k in (-1, 0, 1)]
    anterior = max((d for d in datas if d < hoje), default=None)
    proximo = min(d for d in datas if d >= hoje)
    return anterior, proximo


def resolvido(vencimento: date, resolvidos: set[date], pagamentos: Iterable[date]) -> bool:
    """Pago ou pulado pelo lembrete, ou já lançado e ligado ao fixo naquele mês (ex.: "paguei
    a internet 120 todo dia 5" cria o fixo e o lançamento juntos)."""
    if vencimento in resolvidos:
        return True
    inicio = vencimento - timedelta(days=ANTECEDENCIA_PAGAMENTO)
    return any(
        (p.year, p.month) == (vencimento.year, vencimento.month) or inicio <= p < vencimento
        for p in pagamentos
    )


def devido(
    f: Fixo,
    hoje: date,
    horario: str,
    resolvidos: Iterable[date] = (),
    pagamentos: Iterable[date] = (),
) -> Lembrete | None:
    if not f.ativo or f.horario not in {horario, "both"}:
        return None
    feitos, pagos = set(resolvidos), list(pagamentos)
    anterior, proximo = vencimentos_perto(f.dia, hoje)
    if proximo == hoje:
        # No dia do vencimento só cabe o "vence hoje" (o atraso do mês passado para aqui).
        if f.no_dia and not resolvido(proximo, feitos, pagos):
            return Lembrete(f, proximo, "on_day")
        return None
    if proximo == hoje + timedelta(days=1) and f.antes and not resolvido(proximo, feitos, pagos):
        return Lembrete(f, proximo, "before")
    if (
        anterior is not None
        and f.depois
        and (f.desde is None or anterior >= f.desde)  # cadastrado depois: não cobra o passado
        and not resolvido(anterior, feitos, pagos)
    ):
        return Lembrete(f, anterior, "after")
    return None


def mes_de(d: date) -> str:
    return MESES[d.month - 1]


# ---------------------------------------------------------------------------
# Mensagem do lembrete
# ---------------------------------------------------------------------------
def _data(d: date) -> str:
    return f"{d:%d/%m}"


def saida(lb: Lembrete, emoji: str, destino: str) -> Saida:
    f = lb.fixo
    titulo = t.LEMBRETE[(f.tipo, lb.regra)].format(
        emoji=emoji, nome=seguro(f.nome, 40), data=_data(lb.vencimento)
    )
    valor = t.LEMBRETE_VALOR[f.valor_tipo].format(valor=valores.em_reais(f.centavos))
    chave = f"{seg.curto(f.id)}:{lb.vencimento:%Y%m%d}"
    pago = "✅ Recebi" if f.tipo == "income" else "✅ Paguei"
    return Saida(
        f"{titulo}\n{valor}",
        destino=destino,
        botoes=(
            (Botao(pago, f"lm:pg:{chave}"), Botao("✏️ Outro valor", f"lm:ov:{chave}")),
            (Botao("⏭️ Pular este mês", f"lm:pl:{chave}"),),
        ),
    )


# ---------------------------------------------------------------------------
# SQL (fixo, parametrizado; sempre dentro de db.account_context)
# ---------------------------------------------------------------------------
def _resolvidos(cur: Any, desde: date) -> dict[uuid.UUID, set[date]]:
    rows = cur.execute(
        "select fixed_item_id, due_date from telegrana.fixed_occurrences where due_date >= %s",
        (desde,),
    ).fetchall()
    achados: dict[uuid.UUID, set[date]] = {}
    for fixo_id, vencimento in rows:
        achados.setdefault(fixo_id, set()).add(vencimento)
    return achados


def _pagamentos(cur: Any, desde: date) -> dict[uuid.UUID, list[date]]:
    rows = cur.execute(
        "select x.fixed_item_id, x.cash_on from telegrana.transactions x"
        " where x.fixed_item_id is not null and x.deleted_at is null and x.cash_on >= %s"
        # O ✅ Paguei já resolveu o mês dele: não pode valer também para o mês em que foi tocado.
        " and not exists (select 1 from telegrana.fixed_occurrences o"
        " where o.transaction_id = x.id)",
        (desde,),
    ).fetchall()
    achados: dict[uuid.UUID, list[date]] = {}
    for fixo_id, dia in rows:
        achados.setdefault(fixo_id, []).append(dia)
    return achados


def _destino(cur: Any, canal: str) -> str | None:
    row = cur.execute(
        "select c.external_id from telegrana.user_channels c"
        " join telegrana.account_members m on m.user_id = c.user_id"
        " where m.role = 'owner' and c.channel = %s",
        (canal,),
    ).fetchone()
    return str(row[0]) if row else None


def _marca_envio(cur: Any, account_id: uuid.UUID, lb: Lembrete, hoje: date, horario: str) -> bool:
    """Grava ANTES de enviar: na dúvida, um lembrete a menos, nunca um repetido."""
    row = cur.execute(
        "insert into telegrana.reminder_sends (account_id, fixed_item_id, due_date, rule,"
        " sent_on, slot) values (%s, %s, %s, %s, %s, %s)"
        " on conflict (account_id, fixed_item_id, sent_on, slot) do nothing returning id",
        (account_id, lb.fixo.id, lb.vencimento, lb.regra, hoje, horario),
    ).fetchone()
    return row is not None


def da_conta(cur: Any, account_id: uuid.UUID, canal: str, hoje: date, horario: str) -> list[Saida]:
    destino = _destino(cur, canal)
    if destino is None:
        return []
    inicio = hoje - timedelta(days=70)
    resolvidos = _resolvidos(cur, inicio)
    pagamentos = _pagamentos(cur, inicio)
    emojis = {r[0]: r[1] for r in cur.execute("select id, emoji from telegrana.categories")}
    saidas = []
    for f in fixos.lista(cur):
        lb = devido(f, hoje, horario, resolvidos.get(f.id, set()), pagamentos.get(f.id, []))
        if lb is None or not _marca_envio(cur, account_id, lb, hoje, horario):
            continue
        emoji = emojis.get(f.categoria_id, fixos.MARCA) if f.categoria_id else fixos.MARCA
        saidas.append(saida(lb, emoji, destino))
    return saidas


def da_rotina(conn: db.Connection, canal: str, momento: datetime) -> tuple[list[Saida], int]:
    """Lembretes de todas as contas para este horário. Devolve (saídas, contas com falha).

    Cada conta numa transação própria: a falha de uma não impede as outras.
    """
    hoje, horario = momento.date(), horario_de(momento)
    with conn.transaction():
        contas = [
            r[0]
            for r in conn.execute(
                "select o_account_id from telegrana.accounts_with_reminders()"
            ).fetchall()
        ]
    saidas: list[Saida] = []
    falhas = 0
    for account_id in contas:
        try:
            with db.account_context(conn, account_id) as cur:
                saidas.extend(da_conta(cur, account_id, canal, hoje, horario))
        except psycopg.Error as exc:
            falhas += 1
            log.error("lembretes.conta_falhou", extra={"erro": type(exc).__name__})
    return saidas, falhas


# ---------------------------------------------------------------------------
# Botões do lembrete e resposta do "Outro valor"
# ---------------------------------------------------------------------------
_DATA = re.compile(r"\d{8}")


def _vencimento(texto: str, hoje: date) -> date | None:
    if not _DATA.fullmatch(texto):
        return None
    try:
        d = date(int(texto[:4]), int(texto[4:6]), int(texto[6:]))
    except ValueError:
        return None
    return d if abs((d - hoje).days) <= JANELA_BOTAO else None


def trata(conn: db.Connection, ctx: Contexto, e: Entrada, p: Pessoa) -> Resultado:
    r = Resultado(rotulo="lembrete", conta=p.account_id)
    hoje = agora().date()
    if e.pergunta in PERGUNTAS:
        return _resposta(conn, e, p, hoje, r)
    partes = (e.acao or "").split(":")
    if len(partes) != 4:
        return r.diz(t.USE_OS_BOTOES)
    _, acao, curto, quando = partes
    r.rotulo = f"lembrete.{acao}"
    fixo_id = seg.longo(curto)
    vencimento = _vencimento(quando, hoje)
    if vencimento is None:
        return r.diz(t.LEMBRETE_INVALIDO)
    with db.account_context(conn, p.account_id) as cur:
        f = fixos.por_id(cur, fixo_id) if fixo_id else None  # RLS: outra conta não acha
        if f is None:
            return r.diz(t.FIXO_SUMIU)
        if acao == "pg":
            return _paga(cur, p, f, vencimento, f.centavos, hoje, r)
        if acao == "ov":
            if _ja_resolvido(cur, f, vencimento):
                return r.diz(_ja(f, vencimento))
            return r.diz(
                f"{t.PERGUNTAS['lm_valor']}\n{MARCA} {f.nome} · {vencimento:%d/%m/%Y}",
                pergunta="lm_valor",
            )
        if acao == "pl":
            if not _resolve(cur, p, f, vencimento, "skipped"):
                return r.diz(_ja(f, vencimento))
            return r.diz(t.LEMBRETE_PULADO.format(nome=seguro(f.nome, 40), mes=mes_de(vencimento)))
    return r.diz(t.USE_OS_BOTOES)


def _resposta(conn: db.Connection, e: Entrada, p: Pessoa, hoje: date, r: Resultado) -> Resultado:
    r.rotulo = "lembrete.valor"
    nome, _, quando = e.contexto.removeprefix(MARCA).strip().rpartition(" · ")
    achado = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", quando)
    vencimento = _vencimento(f"{achado[3]}{achado[2]}{achado[1]}", hoje) if achado else None
    if not nome or vencimento is None:
        return r.diz(t.LEMBRETE_INVALIDO)
    with db.account_context(conn, p.account_id) as cur:
        f = fixos.por_nome(cur, nome)
        if f is None:
            return r.diz(t.FIXO_SUMIU)
        valor = valores.interpreta(e.texto)
        if not valor.centavos:
            return r.diz(
                f"{t.PERGUNTAS['lm_valor']}\n{MARCA} {f.nome} · {vencimento:%d/%m/%Y}",
                pergunta="lm_valor",
            )
        return _paga(cur, p, f, vencimento, valor.centavos, hoje, r)


def _ja(f: Fixo, vencimento: date) -> str:
    return t.LEMBRETE_JA_RESOLVIDO.format(nome=seguro(f.nome, 40), mes=mes_de(vencimento))


def _ja_resolvido(cur: Any, f: Fixo, vencimento: date) -> bool:
    inicio = vencimento - timedelta(days=40)
    return resolvido(
        vencimento,
        _resolvidos(cur, inicio).get(f.id, set()),
        _pagamentos(cur, inicio).get(f.id, []),
    )


def _resolve(cur: Any, p: Pessoa, f: Fixo, vencimento: date, situacao: str) -> uuid.UUID | None:
    """Marca o vencimento como resolvido; None se já estava (toque duplo, outro botão)."""
    if _ja_resolvido(cur, f, vencimento):
        return None
    row = cur.execute(
        "insert into telegrana.fixed_occurrences (account_id, fixed_item_id, due_date, status)"
        " values (%s, %s, %s, %s)"
        " on conflict (account_id, fixed_item_id, due_date) do nothing returning id",
        (p.account_id, f.id, vencimento, situacao),
    ).fetchone()
    return uuid.UUID(str(row[0])) if row else None


def _paga(
    cur: Any, p: Pessoa, f: Fixo, vencimento: date, centavos: int, hoje: date, r: Resultado
) -> Resultado:
    ocorrencia = _resolve(cur, p, f, vencimento, "paid")
    if ocorrencia is None:
        return r.diz(_ja(f, vencimento))
    tx_id = lrepo.grava(
        cur,
        p.account_id,
        p.user_id,
        tipo=f.tipo,
        centavos=centavos,
        categoria_id=f.categoria_id,
        forma_id=f.forma_id,
        destino_id=None,
        data=hoje,
        futura=False,
        descricao=f.nome,
        origem="fixed",
        texto_original="",
        parcelas=None,
    )
    fixos.liga_lancamento(cur, tx_id, f.id)
    cur.execute(
        "update telegrana.fixed_occurrences set transaction_id = %s where id = %s",
        (tx_id, ocorrencia),
    )
    tx = lrepo.lancamento(cur, tx_id)
    if tx is None:
        raise RuntimeError("lançamento recém-gravado não encontrado")
    r.saidas.append(_recibo(cur, tx, lrepo.categorias(cur), hoje))
    return r

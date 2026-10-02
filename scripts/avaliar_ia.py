#!/usr/bin/env python3
"""Avalia a extração (IA + código) contra o gabarito (PLANO 5.3; D036).

Uso local (lê tests/eval/data/ e a chave GROQ_API_KEY_DEV do .env.local):
    uv run python scripts/avaliar_ia.py
No CI: `--baixar` busca o conjunto no bucket privado e `--chave-ssm` lê a chave de dev.

Imprime SÓ métricas e ids de caso: o repositório e os logs do Actions são públicos e as
frases do conjunto nunca podem aparecer (D016). Sai com erro se ficar abaixo das metas:
valor, tipo e data ≥ 95%; categoria ≥ 90%; intenção ≥ 90%.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from telegrana.ai.groq import ErroIA, Groq  # noqa: E402
from telegrana.core.categorias import PADROES  # noqa: E402
from telegrana.core.entendimento import entende  # noqa: E402
from telegrana.core.interpretacao import CategoriaConta, Proposta  # noqa: E402

HOJE = date(2026, 10, 1)  # data de referência do gabarito
ESPERA_MAXIMA = 120.0  # espera maior que isso = cota do dia acabou: parar, não insistir
METAS = {"valor": 0.95, "tipo": 0.95, "data": 0.95, "categoria": 0.90, "intencao": 0.90}
_TIPO = {"gasto": "expense", "ganho": "income", "transferencia": "transfer"}


@dataclass
class Placar:
    acertos: dict[str, int] = field(default_factory=dict)
    total: dict[str, int] = field(default_factory=dict)
    falhas: dict[str, list[str]] = field(default_factory=dict)

    def conta(self, metrica: str, ok: bool, caso: str) -> None:
        self.total[metrica] = self.total.get(metrica, 0) + 1
        if ok:
            self.acertos[metrica] = self.acertos.get(metrica, 0) + 1
        else:
            self.falhas.setdefault(metrica, []).append(caso)

    def taxa(self, metrica: str) -> float:
        total = self.total.get(metrica, 0)
        return self.acertos.get(metrica, 0) / total if total else 1.0


def _categoria_ok(esperada: Any, p: Proposta) -> bool:
    if esperada is None:
        return p.categoria is None
    aceitas = esperada if isinstance(esperada, list) else [esperada]
    if p.categoria is None:
        return "?" in aceitas
    return p.categoria in aceitas


def _avalia_caso(caso: dict[str, Any], interpretacao: Any, placar: Placar) -> None:
    id_ = caso["id"]
    placar.conta("intencao", interpretacao.intencao in caso["intencoes"], id_)
    esperados = caso["lancamentos"]
    if "lancamentos" not in caso["intencoes"] or not esperados:
        return
    previstos = list(interpretacao.propostas)
    if caso.get("aceita_so_pergunta") and not previstos and interpretacao.pergunta:
        # Perguntar antes de registrar também está certo neste caso (ex.: total acumulado).
        for metrica in ("quantidade", "tipo", "valor", "data", "categoria", "pergunta (info)"):
            placar.conta(metrica, True, id_)
        return
    placar.conta("quantidade", len(previstos) == len(esperados), id_)
    for i, esperado in enumerate(esperados):
        p = previstos[i] if i < len(previstos) else None
        rotulo = f"{id_}#{i + 1}"
        placar.conta("tipo", p is not None and p.tipo == _TIPO[esperado["tipo"]], rotulo)
        placar.conta("valor", p is not None and p.centavos == esperado["valor"], rotulo)
        data = date.fromisoformat(esperado["data"]) if esperado["data"] else None
        placar.conta("data", p is not None and p.data == data, rotulo)
        placar.conta("categoria", p is not None and _categoria_ok(esperado["categoria"], p), rotulo)
        if esperado["forma"] is not None:
            placar.conta("forma (info)", p is not None and p.forma == esperado["forma"], rotulo)
        if esperado["parcelas"] is not None:
            placar.conta(
                "parcelas (info)", p is not None and p.parcelas == esperado["parcelas"], rotulo
            )
        if esperado["fixo"] is not None:
            placar.conta(
                "fixo (info)", p is not None and p.pode_ser_fixo == esperado["fixo"], rotulo
            )
    perguntou = any(not p.completa for p in previstos) or interpretacao.pergunta is not None
    placar.conta("pergunta (info)", perguntou == caso["perguntar"], id_)


def _chave(args: argparse.Namespace) -> str:
    if args.chave_ssm:
        import boto3

        ssm = boto3.client("ssm", region_name="us-east-1")
        nome = "/telegrana/dev/groq/api_key"
        return str(ssm.get_parameter(Name=nome, WithDecryption=True)["Parameter"]["Value"])
    if os.environ.get("GROQ_API_KEY"):
        return os.environ["GROQ_API_KEY"]
    for linha in (RAIZ / ".env.local").read_text(encoding="utf-8-sig").splitlines():
        chave, _, valor = linha.partition("=")
        if chave.strip() == args.chave_local:
            return valor.strip()
    raise SystemExit(f"{args.chave_local} não encontrada no .env.local")


def _baixa(bucket: str, destino: Path) -> None:
    import boto3

    s3 = boto3.client("s3", region_name="us-east-1")
    s3.download_file(bucket, "gabarito.jsonl", str(destino / "gabarito.jsonl"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dados", type=Path, default=RAIZ / "tests" / "eval" / "data")
    parser.add_argument("--baixar", metavar="BUCKET", help="baixa o conjunto do bucket privado")
    parser.add_argument("--chave-ssm", action="store_true", help="lê a chave de dev no SSM")
    parser.add_argument(
        "--chave-local",
        default="GROQ_API_KEY_DEV",
        help="variável do .env.local (GROQ_API_KEY_PROD só enquanto a produção não tem uso real)",
    )
    parser.add_argument(
        "--intervalo", type=float, default=9.0, help="segundos entre chamadas (8 mil tokens/min)"
    )
    parser.add_argument("--casos", nargs="*", help="só estes ids (ex.: t01 a07)")
    parser.add_argument("--prazo", type=float, default=1500.0, help="segundos até parar")
    parser.add_argument(
        "--espera-maxima",
        type=float,
        default=ESPERA_MAXIMA,
        help="maior espera aceita num limite do Groq; acima disso, para (inconclusiva)",
    )
    parser.add_argument("--resultado", type=Path, help="grava o placar em JSON (sem frases)")
    parser.add_argument(
        "--continuar",
        type=Path,
        help="retoma de um --resultado anterior (pula os casos já avaliados e soma o placar)",
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as temporario:
        pasta = args.dados
        if args.baixar:
            pasta = Path(temporario)
            _baixa(args.baixar, pasta)
        casos = [
            json.loads(linha)
            for linha in (pasta / "gabarito.jsonl").read_text(encoding="utf-8").splitlines()
            if linha.strip()
        ]
    if args.casos:
        casos = [c for c in casos if c["id"] in set(args.casos)]
    anterior: dict[str, Any] = {}
    if args.continuar and args.continuar.exists():
        anterior = json.loads(args.continuar.read_text(encoding="utf-8"))
        feitos = set(anterior.get("avaliados", []))
        casos = [c for c in casos if c["id"] not in feitos]

    categorias = [CategoriaConta(code, nome, emoji, tipo) for tipo, code, nome, emoji in PADROES]
    groq = Groq(_chave(args))
    chamadas_ia = 0
    placar = Placar(
        dict(anterior.get("acertos", {})),
        dict(anterior.get("total", {})),
        {m: list(f) for m, f in anterior.get("falhas", {}).items()},
    )
    feitos_ids: list[str] = list(anterior.get("avaliados", []))
    tokens = {"entrada": 0, "saida": 0, "cache": 0}
    erros: list[str] = []
    inicio = time.monotonic()
    avaliados, motivo_parada = 0, ""
    for n, caso in enumerate(casos, 1):
        if time.monotonic() - inicio > args.prazo:
            motivo_parada = f"prazo de {args.prazo:.0f}s esgotado"
            break
        entendido = None
        for tentativa in range(12):
            try:
                # O mesmo caminho do bot: atalho sem IA primeiro, IA só quando precisa.
                entendido = entende(caso["texto"], categorias, [], HOJE, groq)
                break
            except ErroIA as exc:
                if exc.limite and (exc.espera or 0) > args.espera_maxima:
                    motivo_parada = "cota diária do Groq esgotada"
                    break
                if not exc.limite or tentativa == 11:
                    erros.append(f"{caso['id']}: {exc}")
                    break
                print(f"  {caso['id']}: limite do Groq, aguardando", flush=True)
                time.sleep(min(args.espera_maxima, (exc.espera or 10.0) + 1))
        if motivo_parada:
            break
        avaliados += 1
        feitos_ids.append(caso["id"])
        if entendido is None:
            placar.conta("intencao", False, caso["id"])
            continue
        if entendido.usou_ia and groq.ultimo_uso:
            chamadas_ia += 1
            tokens["entrada"] += groq.ultimo_uso.tokens_entrada
            tokens["saida"] += groq.ultimo_uso.tokens_saida
            tokens["cache"] += groq.ultimo_uso.tokens_em_cache
        antes = {m: len(f) for m, f in placar.falhas.items()}
        _avalia_caso(caso, entendido.interpretacao, placar)
        erradas = sorted(
            m for m, f in placar.falhas.items() if len(f) > antes.get(m, 0)
        )  # só nomes de métricas e o id: nunca a frase
        print(
            f"  {caso['id']}: {'ok' if not erradas else 'falhou ' + ', '.join(erradas)}", flush=True
        )
        if n < len(casos) and entendido.usou_ia:
            time.sleep(args.intervalo)

    print(
        f"Avaliação: {avaliados}/{len(casos)} casos nesta rodada em"
        f" {time.monotonic() - inicio:.0f}s; {len(feitos_ids)} no total"
    )
    print(f"Chamadas à IA: {chamadas_ia} (o resto foi pelo atalho sem IA)")
    print(
        f"Tokens: entrada {tokens['entrada']} (cache {tokens['cache']}), saída {tokens['saida']};"
        f" contados no limite ~{tokens['entrada'] - tokens['cache'] + tokens['saida']}"
    )
    reprovado = False
    for metrica in sorted(placar.total, key=lambda m: (m.endswith("(info)"), m)):
        taxa = placar.taxa(metrica)
        meta = METAS.get(metrica)
        situacao = (
            "" if meta is None else (" ok" if taxa >= meta else f" ABAIXO DA META {meta:.0%}")
        )
        reprovado |= meta is not None and taxa < meta
        falhas = ", ".join(placar.falhas.get(metrica, [])) or "-"
        print(
            f"  {metrica:<16} {taxa:6.1%} ({placar.acertos.get(metrica, 0)}/"
            f"{placar.total[metrica]}){situacao}  falhas: {falhas}"
        )
    if erros:
        print("Erros da IA:", "; ".join(erros))
        reprovado = True
    if motivo_parada:
        print(f"INCONCLUSIVA: {motivo_parada}; {len(casos) - avaliados} casos sem avaliar.")
    if args.resultado:
        args.resultado.write_text(
            json.dumps(
                {
                    "taxas": {m: placar.taxa(m) for m in placar.total},
                    "acertos": placar.acertos,
                    "total": placar.total,
                    "falhas": placar.falhas,
                    "avaliados": feitos_ids,
                    "tokens": tokens,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    if motivo_parada:
        return 2
    return 1 if reprovado else 0


if __name__ == "__main__":
    sys.exit(main())

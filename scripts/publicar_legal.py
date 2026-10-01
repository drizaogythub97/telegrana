#!/usr/bin/env python3
"""Publica os Termos de Uso e a Política de Privacidade no Telegraph e registra no SSM.

Uso (na raiz, com `aws login --profile telegrana` ativo):
    uv run python scripts/publicar_legal.py --contato @usuario_do_admin

Para cada documento (`legal/termos-vN.md` e `legal/privacidade-vN.md`, maior N):
- preenche `{{data_vigencia}}` (data da 1ª publicação da versão) e `{{contato_admin}}`;
- calcula o SHA-256 do texto **sem** o contato (trocar o contato não exige novo aceite:
  LGPD art. 8º, §6º só cita os incisos I, II, III e V do art. 9º; D032);
- publica (ou mantém, se nada mudou) e grava em `/telegrana/<env>/legal/<doc>` o JSON
  {versao, url, path, sha256, vigencia}. Também grava `/telegrana/<env>/admin/contact`.

Uma versão já publicada só tem o texto alterado com --corrigir-versao (use só antes de
qualquer aceite; depois, crie a versão N+1). O token da conta do Telegraph fica em
`/telegrana/telegraph_token` (SecureString).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import boto3  # noqa: E402

from telegrana.infra import telegraph  # noqa: E402

REGIAO = "us-east-1"
AMBIENTES = ("dev", "prod")
DOCUMENTOS = ("termos", "privacidade")
TOKEN_SSM = "/telegrana/telegraph_token"  # noqa: S105  # nosec B105 — caminho no SSM, não o valor


def _ssm() -> object:
    sessao = boto3.Session(
        profile_name=os.environ.get("AWS_PROFILE", "telegrana-sdk"), region_name=REGIAO
    )
    return sessao.client("ssm")


def _le(ssm: object, nome: str, *, segredo: bool = False) -> str | None:
    try:
        resposta = ssm.get_parameter(Name=nome, WithDecryption=segredo)  # type: ignore[attr-defined]
    except ssm.exceptions.ParameterNotFound:  # type: ignore[attr-defined]
        return None
    return str(resposta["Parameter"]["Value"])


def _grava(ssm: object, nome: str, valor: str, *, segredo: bool = False) -> None:
    ssm.put_parameter(  # type: ignore[attr-defined]
        Name=nome,
        Value=valor,
        Type="SecureString" if segredo else "String",
        Overwrite=True,
        Tier="Standard",
    )
    print(f"  gravado: {nome}")


def _ultima_versao(doc: str) -> tuple[int, Path]:
    candidatos = []
    for arquivo in (RAIZ / "legal").glob(f"{doc}-v*.md"):
        achado = re.fullmatch(rf"{doc}-v(\d+)\.md", arquivo.name)
        if achado:
            candidatos.append((int(achado.group(1)), arquivo))
    if not candidatos:
        raise SystemExit(f"nenhum legal/{doc}-vN.md")
    return max(candidatos)


def _token(ssm: object) -> str:
    token = _le(ssm, TOKEN_SSM, segredo=True)
    if token:
        return token
    conta = telegraph.chama("createAccount", short_name="Telegrana", author_name="Telegrana")
    _grava(ssm, TOKEN_SSM, conta["access_token"], segredo=True)
    print("  conta do Telegraph criada")
    return str(conta["access_token"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contato", required=True, help="como falar com o admin, ex.: @usuario")
    parser.add_argument("--corrigir-versao", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"@[A-Za-z0-9_]{5,32}", args.contato):
        raise SystemExit("--contato precisa ser um @ do Telegram")

    ssm = _ssm()
    token = _token(ssm)
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y")
    for ambiente in AMBIENTES:
        _grava(ssm, f"/telegrana/{ambiente}/admin/contact", args.contato)

    for doc in DOCUMENTOS:
        versao, arquivo = _ultima_versao(doc)
        print(f"{doc} v{versao}")
        bruto = _le(ssm, f"/telegrana/prod/legal/{doc}")
        atual = json.loads(bruto) if bruto else None
        mesma_versao = atual is not None and int(atual["versao"]) == versao
        vigencia = atual["vigencia"] if mesma_versao and atual else hoje
        modelo = arquivo.read_text(encoding="utf-8").replace("{{data_vigencia}}", vigencia)
        sha = hashlib.sha256(modelo.encode("utf-8")).hexdigest()
        titulo, nos = telegraph.converte(modelo.replace("{{contato_admin}}", args.contato))

        if mesma_versao and atual and atual["sha256"] != sha and not args.corrigir_versao:
            raise SystemExit(
                f"legal/{arquivo.name} mudou, mas a v{versao} já foi publicada. "
                "Crie a versão seguinte ou use --corrigir-versao (só antes de qualquer aceite)."
            )
        if (
            mesma_versao
            and atual
            and atual["sha256"] == sha
            and atual.get("contato") == args.contato
        ):
            print(f"  já publicado: {atual['url']}")
            continue
        if mesma_versao and atual:
            pagina = telegraph.chama(
                f"editPage/{atual['path']}",
                access_token=token,
                title=titulo,
                author_name="Telegrana",
                content=nos,
            )
            print("  página atualizada (mesmo endereço)")
        else:
            pagina = telegraph.chama(
                "createPage",
                access_token=token,
                title=titulo,
                author_name="Telegrana",
                content=nos,
            )
            print("  página criada")
        registro = json.dumps(
            {
                "versao": versao,
                "url": pagina["url"],
                "path": pagina["path"],
                "sha256": sha,
                "vigencia": vigencia,
                "contato": args.contato,
            }
        )
        for ambiente in AMBIENTES:
            _grava(ssm, f"/telegrana/{ambiente}/legal/{doc}", registro)
        print(f"  {pagina['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

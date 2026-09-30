#!/usr/bin/env python3
"""Prepara uma branch do Neon: papéis, migrações e URLs no .env.local (sem exibir segredos).

Uso (na raiz do projeto):
    uv run python scripts/db_bootstrap.py dev

- Usa NEON_OWNER_URL_<BRANCH> (papel dono) só para criar os papéis.
- Gera senhas novas (rotação) e grava NEON_MIGRATOR_URL_<BRANCH> e NEON_APP_URL_<BRANCH>.
- Aplica as migrações com o papel telegrana_migrator.
- Produção: só pelo pipeline, a partir da S1.3 (senhas no SSM, não no .env.local).
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from telegrana.infra import bootstrap, db, migrate  # noqa: E402

ENV = RAIZ / ".env.local"
BRANCHES = {"dev"}


def _le_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for linha in ENV.read_text(encoding="utf-8-sig").splitlines():
        chave, sep, valor = linha.partition("=")
        if sep and not linha.lstrip().startswith("#"):
            env[chave.strip()] = valor.strip()
    return env


def _grava_env(valores: dict[str, str]) -> None:
    linhas = ENV.read_text(encoding="utf-8-sig").splitlines()
    pendentes = dict(valores)
    for i, linha in enumerate(linhas):
        chave = linha.partition("=")[0].strip()
        if chave in pendentes and not linha.lstrip().startswith("#"):
            linhas[i] = f"{chave}={pendentes.pop(chave)}"
    linhas += [f"{k}={v}" for k, v in pendentes.items()]
    ENV.write_text("\n".join(linhas) + "\n", encoding="utf-8", newline="\n")


def _com_usuario(url: str, usuario: str, senha: str) -> str:
    partes = urlsplit(url)
    host = partes.hostname or ""
    porta = f":{partes.port}" if partes.port else ""
    netloc = f"{quote(usuario, safe='')}:{quote(senha, safe='')}@{host}{porta}"
    return urlunsplit((partes.scheme, netloc, partes.path, partes.query, partes.fragment))


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in BRANCHES:
        print(f"uso: scripts/db_bootstrap.py {{{'|'.join(sorted(BRANCHES))}}}")
        return 2
    branch = sys.argv[1].upper()
    env = _le_env()
    owner_url = env.get(f"NEON_OWNER_URL_{branch}", "")
    if not owner_url:
        print(f"NEON_OWNER_URL_{branch} em branco no .env.local")
        return 1
    database = urlsplit(owner_url).path.lstrip("/") or "neondb"

    senhas = {"migrator": secrets.token_urlsafe(32), "app": secrets.token_urlsafe(32)}
    with db.connect(owner_url, autocommit=True, application_name="telegrana-bootstrap") as adm:
        bootstrap.bootstrap_roles(
            adm, database, migrator_password=senhas["migrator"], app_password=senhas["app"]
        )
    print(f"papéis criados/rotacionados na branch {branch.lower()}")

    migrator_url = _com_usuario(owner_url, bootstrap.ROLE_MIGRATOR, senhas["migrator"])
    app_url = _com_usuario(owner_url, bootstrap.ROLE_APP, senhas["app"])
    _grava_env({f"NEON_MIGRATOR_URL_{branch}": migrator_url, f"NEON_APP_URL_{branch}": app_url})
    print("URLs gravadas no .env.local (valores não exibidos)")

    with db.connect(migrator_url, application_name="telegrana-migrate") as conn:
        aplicadas = migrate.migrate(conn)
    print(f"migrações aplicadas agora: {aplicadas or 'nenhuma (já estava em dia)'}")

    with db.connect(app_url) as conn:
        visiveis = conn.execute("select count(*) from telegrana.accounts").fetchone()
    print(
        f"conferência: o app sem contexto de conta enxerga {visiveis[0] if visiveis else '?'} conta(s) (esperado: 0)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

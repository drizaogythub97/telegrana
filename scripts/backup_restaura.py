#!/usr/bin/env python3
"""Restaura um backup do Telegrana num banco VAZIO (S8, D052).

Uso:
    uv run python scripts/backup_restaura.py <arquivo.tgbk> <chave-privada.txt> <VARIAVEL_DA_URL>

`VARIAVEL_DA_URL` é o NOME de uma variável do .env.local com a URL do papel dono de um
banco vazio (ex.: uma branch nova do Neon criada para isso) — a URL nunca vai na linha de
comando. O script cria os papéis com senhas novas, aplica as migrações até a versão do
backup, carrega as tabelas em ordem de dependência e confere as linhas com o manifesto.

Restaurar a PRODUÇÃO de verdade (incidente): criar a branch nova, restaurar nela, conferir,
e só então apontar o SSM (scripts/ssm_setup.py --rotacionar-banco-prod) para ela —
procedimento completo em docs/OPERACAO.md.
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "scripts"))

from backup_abre import le_chave  # noqa: E402
from db_bootstrap import _com_usuario, _le_env  # noqa: E402
from telegrana.infra import backup, bootstrap, db, migrate  # noqa: E402


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    arquivo, chave = Path(sys.argv[1]).expanduser(), Path(sys.argv[2]).expanduser()
    owner_url = _le_env().get(sys.argv[3], "")
    if not owner_url:
        print(f"{sys.argv[3]} em branco no .env.local")
        return 1
    dados = backup.abre(arquivo.read_bytes(), le_chave(chave))
    manifesto, _ = backup.le_pacote(dados)
    database = urlsplit(owner_url).path.lstrip("/") or "neondb"
    senhas = {"migrator": secrets.token_urlsafe(32), "app": secrets.token_urlsafe(32)}
    with db.connect(owner_url, autocommit=True, application_name="telegrana-bootstrap") as adm:
        bootstrap.bootstrap_roles(
            adm, database, migrator_password=senhas["migrator"], app_password=senhas["app"]
        )
    migrator_url = _com_usuario(owner_url, bootstrap.ROLE_MIGRATOR, senhas["migrator"])
    with db.connect(migrator_url, application_name="telegrana-restaura") as conn:
        migrate.migrate(conn, ate=int(manifesto["esquema"]))
        contagens = backup.restaura(conn, dados)
    print(
        f"restaurado o backup de {manifesto['gerado_em']}: "
        f"{len(contagens)} tabelas, {sum(contagens.values())} linhas (conferidas com o manifesto)"
    )
    print("As senhas novas dos papéis NÃO foram gravadas: rode scripts/ssm_setup.py para usá-lo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

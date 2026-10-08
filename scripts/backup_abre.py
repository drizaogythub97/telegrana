#!/usr/bin/env python3
"""Abre um backup do Telegrana (S8, D052): decifra com a chave privada e extrai os CSVs.

Uso:
    uv run python scripts/backup_abre.py <arquivo.tgbk> <chave-privada.txt> <pasta-de-saída>

A pasta de saída fica com um CSV por tabela e o `manifesto.json` (linhas por tabela,
versão do esquema). São dados pessoais em claro: use uma pasta fora do projeto e apague
quando terminar. Para restaurar num banco, veja scripts/backup_restaura.py.
"""

from __future__ import annotations

import io
import sys
import tarfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from telegrana.infra import backup  # noqa: E402


def le_chave(caminho: Path) -> str:
    linhas = [x.strip() for x in caminho.read_text(encoding="utf-8").splitlines() if x.strip()]
    return linhas[-1]


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    arquivo, chave, saida = (Path(x).expanduser().resolve() for x in sys.argv[1:])
    if saida == RAIZ or RAIZ in saida.parents:
        print("Use uma pasta de saída FORA do projeto (são dados pessoais em claro).")
        return 2
    dados = backup.abre(arquivo.read_bytes(), le_chave(chave))
    manifesto, _ = backup.le_pacote(dados)  # valida o pacote antes de extrair
    saida.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(dados), mode="r:gz") as tar:
        tar.extractall(saida, filter="data")
    total = sum(manifesto["tabelas"].values())
    print(
        f"backup de {manifesto['gerado_em']} (esquema {manifesto['esquema']}): "
        f"{len(manifesto['tabelas'])} tabelas, {total} linhas → {saida}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

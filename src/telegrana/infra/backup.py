"""Backup lógico cifrado (S8, PLANO 12 "Backup", D052).

O Neon Free só volta 6 horas e não faz backup agendado. Toda semana a Lambda `backup` lê o
banco inteiro com o papel `telegrana_backup` (só leitura), numa transação REPEATABLE READ
(fotografia consistente), e monta um `.tar.gz` em memória: um CSV por tabela e um
`manifesto.json` (data, versão do esquema, linhas por tabela). O pacote é cifrado com a
CHAVE PÚBLICA do backup e vai como arquivo para o chat do admin. Só a chave privada, que o
Adriano guarda offline, abre o arquivo: nem o bot, nem o agente, nem o Telegram conseguem.

Cifra (formato `TGBK1`): X25519 efêmero + HKDF-SHA256 + ChaCha20-Poly1305
(biblioteca `cryptography`, PyCA). Arquivo = MAGICO + chave pública efêmera (32) +
nonce (12) + texto cifrado com etiqueta; o MAGICO entra como dado autenticado.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import os
import tarfile
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from psycopg import sql

MAGICO = b"TGBK1\n"
_INFO = b"telegrana-backup-v1"
# Só registro técnico de deduplicação (reconstruído sozinho): fica fora.
FORA = frozenset({"processed_updates"})


class ErroBackup(RuntimeError):
    """Arquivo inválido, chave errada ou adulterado (a mensagem nunca tem conteúdo)."""


@dataclass(frozen=True, slots=True)
class Pacote:
    dados: bytes  # .tar.gz (ainda NÃO cifrado)
    tabelas: dict[str, int]  # tabela -> linhas
    esquema: int  # última migração aplicada


# ---------------------------------------------------------------------------
# Exportação
# ---------------------------------------------------------------------------
def tabelas(conn: Any) -> list[str]:
    rows = conn.execute(
        "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace"
        " where n.nspname = 'telegrana' and c.relkind = 'r' order by c.relname"
    ).fetchall()
    return [str(r[0]) for r in rows if r[0] not in FORA]


def exporta(conn: Any, agora: datetime) -> Pacote:
    """Lê tudo numa fotografia consistente e devolve o pacote (em memória)."""
    contagens: dict[str, int] = {}
    arquivos: dict[str, bytes] = {}
    with conn.transaction():
        conn.execute("set transaction isolation level repeatable read, read only")
        esquema = int(
            conn.execute(
                "select coalesce(max(version), 0) from telegrana.schema_migrations"
            ).fetchone()[0]
        )
        for nome in tabelas(conn):
            tabela = sql.Identifier("telegrana", nome)
            bruto = bytearray()
            with conn.cursor().copy(
                sql.SQL("copy (select * from {}) to stdout with (format csv, header true)").format(
                    tabela
                )
            ) as copia:
                for parte in copia:
                    bruto += bytes(parte)
            arquivos[f"{nome}.csv"] = bytes(bruto)
            linhas = conn.execute(sql.SQL("select count(*) from {}").format(tabela)).fetchone()
            contagens[nome] = int(linhas[0])
    manifesto = {
        "formato": 1,
        "gerado_em": agora.isoformat(timespec="seconds"),
        "esquema": esquema,
        "tabelas": contagens,
    }
    arquivos["manifesto.json"] = json.dumps(manifesto, ensure_ascii=False, indent=1).encode()
    saida = io.BytesIO()
    with tarfile.open(fileobj=saida, mode="w:gz", compresslevel=9) as tar:
        for nome, conteudo in sorted(arquivos.items()):
            info = tarfile.TarInfo(nome)
            info.size = len(conteudo)
            info.mtime = int(agora.timestamp())
            tar.addfile(info, io.BytesIO(conteudo))
    return Pacote(saida.getvalue(), contagens, esquema)


def le_pacote(dados: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Abre o .tar.gz (já decifrado): (manifesto, tabela -> CSV bruto)."""
    manifesto: dict[str, Any] = {}
    csvs: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(dados), mode="r:gz") as tar:
        for membro in tar.getmembers():
            if not membro.isfile() or "/" in membro.name or membro.name.startswith("."):
                raise ErroBackup("pacote com arquivo inesperado")
            arquivo = tar.extractfile(membro)
            if arquivo is None:
                continue
            if membro.name == "manifesto.json":
                manifesto = json.loads(arquivo.read())
            elif membro.name.endswith(".csv"):
                csvs[membro.name[:-4]] = arquivo.read()
    if not manifesto:
        raise ErroBackup("pacote sem manifesto")
    return manifesto, csvs


# ---------------------------------------------------------------------------
# Restauração (num banco VAZIO, já migrado até a mesma versão do esquema)
# ---------------------------------------------------------------------------
_DEPENDENCIAS = (
    "select filha.relname, mae.relname from pg_constraint c"
    " join pg_class filha on filha.oid = c.conrelid"
    " join pg_class mae on mae.oid = c.confrelid"
    " join pg_namespace n on n.oid = filha.relnamespace"
    " where c.contype = 'f' and n.nspname = 'telegrana'"
)
_IDENTIDADES = (
    "select c.relname, a.attname from pg_attribute a"
    " join pg_class c on c.oid = a.attrelid join pg_namespace n on n.oid = c.relnamespace"
    " where n.nspname = 'telegrana' and a.attidentity <> '' and not a.attisdropped"
)
_NAO_RESTAURA = frozenset({"schema_migrations"})  # as migrações já criaram


def ordem(conn: Any, nomes: list[str]) -> list[str]:
    """Mães antes das filhas (chave estrangeira para a própria tabela não conta: a checagem
    roda no fim do COPY, com todas as linhas já lá)."""
    maes: dict[str, set[str]] = {n: set() for n in nomes}
    for filha, mae in conn.execute(_DEPENDENCIAS).fetchall():
        if filha in maes and mae in maes and filha != mae:
            maes[filha].add(mae)
    feitas: list[str] = []
    while len(feitas) < len(nomes):
        prontas = sorted(n for n in nomes if n not in feitas and maes[n] <= set(feitas))
        if not prontas:
            raise ErroBackup("dependência circular entre tabelas")
        feitas += prontas
    return feitas


def restaura(conn: Any, dados: bytes) -> dict[str, int]:
    """Carrega o pacote (decifrado) num banco vazio. `conn`: papel migrador do banco novo."""
    manifesto, csvs = le_pacote(dados)
    versao = int(
        conn.execute(
            "select coalesce(max(version), 0) from telegrana.schema_migrations"
        ).fetchone()[0]
    )
    if versao != int(manifesto["esquema"]):
        raise ErroBackup(
            f"banco na versão {versao}, backup na {manifesto['esquema']}: migre até a mesma"
        )
    nomes = [n for n in tabelas(conn) if n in csvs and n not in _NAO_RESTAURA]
    with conn.transaction():
        for nome in nomes:
            if conn.execute(
                sql.SQL("select 1 from {} limit 1").format(sql.Identifier("telegrana", nome))
            ).fetchone():
                raise ErroBackup(f"o banco de destino não está vazio ({nome})")
        for nome in ordem(conn, nomes):
            bruto = csvs[nome]
            primeira = bruto.splitlines()[0].decode("utf-8")
            cabecalho = next(csv.reader([primeira]))
            colunas = sql.SQL(", ").join(sql.Identifier(c) for c in cabecalho)
            tabela = sql.Identifier("telegrana", nome)
            comando = sql.SQL("copy {} ({}) from stdin with (format csv, header true)").format(
                tabela, colunas
            )
            # O Postgres não aceita COPY FROM com RLS valendo para quem copia: o dono tira o
            # FORCE só durante a carga, NESTA transação (falhou → volta tudo, inclusive isso).
            forcada = conn.execute(
                "select relforcerowsecurity from pg_class where oid = %s::regclass",
                (f"telegrana.{nome}",),
            ).fetchone()
            if forcada and forcada[0]:
                conn.execute(sql.SQL("alter table {} no force row level security").format(tabela))
            with conn.cursor().copy(comando) as copia:
                copia.write(bruto)
            if forcada and forcada[0]:
                conn.execute(sql.SQL("alter table {} force row level security").format(tabela))
        for nome, coluna in conn.execute(_IDENTIDADES).fetchall():
            if nome in nomes:
                tabela = sql.Identifier("telegrana", nome)
                conn.execute(
                    sql.SQL(
                        "select setval(pg_get_serial_sequence({}, {}), coalesce(max({}), 1),"
                        " max({}) is not null) from {}"
                    ).format(
                        sql.Literal(f"telegrana.{nome}"),
                        sql.Literal(coluna),
                        sql.Identifier(coluna),
                        sql.Identifier(coluna),
                        tabela,
                    )
                )
        contagens = {
            n: int(
                conn.execute(
                    sql.SQL("select count(*) from {}").format(sql.Identifier("telegrana", n))
                ).fetchone()[0]
            )
            for n in nomes
        }
        esperado = {n: int(manifesto["tabelas"][n]) for n in nomes}
        if contagens != esperado:
            raise ErroBackup("contagem de linhas diferente do manifesto")
    return contagens


# ---------------------------------------------------------------------------
# Chaves e cifra
# ---------------------------------------------------------------------------
def _b64(chave: bytes) -> str:
    return base64.b64encode(chave).decode()


def gera_chaves() -> tuple[str, str]:
    """(privada, pública) em base64. A privada nunca vai para o SSM nem para o repositório."""
    privada = X25519PrivateKey.generate()
    bruta = privada.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    publica = privada.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return _b64(bruta), _b64(publica)


def _chave_simetrica(compartilhado: bytes, efemera: bytes, destino: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=_INFO + efemera + destino
    ).derive(compartilhado)


def cifra(dados: bytes, publica_b64: str) -> bytes:
    try:
        destino = base64.b64decode(publica_b64, validate=True)
        publica = X25519PublicKey.from_public_bytes(destino)
    except ValueError as exc:
        raise ErroBackup("chave pública inválida") from exc
    efemera = X25519PrivateKey.generate()
    efemera_pub = efemera.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    chave = _chave_simetrica(efemera.exchange(publica), efemera_pub, destino)
    nonce = os.urandom(12)
    return MAGICO + efemera_pub + nonce + ChaCha20Poly1305(chave).encrypt(nonce, dados, MAGICO)


def abre(cifrado: bytes, privada_b64: str) -> bytes:
    if not cifrado.startswith(MAGICO) or len(cifrado) < len(MAGICO) + 32 + 12 + 16:
        raise ErroBackup("não é um backup do Telegrana")
    try:
        privada = X25519PrivateKey.from_private_bytes(base64.b64decode(privada_b64, validate=True))
    except ValueError as exc:
        raise ErroBackup("chave privada inválida") from exc
    inicio = len(MAGICO)
    efemera_pub = cifrado[inicio : inicio + 32]
    nonce = cifrado[inicio + 32 : inicio + 44]
    destino = privada.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    compartilhado = privada.exchange(X25519PublicKey.from_public_bytes(efemera_pub))
    chave = _chave_simetrica(compartilhado, efemera_pub, destino)
    try:
        return ChaCha20Poly1305(chave).decrypt(nonce, cifrado[inicio + 44 :], MAGICO)
    except Exception as exc:  # InvalidTag: chave errada ou arquivo adulterado
        raise ErroBackup("chave errada ou arquivo adulterado") from exc

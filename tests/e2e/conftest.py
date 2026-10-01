"""Ponta a ponta no SERVIDOR DE TESTES do Telegram (PLANO 10.1; D034).

- O bot de teste roda aqui mesmo: um laço de `getUpdates` (Bot API de teste) entrega
  cada update ao mesmo adaptador + núcleo da Lambda, com um banco descartável.
- Três pessoas de verdade (contas de teste, Telethon) conversam com ele: admin, Ana e Bruno.

Requer (env ou .env.local): TELEGRAM_API_ID, TELEGRAM_API_HASH, E2E_BOT_TOKEN,
E2E_BOT_USERNAME, E2E_SESSION_{ADMIN,A,B} (criados por scripts/e2e_contas.py) e
TELEGRANA_TEST_DATABASE_URL. Rodar: `uv run pytest -m e2e`.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

from telegrana.channels.telegram import adaptador, webhook
from telegrana.channels.telegram.api import BASE_URL, TelegramAPI
from telegrana.core import roteador
from telegrana.core.contexto import Contexto, Documento
from telegrana.infra import db
from tests.conftest import Banco

RAIZ = Path(__file__).resolve().parents[2]
CHAVES = (
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "E2E_BOT_TOKEN",
    "E2E_BOT_USERNAME",
    "E2E_SESSION_ADMIN",
    "E2E_SESSION_A",
    "E2E_SESSION_B",
)
DC, IP, PORTA = 2, "149.154.167.40", 80
ESPERA = 25.0
log = logging.getLogger("telegrana.e2e")


def _config() -> dict[str, str]:
    valores = {k: os.environ[k] for k in CHAVES if os.environ.get(k)}
    arquivo = RAIZ / ".env.local"
    if arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8-sig").splitlines():
            chave, sep, valor = linha.partition("=")
            if sep and chave.strip() in CHAVES:
                valores.setdefault(chave.strip(), valor.strip())
    return valores


# ---------------------------------------------------------------------------
# O bot (laço de getUpdates com o código da Lambda)
# ---------------------------------------------------------------------------
class BotLocal(threading.Thread):
    def __init__(self, token: str, banco_url: str, ctx: Contexto, admin_id: int) -> None:
        super().__init__(daemon=True, name="bot-e2e")
        self.token, self.banco_url, self.ctx, self.admin_id = token, banco_url, ctx, admin_id
        self.parar = threading.Event()
        self.pronto = threading.Event()
        self.erros: list[str] = []
        self.api = TelegramAPI(
            token,
            test_server=True,
            client=httpx.Client(base_url=BASE_URL, timeout=httpx.Timeout(40.0, connect=10.0)),
        )

    def run(self) -> None:
        self.api.call("deleteWebhook", drop_pending_updates=True)
        id_do_bot = adaptador.bot_id(self.token)
        with db.connect(self.banco_url, application_name="telegrana-e2e") as conn:
            self.pronto.set()
            deslocamento: int | None = None
            while not self.parar.is_set():
                try:
                    updates = self.api.call(
                        "getUpdates",
                        offset=deslocamento,
                        timeout=5,
                        allowed_updates=webhook.ALLOWED_UPDATES,
                    )
                except Exception as exc:
                    self.erros.append(f"getUpdates: {type(exc).__name__}")
                    time.sleep(1)
                    continue
                for update in updates:
                    deslocamento = int(update["update_id"]) + 1
                    convertido = adaptador.para_entrada(update, id_do_bot)
                    if convertido is None:
                        continue
                    entrada, origem = convertido
                    try:
                        resultado = roteador.trata(conn, self.ctx, entrada)
                        adaptador.executa(self.api, resultado, origem, self.admin_id)
                    except Exception as exc:
                        self.erros.append(f"{entrada.comando or entrada.acao}: {exc!r}")


# ---------------------------------------------------------------------------
# Uma pessoa de teste (Telethon)
# ---------------------------------------------------------------------------
@dataclass
class Pessoa:
    nome: str
    cliente: Any
    bot: Any = None
    eu: Any = None
    ultimo: int = 0
    recebidas: list[Any] = field(default_factory=list)

    @property
    def id(self) -> int:
        return int(self.eu.id)

    @property
    def telefone(self) -> str:
        return str(self.eu.phone)

    def prepara(self, bot_username: str) -> None:
        self.eu = self.cliente.get_me()
        self.bot = self.cliente.get_entity(bot_username)
        mensagens = self.cliente.get_messages(self.bot, limit=1)
        self.ultimo = mensagens[0].id if mensagens else 0

    def espera(self, trecho: str, timeout: float = ESPERA) -> Any:
        """Espera uma mensagem do bot que contenha `trecho`; devolve essa mensagem."""
        fim = time.monotonic() + timeout
        while time.monotonic() < fim:
            novas = self.cliente.get_messages(self.bot, min_id=self.ultimo, limit=30)
            for m in sorted(novas, key=lambda x: x.id):
                self.ultimo = max(self.ultimo, m.id)
                if not m.out:
                    self.recebidas.append(m)
            for m in reversed(self.recebidas):
                if trecho in (m.raw_text or ""):
                    self.recebidas = [x for x in self.recebidas if x.id > m.id]
                    return m
            time.sleep(0.8)
        vistas = [(x.raw_text or "")[:60] for x in self.recebidas[-5:]]
        raise AssertionError(f"{self.nome}: não chegou mensagem com {trecho!r}; últimas: {vistas}")

    def diz(self, texto: str) -> None:
        self.cliente.send_message(self.bot, texto)

    def responde(self, pergunta: Any, texto: str) -> None:
        self.cliente.send_message(self.bot, texto, reply_to=pergunta.id)

    def toca(self, mensagem: Any, rotulo: str) -> None:
        resultado = mensagem.click(text=lambda t: rotulo in t)
        if resultado is None:
            raise AssertionError(f"{self.nome}: botão {rotulo!r} não encontrado")

    def compartilha(self, telefone: str) -> None:
        from telethon.tl.types import InputMediaContact

        self.cliente.send_message(
            self.bot,
            file=InputMediaContact(
                phone_number=telefone, first_name=self.nome, last_name="Teste", vcard=""
            ),
        )


@dataclass
class Mundo:
    bot: BotLocal
    admin: Pessoa
    ana: Pessoa
    bruno: Pessoa
    banco: Banco

    def esquece_identidade(self, pessoa: Pessoa) -> None:
        """Simula "apaguei o Telegram e criei outro": a conta perde o vínculo com este id."""
        with db.connect(self.banco.migrator) as conn, conn.transaction():
            conn.execute(
                "update telegrana.user_channels set external_id = %s"
                " where channel = 'telegram' and external_id = %s",
                ("1" + str(pessoa.id), str(pessoa.id)),
            )

    def libera_tentativas(self, pessoa: Pessoa) -> None:
        with db.connect(self.banco.migrator) as conn, conn.transaction():
            conn.execute(
                "delete from telegrana.auth_attempts where external_id = %s", (str(pessoa.id),)
            )


@pytest.fixture(scope="session")
def mundo(banco: Banco) -> Iterator[Mundo]:
    cfg = _config()
    faltando = [k for k in CHAVES if not cfg.get(k)]
    if faltando:
        motivo = f"E2E sem configuração ({', '.join(faltando)}): rode scripts/e2e_contas.py"
        if os.environ.get("E2E_OBRIGATORIO"):  # no CI, pular seria liberar prod sem E2E
            pytest.fail(motivo)
        pytest.skip(motivo)
    from telethon.sessions import StringSession
    from telethon.sync import TelegramClient

    pessoas = {}
    for chave, nome in (("ADMIN", "Admin"), ("A", "Ana"), ("B", "Bruno")):
        cliente = TelegramClient(
            StringSession(cfg[f"E2E_SESSION_{chave}"]),
            int(cfg["TELEGRAM_API_ID"]),
            cfg["TELEGRAM_API_HASH"],
        )
        cliente.session.set_dc(DC, IP, PORTA)
        cliente.connect()
        if not cliente.is_user_authorized():
            pytest.fail(f"sessão {chave} expirou: rode scripts/e2e_contas.py de novo")
        pessoas[chave] = Pessoa(nome, cliente)
        pessoas[chave].prepara("@" + cfg["E2E_BOT_USERNAME"])

    ctx = Contexto(
        canal="telegram",
        admin_id=str(pessoas["ADMIN"].id),
        contato_admin="@admin_teste",
        termos=Documento(
            1, "https://telegra.ph/Termos-de-Uso-do-Telegrana--versão-1-10-01", b"\x01" * 32
        ),
        privacidade=Documento(
            1,
            "https://telegra.ph/Política-de-Privacidade-do-Telegrana--versão-1-10-01",
            b"\x02" * 32,
        ),
        link_convite=lambda token: f"https://t.me/{cfg['E2E_BOT_USERNAME']}?start={token}",
        pepper=secrets.token_bytes(32),
    )
    bot = BotLocal(cfg["E2E_BOT_TOKEN"], banco.app, ctx, pessoas["ADMIN"].id)
    bot.start()
    assert bot.pronto.wait(30), "o bot local não subiu"
    yield Mundo(bot, pessoas["ADMIN"], pessoas["A"], pessoas["B"], banco)
    bot.parar.set()
    bot.join(15)
    for p in pessoas.values():
        p.cliente.disconnect()
    assert not bot.erros, f"erros no bot durante o E2E: {bot.erros}"


def token_do_link(texto: str) -> str:
    achado = re.search(r"start=([A-Za-z0-9_-]{43})", texto)
    assert achado, "link de convite não encontrado"
    return achado.group(1)


def codigo_de(texto: str) -> str:
    achado = re.search(r"[0-9A-Z]{4}(?:-[0-9A-Z]{4}){4}", texto)
    assert achado, "código de recuperação não encontrado"
    return achado.group(0)

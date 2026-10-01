#!/usr/bin/env python3
"""Cria as contas de teste e o bot de teste no SERVIDOR DE TESTES do Telegram (S1.5).

**Quem roda é o Adriano, uma vez** (o agente não cria contas):
    uv run python scripts/e2e_contas.py

O servidor de testes é uma rede separada da oficial: números fictícios 99966XYYYY
(X = data center), sem SMS; o código de login é o número do data center repetido 5 vezes.
Nada aqui toca a sua conta do Telegram.

O script:
1. cria (ou entra em) 3 contas de teste no DC 2: admin, Ana e Bruno;
2. pela conta admin, conversa com o @BotFather de teste e cria o bot de teste;
3. grava no .env.local (sem mostrar na tela): E2E_SESSION_ADMIN, E2E_SESSION_A,
   E2E_SESSION_B (sessões do Telethon), E2E_BOT_TOKEN e E2E_BOT_USERNAME;
4. copia esses valores (e TELEGRAM_API_ID/HASH) para os segredos do ambiente `e2e` do
   GitHub com `gh secret set`, para o CI rodar o E2E (use --sem-github para pular).

Rodar de novo recria tudo (útil se o servidor de testes apagar as contas, o que acontece
de tempos em tempos).
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from telethon import errors
from telethon.sessions import StringSession
from telethon.sync import TelegramClient

RAIZ = Path(__file__).resolve().parent.parent
ENV = RAIZ / ".env.local"
DC, IP, PORTA = 2, "149.154.167.40", 80  # servidor de testes, DC 2 (my.telegram.org)
CODIGO = str(DC) * 5
CONTAS = (("ADMIN", "Admin", "Teste"), ("A", "Ana", "Teste"), ("B", "Bruno", "Teste"))


def _le_env() -> dict[str, str]:
    valores: dict[str, str] = {}
    for linha in ENV.read_text(encoding="utf-8-sig").splitlines():
        chave, sep, valor = linha.partition("=")
        if sep and not chave.strip().startswith("#"):
            valores[chave.strip()] = valor.strip()
    return valores


def _grava_env(novos: dict[str, str]) -> None:
    linhas = ENV.read_text(encoding="utf-8-sig").splitlines()
    restantes = dict(novos)
    saida = []
    for linha in linhas:
        chave = linha.partition("=")[0].strip()
        if chave in restantes:
            saida.append(f"{chave}={restantes.pop(chave)}")
        else:
            saida.append(linha)
    if restantes:
        saida.append("# E2E no servidor de testes do Telegram (scripts/e2e_contas.py)")
        saida.extend(f"{k}={v}" for k, v in restantes.items())
    ENV.write_text("\n".join(saida) + "\n", encoding="utf-8", newline="\n")


def _cliente(api_id: int, api_hash: str) -> TelegramClient:
    cliente = TelegramClient(StringSession(), api_id, api_hash)
    cliente.session.set_dc(DC, IP, PORTA)
    return cliente


def _conta(api_id: int, api_hash: str, nome: str, sobrenome: str) -> TelegramClient:
    for _ in range(5):
        telefone = f"99966{DC}{secrets.randbelow(10_000):04d}"
        cliente = _cliente(api_id, api_hash)
        try:
            cliente.start(
                phone=telefone,
                code_callback=lambda: CODIGO,
                first_name=nome,
                last_name=sobrenome,
            )
        except errors.SessionPasswordNeededError:
            # Número já usado por outra pessoa, com senha: tenta outro.
            cliente.disconnect()
            continue
        eu = cliente.get_me()
        if eu.first_name != nome:  # conta de outra pessoa sem senha: ajusta o nome
            from telethon.tl.functions.account import UpdateProfileRequest

            cliente(UpdateProfileRequest(first_name=nome, last_name=sobrenome))
        print(f"  conta {nome}: ok (id {eu.id})")
        return cliente
    raise SystemExit("não consegui um número de teste livre; rode de novo")


def _cria_bot(admin: TelegramClient) -> tuple[str, str]:
    usuario = f"telegrana_e2e_{secrets.token_hex(3)}_bot"
    with admin.conversation("BotFather", timeout=60) as conversa:
        conversa.send_message("/newbot")
        conversa.get_response()
        conversa.send_message("Telegrana E2E")
        conversa.get_response()
        conversa.send_message(usuario)
        resposta = conversa.get_response().raw_text
    achado = re.search(r"\d{5,}:[A-Za-z0-9_-]{30,}", resposta)
    if not achado:
        raise SystemExit("o BotFather de teste não devolveu o token; rode de novo")
    print(f"  bot de teste: @{usuario}")
    return achado.group(0), usuario


def _github(valores: dict[str, str]) -> None:
    gh = shutil.which("gh")
    if gh is None:
        raise SystemExit("gh (GitHub CLI) não encontrado; rode com --sem-github")
    for nome, valor in valores.items():
        # Argumentos fixos; o valor vai só pela entrada padrão (nunca na linha de comando).
        subprocess.run(
            [gh, "secret", "set", nome, "--env", "e2e"],
            input=valor.encode(),
            check=True,
            capture_output=True,
        )
    print(f"  {len(valores)} segredos atualizados no ambiente e2e do GitHub")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sem-github", action="store_true")
    args = parser.parse_args()
    env = _le_env()
    api_id, api_hash = env.get("TELEGRAM_API_ID", ""), env.get("TELEGRAM_API_HASH", "")
    if not api_id.isdigit() or not api_hash:
        raise SystemExit("TELEGRAM_API_ID/TELEGRAM_API_HASH ausentes no .env.local")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    print("Servidor de testes do Telegram (DC 2)")
    clientes = {chave: _conta(int(api_id), api_hash, n, s) for chave, n, s in CONTAS}
    token, usuario = _cria_bot(clientes["ADMIN"])
    novos = {f"E2E_SESSION_{k}": c.session.save() for k, c in clientes.items()}
    novos |= {"E2E_BOT_TOKEN": token, "E2E_BOT_USERNAME": usuario}
    _grava_env(novos)
    if not args.sem_github:
        _github(novos | {"TELEGRAM_API_ID": api_id, "TELEGRAM_API_HASH": api_hash})
    for cliente in clientes.values():
        cliente.disconnect()
    print("Pronto: sessões e token gravados no .env.local (nada foi mostrado).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

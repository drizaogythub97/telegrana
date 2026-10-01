"""Primitivas de segurança do cadastro e da recuperação (PLANO 3.2 a 3.5, D033).

Nada aqui conhece canal nem banco: só geração e conferência de segredos.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# Crockford base32: sem I, L, O e U (evita confusão na hora de digitar).
ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_TAMANHO_SELETOR = 8  # 40 bits, em claro no banco (só localiza a linha)
_TAMANHO_VERIFICADOR = 12  # 60 bits, guardado só como Argon2id
_TROCAS = str.maketrans({"O": "0", "I": "1", "L": "1"})
_TOKEN_CONVITE = re.compile(r"^[A-Za-z0-9_-]{43}$")

# Parâmetros padrão do argon2-cffi (RFC 9106, perfil de baixa memória: 64 MiB, t=3, p=4).
_hasher = PasswordHasher()

# Travas (PLANO 3.5): 5 erros → 15 min; cada erro a mais dobra, até 24 h.
TENTATIVAS_LIVRES = 5
_TRAVA_INICIAL = timedelta(minutes=15)
_TRAVA_MAXIMA = timedelta(hours=24)


# ---------------------------------------------------------------------------
# Convite
# ---------------------------------------------------------------------------
def novo_token_convite() -> str:
    """32 bytes aleatórios em base64url: 43 caracteres (cabe no deep link do Telegram)."""
    return secrets.token_urlsafe(32)


def token_valido(token: str) -> bool:
    return bool(_TOKEN_CONVITE.fullmatch(token))


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()


# ---------------------------------------------------------------------------
# Telefone
# ---------------------------------------------------------------------------
def normaliza_telefone(bruto: str) -> str | None:
    """E.164 a partir do número que o Telegram entrega (já internacional, com ou sem +)."""
    digitos = re.sub(r"\D", "", bruto)
    if not 8 <= len(digitos) <= 15:
        return None
    return "+" + digitos


def decodifica_pepper(valor: str) -> bytes:
    pepper = base64.urlsafe_b64decode(valor + "=" * (-len(valor) % 4))
    if len(pepper) < 32:
        raise ValueError("pepper do telefone precisa ter ao menos 32 bytes")
    return pepper


def hmac_telefone(e164: str, pepper: bytes) -> bytes:
    return hmac.new(pepper, e164.encode("ascii"), hashlib.sha256).digest()


# ---------------------------------------------------------------------------
# Código de recuperação
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class CodigoRecuperacao:
    exibicao: str  # XXXX-XXXX-XXXX-XXXX-XXXX (mostrado uma única vez)
    seletor: str
    verificador: str


def novo_codigo() -> CodigoRecuperacao:
    total = _TAMANHO_SELETOR + _TAMANHO_VERIFICADOR
    bruto = "".join(secrets.choice(ALFABETO) for _ in range(total))
    grupos = "-".join(bruto[i : i + 4] for i in range(0, total, 4))
    return CodigoRecuperacao(grupos, bruto[:_TAMANHO_SELETOR], bruto[_TAMANHO_SELETOR:])


def separa_codigo(digitado: str) -> tuple[str, str] | None:
    """Aceita espaços, hífens, minúsculas e as trocas comuns (O→0, I/L→1)."""
    limpo = re.sub(r"[\s-]", "", digitado).upper().translate(_TROCAS)
    if len(limpo) != _TAMANHO_SELETOR + _TAMANHO_VERIFICADOR or any(
        c not in ALFABETO for c in limpo
    ):
        return None
    return limpo[:_TAMANHO_SELETOR], limpo[_TAMANHO_SELETOR:]


def hash_verificador(verificador: str) -> str:
    return _hasher.hash(verificador)


def confere_verificador(hash_guardado: str, verificador: str) -> bool:
    try:
        return _hasher.verify(hash_guardado, verificador)
    except VerificationError, InvalidHashError:
        return False


def trava_para(falhas: int) -> timedelta | None:
    """Quanto tempo bloquear depois de `falhas` erros seguidos (None = ainda livre)."""
    if falhas < TENTATIVAS_LIVRES:
        return None
    trava: timedelta = _TRAVA_INICIAL * 2 ** min(falhas - TENTATIVAS_LIVRES, 10)
    return min(trava, _TRAVA_MAXIMA)


# ---------------------------------------------------------------------------
# Identificadores curtos para botões (callback_data do Telegram tem 64 bytes)
# ---------------------------------------------------------------------------
def curto(valor: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(valor.bytes).decode("ascii").rstrip("=")


def longo(valor: str) -> uuid.UUID | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{22}", valor):
        return None
    return uuid.UUID(bytes=base64.urlsafe_b64decode(valor + "=="))

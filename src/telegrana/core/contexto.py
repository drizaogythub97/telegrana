"""Configuração que o núcleo recebe do ponto de entrada (sem nada de canal)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True, slots=True)
class Documento:
    versao: int
    url: str
    sha256: bytes


@dataclass(frozen=True, slots=True)
class Contexto:
    canal: str
    admin_id: str  # external_id do administrador no canal
    contato_admin: str  # como falar com o admin (aparece nos textos)
    termos: Documento
    privacidade: Documento
    link_convite: Callable[[str], str]  # token → link de convite do canal
    pepper: bytes = field(repr=False)
    extrator: Any = None  # provedor de IA (core.entendimento.Extrator); None = sem IA
    max_usos_convite: int = 20
    max_pedidos_por_hora: int = 20


def data_br(momento: datetime) -> str:
    return momento.astimezone(FUSO).strftime("%d/%m/%Y")


def agora() -> datetime:
    return datetime.now(FUSO)

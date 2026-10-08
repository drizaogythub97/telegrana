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
class Limites:
    """Uso por pessoa (S8, D051): "folgados", decisão do Adriano em 08/10/2026."""

    por_minuto: int = 40
    por_dia: int = 600
    ia: int = 200  # chamadas à IA por dia
    audio_segundos: int = 60 * 60  # por dia
    arquivos: int = 20  # PDF/planilha por dia


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
    transcritor: Any = None  # provedor de transcrição (core.audio.Transcritor); None = sem áudio
    max_usos_convite: int = 20
    max_pedidos_por_hora: int = 20
    limites: Limites = field(default_factory=Limites)


def data_br(momento: datetime) -> str:
    return momento.astimezone(FUSO).strftime("%d/%m/%Y")


def agora() -> datetime:
    return datetime.now(FUSO)

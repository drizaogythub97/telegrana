"""Identidade visual do Telegrana (PLANO 7.2): tokens únicos para XLSX, PDF e prévias.

Paleta extraída da logo original (`assets/brand/logo-original.png`).
"""

from __future__ import annotations

AZUL_CLARO = "#0FADFC"  # topo do "t"
AZUL = "#0179E0"  # texto "Tele"
AZUL_ESCURO = "#0068CB"  # sombra do "t"
TRANSICAO = "#0389A2"  # azul → verde
VERDE = "#19B751"  # texto "grana"
VERDE_ESCURO = "#09A451"
TEXTO = "#0F172A"
FUNDO = "#F8FAFC"
GASTO = "#EF4444"

DEGRADE = (AZUL, TRANSICAO, VERDE)


def hex_rgb(cor: str) -> tuple[int, int, int]:
    valor = cor.lstrip("#")
    if len(valor) != 6:
        raise ValueError(f"cor inválida: {cor}")
    return int(valor[0:2], 16), int(valor[2:4], 16), int(valor[4:6], 16)

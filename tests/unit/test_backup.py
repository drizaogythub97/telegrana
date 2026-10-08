"""Cifra do backup (S8, D052): só a chave privada certa abre; adulterado não abre."""

from __future__ import annotations

import base64

import pytest

from telegrana.infra import backup


def test_ida_e_volta() -> None:
    privada, publica = backup.gera_chaves()
    dados = b"tabela,linhas\n" * 1000
    cifrado = backup.cifra(dados, publica)
    assert cifrado.startswith(backup.MAGICO)
    assert dados not in cifrado
    assert backup.abre(cifrado, privada) == dados
    assert backup.cifra(dados, publica) != cifrado  # chave efêmera e nonce novos


def test_chave_errada_nao_abre() -> None:
    _, publica = backup.gera_chaves()
    outra, _ = backup.gera_chaves()
    with pytest.raises(backup.ErroBackup, match="chave errada"):
        backup.abre(backup.cifra(b"segredo", publica), outra)


def test_adulterado_nao_abre() -> None:
    privada, publica = backup.gera_chaves()
    cifrado = bytearray(backup.cifra(b"segredo" * 10, publica))
    cifrado[-5] ^= 1
    with pytest.raises(backup.ErroBackup):
        backup.abre(bytes(cifrado), privada)


def test_arquivos_e_chaves_invalidos() -> None:
    privada, _ = backup.gera_chaves()
    with pytest.raises(backup.ErroBackup, match="não é um backup"):
        backup.abre(b"qualquer coisa", privada)
    with pytest.raises(backup.ErroBackup, match="chave pública inválida"):
        backup.cifra(b"x", base64.b64encode(b"curta").decode())
    with pytest.raises(backup.ErroBackup, match="chave pública inválida"):
        backup.cifra(b"x", "isso não é base64!")

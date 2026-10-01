"""Primitivas de segurança do cadastro (core.seguranca)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from telegrana.core import seguranca as seg


def test_token_de_convite_cabe_no_deep_link_e_so_vai_ao_banco_como_hash() -> None:
    token = seg.novo_token_convite()
    assert seg.token_valido(token)
    assert len(token) == 43
    assert len(seg.hash_token(token)) == 32
    assert seg.hash_token(token) != seg.hash_token(seg.novo_token_convite())


@pytest.mark.parametrize("token", ["", "curto", "x" * 44, "a" * 42 + "!", "ç" * 43])
def test_token_invalido(token: str) -> None:
    assert not seg.token_valido(token)


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("5511999998888", "+5511999998888"),
        ("+55 (11) 99999-8888", "+5511999998888"),
        ("1234567", None),
        ("1234567890123456", None),
    ],
)
def test_normaliza_telefone(bruto: str, esperado: str | None) -> None:
    assert seg.normaliza_telefone(bruto) == esperado


def test_hmac_do_telefone_depende_do_pepper() -> None:
    a = seg.hmac_telefone("+5511999998888", b"a" * 32)
    assert len(a) == 32
    assert a == seg.hmac_telefone("+5511999998888", b"a" * 32)
    assert a != seg.hmac_telefone("+5511999998888", b"b" * 32)


def test_pepper_curto_e_recusado() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        seg.decodifica_pepper("YWJj")


def test_codigo_de_recuperacao_ida_e_volta() -> None:
    codigo = seg.novo_codigo()
    assert len(codigo.exibicao) == 24
    assert codigo.exibicao.count("-") == 4
    assert seg.separa_codigo(codigo.exibicao) == (codigo.seletor, codigo.verificador)
    # Digitado sem hífens, em minúsculas e com espaços.
    assert seg.separa_codigo(codigo.exibicao.replace("-", " ").lower()) == (
        codigo.seletor,
        codigo.verificador,
    )
    guardado = seg.hash_verificador(codigo.verificador)
    assert guardado.startswith("$argon2id$")
    assert codigo.verificador not in guardado
    assert seg.confere_verificador(guardado, codigo.verificador)
    assert not seg.confere_verificador(guardado, seg.novo_codigo().verificador)
    assert not seg.confere_verificador("lixo", codigo.verificador)


def test_codigo_aceita_trocas_comuns() -> None:
    assert seg.separa_codigo("OOOO-IIII-LLLL-0000-1111") == ("00001111", "111100001111")


@pytest.mark.parametrize("digitado", ["", "ABCD", "ABCD-EFGH-JKMN-PQRS-TVWU", "A" * 21])
def test_codigo_mal_formado(digitado: str) -> None:
    assert seg.separa_codigo(digitado) is None


def test_trava_progressiva() -> None:
    assert seg.trava_para(4) is None
    assert seg.trava_para(5) == timedelta(minutes=15)
    assert seg.trava_para(6) == timedelta(minutes=30)
    assert seg.trava_para(50) == timedelta(hours=24)


def test_identificador_curto_ida_e_volta() -> None:
    valor = uuid.uuid4()
    curto = seg.curto(valor)
    assert len(curto) == 22
    assert seg.longo(curto) == valor
    assert seg.longo("curto") is None
    assert seg.longo("!" * 22) is None

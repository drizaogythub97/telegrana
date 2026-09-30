"""Configuração: segredos do SSM nunca aparecem em repr/log."""

import pytest

from telegrana.infra import config

VALORES = {
    "/telegrana/dev/telegram/bot_token": "123:token-secreto",
    "/telegrana/dev/telegram/webhook_secret": "segredo-webhook",
    "/telegrana/dev/neon/app_url": "postgresql://telegrana_app:senha@host/neondb",
}


def busca(nomes: list[str]) -> dict[str, str]:
    return {n: VALORES[n] for n in nomes if n in VALORES}


def test_carrega_e_esconde_segredos() -> None:
    s = config.load_settings(busca, {"TELEGRANA_ENV": "dev", "ADMIN_TELEGRAM_ID": "42"})
    assert s.admin_telegram_id == 42
    assert s.telegram_bot_token == "123:token-secreto"
    texto = repr(s)
    for segredo in VALORES.values():
        assert segredo not in texto


@pytest.mark.parametrize(
    "environ",
    [
        {"ADMIN_TELEGRAM_ID": "42"},
        {"TELEGRANA_ENV": "producao", "ADMIN_TELEGRAM_ID": "42"},
        {"TELEGRANA_ENV": "dev"},
        {"TELEGRANA_ENV": "dev", "ADMIN_TELEGRAM_ID": "abc"},
    ],
)
def test_ambiente_invalido(environ: dict[str, str]) -> None:
    with pytest.raises(config.ConfigError):
        config.load_settings(busca, environ)


def test_parametro_faltando_nao_expoe_valores() -> None:
    def incompleto(nomes: list[str]) -> dict[str, str]:
        return {nomes[0]: VALORES[nomes[0]]}

    with pytest.raises(config.ConfigError) as info:
        config.load_settings(incompleto, {"TELEGRANA_ENV": "dev", "ADMIN_TELEGRAM_ID": "42"})
    assert "token-secreto" not in str(info.value)

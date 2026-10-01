"""Configuração: segredos do SSM nunca aparecem em repr/log."""

import pytest

from telegrana.infra import config

VALORES = {
    "/telegrana/dev/telegram/bot_token": "123:token-secreto",
    "/telegrana/dev/telegram/webhook_secret": "segredo-webhook",
    "/telegrana/dev/neon/app_url": "postgresql://telegrana_app:senha@host/neondb",
    "/telegrana/dev/phone/hmac_pepper": "pepper-secreto-pepper-secreto-pepper",
    "/telegrana/dev/legal/termos": '{"versao": 1, "url": "https://telegra.ph/t", "sha256": "00"}',
    "/telegrana/dev/legal/privacidade": '{"versao": 1, "url": "https://telegra.ph/p", "sha256": "00"}',
    "/telegrana/dev/admin/contact": "@admin",
}
SEGREDOS = ("123:token-secreto", "segredo-webhook", "senha", "pepper-secreto")


def busca(nomes: list[str]) -> dict[str, str]:
    return {n: VALORES[n] for n in nomes if n in VALORES}


def test_carrega_e_esconde_segredos() -> None:
    s = config.load_settings(busca, {"TELEGRANA_ENV": "dev", "ADMIN_TELEGRAM_ID": "42"})
    assert s.admin_telegram_id == 42
    assert s.telegram_bot_token == "123:token-secreto"
    texto = repr(s)
    for segredo in SEGREDOS:
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

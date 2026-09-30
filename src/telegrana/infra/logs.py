"""Logs estruturados sem dados pessoais (PLANO 8.5).

A Lambda usa o formato JSON nativo (LoggingConfig no template). Aqui só garantimos que
bibliotecas de HTTP não registrem URLs: a URL da Bot API contém o token do bot.
"""

from __future__ import annotations

import logging

_SILENCIADOS = ("httpx", "httpcore", "urllib3", "botocore", "boto3")


def configure(level: int = logging.INFO) -> None:
    logging.getLogger().setLevel(level)
    for nome in _SILENCIADOS:
        logging.getLogger(nome).setLevel(logging.WARNING)

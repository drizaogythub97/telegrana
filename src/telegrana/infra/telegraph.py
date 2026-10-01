"""Publicação dos textos legais no Telegraph (PLANO 3.6; D032, D033).

Converte o subconjunto de Markdown usado em `legal/*.md` para os nós do Telegraph
(tags permitidas: h3, h4, p, ul, li, blockquote, b, i, code, br, a) e chama a API.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

API = "https://api.telegra.ph"
LIMITE_BYTES = 64 * 1024  # limite do conteúdo de uma página

type No = str | dict[str, Any]

_INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\*[^*\s][^*]*\*)")


class TelegraphError(RuntimeError):
    """Falha da API do Telegraph (sem o token na mensagem)."""


def inline(texto: str) -> list[No]:
    """**negrito**, *itálico* e `código`."""
    nos: list[No] = []
    for parte in _INLINE.split(texto):
        if not parte:
            continue
        if parte.startswith("**") and parte.endswith("**") and len(parte) > 4:
            nos.append({"tag": "b", "children": inline(parte[2:-2])})
        elif parte.startswith("`") and parte.endswith("`") and len(parte) > 2:
            nos.append({"tag": "code", "children": [parte[1:-1]]})
        elif parte.startswith("*") and parte.endswith("*") and len(parte) > 2:
            nos.append({"tag": "i", "children": inline(parte[1:-1])})
        else:
            nos.append(parte)
    return nos


def _celulas(linha: str) -> list[str]:
    return [c.strip() for c in linha.strip().strip("|").split("|")]


def _tabela(linhas: list[str]) -> No:
    """Telegraph não tem tabela: cada linha vira um item com os rótulos do cabeçalho."""
    cabecalho = _celulas(linhas[0])
    itens: list[No] = []
    for linha in linhas[2:]:
        celulas = _celulas(linha)
        filhos: list[No] = [{"tag": "b", "children": inline(celulas[0])}]
        for rotulo, valor in zip(cabecalho[1:], celulas[1:], strict=False):
            filhos += [{"tag": "br"}, {"tag": "i", "children": [f"{rotulo}: "]}, *inline(valor)]
        itens.append({"tag": "li", "children": filhos})
    return {"tag": "ul", "children": itens}


def converte(markdown: str) -> tuple[str, list[No]]:
    """(título, nós). O título é o primeiro `# `; ele sai do corpo."""
    titulo = ""
    nos: list[No] = []
    linhas = markdown.splitlines()
    i = 0
    while i < len(linhas):
        linha = linhas[i].rstrip()
        if not linha.strip():
            i += 1
            continue
        if linha.startswith("# ") and not titulo:
            titulo = linha[2:].strip()
        elif linha.startswith("### "):
            nos.append({"tag": "h4", "children": inline(linha[4:].strip())})
        elif linha.startswith("## "):
            nos.append({"tag": "h3", "children": inline(linha[3:].strip())})
        elif linha.startswith("|"):
            bloco = []
            while i < len(linhas) and linhas[i].startswith("|"):
                bloco.append(linhas[i])
                i += 1
            nos.append(_tabela(bloco))
            continue
        elif linha.startswith("- "):
            itens: list[No] = []
            while i < len(linhas) and linhas[i].startswith("- "):
                itens.append({"tag": "li", "children": inline(linhas[i][2:].strip())})
                i += 1
            nos.append({"tag": "ul", "children": itens})
            continue
        elif linha.startswith("> "):
            nos.append({"tag": "blockquote", "children": inline(linha[2:].strip())})
        else:
            nos.append({"tag": "p", "children": inline(linha.strip())})
        i += 1
    if not titulo:
        raise ValueError("o documento precisa começar com um título '# '")
    if len(json.dumps(nos, ensure_ascii=False).encode()) > LIMITE_BYTES:
        raise ValueError("documento maior que o limite de 64 KB do Telegraph")
    return titulo, nos


def chama(metodo: str, client: httpx.Client | None = None, **params: Any) -> Any:
    dados = {k: json.dumps(v) if isinstance(v, list) else v for k, v in params.items()}
    try:
        resposta = (client or httpx.Client(timeout=20.0)).post(f"{API}/{metodo}", data=dados)
        corpo = resposta.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise TelegraphError(f"{metodo}: falha de comunicação ({type(exc).__name__})") from None
    if not isinstance(corpo, dict) or not corpo.get("ok"):
        erro = str(corpo.get("error", "")) if isinstance(corpo, dict) else ""
        raise TelegraphError(f"{metodo}: {erro[:200]}")
    return corpo["result"]

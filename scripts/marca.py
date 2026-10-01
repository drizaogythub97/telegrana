#!/usr/bin/env python3
"""Gera os recortes da logo em assets/brand/out/ (PLANO 7.2). Não altera o original.

Uso:  uv run python scripts/marca.py

Saídas:
- icon-640.png (+ 512, 256, 128, 64): só o símbolo, fundo branco, cabe no recorte redondo
  da foto do bot;
- logo-full.png: símbolo + nome, fundo transparente;
- logo-horizontal.png: símbolo à esquerda, nome à direita (cabeçalho de PDF/XLSX);
- logo-mono-white.png: versão branca (vazada) para aplicar sobre o degradê;
- previa.png: folha de prévia para aprovação (não vai para o bot).

Fundo: o branco ligado à borda da imagem (e o miolo das letras do nome) vira
transparente com "cor para alfa" contra o branco; o branco de dentro do símbolo (o "$")
fica. Requer Pillow (dependência só de desenvolvimento).
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

RAIZ = Path(__file__).resolve().parent.parent
ORIGINAL = RAIZ / "assets" / "brand" / "logo-original.png"
SAIDA = RAIZ / "assets" / "brand" / "out"
sys.path.insert(0, str(RAIZ / "src"))

from telegrana.exports import brand  # noqa: E402

LIMIAR_FUNDO = 40  # distância máxima do branco para contar como fundo
OPACO = 128


def _distancia_do_branco(rgb: Image.Image) -> Image.Image:
    """255 - menor canal: 0 no branco puro, ~255 em cores saturadas."""
    r, g, b = rgb.split()
    return ImageChops.invert(ImageChops.darker(r, ImageChops.darker(g, b)))


def _regiao_de_fundo(dist: Image.Image, faixa_texto: int) -> Image.Image:
    """Máscara (L, 255 = fundo): perto do branco e ligada à borda, ou na faixa do nome."""
    largura, altura = dist.size
    d = dist.load()
    if d is None:
        raise RuntimeError("imagem vazia ou sem acesso aos pixels")
    regiao = Image.new("L", dist.size, 0)
    m = regiao.load()
    if m is None:
        raise RuntimeError("imagem vazia ou sem acesso aos pixels")
    fila: deque[tuple[int, int]] = deque()
    for x in range(largura):
        fila.extend(((x, 0), (x, altura - 1)))
    for y in range(altura):
        fila.extend(((0, y), (largura - 1, y)))
    while fila:
        x, y = fila.popleft()
        if m[x, y] or d[x, y] > LIMIAR_FUNDO:  # type: ignore[operator]
            continue
        m[x, y] = 255
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < largura and 0 <= ny < altura and not m[nx, ny]:
                fila.append((nx, ny))
    # Miolo das letras (e, g, a): fechado pelo traço, mas é fundo.
    for y in range(faixa_texto, altura):
        for x in range(largura):
            if d[x, y] <= LIMIAR_FUNDO:  # type: ignore[operator]
                m[x, y] = 255
    return regiao


def _sem_fundo(rgb: Image.Image, faixa_texto: int) -> Image.Image:
    dist = _distancia_do_branco(rgb)
    regiao = _regiao_de_fundo(dist, faixa_texto)
    # Faixa de 2 px em volta do fundo: as bordas suavizadas também passam por cor→alfa.
    borda = ImageChops.subtract(regiao.filter(ImageFilter.MaxFilter(5)), regiao)
    saida = rgb.convert("RGBA")
    px, d, mr, mb = saida.load(), dist.load(), regiao.load(), borda.load()
    if px is None or d is None or mr is None or mb is None:
        raise RuntimeError("imagem vazia ou sem acesso aos pixels")
    largura, altura = rgb.size
    for y in range(altura):
        for x in range(largura):
            if not (mr[x, y] or mb[x, y]):
                continue
            alfa = int(d[x, y])  # type: ignore[arg-type]
            if mr[x, y]:
                alfa = max(0, alfa - 4) * 255 // 251  # o "branco" do arquivo é ~251-254
            if alfa == 0:
                px[x, y] = (255, 255, 255, 0)
                continue
            r, g, b, _ = px[x, y]  # type: ignore[misc]
            # Tira a mistura com o branco (despremultiplica).
            px[x, y] = (
                *(max(0, min(255, (c - 255 + alfa) * 255 // alfa)) for c in (r, g, b)),
                alfa,
            )
    return saida


def _faixas(alfa: Image.Image) -> tuple[tuple[int, int], tuple[int, int]]:
    """(topo, base) do símbolo e do nome, separados pela maior faixa vazia horizontal."""
    largura, altura = alfa.size
    a = alfa.load()
    if a is None:
        raise RuntimeError("imagem vazia ou sem acesso aos pixels")
    cheias = [any(a[x, y] > OPACO for x in range(0, largura, 2)) for y in range(altura)]  # type: ignore[operator]
    linhas = [y for y, c in enumerate(cheias) if c]
    topo, base = linhas[0], linhas[-1]
    melhor, inicio, vazio = (0, 0), None, 0
    for y in range(topo, base):
        if not cheias[y]:
            inicio = y if inicio is None else inicio
            vazio += 1
            if vazio > melhor[0]:
                melhor = (vazio, inicio)
        else:
            inicio, vazio = None, 0
    corte = melhor[1] + melhor[0] // 2
    return (topo, corte), (corte, base + 1)


def _recorta(img: Image.Image, topo: int, base: int) -> Image.Image:
    faixa = img.crop((0, topo, img.width, base))
    caixa = faixa.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    if caixa is None:
        raise RuntimeError("imagem vazia ou sem acesso aos pixels")
    return faixa.crop(caixa)


def _icone(simbolo: Image.Image) -> Image.Image:
    """Quadrado branco em que o símbolo cabe no círculo com folga (foto redonda do bot).

    Os cantos da caixa do símbolo quase não têm desenho (exceto a ponta da seta), então
    a meia-diagonal pode ocupar 95% do raio.
    """
    meia_diagonal = (simbolo.width**2 + simbolo.height**2) ** 0.5 / 2
    lado = int(meia_diagonal * 2 / 0.95)
    quadro = Image.new("RGB", (lado, lado), (255, 255, 255))
    quadro.paste(simbolo, ((lado - simbolo.width) // 2, (lado - simbolo.height) // 2), simbolo)
    return quadro


def _mono_branca(rgba: Image.Image) -> Image.Image:
    """Branco vazado: a opacidade segue a "força" da cor (o branco interno vira furo)."""
    dist = _distancia_do_branco(rgba.convert("RGB"))
    alfa = ImageChops.multiply(rgba.getchannel("A"), dist.point(lambda v: min(255, v * 2)))
    branca = Image.new("RGBA", rgba.size, (255, 255, 255, 0))
    branca.putalpha(alfa)
    return branca


def _degrade(tamanho: tuple[int, int]) -> Image.Image:
    a, b = brand.hex_rgb(brand.AZUL), brand.hex_rgb(brand.VERDE)
    fundo = Image.new("RGB", tamanho)
    desenho = ImageDraw.Draw(fundo)
    for x in range(tamanho[0]):
        t = x / max(1, tamanho[0] - 1)
        desenho.line(
            [(x, 0), (x, tamanho[1])], fill=tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
        )
    return fundo


def _encaixa(img: Image.Image, caixa: tuple[int, int]) -> Image.Image:
    copia = img.copy()
    copia.thumbnail(caixa, Image.Resampling.LANCZOS)
    return copia


def _previa(
    icone: Image.Image, cheia: Image.Image, horizontal: Image.Image, mono: Image.Image
) -> Image.Image:
    folha = Image.new("RGB", (1500, 1020), brand.hex_rgb(brand.FUNDO))
    desenho = ImageDraw.Draw(folha)
    try:  # fonte com acentos (Windows); na falta, a padrão do Pillow
        desenho.font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        desenho.font = ImageFont.load_default(18)
    # Foto do bot: como o Telegram mostra (redonda), grande e minúscula.
    for tamanho, x in ((300, 40), (64, 380), (40, 470)):
        foto = icone.resize((tamanho, tamanho), Image.Resampling.LANCZOS)
        mascara = Image.new("L", (tamanho, tamanho), 0)
        ImageDraw.Draw(mascara).ellipse((0, 0, tamanho - 1, tamanho - 1), fill=255)
        folha.paste(foto, (x, 40), mascara)
    desenho.text((40, 350), "foto do bot (recorte redondo): 300, 64 e 40 px", fill=(15, 23, 42))
    # Logo completa sobre fundos diferentes.
    for i, cor in enumerate(((255, 255, 255), brand.hex_rgb(brand.TEXTO))):
        x = 560 + i * 470
        folha.paste(Image.new("RGB", (450, 330), cor), (x, 20))
        logo = _encaixa(cheia, (400, 290))
        folha.paste(logo, (x + (450 - logo.width) // 2, 20 + (330 - logo.height) // 2), logo)
    desenho.text((560, 360), "logo-full.png (transparente) no claro e no escuro", fill=(15, 23, 42))
    # Horizontal e versão branca sobre o degradê.
    folha.paste(Image.new("RGB", (1420, 260), (255, 255, 255)), (40, 400))
    h = _encaixa(horizontal, (1300, 200))
    folha.paste(h, (40 + (1420 - h.width) // 2, 400 + (260 - h.height) // 2), h)
    desenho.text((40, 670), "logo-horizontal.png (cabeçalho de PDF e XLSX)", fill=(15, 23, 42))
    folha.paste(_degrade((1420, 260)), (40, 700))
    m = _encaixa(mono, (1300, 200))
    folha.paste(m, (40 + (1420 - m.width) // 2, 700 + (260 - m.height) // 2), m)
    desenho.text((40, 970), "logo-mono-white.png sobre o degradê azul→verde", fill=(15, 23, 42))
    return folha


def main() -> int:
    original = Image.open(ORIGINAL).convert("RGB")
    SAIDA.mkdir(parents=True, exist_ok=True)

    # 1ª passada só para achar onde começa o nome; 2ª com o miolo das letras.
    rascunho = _sem_fundo(original, faixa_texto=original.height)
    (s_topo, s_base), (t_topo, t_base) = _faixas(rascunho.getchannel("A"))
    rgba = _sem_fundo(original, faixa_texto=t_topo)

    simbolo = _recorta(rgba, s_topo, s_base)
    nome = _recorta(rgba, t_topo, t_base)
    icone = _icone(simbolo).resize((640, 640), Image.Resampling.LANCZOS)
    icone.save(SAIDA / "icon-640.png", optimize=True)
    icone.save(SAIDA / "icon-640.jpg", quality=95)  # a foto do bot só aceita JPG
    for tamanho in (512, 256, 128, 64):
        icone.resize((tamanho, tamanho), Image.Resampling.LANCZOS).save(
            SAIDA / f"icon-{tamanho}.png", optimize=True
        )

    caixa = rgba.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    if caixa is None:
        raise RuntimeError("imagem vazia ou sem acesso aos pixels")
    cheia = rgba.crop(caixa)
    cheia.save(SAIDA / "logo-full.png", optimize=True)

    altura = nome.height * 2
    s = simbolo.resize(
        (int(simbolo.width * altura / simbolo.height), altura), Image.Resampling.LANCZOS
    )
    vao = nome.height // 2
    horizontal = Image.new("RGBA", (s.width + vao + nome.width, altura), (255, 255, 255, 0))
    horizontal.paste(s, (0, 0), s)
    horizontal.paste(nome, (s.width + vao, (altura - nome.height) // 2), nome)
    horizontal.save(SAIDA / "logo-horizontal.png", optimize=True)

    mono = _mono_branca(cheia)
    mono.save(SAIDA / "logo-mono-white.png", optimize=True)

    _previa(icone, cheia, horizontal, mono).save(SAIDA / "previa.png", optimize=True)
    for arquivo in sorted(SAIDA.iterdir()):
        with Image.open(arquivo) as img:
            print(f"{arquivo.name}: {img.width}x{img.height}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

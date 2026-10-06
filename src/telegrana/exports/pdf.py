"""PDF com a identidade visual (PLANO 6 e 7; S7, D048): fpdf2, leve, sem navegador.

Cabeçalho com a logo e a faixa em degradê azul → verde, resumo em cards, barras por
categoria e a tabela de lançamentos. Fonte Helvetica (Latin-1): emojis e símbolos fora do
Latin-1 saem do texto. Gerado em memória: nada vai para disco.
"""

from __future__ import annotations

import re
from importlib import resources

from fpdf import FPDF

from telegrana.core import valores
from telegrana.exports import brand
from telegrana.exports.dados import Dados, Linha

TIPO = "application/pdf"
_LOGO = resources.files("telegrana.exports").joinpath("logo.png")
_TROCAS = {  # pontuação tipográfica fora do Latin-1 (por código, para não confundir)
    chr(0x2014): "-",
    chr(0x2013): "-",
    chr(0x2026): "...",
    chr(0x2192): "->",
    chr(0x201C): '"',
    chr(0x201D): '"',
    chr(0x2018): "'",
    chr(0x2019): "'",
}
MAX_BARRAS = 10
_COLUNAS = (("Data", 18), ("Descrição", 66), ("Categoria", 38), ("Forma", 32), ("Valor", 32))


def texto(s: str) -> str:
    """Só Latin-1 (fonte padrão do PDF): troca pontuação tipográfica e tira emojis."""
    for de, para in _TROCAS.items():
        s = s.replace(de, para)
    limpo = "".join(c for c in s if ord(c) < 256)
    return re.sub(r"\s+", " ", limpo).strip()


def _cor(cor: str) -> tuple[int, int, int]:
    return brand.hex_rgb(cor)


def _mistura(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


class _Pdf(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", size=8)
        self.set_text_color(*_cor("#64748B"))
        self.cell(0, 6, f"Telegrana · página {self.page_no()}/{{nb}}", align="C")


def _degrade(pdf: FPDF, x: float, y: float, w: float, h: float) -> None:
    """Faixa azul → verde (desenhada em fatias: funciona em qualquer leitor de PDF)."""
    cores = [_cor(c) for c in brand.DEGRADE]
    fatias = 90
    for i in range(fatias):
        t = i / (fatias - 1)
        trecho = 0 if t <= 0.5 else 1
        local = t / 0.5 if trecho == 0 else (t - 0.5) / 0.5
        pdf.set_fill_color(*_mistura(cores[trecho], cores[trecho + 1], local))
        pdf.rect(x + w * i / fatias, y, w / fatias + 0.2, h, style="F")


def _cabecalho(pdf: FPDF, d: Dados) -> None:
    pdf.image(str(_LOGO), x=12, y=10, w=52)
    pdf.set_xy(80, 11)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*_cor(brand.TEXTO))
    pdf.cell(118, 7, texto(d.titulo), align="R")
    pdf.set_xy(80, 18)
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(*_cor("#475569"))
    pdf.cell(118, 5, texto(f"{d.visao} · gerado em {d.gerado:%d/%m/%Y}"), align="R")
    _degrade(pdf, 12, 28, 186, 2.2)
    pdf.set_y(36)


def _cards(pdf: FPDF, d: Dados) -> None:
    cards = (
        ("Entrou", d.entrou, brand.VERDE_ESCURO),
        ("Saiu", d.saiu, brand.GASTO),
        ("Saldo", d.saldo, brand.AZUL if d.saldo >= 0 else brand.GASTO),
    )
    y = pdf.get_y()
    largura = 59
    for i, (rotulo, valor, cor) in enumerate(cards):
        x = 12 + i * (largura + 4.5)
        pdf.set_fill_color(*_cor(brand.FUNDO))
        pdf.set_draw_color(*_cor("#E2E8F0"))
        pdf.rect(x, y, largura, 20, style="DF", round_corners=True, corner_radius=2.5)
        pdf.set_xy(x + 4, y + 3)
        pdf.set_font("Helvetica", size=9)
        pdf.set_text_color(*_cor("#64748B"))
        pdf.cell(largura - 8, 5, rotulo)
        pdf.set_xy(x + 4, y + 9)
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(*_cor(cor))
        sinal = "-" if valor < 0 else ""
        pdf.cell(largura - 8, 8, texto(sinal + valores.em_reais(abs(valor))))
    pdf.set_y(y + 27)


def _titulo(pdf: FPDF, s: str) -> None:
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*_cor(brand.TEXTO))
    pdf.cell(0, 7, texto(s), new_x="LMARGIN", new_y="NEXT")


def _barras(pdf: FPDF, d: Dados) -> None:
    gastos = [c for c in d.categorias if c.gastos][:MAX_BARRAS]
    if not gastos:
        return
    _titulo(pdf, "Onde mais gastou")
    total = sum(c.gastos for c in d.categorias) or 1
    maior = max(c.gastos for c in gastos)
    for c in gastos:
        y = pdf.get_y() + 1
        pdf.set_xy(12, y)
        pdf.set_font("Helvetica", size=9)
        pdf.set_text_color(*_cor(brand.TEXTO))
        pdf.cell(46, 6, texto(c.nome)[:28])
        largura = max(1.0, 92 * c.gastos / maior)
        pdf.set_fill_color(*_cor(brand.AZUL))
        pdf.rect(60, y + 1, largura, 4, style="F")
        pdf.set_xy(156, y)
        pdf.cell(
            42,
            6,
            texto(f"{valores.em_reais(c.gastos)} · {round(100 * c.gastos / total)}%"),
            align="R",
        )
        pdf.set_y(y + 6)
    pdf.ln(4)


def _linha_tabela(pdf: FPDF, valores_: tuple[str, ...], cabecalho: bool, par: bool) -> None:
    if cabecalho:
        pdf.set_fill_color(*_cor(brand.AZUL))
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 8.5)
    else:
        pdf.set_fill_color(*(_cor(brand.FUNDO) if par else (255, 255, 255)))
        pdf.set_text_color(*_cor(brand.TEXTO))
        pdf.set_font("Helvetica", size=8.5)
    for (_, largura), v in zip(_COLUNAS, valores_, strict=True):
        alinhamento = "R" if _ == "Valor" else "L"
        limite = max(4, int(largura / 1.65))
        pdf.cell(
            largura,
            6,
            v if len(v) <= limite else v[: limite - 1] + ".",
            fill=True,
            align=alinhamento,
        )
    pdf.ln(6)


def _tabela(pdf: FPDF, titulo: str, linhas: tuple[Linha, ...]) -> None:
    if not linhas:
        return
    if pdf.get_y() > 250:
        pdf.add_page()
    _titulo(pdf, titulo)
    cab = tuple(t for t, _ in _COLUNAS)
    _linha_tabela(pdf, cab, True, False)
    for i, x in enumerate(linhas):
        if pdf.get_y() > 275:
            pdf.add_page()
            _linha_tabela(pdf, cab, True, False)
        descricao = x.descricao + (f" ({x.parcela})" if x.parcela else "")
        sinal = "+" if x.tipo == "Ganho" else ""
        _linha_tabela(
            pdf,
            (
                f"{x.dia:%d/%m}",
                texto(descricao) or "-",
                texto(x.categoria) or "-",
                texto(x.forma) or "-",
                sinal + valores.em_reais(x.centavos),
            ),
            False,
            i % 2 == 1,
        )
    pdf.ln(4)


def gera(d: Dados) -> bytes:
    pdf = _Pdf(format="A4")
    pdf.set_margins(12, 10, 12)
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_title(texto(f"Telegrana - {d.titulo}"))
    pdf.set_author("Telegrana")
    pdf.add_page()
    _cabecalho(pdf, d)
    _cards(pdf, d)
    _barras(pdf, d)
    _tabela(pdf, "Lançamentos", d.lancamentos)
    if d.truncado:
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(
            0, 5, "Período longo: só os lançamentos que couberam. Peça a planilha para ver todos."
        )
    return bytes(pdf.output())

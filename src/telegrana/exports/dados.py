"""O que vai num arquivo exportado (S7, D048): montado pelo núcleo, desenhado em PDF ou XLSX.

Só dados já calculados pelo código/SQL (regra de ouro 2). Valores em centavos inteiros;
quem formata é cada gerador.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class Linha:
    dia: date
    descricao: str
    categoria: str
    forma: str
    tipo: str  # "Gasto" | "Ganho"
    centavos: int
    parcela: str  # "2/4" ou ""


@dataclass(frozen=True, slots=True)
class CategoriaTotal:
    nome: str
    gastos: int
    ganhos: int


@dataclass(frozen=True, slots=True)
class Dados:
    titulo: str  # "Relatório de outubro/2026"
    periodo: str  # "outubro/2026", "01/08 a 06/10/2026"
    visao: str  # "Realizado (o que já foi pago)"
    gerado: date
    entrou: int
    saiu: int
    categorias: tuple[CategoriaTotal, ...]
    lancamentos: tuple[Linha, ...]
    compromissos: tuple[Linha, ...]
    truncado: bool = False  # mais lançamentos do que cabem no arquivo

    @property
    def saldo(self) -> int:
        return self.entrou - self.saiu

    def nome_arquivo(self, extensao: str, inicio: date) -> str:
        """Sem dado pessoal: só o período."""
        return f"telegrana-{inicio:%Y-%m}.{extensao}"

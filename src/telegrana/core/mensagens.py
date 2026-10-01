"""Entradas e saídas do núcleo, sem nada de canal (regra de ouro 10).

O adaptador de cada canal (Telegram hoje, WhatsApp na S9) converte o que chega em
`Entrada` e desenha a `Saida`. Marcação de texto mínima, traduzida pelo adaptador:
`**negrito**` e `` `código` ``. Conteúdo vindo do usuário passa por `seguro()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ADMIN = "admin"  # destino especial: o administrador


@dataclass(frozen=True, slots=True)
class Entrada:
    canal: str
    external_id: str  # identidade verificada pelo canal (from.id no Telegram)
    nome: str = ""  # nome de exibição no canal (só para o pedido de acesso)
    username: str | None = None
    texto: str = ""
    comando: str | None = None  # sem a barra, minúsculo
    argumento: str = ""
    acao: str | None = None  # botão tocado
    telefone: str | None = None  # contato compartilhado pelo próprio remetente
    contato_alheio: bool = False  # contato de outra pessoa (recusado)
    pergunta: str | None = None  # id da pergunta do bot que esta mensagem responde


@dataclass(frozen=True, slots=True)
class Botao:
    rotulo: str
    acao: str | None = None
    url: str | None = None


@dataclass(frozen=True, slots=True)
class Saida:
    texto: str
    destino: str | None = None  # None = quem mandou a entrada; ADMIN; ou um external_id
    botoes: tuple[tuple[Botao, ...], ...] = ()
    pedir_telefone: str | None = None  # rótulo do botão "compartilhar meu número"
    pergunta: str | None = None  # pede resposta direta (id em textos.PERGUNTAS)
    protegida: bool = False  # sem encaminhar nem salvar (código de recuperação)
    tirar_teclado: bool = False


@dataclass(slots=True)
class Resultado:
    saidas: list[Saida] = field(default_factory=list)
    apagar_entrada: bool = False  # a mensagem do usuário tinha segredo (código)
    aviso: str | None = None  # resposta curta ao toque no botão
    rotulo: str = "nada"  # rótulo técnico para log (sem conteúdo do usuário)

    def diz(self, texto: str, **kw: object) -> Resultado:
        self.saidas.append(Saida(texto, **kw))  # type: ignore[arg-type]
        return self


def seguro(texto: str, limite: int = 200) -> str:
    """Tira a marcação do conteúdo digitado pelo usuário antes de ecoar."""
    return texto.replace("*", "").replace("`", "").strip()[:limite]

"""Adaptador do Telegram: leitura dos updates e desenho das saídas."""

from __future__ import annotations

from typing import Any

import pytest

from telegrana.channels.telegram import adaptador
from telegrana.core import textos
from telegrana.core.mensagens import ADMIN, Botao, Saida

BOT = 123


def mensagem(**extra: Any) -> dict[str, Any]:
    base = {
        "message_id": 7,
        "from": {"id": 42, "first_name": "Maria", "last_name": "Souza", "username": "maria"},
        "chat": {"id": 42, "type": "private"},
    }
    return {"message": {**base, **extra}}


def test_bot_id_vem_do_token() -> None:
    assert adaptador.bot_id("123456:ABC-def") == 123456


def test_comando_com_argumento_e_nome_do_bot() -> None:
    convertido = adaptador.para_entrada(mensagem(text="/Start@TelegranaBot abc"), BOT)
    assert convertido is not None
    entrada, origem = convertido
    assert (entrada.comando, entrada.argumento) == ("start", "abc")
    assert entrada.external_id == "42"
    assert entrada.nome == "Maria Souza"
    assert origem.chat_id == 42
    assert origem.message_id == 7


def test_contato_proprio_e_alheio() -> None:
    proprio = adaptador.para_entrada(
        mensagem(contact={"user_id": 42, "phone_number": "5511999998888"}), BOT
    )
    alheio = adaptador.para_entrada(
        mensagem(contact={"user_id": 99, "phone_number": "5511000000000"}), BOT
    )
    sem_user = adaptador.para_entrada(mensagem(contact={"phone_number": "5511000000000"}), BOT)
    assert proprio is not None
    assert alheio is not None
    assert sem_user is not None
    assert proprio[0].telefone == "5511999998888"
    assert not proprio[0].contato_alheio
    assert alheio[0].telefone is None
    assert alheio[0].contato_alheio
    assert sem_user[0].contato_alheio  # contato sem user_id não é do remetente


def test_resposta_a_pergunta_do_bot() -> None:
    pergunta = textos.primeira_linha(textos.PERGUNTAS["codigo"])
    respondida = {"from": {"id": BOT, "is_bot": True}, "text": pergunta + "\nmais texto"}
    convertido = adaptador.para_entrada(mensagem(text="ABCD", reply_to_message=respondida), BOT)
    assert convertido is not None
    assert convertido[0].pergunta == "codigo"


def test_resposta_a_mensagem_de_outro_nao_conta_como_pergunta() -> None:
    pergunta = textos.primeira_linha(textos.PERGUNTAS["codigo"])
    respondida = {"from": {"id": 999}, "text": pergunta}
    convertido = adaptador.para_entrada(mensagem(text="ABCD", reply_to_message=respondida), BOT)
    assert convertido is not None
    assert convertido[0].pergunta is None


def test_ignora_grupo_e_bots() -> None:
    grupo = mensagem(text="oi")
    grupo["message"]["chat"]["type"] = "group"
    robo = mensagem(text="oi")
    robo["message"]["from"]["is_bot"] = True
    assert adaptador.para_entrada(grupo, BOT) is None
    assert adaptador.para_entrada(robo, BOT) is None
    assert adaptador.para_entrada({"edited_message": {}}, BOT) is None


def test_callback() -> None:
    update = {
        "callback_query": {
            "id": "cb1",
            "from": {"id": 42, "first_name": "Maria"},
            "message": {"message_id": 9, "chat": {"id": 42, "type": "private"}},
            "data": "termos:aceito",
        }
    }
    convertido = adaptador.para_entrada(update, BOT)
    assert convertido is not None
    entrada, origem = convertido
    assert entrada.acao == "termos:aceito"
    assert origem.callback_id == "cb1"
    assert origem.message_id == 9


def test_html_escapa_tudo_e_traduz_a_marcacao() -> None:
    assert adaptador.html_de("**Oi** <b>x</b> & `A-1`") == (
        "<b>Oi</b> &lt;b&gt;x&lt;/b&gt; &amp; <code>A-1</code>"
    )


def test_teclados() -> None:
    inline = adaptador.teclado(
        Saida("x", botoes=((Botao("A", "a"), Botao("Site", url="https://telegra.ph/x")),))
    )
    assert inline == {
        "inline_keyboard": [
            [{"text": "A", "callback_data": "a"}, {"text": "Site", "url": "https://telegra.ph/x"}]
        ]
    }
    contato = adaptador.teclado(Saida("x", pedir_telefone="📱"))
    assert contato is not None
    assert contato["keyboard"] == [[{"text": "📱", "request_contact": True}]]
    assert adaptador.teclado(Saida("x", pergunta="codigo")) == {
        "force_reply": True,
        "input_field_placeholder": "Responda aqui",
    }
    assert adaptador.teclado(Saida("x", tirar_teclado=True)) == {"remove_keyboard": True}
    assert adaptador.teclado(Saida("x")) is None


def test_destino() -> None:
    origem = adaptador.Origem(chat_id=42)
    assert adaptador.destino(Saida("x"), origem, 1) == 42
    assert adaptador.destino(Saida("x", destino=ADMIN), origem, 1) == 1
    assert adaptador.destino(Saida("x", destino="77"), origem, 1) == 77


def test_perguntas_tem_primeiras_linhas_distintas() -> None:
    linhas = [textos.primeira_linha(p) for p in textos.PERGUNTAS.values()]
    assert len(set(linhas)) == len(linhas)
    for chave, texto in textos.PERGUNTAS.items():
        assert textos.pergunta_respondida(textos.primeira_linha(texto)) == chave


def test_voz_vira_audio_que_so_baixa_quando_pedido() -> None:
    baixados: list[tuple[str, int]] = []

    def baixar(file_id: str, limite: int) -> bytes:
        baixados.append((file_id, limite))
        return b"OggS"

    voz = {"file_id": "VOZ1", "duration": 7, "mime_type": "audio/ogg", "file_size": 9000}
    entrada, _ = adaptador.para_entrada(mensagem(voice=voz), BOT, baixar)  # type: ignore[misc]
    assert entrada.audio is not None
    assert (entrada.audio.duracao, entrada.audio.tamanho, entrada.audio.formato) == (7, 9000, "ogg")
    assert baixados == []  # nada baixado até o núcleo pedir
    assert entrada.audio.baixar() == b"OggS"
    assert baixados == [("VOZ1", 20 * 1024 * 1024)]


def test_arquivo_de_audio_formato_e_falha_do_canal() -> None:
    from telegrana.channels.telegram.api import TelegramError
    from telegrana.core.mensagens import ErroCanal

    def falha(file_id: str, limite: int) -> bytes:
        raise TelegramError("download: HTTP 404")

    arquivo = {"file_id": "A", "duration": 30, "file_name": "nota.m4a"}
    entrada, _ = adaptador.para_entrada(mensagem(audio=arquivo), BOT, falha)  # type: ignore[misc]
    assert entrada.audio is not None
    assert entrada.audio.formato == "m4a"
    with pytest.raises(ErroCanal):
        entrada.audio.baixar()
    # Sem baixador (ex.: testes antigos), áudio é ignorado.
    sem, _ = adaptador.para_entrada(mensagem(voice={"file_id": "V"}), BOT)  # type: ignore[misc]
    assert sem.audio is None


class _ApiAnota:
    def __init__(self, falha: str | None = None) -> None:
        self.chamadas: list[tuple[str, dict[str, Any]]] = []
        self.falha = falha

    def call(self, metodo: str, **params: Any) -> Any:
        self.chamadas.append((metodo, params))
        if self.falha and metodo == "editMessageText":
            from telegrana.channels.telegram.api import TelegramError

            raise TelegramError(self.falha)
        return {"message_id": 99}


def test_tela_de_ajuste_troca_a_mensagem_tocada() -> None:
    from telegrana.core.mensagens import Resultado

    origem = adaptador.Origem(42, message_id=7, callback_id="cb1")
    r = Resultado(saidas=[Saida("tela nova", botoes=((Botao("ok", "x:1"),),), substitui=True)])
    api = _ApiAnota()
    falhas, _ = adaptador.executa(api, r, origem, BOT)  # type: ignore[arg-type]
    assert falhas == 0
    assert [m for m, _ in api.chamadas] == ["answerCallbackQuery", "editMessageText"]
    assert api.chamadas[1][1]["message_id"] == 7
    # Tocar duas vezes no mesmo: o Telegram responde "not modified" e isso não é falha.
    api = _ApiAnota(falha="editMessageText: HTTP 400 Bad Request: message is not modified")
    assert adaptador.executa(api, r, origem, BOT)[0] == 0  # type: ignore[arg-type]


def test_mensagem_que_abre_a_resposta() -> None:
    assert adaptador.teclado(Saida("✏️ responda", responder=True)) == {
        "force_reply": True,
        "input_field_placeholder": "Responda aqui",
    }

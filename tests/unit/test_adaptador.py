"""Adaptador do Telegram: leitura dos updates e desenho das saídas."""

from __future__ import annotations

from typing import Any

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

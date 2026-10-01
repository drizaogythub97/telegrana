"""Cenários do critério de pronto da S1 (PLANO 14) de ponta a ponta (D034).

Os testes contam uma história com as mesmas pessoas: a ordem importa.
"Trocar de Telegram" = a mesma pessoa com outro id (o que o Telegram faz quando a
conta é recriada), com o mesmo número ou não.
"""

from __future__ import annotations

import re

import pytest

from tests.e2e.conftest import ADMIN_ID, Mundo, Pessoa

pytestmark = [pytest.mark.e2e, pytest.mark.integration]

_estado: dict[str, str] = {}
_pessoas: dict[str, Pessoa] = {}
TELEFONE_ANA = "5511912345678"
TELEFONE_BRUNO = "5521987654321"


@pytest.fixture
def admin(mundo: Mundo) -> Pessoa:
    return _pessoas.setdefault("admin", mundo.pessoa(ADMIN_ID, "Adriano Admin", "5511900000000"))


@pytest.fixture
def ana(mundo: Mundo) -> Pessoa:
    return _pessoas.setdefault("ana", mundo.pessoa(900_000_101, "Ana Teste", TELEFONE_ANA, "ana"))


@pytest.fixture
def bruno(mundo: Mundo) -> Pessoa:
    return _pessoas.setdefault("bruno", mundo.pessoa(900_000_202, "Bruno Teste", TELEFONE_BRUNO))


def _codigo(texto: str) -> str:
    achado = re.search(r"[0-9A-Z]{4}(?:-[0-9A-Z]{4}){4}", texto)
    assert achado, "código de recuperação não encontrado"
    return achado.group(0)


def test_desconhecido_ve_bot_privado(bruno: Pessoa) -> None:
    bruno.diz("/start")
    tela = bruno.espera("acesso antecipado")
    assert [b["text"] for b in tela.botoes()] == ["🙋 Pedir acesso", "🔄 Já tenho conta"]


def test_entra_pelo_link_e_conclui_o_cadastro(admin: Pessoa, ana: Pessoa, bruno: Pessoa) -> None:
    admin.diz("/link novo")
    link = admin.espera("Link de convite")
    achado = re.search(r"https://t\.me/telegrana_e2e_bot\?start=([A-Za-z0-9_-]{43})", link.texto)
    assert achado, link.texto
    _estado["token"] = achado.group(1)

    ana.diz(f"/start {_estado['token']}")
    ana.espera("Bem-vindo ao Telegrana")
    termos = ana.espera("Antes de começar")
    urls = [b.get("url") for b in termos.botoes() if "url" in b]
    assert urls == ["https://telegra.ph/termos-e2e", "https://telegra.ph/privacidade-e2e"]
    assert "<b>Os dados ficam em servidores nos EUA</b>" in termos.html
    # Recusar os termos (não aceitar): nada avança.
    ana.diz("Ana Teste")
    ana.espera("Antes de começar")
    ana.toca("Li e aceito")
    ana.espera("nome completo")
    ana.diz("Ana Teste")
    ana.espera("É isso mesmo?")
    ana.toca("Sim")
    ana.espera("compartilhe o seu número")
    ana.anexa_contato_de(bruno)
    ana.espera("seu próprio")
    ana.compartilha_meu_numero()
    ana.espera("Número recebido")
    ana.espera("18 anos ou mais?")
    ana.toca("Tenho 18 anos ou mais")
    codigo = ana.espera("Seu código de recuperação")
    assert codigo.protegida, "o código precisa vir protegido (sem encaminhar nem salvar)"
    _estado["codigo_ana"] = _codigo(codigo.texto)
    ana.toca("Guardei")
    ana.espera("Conta criada")
    aviso = admin.espera("criou a conta (convite)")
    assert "Ana Teste" in aviso.texto


def test_botao_usado_some_e_toque_repetido_nao_faz_nada(ana: Pessoa) -> None:
    ana.diz("/codigo_novo")
    ana.espera("Gerar um novo código")
    ana.toca("Cancelar")
    ana.espera("nada foi alterado")
    with pytest.raises(AssertionError, match="não está na tela"):
        ana.toca("Gerar novo código")


def test_comandos_da_conta(ana: Pessoa) -> None:
    ana.diz("/meus_dados")
    dados = ana.espera("Seus dados no Telegrana")
    assert "Ana Teste" in dados.texto
    assert "vinculado ✅" in dados.texto
    ana.diz("/corrigir_nome")
    ana.espera("nome completo correto?")
    ana.responde("Ana Teste Souza")
    ana.espera("Nome atualizado para Ana Teste Souza")
    ana.diz("/termos")
    ana.espera("Termos e privacidade")
    ana.diz("gastei 30 no mercado")
    ana.espera("lançamentos chegam na próxima etapa")


def test_link_revogado_nao_entra(admin: Pessoa, bruno: Pessoa) -> None:
    admin.diz("/link revogar")
    admin.espera("revogado")
    bruno.diz(f"/start {_estado['token']}")
    bruno.espera("acesso antecipado")


def test_pede_acesso_admin_aprova_e_menor_tem_dados_apagados(admin: Pessoa, bruno: Pessoa) -> None:
    bruno.diz("/start")
    bruno.espera("acesso antecipado")
    bruno.toca("Pedir acesso")
    bruno.espera("vão para o administrador")
    bruno.espera("Como você conhece o Adriano?")
    bruno.responde("Sou o primo do teste <b>")
    bruno.espera("Pedido enviado")
    pedido = admin.espera("pediu acesso")
    assert "Sou o primo do teste <b>" in pedido.texto  # o HTML do usuário chega escapado
    admin.toca("Aprovar")
    admin.espera("Acesso liberado")
    bruno.espera("Seu acesso foi liberado")
    bruno.toca("Criar minha conta")
    bruno.espera("Antes de começar")
    bruno.toca("Li e aceito")
    bruno.espera("nome completo")
    bruno.diz("Bruno Teste")
    bruno.espera("É isso mesmo?")
    bruno.toca("Sim")
    bruno.espera("compartilhe o seu número")
    bruno.compartilha_meu_numero()
    bruno.espera("18 anos ou mais?")
    bruno.toca("Não tenho")
    bruno.espera("Os dados do seu cadastro foram apagados")


def test_pedido_recusado(admin: Pessoa, bruno: Pessoa) -> None:
    bruno.diz("/start")
    bruno.espera("acesso antecipado")
    bruno.toca("Pedir acesso")
    bruno.espera("Como você conhece o Adriano?")
    bruno.responde("De novo")
    bruno.espera("Pedido enviado")
    admin.espera("pediu acesso")
    admin.toca("Recusar")
    admin.espera("Pedido recusado")
    bruno.nada_novo()  # a pessoa recusada não é avisada
    bruno.diz("/start")
    bruno.espera("acesso antecipado")
    bruno.toca("Pedir acesso")
    bruno.espera("Não é possível pedir acesso agora")


def test_recupera_pelo_telefone(mundo: Mundo, admin: Pessoa, ana: Pessoa) -> None:
    nova = mundo.pessoa(900_000_102, "Ana Teste", TELEFONE_ANA)  # recriou o Telegram, mesmo número
    nova.diz("/start")
    nova.espera("acesso antecipado")
    nova.toca("Já tenho conta")
    nova.espera("Recuperar minha conta")
    nova.toca("Pelo meu número")
    nova.espera("compartilhar o seu número")
    nova.compartilha_meu_numero()
    nova.espera("Conta recuperada")
    ana.espera("foi transferida para outro Telegram")  # a conta antiga é avisada
    admin.espera("recuperou a conta (telefone)")
    nova.diz("/meus_dados")
    nova.espera("Ana Teste Souza")
    _pessoas["ana"] = nova


def test_recupera_pelo_codigo(mundo: Mundo, ana: Pessoa) -> None:
    nova = mundo.pessoa(900_000_103, "Ana Teste", "5511900001111")  # outro número
    nova.diz("/entrar")
    nova.espera("Digite o seu código de recuperação")
    nova.responde(_estado["codigo_ana"].lower().replace("-", " "))
    nova.espera("Conta recuperada")
    codigo = nova.espera("Seu código de recuperação")
    assert codigo.protegida
    assert _codigo(codigo.texto) != _estado["codigo_ana"]
    _estado["codigo_ana"] = _codigo(codigo.texto)
    nova.espera("compartilhe o seu número atual")
    nova.compartilha_meu_numero()
    nova.espera("Número atualizado")
    ana.espera("foi transferida para outro Telegram")
    _pessoas["ana"] = nova


def test_codigo_errado_trava(mundo: Mundo) -> None:
    intrusa = mundo.pessoa(900_000_999, "Intrusa", "5511900009999")
    for _ in range(5):
        intrusa.diz("/entrar")
        intrusa.espera("Digite o seu código")
        intrusa.responde("ABCD-EFGH-JKMN-PQRS-TVWX")
        intrusa.espera("Código não confere")
    intrusa.diz("/entrar")
    intrusa.espera("Digite o seu código")
    intrusa.responde(_estado["codigo_ana"])  # nem o código certo passa durante a trava
    intrusa.espera("Muitas tentativas")


def test_recuperacao_manual_pelo_admin(mundo: Mundo, admin: Pessoa, ana: Pessoa) -> None:
    nova = mundo.pessoa(900_000_104, "Ana Teste", "5511900002222")  # perdeu código e número
    nova.diz("/start")
    nova.espera("acesso antecipado")
    nova.toca("Já tenho conta")
    nova.espera("Recuperar minha conta")
    nova.toca("Perdi os dois")
    nova.espera("Qual é o seu nome completo")
    nova.responde("Ana Teste Souza")
    nova.espera("Pedido enviado ao administrador")
    admin.espera("perdeu o acesso")
    admin.toca("Ana Teste Souza")
    admin.espera("religada")
    nova.espera("Conta recuperada")
    assert nova.espera("Seu código de recuperação").protegida
    ana.espera("foi transferida para outro Telegram")
    _pessoas["ana"] = nova


def test_bloqueio_pelo_admin(admin: Pessoa, ana: Pessoa) -> None:
    admin.diz("/usuarios")
    admin.espera("Contas")
    admin.toca("Bloquear Ana Teste Souza")
    admin.espera("bloqueada")
    ana.diz("/meus_dados")
    ana.espera("Sua conta está bloqueada")
    admin.diz("/usuarios")
    admin.espera("Contas")
    admin.toca("Desbloquear Ana Teste Souza")
    admin.espera("desbloqueada")
    ana.diz("/meus_dados")
    ana.espera("Seus dados no Telegrana")


def test_apaga_a_conta(admin: Pessoa, ana: Pessoa) -> None:
    ana.diz("/apagar_conta")
    ana.espera("Apagar a conta?")
    ana.toca("Apagar minha conta")
    ana.espera("Última confirmação")
    ana.toca("Sim, apagar tudo")
    ana.espera("Sua conta foi apagada")
    admin.espera("Uma conta foi apagada")
    ana.diz("/start")
    ana.espera("acesso antecipado")

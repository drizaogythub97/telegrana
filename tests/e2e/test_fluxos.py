"""Cenários do critério de pronto da S1 (PLANO 14), num Telegram de verdade (teste).

A ordem importa: os testes contam uma história com as mesmas pessoas.
"""

from __future__ import annotations

import pytest

from tests.e2e.conftest import Mundo, codigo_de, token_do_link

pytestmark = pytest.mark.e2e

_estado: dict[str, str] = {}


def test_desconhecido_ve_bot_privado(mundo: Mundo) -> None:
    mundo.bruno.diz("/start")
    mundo.bruno.espera("O Telegrana é privado")


def test_entra_pelo_link_e_conclui_o_cadastro(mundo: Mundo) -> None:
    admin, ana = mundo.admin, mundo.ana
    admin.diz("/link novo")
    link = admin.espera("Link de convite")
    _estado["token"] = token_do_link(link.raw_text)

    ana.diz(f"/start {_estado['token']}")
    ana.espera("Bem-vindo ao Telegrana")
    termos = ana.espera("Antes de começar")
    # Recusar os termos (não tocar em aceitar): o cadastro não anda.
    ana.diz("Ana Teste")
    termos = ana.espera("Antes de começar")
    ana.toca(termos, "Li e aceito")
    ana.espera("nome completo")
    ana.diz("Ana Teste")
    confirma = ana.espera("É isso mesmo?")
    ana.toca(confirma, "Sim")
    ana.espera("compartilhe o seu número")
    # Contato de outra pessoa é recusado.
    ana.compartilha(mundo.bruno.telefone)
    ana.espera("seu próprio")
    ana.compartilha(ana.telefone)
    maioridade = ana.espera("18 anos ou mais?")
    ana.toca(maioridade, "Tenho 18 anos ou mais")
    codigo = ana.espera("Seu código de recuperação")
    assert codigo.noforwards, "o código precisa vir protegido (sem encaminhar)"
    _estado["codigo_ana"] = codigo_de(codigo.raw_text)
    ana.toca(codigo, "Guardei")
    ana.espera("Conta criada")
    admin.espera("Ana Teste criou a conta (convite)")


def test_comandos_da_conta(mundo: Mundo) -> None:
    ana = mundo.ana
    ana.diz("/meus_dados")
    dados = ana.espera("Seus dados no Telegrana")
    assert "Ana Teste" in dados.raw_text
    assert "vinculado" in dados.raw_text
    ana.diz("/termos")
    ana.espera("Termos e privacidade")


def test_link_revogado_nao_entra(mundo: Mundo) -> None:
    mundo.admin.diz("/link revogar")
    mundo.admin.espera("revogado")
    mundo.bruno.diz(f"/start {_estado['token']}")
    mundo.bruno.espera("O Telegrana é privado")


def test_pede_acesso_admin_aprova_e_menor_tem_dados_apagados(mundo: Mundo) -> None:
    admin, bruno = mundo.admin, mundo.bruno
    bruno.diz("/start")
    privado = bruno.espera("O Telegrana é privado")
    bruno.toca(privado, "Pedir acesso")
    bruno.espera("vão para o administrador")
    pergunta = bruno.espera("Como você conhece o Adriano?")
    bruno.responde(pergunta, "Sou o primo do teste")
    bruno.espera("Pedido enviado")
    pedido = admin.espera("pediu acesso")
    assert "Sou o primo do teste" in pedido.raw_text
    admin.toca(pedido, "Aprovar")
    admin.espera("Acesso liberado")
    liberado = bruno.espera("Seu acesso foi liberado")
    bruno.toca(liberado, "Criar minha conta")
    termos = bruno.espera("Antes de começar")
    bruno.toca(termos, "Li e aceito")
    bruno.espera("nome completo")
    bruno.diz("Bruno Teste")
    bruno.toca(bruno.espera("É isso mesmo?"), "Sim")
    bruno.espera("compartilhe o seu número")
    bruno.compartilha(bruno.telefone)
    bruno.toca(bruno.espera("18 anos ou mais?"), "Não tenho")
    bruno.espera("só para maiores de 18 anos")


def test_pedido_recusado(mundo: Mundo) -> None:
    admin, bruno = mundo.admin, mundo.bruno
    bruno.diz("/start")
    bruno.toca(bruno.espera("O Telegrana é privado"), "Pedir acesso")
    bruno.responde(bruno.espera("Como você conhece o Adriano?"), "De novo")
    bruno.espera("Pedido enviado")
    admin.toca(admin.espera("pediu acesso"), "Recusar")
    admin.espera("Pedido recusado")
    bruno.diz("/start")
    bruno.toca(bruno.espera("O Telegrana é privado"), "Pedir acesso")
    bruno.espera("Não é possível pedir acesso agora")


def test_recupera_pelo_telefone(mundo: Mundo) -> None:
    ana = mundo.ana
    mundo.esquece_identidade(ana)
    ana.diz("/start")
    ana.toca(ana.espera("O Telegrana é privado"), "Já tenho conta")
    ana.toca(ana.espera("Recuperar minha conta"), "Pelo meu número")
    ana.espera("compartilhar o seu número")
    ana.compartilha(ana.telefone)
    ana.espera("Conta recuperada")
    mundo.admin.espera("recuperou a conta (telefone)")


def test_recupera_pelo_codigo(mundo: Mundo) -> None:
    ana = mundo.ana
    mundo.esquece_identidade(ana)
    ana.diz("/entrar")
    pergunta = ana.espera("Digite o seu código de recuperação")
    ana.responde(pergunta, _estado["codigo_ana"].lower())
    ana.espera("Conta recuperada")
    novo = ana.espera("Seu código de recuperação")
    _estado["codigo_ana"] = codigo_de(novo.raw_text)
    ana.diz("/meus_dados")
    ana.espera("Seus dados no Telegrana")


def test_codigo_errado_trava(mundo: Mundo) -> None:
    ana = mundo.ana
    mundo.esquece_identidade(ana)
    for _ in range(5):
        ana.diz("/entrar")
        ana.responde(ana.espera("Digite o seu código"), "ABCD-EFGH-JKMN-PQRS-TVWX")
        ana.espera("Código não confere")
    ana.diz("/entrar")
    ana.responde(ana.espera("Digite o seu código"), _estado["codigo_ana"])
    ana.espera("Muitas tentativas")
    mundo.libera_tentativas(ana)


def test_recuperacao_manual_pelo_admin(mundo: Mundo) -> None:
    admin, ana = mundo.admin, mundo.ana
    ana.diz("/start")
    ana.toca(ana.espera("O Telegrana é privado"), "Já tenho conta")
    ana.toca(ana.espera("Recuperar minha conta"), "Perdi os dois")
    ana.responde(ana.espera("Qual é o seu nome completo"), "Ana Teste")
    ana.espera("Pedido enviado ao administrador")
    pedido = admin.espera("perdeu o acesso")
    admin.toca(pedido, "Ana Teste")
    admin.espera("religada")
    ana.espera("Conta recuperada")
    ana.espera("Seu código de recuperação")


def test_apaga_a_conta(mundo: Mundo) -> None:
    ana = mundo.ana
    ana.diz("/apagar_conta")
    ana.toca(ana.espera("Apagar a conta?"), "Apagar minha conta")
    ana.toca(ana.espera("Última confirmação"), "Sim, apagar tudo")
    ana.espera("Sua conta foi apagada")
    ana.diz("/start")
    ana.espera("O Telegrana é privado")

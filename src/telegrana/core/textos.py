"""Textos do bot (pt-BR). Marcação: **negrito** e `código` (ver core.mensagens)."""

from __future__ import annotations

# Perguntas que pedem resposta direta. O adaptador reconhece a resposta pela
# primeira linha da pergunta: mantenha-as distintas.
PERGUNTAS = {
    "acesso": "🙋 Como você conhece o Adriano?\nResponda em uma mensagem (até 200 caracteres).",
    "codigo": "🔑 Digite o seu código de recuperação.\nEle tem 20 letras e números, como `ABCD-EFGH-JKMN-PQRS-TVWX`.",
    "rec_nome": "🆘 Qual é o seu nome completo, como está no cadastro?\nO administrador vai conferir com você antes de liberar.",
    "nome": "✏️ Qual é o seu nome completo correto?",
    # Categorias (a 2ª linha das perguntas de edição diz qual categoria: é o contexto).
    "cat_nova_gasto": "➕ Nova categoria de gasto: mande o emoji e o nome.\nExemplo: 🏋️ Academia",
    "cat_nova_ganho": "➕ Nova categoria de ganho: mande o emoji e o nome.\nExemplo: 🏠 Aluguel recebido",
    "cat_renomear": "✏️ Qual é o novo nome desta categoria?",
    "cat_emoji": "🎨 Mande o novo emoji desta categoria.",
}


def primeira_linha(texto: str) -> str:
    return texto.replace("**", "").replace("`", "").splitlines()[0].strip()


def pergunta_respondida(texto_da_pergunta: str) -> str | None:
    """Qual pergunta do bot tem esta primeira linha (texto sem marcação)."""
    alvo = texto_da_pergunta.strip().splitlines()[0].strip() if texto_da_pergunta.strip() else ""
    for chave, texto in PERGUNTAS.items():
        if alvo == primeira_linha(texto):
            return chave
    return None


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------
PRIVADO = (
    "🔒 **O Telegrana está em acesso antecipado.**\n"
    "Por enquanto, só entra quem foi convidado. Peça acesso abaixo."
)
AVISO_PEDIDO = (
    "Ao pedir acesso, **seu nome e seu @ do Telegram** e a sua resposta vão para o "
    "administrador decidir. Se o pedido não for aceito, tudo é apagado em até 7 dias."
)
PEDIDO_ENVIADO = (
    "✅ Pedido enviado. Você recebe uma mensagem aqui assim que o administrador decidir."
)
PEDIDO_PENDENTE = "⏳ Seu pedido já está com o administrador. Aguarde a resposta por aqui."
PEDIDO_INDISPONIVEL = "Não é possível pedir acesso agora. Tente de novo mais tarde."
PEDIDO_TAMANHO = "A resposta precisa ter entre 1 e 200 caracteres. Tente de novo."
ACESSO_LIBERADO = "✅ **Seu acesso foi liberado!** Toque abaixo para criar sua conta."

JA_TENHO_CONTA = (
    "🔄 **Recuperar minha conta**\n"
    "Escolha como:\n"
    "• **Pelo meu número**: se o seu número de telefone é o mesmo do cadastro.\n"
    "• **Tenho o código**: o código de recuperação que você guardou no cadastro.\n"
    "• **Perdi os dois**: o administrador confere com você e libera."
)
PEDIR_NUMERO = "📱 Toque no botão abaixo para compartilhar o seu número."
BOTAO_NUMERO = "📱 Compartilhar meu número"
SO_PROPRIO_NUMERO = "⚠️ Só aceito o **seu próprio** número. Use o botão 📱 abaixo."
NUMERO_INVALIDO = "Não consegui ler esse número. Use o botão 📱 abaixo."
NUMERO_SEM_CONTA = (
    "Não encontrei conta com esse número. Se você trocou de número, use **Tenho o código** "
    "ou **Perdi os dois**."
)
CODIGO_INVALIDO = "❌ Código não confere. Confira e tente de novo com /entrar."
CODIGO_FORMATO = "Esse código não parece certo: são 20 letras e números. Tente de novo com /entrar."
TRAVADO = "⏳ Muitas tentativas. Por segurança, tente de novo em {minutos} min."
RECUPERADA = "✅ **Conta recuperada!** Ela agora está ligada a este Telegram."
RECUPERADA_PELO_CADASTRO = (
    "✅ Esse número já tinha uma conta Telegrana: ela foi **religada a este Telegram**."
)
PEDIR_NUMERO_NOVO = "📱 Para a próxima vez, compartilhe o seu número atual: ele passa a valer para recuperar a conta."
RECUPERACAO_EM_USO = (
    "Este Telegram já tem uma conta Telegrana ativa. Para trocar, fale com o administrador."
)
PEDIDO_RECUPERACAO_ENVIADO = (
    "✅ Pedido enviado ao administrador. Ele vai confirmar que é você antes de liberar."
)
AVISO_CONTA_ANTIGA = (
    "⚠️ Sua conta Telegrana foi transferida para outro Telegram. "
    "Não foi você? Fale com o administrador."
)

# ---------------------------------------------------------------------------
# Cadastro
# ---------------------------------------------------------------------------
BOAS_VINDAS = (
    "👋 **Bem-vindo ao Telegrana!**\n"
    "Sou seu assistente financeiro com **inteligência artificial**: você me conta seus "
    "gastos e ganhos por mensagem ou áudio, do seu jeito, e eu entendo, organizo e mostro "
    "para onde o seu dinheiro está indo."
)
RESUMO_TERMOS = (
    "📜 **Antes de começar**\n"
    "🧾 Guardamos seus lançamentos, seu nome e um código do seu telefone (para recuperar a conta).\n"
    "🔐 Cada conta é isolada: ninguém vê seus dados, nem outros usuários.\n"
    "🤖 Suas mensagens passam por uma IA só para entender o que você disse; ela não guarda nem aprende com elas.\n"
    "🌎 **Os dados ficam em servidores nos EUA** (AWS, Neon, Groq).\n"
    "⚠️ **Se você descrever algo sensível** (ex.: saúde, religião), isso só serve para organizar suas finanças.\n"
    "💬 A conversa com bots do Telegram não tem criptografia de ponta a ponta.\n"
    "📊 O Telegrana organiza, não é consultoria financeira.\n"
    "🗑️ Você pode exportar ou apagar tudo quando quiser.\n\n"
    "Ao tocar em **Li e aceito**, você concorda com os Termos de Uso e com a Política de "
    "Privacidade, inclusive com os dois pontos em negrito acima."
)
TERMOS_MUDARAM = (
    "📜 **Os Termos de Uso ou a Política de Privacidade mudaram.**\n"
    "Leia as versões novas e aceite para continuar. Até lá, só /apagar_conta funciona."
)
BOTAO_TERMOS = "📄 Termos de Uso"
BOTAO_PRIVACIDADE = "🔒 Privacidade"
BOTAO_ACEITO = "✅ Li e aceito"
PEDIR_NOME = "📝 Qual é o seu **nome completo**?"
NOME_INVALIDO = (
    "Use só letras, espaços, hífen e apóstrofo, com 2 a 120 caracteres, e pelo menos "
    "nome e sobrenome. Tente de novo."
)
CONFIRMAR_NOME = "Seu nome é **{nome}**. É isso mesmo?"
PEDIR_TELEFONE = (
    "📱 Agora, compartilhe o seu número pelo botão abaixo.\n"
    "Guardamos **só um código** dele, que serve para recuperar a sua conta se você "
    "recriar o Telegram com o mesmo número."
)
PEDIR_MAIORIDADE = "🔞 O Telegrana é só para maiores de 18 anos. Você tem 18 anos ou mais?"
MENOR = (
    "O Telegrana é só para maiores de 18 anos, então não posso continuar. "
    "**Os dados do seu cadastro foram apagados.**"
)
CODIGO_RECUPERACAO = (
    "🔑 **Seu código de recuperação**\n\n`{codigo}`\n\n"
    "Guarde em lugar seguro (por exemplo, nas suas Mensagens Salvas, fora desta conversa). "
    "Ele serve para recuperar a conta se você trocar de Telegram **e** de número.\n"
    "⚠️ Quem tiver esse código pode pedir a sua conta. **Ele não será mostrado de novo.**"
)
BOTAO_GUARDEI = "✅ Guardei"
PRONTO = (
    "🎉 **Conta criada!**\n"
    "Os lançamentos por texto e áudio chegam na próxima etapa do Telegrana. "
    "Enquanto isso, veja /ajuda.\n\n"
    "💡 Dica: o Telegram apaga contas que ficam muito tempo sem uso. Se você usa o "
    "Telegram só para o Telegrana, aumente esse prazo em Configurações > Privacidade e Segurança."
)
EM_BREVE = "🛠️ Os lançamentos chegam na próxima etapa. Por enquanto, veja /ajuda."
USE_OS_BOTOES = "Use os botões da mensagem acima para continuar."

# ---------------------------------------------------------------------------
# Conta
# ---------------------------------------------------------------------------
AJUDA = (
    "📋 **Comandos**\n"
    "/meus_dados — o que está guardado sobre você\n"
    "/corrigir_nome — corrigir o seu nome\n"
    "/categorias — ver, criar e editar suas categorias\n"
    "/termos — termos de uso, privacidade e versão aceita\n"
    "/codigo_novo — gerar um novo código de recuperação\n"
    "/apagar_conta — apagar tudo, definitivamente"
)
JA_TEM_CONTA = "Você já tem conta. 🙂 Veja /ajuda."
MEUS_DADOS = (
    "🗂️ **Seus dados no Telegrana**\n"
    "• Nome: **{nome}**\n"
    "• Telefone: {telefone}\n"
    "• Maioridade declarada em {maioridade}\n"
    "• Termos de Uso v{termos} e Política de Privacidade v{privacidade}, aceitos em {aceite}\n"
    "• Código de recuperação: {codigo}\n"
    "• Conta criada em {criada}\n\n"
    "Seus lançamentos aparecem aqui quando chegarem. Para uma cópia completa ou qualquer "
    "outro pedido sobre seus dados, fale com o administrador ({contato})."
)
NOME_CORRIGIDO = "✅ Nome atualizado para **{nome}**."
TERMOS_INFO = (
    "📜 **Termos e privacidade**\n"
    "Você aceitou os Termos de Uso v{termos} e a Política de Privacidade v{privacidade} em {aceite}."
)
CODIGO_NOVO_CONFIRMA = (
    "🔑 Gerar um **novo código de recuperação**? O código atual deixa de valer na hora."
)
BOTAO_GERAR = "🔑 Gerar novo código"
TELEFONE_ATUALIZADO = "✅ Número atualizado. Ele passa a valer para recuperar a conta."
TELEFONE_DE_OUTRA_CONTA = "Esse número já está ligado a outra conta Telegrana."
APAGAR_1 = (
    "🗑️ **Apagar a conta?**\n"
    "Isso apaga **tudo**, de forma definitiva: nome, código do telefone, código de "
    "recuperação, aceites e lançamentos.\n"
    "Quer uma cópia antes? Peça ao administrador ({contato}).\n"
    "As mensagens desta conversa continuam no seu Telegram até você apagar o chat."
)
APAGAR_2 = "⚠️ **Última confirmação.** Não dá para desfazer. Apagar tudo agora?"
APAGADA = "✅ Sua conta foi apagada. Obrigado por ter usado o Telegrana."
CANCELADO = "Tudo certo, nada foi alterado."
BLOQUEADA = "🚫 Sua conta está bloqueada. Fale com o administrador ({contato})."

# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
ADM_PEDIDO = "🙋 **{nome}** ({username}) pediu acesso:\n“{mensagem}”"
ADM_PEDIDO_RECUPERACAO = (
    "🆘 **{nome}** ({username}) perdeu o acesso e diz se chamar “{mensagem}”.\n"
    "Confira com a pessoa **fora do bot** antes de religar. Qual conta é dela?"
)
ADM_APROVADO = "✅ Acesso liberado para {nome}."
ADM_RECUSADO = "❌ Pedido recusado. A pessoa não recebe aviso."
ADM_PEDIDO_RESOLVIDO = "Esse pedido já foi resolvido ou expirou."
ADM_ENTROU = "👤 **{nome}** criou a conta ({via})."
ADM_RECUPEROU = "🔄 **{nome}** recuperou a conta ({via})."
ADM_RELIGADO = "✅ Conta de {nome} religada. A pessoa recebeu um código novo."
ADM_APAGOU = "🗑️ Uma conta foi apagada pelo próprio usuário."
ADM_BLOQUEADO = "🚫 Conta de {nome} bloqueada."
ADM_DESBLOQUEADO = "✅ Conta de {nome} desbloqueada."
ADM_LINK_NOVO = (
    "🔗 **Link de convite** (vale para {usos} contas; o anterior foi revogado):\n{link}\n\n"
    "Guarde esta mensagem: o link não pode ser mostrado de novo, só trocado (/link novo)."
)
ADM_LINK_STATUS = "🔗 Link ativo desde {criado}: **{usados}/{maximo}** contas criadas."
ADM_SEM_LINK = "Nenhum link de convite ativo. Gere um com /link novo."
ADM_LINK_REVOGADO = "🚫 Link de convite revogado. Ninguém mais entra por ele."
ADM_USUARIOS_VAZIO = "Nenhuma conta criada ainda."
ADM_AJUDA = (
    "🛠️ **Admin**\n"
    "/link — situação do link de convite\n"
    "/link novo — gerar link novo (revoga o atual)\n"
    "/link revogar — revogar sem gerar outro\n"
    "/usuarios — contas, com bloqueio e desbloqueio"
)

# ---------------------------------------------------------------------------
# Categorias
# ---------------------------------------------------------------------------
CATEGORIA_CRIADA = "✅ Categoria criada: {rotulo}"
CATEGORIA_RENOMEADA = "✅ Pronto: {rotulo}"
CATEGORIA_DESATIVADA = (
    "🚫 {rotulo} desativada. Ela sai das opções, mas os lançamentos antigos continuam com ela."
)
CATEGORIA_REATIVADA = "✅ {rotulo} reativada."
CATEGORIA_FIXA = "{rotulo} não pode ser desativada: é para onde vai o que não se encaixa em outra."
CATEGORIA_JA_EXISTE = "Você já tem uma categoria chamada {nome}."
CATEGORIA_NOME_INVALIDO = (
    "Esse nome não serve: use até 40 letras, números e espaços, com um emoji antes se quiser."
)
CATEGORIA_EMOJI_INVALIDO = "Mande só um emoji (por exemplo 🏋️). Tente de novo em /categorias."
CATEGORIA_SUMIU = "Não encontrei essa categoria. Veja a lista atual em /categorias."

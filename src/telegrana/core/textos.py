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
    # Lançamentos (a 2ª linha diz de qual lançamento se trata)
    "lc_valor": "💬 Quanto foi?",
    "lc_data": "📅 Quando foi? (ex.: hoje, ontem, sexta, 05/09)",
    # Fixos (a 2ª linha diz qual fixo: "🔁 <nome>")
    "fi_valor": "💰 Qual é o novo valor deste fixo?",
    "fi_dia": "📅 Em que dia do mês ele vence? (de 1 a 31)",
    # Lembretes (a 2ª linha diz qual fixo e qual vencimento: "🔔 <nome> · dd/mm/aaaa")
    "lm_valor": "💬 Qual foi o valor desta vez?",
    # Cartões (a 2ª linha diz qual cartão: "💳 <nome>")
    "lc_cartao": "💳 Em qual cartão foi? Me diga o nome (ex.: Nubank).",
    "lc_cartao_dias": "📅 Cartão novo! Em que dia a fatura fecha e em que dia vence? (ex.: fecha 3, vence 10)",
    "ct_nome": "💳 Qual é o nome do cartão? (ex.: Nubank, Inter)",
    "ct_dias": "📅 Em que dia a fatura fecha e em que dia vence? (ex.: fecha 3, vence 10)",
    "ct_renomear": "✏️ Qual é o novo nome deste cartão?",
    # Faturas (a 2ª linha diz qual: "🧾 <cartão> · dd/mm/aaaa")
    "fa_valor": "💬 Quanto você pagou desta fatura?",
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
    "Já pode me contar seus gastos e ganhos, por texto ou áudio. Experimente: "
    "«mercado 45,90 no pix» ou um áudio dizendo «gastei 30 reais de pão hoje». "
    "Mais em /ajuda.\n\n"
    "💡 Dica: o Telegram apaga contas que ficam muito tempo sem uso. Se você usa o "
    "Telegram só para o Telegrana, aumente esse prazo em Configurações > Privacidade e Segurança."
)
USE_OS_BOTOES = "Use os botões da mensagem acima para continuar."

# ---------------------------------------------------------------------------
# Conta
# ---------------------------------------------------------------------------
AJUDA = (
    "💬 **Para registrar**, é só escrever ou mandar um áudio: «mercado 45,90 no pix», "
    "«uber 18 ontem», «recebi 3.500 de salário». Para corrigir, responda ao recibo.\n\n"
    "📋 **Comandos**\n"
    "/meus_dados — o que está guardado sobre você\n"
    "/corrigir_nome — corrigir o seu nome\n"
    "/categorias — ver, criar e editar suas categorias\n"
    "/fixos — contas e ganhos que se repetem todo mês, com lembretes\n"
    "/cartoes — seus cartões de crédito (fechamento e vencimento da fatura)\n"
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

# ---------------------------------------------------------------------------
# Lançamentos (S2.3)
# ---------------------------------------------------------------------------
REGISTRADO = {
    "expense": "✅ **Gasto registrado**",
    "income": "🟢 **Ganho registrado**",
    "transfer": "🔁 **Transferência registrada**",
}
PREVISTO = "🗓️ **Gasto previsto**"
CORRIGIDO = "✏️ **Corrigido**"
PERGUNTA_FIXO = "🔁 Isso se repete todo mês?"
PERGUNTA_CATEGORIA = "🤔 Em qual categoria fica **{resumo}**?"
PERGUNTA_CONFIRMAR = "⚠️ Valor alto: confirma **{resumo}**?"
PERGUNTA_DUVIDA = "🤔 Registro **{resumo}** como um lançamento novo?"
CORRIGIR_COMO = (
    "✏️ Responda a **esta mensagem** (ou ao recibo) com a correção, por texto ou áudio. "
    "Por exemplo: «foi 54,90», «foi no débito», «foi ontem» ou «foi na padaria»."
)
ESCOLHA_CATEGORIA = "🏷️ Qual a categoria certa para **{resumo}**?"
APAGADO = "🗑️ Apagado: {resumo}"
DESFEITO = "↩️ Lançamento de volta."
RASCUNHO_CANCELADO = "👍 Tudo bem, não registrei."
RASCUNHO_SUMIU = "Esse lançamento já foi resolvido ou expirou. Pode mandar de novo."
LEMBRAR_REGRA = "🧠 Quer que eu lembre: «{termo}» é sempre {rotulo}?"
REGRA_APRENDIDA = "🧠 Pronto: «{termo}» vai sempre para {rotulo}."
FIXO_TITULO = "🔁 **Fixo**"
FIXO_CRIADO = "🔁 **Fixo cadastrado**"
FIXO_JA_EXISTE = "🔁 **Esse fixo já existe**"
FIXO_ATUALIZADO = "✅ **Fixo atualizado**"
FIXOS_TITULO = "🔁 **Seus fixos**"
FIXOS_VAZIO = (
    "🔁 Você ainda não tem fixos. Mande, por exemplo: «aluguel 1500 todo dia 10», "
    "«salário 3.500 todo dia 5» ou «internet 120 todo mês dia 15». "
    "Ou toque em «Sim, todo mês» num recibo."
)
FIXO_SUMIU = "Esse fixo não existe mais. Veja seus fixos em /fixos."
FIXO_APAGAR_CONFIRMA = (
    "🗑️ Apagar o fixo **{nome}**? Os lembretes param; os lançamentos já feitos continuam."
)
FIXO_APAGADO = "🗑️ Fixo apagado."
FIXO_DESFEITO = "↩️ Pronto, não é mais um fixo."
FIXO_NAO = "👍 Anotado."
# Lembretes (S4.2): {emoji} {nome} {quando}; a 2ª linha é o valor.
LEMBRETE = {
    ("expense", "before"): "{emoji} **{nome}** vence amanhã ({data})",
    ("expense", "on_day"): "{emoji} **{nome}** vence hoje",
    ("expense", "after"): "⏰ **{nome}** venceu em {data} e ainda não está marcado como pago",
    ("income", "before"): "{emoji} **{nome}** cai amanhã ({data})",
    ("income", "on_day"): "{emoji} **{nome}** cai hoje",
    ("income", "after"): "⏰ **{nome}** era para ter caído em {data} e ainda não está marcado",
}
LEMBRETE_VALOR = {"fixed": "Valor: {valor}", "estimated": "Valor estimado: {valor}"}
LEMBRETE_PULADO = "⏭️ Pronto, {nome} de {mes} ficou de fora. No próximo mês eu lembro de novo."
LEMBRETE_JA_RESOLVIDO = "👍 {nome} de {mes} já está resolvido."
LEMBRETE_INVALIDO = "Esse lembrete é antigo. Veja seus fixos em /fixos."
# Cartões (S5.1, D045)
COMPRA_CREDITO = "💳 **Compra no crédito registrada**"
PERGUNTA_CARTAO = "💳 Em qual cartão foi **{resumo}**?"
CARTOES_TITULO = "💳 **Seus cartões**"
CARTOES_VAZIO = (
    "💳 Você ainda não tem cartões. Toque em ➕ Novo cartão, ou registre uma compra no "
    "crédito (ex.: «tênis 600 em 3x no Nubank») que eu cadastro o cartão na hora."
)
CARTAO_TITULO = "💳 **Cartão**"
CARTAO_CRIADO = "💳 **Cartão cadastrado**"
CARTAO_JA_EXISTE = "💳 **Esse cartão já existe**"
CARTAO_ATUALIZADO = "✅ **Cartão atualizado**"
CARTAO_SUMIU = "Esse cartão não existe mais. Veja seus cartões em /cartoes."
CARTAO_APAGAR_CONFIRMA = "🗑️ Apagar o cartão **{nome}**?"
CARTAO_APAGADO = "🗑️ Cartão apagado."
CARTAO_DESATIVADO = (
    "⏸️ O {nome} tem lançamentos, então ficou só desativado (as compras e parcelas continuam)."
)
CARTAO_NOME_RUIM = "Mande só o nome do cartão, com até 30 letras (ex.: Nubank)."
CARTAO_NOME_EXISTE = "Já existe uma forma de pagamento chamada «{nome}». Escolha outro nome."
DIAS_NAO_ENTENDI = "Não entendi os dias. Mande assim: «fecha 3, vence 10»."
MOVER_ANTIGAS = (
    "💳 Você tem {n} compra(s) no crédito registradas antes dos cartões. Coloco no {nome}? "
    "Elas viram parcelas nas faturas certas e só contam como gasto quando a fatura for paga."
)
ANTIGAS_MOVIDAS = "✅ Pronto: {n} compra(s) foram para as faturas do {nome}."
ANTIGAS_FICAM = "👍 Ficam como estão."
# Faturas (S5.2, D046)
FATURA_TITULO = "🧾 **Fatura do {nome}** · vence {data}"
FATURA_FECHOU = "🧾 **Fatura do {nome} fechou** · vence {data}"
FATURA_VENCE_AMANHA = "🧾 **Fatura do {nome}** vence amanhã ({data})"
FATURA_VENCE_HOJE = "🧾 **Fatura do {nome}** vence hoje"
FATURA_ATRASADA = "⏰ **Fatura do {nome}** venceu em {data} e ainda não está marcada como paga"
FATURA_MAIS = "…e mais {n} item(ns)"
FATURA_VAZIA = "🧾 Não há fatura em aberto no {nome}."
FATURA_JA_PAGA = "👍 A fatura do {nome} que vence {data} já está paga."
FATURA_PAGA = (
    "✅ **Fatura do {nome} paga**: {pago}. {n} item(ns) viraram gasto hoje, cada um na sua "
    "categoria."
)
FATURA_PAGA_PARCIAL = (
    "✅ **Pagamento parcial da fatura do {nome}**: {pago}. Cada compra virou gasto na mesma "
    "proporção; os {resto} restantes foram para a fatura de {data} como «Saldo anterior»."
)
FATURA_ENCARGOS = " Os {valor} a mais entraram como 💸 Encargos e juros."
DESCRICAO_ENCARGOS = "Juros e encargos da fatura"
FATURAS_DO_CARTAO = "🧾 **Faturas do {nome}** (toque para ver)"
SEM_CARTOES = "💳 Você ainda não tem cartões. Veja /cartoes."
QUAL_FATURA = "🧾 Fatura de qual cartão?"
ESTORNO_SEM_VALOR = "Quanto foi o estorno? Ex.: «estorno de 80 no Inter»."
ESTORNO_SEM_COMPRA = (
    "Não achei uma compra no cartão com parcelas em aberto para abater {valor}. Se for o "
    "caso, apague ou corrija a compra pelo recibo."
)
ESTORNO_QUAL = "↩️ Estorno de {valor}: de qual compra?"
ESTORNO_FEITO = "↩️ Estorno de {valor} abatido de «{descricao}»."
ESTORNO_NENHUMA = "👍 Nada mudou."
PERGUNTA_CATEGORIA_CORRECAO = "🤔 Para qual categoria vai **{resumo}**?"
CORRECAO_IGUAL = "👍 O lançamento já está assim."
CORRECAO_NAO_ENTENDI = (
    "Não entendi a correção. Use os botões do recibo ou responda, por exemplo, «foi 54,90»."
)
NADA_PARA_CORRIGIR = (
    "Não achei um lançamento recente para corrigir. Responda direto ao recibo que quer mudar."
)
NADA_PARA_APAGAR = "Não achei um lançamento recente para apagar. Use o botão 🗑️ do recibo."
NAO_ENTENDI = (
    "🤔 Não entendi bem. Me conta assim, por exemplo: «mercado 45,90 no pix» ou "
    "«recebi 1.500 de salário»."
)
CONSULTA_EM_BREVE = (
    "📊 Consultas e relatórios chegam numa próxima etapa. Por enquanto, eu registro."
)
FATURA_EM_BREVE = "💳 Faturas de cartão chegam numa próxima etapa."
OI = "👋 Oi! Me conta um gasto ou um ganho, por texto ou áudio, que eu registro."
SOBRECARREGADO = (
    "⏳ Estou com muita demanda agora. Manda de novo daqui a alguns minutos, por favor."
)
IA_FALHOU = "😕 Não consegui entender agora. Pode tentar de novo?"
ADM_COTA_IA = (
    "⚠️ IA: o modelo {modelo} já usou {pct}% da cota de hoje no Groq. "
    "Quando acabar, sigo nos modelos de reserva."
)
SO_TEXTO_OU_AUDIO = "Me conta um gasto ou um ganho, por texto ou áudio, que eu registro. 🙂"
AUDIO_LONGO = "🎙️ Esse áudio passa de 2 minutos. Manda um mais curto (ou por texto), por favor."
AUDIO_GRANDE = "🎙️ Esse arquivo de áudio é grande demais. Manda um mais curto, por favor."
AUDIO_INDISPONIVEL = "🎙️ Não consigo ouvir áudios agora. Me manda por texto, por favor."
AUDIO_FALHOU = "😕 Não consegui ouvir esse áudio. Pode mandar de novo ou escrever?"
AUDIO_VAZIO = "🎙️ Não ouvi nada nesse áudio. Pode mandar de novo?"
OUVI = "🎙️ Ouvi: «{trecho}»"

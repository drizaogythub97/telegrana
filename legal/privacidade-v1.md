# Política de Privacidade do Telegrana — versão 1

*Vigente desde {{data_vigencia}}.*

## 1. Quem cuida dos seus dados

O responsável (controlador) pelos seus dados é **Adriano Cardoso**, pessoa física, que mantém o Telegrana para uso familiar, **de graça e sem fins comerciais**. Ele também é o **encarregado** pelo atendimento sobre seus dados.

*Contato:* {{contato_admin}} no Telegram. É por esse canal que você tira dúvidas, exerce seus direitos e faz reclamações.

O Telegrana cumpre a **Lei Geral de Proteção de Dados (LGPD, Lei 13.709/2018)**. Mesmo sendo um projeto familiar, aplicamos a lei por inteiro: coletar só o necessário, usar só para o que está escrito aqui e deixar você no controle.

## 2. Quais dados tratamos e por quê

**Antes do aceite destes termos**, só tratamos o mínimo para você entrar:

- se você **pedir acesso**: seu identificador do Telegram (um número), seu nome e @ do Telegram e a mensagem do pedido, para o administrador decidir. São **apagados em até 7 dias** ou quando a sua conta é criada;
- se você **chegar por convite**: o identificador do Telegram, para lembrar em que etapa do cadastro você está. Cadastros não concluídos são **apagados em 7 dias**.

**Depois do aceite:**

| Dado | Para que serve | Como é guardado |
|---|---|---|
| Identificador do Telegram (um número) | Saber que é você e separar sua conta das outras | Número |
| Nome completo | Para o administrador saber quem é você (avisos e recuperação de conta) e para o cabeçalho dos relatórios | Texto |
| Telefone | Recuperar sua conta se você recriar o Telegram com o mesmo número | **Não guardamos o número.** Guardamos só um código (HMAC-SHA256) gerado com uma chave secreta guardada em cofre separado. Sem essa chave, o código não serve para descobrir o número. Mesmo assim, ele continua sendo dado pessoal e é protegido como tal |
| Código de recuperação | Recuperar sua conta se você trocar de Telegram **e** de número | Só um resumo protegido (Argon2). Ninguém, nem o administrador, consegue ver o código |
| Declaração de maioridade | O Telegrana é só para maiores de 18 anos | A data em que você declarou |
| Aceite dos termos | Comprovar que você aceitou, e qual versão | Versão aceita e data |
| Seus lançamentos: valores, datas, categorias, descrições, formas de pagamento, cartões, contas fixas e a transcrição dos áudios | Prestar o serviço: registrar, lembrar e gerar relatórios | Na sua conta, isolada das demais |
| Registros de segurança: entrada, aprovação de acesso, recuperação, troca de Telegram e exclusão de conta | Proteger sua conta e investigar abusos | Data e tipo do evento, **sem** valores, descrições nem mensagens |

**Não coletamos** e-mail, data de nascimento, documentos (CPF, RG), dados bancários, senhas, números de cartão nem localização.

O telefone só é recebido pelo botão oficial do Telegram "Compartilhar meu número", e só é aceito se for o **seu próprio** número.

Os **áudios** são transcritos e descartados na hora. Só o texto da transcrição fica guardado, junto do lançamento, para você conferir.

> **⚠️ Em destaque: informações sensíveis.** O Telegrana **não pede** dados sensíveis (saúde, religião, opinião política, vida sexual, origem racial e outros). Mas a descrição de um gasto pode revelar algo assim, como "consulta no psiquiatra" ou "dízimo". **Ao aceitar, você consente, de forma específica, que essas informações, se você mesmo as enviar, sejam usadas só para registrar e organizar as suas finanças**, com a mesma proteção de todo o resto. Se preferir, use descrições genéricas ("saúde", "doação"). Você pode retirar esse consentimento quando quiser, apagando o lançamento ou a conta.

**Dados de outras pessoas:** se você registrar o nome de alguém (por exemplo, "paguei 50 ao João"), use só o necessário. Esse registro fica apenas na sua conta.

## 3. Base legal

| Tratamento | Base na LGPD |
|---|---|
| Pedido de acesso e cadastro | Procedimentos preliminares a um serviço pedido por você (art. 7º, V) |
| Cadastro, lançamentos, lembretes e relatórios | Execução do serviço que você pediu ao aceitar os termos (art. 7º, V) |
| Registros de segurança | Legítimo interesse em proteger as contas (art. 7º, IX), limitado ao mínimo e sem conteúdo financeiro |
| Informações sensíveis que você mesmo enviar | Seu consentimento específico e destacado (art. 11, I), dado no aceite |

**Se você não fornecer** nome, telefone e a declaração de maioridade, não é possível criar a conta. Os demais dados vêm do seu uso: você decide o que registra.

## 4. Com quem os dados são compartilhados

Para funcionar, o Telegrana usa estes **operadores**, que tratam os dados em nome do Telegrana, seguindo os termos de proteção de dados de cada um:

| Serviço | Para quê | Onde |
|---|---|---|
| **Amazon Web Services (AWS)** | Onde o bot roda | EUA |
| **Neon** | Banco de dados onde ficam seus dados | EUA, na infraestrutura da AWS |
| **Groq** | Inteligência artificial que entende suas mensagens e transcreve os áudios | EUA |

O **Telegram** é o aplicativo pelo qual você conversa com o bot. Ele é um serviço independente: trata os seus dados segundo a política dele, que você aceitou ao usar o Telegram.

> **🌎 Em destaque: transferência internacional.** Seus dados são **guardados e processados fora do Brasil, nos EUA**. Essa transferência é necessária para prestar o serviço que você pediu (LGPD, art. 33, IX).

**Ninguém recebe seus dados para publicidade**, e nada é vendido. Dados só são entregues a autoridades quando houver obrigação legal ou ordem judicial.

## 5. Inteligência artificial

- A IA recebe só o necessário para entender cada mensagem: o texto (ou o áudio), a lista das suas categorias e formas de pagamento e a data de hoje. **Ela não recebe o seu histórico.**
- O provedor de IA (Groq) está configurado para **não guardar** suas mensagens (retenção zero) e **não usá-las para treinar** modelos.
- A IA só sugere como interpretar a mensagem. O bot mostra um recibo de cada lançamento para você conferir e pergunta quando tem dúvida. **Nenhuma decisão sobre você é tomada só por máquina.**
- A IA não decide nada sobre acesso, não faz contas e não vê dados de outras pessoas.

## 6. Como protegemos seus dados

- Cada conta é **isolada** no banco de dados: uma pessoa não consegue ver os dados de outra, nem por erro do sistema (há testes automáticos que tentam e precisam falhar).
- Conexões **criptografadas** e dados guardados criptografados pelos provedores.
- Senhas, chaves e segredos ficam em cofre, nunca no código.
- Os registros técnicos (logs) **não contêm** seus valores, descrições, nomes nem mensagens, e são apagados em 7 dias.

**Limite importante:** conversas com bots do Telegram **não têm criptografia de ponta a ponta**. O Telegram consegue, tecnicamente, ter acesso às mensagens trocadas com o bot. Não envie ao Telegrana senhas, números de cartão ou documentos.

## 7. Incidentes de segurança

Se acontecer um incidente que possa trazer risco ou dano relevante a você, **avisamos você pelo próprio bot** e comunicamos a Autoridade Nacional de Proteção de Dados (ANPD), nos prazos da regulamentação. O aviso diz o que aconteceu, quais dados foram afetados, o que já foi feito e o que você pode fazer.

## 8. Por quanto tempo guardamos

| O quê | Por quanto tempo |
|---|---|
| Seus dados e lançamentos | Enquanto sua conta existir |
| Registros de segurança da sua conta | Enquanto sua conta existir |
| Pedidos de acesso e cadastros não concluídos | Até 7 dias |
| Contagem de tentativas erradas de recuperação de conta (para barrar abusos) | 1 dia |
| Logs técnicos (sem dados pessoais) | 7 dias |

Quando você apaga a conta, **tudo é apagado**: nome, código do telefone, código de recuperação, aceites, lançamentos e registros de segurança. Fica só um registro **anônimo** de que uma conta foi excluída naquela data. O provedor do banco mantém cópias técnicas de recuperação por até **6 horas**; depois disso, não há mais cópia.

As **mensagens que você trocou com o bot continuam no seu Telegram** até você apagar a conversa. Apagar a conta no Telegrana não apaga esse histórico: para isso, apague também a conversa no Telegram.

## 9. Seus direitos e como exercê-los

| Seu direito | Como |
|---|---|
| Saber se tratamos seus dados e ver o que está guardado | `/meus_dados`, na hora. Uma declaração completa pode ser pedida pelo contato |
| Corrigir seus dados | `/corrigir_nome`; lançamentos você corrige ou apaga pelo próprio bot |
| Receber uma cópia dos seus dados (portabilidade) | `/exportar` (planilha completa). Enquanto o comando não estiver disponível, peça pelo contato |
| Apagar seus dados e retirar o consentimento | `/apagar_conta` (tudo) ou apagando lançamentos |
| Pedir anonimização, bloqueio ou exclusão de dado desnecessário | Pelo contato |
| Saber com quem compartilhamos | Seção 4 desta política |
| Opor-se aos registros de segurança | Pelo contato |
| Ver os termos e a versão aceita | `/termos` |

Pedidos feitos pelo contato são respondidos em **até 15 dias**. Se você não ficar satisfeito, pode reclamar à **ANPD** (gov.br/anpd).

## 10. Menores de idade

O Telegrana é **só para maiores de 18 anos**. Se soubermos que uma conta pertence a um menor, ela será apagada.

## 11. Mudanças nesta política

Se esta política mudar, o bot mostra um resumo das mudanças e pede um novo aceite. Qualquer dado novo só passa a ser coletado depois de estar descrito aqui e aceito por você. Cada versão fica registrada com número e data.

# Telegrana — Plano do projeto

> Alinhamento fechado com o Adriano em 29/09/2026, na fase de planejamento (revisado no mesmo dia com cadastro, recuperação e termos). Fonte da verdade do projeto.
> Mudanças posteriores: registrar em `docs/DECISOES.md` e marcar aqui com a data.
> **Revisão 29/09/2026 (S0):** repositório público (D015), dados de avaliação fora do Git (D016), acesso AWS por `aws login` (D017), sem Docker local (D018), limites do Groq (D019), iPhone na família (D020).

---

## 0. Visão

Um assistente financeiro no Telegram para o Adriano e a família. A pessoa fala ou escreve do jeito dela ("uns 50 conto no posto", "caiu o salário, 3200", "tênis 600 em 3x no Nubank") e o Telegrana registra, organiza, lembra dos vencimentos e responde qualquer pergunta sobre o dinheiro, em mensagem clara com emojis, ou em planilha e PDF quando pedido.

- Usuários: 5 a 10 pessoas, uso familiar, sem fins comerciais.
- Cada pessoa tem sua conta, totalmente isolada das outras.
- Roda 100% online, sem depender do PC do Adriano.

---

## 1. Decisões fechadas

| # | Tema | Decisão |
|---|---|---|
| 1 | Canal | Telegram (bot único `@TelegranaBot` ou variação disponível) |
| 2 | Nome | **Telegrana** (só o T maiúsculo) |
| 3 | IA | **Groq**: Whisper large-v3 para áudio; `gpt-oss-20b` para extração de lançamentos, `gpt-oss-120b` para relatórios/consultas. Comparado com Grok (xAI) e API do Claude: descartados por custo, cartão e, no caso do Grok, uso de dados para treino |
| 4 | Computação | AWS Lambda com Function URL, na conta AWS antiga do Adriano (Always Free) |
| 5 | Agendamento | EventBridge Scheduler (14 milhões de invocações/mês grátis, permanente; suporta fuso e horário de verão) |
| 6 | Banco | Um único Neon Postgres (Free, sem cartão), com contas isoladas por RLS |
| 7 | Cartão de crédito | Só a AWS tem cartão; todo o resto é gratuito e sem cartão |
| 8 | Autenticação | O `from.id` do Telegram é a identidade. Sem usuário/senha. Código de recuperação para migrar a conta para outro Telegram |
| 9 | Entrada no bot | Link de convite reutilizável dá acesso livre; quem achar o bot sozinho gera pedido de acesso aprovado pelo admin |
| 10 | Contas | Individuais na V1; modelo de dados já preparado para contas compartilhadas (membros) no futuro |
| 11 | Cartão de crédito (lógica) | Regime de caixa: compra no crédito só vira gasto realizado quando a fatura é paga; parcelamento distribuído pelas faturas |
| 12 | Lembretes | Configuráveis por item: 1 dia antes, no dia, diário após vencimento; às 9h, 20h ou ambos |
| 13 | Linguagem | Python |
| 14 | Desenvolvimento | 100% pelo Claude Code, automação máxima, testes automatizados incluindo o celular do Adriano via adb Wi-Fi |
| 15 | Cadastro | Nome completo, telefone verificado pelo botão do Telegram (guardado só como HMAC) e declaração de maioridade. Sem e-mail e sem data de nascimento na V1 |
| 16 | Recuperação | Automática pelo mesmo telefone; código de recuperação para número novo; aprovação manual do admin como último recurso |
| 17 | Termos | Termos de Uso e Política de Privacidade versionados, publicados no Telegraph, aceite obrigatório antes de qualquer coleta |
| 18 | WhatsApp | Depois da V1 no Telegram: estudo de viabilidade e investimento na AWS |

---

## 2. Arquitetura

```
Usuário (Telegram)
   │  texto / áudio / botões
   ▼
Telegram Bot API ── webhook (HTTPS + secret token) ──▶ Lambda "bot" (Function URL)
                                                         │
                          ┌──────────────────────────────┼─────────────────────┐
                          ▼                              ▼                     ▼
                  Groq (Whisper, gpt-oss)      Neon Postgres (RLS)     Geração XLSX/PDF (/tmp)
                                                         ▲
EventBridge Scheduler ── 09:00 e 20:00 BRT ──▶ Lambda "rotinas" (lembretes, resumos, fechamento de mês)

AWS Budgets ── estouro ──▶ SNS ──▶ Lambda "kill-switch" ──▶ concorrência reservada = 0 nas Lambdas
```

### Componentes

- **Lambda `bot`**: recebe o webhook, valida, deduplica, identifica a conta, processa e responde. Processamento síncrono (transcrição + LLM cabem em poucos segundos); timeout curto (ex.: 30 s). Idempotência pelo `update_id` garante que reenvios do Telegram não dupliquem nada.
- **Lambda `rotinas`**: disparada pelo Scheduler às 09:00 e 20:00 (`America/Sao_Paulo`). Varre vencimentos e resumos pendentes de todas as contas e envia. Registra cada envio para nunca repetir.
- **Lambda `kill-switch`**: acionada pelo orçamento estourado; zera a concorrência reservada das outras Lambdas e avisa o admin.
- **Camadas do código** (núcleo agnóstico de canal):
  - `core/` — domínio: contas, lançamentos, categorias, fixos, cartões, faturas, relatórios. Não conhece Telegram.
  - `ai/` — cliente de IA com provedor trocável por configuração, prompts, esquemas Pydantic de saída.
  - `channels/telegram/` — adaptador: parse de updates, formatação HTML, teclados, envio de arquivos.
  - `infra/` — banco, segredos, logs, métricas.
  - `exports/` — XLSX e PDF.
- **Biblioteca de Telegram**: preferir chamadas diretas à Bot API com `httpx` + modelos próprios (menos dependências, controle total do webhook em Lambda). Adotar `python-telegram-bot` somente se reduzir código de forma clara; registrar a escolha em DECISOES.md.
- **Banco**: `psycopg` 3 contra o endpoint *pooled* do Neon. Neon desliga após 5 min parado e acorda em centenas de ms; aceitável.

---

## 3. Contas, acesso e convites

### 3.1 Identidade

- A identidade do usuário é o `from.id` do Telegram, que chega verificado em todo update (o webhook só aceita requisições com o secret token).
- Não existe usuário/senha. Motivos: senha trafegaria no chat sem criptografia ponta a ponta, exigiria recuperação por e-mail e abriria força bruta e phishing.
- O papel **admin** é definido por variável de ambiente (`ADMIN_TELEGRAM_ID`), nunca por dado editável pelo bot.

### 3.2 Entrada no bot (atualizado 29/09/2026)

Dois caminhos de entrada que terminam no **mesmo** fluxo de cadastro (3.3).

**Caminho A — pelo link de convite** (`t.me/TelegranaBot?start=<token>`)

1. O bot valida o token: existe, ativo, não revogado, dentro do limite de usos e da validade.
2. Válido → segue para o cadastro (3.3). O uso do link só é contabilizado quando a conta é de fato criada.
3. Inválido, revogado ou esgotado → cai no Caminho B (sem revelar o motivo exato).

**Caminho B — achou o bot sozinho** (busca, @, encaminhamento, link inválido)

1. O bot responde: `🔒 O Telegrana é privado.` + `[🙋 Pedir acesso]`. Antes de enviar o pedido, mostra uma linha de aviso: "Seu nome do Telegram e sua mensagem serão enviados ao administrador."
2. Pergunta: **"Como você conhece o Adriano?"** (resposta livre, até 200 caracteres, texto escapado).
3. O admin recebe: `🙋 Maria Souza (@maria) pediu acesso · "sou prima do Adriano" [✅ Aprovar] [❌ Recusar]`.
4. **Aprovado** → a pessoa recebe `✅ Seu acesso foi liberado!` + `[Criar minha conta]` → cadastro (3.3). A aprovação vale 7 dias.
5. **Recusado** → nenhuma resposta à pessoa; novo pedido só depois de 30 dias.
6. Pedidos pendentes expiram em 7 dias e são apagados (nome, @ e mensagem).

**Anti-abuso:** 1 pedido pendente por `from.id`; limite global de pedidos por hora; nenhuma chamada de IA, geração de arquivo ou consulta pesada para quem não tem conta.

**Link de convite reutilizável (um link para a família toda):**

- O admin gera com `/link`. Não é preciso gerar um por pessoa.
- Token aleatório de 32 bytes em base64url (43 caracteres, dentro do limite de 64 do deep link do Telegram, só `A-Z a-z 0-9 _ -`). Guardado **apenas como hash** (SHA-256) no banco.
- Configuração: limite de usos (padrão 20), validade opcional (padrão sem validade), ativo/revogado.
- `/link novo` revoga o anterior e gera outro na hora. `/link status` mostra usos e contas criadas por ele.
- A cada conta criada pelo link, o admin recebe `👤 Maria Souza entrou pelo link [🚫 Bloquear]`.
- Risco aceito e mitigado: quem tiver o link entra (limite de usos, aviso com bloqueio, rotação em um comando).

**Onde o admin recebe os avisos:** na própria conversa dele com o `@TelegranaBot`; o admin é reconhecido pelo `ADMIN_TELEGRAM_ID` (variável de ambiente). Bot de administração separado descartado na V1.

### 3.3 Cadastro (primeira vez)

Ordem obrigatória — **nenhum dado pessoal é coletado antes do aceite dos termos**:

1. **Boas-vindas** com a logo e uma frase sobre o que o bot faz.
2. **Termos e privacidade** (seção 3.6): resumo + `[📄 Ler termos completos] [🔒 Política de privacidade] [✅ Li e aceito]`. Sem aceite, o cadastro não avança (a pessoa pode voltar depois com `/start`).
3. **Cadastro mínimo** (seção 3.4):
   - Nome completo (texto; validação de tamanho e caracteres; confirmação `É isso mesmo? [✅ Sim] [✏️ Corrigir]`).
   - Telefone pelo botão nativo do Telegram `[📱 Compartilhar meu número]` (`request_contact`). O bot aceita **somente** o contato cujo `user_id` é o do próprio remetente (impede enviar o número de outra pessoa).
   - Declaração de maioridade: `[✅ Tenho 18 anos ou mais]`. Sem a declaração, o cadastro é encerrado com mensagem educada (V1 é só para adultos).
4. **Configuração inicial** (pode pular e fazer depois): categorias padrão (aceitar ou ajustar), formas de pagamento (Pix, débito e dinheiro já vêm), cartões de crédito (nome, dia de fechamento, dia de vencimento).
5. **Código de recuperação**: gerado e mostrado **uma única vez** com `protect_content`, orientando a guardar nas Mensagens Salvas ou em outro lugar seguro. Guardado como hash Argon2id.
6. **Pronto**: exemplo de uso ("Tenta me mandar um áudio: 'gastei 30 reais de pão hoje'") + aviso ao admin.

O cadastro é uma **máquina de estados** persistida (`onboarding_step`): se a pessoa parar no meio, retoma de onde parou; cadastros incompletos há mais de 7 dias são apagados.

### 3.4 Dados coletados (minimização)

| Dado | Coletado? | Finalidade | Como é guardado |
|---|---|---|---|
| `from.id` do Telegram | Sim | Identidade e isolamento da conta | Texto (necessário para o funcionamento) |
| Nome completo | Sim | Identificação pelo admin (avisos, recuperação manual), cabeçalho de relatórios | Texto |
| Telefone | Sim, **somente** pelo botão nativo | Recuperação automática da conta | **Apenas HMAC-SHA256** com chave secreta (pepper no SSM); o número em si nunca é gravado. Normalizado em E.164 antes do HMAC |
| Declaração de maioridade | Sim | Base legal (V1 só para adultos) | Booleano + data |
| Aceite dos termos | Sim | Prova do consentimento | Versão, hash do texto, data/hora |
| @ e nome do Telegram | Só nos pedidos de acesso | Admin decidir o pedido | Apagados com o pedido (7 dias) ou ao criar a conta |
| E-mail | **Não** (V1) | Sem finalidade hoje; entra só se houver recuperação por e-mail | — |
| Data de nascimento | **Não** | Sem finalidade; a declaração de maioridade basta | — |

Qualquer dado novo exige finalidade escrita aqui, atualização da política de privacidade e novo aceite.

### 3.5 Login, recuperação e exclusão

A identidade é a **conta do Telegram** (`from.id`), não o aparelho.

| Situação | O que acontece |
|---|---|
| Trocou de celular / reinstalou o app | Nada a fazer: mesmo `from.id`, o bot reconhece e o histórico continua |
| Apagou a conta do Telegram e criou outra **com o mesmo número** | No `/start`, o bot oferece `[🔄 Recuperar minha conta]` → pede `[📱 Compartilhar meu número]` → se o HMAC bater com o de uma conta existente, a conta é religada ao novo `from.id` |
| Conta nova com **outro número** | `/entrar` + código de recuperação → religa a conta; o bot pede para compartilhar o número novo (atualiza o HMAC) |
| Perdeu o código **e** trocou de número | Pedido de recuperação ao admin com o nome completo informado; o admin confere a pessoa **fora do bot** e aprova; a conta é religada |

Regras de segurança da recuperação:

- Bloqueio progressivo por `from.id` após tentativas erradas de código (ex.: 5 erros → 15 min, dobrando).
- O código de recuperação é **trocado a cada uso** e mostrado de novo uma única vez.
- Toda religação: aviso ao admin, registro em `audit_log` e, se a conta antiga do Telegram ainda existir, recado a ela: "⚠️ Sua conta Telegrana foi transferida para outro Telegram. Não foi você? Fale com o administrador."
- Religar desvincula o `from.id` antigo (uma conta Telegrana ↔ um `from.id` por vez na V1).
- `/codigo_novo`: gera novo código de recuperação (invalida o anterior), com confirmação.
- Orientação no onboarding e na política: o Telegram apaga contas inativas após um prazo configurável (padrão 6 meses) — quem usa o Telegram só para o bot deve aumentar esse prazo nas configurações de privacidade do app.

Exclusão e portabilidade:

- `/exportar`: XLSX completo com todos os dados da conta.
- `/apagar_conta`: oferece o export antes, pede confirmação dupla, apaga **tudo** de forma definitiva (inclusive nome, HMAC do telefone e aceites; permanece só um registro anônimo em `audit_log` de que uma conta foi excluída naquela data).
- `/meus_dados`: mostra o que está guardado sobre a pessoa (nome, maioridade, data do aceite, versão dos termos; o telefone aparece como "vinculado ✅").
- `/corrigir_nome`: corrige o nome completo.

### 3.6 Termos de uso e política de privacidade

- Dois documentos em português simples: **Termos de Uso** e **Política de Privacidade**, versionados em `legal/` no repositório (`termos-v1.md`, `privacidade-v1.md`).
- Publicados como páginas do **Telegraph** (telegra.ph, abre dentro do Telegram, grátis), criadas pela API do Telegraph com a conta do projeto; o link de cada versão fica na configuração.
- O agente redige a primeira versão; **o Adriano revisa e aprova antes de publicar**.
- Aceite registrado em `terms_acceptances (user_id, doc, version, content_sha256, accepted_at)`.
- Nova versão → na próxima mensagem, a pessoa vê o resumo das mudanças e `[✅ Li e aceito]` antes de continuar usando. Até aceitar, só `/exportar` e `/apagar_conta` funcionam.
- `/termos` mostra os links e a versão aceita.

Resumo exibido no bot (modelo):

```
📜 Antes de começar
🧾 Guardamos seus lançamentos, seu nome e um código do seu telefone (para recuperar a conta).
🔐 Cada conta é isolada: ninguém vê seus dados, nem outros usuários.
🤖 Suas mensagens passam por uma IA só para entender o que você disse; ela não guarda nem aprende com elas.
🌎 Os dados ficam em servidores nos EUA (AWS, Neon, Groq).
💬 A conversa com bots do Telegram não tem criptografia de ponta a ponta.
📊 O Telegrana organiza, não é consultoria financeira.
🗑️ Você pode exportar ou apagar tudo quando quiser.
```

Conteúdo mínimo obrigatório dos documentos:

- **Controlador**: Adriano, pessoa física; canal de contato.
- **Dados coletados e finalidade** (tabela da seção 3.4), base legal (consentimento e execução do serviço pedido pelo usuário).
- **Operadores e transferência internacional**: Telegram, AWS, Neon, Groq; servidores nos EUA.
- **IA**: uso só para interpretação; Groq sem treino e com retenção zero ativada.
- **Segurança adotada** em linguagem simples e **limites** (Telegram sem criptografia ponta a ponta em bots).
- **Direitos do titular**: acesso (`/meus_dados`), correção, portabilidade (`/exportar`), eliminação (`/apagar_conta`), revogação do consentimento.
- **Retenção**: enquanto a conta existir; pedidos de acesso e cadastros incompletos apagados em 7 dias; logs técnicos sem dados pessoais por 7 dias.
- **Sem garantia**: não é consultoria financeira; o usuário confere os próprios números; serviço gratuito, sem garantia de disponibilidade.
- **Regras de uso**: uso pessoal, proibido uso comercial ou ilícito; o admin pode suspender contas.
- **Menores**: V1 só para maiores de 18 anos.
- **Mudanças nos termos**: novo aceite obrigatório.

Nota registrada: a LGPD não se aplica ao tratamento feito por pessoa física para fins exclusivamente particulares e não econômicos (art. 4º, I), o que provavelmente cobre o uso familiar. Os termos são adotados mesmo assim como boa prática. **Se o bot sair do círculo familiar ou virar público/portfólio, os textos devem ser revisados por um advogado antes.**

### 3.7 Preparado para contas compartilhadas (não implementar na V1)

- Tabela `accounts` (o "cofre" de dados) separada de `users` (a pessoa no Telegram) e `account_members (account_id, user_id, role)`.
- Na V1 cada usuário tem exatamente uma conta e é `owner` dela. A RLS já filtra por `account_id` da sessão, então habilitar uma conta "Casa" no futuro é adicionar membros e um seletor de conta, sem mudar o isolamento.

---

## 4. Domínio financeiro

### 4.1 Lançamentos

- Tipos: **gasto** e **ganho** (e **transferência** entre formas de pagamento da mesma pessoa, ex.: pagar fatura, se necessário para a lógica de cartão).
- Campos: valor (centavos), tipo, categoria, forma de pagamento, data de competência (quando aconteceu), data de caixa (quando o dinheiro saiu/entrou de fato), descrição, origem (texto/áudio/fixo/fatura), texto original ou transcrição, status (`realizado`, `previsto`), id do update de origem.
- Uma mensagem pode gerar vários lançamentos ("paguei 40 de uber e 25 de almoço").
- Todo lançamento gera um **recibo** com botões:

```
✅ Gasto registrado
🛒 Mercado · R$ 45,90
💳 Pix · hoje, 29/09
📝 compras no Dia
[✏️ Corrigir] [🏷️ Categoria] [🗑️ Apagar]
```

- Corrigir também funciona respondendo (reply) ao recibo em linguagem natural: "na verdade foi 54,90".
- Exclusão lógica (`deleted_at`) com "desfazer" por alguns minutos; o export e os relatórios ignoram excluídos.

### 4.2 Categorias

- Lista padrão com emoji fixo (ex.: 🛒 Mercado, 🍽️ Alimentação fora, 🏠 Moradia, 💡 Contas da casa, 🚗 Transporte, ⛽ Combustível, 💊 Saúde, 📚 Educação, 🎮 Lazer, 👕 Vestuário, 📱 Assinaturas, 🐾 Pets, 👶 Filhos, 🎁 Presentes, 💸 Encargos e juros, 📦 Outros; ganhos: 💼 Salário, 🧾 Serviços/Freela, 📈 Rendimentos, ↩️ Reembolso, 🎉 Outros ganhos).
- Cada conta pode criar, renomear, trocar emoji e desativar categorias (`/categorias`). Nunca apagar categoria com lançamentos: desativar.
- A IA escolhe **dentro da lista da conta**; se não houver encaixe, usa "Outros" e oferece criar uma nova.

### 4.3 Fixos e recorrentes

- Gastos fixos (água, luz, internet, aluguel, assinaturas) e ganhos fixos (salário, pensão).
- Campos: nome, tipo, categoria, valor **fixo** ou **estimado**, dia do mês (tratar meses curtos: dia 31 vira o último dia), forma de pagamento padrão, configuração de lembretes, ativo.
- **O fixo gera lembrete, não lançamento automático.** Ao tocar em `✅ Paguei` (ou `✅ Recebi`), o lançamento é criado com o valor fixo ou com o valor informado.

```
💡 Conta de luz vence hoje
Valor estimado: R$ 180,00
[✅ Paguei] [✏️ Outro valor] [⏭️ Pular este mês]
```

### 4.4 Lembretes (aprovado)

Por item (fixo ou fatura de cartão), cada um configurável individualmente:

- **Regras** (combináveis): `1 dia antes`, `no dia`, `diário após o vencimento` (até marcar Paguei/Recebi ou Pular).
- **Horário**: `manhã (09:00)`, `noite (20:00)` ou `ambos`.
- Lembretes podem ser desligados por item.
- Motor: EventBridge Scheduler dispara a Lambda `rotinas` às 09:00 e às 20:00 (`America/Sao_Paulo`). Ela calcula o que vence para cada conta e grava `reminder_sends (account_id, item_id, due_date, rule, slot)` com restrição única para nunca duplicar.

### 4.5 Cartão de crédito, parcelamento e fatura (aprovado)

Princípio: **regime de caixa**. Compra no crédito é compromisso; vira gasto realizado quando a fatura é paga.

1. **Cartão**: nome, dia de fechamento, dia de vencimento, (opcional) limite.
2. **Compra**: "tênis 600 em 3x no Nubank" gera 3 parcelas de R$ 200,00. Cada parcela é atribuída à fatura correta pela data de fechamento (compra após o fechamento cai na fatura seguinte). Centavos da divisão ficam na primeira parcela.
3. **Fatura**: agrega as parcelas do período. Fecha automaticamente na data de fechamento. O vencimento usa o mesmo motor de lembretes dos fixos.
4. **Pagamento**: `✅ Paguei a fatura` (valor total ou outro valor). Cada item da fatura vira gasto **realizado na data do pagamento, mantendo a própria categoria** (o relatório mostra "👕 Vestuário R$ 200", não "Fatura R$ 2.300").
5. **Casos especiais**: pagamento parcial (saldo restante vai para a próxima fatura como item "Saldo anterior"); juros e multa (gasto em 💸 Encargos); estorno (crédito na fatura); compra à vista no crédito (1 parcela).
6. **Visões nos relatórios**: ✅ Realizado (padrão) · 🗓️ Compromissos (fatura aberta e parcelas futuras) · 🛍️ Por data da compra (opcional).

Pix, débito e dinheiro: realizados na hora.

---

## 5. IA (Groq)

### 5.1 Uso

| Tarefa | Modelo | Saída |
|---|---|---|
| Transcrever áudio | `whisper-large-v3` (idioma `pt`, prompt com vocabulário: Pix, Nubank, débito, crédito, parcelado, boleto...) | texto |
| Classificar intenção e extrair lançamentos | `gpt-oss-20b` | JSON validado (Pydantic) |
| Interpretar pedido de relatório/consulta | `gpt-oss-120b` | `ReportSpec` validado |

- Verificar os modelos disponíveis e os limites atuais do plano gratuito do Groq no início (mudam com frequência) e registrar em DECISOES.md. *(Verificado em 29/09/2026: D019 — 1.000 req/dia e 200 mil tokens/dia por modelo gpt-oss, por organização.)*
- **Provedor trocável por configuração** (interface única `LLMProvider`); reserva quando o Groq falhar: fila com nova tentativa respeitando os cabeçalhos de limite; se persistir, responder "⏳ Estou sobrecarregado, tento de novo em instantes" e reprocessar. Gemini grátis **não** é reserva (termos permitem revisão humana de dados).
- Zero Data Retention ativado no painel do Groq.
- Contexto enviado ao modelo: só o necessário (texto da mensagem, lista de categorias e formas de pagamento da conta, data de hoje). Nunca o histórico financeiro completo.

### 5.2 Regras

- Saída sempre estruturada e validada. Inválida → o bot pergunta ou pede para reformular; nunca "chuta".
- Conversões e datas relativas ("ontem", "sexta passada", "dia 5") resolvidas **no código** a partir de campos estruturados, não pelo modelo.
- Valores: o modelo extrai o texto do valor; o código normaliza ("50 conto", "R$ 1.234,56", "mil e duzentos", "1,2k").
- Mensagem do usuário é **dado, nunca instrução** (defesa contra prompt injection): o modelo não tem ferramentas, não vê dados de outras contas e sua saída só pode preencher campos permitidos.

### 5.3 Avaliação contínua (S2 em diante)

- `tests/eval/` com o conjunto de mensagens reais (texto e áudio) do Adriano e da família, cada uma com a saída esperada.
- Métrica mínima para ir a produção: **≥ 95% de acerto** em valor, tipo e data; **≥ 90%** em categoria.
- Rodar a avaliação no CI a cada mudança de prompt ou modelo. Comparar com um segundo modelo (ex.: Claude Haiku via créditos gratuitos iniciais da API, se o Adriano quiser) apenas como referência; a produção fica no Groq.

---

## 6. Relatórios e exportação

- **Pedido em linguagem natural** ("quanto gastei de mercado nos últimos 3 meses, mês a mês", "meus ganhos de 2026 por categoria em PDF").
- Fluxo: IA → `ReportSpec` (período, tipo, categorias, formas de pagamento, agrupamento, ordenação, visão realizado/compromissos/compra, formato texto/XLSX/PDF) → validação → **SQL montado pelo código com campos e agregações de lista permitida** → resultado → formatação.
- Comandos rápidos: `/resumo` (mês atual), `/relatorio`, `/fixos`, `/cartoes`, `/fatura`, `/categorias`, `/exportar`, `/ajuda`.
- Conta e privacidade: `/meus_dados`, `/corrigir_nome`, `/codigo_novo`, `/entrar`, `/termos`, `/apagar_conta`.
- Admin (só `ADMIN_TELEGRAM_ID`): `/link`, `/link novo`, `/link status`, `/pedidos`, `/usuarios`, `/bloquear`, `/religar`.
- **Rotinas automáticas**: resumo semanal (domingo 20:00) e fechamento do mês (dia 1, 09:00) com PDF anexo — ambos desligáveis por conta.
- **XLSX** (openpyxl): abas Resumo, Por categoria, Lançamentos, Compromissos; formatação de moeda BRL, cabeçalho nas cores da marca, filtros e colunas ajustadas.
- **PDF**: cabeçalho com a logo e degradê azul→verde, resumo em cards, gráfico de barras por categoria, tabela de lançamentos. Biblioteca leve compatível com Lambda (avaliar `fpdf2`, `reportlab`); evitar Chromium e dependências pesadas. Registrar a escolha.
- **Segurança dos arquivos**: neutralizar injeção de fórmula em XLSX/CSV (prefixar `'` em células de texto iniciadas por `=`, `+`, `-`, `@`, tab ou CR); arquivos gerados em `/tmp`, enviados e apagados na mesma execução; nome do arquivo sem dados sensíveis.

---

## 7. Mensagens e identidade visual

### 7.1 Mensagens

- Formatação **HTML do Telegram** (`parse_mode=HTML`). Todo texto vindo do usuário ou do banco é escapado (`&`, `<`, `>`).
- Claras, objetivas, com emoji ilustrando o que for possível. Emoji fixo por categoria. 🟢 ganho, 🔴 gasto, 💰 saldo, 🗓️ compromisso, ⚠️ atenção.
- Tabelas em bloco monoespaçado (`<pre>`), detalhes longos em citação recolhível (`<blockquote expandable>`).
- Botões inline para ações; `callback_data` curto e **nunca confiável**: sempre revalidar no servidor que o item pertence à conta de quem clicou.
- Valores sempre no formato brasileiro: `R$ 1.234,56`. Datas: `29/09` ou `29/09/2026`.
- Menu de comandos registrado via `setMyCommands`; descrição e foto do bot via BotFather/API.

Exemplo de resumo:

```
📊 Setembro/2026
🟢 Ganhos   R$ 5.200,00
🔴 Gastos   R$ 3.870,45
💰 Saldo  + R$ 1.329,55

🏠 Moradia   R$ 1.500 (39%)
🛒 Mercado   R$   820 (21%)
🚗 Transp.   R$   410 (11%)

🗓️ Fatura Nubank aberta: R$ 640,00 (vence 10/10)
```

### 7.2 Identidade visual

Logo criada pelo Adriano (arquivo que ele colocará em `assets/brand/` ao iniciar o projeto). Paleta extraída da logo:

| Papel | Cor |
|---|---|
| Azul claro (topo do "t") | `#0FADFC` |
| Azul Telegrana (texto "Tele") | `#0179E0` |
| Azul escuro (sombra do "t") | `#0068CB` |
| Transição azul→verde | `#0389A2` |
| Verde grana (texto "grana") | `#19B751` |
| Verde escuro | `#09A451` |
| Texto | `#0F172A` |
| Fundo | `#F8FAFC` |
| Gasto (relatórios) | `#EF4444` |

**Tarefas de marca para o agente (S1):**

1. Ler a logo original de `assets/brand/` sem alterá-la.
2. Remover o fundo branco (PNG com transparência), sem serrilhado nas bordas.
3. Gerar:
   - `icon-640.png` — só o símbolo ("t" com a nota e a seta), quadrado 640×640, centralizado com margem para o recorte **redondo** da foto do bot; conferir legibilidade em 64×64.
   - `logo-full.png` — símbolo + "Telegrana", fundo transparente, alta resolução.
   - `logo-horizontal.png` — símbolo à esquerda e nome à direita, para o cabeçalho de PDF e XLSX.
   - `logo-mono-white.png` — versão branca para aplicar sobre o degradê.
   - Tamanhos derivados: 512, 256, 128, 64.
4. Salvar em `assets/brand/out/`, registrar a paleta em `src/.../brand.py` (tokens únicos usados por XLSX e PDF).
5. Mostrar as prévias ao Adriano antes de aplicar a foto no bot.

Observação registrada: o avião de papel da logo remete ao símbolo do Telegram (marca registrada). **Risco aceito** para uso familiar; reavaliar se o projeto virar público ou portfólio.

---

## 8. Segurança (inegociável)

Modelo de ameaças mínimo: bot público no Telegram, dados financeiros pessoais de várias pessoas no mesmo banco, IA recebendo texto livre, execução paga (AWS) exposta à internet.

### 8.1 Entrada (webhook)

- Function URL com `AuthType NONE` (o Telegram não assina requisições com IAM) → **exigir o cabeçalho `X-Telegram-Bot-Api-Secret-Token`**, comparado em tempo constante; rejeitar sem processar e sem detalhar o erro.
- Aceitar só `POST` e `Content-Type: application/json`; limite de tamanho do corpo; parse estrito.
- `setWebhook` com `allowed_updates` mínimo (`message`, `callback_query`, `my_chat_member`), `max_connections` baixo (ex.: 5) e `drop_pending_updates` no deploy.
- **Idempotência**: tabela `processed_updates (update_id)` com restrição única; update repetido é ignorado.
- Ignorar mensagens de grupos e canais (o bot só opera em chat privado); o bot sai de grupos em que for adicionado.
- Opcional: verificar faixas de IP do Telegram (defesa em profundidade; não substitui o token).

### 8.2 Autorização e isolamento

- Toda tabela de dados tem `account_id` e **RLS habilitado e forçado** (`FORCE ROW LEVEL SECURITY`).
- A aplicação conecta com um papel **sem** privilégio de dono e **sem** `BYPASSRLS`. Migrações rodam com outro papel (migrador), só no pipeline de deploy.
- A conta da sessão é definida por transação (`SET LOCAL app.account_id = ...`), derivada do `from.id` verificado. Política RLS compara com essa variável.
- Chaves compostas `(account_id, id)` e FKs compostas em todas as relações (parcela→fatura→cartão, lançamento→categoria etc.).
- `callback_data` e respostas (reply) revalidados: o item precisa existir **na conta da sessão**.
- **Suíte de testes de isolamento obrigatória**: para cada tabela e cada rota, criar duas contas e provar que A não lê, altera, apaga, exporta nem referencia dados de B. Roda no CI; bloqueia deploy.
- Comandos de admin conferidos pelo `ADMIN_TELEGRAM_ID`; ações administrativas registradas em `audit_log`.

### 8.3 IA

- Entrada do usuário tratada como dado; limites: texto até 1.000 caracteres, áudio até 2 minutos / 20 MB, antes de chamar a IA.
- Saída só por esquema Pydantic estrito (`extra="forbid"`, enums, faixas de valor). Nada que o modelo diga vira SQL, comando, URL ou decisão de acesso.
- Sem histórico de outras contas no prompt. Sem ferramentas/funções que acessem o banco.

### 8.4 Segredos

- Produção: SSM Parameter Store `SecureString` (chave gerenciada `aws/ssm`), lidos na inicialização da Lambda e mantidos em memória; nunca em variáveis de ambiente em texto puro no template.
- Local: `.env.local` (no `.gitignore`), criado pelo Adriano conforme os guias da S0.
- CI: GitHub Actions com **OIDC** e papel IAM de deploy com permissões mínimas, restrito ao repositório e à branch `main`.
- `gitleaks` (ou equivalente) em pre-commit e no CI; secret scanning e push protection ativos no GitHub. *(29/09/2026: só são gratuitos em repositório público; por isso o repositório é público — D015.)*
- Rotação documentada para cada segredo (token do bot, chave do Groq, senha do banco, token do webhook, segredo do link de convite).

### 8.5 Dados e privacidade

- Logs estruturados **sem** valores, descrições, transcrições, nomes ou tokens; apenas ids técnicos, tipo de evento, latência e erro. Retenção de 7 dias no CloudWatch.
- Mensagens com código de recuperação: enviadas com `protect_content` e orientação para apagar do chat após salvar.
- Telefone nunca gravado em claro: só HMAC-SHA256 com pepper guardado no SSM (sem o pepper, o hash não serve para descobrir o número). O contato compartilhado só é aceito se `contact.user_id == from.id`.
- Minimização (seção 3.4): nenhum dado novo sem finalidade escrita, atualização da política e novo aceite.
- Áudios: baixados para memória/`/tmp`, transcritos e descartados; nunca armazenados. A transcrição fica no lançamento (para auditoria do próprio usuário) e sai junto em `/apagar_conta`.
- Direitos do titular (LGPD, mesmo em uso familiar): `/meus_dados`, `/corrigir_nome`, `/exportar`, `/apagar_conta`; termos e política versionados com aceite registrado (seção 3.6).
- Conexão com o Neon sempre com TLS verificado (`sslmode=verify-full`).

### 8.6 Abuso e disponibilidade

- Limite de requisições por conta (ex.: 20 mensagens/min, 300/dia) e global; chamadas de IA contadas por conta.
- Quem não tem conta não aciona IA, banco pesado nem geração de arquivos.
- Timeouts em todas as chamadas externas; retry com backoff só onde idempotente.

### 8.7 Cadeia de suprimentos e código

- Dependências travadas com hash (`uv lock` ou `pip-compile --generate-hashes`); lista curta e justificada de pacotes.
- CI: `ruff`, `mypy --strict` no núcleo, `bandit`, `pip-audit`, testes, suíte de isolamento, avaliação de IA.
- Dependabot/Renovate para atualizações de segurança.
- Nenhuma dependência de pacotes "anti-ban", wrappers desconhecidos ou forks sem manutenção.

### 8.8 Conta AWS

- MFA na root; root não é usada no dia a dia.
- Acesso de desenvolvimento por usuário/perfil com permissões mínimas e credenciais temporárias (IAM Identity Center ou `aws configure sso`, se disponível; caso contrário usuário IAM com MFA). *(29/09/2026: usuário IAM `adriano-dev` com MFA + `aws login`, credencial temporária de até 12 h, sem access keys; administrador durante o bootstrap, reduzido na S8 — D017.)*
- IAM por função: cada Lambda com papel próprio e só as permissões que usa.
- CloudTrail (trilha de gerenciamento padrão, gratuita) ativo.

---

## 9. Custos e proteções (AWS)

Conta antiga (mais de 12 meses): só os benefícios **Always Free**, que atendem o projeto.

| Serviço | Franquia permanente | Uso previsto (10 pessoas) |
|---|---|---|
| Lambda | 1 milhão de requisições + 400 mil GB-s/mês | ~2% |
| EventBridge Scheduler | 14 milhões de invocações/mês | ~60/mês |
| AWS Budgets | Alertas grátis; 2 orçamentos com ação grátis | 1 com ação + alertas |
| SSM Parameter Store (padrão) | Grátis | poucos parâmetros |
| CloudWatch Logs | Franquia básica | mínimo com retenção de 7 dias |

**Proteções (S0.2 + S1):**

1. **Auditoria inicial** da conta em todas as regiões: recursos esquecidos de cursos (EC2, EBS, snapshots, IP elástico, NAT Gateway, RDS, S3). Listar ao Adriano antes de apagar qualquer coisa.
2. **Orçamentos**: "zero spend" (alerta ao primeiro centavo) e um orçamento de US$ 1/mês com alertas real e previsto.
3. **Kill-switch**: orçamento com ação → SNS → Lambda que zera a concorrência reservada das Lambdas do projeto e avisa o admin no Telegram. Atenção: o Budgets atualiza poucas vezes ao dia; é cinto de segurança, não bloqueio instantâneo.
4. **Tetos técnicos**: concorrência reservada baixa nas Lambdas (ex.: 5), memória e timeout mínimos necessários, `max_connections` do webhook baixo.
5. **Nada de serviços pagos no caminho**: sem API Gateway, sem NAT, sem VPC, sem Secrets Manager, sem KMS gerenciado pelo cliente, sem S3 obrigatório (se o SAM precisar de bucket de artefatos, usar ciclo de vida curto; custo de centavos, registrar).
6. Neon Free e Groq Free não têm cartão: no pior caso, param de responder, não cobram.

---

## 10. Automação de desenvolvimento e testes

Objetivo: depois da S0, o Claude Code desenvolve, testa e publica **sem precisar do Adriano**, exceto para validação visual e aprovações.

### 10.1 Pirâmide de testes

1. **Unitários**: parsing de valores e datas, regras de cartão/fatura/parcelas, lembretes, formatação de mensagens, geração de XLSX/PDF.
2. **Integração com banco real**: Postgres em container **do CI** (mesma versão do Neon) e branch `dev` do Neon na máquina local; inclui a suíte de isolamento RLS. *(29/09/2026: sem Docker local — D018.)*
3. **Avaliação de IA** (`tests/eval/`): conjunto real de mensagens e áudios com saída esperada.
4. **Ponta a ponta no ambiente de testes do Telegram**:
   - O Telegram tem servidores de teste separados, com números reservados no formato `99966XYYYY` (X = data center 1–3) cujo código de login é o número do DC repetido; sem SMS, sem celular.
   - Com `api_id`/`api_hash` do my.telegram.org, o agente usa um cliente de usuário (ex.: Telethon) no servidor de teste para: criar usuários de teste, conversar com o **@BotFather de teste** para criar o bot de teste, e conversar com o bot enviando textos, áudios (gerados por TTS ou gravados) e cliques em botões, validando cada resposta.
   - A Bot API de teste é acessada pelo caminho `/bot<token>/test/<método>`.
   - Verificar esses detalhes na documentação atual antes de implementar.
5. **Validação no aparelho real** (adb Wi-Fi no celular Android do Adriano): abrir o Telegram, capturar telas das mensagens, recibos, teclados, PDF e XLSX abertos, e conferir a formatação. Usar para entregas visuais e antes de cada liberação à família. Nunca ler outras conversas do aparelho além da conversa com o bot.

### 10.2 Ambientes

| Ambiente | Bot | Banco | Uso |
|---|---|---|---|
| `test` | bot no servidor de testes do Telegram | Postgres em container do CI / branch `dev` do Neon (local) | E2E automatizado |
| `dev` | `@TelegranaDevBot` (produção do Telegram, privado) | branch `dev` do Neon | testes manuais e no celular |
| `prod` | `@TelegranaBot` | branch principal do Neon | família |

### 10.3 Pipeline

- PR → CI (lint, tipos, segurança, testes, isolamento, eval) → merge em `main` → deploy automático em `dev` → E2E → promoção para `prod` (automática após E2E verde na V1; o Adriano pode pedir aprovação manual).
- Migrações versionadas, aplicadas pelo pipeline com o papel migrador, sempre compatíveis com a versão anterior do código (deploy sem janela de indisponibilidade).

---

## 11. S0 — Ações manuais do Adriano (micro-fases)

**Regra para o agente**: antes de escrever cada guia, **pesquisar o procedimento atual** na documentação oficial da plataforma (as telas mudam), anotar a data da verificação e produzir um passo a passo detalhado em `docs/manual/S0.x-<plataforma>.md` com:

1. Objetivo da micro-fase e tempo estimado.
2. Pré-requisitos.
3. Passo a passo numerado, com o caminho exato de menus e o que clicar/preencher.
4. **O que entregar ao agente** e **como** (sempre em `.env.local`, nunca colando segredo no chat; ou via CLI direto para o SSM quando fizer sentido).
5. Checklist de verificação ("como saber que deu certo").
6. Erros comuns e como resolver.

O agente entrega todos os guias **de uma vez, no início**, em ordem, para o Adriano executar em sequência. Depois valida cada entrega automaticamente (ex.: testa a chave do Groq, conecta no Neon, confere o token do bot) e só então segue para a S1.

| Micro-fase | Plataforma | O que o Adriano faz | O que o agente recebe |
|---|---|---|---|
| **S0.1** | GitHub | Criar repositório **público** `telegrana` (D015, 29/09/2026); ativar secret scanning, push protection e Dependabot; dar ao Claude Code acesso ao repo | URL do repo; acesso git funcionando |
| **S0.2** | AWS | Entrar na conta antiga; ativar MFA na root; criar acesso de desenvolvimento com permissões adequadas e configurar o AWS CLI local; confirmar região `us-east-1`; autorizar o agente a criar o provedor OIDC do GitHub, os orçamentos e o kill-switch | Perfil do AWS CLI funcionando na máquina; o agente então audita a conta e cria orçamentos, OIDC e papéis via código |
| **S0.3** | Neon | Criar conta (sem cartão), projeto `telegrana` em `us-east-1` (AWS), Postgres na versão mais recente estável; criar branch `dev` | String de conexão do dono (para o agente criar os papéis `migrator` e `app`) em `.env.local` |
| **S0.4** | Groq | Criar conta; ativar **Zero Data Retention** em Data Controls; criar duas chaves de API (`telegrana-prod`, `telegrana-dev`) | Chaves em `.env.local` |
| **S0.5** | Telegram | No @BotFather: criar `@TelegranaBot` (nome de exibição "Telegrana"; se ocupado, variação) e `@TelegranaDevBot`; em my.telegram.org: criar aplicativo e obter `api_id` e `api_hash` (para os testes automáticos); informar o próprio `from.id` (o agente pode descobrir pelo bot de dev) | Tokens dos dois bots, `api_id`, `api_hash`, `ADMIN_TELEGRAM_ID` em `.env.local`. O bot do **servidor de testes** o agente cria sozinho |
| **S0.6** | Celular (Android) | Ativar opções de desenvolvedor e **depuração por Wi-Fi**; parear com o PC (`adb pair`) e conectar (`adb connect`); Telegram instalado e logado | `adb devices` listando o aparelho |
| **S0.7** | Marca e dados | Colocar a logo em `assets/brand/`; **coletar o conjunto de teste**: 40–60 mensagens reais do jeito que ele e a esposa falariam (texto) e 15–20 áudios curtos, incluindo casos bagunçados, ganhos, fixos e compras parceladas; revisar a lista de categorias padrão | Arquivos em `tests/eval/data/` (**fora do Git**, D016) e `assets/brand/` |

Observações:
- O agente deve verificar se o Adriano usa Android (adb); se algum membro usar iPhone, a validação visual nele fica manual, com checklist gerado pelo agente.
- Nenhum passo pede cartão fora da AWS. Se alguma plataforma pedir, **parar e avisar**.

---

## 12. Sprints

Cada sprint fecha com o **protocolo de encerramento** (CLAUDE.md).

| Sprint | Entrega | Critério de pronto |
|---|---|---|
| **S0** | Guias manuais (S0.1–S0.7) e validação automática de cada entrega | Todas as credenciais validadas; conta AWS auditada; orçamentos e kill-switch criados |
| **S1 — Fundação** | Repo, estrutura, SAM, Lambdas `bot`/`rotinas`/`kill-switch`, Function URL, webhook com secret, deduplicação, esquema inicial com RLS e papéis, migrações, CI/CD com OIDC, logs, segredos no SSM, recortes da logo, `/start` com link de convite, pedido de acesso com "como você conhece o Adriano?" e aprovação do admin, termos e política (rascunho revisado pelo Adriano e publicado no Telegraph), cadastro mínimo (nome, telefone via botão, maioridade) como máquina de estados, código de recuperação, recuperação por telefone, `/entrar`, recuperação manual pelo admin, `/meus_dados`, `/corrigir_nome`, `/termos`, `/apagar_conta` | E2E no servidor de testes cobrindo: entrar pelo link, link revogado, pedir acesso, aprovar, recusar, recusar termos, sem maioridade, contato de outra pessoa rejeitado, recuperação por telefone, por código e manual, bloqueio por tentativas; suíte de isolamento verde |
| **S2 — Lançamentos por texto** | Extração com gpt-oss-20b, normalização de valores e datas, múltiplos lançamentos por mensagem, recibo com botões, correção por reply, categorias, avaliação de IA no CI | Eval ≥ 95% valor/tipo/data e ≥ 90% categoria |
| **S3 — Áudio** | Download, Whisper com vocabulário, mesmo fluxo do texto, transcrição resumida no recibo | Eval de áudio no mesmo patamar |
| **S4 — Fixos e lembretes** | Cadastro/edição de fixos, motor de lembretes (regras e horários), Scheduler, `✅ Paguei/Recebi`, `⏭️ Pular` | Testes de calendário (meses curtos, virada de mês, horário) e E2E de lembretes |
| **S5 — Cartão de crédito** | Cartões, parcelamento, faturas, fechamento, pagamento total/parcial, juros, estorno, lembretes de fatura | Testes das regras de fatura com casos de borda |
| **S6 — Relatórios em texto** | `ReportSpec`, consultas por linguagem natural, `/resumo`, visões realizado/compromissos/compra, resumo semanal e fechamento mensal | Testes de consultas; números conferidos contra SQL de referência |
| **S7 — Exportação** | XLSX e PDF com identidade visual, `/exportar` completo | Arquivos abertos e conferidos no celular via adb |
| **S8 — Endurecimento e entrada da família** | Revisão de segurança completa (checklist da seção 8), teste do kill-switch, limites de uso, backup (ver abaixo), documentação de operação | Adriano usa sozinho por 2 semanas; depois gera o link para a família |

**Backup (S8)**: o Neon Free só restaura as últimas 6 horas. Proposta: export lógico semanal cifrado (chave pública; a privada fica só com o Adriano, offline) enviado ao chat do admin, mais o XLSX mensal de cada usuário. O agente avalia e registra a solução final.

---

## 13. Depois da V1 (backlog)

- Contas compartilhadas (conta "Casa" com membros) — estrutura já preparada.
- Orçamento por categoria com alertas de 80% e 100%.
- Leitura de cupom fiscal (QR code da NFC-e).
- Metas de economia.
- Painel web (somente leitura) com login pelo Telegram.
- **Canal WhatsApp** (decidido: estudar depois da V1): avaliar viabilidade e o investimento na AWS para um gateway sempre ligado fora da Lambda; o núcleo já é agnóstico de canal.
- Recuperação por e-mail (só se houver necessidade; exigiria coleta de e-mail com finalidade, envio via SES e nova versão da política).
- Contas para menores de idade vinculadas a um responsável.

---

## 14. Assunções a confirmar no início

- O celular principal do Adriano é Android (necessário para adb). ✅ **Confirmado em 29/09/2026: Android 11+.** Há iPhone na família → checklist visual manual (D020).
- O @ `TelegranaBot` pode estar ocupado; qualquer variação serve. (Ordem de alternativas no guia S0.5.)
- Limites atuais do Groq (modelos e cotas) — verificar e registrar. ✅ **Verificado em 29/09/2026 (D019).**
- A conta AWS não tem Organizations; se tiver, avaliar SCPs para o kill-switch. ⏳ **Verificado automaticamente pelo `check_setup` após a S0.2.**

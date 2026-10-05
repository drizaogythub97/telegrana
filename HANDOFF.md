# HANDOFF.md — Telegrana

> Atualizado em 05/10/2026 · **S0 a S4 encerradas** · texto, áudio, **fixos e lembretes** no ar em dev e prod · próxima: **S5 — cartão de crédito**.
> **Repositório público (D015): nada de segredo nem dado pessoal neste arquivo.** Segredos: só o nome da variável e onde ela mora.

## Leia nesta ordem

1. `CLAUDE.md` — regras permanentes (segurança, regras de ouro, protocolo de encerramento).
2. Este arquivo.
3. `docs/PLANO.md` — fonte da verdade. Revisões datadas de 29 e 30/09/2026; a seção 15 descreve o WhatsApp (S9).
4. `docs/DECISOES.md` — D001 a D044. As mais recentes mudam bastante o plano original: D015 (repositório público), D017 (acesso por `aws login`), D021/D026 (conta AWS nova com créditos), D022 (WhatsApp), D023 (base AWS), D024 (Neon), D025 (Groq), D027/D028 (avaliação da IA).
5. `deploy/README.md` — base da conta AWS e como religar depois do kill-switch.

## Estado atual

A S1 foi dividida em 5 micro-fases (aceito pelo Adriano em 30/09/2026). **S1.1 (esqueleto e CI)** concluída no PR #17 (`a69e6e7`); **S1.2 (banco)** no PR #19 (`d5caa19`); **S1.3 (infra e webhook)** no PR #20 (`07cd4db`). **S1.4 (entrada, cadastro, recuperação, comandos de conta e de admin)** no PR #24 (`d6bd378`, D033), com a correção do deploy no PR #25 (`8ae59fc`). **No ar em dev e prod** (produção publicada pela execução 36867652126 em 01/10/2026). O Adriano validou o cadastro completo dele no bot de dev pelo celular. **S1.5 (marca, perfil do bot e E2E simulado)** no PR #27 (`8ee82a7`, D034): a partir dela, **todo merge na `main` vai sozinho para produção** quando `deploy-dev` e `e2e` passam (primeira vez: execução 36890022856). Os textos legais estão publicados no Telegraph (D032). **Posicionamento revisto (D035)**: assistente financeiro **individual** com IA em destaque, em acesso antecipado por convite; lançamento público só depois dos pré-requisitos do PLANO, seção 16. O Adriano tem conta ativa em prod desde 01/10/2026 12:17.

### S4 — encerrada em 05/10/2026 (D043, D044; PRs #41, #43–#45, #47, #48, #50)

- **S4.1 — fixos** (PR #41, `4b6c4f2`, em prod; ajustes nos PRs #43–#45): `core/fixos.py` + migração **0006** (`fixed_items` isolada; `transactions.fixed_item_id`). Nasce pelo "Sim, todo mês" do recibo (cria na hora, com ⚙️ Ajustar e ↩️ Desfazer), por frase com recorrência ("aluguel 1500 todo dia 10" só cadastra; "paguei a internet 120 todo dia 5" lança e cadastra) e é gerido em `/fixos` (valor, dia, lembretes, fixo/estimado, pausar, apagar). Testes: `tests/unit/test_fixos.py` (calendário, recorrência, fixo x estimado), `tests/integration/test_fixos.py` (5, inclui isolamento), isolamento (fixo não aponta para categoria/forma de outra conta; lançamento não aponta para fixo de outra conta) e E2E (fixo por frase + ajustes).
- **S4.2 — lembretes** (D044; PR #47, `70f4314`; ajustes nos PRs #48 e #50; em prod): motor puro `core/lembretes.py` — por fixo ativo e no horário escolhido (09:00/20:00 São Paulo), **no máximo um** lembrete: "vence hoje", "vence amanhã" ou "venceu em dd/mm…" todo dia depois, até ✅ Paguei/Recebi ou ⏭️ Pular, e só até o próximo vencimento. Fixo cadastrado depois do vencimento não cobra aquele mês. Migração **0008**: `fixed_occurrences` (mês resolvido: pago/pulado + lançamento; única por fixo + vencimento) e `reminder_sends` (único por fixo + dia + horário; gravado **antes** de enviar; apagado com 60 dias), ambas ISOLADAS; `accounts_with_reminders()` (SECURITY DEFINER, só ids). ✅ Paguei lança `source = 'fixed'` ligado ao fixo e mostra o recibo de sempre; ✏️ Outro valor pergunta o valor — e, por 10 min, a próxima mensagem que for **só um valor** paga aquele vencimento mesmo sem responder (migração **0009**, PR #48); lançamento já ligado ao fixo no mesmo mês (ou até 7 dias antes) também resolve.
- **Lambda `rotinas`**: só manda lembretes quando quem chama é a agenda (`{"origem": "agenda"}` no Scheduler); a verificação do deploy invoca com `{}` e só limpa. **Em dev** aceita `{"momento": "2026-10-19T09:00"}` para simular outro dia/horário (comando em "Comandos úteis").
- **Áudio respondendo a perguntas** (PR #50): resposta por áudio a qualquer pergunta de fora dos lançamentos (valor do lembrete, valor/dia do fixo, nome) é transcrita em `conta.trata` antes de seguir; o dia do fixo aceita "dia doze".
- **Roteiro G** (`docs/ROTEIRO-TESTES.md`, 05/10/2026, agente pelo Telegram Web + áudio do Adriano): G1–G6 certos depois dos PRs #48 e #50; do roteiro saíram também a descrição com acentos ("Condominio" → "condomínio") e o "Outro valor" sem responder.
- **Testes**: `tests/unit/test_lembretes.py` (calendário: meses curtos, viradas de mês/ano, horário, resolução, mensagem, só a agenda lembra, `so_valor`), `tests/integration/test_lembretes.py` (rotina, botões, idempotência, Outro valor sem responder, isolamento), isolamento (tabelas novas + função), E2E pela rotina (`rotinas.lembra` com a Bot API simulada). CI: 467+ testes.

### S3 — encerrada em 05/10/2026 (D041, D042; PRs #36–#40, #43–#45)

- **S3.1 — áudio no bot** (PR #36, `d197494`, em prod): `voice`/`audio` do Telegram → `Entrada.audio` (duração, tamanho, formato, `baixar()` fornecido pelo canal) → `core/lancamentos.trata`: limites **antes** de baixar (≤ 2 min, ≤ 20 MB; `core/audio.py`) → download em memória (`TelegramAPI.baixa_arquivo`, para em 20 MB; o link com token nunca sai dali) → `ai/whisper.py` (cadeia `whisper-large-v3` → `whisper-large-v3-turbo`, `language=pt`, prompt com vocabulário) → a transcrição segue **como texto** (perguntas, correção de recibo, tudo). Recibo com "🎙️ «transcrição resumida»"; áudio que não vira recibo recebe "🎙️ Ouvi: «…»". "Digitando…" enquanto ouve. `ai/cadeia.py` agora é comum à extração e à transcrição. Migração **0005**: `ai_usage.audio_seconds` (medidor em segundos; aviso ao admin em 70% de 28.800 s/dia por modelo).
- **Avaliação dos áudios** (`scripts/avaliar_ia.py --audio [--modelo-audio ...]`; cache das transcrições): **whisper-large-v3: 100%** em intenção, valor, tipo, data e categoria nos 11 áudios reais; WER médio 14,9% (pior 25%), sem efeito no resultado. O workflow do CI ganhou o passo de áudio.
- **`whisper-large-v3-turbo` liberado** na allowlist pelo agente (Chrome, autorizado pelo Adriano em 02/10/2026) e avaliado: **100%**, WER 14,3%. A cadeia de áudio tem os dois modelos.
- **Testes**: unitários (Whisper, download, adaptador) + `tests/integration/test_audio.py` (10, Postgres real, transcritor falso: recibo, limites antes de baixar, falhas, eco, pergunta e correção por áudio, medidor) + E2E 18 (novo: áudio com "digitando…", recibo, correção, eco, recusa > 2 min; a Bot API simulada ganhou `getFile`, download e `sendChatAction`).

- **S3.2 — correções pela IA** (D042; PR #38, `5c7abd7`): o roteiro de voz do Adriano mostrou que o leitor de correções por código não entendia "foi na padaria, não foi no mercado". Agora a correção vai à IA (`Groq.corrige` → `CorrecaoIA`, prompt `REGRAS_CORRECAO` com o resumo do lançamento) e o código aplica: valor/data só se estiverem na frase, regra aprendida primeiro, ambíguo vira pergunta sem a categoria negada + "➕ Criar «…»" (`tx:nc`) + "🔎 Outra". Sem IA: o leitor por código (agora com as regras aprendidas). `tests/integration/test_correcao.py` (9). Não há ainda conjunto de avaliação de correções: juntar frases reais do Adriano quando aparecerem.
- **Correção, do jeito que a pessoa faz** (PRs #40, #44, #45): responder ao recibo **ou** à mensagem do ✏️ Corrigir corrige aquele lançamento; depois de tocar ✏️ Corrigir, a próxima mensagem (10 min, uma só, migração **0007**) também; frases que só podem ser correção ("na verdade", "na vdd", "não era", "errei", "corrige", "o certo é") vão direto para o **último lançamento mexido** (criado ou corrigido) nas últimas 24 h.
- **Roteiros** (`docs/ROTEIRO-TESTES.md`): 02, 03 e 05/10/2026 — áudio pelo Adriano no celular, texto pelo agente no Telegram Web. Tudo certo na última rodada (05/10), inclusive correção por áudio sem responder. Do roteiro saíram: "r pao" na descrição, saudação "texto ou áudio", telas de ajuste que se atualizam (`Saida.substitui` → `editMessageText`), ✏️ Corrigir que abre a resposta (`Saida.responder`), medição de tempo (`ia.chamada`, `update.processado` com `ms`; IA ~0,9 s, mensagem 0,9–1,5 s).

### S2 — encerrada em 02/10/2026 (D036–D040; PRs #30, #33, #34)

O Telegrana registra gastos, ganhos e transferências **por texto**, com IA, em dev e prod (produção publicada pelo pipeline do `93fdb3e` e do `be2df4b`). O roteiro de validação rodou no bot de dev pelo Telegram Web do Adriano (o adb não achou o celular): tudo certo, sem erro no CloudWatch.

- **Caminho de uma mensagem**: `core/entendimento.entende` → **atalho sem IA** (`core/atalho.py`: frases curtas com um valor e uma palavra-chave; "gastei no mercado" pergunta o valor) → senão **IA** (`ai/groq.py`) → `atalho.resgata` (lançamento claro que a IA deixou passar: total do mês lido como consulta, gasto sem valor) → `core/interpretacao.py` (o código decide: valores, datas, categoria só se existir na conta, regras da pessoa > ambíguos > regras de fábrica > IA, pendências) → `core/lancamentos.py`.
- **No bot** (`core/lancamentos.py` + `core/lancamentos_repo.py`): recibo com ✏️ Corrigir / 🏷️ Categoria / 🗑️ Apagar (↩️ Desfazer) — botões `tx:fix|cat|sc|del|un`; pendência vira rascunho (`pending_entries`, 1 dia) + pergunta (`lc:c|n|ok|x`, `lc_valor`, `lc_data`); criar categoria na hora; regra aprendida ("✅ Sempre", `rg:`); "é fixo?" (`fx:s|n` → `transactions.recurring`, para a S4); crédito e parcelas gravados antes da S5; correção **respondendo ao recibo** (`message_refs`, 30 dias). O bot **nunca** mostra texto livre da IA (D039). Comando desconhecido → `/ajuda`, que explica como registrar.
- **IA (D040)**: cadeia **gpt-oss-120b → qwen3.8-27b → gpt-oss-20b**, cada um com 200 mil tokens/dia próprios no plano gratuito (600 mil somados; uso pesado de 10 pessoas ≈ 145 mil). Limite (429), bloqueio (403/404), queda (5xx) ou resposta inválida passam para o seguinte; o esgotado fica de fora até o `retry-after`. Só com todos de fora a pessoa vê "muita demanda, manda de novo". qwen com `reasoning_effort: low` + `reasoning_format: hidden`; gpt-oss com `low` + `include_reasoning: false`. Timeout 15 s (Lambda 30 s). Sem chave do Groq, o atalho continua funcionando.
- **Medidor** (`ai_usage`, global, sem dado pessoal): tokens do dia por modelo; aviso ao admin quando um modelo passa de 70%.
- **Banco**: migrações 0003 (categorias, formas, lançamentos, regras) e 0004 (rascunhos, recibo↔lançamento, medidor, parcelas/recorrente, formas Crédito e Boleto, `UPDATE (category_id)` nas regras). Tudo ISOLADO com RLS forçado, exceto `ai_usage`.
- **Avaliação** (72 casos, conjunto privado no bucket; D036/D037/D040): **gpt-oss-120b 100%** e **qwen 100%** em intenção, valor, tipo, data e categoria; o **gpt-oss-20b** fez 19/72 (todos certos) e ficou inconclusivo por cota — completar com `--continuar`. `scripts/avaliar_ia.py --modelo <m>` + **cache de respostas** (`tests/eval/data/cache/`, fora do Git): mudou só código → reavaliação com 0 token. O workflow "Avaliação da IA" roda nos PRs que mexem na IA (dev key, OIDC só leitura, só métricas e ids no log).
- **Testes**: 234 unitários + integração contra Postgres real (fluxo de lançamentos com IA falsa, incluindo recibo/botão de outra conta) + **17 E2E**.
- **Uso local da chave de produção** nas avaliações: autorizado **só até a família começar a usar** a produção (D038 item 2).

### S2.1 — o que existe (D036)

- **Banco (migração 0003)**: `categories`, `payment_methods`, `transactions`, `category_rules` — ISOLADAS, RLS forçado, chaves estrangeiras **compostas** (testes provam que lançamento/regra não aponta para categoria de outra conta). Centavos `bigint`; `occurred_on`/`cash_on`; transferência sem categoria e com destino; `deleted_at`.
- **Padrões**: `telegrana.seed_account_defaults(conta)` (21 categorias com `code` estável + Pix, Débito, Dinheiro, Poupança). Roda ao concluir o cadastro; rodou na migração para as contas existentes (prod: 1 conta, 21 categorias, 4 formas, conferido em 01/10/2026).
- **`/categorias`** (`core/categorias.py`): criar (emoji + nome em qualquer ordem), renomear, trocar emoji, desativar/reativar; "Outros"/"Outros ganhos" fixas. Perguntas de edição levam a categoria na 2ª linha → `Entrada.contexto` (o adaptador extrai do `reply_to_message` do próprio bot).
- **Testes**: 217 no `pytest` padrão + 14 cenários de E2E (novo: categorias).

### S1.5 — o que existe (D034)

- **E2E simulado** (`tests/e2e/`, `uv run pytest -m e2e`): updates no formato do Telegram vão ao `bot.handler` real; `tests/e2e/telegram_simulado.py` faz a Bot API e **recusa** o que o Telegram recusaria (HTML inválido, > 4096 caracteres, botões malformados, `callback_data` > 64 bytes, chat inexistente, contato sem o teclado de contato, callback respondido duas vezes). 13 cenários (os 11 do critério da S1 + botão usado some + bloqueio). "Trocar de Telegram" = mesma pessoa com outro id. Fica fora do `pytest` padrão (marcador `e2e`); o CI roda no job `e2e`. **Motivo**: as contas de teste do servidor de testes do Telegram estão desativadas desde 06/2025 (tdlib/td#3370).
- **Pipeline**: `main` → `qualidade`/`testes`/`segredos` → `deploy-dev` e `e2e` → `deploy-prod` (automático). Cada deploy: build → migrações → stack → webhook → `perfil` (menu e descrições) → `verificar` (invoca as Lambdas).
- **Marca**: `scripts/marca.py` → `assets/brand/out/` (ícone 640…64 em PNG + `icon-640.jpg` para a foto do bot; `logo-full`, `logo-horizontal`, `logo-mono-white`; `previa.png`). Paleta em `src/telegrana/exports/brand.py`. Aprovada e aplicada nos dois bots (`deploy_tasks.py perfil --env <env> --foto`).
- **Menu de comandos**: geral para todos; o do admin (com `/admin`, `/link`, `/usuarios`) só aparece no chat dele **depois que ele conversar com o bot**. Em prod, o Adriano ainda não mandou `/start` ao @TelegranaAppBot (o deploy pula esse menu até lá).
- **Celular**: primeira captura via adb feita (só a conversa com o bot de dev; capturas apagadas depois). Roteiro antes de cada liberação para a família: ver Gotchas > Celular.

### S1.4 — o que existe (D033)

- **Fluxos**: bot privado com `🙋 Pedir acesso` / `🔄 Já tenho conta`; convite por link (`/link novo`); aprovação/recusa pelo admin; aceite dos termos (resumo com os dois destaques + links do Telegraph); cadastro nome → telefone (só o próprio) → maioridade → código de recuperação → pronto; recuperação por telefone, por código (`/entrar`) e manual pelo admin; `/meus_dados`, `/corrigir_nome`, `/termos`, `/codigo_novo`, `/apagar_conta` (confirmação dupla), `/ajuda`; admin: `/admin`, `/link`, `/link novo`, `/link revogar`, `/usuarios` (bloquear/desbloquear). Lançamentos ainda não: qualquer outra mensagem responde "chegam na próxima etapa".
- **Código**: `core/{mensagens,roteador,cadastro,conta,admin,repositorio,seguranca,textos,contexto}.py`, `channels/telegram/adaptador.py`, `infra/telegraph.py`, migração `0002_cadastro.sql`. **155 testes** (o fluxo inteiro roda contra Postgres real em `tests/integration/test_cadastro.py`).
- **SSM novos**: `/telegrana/<env>/phone/hmac_pepper` (SecureString; **nunca rotacionar**), `/telegrana/<env>/legal/{termos,privacidade}` (JSON da publicação), `/telegrana/<env>/admin/contact`, `/telegrana/telegraph_token` (SecureString; só para o script). A Lambda **não sobe** sem eles: num ambiente novo, rodar `ssm_setup.py` e `publicar_legal.py --contato <@ do admin>` antes do deploy.
- **Textos legais publicados** em 01/10/2026: Termos v1 e Política v1 no Telegraph (endereços no SSM). Mudou o texto depois de alguém aceitar? Criar `legal/<doc>-v2.md` e publicar; o bot pede novo aceite sozinho.

### S1.3 — o que existe (D031)

- **No ar**: stacks `telegrana-dev` e `telegrana-prod` (`deploy/app.yaml`), com Lambdas `telegrana-<env>-bot` (Function URL; webhook registrado no Telegram, `max_connections` 3) e `telegrana-<env>-rotinas` (agenda `telegrana-<env>-rotinas`, 09:00/20:00 America/Sao_Paulo, limpeza de retenção). Teste real: o Adriano mandou `/start` ao @TelegranaAppDevBot e recebeu a resposta. Produção publicada pela execução manual 36768116069 (01/10/2026, todos os jobs verdes); webhook do @TelegranaAppBot conferido (sem pendências nem erro).
- **Textos legais aprovados** (D032): `legal/termos-v1.md`, `legal/privacidade-v1.md` e `legal/registro-tratamento.md`, revisados com as skills jurídicas, com os marcadores `{{contato_admin}}` e `{{data_vigencia}}` preenchidos por `scripts/publicar_legal.py`.
- **Código**: `infra/config.py` (SSM, `repr=False`), `infra/logs.py` (silencia HTTP), `channels/telegram/api.py` (Bot API com httpx; erros sem token), `channels/telegram/webhook.py` (validação), `entrypoints/bot.py` e `entrypoints/rotinas.py`. **93 testes.**
- **SSM**: `/telegrana/admin_telegram_id`, `/telegrana/<env>/telegram/{bot_token,webhook_secret}`, `/telegrana/<env>/neon/{app_url,migrator_url}`. Gravar/rotacionar: `uv run python scripts/ssm_setup.py` (`--rotacionar-webhook`, `--rotacionar-banco-prod`). Os papéis do banco de **produção** foram criados; as senhas existem **só no SSM**. A migração 0001 foi aplicada em prod pelo pipeline.
- **Base** (`telegrana-bootstrap`): + limite `telegrana-limite-lambdas`, bucket `telegrana-artefatos-<conta>` (7 dias), papel de deploy com permissões mínimas e OIDC nos ambientes `dev`/`prod` do GitHub (restritos à `main`); kill-switch avisando também no Telegram.
- **Pipeline**: merge na `main` → `deploy-dev` automático. Produção: `gh workflow run CI --ref main -f prod=true` (automático depois do E2E da S1.5). Variáveis do repositório: `AWS_DEPLOY_ROLE_ARN`, `LAMBDA_BOUNDARY_ARN`, `ARTIFACT_BUCKET`. Action nova na lista permitida: `aws-actions/configure-aws-credentials`.
- **Scripts**: `build_lambda.py` (pacote linux arm64 via uv), `deploy_tasks.py` (`migrar`, `webhook`, `webhook-info`), `ssm_setup.py`, `db_bootstrap.py`.

### S1.2 — o que existe (D030)

- `src/telegrana/infra/db.py` (`connect` com TLS `verify-full` fora de localhost; `account_context` para o RLS), `bootstrap.py` (papéis), `migrate.py` (executor: `python -m telegrana.infra.migrate` com `TELEGRANA_MIGRATOR_URL`), `migrations/0001_fundacao.sql`.
- Esquema `telegrana`: **isoladas** (RLS forçado) `accounts`, `users`, `account_members`, `user_channels`, `terms_acceptances`; **globais** (por GRANT) `invite_links`, `access_requests`, `processed_updates`, `audit_log` (app: só INSERT), `schema_migrations`. Funções definer `resolve_identity` e `start_onboarding`.
- Testes: `tests/conftest.py` (fixture `banco`: cria banco descartável, papéis e migrações), `tests/isolation/test_isolamento.py` (isolamento cruzado + meta-testes), `tests/integration/test_migrate.py`. **51 testes**, localmente contra a branch `testes` do Neon e no CI contra o Postgres 18 do container.
- Neon: branch **`testes`** criada pelo agente (sem expiração; dono em `TELEGRANA_TEST_DATABASE_URL`); branch **`dev`** com papéis e migração 0001 (`NEON_APP_URL_DEV`, `NEON_MIGRATOR_URL_DEV`, rotacionáveis com `uv run python scripts/db_bootstrap.py dev`). **Produção: nada criado** (fica para a S1.3, pelo pipeline, com senhas no SSM).

### S1.1 — o que existe (D029)

- `pyproject.toml` (uv, Python 3.14 = runtime `python3.14` da Lambda), `uv.lock` com hashes. Por enquanto, nenhuma dependência de execução.
- Pacote `src/telegrana/{core,ai,channels/telegram,infra,exports}` só com os `__init__` (docstrings das camadas).
- Testes: `tests/unit/test_arquitetura.py` (núcleo agnóstico de canal), `tests/unit/test_check_setup.py` (mascaramento de segredos; toda variável marcada `SEGREDO` no modelo precisa estar em `SECRET_KEYS`), `tests/integration/test_postgres.py` (Postgres 18).
- CI `.github/workflows/ci.yml`: jobs **`qualidade`**, **`testes`** (Postgres 18 em container) e **`segredos`** (gitleaks). Os três são **checks obrigatórios** no ruleset `protege-main`.
- Actions: **só as permitidas** (as do GitHub, `astral-sh/setup-uv`, `gitleaks/gitleaks-action`) e **fixação por hash obrigatória** (`sha_pinning_required`). Uma action nova precisa entrar na lista (`gh api -X PUT repos/<repo>/actions/permissions/selected-actions`).
- CodeQL *default setup* ligado (Python + Actions). Dependabot semanal (uv + actions).
- pre-commit instalado na máquina: gitleaks (baixa o Go sozinho), ruff, higiene e a trava `bloqueia-dados-pessoais`. Guia em `docs/DESENVOLVIMENTO.md`.

`python scripts/check_setup.py` → **42 OK, 0 falhas, 1 pendente** (11 de 15 áudios de avaliação; não bloqueia).

### O que existe e onde

| Peça | Estado | Onde / como acessar |
|---|---|---|
| GitHub | repositório **público** `drizaogythub97/telegrana`; secret scanning, push protection, Dependabot (alerts, security updates, malware), private vulnerability reporting; Actions com `GITHUB_TOKEN` só leitura e aprovação obrigatória para PRs de fora; ruleset `protege-main` (id 24246219: PR obrigatório, sem force-push, sem apagar; **admin com bypass "always"**) | `gh` logado como `drizaogythub97` |
| AWS | **conta nova** (30/09/2026), **plano FREE**, **US$ 200 de créditos até 30/09/2027**; usuário IAM `adriano-dev` (MFA, AdministratorAccess + SignInLocalDevelopmentAccess, sem access keys); MFA na root; sem Organizations | perfil `telegrana` via `aws login --profile telegrana` (sessão ≤ 12 h; quem renova é o Adriano) |
| AWS — base | stack `telegrana-bootstrap` (`deploy/bootstrap.yaml`): orçamentos `telegrana-gasto-zero` (US$ 0,01) e `telegrana-teto-mensal` (US$ 1; créditos contam), SNS `telegrana-orcamento-estourado` (e-mail + Lambda) e `telegrana-avisos` (e-mail), Lambda `telegrana-kill-switch` (zera a concorrência das `telegrana-*`), OIDC do GitHub + papel `telegrana-github-deploy` (só `main`, **sem permissões ainda**) | e-mails de alerta confirmados |
| Neon | projeto `telegrana` (`aws-us-east-1`, **Postgres 18**), branches `production` e `dev` **sem expiração**; nada criado dentro do banco | `NEON_OWNER_URL_PROD`, `NEON_OWNER_URL_DEV` (papel dono, conexão direta), `NEON_API_KEY` (**Project-scoped**), `NEON_PROJECT_ID` — tudo no `.env.local` |
| Groq | Global ZDR ligado; allowlist: `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.8-27b`, `whisper-large-v3`, `whisper-large-v3-turbo` (qwen e turbo liberados em 02/10/2026); projetos `telegrana-prod` (limites cheios) e `telegrana-dev` (desde 05/10/2026: **4 mil tokens/min, 50 mil tokens/dia e 400 req/dia** em cada modelo de texto; Whisper v3 e turbo com 800 req/dia e 10.800 s/dia — D044). **Limites do plano gratuito são por modelo e por organização** (D040) | `GROQ_API_KEY_PROD`, `GROQ_API_KEY_DEV` |
| Telegram | produção **@TelegranaAppBot**, dev **@TelegranaAppDevBot** (fora de grupos, sem webhook); app de testes "Telegrana Testes" no my.telegram.org; admin = o Adriano | `TELEGRAM_BOT_TOKEN_{PROD,DEV}`, `TELEGRAM_BOT_USERNAME_{PROD,DEV}`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `ADMIN_TELEGRAM_ID` |
| Celular | Samsung Galaxy A54 (SM-A546E), **Android 16**, pareado por adb Wi-Fi, Telegram instalado | reconectar: `adb mdns services` → `adb connect IP:PORTA` |
| Avaliação da IA | 11 áudios reais do Adriano + `audios.txt` conferido; `mensagens.txt` com 61 frases humanizadas escritas pelo agente | `tests/eval/data/` (**fora do Git**) |
| Marca | `assets/brand/logo-original.png` (1254×1254, fundo branco; pode ser pública) | recortes na S1 |

### Entregas da S0 (PRs mesclados com squash)

| PR | Hash | Conteúdo |
|---|---|---|
| — | `fdba718` | estrutura, guias S0.1–S0.7, `check_setup.py`, D015–D020 |
| — | `d69da5c` | S0.1 concluída (push inicial, ruleset) |
| #1 | `d0ddb28` | logo no repositório e no README |
| #2 | `6a28b5f` | conta AWS nova no plano gratuito (D021) |
| #3 | `9563265` | WhatsApp como S9 (D022) |
| #4 | `1d9e8b0` | S0.2 concluída |
| #5 | `0c00ec0` | base AWS: orçamentos, kill-switch, OIDC (D023) |
| #6 | `1bef403` | chave Project-scoped do Neon (D024) |
| #7 | `a4dc3a1` | S0.3 concluída |
| #8 | `4f63986` | Groq: ZDR, allowlist, projetos (D025) |
| #9 | `98b7c19` | S0.4 concluída |
| #10 | `f87a40f` | inscrições SNS confirmadas |
| #11 | `c003b61` | S0.5 concluída |
| #12 | `29fd137` | S0.6 concluída |
| #13 | `1d7bbdf` | fix: celular duplicado no adb |
| #14 | `592c3a9` | créditos AWS completos (D026) |
| #15 | `811908d` | conjunto de avaliação (D027) |
| #16 | `7c67819` | encerramento da S0 (D028) |
| #17 | `a69e6e7` | **S1.1**: esqueleto, ferramentas de qualidade e CI (D029) |
| #18 | `ef38785` | encerramento da S1.1 |
| #19 | `d5caa19` | **S1.2**: banco com RLS forçado e suíte de isolamento (D030) |
| #20 | `07cd4db` | **S1.3**: Lambdas, segredos no SSM e deploy por OIDC (D031) |
| #21 | `3cd7733` | fix: OIDC com *sub* imutável do GitHub |
| #22 | `04f2c7f` | encerramento da S1.3 |
| #23 | `e3577f7` | Termos de Uso e Política de Privacidade v1 (D032) |
| #24 | `d6bd378` | **S1.4**: entrada, cadastro, recuperação e comandos (D033) |
| #25 | `8ae59fc` | fix: `CodeUri` em cada Lambda + verificação pós-deploy |
| #26 | `a664f35` | encerramento da S1.4 |
| #27 | `8ee82a7` | **S1.5**: marca, perfil do bot e E2E simulado (D034) |
| #28 | `15d2719` | encerramento da S1.5 e da S1 |
| #29 | `9e3bb0f` | posicionamento: assistente individual com IA; pré-requisitos do lançamento (D035) |
| #30 | `d4d600f` | **S2.1**: categorias e lançamentos no banco; `/categorias` (D036) |
| #31 | `6f06e5f` | encerramento da S2.1 |
| #32 | (fechado) | S2.2 — incorporado ao #33 |
| #33 | `93fdb3e` | **S2.2 + S2.3**: IA de extração, lançamentos no bot, atalho, medidor, cadeia de modelos (D037–D040) |
| #34 | `be2df4b` | qwen na cadeia + ajustes do roteiro de validação (D040) |
| #35 | `8f2087f` | encerramento da S2 |
| #36 | `d197494` | **S3.1**: lançamentos por áudio (D041) |
| #37 | `a7d12fa` | docs: turbo liberado e avaliado |
| #38 | `5c7abd7` | **S3.2**: correções interpretadas pela IA (D042) |
| #39 | `9bf7cac` | IA: espera curta no limite por minuto; CI sem disputar a cota |
| #40 | `0809ab0` | correção: responder ao ✏️ Corrigir; último das 24 h |
| #41 | `4b6c4f2` | **S4.1**: fixos (D043) |
| #42 | `8eef743` | test: espera do limite com tolerância |
| #43 | `3ba18c0` | ajustes do roteiro de 03/10 |
| #44 | `c8370ff` | correção pendente depois do ✏️ Corrigir (migração 0007) |
| #45 | `aab6f07` | correção sem responder: último mexido e frases de correção |
| #46 | `9075f4f` | encerramento da S3 |
| #47 | `70f4314` | **S4.2**: lembretes dos fixos (D044) |
| #48 | `d41d2bc` | "Outro valor" sem responder (migração 0009); descrição com acentos |
| #49 | `ef21e11` | Dependabot: boto3, mypy, ruff (dev) |
| #50 | `18a088f` | áudio respondendo às perguntas do lembrete e do fixo |
| #51 | (este) | encerramento da S4 |

## Ponto de partida exato da próxima sessão (S5 — cartão de crédito)

1. Ler os 5 documentos acima. `git pull`; `python scripts/check_setup.py`. `aws login --profile telegrana` é do Adriano (ver Gotchas > AWS se der 400 ou se nenhuma aba abrir).
2. **Antes de codar, perguntar ao Adriano de uma vez** (PLANO 4.5 deixa em aberto): (a) os cartões dele (nome, dia de fechamento e de vencimento — só os nomes e dias, nada de número de cartão); (b) o que fazer com as compras no crédito já lançadas desde a S2 (hoje são `transactions` com forma Crédito e `installments`, gravadas como gasto realizado na data da compra): migrar para parcelas na fatura do cartão ou deixar como estão; (c) se "no crédito" sem dizer o cartão deve perguntar qual (quando houver mais de um) ou usar o principal.
3. **S5 — proposta de divisão** (registrar numa D045 com o que o Adriano decidir):
   - **S5.1 — cartões e compras**: migração 0010 com `cards` (ISOLADA: nome único por conta, fechamento, vencimento, limite opcional, forma de pagamento ligada) e `card_installments` (ISOLADA: compra, número/total, valor em centavos — resto na 1ª parcela —, fatura de destino calculada pelo fechamento); "tênis 600 em 3x no Nubank" vira compra + parcelas (compromisso, não gasto realizado: **regime de caixa**); `/cartoes` para cadastrar e editar (mesmo padrão de `/fixos`); a IA/atalho já devolvem forma e parcelas — falta o nome do cartão.
   - **S5.2 — fatura**: fechamento automático pela rotina (mesma Lambda), lembrete do vencimento reaproveitando `core/lembretes.py` (o item passa a ser fixo **ou** fatura), ✅ Paguei a fatura (total ou outro valor) → cada item vira gasto realizado na data do pagamento com a própria categoria; pagamento parcial → "Saldo anterior" na próxima; juros/multa em 💸 Encargos; estorno.
   - **S5.3 — E2E, roteiro (bloco H) e produção.**
   - Testes de borda obrigatórios (PLANO): compra no dia do fechamento, fechamento 31 em mês curto, 12x atravessando o ano, centavos da divisão, pagamento parcial, estorno de compra parcelada, isolamento de cartão/parcela entre contas.
4. Seguir o protocolo de sempre: branch → PR → CI verde → merge (vai sozinho para prod) → roteiro (agente por texto no Telegram Web; áudios com o Adriano) → encerramento.

## Pendências do Adriano

- **Decidir se troca a senha do papel dono da branch de testes do Neon** (a da `TELEGRANA_TEST_DATABASE_URL`): em 05/10/2026 uma falha de teste imprimiu essa URL na saída do pytest local (só na sessão do agente; nada em Git, log ou CI). O `repr` foi corrigido; a troca pode ser feita pelo agente via API do Neon, gravando direto no `.env.local`.

- **Quando a família começar a usar a produção** (D038 item 2): parar de usar a chave de produção nas avaliações locais (os tetos do `telegrana-dev` já estão aplicados desde 05/10/2026).

- Opcional: mais 4 a 9 áudios (a voz da esposa, com o consentimento dela) em `tests/eval/data/audios/`, mais as linhas correspondentes em `audios.txt`.
- Quando der: testar o convite com um segundo Telegram de verdade (ex.: o da esposa), para ver as telas do convidado.
- ⏰ **Até 30/03/2027: upgrade da conta AWS para o plano pago** (senão a conta é fechada; provavelmente foi o que aconteceu com a conta antiga). O agente deve lembrar a partir de 01/2027 e só fazer com o kill-switch testado.

## Perguntas em aberto

1. CloudTrail: basta o *Event history* (grátis, 90 dias) ou criar uma trilha em S3 (centavos, cobertos pelos créditos)? Recomendação do agente: só o Event history na V1. Confirmar com o Adriano na S1.3.
2. ~~Como o CI roda a avaliação da IA sem publicar os dados~~ — decidido na D036 (bucket privado + OIDC só leitura + log só com métricas).

## Gotchas (acumulados)

**Fluxo com CI (desde a S1.1)**
- O admin tem bypass no ruleset, mas **não o use**: sempre branch → PR → esperar `qualidade`, `testes` e `segredos` verdes → `gh pr merge --squash`. Leia o CI com `mcp__ccd_pr__get_status` e confirme uma vez com `gh pr checks <n>`, sem ficar consultando em laço.
- Arquivos gravados pelo Python no Windows saem com CRLF, e o hook `mixed-line-ending` interrompe o commit ao corrigir. Grave com `write_text(..., newline="\n")` ou refaça o `git add` e o commit.
- O `uv` não está no PATH do Git Bash: use `~/AppData/Roaming/Python/Python314/Scripts/uv.exe`.

**IA e Groq (S2)**
- Com os tetos de dev (D044), a avaliação do CI (cadeia, sem cache, ~90 mil tokens) cabe **uma vez por dia**: a segunda rodada sai INCONCLUSIVA por cota. Não é check obrigatório; refaça no dia seguinte (`workflow_dispatch`).
- **Limites por modelo E por organização** (dev + prod juntos): 200 mil tokens/dia, 1.000 req/dia, 8 mil tokens/min por modelo no plano gratuito. A Política de Uso Aceitável do Groq **proíbe** criar outras contas ou organizações para somar limites — não proponha isso. A folga vem da cadeia de modelos (D040).
- Uma avaliação completa gasta ~45–50 mil tokens do modelo avaliado. Use o **cache** (padrão) e `--casos` enquanto ajusta; `--sem-cache` só quando quiser medir a variação do modelo.
- Desde o PR #36 o CI avalia a **cadeia** (`--modelo cadeia`), como o bot: fica inconclusivo só se todos os modelos esgotarem. Local, use `--modelo <um>` (com cache) para comparar modelos.
- O workflow "Avaliação da IA" sai **INCONCLUSIVA (código 2)** quando a cota do modelo acaba — aparece como check vermelho, mas **não é obrigatório**. Leia o log: se as métricas avaliadas estão acima da meta, não é regressão (foi o caso do PR #34). Melhoria possível: tratar o código 2 como aviso.
- O modelo varia entre rodadas mesmo com temperatura 0 (ex.: t14 errou a categoria no CI e acertou no local). Sempre que possível, regra no **código** > instrução no prompt.
- qwen com `reasoning_effort: none` repete até estourar `max_completion_tokens` (HTTP 400 `json_validate_failed`): use `low`.
- Diagnóstico de caso que falhou: **local**, lendo o cache (0 token) — nunca imprimir frases do conjunto no CI.
- Heredoc no Git Bash: `\\b` dentro de `'EOF'` vira o caractere de controle 0x08 numa regex (erro silencioso, aconteceu duas vezes). Para editar Python com regex ou barras invertidas, gravar o script com a ferramenta Write e executar o arquivo.
- O Neon pode derrubar a conexão no meio da suíte longa ("server closed the connection unexpectedly"): rode de novo os arquivos afetados antes de investigar. A integração do fluxo de lançamentos leva ~5–6 min contra o Neon.
- Migração ainda **não aplicada** em dev/prod (só na branch) pode ser editada; depois do merge, nunca (checksum) — crie outra.
- O repositório **não permite auto-merge**: mesclar à mão quando o CI passar.

**Testes e E2E (S1.5)**
- **O servidor de testes do Telegram não serve mais**: as contas `99966XYYYY` estão desativadas desde 06/2025 (o pedido de código funciona, mas `22222`/`222222` dão `PHONE_CODE_INVALID`). Não tente de novo sem notícia oficial de que voltou (D034).
- O E2E fica fora do `pytest` padrão (`addopts -m "not e2e"`): rode `uv run pytest -m e2e`. Usa o banco descartável da sessão: ~3 min contra o Neon (`testes`), ~1 min no CI.
- Erro de log em nível ERROR durante o E2E derruba o teste no fim (handler `_Erros`): uma exceção engolida pelo `bot.handler` não passa despercebida.

**Celular (adb)**
- Se `adb devices` vier vazio, a depuração Wi-Fi do celular está desligada (ou ele está no outro roteador): peça ao Adriano para ligar, ou valide pelo Telegram Web.
- `adb mdns services` acha o celular já pareado (`_adb-tls-connect`); `adb connect IP:PORTA`. A porta muda a cada vez.
- `am start -d "tg://resolve?domain=..."` **abre a lista de conversas**, não o chat: não leia nada além do necessário; toque na conversa do bot (`input tap`) e só então capture. Apague as capturas do scratchpad depois de conferir.
- Roteiro antes de liberar para a família: no bot de **dev**, desligar a identidade do Adriano no banco de dev (`update telegrana.user_channels set external_id = '1' || external_id where external_id = '<id>'`, com `NEON_MIGRATOR_URL_DEV`) → ele vê "bot privado" → **ele** toca "Já tenho conta" > "Pelo meu número" (compartilhar o número é dele) → conta recuperada. Capturar as telas.

**Máquina do Adriano (fora do app do Claude)**
- O app do Claude no Windows é MSIX: o que o agente instala em `AppData` vai para `C:\Users\adria\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\...` e **o PowerShell do Adriano não vê**. O `uv` dele é `& "C:\Users\adria\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Python\Python314\Scripts\uv.exe"`. Ao passar um comando para ele rodar, use esse caminho completo.

**Repositório e privacidade**
- O nome é **Telegrana**, não "TeleGrana".
- Repositório **público**. Nunca commitar `.env.local`, nada de `tests/eval/data/`, capturas do celular ou `*.session` do Telethon. **O Adriano já colocou dados numa pasta não ignorada uma vez** (`tests/audios testes/`): sempre `git status` antes de commitar.
- Commits com a identidade local `Adriano Cardoso <225630126+drizaogythub97@users.noreply.github.com>`; o e-mail global da máquina é pessoal.
- A `main` exige PR (o admin passa por cima). Fluxo usado na S0: branch → PR → `gh pr merge --squash --delete-branch`.

**Máquina (Windows)**
- AWS CLI 2.37.6 e SAM CLI 1.166.2 foram instalados **depois** do início da sessão do agente. No PowerShell do agente, recarregar o PATH: `$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")`.
- Python 3.14; `uv` 0.12 em `%APPDATA%\Python\Python314\Scripts\uv.exe` (fora do PATH do Git Bash). Docker **não** instalado (D018).
- Heredoc no Git Bash quebra com muitas crases seguidas: gravar o script Python no scratchpad e executar o arquivo.
- adb 37.0.1 em `C:\Users\adria\AppData\Local\Android\Sdk\platform-tools`, mDNS ativo. **A casa tem dois roteadores**: o PC fica no modem (`192.168.15.x`); o celular precisa estar no Wi-Fi do modem. O mesmo celular pode aparecer duas vezes no `adb devices` (manual + mDNS); o `check_setup` já agrupa pelo número de série. Samsung: se o adb recusar comandos, desativar o "Bloqueador automático".

**AWS**
- Conta nova: **só 5 execuções simultâneas de Lambda no total**; não dá para reservar concorrência por função (zerar funciona). Orçamentos com `IncludeCredit: false`: na S9, subir o teto antes de ligar a EC2, senão o kill-switch dispara.
- `aws login` dura no máximo 12 h. Se o SAM não aceitar essas credenciais, usar o perfil ponte com `credential_process` (guia S0.2).
- Bedrock nesta conta: "Operation not allowed" no plano gratuito (testado de novo em 02/10/2026 com `openai.gpt-oss-20b-1:0`). Reserva paga possível depois do upgrade (D040).
- Git Bash + AWS CLI: caminhos do SSM (`/telegrana/...`) viram `C:/Program Files/Git/telegrana/...`; prefixe com `MSYS_NO_PATHCONV=1`.
- Recursos criados por API/IaC contam para as atividades de crédito (D026). API útil: `aws freetier get-account-plan-state` / `list-account-activities`.

**Deploy (S1.4)**
- O `aws cloudformation package` do CI **não lê os `Globals` do SAM**: `CodeUri` precisa estar em cada função, senão ele empacota a pasta `deploy/` e a Lambda sobe vazia (`Runtime.ImportModuleError`). Foi o que deixou a produção fora do ar entre a S1.3 e o PR #25. O pipeline agora roda `deploy_tasks.py verificar` (bot sem segredo → 401; rotina roda) e falha se a Lambda não importar.
- A Lambda não sobe sem os parâmetros novos do SSM (pepper, `legal/*`, `admin/contact`). Ambiente novo: `ssm_setup.py` e `publicar_legal.py --contato @...` **antes** do primeiro deploy.
- Teste rápido sem celular: mandar um update sintético assinado com o segredo do webhook para a Function URL, com `from.id` inexistente (o bot processa e só falha ao responder: "chat not found"). Nunca imprimir o segredo.
- Os logs do bot registram só rótulos técnicos (`cadastro.nome`, `admin.link.novo`...): para ver o que um teste fez, resuma os eventos `update.processado` do CloudWatch.

**AWS (S1.3)**
- **OIDC do GitHub**: este repositório emite o *sub* no formato **imutável** (`repo:drizaogythub97@225630126/telegrana@1397881731:environment:<env>`). Uma confiança com `repo:dono/repo` faz a `configure-aws-credentials` ficar tentando **em silêncio**, sem mensagem de erro. Conferir com `gh api repos/<repo>/actions/oidc/customization/sub`.
- AWS CLI no Windows: exportar `AWS_CLI_FILE_ENCODING=UTF-8` para ler templates com acento ou emoji (senão dá erro de `charmap`).
- boto3 no Windows: use o perfil `telegrana-sdk` (o `credential_process` chama `aws.exe` pelo caminho completo). O perfil `telegrana` sozinho exige `awscrt`.
- O deploy manual daqui usa o `sam deploy`; o CI usa `aws cloudformation package/deploy`. Os dois leem `deploy/app.yaml` com `CodeUri: ../.build/lambda`: rode antes `scripts/build_lambda.py`.
- A conta tem 5 Lambdas simultâneas: não use concorrência reservada nas funções.

**Neon**
- Papéis criados por SQL recebem senha longa (`token_urlsafe(32)`). O executor de migrações roda arquivos com várias instruções: passe **bytes** ao `execute` (protocolo simples); `str` não literal dá erro de tipo no mypy.
- Os testes criam e apagam bancos `telegrana_t_*` na branch `testes`. Se um teste for interrompido, pode sobrar um banco: `DROP DATABASE ... WITH (FORCE)` com o dono da branch.
- A branch principal se chama `production`. Toda branch nova vem com **expiração de 1 dia** por padrão (desligar sempre).
- A chave Project-scoped **não lista projetos**: use `GET /api/v2/projects/{NEON_PROJECT_ID}`. Chave pessoal é recusada pelo check (a primeira tentativa do Adriano gerou uma, que foi revogada).
- Papéis criados por SQL não recebem `neon_superuser` (bom para `app`/`migrator`). `BYPASSRLS` só via `neon_superuser`. A senha de papel criado por SQL exige 60 bits de entropia.
- TLS no Windows: usar `certifi` com `verify-full` (o `sslrootcert=system` não é confiável). Na Lambda, avaliar.
- Não usar o "Agent prompt" nem o "Onboard your agent" do Neon (D024).

**Groq**
- Limites por modelo e por organização; o teto do projeto dev protege a produção (D025, D038 item 2). O console cria a chave no **projeto selecionado no topo**. Modelo novo: liberar em Settings → Limits → **Allowed Models** → Edit (sem isso, HTTP 403 "blocked at the organization level").
- O `check_setup` descobre o projeto da chave pelo cabeçalho `x-ratelimit-limit-requests` (1000 = prod, 400 = dev), gastando uns 100 tokens.

**Telegram**
- O primeiro `/start` de 30/09 (14:02) sumiu da fila do bot de dev sem explicação (0 pendentes, sem webhook, sem outro consumidor). Se acontecer de novo, suspeitar de vazamento do token → `/revoke`.
- Telethon **só** no servidor de testes, com contas `99966XYYYY` (código = número do DC repetido 5 vezes); Bot API de teste em `/bot<token>/test/<método>`. Nunca logar a conta real do Adriano.
- Deep link: `start` com até 64 caracteres (`A-Z a-z 0-9 _ -`). Contato compartilhado: só se `contact.user_id == from.id`.

**Navegador (Claude in Chrome)**
- Logins com senha ou código são **sempre** do Adriano; o agente assume depois.
- Para passar um segredo da tela ao `.env.local` sem expô-lo: JS copia para a área de transferência dentro de um listener de clique **real**; o PowerShell grava com regex e limpa a área de transferência.
- Páginas que usam `alert()` travam a extensão: sobrescrever `window.alert` antes de enviar formulários (my.telegram.org).
- **Telegram Web** (`web.telegram.org/a/`, logado na conta do Adriano): abrir **só** o chat do bot de dev; o primeiro clique na lista às vezes abre outro chat (o layout muda ao carregar) — confira o título antes de digitar. Responder a uma mensagem: botão direito → "Reply" (o menu demora a aparecer; tire uma captura antes de clicar). Os testes ficam na conta de dev do Adriano.
- GitHub Advanced Security e Groq não atualizam a página depois de um clique: confirmar pela API/texto antes de clicar de novo. Campos numéricos do Groq formatam "8.000": digitar o número cru e conferir o valor salvo.

**Lembretes e rotina (S4)**
- Testar lembretes em dev sem esperar o dia: `aws lambda invoke --function-name telegrana-dev-rotinas --payload '{"momento": "2026-10-19T09:00"}' --cli-binary-format raw-in-base64-out --profile telegrana saida.json` (só dev; grava `reminder_sends` com a data simulada, então aquele dia/horário real não repete o lembrete em dev).
- A verificação do deploy invoca a `rotinas` com `{}`: ela **não** pode mandar mensagem a ninguém — só a agenda (`{"origem": "agenda"}`) lembra.
- **Telegram Web não abre a resposta sozinho** (force reply): todo fluxo que pergunta algo precisa funcionar também com a resposta solta (marca de 10 min, como no ✏️ Corrigir e no ✏️ Outro valor). No celular a resposta abre sozinha — e aí a resposta chega como `pergunta`, inclusive por áudio (transcrito em `conta.trata`).

**GitHub Actions (05/10/2026)**
- Job parado em `queued` por muitos minutos com o GitHub "operacional": `gh run cancel <run>` e `gh run rerun <run> --job <id do job>`. PR cujo CI não disparou: `gh pr close <n>` + `gh pr reopen <n>`.

**AWS e Windows**
- `aws login --profile telegrana --remote` **não abre aba**: imprime o link e espera o código. O painel de terminal do app falha na integração; abra uma janela própria: `Start-Process pwsh -ArgumentList '-NoExit','-NoProfile','-Command','aws login --profile telegrana --remote'`. A tela pede o ID da conta (está no `login_session` do perfil em `~/.aws/config`).
- No Git Bash, caminhos como `/aws/lambda/...` viram caminhos do Windows: prefixe `MSYS_NO_PATHCONV=1` (ex.: `aws logs filter-log-events --log-group-name /aws/lambda/telegrana-dev-bot ...`).
- Testes com o Neon de testes podem levar 10+ min (rede lenta em 05/10/2026); o CI usa Postgres local e roda tudo em segundos. A fixture `Banco` não mostra as URLs no `repr` (uma falha de teste não pode imprimir senha).

## Comandos úteis

```powershell
python scripts/check_setup.py                   # tudo
python scripts/check_setup.py s0.3 s0.4         # só algumas fases
python scripts/check_setup.py --descobrir-admin-id
aws login --profile telegrana                   # (Adriano) renova a sessão AWS
aws freetier get-account-plan-state --profile telegrana --region us-east-1
aws sns list-subscriptions --profile telegrana
adb mdns services ; adb connect IP:PORTA ; adb devices -l
```

# HANDOFF.md — Telegrana

> Atualizado em 01/10/2026 · S0 encerrada · S1.1–S1.4 encerradas · Próxima: **S1.5 — E2E no servidor de testes e marca**.
> **Repositório público (D015): nada de segredo nem dado pessoal neste arquivo.** Segredos: só o nome da variável e onde ela mora.

## Leia nesta ordem

1. `CLAUDE.md` — regras permanentes (segurança, regras de ouro, protocolo de encerramento).
2. Este arquivo.
3. `docs/PLANO.md` — fonte da verdade. Revisões datadas de 29 e 30/09/2026; a seção 15 descreve o WhatsApp (S9).
4. `docs/DECISOES.md` — D001 a D028. As mais recentes mudam bastante o plano original: D015 (repositório público), D017 (acesso por `aws login`), D021/D026 (conta AWS nova com créditos), D022 (WhatsApp), D023 (base AWS), D024 (Neon), D025 (Groq), D027/D028 (avaliação da IA).
5. `deploy/README.md` — base da conta AWS e como religar depois do kill-switch.

## Estado atual

A S1 foi dividida em 5 micro-fases (aceito pelo Adriano em 30/09/2026). **S1.1 (esqueleto e CI)** concluída no PR #17 (`a69e6e7`); **S1.2 (banco)** no PR #19 (`d5caa19`); **S1.3 (infra e webhook)** no PR #20 (`07cd4db`). **S1.4 (entrada, cadastro, recuperação, comandos de conta e de admin)** no PR #24 (`d6bd378`, D033), com a correção do deploy no PR #25 (`8ae59fc`). **No ar em dev e prod** (produção publicada pela execução 36867652126 em 01/10/2026). O Adriano validou o cadastro completo dele no bot de dev pelo celular; o caminho de **um segundo usuário** (convite, pedido de acesso, aprovação) está coberto pelos testes de integração, mas ainda não foi visto num Telegram real: fica para o E2E da S1.5. Os textos legais estão publicados no Telegraph (D032).

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
| Groq | Global ZDR ligado; allowlist: `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `whisper-large-v3`; projetos `telegrana-prod` (limites cheios) e `telegrana-dev` (400 req/dia e 80 mil tokens/dia por gpt-oss; Whisper 800 req/dia e 10.800 s/dia) | `GROQ_API_KEY_PROD`, `GROQ_API_KEY_DEV` |
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
| #26 | (este) | encerramento da S1.4 |

## Ponto de partida exato da próxima sessão (S1.5 — E2E e marca)

1. Ler os 5 documentos acima. `git pull`; conferir que a `main` está limpa.
2. `python scripts/check_setup.py`. Se a AWS acusar sessão expirada, pedir ao Adriano: `aws login --profile telegrana`. No PowerShell do agente, recarregar o PATH antes de chamar `aws`/`sam` (ver Gotchas).
3. Divisão da S1 (aceita em 30/09/2026). **Começar pela S1.5**; S1.1–S1.4 estão feitas:
   - ~~**S1.1 — Esqueleto e CI**~~ ✅ PR #17: `pyproject.toml` com `uv` (lock com hashes), `ruff`, `mypy --strict` no núcleo, `pytest`, `bandit`, `pip-audit`, gitleaks no pre-commit e no CI; workflow do GitHub Actions com Postgres 18 em *service container* (D018); CodeQL; `dependabot.yml`; depois, acrescentar os *required status checks* ao ruleset `protege-main`.
   - ~~**S1.2 — Banco**~~ ✅ PR #19: ferramenta de migração (decidir e registrar: SQL versionado com runner próprio vs. Alembic); papéis `migrator` e `app` (criados por SQL com as strings do dono; senhas no SSM); esquema inicial com `accounts`, `users`, **`user_channels`** (D022; nada de `telegram_id` fixo), `account_members`, `terms_acceptances`, `invite_links`, `access_requests`, `processed_updates`, `recovery_codes`, `audit_log`; **RLS forçado** e chaves compostas; **suíte de isolamento** desde o primeiro teste.
   - ~~**S1.3 — Infra e webhook**~~ ✅ PR #20. Além do que está abaixo: bootstrap de papéis e migrações da **produção** pelo pipeline (senhas geradas e gravadas no SSM; `TELEGRANA_MIGRATOR_URL` lido do SSM no job de deploy); a Lambda usa `telegrana_app`. Confirmar antes que a sessão `aws login` do Adriano esteja ativa.
   - Itens originais da S1.3: template SAM com Lambdas `bot` e `rotinas`, Function URL, SSM SecureString, logs com 7 dias; permissões mínimas do papel `telegrana-github-deploy`; bucket de artefatos do SAM (decidir: custo de centavos coberto pelos créditos, com ciclo de vida curto); `setWebhook` com secret token, `allowed_updates` mínimo, **`max_connections` ≤ 3** (D023) e `drop_pending_updates`; kill-switch avisando no Telegram.
   - ~~**S1.4 — Entrada e cadastro**~~ ✅ PRs #24 e #25. Histórico do que se pediu: O webhook já entrega updates validados e deduplicados em `entrypoints/bot.py::_processa`; o cadastro entra aí, com a lógica no `core/` (agnóstico de canal) e a formatação/teclados em `channels/telegram/`. Usar `resolve_identity`/`start_onboarding` e `db.account_context`. O pepper do HMAC do telefone vai para o SSM (`/telegrana/<env>/phone/hmac_pepper`, gerado por `ssm_setup.py`). Dependência nova provável: `argon2-cffi` (código de recuperação). **Obrigações que os textos legais criaram para o código estão em D032** (tela de aceite com dois destaques, aviso antes do pedido de acesso, limpeza de cadastros incompletos em 7 dias, `audit_log` sem dado pessoal e apagado na exclusão, exportação manual até existir `/exportar`). Itens do plano: `/start` com convite, pedido de acesso, termos (rascunhos em `legal/` para o Adriano aprovar; conta do Telegraph pela API), cadastro mínimo como máquina de estados, código de recuperação (Argon2id), recuperação em 3 níveis, comandos de privacidade e de admin.
   - **S1.5 — E2E e marca** (próxima): bot no **servidor de testes** do Telegram (Telethon, contas `99966XYYYY`) cobrindo os cenários do critério de pronto da S1; recortes da logo (prévias para o Adriano); primeira captura no celular via adb (com autorização). **O agente não cria contas nem digita códigos de login**: preparar um script que o **Adriano roda uma vez** no terminal dele para criar as contas de teste (e o bot de teste no BotFather do servidor de testes) e salvar as sessões em arquivos `*.session` (já no `.gitignore`); daí em diante o E2E roda sozinho. O bot de teste precisa de ambiente próprio (token no SSM, `TelegramAPI(test_server=True)`, webhook próprio). Primeiro cenário a cobrir: **segundo usuário entrando por convite e por pedido de acesso** (ainda não visto num Telegram real).
4. Antes de cada escolha técnica nova (runtime da Lambda: conferir se já existe `python3.14`; biblioteca de migração; versão do SAM), **pesquisar a documentação oficial** e registrar em DECISOES.md.

## Pendências do Adriano

- Revisar a lista de **categorias padrão** (PLANO 4.2) e responder pelo chat. Não bloqueia a S1; é necessário antes da S2.
- Opcional: mais 4 a 9 áudios (a voz da esposa, com o consentimento dela) em `tests/eval/data/audios/`, mais as linhas correspondentes em `audios.txt`.
- S1.5: rodar uma vez o script de criação das contas do servidor de testes (o agente prepara); aprovar as prévias dos recortes da logo.
- Quando der: testar o convite com um segundo Telegram de verdade (ex.: o da esposa), para ver as telas do convidado.
- ⏰ **Até 30/03/2027: upgrade da conta AWS para o plano pago** (senão a conta é fechada; provavelmente foi o que aconteceu com a conta antiga). O agente deve lembrar a partir de 01/2027 e só fazer com o kill-switch testado.

## Perguntas em aberto

1. CloudTrail: basta o *Event history* (grátis, 90 dias) ou criar uma trilha em S3 (centavos, cobertos pelos créditos)? Recomendação do agente: só o Event history na V1. Confirmar com o Adriano na S1.3.
2. Como o CI roda a avaliação da IA sem publicar os dados (D016): decidir na S2.

## Gotchas (acumulados)

**Fluxo com CI (desde a S1.1)**
- O admin tem bypass no ruleset, mas **não o use**: sempre branch → PR → esperar `qualidade`, `testes` e `segredos` verdes → `gh pr merge --squash`. Leia o CI com `mcp__ccd_pr__get_status` e confirme uma vez com `gh pr checks <n>`, sem ficar consultando em laço.
- Arquivos gravados pelo Python no Windows saem com CRLF, e o hook `mixed-line-ending` interrompe o commit ao corrigir. Grave com `write_text(..., newline="\n")` ou refaça o `git add` e o commit.
- O `uv` não está no PATH do Git Bash: use `~/AppData/Roaming/Python/Python314/Scripts/uv.exe`.

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
- Bedrock nesta conta: "Operation not allowed" (bloqueio de conta nova). Não usamos.
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
- Limites **por organização**; o teto do dev protege a produção (D025). O console cria a chave no **projeto selecionado no topo**. Para usar um modelo novo (ex.: `llama-prompt-guard-2` na S2), liberar antes na allowlist.
- O `check_setup` descobre o projeto da chave pelo cabeçalho `x-ratelimit-limit-requests` (1000 = prod, 400 = dev), gastando uns 100 tokens.

**Telegram**
- O primeiro `/start` de 30/09 (14:02) sumiu da fila do bot de dev sem explicação (0 pendentes, sem webhook, sem outro consumidor). Se acontecer de novo, suspeitar de vazamento do token → `/revoke`.
- Telethon **só** no servidor de testes, com contas `99966XYYYY` (código = número do DC repetido 5 vezes); Bot API de teste em `/bot<token>/test/<método>`. Nunca logar a conta real do Adriano.
- Deep link: `start` com até 64 caracteres (`A-Z a-z 0-9 _ -`). Contato compartilhado: só se `contact.user_id == from.id`.

**Navegador (Claude in Chrome)**
- Logins com senha ou código são **sempre** do Adriano; o agente assume depois.
- Para passar um segredo da tela ao `.env.local` sem expô-lo: JS copia para a área de transferência dentro de um listener de clique **real**; o PowerShell grava com regex e limpa a área de transferência.
- Páginas que usam `alert()` travam a extensão: sobrescrever `window.alert` antes de enviar formulários (my.telegram.org).
- GitHub Advanced Security e Groq não atualizam a página depois de um clique: confirmar pela API/texto antes de clicar de novo. Campos numéricos do Groq formatam "8.000": digitar o número cru e conferir o valor salvo.

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

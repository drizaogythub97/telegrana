# HANDOFF.md — Telegrana

> Atualizado em 01/10/2026 · S0, S1 e S2.1 encerradas · **S2.2 em andamento (PR #32 aberto, falta a avaliação passar)**.
> **Repositório público (D015): nada de segredo nem dado pessoal neste arquivo.** Segredos: só o nome da variável e onde ela mora.

## Leia nesta ordem

1. `CLAUDE.md` — regras permanentes (segurança, regras de ouro, protocolo de encerramento).
2. Este arquivo.
3. `docs/PLANO.md` — fonte da verdade. Revisões datadas de 29 e 30/09/2026; a seção 15 descreve o WhatsApp (S9).
4. `docs/DECISOES.md` — D001 a D028. As mais recentes mudam bastante o plano original: D015 (repositório público), D017 (acesso por `aws login`), D021/D026 (conta AWS nova com créditos), D022 (WhatsApp), D023 (base AWS), D024 (Neon), D025 (Groq), D027/D028 (avaliação da IA).
5. `deploy/README.md` — base da conta AWS e como religar depois do kill-switch.

## Estado atual

A S1 foi dividida em 5 micro-fases (aceito pelo Adriano em 30/09/2026). **S1.1 (esqueleto e CI)** concluída no PR #17 (`a69e6e7`); **S1.2 (banco)** no PR #19 (`d5caa19`); **S1.3 (infra e webhook)** no PR #20 (`07cd4db`). **S1.4 (entrada, cadastro, recuperação, comandos de conta e de admin)** no PR #24 (`d6bd378`, D033), com a correção do deploy no PR #25 (`8ae59fc`). **No ar em dev e prod** (produção publicada pela execução 36867652126 em 01/10/2026). O Adriano validou o cadastro completo dele no bot de dev pelo celular. **S1.5 (marca, perfil do bot e E2E simulado)** no PR #27 (`8ee82a7`, D034): a partir dela, **todo merge na `main` vai sozinho para produção** quando `deploy-dev` e `e2e` passam (primeira vez: execução 36890022856). Os textos legais estão publicados no Telegraph (D032). **Posicionamento revisto (D035)**: assistente financeiro **individual** com IA em destaque, em acesso antecipado por convite; lançamento público só depois dos pré-requisitos do PLANO, seção 16. O Adriano tem conta ativa em prod desde 01/10/2026 12:17.

### S2.2 — em andamento (D037, PR #32 ainda NÃO mesclado)

- **Pronto no PR #32** (CI de código verde esperado): contrato estrito `core/extracao.py`, `ai/prompt.py`, `ai/groq.py`, `core/valores.py`, `core/datas.py`, `core/interpretacao.py`, `scripts/avaliar_ia.py`, `scripts/avaliacao_dados.py`, `.github/workflows/avaliacao.yml`. O bot ainda **não** chama a IA (isso é a S2.3).
- **Já aplicado fora do Git**: stack `telegrana-bootstrap` com o bucket `telegrana-avaliacao-<conta>` e o papel `telegrana-github-avaliacao`; ambiente GitHub `avaliacao` e variáveis `EVAL_ROLE_ARN`/`EVAL_BUCKET`; `/telegrana/<env>/groq/api_key` no SSM; conjunto (gabarito + frases + áudios) enviado ao bucket; teto do projeto `telegrana-dev` do Groq em **150 mil tokens/dia** no `gpt-oss-20b` (autorizado pelo Adriano).
- **Gabarito**: `tests/eval/data/gabarito.jsonl` (72 casos; local e no bucket; fora do Git). Regras do Adriano (D037): categoria ambígua → perguntar; recorrente → perguntar se é fixo; "esse mês já" → perguntar antes.
- **1ª rodada completa** (prompt já enxuto): intenção 100%, valor 98,5%, tipo 98,5%, data 97%, **categoria 81,8%** (meta 90%). Ajustes feitos depois dela (código: nome da categoria aceito, "Outros" vira pergunta, total acumulado, data perdida e "vence" achados no texto; prompt: dicas das categorias, ambíguos explícitos, transferência só entre contas próprias, "trinta e cinco e noventa" é um valor). **A 2ª rodada não terminou**: a cota diária do Groq da organização acabou.
- **Uso local da chave de produção** nas avaliações: autorizado pelo Adriano **só até a família começar a usar** a produção.

### S2.1 — o que existe (D036)

- **Banco (migração 0003)**: `categories`, `payment_methods`, `transactions`, `category_rules` — ISOLADAS, RLS forçado, chaves estrangeiras **compostas** (testes provam que lançamento/regra não aponta para categoria de outra conta). Centavos `bigint`; `occurred_on`/`cash_on`; transferência sem categoria e com destino; `deleted_at`.
- **Padrões**: `telegrana.seed_account_defaults(conta)` (21 categorias com `code` estável + Pix, Débito, Dinheiro, Poupança). Roda ao concluir o cadastro; rodou na migração para as contas existentes (prod: 1 conta, 21 categorias, 4 formas, conferido em 01/10/2026).
- **`/categorias`** (`core/categorias.py`): criar (emoji + nome em qualquer ordem), renomear, trocar emoji, desativar/reativar; "Outros"/"Outros ganhos" fixas. Perguntas de edição levam a categoria na 2ª linha → `Entrada.contexto` (o adaptador extrai do `reply_to_message` do próprio bot).
- **Testes**: 217 no `pytest` padrão + 14 cenários de E2E (novo: categorias).
- **Ainda sem lançamentos**: as tabelas existem, mas nada grava em `transactions` até a S2.3; texto livre continua respondendo "chegam na próxima etapa".

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
| #26 | `a664f35` | encerramento da S1.4 |
| #27 | `8ee82a7` | **S1.5**: marca, perfil do bot e E2E simulado (D034) |
| #28 | `15d2719` | encerramento da S1.5 e da S1 |
| #29 | `9e3bb0f` | posicionamento: assistente individual com IA; pré-requisitos do lançamento (D035) |
| #30 | `d4d600f` | **S2.1**: categorias e lançamentos no banco; `/categorias` (D036) |
| #31 | `6f06e5f` | encerramento da S2.1 |
| #32 | (aberto) | **S2.2**: extração pela IA, normalização e avaliação (D037) |

## Ponto de partida exato da próxima sessão (fechar a S2.2)

1. Ler os 5 documentos acima. `git pull`; `git checkout feat/s2.2-extracao` (PR #32). `python scripts/check_setup.py`.
2. **Rodar a avaliação completa** (local, ~11 min, ~60 mil tokens): `uv run python scripts/avaliar_ia.py --chave-local GROQ_API_KEY_PROD` (ou `GROQ_API_KEY_DEV`). Saída 0 = passou; 1 = abaixo da meta; 2 = **inconclusiva** (cota/prazo). Se der 2 de cara, a cota diária da organização (200 mil tokens, janela de 24 h, dev + prod juntos) ainda não voltou: esperar. Para ver **localmente** o que a IA respondeu nos casos que falharam, use um script de diagnóstico que imprime a frase (nunca no CI).
3. Ajustar prompt/código até: valor, tipo, data ≥ 95%; categoria ≥ 90%; intenção ≥ 90%. Lembre: o modelo varia um pouco entre rodadas mesmo com temperatura 0 — prefira regras no **código** (determinísticas) quando der.
4. Atualizar o gabarito no bucket se mudar (`scripts/avaliacao_dados.py enviar`); disparar o workflow "Avaliação da IA" no PR (roda pelo filtro de caminhos) e conferir que passa no CI também.
5. Mesclar o PR #32, encerrar a S2.2 com o protocolo e seguir para a **S2.3** (incluir os itens 1–3 da **D038**: atalho sem IA, dev separado de prod, medidor de uso; e mais: lançamentos no bot: recibo com botões, perguntas da IA com botões e criação de categoria, correção por reply, apagar com desfazer, regras aprendidas, pergunta "é fixo?", tratamento de cartão de crédito antes da S5, E2E com Groq falso, roteiro no celular, produção). Na S2.3 a chave `groq/api_key` entra em `config.PARAMETROS`.

## Pendências do Adriano

- Opcional: mais 4 a 9 áudios (a voz da esposa, com o consentimento dela) em `tests/eval/data/audios/`, mais as linhas correspondentes em `audios.txt`.
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

**IA e Groq (S2.2)**
- **Cota diária por organização**: 200 mil tokens/dia no `gpt-oss-20b`, somando dev e prod (os tetos por projeto são sub-limites). Uma avaliação completa gasta ~60 mil; um dia de ajustes acaba com a cota. Use `--casos` para rodar só alguns casos enquanto ajusta.
- **8 mil tokens/minuto**: avalie com `--intervalo 9` (padrão). O cache de prompt do Groq é irregular; não conte com ele.
- O modelo às vezes devolve o **nome** da categoria em vez do código, junta ou separa valores, perde "vence"/datas: o código já corrige o que dá (`core/interpretacao.py`). Sempre que possível, regra no código > instrução no prompt.
- Heredoc no Git Bash: `\\b` dentro de `'PYEOF'` virou o caractere de controle 0x08 numa regex (erro silencioso). Para editar Python com regex, gravar o script com a ferramenta Write.
- O Neon pode derrubar a conexão no meio da suíte longa ("server closed the connection unexpectedly"): rode de novo os arquivos afetados antes de investigar.

**Testes e E2E (S1.5)**
- **O servidor de testes do Telegram não serve mais**: as contas `99966XYYYY` estão desativadas desde 06/2025 (o pedido de código funciona, mas `22222`/`222222` dão `PHONE_CODE_INVALID`). Não tente de novo sem notícia oficial de que voltou (D034).
- O E2E fica fora do `pytest` padrão (`addopts -m "not e2e"`): rode `uv run pytest -m e2e`. Usa o banco descartável da sessão: ~3 min contra o Neon (`testes`), ~1 min no CI.
- Erro de log em nível ERROR durante o E2E derruba o teste no fim (handler `_Erros`): uma exceção engolida pelo `bot.handler` não passa despercebida.

**Celular (adb)**
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

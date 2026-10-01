# DECISOES.md — Telegrana

Registro de decisões. Formato: número, data, decisão, motivo, alternativas descartadas.

## D001 · 2026-09-21 · Telegram em vez de WhatsApp
- **Motivo**: API oficial do WhatsApp exige cartão na Meta e cobra respostas acima de 1.000/mês por número desde 01/10/2026; APIs não oficiais (Baileys) exigem processo sempre ligado (incompatível com Lambda), têm risco de banimento e, em serviços gratuitos de terceiros, entregam a sessão a quem hospeda.
- **Descartado**: WhatsApp Cloud API; Baileys em PC/VPS; Green API / Whapi (planos gratuitos de teste).

## D002 · 2026-09-29 · IA no Groq
- **Motivo**: grátis, sem cartão, Whisper incluso, não treina com dados de clientes, Zero Data Retention self-service.
- **Descartado**: API do Claude (o plano Pro não inclui API; cobrança separada e sem entrada de áudio nativa); Grok/xAI (pago; créditos grátis condicionados a uso dos dados para treino); Gemini grátis (termos permitem revisão humana de dados; não serve nem como reserva).

## D003 · 2026-09-29 · AWS Lambda na conta antiga
- **Motivo**: o Adriano quer a experiência com Lambda; Always Free (Lambda, EventBridge Scheduler, Budgets) cobre o projeto com folga. Cartão só na AWS, com orçamentos e kill-switch.

## D004 · 2026-09-29 · Um banco, contas isoladas por RLS
- **Motivo**: pedido do Adriano (várias contas totalmente isoladas num sistema só). RLS forçado + chaves compostas + testes de isolamento. Estrutura preparada para contas compartilhadas no futuro.
- **Descartado**: um bot e um banco por pessoa (decisão de 2026-09-21, substituída).

## D005 · 2026-09-29 · Identidade pelo Telegram, sem usuário e senha
- **Motivo**: o `from.id` já chega verificado; senha no chat trafega sem criptografia ponta a ponta, exige recuperação por e-mail e abre força bruta/phishing. Código de recuperação para trocar de conta do Telegram.

## D006 · 2026-09-29 · Entrada por link reutilizável + pedido de acesso
- **Motivo**: o Adriano quer que quem receba o link entre livremente, sem gerar um código por pessoa, e que quem achar o bot sozinho peça permissão a ele.
- **Mitigações**: token só como hash, limite de usos, rotação com `/link novo`, aviso ao admin a cada entrada com botão de bloqueio. Avisos do admin chegam no próprio @TelegranaBot (bot de admin separado descartado na V1).

## D007 · 2026-09-29 · Cartão de crédito em regime de caixa
- **Motivo**: definição do Adriano: compra no crédito só vira gasto quando a fatura é paga. Parcelas distribuídas pelas faturas; cada item da fatura mantém sua categoria no pagamento.

## D008 · 2026-09-29 · Lembretes configuráveis por item
- Regras: 1 dia antes, no dia, diário após vencimento; horários 09:00, 20:00 ou ambos (`America/Sao_Paulo`).

## D009 · 2026-09-29 · Nome "Telegrana" e logo do Adriano
- Grafia com só o T maiúsculo. O avião de papel da logo remete ao símbolo do Telegram: risco aceito para uso familiar, reavaliar se virar público.

## D010 · 2026-09-29 · Cadastro mínimo: nome, telefone verificado e maioridade
- **Motivo**: identificar as pessoas sem acumular dado sem uso (princípio da necessidade da LGPD). Telefone pelo botão nativo do Telegram (verificado pelo próprio Telegram) e guardado só como HMAC com pepper: serve para recuperar a conta sem expor o número.
- **Descartado**: e-mail (sem finalidade na V1; exigiria serviço de envio) e data de nascimento (sem finalidade; a declaração de maioridade basta).

## D011 · 2026-09-29 · Recuperação em três níveis
- Mesmo telefone → automática; outro número → código de recuperação; perdeu tudo → aprovação manual do admin após conferência fora do bot. Toda religação avisa o admin e a conta antiga.

## D012 · 2026-09-29 · Termos de Uso e Política de Privacidade
- Aceite obrigatório antes de qualquer coleta; textos versionados no repositório e publicados no Telegraph; aceite registrado com versão e hash; nova versão exige novo aceite. Rascunho do agente, revisão e aprovação do Adriano. Se o bot deixar de ser familiar, revisão por advogado.

## D013 · 2026-09-29 · Pedido de acesso pergunta "Como você conhece o Adriano?"
- Dá ao admin contexto para decidir; texto livre de até 200 caracteres, apagado com o pedido.

## D014 · 2026-09-29 · WhatsApp depois da V1
- Primeiro o Telegram completo; depois estudo de viabilidade e do investimento na AWS para um gateway de WhatsApp.

## D015 · 2026-09-29 · Repositório GitHub público
- **Motivo**: pesquisa de 29/09/2026 mostrou que secret scanning e push protection **não são gratuitos** em repositório privado de conta pessoal (exigem GitHub Secret Protection, pago). O Adriano escolheu o repositório público, que tem as duas proteções de graça (e Actions sem limite de minutos).
- **Consequências**: nada pessoal no repositório (`.env.local` e `tests/eval/data/` no `.gitignore`); commits com o e-mail *noreply* do GitHub (configurado no repositório local); Actions com `GITHUB_TOKEN` só leitura e aprovação obrigatória de PRs de fora; o @ do bot fica descobrível (mitigado pelo fluxo de pedido de acesso e limites). gitleaks continua no pre-commit e no CI (defesa em profundidade).
- **Descartado**: privado + só gitleaks (recomendação do agente, preterida); privado + Secret Protection (pago, viola a regra de custo zero).

## D016 · 2026-09-29 · Conjunto de avaliação da IA fora do repositório
- **Motivo**: consequência de D015. As mensagens e áudios reais da família são dados pessoais e financeiros; ficam em `tests/eval/data/` (ignorado pelo Git), só na máquina do Adriano.
- **A decidir na S2**: como o CI roda a avaliação sem publicar os dados. Proposta: repositório **privado** separado (`telegrana-eval-data`) lido pelo CI com token de leitura restrito; alternativa: rodar a avaliação só localmente antes de cada mudança de prompt/modelo.

## D017 · 2026-09-29 · Acesso AWS de desenvolvimento por `aws login` (sem chaves fixas)
- **Decisão**: usuário IAM `adriano-dev` com MFA, políticas `AdministratorAccess` + `SignInLocalDevelopmentAccess`; o AWS CLI (≥ 2.32) usa `aws login --profile telegrana`, que gera credenciais temporárias (até 12 h). Nenhuma access key existe.
- **Motivo**: IAM Identity Center em conta avulsa só permite *account instance*, que não dá acesso a contas AWS (só a aplicações); a instância de organização exigiria ativar o AWS Organizations só para isso. O `aws login` (lançado em nov/2025) entrega credencial temporária sem essa mudança estrutural.
- **Administrador na S0/S1**: o bootstrap cria papéis IAM, OIDC, orçamentos e Lambdas (criar papéis já equivale a admin). Mitigação: MFA, sessão curta, nenhuma chave. **Na S8**: deploy só pelo CI (papel OIDC mínimo) e redução do `adriano-dev`.
- **Descartado**: usuário IAM com access key + `aws configure mfa-login` (chave de longo prazo no disco); IAM Identity Center com AWS Organizations (mudança estrutural desnecessária para uma conta).

## D018 · 2026-09-29 · Sem Postgres local em Docker
- **Decisão** (escolha do Adriano): testes de integração locais contra a branch `dev` do Neon; no CI, Postgres em *service container* do GitHub Actions (mesma versão major do Neon, 18).
- **Motivo**: Docker não está instalado; Docker Desktop no Windows exige WSL2 e é pesado. O container do CI é grátis (repositório público).
- **Descartado**: Docker Desktop local.

## D019 · 2026-09-29 · Limites do Groq Free registrados
- Verificado em 29/09/2026 (console.groq.com/docs/rate-limits), por **organização**: `openai/gpt-oss-20b` e `openai/gpt-oss-120b` — 30 req/min, 1.000 req/dia, 8.000 tokens/min, 200.000 tokens/dia (cada modelo); `whisper-large-v3` — 20 req/min, 2.000 req/dia, 7.200 s de áudio/hora, 28.800 s/dia. Nenhum dos três tem descontinuação anunciada (Llama 3.x saiu do Free em 16/08/2026; não usamos).
- **Risco monitorado**: 200 mil tokens/dia no 20b ≈ 150–200 extrações/dia para a família toda. Mitigações: prompt enxuto (só categorias e formas de pagamento da conta), limites por conta (seção 8.6), contagem de tokens por conta a partir da S2 e alerta ao admin a 70% da cota diária.
- ZDR disponível a todos os clientes em Settings → Data Controls.

## D020 · 2026-09-29 · Validação visual em iPhone é manual
- O Adriano usa Android 11+ (adb por Wi-Fi confirmado como caminho). Há iPhone na família: antes de cada liberação à família (a partir da S8), o agente gera um checklist visual para conferência manual no iPhone.

## D021 · 2026-09-30 · Conta AWS nova, no plano gratuito com créditos
- **Fato**: a conta antiga do Adriano foi suspensa; em 30/09/2026 ele criou uma conta nova, no **Free account plan**, com US$ 100 de créditos (validade 30/09/2027) e mais até US$ 100 por 5 atividades de US$ 20 (prazo de 6 meses).
- **Regras da conta nova** (verificadas em 30/09/2026, aws.amazon.com/free/free-tier-faqs): o plano gratuito termina em 6 meses (30/03/2027) ou quando os créditos acabarem, o que vier primeiro; se não houver upgrade para o plano pago, a conta é fechada (90 dias de carência). Os créditos restantes continuam valendo depois do upgrade, até expirar. O Always Free (Lambda, EventBridge Scheduler etc.) vale nos dois planos. EC2 do free tier para contas novas: `t3.micro`, `t3.small`, `t4g.micro`, `t4g.small`, `c7i-flex.large`, `m7i-flex.large`.
- **Decisão**: desenvolver no plano gratuito (a AWS não consegue cobrar o cartão) e fazer o upgrade para o plano pago **depois** de orçamentos e kill-switch prontos e **antes** de 30/03/2027. Fazer as 5 atividades de crédito como `adriano-dev` (Budgets e Lambda com os recursos reais do projeto; EC2, RDS e Bedrock descartáveis, apagados na hora).
- **Provável causa da suspensão da conta antiga** (pelo relato do Adriano, ela foi criada e ficou sem uso por 6 meses ou mais): contas criadas depois de 15/07/2025 no plano gratuito são **fechadas ao fim de 6 meses sem upgrade**. É exatamente o risco da conta nova: **prazo duro de upgrade em 30/03/2027** (lembrete no HANDOFF; o agente avisa a partir de 01/2027).
- **Muda no plano**: a seção 9 deixa de falar em "conta antiga"; a auditoria da S0.2 vira conferência de conta vazia; o upgrade de plano entra como tarefa com prazo.

## D022 · 2026-09-30 · WhatsApp não oficial (whatsmeow) como S9, pago com os créditos da AWS
- **Decisão** (aprovada pelo Adriano): depois da V1 no Telegram, a S9 adiciona o canal WhatsApp. Um gateway **whatsmeow (Go)** roda numa EC2 `t4g.micro` sem portas de entrada, conversa com o mesmo núcleo pela Lambda (via IAM) e recebe as mensagens de saída por uma fila SQS. Detalhes na seção 15 do plano.
- **Motivo**: os créditos da conta nova (D021) pagam o servidor sempre ligado até 09/2027. A API oficial passou a cobrar a partir de 01/10/2026 e exige cartão na Meta.
- **Efeito já na S1**: identidades por canal (`user_channels`) e formatador guiado pelas capacidades de cada canal; nada de `telegram_id` fixo.
- **Riscos aceitos**: banimento do número (chip dedicado; o Telegram continua principal; nenhum dado se perde); depois de 09/2027, custo de US$ 7 a 10/mês ou desligamento.
- **Revisa**: D001 (o problema do "processo sempre ligado" se resolve com a EC2 paga pelos créditos) e D014 (o estudo vira sprint).
- **Descartado**: Baileys (Node: mais memória, árvore npm grande, caso lotusbail); neonize (camada Python sobre o whatsmeow, menos madura); API oficial (cobrança e cartão na Meta); gateway na máquina do Adriano (o sistema precisa rodar 100% online).

## D023 · 2026-09-30 · Base da conta AWS: orçamentos, kill-switch e OIDC (stack `telegrana-bootstrap`)
- **Autorizado pelo Adriano em 30/09/2026.** CloudFormation puro em `deploy/bootstrap.yaml`: o código do kill-switch vai embutido no template, então não precisa de bucket S3 nem de artefato.
- **Orçamentos com `IncludeCredit: false`**: o consumo pago com créditos aparece nos alertas. Sem isso, o plano gratuito sempre daria US$ 0 e nada alertaria. `telegrana-gasto-zero` (alerta a US$ 0,01) e `telegrana-teto-mensal` (US$ 1: 80% real e 100% previsto por e-mail; 100% real → SNS → kill-switch).
- **Kill-switch por notificação SNS**, não por *Budgets Action*: zero custo e sem gastar a cota de ações grátis. Zera a concorrência das Lambdas `telegrana-*`; relatório por e-mail num tópico separado (`telegrana-avisos`), para não criar laço. O aviso pelo Telegram entra na S1.
- **Limite da conta nova: 5 execuções simultâneas de Lambda** (`get-account-settings`, 30/09/2026). Não dá para reservar concorrência por função (o plano previa "concorrência reservada 5"); o limite da conta já é o teto técnico. Zerar funciona (testado). Webhook do Telegram com `max_connections` ≤ 3, para sobrar folga para `rotinas`/kill-switch. Pedir aumento de cota só se for necessário.
- **Papel OIDC `telegrana-github-deploy`** com confiança restrita a `repo:drizaogythub97/telegrana:ref:refs/heads/main` e **nenhuma permissão** até a S1 (menor privilégio: as permissões nascem junto com o template SAM).
- **Na S9**: subir o teto mensal para o custo planejado da EC2 (pago com créditos) e acrescentar a parada da EC2 ao kill-switch.
- **Descartado**: Budgets Actions (limite de 2 grátis; não param Lambda diretamente); SAM para a base (exigiria bucket S3 de artefatos).

## D024 · 2026-09-30 · Gestão do Neon por chave de API Project-scoped, sem MCP
- **Decisão**: o agente recebe uma chave **Project-scoped** (`NEON_API_KEY`, nome `telegrana-agente`) e gerencia o Neon (branches, senhas, computação) por chamadas diretas à API v2, em scripts versionados. Dentro do banco, o acesso é pelas strings do papel dono.
- **Motivo**: o Adriano quer o mínimo de passos manuais. A chave Project-scoped tem papel de editor, mas **não apaga o projeto** nem gerencia acessos.
- **Descartado**: o *Agent prompt* do Neon (CLI global via npm + MCP + skills + `neon.ts`). Ele puxaria dados reais da família para o contexto do agente (risco de privacidade e de prompt injection por texto livre salvo no banco), acrescentaria dependências fora da stack Python e deixaria o acesso preso à configuração do agente, em vez de scripts auditáveis.

## D025 · 2026-09-30 · Groq: ZDR global, modelos restritos e projetos prod/dev com teto no dev
- **Aplicado pelo agente, via Chrome, com autorização do Adriano** (30/09/2026):
  - **Global ZDR ligado**. Desde 15/10/2025, o padrão do Groq é guardar entradas e saídas por até 30 dias; o ZDR estava desligado.
  - **Allowlist de modelos na organização**: só `openai/gpt-oss-20b`, `openai/gpt-oss-120b` e `whisper-large-v3` (menor privilégio: uma chave vazada não usa outros modelos). Para usar outro modelo (ex.: `llama-prompt-guard-2` na S2), é preciso liberá-lo antes.
  - **Projetos** `telegrana-prod` (limites da organização) e `telegrana-dev` (teto: 400 req/dia e 80 mil tokens/dia em cada gpt-oss; Whisper com 800 req/dia e 10.800 s/dia).
- **Motivo**: a cota diária é da organização; uma rodada de avaliação (~90 mil tokens) poderia esgotar a cota e parar o bot da família. O teto do dev garante pelo menos 120 mil tokens/dia e 600 req/dia para produção.
- **Verificação**: o `check_setup` identifica o projeto de cada chave pelo cabeçalho `x-ratelimit-limit-requests` (RPD) de uma chamada mínima.
- O Default Project fica sem chaves.

## D026 · 2026-09-30 · Créditos da AWS completos (US$ 200)
- As 5 atividades de crédito foram concluídas no dia da criação da conta, com autorização do Adriano. Saldo: **US$ 200, válido até 30/09/2027** (API `freetier`). Todos os recursos descartáveis foram apagados na hora.
- Aprendizado: **recursos criados por API/IaC contam** para as atividades (Budgets e Lambda via CloudFormation). O Bedrock contou pela tentativa no playground, mesmo com o bloqueio "Operation not allowed" de conta nova.
- Efeito no plano (seção 15.4): o WhatsApp da S9 tem folga para rodar com créditos até 09/2027.

## D027 · 2026-09-30 · Composição do conjunto de avaliação da IA
- **Áudio**: 11 gravações reais do Adriano (`tests/eval/data/audios/01–11.ogg`, originalmente notas de voz do WhatsApp). `audios.txt` começou como rascunho do Whisper e **precisa da conferência do Adriano**. A meta segue 15–20; a voz da esposa (com o consentimento dela) é opcional e bem-vinda.
- **Texto**: por escolha do Adriano, as 61 frases foram **escritas pelo agente** imitando a escrita real no Telegram: abreviações (hj, qnt, pfv, vdd), gírias (conto, pila), erros de digitação, falta de acento, emojis, várias despesas numa mensagem, datas relativas, parcelamentos, frases incompletas, correções, perguntas de relatório e 2 tentativas de prompt injection.
- **Casos de borda revelados pelos áudios**: "Bot" transcrito como "Bote"; "guardar na poupança" (movimentação, não gasto); "dar dinheiro para a esposa ir ao mercado" (gasto ou transferência familiar?). Decidir o tratamento na S2.
- **Risco aceito**: frases sintéticas tendem a ser mais "comportadas" que as reais. Mitigação: na S8, as mensagens reais do uso do Adriano (com consentimento, anonimizadas) entram no conjunto.
- Tudo fica em `tests/eval/data/` (fora do Git, D016).

## D028 · 2026-09-30 · Regras de interpretação definidas pelos áudios de teste
- **Finalidade explícita manda** (Adriano): se a mensagem diz para que foi o dinheiro, esse é o lançamento. Ex.: "dei 80 reais pra minha esposa ir no mercado" → **gasto de R$ 80,00 em 🛒 Mercado**. O resto da frase é só a naturalidade de um áudio rápido e não muda a classificação.
- **Guardar na poupança/investir não é gasto** (proposta do agente, aceita sem objeção): vira **transferência** para uma forma de pagamento/conta "Poupança" da própria pessoa e não entra no total de gastos. Ex.: áudio 07, "guardar na poupança 52 mil reais" (valor confirmado pelo Adriano).
- **Sem finalidade identificável → o bot pergunta** (reforça a regra de ouro 7): a extração devolve `categoria = null` com um motivo, e o bot responde com botões das categorias mais prováveis mais "Outra". Nunca chuta nem usa "Outros" sem perguntar. Ex.: "50 reais", "gastei no mercado" (sem valor), "uns 30 e poucos" (valor vago).
- Esses casos entram no gabarito da avaliação (S2).

## D029 · 2026-09-30 · S1.1 — ferramentas do projeto e CI
- **Runtime**: `python3.14` (Lambda, Amazon Linux 2023, arm64; suporte até 06/2029), a mesma versão da máquina. `requires-python = ">=3.14,<3.15"`.
- **Dependências**: `uv` com `uv.lock` (hashes) e instalação sempre com `--locked`. Build com `uv_build`. As dependências de execução só entram junto com o código que as usa.
- **Qualidade**: ruff (inclui as regras S de segurança e DTZ, que exige datetime com fuso), mypy `strict` em `src/` e `scripts/`, bandit, pip-audit, pytest com marcadores `integration`/`isolation`.
- **CI** (`.github/workflows/ci.yml`): jobs `qualidade`, `testes` (Postgres 18 em service container) e `segredos` (gitleaks no histórico completo); actions fixadas por hash de commit; `permissions: contents: read`.
- **pre-commit**: gitleaks, ruff, higiene de arquivos e uma **trava própria** que recusa `tests/eval/data/*` e `.env*` mesmo com `git add -f`.
- **Testes de arquitetura** desde o primeiro dia: `core/`, `ai/` e `exports/` não podem importar canais (regra de ouro 10).
- **Dependabot** semanal (uv e GitHub Actions).
- **Descartado**: Poetry/pip-tools (o uv já cobre lock com hashes e é mais rápido); pre-commit sem gitleaks local (o CI sozinho detectaria o vazamento tarde demais).

## D030 · 2026-09-30 · S1.2 — banco: migrações próprias, papéis e RLS
- **Migrações**: executor próprio (`telegrana.infra.migrate`, ~100 linhas) com arquivos SQL versionados `NNNN_nome.sql`, uma transação por arquivo, trava consultiva e **SHA-256 de cada migração aplicada** (alterar uma migração que já rodou é erro). Descartados: Alembic (traria SQLAlchemy; o projeto não usa ORM), yoyo/dbmate/sqitch (mais uma dependência ou binário para algo simples).
- **Driver**: `psycopg[binary]` 3.3 (wheels para Lambda arm64/cp314) + `certifi` (TLS `verify-full` em Windows e Lambda). Nenhum ORM.
- **Papéis** (criados por `telegrana.infra.bootstrap` com o dono): `telegrana_migrator` (dono do esquema `telegrana`; CREATE no banco) e `telegrana_app` (sem posse, sem BYPASSRLS, `CONNECTION LIMIT 10`, `statement_timeout 5s`, `idle_in_transaction_session_timeout 10s`, `search_path telegrana`).
- **Isolamento**: RLS habilitado e **forçado** nas tabelas ISOLADAS (`accounts`, `users`, `account_members`, `user_channels`, `terms_acceptances`), com política `isolamento` só para `telegrana_app` e política `migrator` para o dono. Contexto por transação: `set_config('app.account_id', ..., true)` via `db.account_context`. Tabelas GLOBAIS (`invite_links`, `access_requests`, `processed_updates`, `audit_log`, `schema_migrations`) controladas por GRANT coluna a coluna; `audit_log` é só INSERT para o app.
- **Antes da conta ser conhecida**, só dois caminhos, SECURITY DEFINER com `search_path` fixo e sem EXECUTE para PUBLIC: `resolve_identity(canal, id)` e `start_onboarding(canal, id)` (cria conta + pessoa + vínculo + identidade; idempotente e seguro contra corrida).
- **IDs**: `uuidv7()` do Postgres 18 (ordenados no tempo).
- **Testes**: banco descartável por sessão (CREATE/DROP DATABASE); suíte de isolamento com leitura, alteração, exclusão e inserção cruzadas + meta-testes do catálogo (toda tabela classificada; RLS forçado; políticas sem PUBLIC; funções definer blindadas). Validada por **sabotagem**: abrir a política de `terms_acceptances` derrubou 2 testes na hora.
- **Branches do Neon**: `testes` (criada pelo agente; só testes automatizados, dono em `TELEGRANA_TEST_DATABASE_URL`) e `dev` (papéis + migração 0001 aplicados; URLs em `NEON_APP_URL_DEV`/`NEON_MIGRATOR_URL_DEV`). **Produção fica intocada até a S1.3**, que leva o bootstrap e as migrações para o pipeline, com senhas no SSM.

## D031 · 2026-09-30 · S1.3 — infraestrutura, segredos e pipeline de deploy
- **Lambdas** (`deploy/app.yaml`, SAM): `telegrana-<env>-bot` (Function URL `AuthType NONE`; a autenticação é o cabeçalho secreto do Telegram, comparado em tempo constante) e `telegrana-<env>-rotinas` (EventBridge Scheduler `cron(0 9,20 * * ? *)` em `America/Sao_Paulo`). Runtime `python3.14` arm64, 256 MB, logs em JSON com 7 dias de retenção. Uma stack por ambiente (`telegrana-dev`, `telegrana-prod`).
- **Limite de permissões obrigatório** (`telegrana-limite-lambdas`): todo papel criado pelo deploy precisa dele (condição `iam:PermissionsBoundary` no papel de deploy). Assim, o pipeline não consegue criar um papel com mais poderes do que logs, leitura de `/telegrana/*` no SSM e invocação das Lambdas do projeto.
- **Papel de deploy** (`telegrana-github-deploy`): OIDC só para os ambientes `dev`/`prod` do GitHub (restritos à `main`); permissões limitadas às stacks, funções, papéis, logs e agendas `telegrana-dev-*`/`telegrana-prod-*`, ao bucket de artefatos e aos segredos de deploy.
- **Artefatos**: bucket `telegrana-artefatos-<conta>` com expiração de 7 dias, sem acesso público, só TLS (custo de centavos pago pelos créditos).
- **Segredos no SSM** (SecureString, `aws/ssm`): tokens, segredo do webhook (`token_urlsafe(48)`), URLs dos papéis do banco. **Produção**: papéis criados pelo agente com o dono **só nesta máquina**; as senhas foram direto para o SSM (`scripts/ssm_setup.py`) e nunca passaram pelo `.env.local` nem pela tela. A Lambda lê tudo uma vez por *cold start* (`telegrana.infra.config`, campos com `repr=False`).
- **Pacote**: `scripts/build_lambda.py` monta os wheels **linux arm64/cp314** com `uv pip install --python-platform aarch64-manylinux_2_28` a partir de qualquer máquina, sem Docker e sem `sam build`.
- **Pipeline** (`ci.yml`): push na `main` → CI → `deploy-dev` (pacote → migrações → `cloudformation package/deploy` → `setWebhook`). Produção: execução manual com `prod=true` (fica automática depois do E2E da S1.5). AWS CLI do runner, sem SAM CLI no CI.
- **Webhook**: `allowed_updates` = message, callback_query, my_chat_member; `max_connections` = 3; `drop_pending_updates` a cada deploy.
- **Dependências novas**: `httpx` (execução; Bot API com timeouts) e `boto3` (**só dev**: o runtime da Lambda já traz). No Windows, o boto3 não usa direto a credencial do `aws login` (exigiria `awscrt`); criado o perfil ponte `telegrana-sdk` (`credential_process`) no `~/.aws/config`.
- **Proteção de logs**: `httpx`/`httpcore`/`botocore` em WARNING, porque a URL da Bot API contém o token. Erros do cliente Telegram não carregam a URL (`from None`).
- **Descartado**: SAM CLI no CI (dependência pesada; o AWS CLI já vem no runner); `sam build` em container (exigiria Docker); Parameters and Secrets Lambda Extension (camada extra; a leitura no cold start basta); bibliotecas de bot (python-telegram-bot/aiogram: abstrações desnecessárias para webhook em Lambda).

## D032 · 2026-10-01 · Termos de Uso e Política de Privacidade v1
- **Revisão**: rascunhos revisados com as skills `lgpd-escritorio`, `revisao-contratos` e `analise-legislacao` (Chat Jurídico, instaladas pelo Adriano em `~/.claude/skills/`). Artigos da LGPD conferidos no texto compilado do Planalto em 01/10/2026; resoluções da ANPD (2/2022, 15/2024, 19/2024) e a janela de 6 h do Neon Free conferidas em fontes secundárias e na documentação do Neon. Aprovados pelo agente por delegação do Adriano. **Não é parecer jurídico.**
- **Bases legais**: execução do serviço pedido pelo titular (art. 7º, V) para cadastro, lançamentos e pedido de acesso; legítimo interesse (art. 7º, IX) só para registros de segurança (`audit_log`), sem conteúdo financeiro; consentimento específico e destacado (art. 11, I) só para dado sensível que a própria pessoa escrever numa descrição; transferência internacional pelo art. 33, IX (necessária à execução do serviço). Descartado: consentimento como base principal (revogável, e o serviço não funciona sem os dados; art. 8º, §4º veda autorização genérica).
- **Encarregado**: o próprio Adriano. A Res. CD/ANPD 2/2022 dispensaria o encarregado para pessoa natural de pequeno porte, mas o uso de IA pode enquadrar o tratamento como de alto risco; designar resolve as duas leituras.
- **Correções de fundo** em relação ao rascunho: "nada antes do aceite" era falso (pedido de acesso e cadastro em andamento existem antes); "código irreversível" do telefone era exagero (com a chave dá para testar números); faltavam o código de recuperação, os registros de segurança, a lista completa de direitos do art. 18 (incluindo ANPD e prazo de 15 dias do art. 19), o aviso de incidente (art. 48), o Telegram como serviço independente (não operador) e o histórico do chat que sobrevive ao `/apagar_conta`.
- **Termos**: incluídas cláusula de responsabilidade equilibrada (sem exoneração de dolo, culpa grave ou incidente com dado), aviso de 7 dias antes de suspensão, 30 dias antes de encerrar o serviço, 15 dias antes de mudar os termos, e foro do domicílio do usuário (contrato de adesão; CC, arts. 423 e 424). A regra que proibia registrar dado de terceiro foi trocada por "registre só o necessário". Sem remuneração, o CDC provavelmente não se aplica, mas os termos já seguem o padrão protetivo.
- **Marcadores** `{{contato_admin}}` e `{{data_vigencia}}`: preenchidos pelo bot ao publicar no Telegraph. Trocar o contato não exige novo aceite (o art. 8º, §6º, cita os incisos I, II, III e V do art. 9º; o contato é o IV). O Adriano ainda **não tem @ no Telegram**; o valor vai para a configuração quando ele criar.
- **Obrigações para o código (S1.4)**: tela de aceite com os dois destaques (dado sensível e transferência internacional) e botão "Aceito"; aviso curto antes de coletar o pedido de acesso; `rotinas` apagando cadastros não concluídos com mais de 7 dias; `audit_log.details` sem dado pessoal e, no `/apagar_conta`, apagar os registros da conta e deixar só o evento anônimo de exclusão; enquanto não houver `/exportar`, exportação manual pelo admin em até 15 dias; aviso de incidente pelo bot.
- **Registro das operações** (art. 37): `legal/registro-tratamento.md`.

## D033 · 2026-10-01 · S1.4 — entrada, cadastro e recuperação
- **Arquitetura**: o núcleo (`core/`) recebe `Entrada` e devolve `Resultado` com `Saida`s neutras (texto com `**negrito**`/`` `código` ``, botões, pedir telefone, pergunta, mensagem protegida); `channels/telegram/adaptador.py` converte updates e desenha teclados. Módulos: `roteador` (quem trata), `cadastro` (sem conta, máquina de estados, recuperação), `conta` (comandos de privacidade), `admin`, `repositorio` (todo o SQL, fixo e parametrizado), `seguranca`, `textos`, `contexto`.
- **Perguntas sem estado no banco**: a resposta livre (pedido de acesso, código, nome) usa *force reply*; o adaptador reconhece a pergunta pela primeira linha da mensagem do próprio bot (`reply_to_message.from.id` = id do bot, tirado do token). Descartado: tabela de "aguardando resposta" (mais um dado pessoal para guardar e limpar).
- **Código de recuperação**: 20 caracteres Crockford base32 (`XXXX-XXXX-XXXX-XXXX-XXXX`, 100 bits): **seletor** de 8 (em claro, único, só localiza a linha) + **verificador** de 12 (60 bits, só como Argon2id com os parâmetros padrão do argon2-cffi, perfil de baixa memória da RFC 9106). Seletor inexistente também gasta um Argon2 (hash falso) para o tempo de resposta não revelar nada. Trocado a cada uso. Descartado: bcrypt/pgcrypto dentro do Postgres (o plano e a Política dizem Argon2) e conferir contra todos os hashes (não escala).
- **Telefone**: E.164 = `+` + dígitos do número que o Telegram entrega (já internacional); HMAC-SHA256 com *pepper* de 32 bytes em `/telegrana/<env>/phone/hmac_pepper` (gerado por `ssm_setup.py`, **nunca rotacionar**). Só o contato com `user_id` = remetente. Descartado: `phonenumbers` (dependência sem ganho para números que já chegam normalizados).
- **Travas**: `auth_attempts` (global) por identidade e tipo (código, telefone): 5 erros → 15 min, dobrando até 24 h; apagadas 1 dia depois da última tentativa (Política e registro atualizados antes da publicação).
- **Funções SECURITY DEFINER novas** (todas com `search_path` fixo e sem EXECUTE para PUBLIC; cobertas pela suíte de isolamento): `recovery_lookup`, `find_user_by_phone`, `relink_identity` (nunca toma identidade de conta ativa; descarta cadastro inacabado), `erase_account` (só a conta do **contexto**; deixa só o evento anônimo), `purge_stale_onboarding`, `admin_list_users` (o código só chama para o admin). Auxiliar interna `_erase_person` sem EXECUTE para o app.
- **Pedido de acesso**: aprovar já cria o cadastro inacabado e apaga o pedido (a Política diz "apagado quando a conta é criada"). Recusado: a pessoa não é avisada e não pede de novo até o pedido expirar (7 dias). Limite global de 20 pedidos por hora. Recuperação manual usa a mesma tabela (`kind = 'recovery'`): o admin escolhe a conta pelos botões, confere a pessoa **fora do bot**, e ela recebe um código novo.
- **Convite**: `/link novo` (revoga o anterior; o link só aparece na criação, porque o banco guarda só o SHA-256), `/link`, `/link revogar`. O uso conta quando o cadastro termina.
- **Configuração inicial** do cadastro (categorias, formas de pagamento, cartões) passa para a S2.
- **Textos legais**: `scripts/publicar_legal.py --contato @...` publica no Telegraph (conta própria; token em `/telegrana/telegraph_token`) e grava `/telegrana/<env>/legal/{termos,privacidade}` = JSON `{versao, url, path, sha256, vigencia, contato}` e `/telegrana/<env>/admin/contact`. O SHA-256 do aceite é do texto com a data de vigência e **sem** o contato. Publicados em 01/10/2026.
- **Dependências novas**: `argon2-cffi` (wheels abi3 para Lambda arm64) e `tzdata` (fuso de São Paulo garantido no Lambda e no Windows).
- **Exportação**: `/exportar` chega com os relatórios; até lá, `/apagar_conta` e `/meus_dados` orientam a pedir a cópia ao admin (D032).

## D034 · 2026-10-01 · S1.5 — E2E simulado, marca e perfil do bot
- **Contexto**: as contas de teste `99966XYYYY` do servidor de testes do Telegram estão **desativadas desde 06/2025** (mantenedor do TDLib em tdlib/td#3370 e #3564: foram registradas em massa e mal usadas; não voltam para uso geral). Confirmado na prática em 01/10/2026: o servidor aceita o pedido de código, mas recusa `22222`/`222222` (`PHONE_CODE_INVALID`). Criar conta lá agora exige número real pelo app de iPhone.
- **Decisão (Adriano, 01/10/2026)**: E2E **simulado** no CI + roteiro no celular antes de cada liberação para a família. O E2E entrega updates no formato do Telegram ao `bot.handler` real (segredo do webhook, deduplicação, adaptador, núcleo, Postgres) e responde pela Bot API simulada (`tests/e2e/telegram_simulado.py`), que **recusa** o que o Telegram recusaria: HTML inválido, texto acima de 4096, botão malformado, `callback_data` acima de 64 bytes, chat inexistente, contato sem o teclado de contato, callback respondido duas vezes (testes de sabotagem em `tests/unit/test_telegram_simulado.py`). Cobre os 11 cenários do critério de pronto da S1 e mais dois (botão usado some; bloqueio).
- **Produção automática**: merge na `main` → `deploy-dev` + `e2e` → `deploy-prod` (PLANO 10.3), com verificação das Lambdas depois de cada deploy. Manual continua possível (`gh workflow run CI --ref main -f prod=true`).
- **Descartado**: Telethon e contas no servidor de testes (indisponível); contas reais com Telethon (userbot: risco de banimento e dado pessoal); servidor de testes com números reais pelo iPhone (frágil, depende de aparelhos e o Telegram apaga as contas).
- **Marca**: `scripts/marca.py` gera `assets/brand/out/` (ícone 640/512/256/128/64 em PNG e o JPG da foto do bot, logo transparente, horizontal e branca vazada; o branco do "$" fica) e `previa.png`; paleta em `telegrana.exports.brand`. Aprovada pelo Adriano em 01/10/2026 e aplicada nos dois bots.
- **Perfil do bot** pela Bot API (`deploy_tasks.py perfil`, roda em todo deploy): menu de comandos para todos os chats privados e um menu com os comandos de admin só no chat do admin (pulado enquanto o admin não conversar com o bot: "chat not found"); descrição e descrição curta ("[DEV]" no dev); `--foto` usa `setMyProfilePhoto` (Bot API 9.4; só JPG).

## D035 · 2026-10-01 · Posicionamento: assistente individual com IA; lançamento público com pré-requisitos
- **Decisão (Adriano)**: o Telegrana não é "controle da família", e sim um assistente financeiro **individual**, com a **IA em destaque** (é o que o torna viável e chamativo). Começa em acesso antecipado por convite (família e amigos) e deve ser divulgado depois.
- **Textos novos (aprovados pelo Adriano)**: boas-vindas, tela de quem chega sem convite ("acesso antecipado") e perfil do bot (descrição e descrição curta). A descrição já cita recursos das próximas sprints; quem entra agora vê "os lançamentos chegam na próxima etapa".
- **Categorias**: lista padrão do PLANO 4.2 aprovada; categorias personalizadas por pessoa; a IA interpreta o que o código não reconhece e, com baixa confiança, faz ela mesma uma pergunta curta com opções em botões; nunca inventa valor, data ou categoria (complementa D028).
- **Pré-requisitos do lançamento público** registrados no PLANO, seção 16 (textos legais v2, capacidade e custos, entrada, marca, operação, avaliação da IA). Até lá, os textos legais v1 continuam válidos: o uso por convite segue pessoal e gratuito.
- **CLAUDE.md** atualizado ("O que é").

## D036 · 2026-10-01 · S2 — divisão, avaliação no CI e modelo de dados dos lançamentos
- **Divisão (aceita pelo Adriano)**: S2.1 categorias e lançamentos no banco + `/categorias`; S2.2 IA de extração (Groq `openai/gpt-oss-20b` com saída **estrita**, `strict: true`, verificado em 01/10/2026) + normalização de valores e datas no código + regras por palavra-chave + gabarito e avaliação; S2.3 lançamentos no bot (recibo, correção, perguntas da IA, regras aprendidas, E2E, celular, produção).
- **Avaliação no CI (fecha a pergunta em aberto 2 / D016)**: o conjunto (frases, gabarito e áudios) fica num **bucket S3 privado** (criptografado, sem acesso público), lido pelo CI pelo mesmo OIDC do deploy. Os logs mostram só percentuais e ids de caso, nunca as frases (o repositório e os logs do Actions são públicos). Roda só quando muda o código da IA ou o gabarito, com a chave do projeto **dev** do Groq, que tem teto próprio e não consome a cota da produção. Limites do Groq gratuito (01/10/2026): 30 req/min, 1.000 req/dia, 8 mil tokens/min e 200 mil tokens/dia por modelo, **por organização**. Descartados: repositório privado (token pessoal para criar e renovar) e avaliação só local (o CI não protegeria a produção).
- **Modelo de dados (migração 0003)**: `categories`, `payment_methods`, `transactions`, `category_rules`, todas ISOLADAS (RLS forçado, `(account_id, id)`) e com chaves estrangeiras **compostas**: um lançamento ou regra não consegue apontar para categoria ou forma de pagamento de outra conta (testado). Valores em centavos `bigint` (> 0 e < 10^11); `occurred_on` (competência) e `cash_on` (caixa); transferência (`kind = 'transfer'`, D028) sem categoria e com destino; exclusão lógica (`deleted_at`).
- **Padrões**: uma função SQL única, `seed_account_defaults` (SECURITY INVOKER: no app, o RLS só deixa gravar na conta do contexto), cria as 21 categorias aprovadas (com `code` estável para regras e IA) e as formas Pix, Débito, Dinheiro e Poupança. Roda ao concluir o cadastro e rodou uma vez na migração para as contas existentes. Idempotente.
- **`/categorias`**: criar (emoji + nome, em qualquer ordem; sem emoji vira 🏷️), renomear, trocar emoji, desativar/reativar. Nunca apaga (os lançamentos antigos continuam com ela). "Outros" e "Outros ganhos" não podem ser desativadas. Nome único por conta, sem diferenciar maiúsculas.
- **Contexto da pergunta**: as perguntas de edição levam na 2ª linha qual categoria é ("🛒 Mercado"); o adaptador entrega essa linha em `Entrada.contexto` e o núcleo acha a categoria pelo rótulo **dentro da conta** (RLS). A linha vem de uma mensagem do próprio bot (`reply_to_message.from.id` = id do bot).


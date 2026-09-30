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

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

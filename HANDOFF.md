# HANDOFF.md — Telegrana

> Atualizado em 29/09/2026 · Fase: **S0 em andamento**. Guias entregues; aguardando o Adriano executar as micro-fases S0.1 a S0.7.
> **Repositório público (D015): nada de segredo nem dado pessoal neste arquivo.**

## Leia nesta ordem

1. `CLAUDE.md` — regras permanentes.
2. Este arquivo.
3. `docs/PLANO.md` — fonte da verdade (revisado em 29/09/2026; as marcações de data mostram o que mudou).
4. `docs/DECISOES.md` — D001 a D020.
5. `docs/manual/README.md` — ordem dos guias da S0 e o que cada fase devolve.

## Estado atual (fim da sessão 1 da S0, 29/09/2026)

**Feito nesta sessão**

- Assunções da seção 14 confirmadas com o Adriano: celular **Android 11+**; **há iPhone na família** (D020); repositório **público** (D015); **sem Docker**, com testes locais contra o Neon `dev` e Postgres em container no CI (D018).
- Pesquisa na documentação oficial (29/09/2026). Contradição encontrada e resolvida: secret scanning e push protection são pagos em repositório privado de conta pessoal, o que levou ao D015. O resto confere com o plano: Always Free da AWS, Budgets (2 orçamentos com ação grátis), Neon Free sem cartão, Groq Free com ZDR e modelos ativos (D019), Bot API de teste, adb por Wi-Fi.
- `git init` local (branch `main`) com estrutura mínima de pastas (`src/telegrana/{core,ai,channels/telegram,infra,exports}`, `tests/{unit,integration,isolation,e2e,eval/data}`, `deploy/`, `legal/`, `scripts/`), `.gitignore`, `.gitattributes`, `README.md` e `.env.local.example` comentado.
- O `.env.local` **já foi criado** na máquina do Adriano (cópia em branco do modelo). Está ignorado pelo Git.
- Guias `docs/manual/S0.1-github.md` … `S0.7-marca-e-dados.md` + `docs/manual/README.md` (ordem e tempos).
- `scripts/check_setup.py`: valida cada fase **só com leituras**, mascara qualquer segredo conhecido na saída e tem o modo `--descobrir-admin-id`. Testado com valores falsos: nenhum vazamento. `scripts/requirements-check.txt` traz `psycopg[binary]` 3.3.6 e `certifi` travados com hash; já estão instalados no Python do usuário.
- Identidade git **deste repositório**: `Adriano Cardoso <225630126+drizaogythub97@users.noreply.github.com>`. O e-mail global da máquina é pessoal e não pode aparecer nos commits.

**Não feito (depende do Adriano)**

- Nenhuma conta ou recurso criado em nenhum serviço (regra desta sessão: só depois da micro-fase concluída e do `check_setup` verde).
- **Sem remoto**: o commit da S0 está só no local. O push acontece depois da S0.1.

## Próximo passo exato

Retome quando o Adriano disser "S0.X concluída". Para cada fase:

1. Rode `python scripts/check_setup.py s0.X` (ele lê o `.env.local`; nunca abra nem imprima esse arquivo).
2. Se estiver verde, execute a ação do agente correspondente:
   - **S0.1** → `git remote add origin https://github.com/<GITHUB_REPO>.git` → `gh auth setup-git` → `git push -u origin main` → criar um ruleset na `main` pela API (PR obrigatório, checks obrigatórios quando existirem, sem force-push e sem apagar a branch; o admin pode contornar enquanto não houver CI) → confirmar `check_setup s0.1` 100% verde.
   - **S0.2** → confirmar Organizations pelo check → **auditoria somente leitura em todas as regiões** (EC2, EBS, snapshots, EIP, NAT, RDS, S3, Lambda, CloudFormation, CloudWatch Logs, ECR, custos do mês pelo Cost Explorer) → **mostrar a lista ao Adriano antes de apagar qualquer coisa** → depois, por IaC (SAM/CloudFormation em `deploy/`): orçamentos *zero spend* e US$ 1/mês (real e previsto), provedor OIDC do GitHub com papel de deploy restrito a `repo:<GITHUB_REPO>:ref:refs/heads/main` e ao environment, e kill-switch (orçamento com ação → SNS → Lambda que zera a concorrência reservada e avisa no Telegram).
   - **S0.3 a S0.5** → só validar. A criação de papéis no banco, do bot de teste etc. é da S1.
   - **S0.6** → pedir autorização e fazer uma captura de teste só da conversa com o bot de dev.
   - **S0.7** → só validar (necessária na S2/S3). Registrar no plano a revisão das categorias que o Adriano mandar pelo chat.
3. Com tudo verde, auditoria feita e orçamentos/OIDC/kill-switch criados: fechar a S0 pelo protocolo e começar a **S1**.

## Armadilhas e gotchas

- O nome é **Telegrana**, não "TeleGrana".
- **Repositório público**: nunca commitar `.env.local`, dados de `tests/eval/data/`, capturas do celular, sessões do Telethon (`*.session`) nem nada que identifique a família além do que já está nos documentos. Conferir o `git status` antes de cada commit.
- **AWS CLI não estava instalado** em 29/09/2026 (o Adriano achava que sim). O guia S0.2 inclui a instalação (≥ 2.32, por causa do `aws login`). SAM CLI e Docker também não estavam instalados.
- O `aws login` dá sessão de **no máximo 12 h**. Se aparecer `ExpiredToken`, peça ao Adriano para rodar `aws login --profile telegrana`; não existe chave fixa. Se o SAM não aceitar essas credenciais, use o perfil ponte com `credential_process` (guia S0.2, erros comuns).
- **Neon**: a branch nova vem com **expiração automática de 1 dia** por padrão (o guia manda desligar). A branch principal se chama `production` (não `main`). Papéis criados por SQL **não** recebem `neon_superuser`, o que é bom para `app`/`migrator`; `BYPASSRLS` só existe via `neon_superuser`. Senha de papel criado por SQL exige 60 bits de entropia.
- **Neon + TLS no Windows**: `sslrootcert=system` não é confiável no Windows; o `check_setup` usa `certifi` com `verify-full`. Na Lambda (Linux), avaliar `sslrootcert=system` ou `certifi`.
- **Groq**: os limites são **por organização** (as chaves prod e dev dividem a cota); 200 mil tokens/dia por modelo gpt-oss (D019).
- **CloudTrail**: o *Event history* (90 dias) é grátis e sempre ativo. Uma *trilha* grava em S3, e o S3 **não** está no Always Free (centavos). O plano pede "trilha de gerenciamento padrão, gratuita": decidir na S0.2 com o Adriano entre só o Event history ou trilha com S3 e ciclo de vida curto. O mesmo vale para o bucket de artefatos do SAM. O orçamento *zero spend* vai alertar qualquer centavo.
- **Budgets**: 2 orçamentos com ação são grátis; a partir do terceiro, US$ 0,10/dia. Atualiza poucas vezes ao dia: o kill-switch é rede de segurança, não bloqueio.
- EventBridge Scheduler: usar o fuso `America/Sao_Paulo` na própria agenda.
- Telegram: `/revoke` no @BotFather invalida o token; `api_id` é um por número; clientes não oficiais ficam sob observação. Por isso o Telethon roda **só** no servidor de testes, com contas `99966XYYYY` (código = DC repetido 5 vezes), nunca com a conta real do Adriano. Bot API de teste: `/bot<token>/test/<método>`.
- Deep link: parâmetro `start` com até 64 caracteres (`A-Z a-z 0-9 _ -`).
- Contato compartilhado: aceitar só se `contact.user_id == from.id`.
- Nenhum dado pessoal antes do aceite dos termos; textos legais aprovados pelo Adriano antes de ir ao Telegraph.
- adb: platform-tools 37.0.1 em `C:\Users\adria\AppData\Local\Android\Sdk\platform-tools` (já no PATH), mDNS ativo. A porta de conexão muda a cada vez que a depuração é religada; o pareamento fica salvo.
- Python da máquina: 3.14. O `uv` 0.12 está instalado em `%APPDATA%\Python\Python314\Scripts\uv.exe` (fora do PATH do Git Bash). O runtime da Lambda (3.12/3.13/3.14) será escolhido na S1.
- Encoding: o `check_setup` reconfigura o stdout para UTF-8 (console do Windows).

## Comandos úteis

```powershell
python scripts/check_setup.py              # todas as fases
python scripts/check_setup.py s0.3 s0.4    # só algumas
python scripts/check_setup.py --descobrir-admin-id
python -m pip install --require-hashes -r scripts/requirements-check.txt
aws login --profile telegrana              # renova a sessão AWS (Adriano)
adb connect IP:PORTA ; adb devices
```

## Pendências do Adriano

- Executar os guias S0.1 → S0.7 (ordem e tempos em `docs/manual/README.md`).
- S0.2: dizer se havia chaves na root e cobrança no mês; autorizar auditoria, orçamentos, OIDC e kill-switch.
- S0.7: revisar as categorias padrão (pelo chat) e pedir o consentimento da esposa para os dados de avaliação.
- Dizer se a logo pode ficar pública no repositório (está em `assets/brand/logo-original.png`, ainda não commitada).
- S1 (previsto): aprovar os rascunhos de `legal/termos-v1.md` e `legal/privacidade-v1.md` e as prévias dos recortes da logo.

## Perguntas em aberto

1. A logo pode ir para o repositório público? Até a resposta, ela fica **fora do commit**.
2. CloudTrail: só o Event history (grátis) ou trilha com S3 (centavos)? Decidir na S0.2.
3. Avaliação da IA no CI sem publicar os dados: decidir na S2 (proposta em D016).

# Operação do Telegrana

> Manual de operação (S8, D054), atualizado em **08/10/2026**. Para quem administra o sistema: o Adriano e o agente. Funções do bot para usuários e admin estão no manual do sistema (documento à parte). Infraestrutura da conta AWS: `deploy/README.md`. Checklist de segurança com evidências: `docs/SEGURANCA.md`.

## Mapa rápido

| Peça | Onde | Ver o estado |
|---|---|---|
| Bot (webhook) | Lambda `telegrana-<env>-bot` | Log `/aws/lambda/telegrana-<env>-bot` (só ids, rótulos e tempos) |
| Lembretes, resumos e limpeza | Lambda `telegrana-<env>-rotinas`, 09:00 e 20:00 | Log das rotinas |
| Backup semanal | Lambda `telegrana-prod-backup`, domingo 03:00 | Chega como arquivo no seu chat de admin |
| Banco | Neon, branches `production` e `dev` | Console do Neon |
| IA | Groq (organização de dev e de prod, com limites próprios) | Console do Groq |
| Custos e kill-switch | Stack `telegrana-bootstrap` | E-mail dos orçamentos |
| Deploy | GitHub Actions: merge na `main` → dev → E2E → prod | Aba Actions |

Prazos fixos: **upgrade da conta AWS até 30/03/2027** (com kill-switch ativo, já testado em 08/10/2026); créditos até 30/09/2027.

## Alarmes (e-mail "ALARM: telegrana-prod-…")

| Alarme | O que significa | O que fazer |
|---|---|---|
| `bot-erros` | Uma mensagem falhou no bot (log com nível ERROR) | Ler o log do bot no horário do alarme: o `erro` diz o tipo (ex.: `OperationalError` = banco). Se repetir, abrir um PR com a correção |
| `bot-lambda` | A própria Lambda do bot falhou (timeout, erro não tratado) | Mesmo log; o Telegram reenvia o update, e a deduplicação evita lançamento em dobro |
| `rotinas-erros` | Lembretes, resumos ou limpeza falharam para alguma conta | Log das rotinas; a rotina seguinte (09:00/20:00) tenta de novo |
| `backup-falhou` | O backup de domingo não saiu | Log do backup; rodar de novo: `aws lambda invoke --function-name telegrana-prod-backup --payload "{}" --cli-binary-format raw-in-base64-out --profile telegrana out.json` |

O alarme volta sozinho para OK quando o erro para. Ver todos: `aws cloudwatch describe-alarms --alarm-name-prefix telegrana- --query "MetricAlarms[].[AlarmName,StateValue]" --output table --profile telegrana`.

## Incidente de segurança (dados pessoais)

Vazamento, acesso indevido, perda de dados ou chave/segredo exposto.

1. **Conter** primeiro: trocar o segredo afetado (seção abaixo); se for grave, acionar o kill-switch (`deploy/README.md`) ou bloquear contas (`/usuarios`).
2. **Registrar** o incidente: data, o que aconteceu, dados e contas afetadas, o que foi feito. O registro é obrigatório para **todo** incidente, comunicado ou não, e fica guardado por **pelo menos 5 anos** (Resolução CD/ANPD nº 15/2024). Guardar fora do repositório (é público).
3. **Avaliar o risco** para as pessoas. Dados financeiros contam como risco relevante.
4. Se houver risco ou dano relevante, **comunicar à ANPD em até 3 dias úteis** desde que se soube do incidente (Res. CD/ANPD nº 15/2024, art. 6º), pelo formulário do site da ANPD, e **avisar as pessoas afetadas** em linguagem clara (pelo próprio bot). Conferir o texto oficial da resolução antes de comunicar.
5. Corrigir a causa (PR), atualizar `docs/SEGURANCA.md` e registrar uma decisão em `docs/DECISOES.md`.

Fontes consultadas em 08/10/2026: [resumo da Resolução 15/2024 (SMABR)](https://smabr.com/regulamento-de-comunicacao-de-incidente-de-seguranca/), [artigo no Migalhas](https://www.migalhas.com.br/depeso/408328/implementacao-da-comunicacao-de-incidente-de-seguranca).

## Kill-switch

- **Acionado de verdade** (e-mail "Telegrana: kill-switch acionado"): o orçamento de US$ 1 estourou e todas as Lambdas `telegrana-*` pararam. Descobrir a causa do custo no Billing **antes** de religar. Religar: `deploy/README.md`, seção "Religar depois de um acionamento".
- **Testar** sem parar a produção: `deploy/README.md`, seção "Testar o kill-switch de verdade, só no dev". Repetir antes do upgrade da conta AWS.

## Backup e restauração

- **Todo domingo, 03:00**: chega no seu chat de admin `telegrana-prod-backup-AAAA-MM-DD.tgbk`, com tabelas, linhas e tamanho na legenda. Só a chave privada abre.
- **Abrir** (ver os dados, sem restaurar): `uv run python scripts/backup_abre.py <arquivo.tgbk> <chave-privada.txt> <pasta FORA do projeto>`. São dados pessoais em claro: apagar a pasta ao terminar.
- **Restaurar** (perda de dados): **nunca** restaurar dentro do branch `production` em uso, porque o script troca as senhas dos papéis e o bot cairia. Caminho seguro, ensaiado em 08/10/2026:
  1. No Neon, criar um **branch filho** (ex.: `restauracao-AAAA-MM-DD`) e, nele, um **banco vazio** (`create database restaura`).
  2. Pôr no `.env.local` uma variável com a URL do dono desse banco (ex.: `NEON_RESTAURA_URL=...`).
  3. `uv run python scripts/backup_restaura.py <arquivo.tgbk> <chave-privada.txt> NEON_RESTAURA_URL` — aplica as migrações até a versão do backup, carrega e confere as linhas.
  4. Conferir os dados (ex.: `/resumo` num bot de dev apontado para ele).
  5. Para virar a produção: apontar `NEON_OWNER_URL_PROD` para o banco restaurado e rodar `uv run python scripts/ssm_setup.py --rotacionar-banco-prod` e `uv run python scripts/backup_papel.py prod`; depois forçar as Lambdas a lerem o SSM de novo (merge vazio na `main` ou `aws lambda update-function-configuration --function-name telegrana-prod-bot --description "restauracao AAAA-MM-DD"`, idem `rotinas` e `backup`).
- **Perdeu a chave privada**: os backups antigos ficam ilegíveis. Gerar outra com `scripts/backup_chave.py` (novo arquivo); os próximos domingos voltam a funcionar.
- Janela do próprio Neon: até **6 horas** para trás (Restore no console), para acidentes recentes.

## Rotação de segredos

Depois de mudar qualquer valor no SSM, as Lambdas só leem de novo numa instância nova: merge na `main` (o pipeline publica) ou `aws lambda update-function-configuration --function-name <função> --description "rotacao AAAA-MM-DD"`.

| Segredo | Quando trocar | Como |
|---|---|---|
| Token do bot (dev ou prod) | Vazou, ou pessoa saiu com acesso | BotFather `/revoke` → novo token em `TELEGRAM_BOT_TOKEN_<ENV>` no `.env.local` → `uv run python scripts/ssm_setup.py` → `uv run python scripts/deploy_tasks.py webhook --env <env>` |
| Segredo do webhook | Vazou | `uv run python scripts/ssm_setup.py --rotacionar-webhook` → `deploy_tasks.py webhook --env dev` e `--env prod` (o Telegram passa a mandar o novo) |
| Chave do Groq | Vazou | Console do Groq: nova chave, apagar a antiga → `GROQ_API_KEY_<ENV>` no `.env.local` → `ssm_setup.py` |
| Senhas do banco (app e migrador) | Vazou, ou a cada 6 meses | Dev: `uv run python scripts/db_bootstrap.py dev` e `ssm_setup.py`. Prod: `ssm_setup.py --rotacionar-banco-prod` |
| Senha do papel de backup | Vazou | `uv run python scripts/backup_papel.py <env>` |
| Chave do backup | Perdeu ou vazou a privada | `scripts/backup_chave.py` (só o Adriano) |
| Link de convite | Circulou demais | `/link novo` (o antigo é revogado) ou `/link revogar` |
| Pepper do telefone | **Não rotacionar** (os HMACs guardados deixariam de bater). Se vazar: trocar e pedir a cada pessoa para compartilhar o número de novo (`/meus_dados`) | `ssm_setup.py` não troca; mudança manual, com decisão registrada |
| Chave da API e dono do Neon | Vazou | Console do Neon (Account → API keys; Roles → reset password) → `.env.local` |

## Dia a dia do admin

- Convites, pedidos de acesso, recuperação manual e bloqueio: comandos `/link`, `/usuarios` e os botões dos avisos (manual do sistema, seção "Administrador").
- Cotas da IA: o aviso "⚠️ IA: o modelo X já usou 70% da cota" chega no seu chat; a cadeia de modelos segue sozinha. Limites por pessoa: D051.
- Quando a família estiver usando a produção, não use a chave do Groq de prod nas avaliações locais (D038).

## Deploy e volta atrás

- Toda mudança: branch → PR → CI verde → merge com squash → dev → E2E → prod, sozinho.
- **Voltar atrás**: `git revert` do commit do merge num PR novo (nunca reescrever o histórico publicado). Migração já aplicada não se desfaz: corrigir com uma migração nova.

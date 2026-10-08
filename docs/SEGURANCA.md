# Revisão de segurança — Telegrana

> Revisão completa do checklist da seção 8 do `docs/PLANO.md`, feita na S8 em **08/10/2026** (D054). Cada item traz onde está a prova: arquivo, teste ou comando. Refazer esta revisão a cada sprint que mexer em entrada, banco, IA, segredos ou infraestrutura.

Legenda: ✅ atende · ⚠️ atende com ressalva registrada · ➖ opcional, não feito.

## 8.1 Entrada (webhook)

| Item | | Evidência |
|---|---|---|
| Cabeçalho `X-Telegram-Bot-Api-Secret-Token` comparado em tempo constante; recusa sem detalhar | ✅ | `channels/telegram/webhook.py` (`hmac.compare_digest`; resposta vazia) |
| Só `POST` e `application/json`; limite de corpo; parse estrito | ✅ | `webhook.py` (`motivo_recusa`: método, tipo, tamanho até `MAX_BODY_BYTES = 256 KB`, segredo; a recusa não detalha o motivo, que só vai para o log) |
| `setWebhook` com `allowed_updates` mínimo, `max_connections` baixo e `drop_pending_updates` | ✅ | `scripts/deploy_tasks.py` (webhook), conferido a cada deploy pelo CI |
| Idempotência por `update_id` | ✅ | `entrypoints/bot.py` (insert em `processed_updates` com chave única) |
| Só chat privado; o bot sai de grupos | ✅ | `channels/telegram/adaptador.py` (`chat.type != "private"`), `api.leave_chat` |
| Faixas de IP do Telegram | ➖ | Opcional no plano; o segredo do cabeçalho já autentica |

## 8.2 Autorização e isolamento

| Item | | Evidência |
|---|---|---|
| Toda tabela com dado de conta tem `account_id` e RLS forçado | ✅ | Migrações 0001–0015; `tests/isolation/test_isolamento.py` (todas as tabelas classificadas: isoladas ou globais) |
| App sem dono, sem `BYPASSRLS`; migrações com outro papel, só no pipeline | ✅ | `infra/bootstrap.py`; teste de atributos dos papéis na suíte de isolamento |
| Conta da sessão por transação (`set_config(..., true)`), a partir do `from.id` | ✅ | `infra/db.py` (`account_context`); `core/roteador.py` |
| Chaves e FKs compostas `(account_id, id)` | ✅ | Migrações (ex.: 0010, 0012) |
| Botões e respostas revalidados na conta da sessão | ✅ | Tratadores (`repo.lancamento` sob RLS; `seg.longo`); D049: resposta escrita vira a MESMA ação do botão, revalidada; perguntas de apagar, código, termos e admin só com toque |
| Suíte de isolamento no CI, bloqueando o deploy | ✅ | Job `testes` (obrigatório no ruleset) |
| Admin por `ADMIN_TELEGRAM_ID`; ações administrativas em `audit_log` | ✅ | `core/roteador.py`, `core/admin.py` (`repo.audita`) |
| Papel de backup só leitura, por políticas explícitas | ✅ | Migração 0015; teste "toda tabela com RLS tem a política de backup" (D052) |

## 8.3 IA

| Item | | Evidência |
|---|---|---|
| Texto até 1.000 caracteres; áudio até 2 min / 20 MB antes da IA | ✅ | `ai/prompt.py` (`LIMITE_MENSAGEM`), `core/audio.py` |
| Saída só por esquema Pydantic estrito; nada vira SQL, comando, URL ou acesso | ✅ | `core/extracao.py` (todos os modelos `extra="forbid"`, enums); escolha (D049) só aponta um número; conversa (D050) só texto + tela de lista fixa, links removidos |
| Sem histórico de outras contas; sem ferramentas que acessem o banco | ✅ | Prompts recebem só a mensagem (+ categorias da própria conta); a conversa não recebe dado da conta |
| Uso da IA por pessoa limitado | ✅ | `core/limites.py` (D051) |

## 8.4 Segredos

| Item | | Evidência |
|---|---|---|
| Produção: SSM SecureString, lidos no cold start, em memória | ✅ | `infra/config.py` (`repr=False`); cada Lambda lê só os seus parâmetros (`deploy/app.yaml`) |
| Local: `.env.local` fora do Git | ✅ | `.gitignore` (`.env`, `.env.*`) |
| CI com OIDC e papel mínimo, só `main` | ✅ | `deploy/bootstrap.yaml` (`telegrana-github-deploy`) |
| gitleaks no pre-commit e no CI; secret scanning e push protection | ✅ | `.pre-commit-config.yaml`; job `segredos`; GitHub: secret scanning, push protection e Dependabot **enabled** (conferido em 08/10/2026) |
| Rotação documentada para cada segredo | ✅ | `docs/OPERACAO.md`, seção "Rotação de segredos" |

## 8.5 Dados e privacidade

| Item | | Evidência |
|---|---|---|
| Logs sem conteúdo; retenção de 7 dias | ✅ | Revisados todos os `extra=` (só ids, rótulos, tempos e nomes de erro); erros da Bot API registram só método, HTTP e a descrição do Telegram. Grupos de log com 7 dias (`app.yaml`, `bootstrap.yaml`) |
| Código de recuperação com `protect_content` | ✅ | `Saida.protegida` → `adaptador.py` |
| Telefone só como HMAC com pepper; contato só do próprio remetente | ✅ | `core/seguranca.py`; `adaptador.py` (`contato_alheio`) |
| Áudio só em memória, descartado | ✅ | `core/audio.py` (`baixar()` só ao transcrever) |
| Direitos do titular | ✅ | `/meus_dados`, `/corrigir_nome`, `/exportar` (S7), `/apagar_conta` |
| TLS verificado no Neon | ✅ | `infra/db.py` (`sslmode=verify-full` + certifi) |
| Backup cifrado; a chave só com o admin | ✅ | D052 (X25519 + ChaCha20-Poly1305) |

## 8.6 Abuso e disponibilidade

| Item | | Evidência |
|---|---|---|
| Limite por conta (minuto e dia) e IA contada por conta | ✅ | `core/limites.py`, migração 0014 (D051: 40/min, 600/dia, 200 IA, 60 min de áudio, 20 arquivos) |
| Quem não tem conta não aciona IA nem arquivos | ✅ | `core/cadastro.py` (sem conta = só entrada); pedidos de acesso limitados por hora |
| Timeouts em todas as chamadas externas | ✅ | `httpx.Timeout` em `api.py`, `groq.py` e `whisper.py`; `connect_timeout` no banco; `statement_timeout` nos papéis |
| Alarmes de erro | ✅ | `deploy/app.yaml` (4 alarmes em prod → e-mail, D051/D052) |

## 8.7 Cadeia de suprimentos e código

| Item | | Evidência |
|---|---|---|
| Dependências travadas com hash | ✅ | `uv.lock` (545 hashes); a Lambda instala só pelo lock |
| CI: ruff, mypy estrito, bandit, pip-audit, testes, isolamento, avaliação da IA | ✅ | `.github/workflows/ci.yml`; em 08/10/2026: bandit sem achados, pip-audit sem vulnerabilidades |
| Dependabot | ✅ | `.github/dependabot.yml` (uv e GitHub Actions, semanal) |
| Sem pacotes obscuros | ✅ | Dependências: psycopg, pydantic, httpx, certifi, fpdf2, openpyxl, cryptography (PyCA) |

## 8.8 Conta AWS

| Item | | Evidência |
|---|---|---|
| MFA na root; root fora do dia a dia | ✅ | S0.2 (`check_setup.py`) |
| Acesso de desenvolvimento com permissões mínimas | ⚠️ | `adriano-dev` segue **administrador** por decisão do Adriano (D051, risco aceito). Mitigação: MFA, `aws login` com sessão de até 12 h, nenhuma access key, deploy da aplicação só pelo CI |
| IAM por função | ✅ | Um papel por Lambda (`app.yaml`), todos sob o limite de permissões `telegrana-limite-lambdas` |
| CloudTrail | ✅ | Histórico de eventos (90 dias, grátis) ativo; trilha em S3 não criada (decisão na D054) |
| Kill-switch testado | ✅ | D053 (teste real no dev em 08/10/2026) |

## Achados desta revisão

- Nenhuma falha encontrada; nenhum item obrigatório em aberto.
- Ressalvas registradas: administrador do `adriano-dev` (risco aceito); verificação de IP do Telegram (opcional, não feita).

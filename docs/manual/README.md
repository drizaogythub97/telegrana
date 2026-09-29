# Guias da S0 — ações manuais do Adriano

> Guias escritos em **29/09/2026**, com os procedimentos pesquisados na documentação oficial de cada plataforma nessa data.

## Antes de começar (2 minutos)

1. O `.env.local` já existe na raiz do projeto, criado a partir do `.env.local.example`, com tudo em branco. Se não existir: `Copy-Item .env.local.example .env.local`.
2. Instale as dependências do validador (uma vez só):

   ```powershell
   python -m pip install --require-hashes -r scripts/requirements-check.txt
   ```

3. A cada fase concluída, rode `python scripts/check_setup.py s0.X` e depois avise no chat: **"S0.X concluída"**.

**Regra única:** segredo só no `.env.local`. Nunca no chat, em print, e-mail ou mensagem.

## Ordem de execução

| # | Guia | Tempo | Depende de | O que você devolve |
|---|---|---|---|---|
| 1 | [S0.1 — GitHub](S0.1-github.md) | 15 min | — | `GITHUB_REPO` |
| 2 | [S0.2 — AWS](S0.2-aws.md) | 45–60 min | — | sessão `aws login` + autorização no chat |
| 3 | [S0.3 — Neon](S0.3-neon.md) | 15 min | S0.1 (login pelo GitHub) | `NEON_OWNER_URL_PROD`, `NEON_OWNER_URL_DEV` |
| 4 | [S0.4 — Groq](S0.4-groq.md) | 10 min | — | `GROQ_API_KEY_PROD`, `GROQ_API_KEY_DEV` + "ZDR ativo" |
| 5 | [S0.5 — Telegram](S0.5-telegram.md) | 25 min | — | 2 tokens, 2 usernames, `api_id`, `api_hash`, `ADMIN_TELEGRAM_ID` |
| 6 | [S0.6 — Android](S0.6-android.md) | 15 min | — | aparelho em `adb devices` |
| 7 | [S0.7 — Marca e dados](S0.7-marca-e-dados.md) | 1h30–2h (pode espalhar por dias) | — | arquivos em `tests/eval/data/` + revisão das categorias no chat |

**Total:** cerca de 2h15 de fases rápidas (S0.1 a S0.6), mais a coleta de dados da S0.7.

Sugestão para uma sentada só: **S0.1 → S0.4 → S0.5 → S0.3 → S0.6 → S0.2**. As rápidas primeiro; a AWS, mais longa, com calma no fim. A S0.7 vai sendo feita aos poucos e **não bloqueia a S1**: só é necessária na S2.

## O que o agente faz depois de cada fase

| Fase | O agente em seguida |
|---|---|
| S0.1 | configura o remoto, faz o primeiro push e cria as regras da branch `main` |
| S0.2 | audita a conta em todas as regiões (somente leitura) e mostra a lista; depois cria orçamentos, OIDC e kill-switch por IaC |
| S0.3 | (na S1) cria os papéis `migrator` e `app` e as migrações com RLS |
| S0.4 | registra os limites confirmados |
| S0.5 | (na S1) cria o bot do servidor de testes e configura descrição, comandos e foto |
| S0.6 | faz uma captura de teste da tela do Telegram, com a sua autorização |
| S0.7 | (na S2/S3) monta as saídas esperadas para você revisar |

## Validação completa

```powershell
python scripts/check_setup.py
```

Resultado: `0` = tudo certo · `1` = alguma falha · `2` = sem falhas, mas com itens pendentes.

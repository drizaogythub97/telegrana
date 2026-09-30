# Desenvolvimento — Telegrana

Guia rápido para quem (pessoa ou agente) vai mexer no código.

## Ferramentas

| Ferramenta | Uso |
|---|---|
| Python **3.14** | mesma versão do runtime `python3.14` da Lambda (D029) |
| **uv** | dependências e ambiente; `uv.lock` com hashes (instalação com `--locked`) |
| ruff | lint + formatação |
| mypy | tipos, **estrito** em `src/` e `scripts/` |
| pytest | testes (`unit`, `integration`, `isolation`, `e2e`) |
| bandit, pip-audit | segurança do código e das dependências |
| pre-commit | verificações locais antes de cada commit (inclui gitleaks e a trava de dados pessoais) |

## Primeira vez na máquina

```powershell
uv sync --locked
uv run pre-commit install
```

## Antes de abrir um PR (o CI roda o mesmo)

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run bandit -c pyproject.toml -r src scripts
uv run pip-audit --skip-editable
uv run pytest
```

## Banco nos testes (D018)

- **CI**: Postgres 18 em container, por meio de `TELEGRANA_TEST_DATABASE_URL`.
- **Local**: sem Docker. Os testes usam a branch **`testes`** do Neon: `TELEGRANA_TEST_DATABASE_URL` no `.env.local` (dono da branch; o conftest lê sozinho). Cada sessão cria e apaga um banco descartável `telegrana_t_*`. Nunca aponte para `dev` ou produção.
- **Preparar/rotacionar a branch dev**: `uv run python scripts/db_bootstrap.py dev` (papéis, migrações, URLs no `.env.local`).
- **Nova tabela** = nova migração `NNNN_nome.sql` **e** classificação em `ISOLADAS` ou `GLOBAIS` em `tests/isolation/test_isolamento.py` (o meta-teste falha se faltar).

## Regras que os testes já garantem

- **Arquitetura** (`tests/unit/test_arquitetura.py`): `core/`, `ai/` e `exports/` não importam canais (regra de ouro 10).
- **Segredos** (`tests/unit/test_check_setup.py`): toda variável marcada como `SEGREDO` no `.env.local.example` precisa ser mascarada pelo `check_setup`.
- **Dados pessoais** (pre-commit): nada de `tests/eval/data/` nem `.env*` entra no Git, mesmo com `git add -f`.

## Fluxo de Git

A `main` é protegida (ruleset `protege-main`): branch → PR → CI verde → merge com squash. Mensagens de commit em pt-BR.

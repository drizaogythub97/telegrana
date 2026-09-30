#!/usr/bin/env python3
"""Valida as entregas manuais da S0 do Telegrana sem nunca imprimir segredos.

Uso (na raiz do projeto):
    python scripts/check_setup.py                  # todas as micro-fases
    python scripts/check_setup.py s0.3 s0.4        # só algumas (aceita "3", "s0.3")
    python scripts/check_setup.py --descobrir-admin-id

Lê as variáveis de ".env.local". Todas as chamadas são somente leitura: nada é
criado, alterado ou apagado em nenhum serviço.

Dependências: biblioteca padrão; para a S0.3 (Neon), "psycopg" e "certifi":
    python -m pip install --require-hashes -r scripts/requirements-check.txt

Código de saída: 0 = tudo certo; 1 = alguma falha; 2 = sem falhas, mas com itens
pendentes (variáveis ainda em branco).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import struct
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env.local"
TIMEOUT = 20

# Variáveis cujo valor é segredo: nunca aparecem na saída.
SECRET_KEYS = (
    "NEON_OWNER_URL_PROD",
    "NEON_OWNER_URL_DEV",
    "GROQ_API_KEY_PROD",
    "GROQ_API_KEY_DEV",
    "TELEGRAM_BOT_TOKEN_PROD",
    "TELEGRAM_BOT_TOKEN_DEV",
    "TELEGRAM_API_HASH",
    "NEON_API_KEY",
)

GROQ_REQUIRED_MODELS = ("openai/gpt-oss-20b", "openai/gpt-oss-120b", "whisper-large-v3")
AUDIO_EXTENSIONS = {".ogg", ".oga", ".opus", ".m4a", ".mp3", ".wav", ".webm", ".flac"}
MIN_AWS_CLI = (2, 32, 0)  # "aws login" exige 2.32.0+


# ---------------------------------------------------------------------------
# Saída com mascaramento de segredos
# ---------------------------------------------------------------------------


class Reporter:
    """Imprime resultados e garante que nenhum segredo conhecido saia na tela."""

    def __init__(self) -> None:
        self._secrets: set[str] = set()
        self.counts = {"ok": 0, "falha": 0, "aviso": 0, "falta": 0}

    def add_secret(self, value: str | None) -> None:
        if value and len(value) >= 6:
            self._secrets.add(value)

    def redact(self, text: str) -> str:
        # Os mais longos primeiro, para não sobrar pedaço de segredo.
        for secret in sorted(self._secrets, key=len, reverse=True):
            text = text.replace(secret, "«oculto»")
        return text

    def _emit(self, tag: str, msg: str, hint: str | None = None) -> None:
        print(self.redact(f"  [{tag}] {msg}"))
        if hint:
            print(self.redact(f"          → {hint}"))

    def section(self, title: str) -> None:
        print(f"\n{title}")

    def ok(self, msg: str) -> None:
        self.counts["ok"] += 1
        self._emit(" OK  ", msg)

    def fail(self, msg: str, hint: str | None = None) -> None:
        self.counts["falha"] += 1
        self._emit("FALHA", msg, hint)

    def warn(self, msg: str, hint: str | None = None) -> None:
        self.counts["aviso"] += 1
        self._emit("AVISO", msg, hint)

    def missing(self, msg: str, hint: str | None = None) -> None:
        self.counts["falta"] += 1
        self._emit("FALTA", msg, hint)

    def info(self, msg: str) -> None:
        self._emit(" ... ", msg)


R = Reporter()


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------


def load_env(path: Path) -> dict[str, str]:
    """Lê KEY=valor, ignorando comentários e linhas vazias. Aspas são removidas."""
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        env[key.strip()] = value
    return env


def run(cmd: list[str], timeout: int = TIMEOUT) -> tuple[int, str, str] | None:
    """Executa um comando; devolve None se o programa não existir."""
    exe = shutil.which(cmd[0])
    if exe is None:
        return None
    try:
        proc = subprocess.run(
            [exe, *cmd[1:]],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=ROOT,
        )
    except subprocess.TimeoutExpired:
        return 124, "", "tempo esgotado"
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def first_line(text: str) -> str:
    return text.strip().splitlines()[0][:200] if text.strip() else ""


def http_json(url: str, headers: dict[str, str] | None = None) -> tuple[int | None, object]:
    """GET que devolve (status, json). Nunca propaga a URL (pode conter token)."""
    if not url.startswith("https://"):
        raise ValueError("só URLs https são permitidas")
    req = urllib.request.Request(
        url, headers={"User-Agent": "telegrana-check-setup/1.0", **(headers or {})}
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # nosec B310 — https verificado acima
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except ValueError, OSError:
            return exc.code, {}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return None, {"erro": type(exc).__name__}


def mask_tail(value: str, keep: int = 4) -> str:
    return "*" * max(len(value) - keep, 0) + value[-keep:]


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", text)[:3])


# ---------------------------------------------------------------------------
# S0.1 — GitHub
# ---------------------------------------------------------------------------


def check_github(env: dict[str, str]) -> None:
    R.section("S0.1 · GitHub")
    repo = env.get("GITHUB_REPO", "")

    rc = run(["git", "config", "user.email"])
    if rc and rc[0] == 0 and rc[1].endswith("@users.noreply.github.com"):
        R.ok("e-mail dos commits deste repositório é o noreply do GitHub")
    else:
        R.fail(
            "e-mail dos commits deste repositório não é o noreply do GitHub",
            "o repositório é público: siga o passo 'E-mail privado' do guia S0.1",
        )

    if not repo:
        R.missing("GITHUB_REPO em branco", "preencha no .env.local (ex.: usuario/telegrana)")
        return
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", repo):
        R.fail("GITHUB_REPO fora do formato dono/nome")
        return

    if run(["gh", "--version"]) is None:
        R.fail("GitHub CLI (gh) não encontrado", "instale em https://cli.github.com")
        return
    status = run(["gh", "auth", "status"])
    if not status or status[0] != 0:
        R.fail("gh não está autenticado", "rode: gh auth login")
        return
    R.ok("gh autenticado")

    res = run(["gh", "api", f"repos/{repo}"])
    if not res or res[0] != 0:
        R.fail(
            f"repositório {repo} não encontrado ou sem acesso", first_line(res[2]) if res else None
        )
        return
    data = json.loads(res[1])
    if data.get("visibility") == "public":
        R.ok(f"repositório {repo} existe e é público (D015)")
    else:
        R.fail(f"repositório está '{data.get('visibility')}'; a decisão D015 é público")
    if not data.get("permissions", {}).get("admin"):
        R.fail("a conta do gh não é administradora do repositório")

    sa = data.get("security_and_analysis") or {}
    features = {  # nosec B105 — rótulos de tela, não senhas
        "secret_scanning": "Secret Protection (secret scanning)",
        "secret_scanning_push_protection": "Push protection",
        "dependabot_security_updates": "Dependabot security updates",
    }
    for key, label in features.items():
        if (sa.get(key) or {}).get("status") == "enabled":
            R.ok(f"{label} ativo")
        else:
            R.fail(f"{label} desativado", "Settings → Advanced Security (guia S0.1)")

    alerts = run(["gh", "api", f"repos/{repo}/vulnerability-alerts", "--silent"])
    if alerts and alerts[0] == 0:
        R.ok("Dependabot alerts ativo")
    else:
        R.fail("Dependabot alerts desativado", "Settings → Advanced Security → Dependabot alerts")

    pvr = run(["gh", "api", f"repos/{repo}/private-vulnerability-reporting"])
    if pvr and pvr[0] == 0 and json.loads(pvr[1] or "{}").get("enabled"):
        R.ok("Private vulnerability reporting ativo")
    else:
        R.warn("Private vulnerability reporting desativado (recomendado no guia)")

    wf = run(["gh", "api", f"repos/{repo}/actions/permissions/workflow"])
    if wf and wf[0] == 0:
        perms = json.loads(wf[1])
        if perms.get("default_workflow_permissions") == "read" and not perms.get(
            "can_approve_pull_request_reviews"
        ):
            R.ok("Actions: GITHUB_TOKEN somente leitura por padrão")
        else:
            R.fail(
                "Actions: GITHUB_TOKEN com escrita por padrão ou aprovando PRs",
                "Settings → Actions → General → Workflow permissions (guia S0.1)",
            )
    else:
        R.warn("não consegui ler as permissões do Actions")

    fork = run(["gh", "api", f"repos/{repo}/actions/permissions/fork-pr-contributor-approval"])
    if fork and fork[0] == 0:
        policy = json.loads(fork[1]).get("approval_policy")
        if policy == "all_external_contributors":
            R.ok("Actions: PRs de fora exigem aprovação para rodar")
        else:
            R.fail(
                f"Actions: aprovação de PRs de fora está '{policy}'",
                "Settings → Actions → General → 'Require approval for all external contributors'",
            )
    else:
        R.warn("não consegui ler a política de PRs de forks (confira manualmente)")

    origin = run(["git", "remote", "get-url", "origin"])
    if not origin or origin[0] != 0:
        R.missing("remoto 'origin' não configurado no git local", "o agente configura após a S0.1")
    elif repo.lower() not in origin[1].lower():
        R.fail("o remoto 'origin' aponta para outro repositório")
    else:
        ls = run(["git", "ls-remote", "origin"], timeout=40)
        if ls and ls[0] == 0:
            R.ok("git consegue acessar o repositório remoto")
        else:
            R.fail("git não consegue acessar o remoto", "rode: gh auth setup-git")


# ---------------------------------------------------------------------------
# S0.2 — AWS
# ---------------------------------------------------------------------------


def aws(args: list[str], profile: str) -> tuple[int, str, str] | None:
    return run(["aws", *args, "--profile", profile, "--output", "json"], timeout=40)


def check_aws(env: dict[str, str]) -> None:
    R.section("S0.2 · AWS")
    profile = env.get("AWS_PROFILE") or "telegrana"
    region = env.get("AWS_REGION") or "us-east-1"

    ver = run(["aws", "--version"])
    if ver is None:
        R.missing("AWS CLI não encontrado", "instale conforme o passo 5 do guia S0.2")
        return
    found = version_tuple(ver[1] or ver[2])
    if found >= MIN_AWS_CLI:
        R.ok(f"AWS CLI {'.'.join(map(str, found))}")
    else:
        R.fail(f"AWS CLI {'.'.join(map(str, found))} é antigo; o 'aws login' exige 2.32.0+")
        return

    ident = aws(["sts", "get-caller-identity"], profile)
    if not ident or ident[0] != 0:
        R.fail(
            f"perfil '{profile}' sem sessão válida: {first_line(ident[2]) if ident else ''}",
            f"rode: aws login --profile {profile}",
        )
        return
    who = json.loads(ident[1])
    arn = who.get("Arn", "")
    account = who.get("Account", "")
    if arn.endswith(":root"):
        R.fail("o perfil está usando a conta ROOT", "use o usuário IAM criado no guia S0.2")
        return
    user_name = arn.rsplit("/", 1)[-1]
    R.ok(
        f"perfil '{profile}' autenticado como usuário IAM '{user_name}' (conta {mask_tail(account)})"
    )

    reg = run(["aws", "configure", "get", "region", "--profile", profile])
    if reg and reg[1] == region:
        R.ok(f"região padrão do perfil: {region}")
    else:
        R.fail(
            f"região do perfil é '{reg[1] if reg else ''}', esperado {region}",
            f"rode: aws configure set region {region} --profile {profile}",
        )

    summary = aws(["iam", "get-account-summary"], profile)
    if summary and summary[0] == 0:
        smap = json.loads(summary[1]).get("SummaryMap", {})
        if smap.get("AccountMFAEnabled") == 1:
            R.ok("MFA ativo na conta root")
        else:
            R.fail("MFA NÃO está ativo na conta root", "passo 2 do guia S0.2")
        if smap.get("AccountAccessKeysPresent") == 0:
            R.ok("root sem chaves de acesso")
        else:
            R.fail("a root tem chaves de acesso", "apague-as (passo 3 do guia S0.2)")
    else:
        R.warn("não consegui ler o resumo da conta (iam:GetAccountSummary)")

    mfa = aws(["iam", "list-mfa-devices", "--user-name", user_name], profile)
    if mfa and mfa[0] == 0 and json.loads(mfa[1]).get("MFADevices"):
        R.ok(f"MFA ativo no usuário IAM '{user_name}'")
    else:
        R.fail(f"usuário IAM '{user_name}' sem MFA", "passo 7 do guia S0.2")

    keys = aws(["iam", "list-access-keys", "--user-name", user_name], profile)
    if keys and keys[0] == 0 and not json.loads(keys[1]).get("AccessKeyMetadata"):
        R.ok("usuário IAM sem chaves de acesso de longo prazo")
    elif keys and keys[0] == 0:
        R.warn("o usuário IAM tem chaves de acesso; o guia usa só 'aws login' (apague-as)")

    org = aws(["organizations", "describe-organization"], profile)
    if org and "AWSOrganizationsNotInUseException" in org[2]:
        R.ok("conta sem AWS Organizations (assunção da seção 14 confirmada)")
    elif org and org[0] == 0:
        R.warn("a conta pertence a uma AWS Organization: o agente avaliará SCPs para o kill-switch")
    else:
        R.warn("não consegui verificar o AWS Organizations")

    sam = run(["sam", "--version"])
    if sam and sam[0] == 0:
        R.ok(f"AWS SAM CLI {'.'.join(map(str, version_tuple(sam[1])))}")
    else:
        R.missing("AWS SAM CLI não encontrado", "passo 11 do guia S0.2")


# ---------------------------------------------------------------------------
# S0.3 — Neon
# ---------------------------------------------------------------------------


NEON_API = "https://console.neon.tech/api/v2"


def check_neon_api(env: dict[str, str]) -> None:
    """Chave de API do projeto (gestão: branches, senhas). Só leitura aqui."""
    key = env.get("NEON_API_KEY", "")
    if not key:
        R.missing("NEON_API_KEY em branco", "guia S0.3, passo 5 (chave Project-scoped)")
        return
    auth = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    # Chave pessoal consegue listar as chaves pessoais do usuário; a Project-scoped, não.
    status, data = http_json(f"{NEON_API}/api_keys", auth)
    if status == 200:
        R.fail(
            "NEON_API_KEY é uma chave PESSOAL (acessa todos os projetos e pode apagá-los)",
            "crie uma Project-scoped em Organization settings → API keys e revogue a pessoal",
        )
        return
    # Chave Project-scoped não lista projetos: o id vem do .env.local (não é segredo).
    project_id = env.get("NEON_PROJECT_ID", "")
    if not project_id:
        R.missing("NEON_PROJECT_ID em branco", "Neon → projeto → Settings → General → Project ID")
        return
    status, data = http_json(f"{NEON_API}/projects/{urllib.parse.quote(project_id)}", auth)
    if status == 401:
        R.fail("NEON_API_KEY recusada (401)")
        return
    if status in (403, 404):
        R.fail(f"a chave não acessa o projeto {project_id} ({status}): escopo ou id errado")
        return
    if status != 200 or not isinstance(data, dict):
        R.fail(f"API do Neon: resposta inesperada ({status or data})")
        return
    project = data.get("project", {})
    R.ok(
        f"NEON_API_KEY válida e restrita ao projeto '{project.get('name')}' "
        f"({project.get('region_id')}, Postgres {project.get('pg_version')})"
    )
    if project.get("region_id") != "aws-us-east-1":
        R.fail("o projeto não está em aws-us-east-1")
    listing, _ = http_json(f"{NEON_API}/projects", auth)
    if listing == 200:
        R.warn("a chave consegue listar outros projetos: prefira uma chave Project-scoped")

    status, data = http_json(f"{NEON_API}/projects/{urllib.parse.quote(project_id)}/branches", auth)
    if status != 200 or not isinstance(data, dict):
        R.fail(f"não consegui listar as branches ({status})")
        return
    branches = {b.get("name"): b for b in data.get("branches", [])}
    for name in ("production", "dev"):
        branch = branches.get(name)
        if branch is None:
            R.fail(f"branch '{name}' não existe no projeto")
        elif branch.get("expires_at"):
            R.fail(
                f"branch '{name}' tem expiração automática ({branch['expires_at']})",
                "Branches → dev → desligue a expiração (senão ela será apagada)",
            )
        else:
            R.ok(f"branch '{name}' existe e não expira")


def check_neon(env: dict[str, str]) -> None:
    R.section("S0.3 · Neon Postgres")
    check_neon_api(env)
    urls = {
        "production": env.get("NEON_OWNER_URL_PROD", ""),
        "dev": env.get("NEON_OWNER_URL_DEV", ""),
    }
    hosts: dict[str, str] = {}

    for branch, url in urls.items():
        if not url:
            R.missing(f"string de conexão da branch '{branch}' em branco")
            continue
        parsed = urllib.parse.urlsplit(url)
        R.add_secret(parsed.password)
        host = parsed.hostname or ""
        problems = []
        if parsed.scheme not in ("postgresql", "postgres"):
            problems.append("não começa com postgresql://")
        if not host.endswith(".neon.tech"):
            problems.append("o host não é do Neon")
        if "us-east-1" not in host:
            problems.append("o host não está em us-east-1")
        if not parsed.password:
            problems.append("sem senha")
        if problems:
            R.fail(f"branch '{branch}': " + "; ".join(problems))
            continue
        if "-pooler" in host:
            R.warn(
                f"branch '{branch}': string com pooler",
                "use a conexão direta (desligue 'Connection pooling' ao copiar)",
            )
        hosts[branch] = host.replace("-pooler", "")

    if len(hosts) == 2 and hosts["production"] == hosts["dev"]:
        R.fail("as duas strings apontam para o mesmo endpoint (mesma branch)")
        return
    if not hosts:
        return

    try:
        import certifi
        import psycopg
    except ImportError:
        R.fail(
            "pacotes psycopg/certifi não instalados",
            "python -m pip install --require-hashes -r scripts/requirements-check.txt",
        )
        return

    for branch, url in urls.items():
        if branch not in hosts:
            continue
        try:
            # verify-full: confere a cadeia de certificados e o nome do host.
            with psycopg.connect(
                url,
                sslmode="verify-full",
                sslrootcert=certifi.where(),
                connect_timeout=TIMEOUT,
                application_name="telegrana-check-setup",
            ) as conn:
                row = conn.execute(
                    "select current_setting('server_version_num')::int, current_user,"
                    " (select rolcreaterole from pg_roles where rolname = current_user),"
                    " pg_has_role(current_user, 'neon_superuser', 'member')"
                ).fetchone()
        except psycopg.Error as exc:
            R.fail(
                f"branch '{branch}': não conectou ({type(exc).__name__}: {first_line(str(exc))})"
            )
            continue
        if row is None:
            R.fail(f"branch '{branch}': a consulta de verificação não retornou dados")
            continue
        version_num, user, createrole, neon_su = row
        major = version_num // 10000
        R.ok(f"branch '{branch}': conectou com TLS verificado como '{user}' (Postgres {major})")
        if major < 17:
            R.warn(f"branch '{branch}': Postgres {major}; o guia pede a versão mais recente (18)")
        if createrole and neon_su:
            R.ok(f"branch '{branch}': papel dono pode criar os papéis migrator e app")
        else:
            R.fail(f"branch '{branch}': o papel não é dono (sem CREATEROLE/neon_superuser)")


# ---------------------------------------------------------------------------
# S0.4 — Groq
# ---------------------------------------------------------------------------


# Limite diário de requisições do gpt-oss-20b em cada projeto do Groq (D025).
GROQ_EXPECTED_RPD = {"prod": 1000, "dev": 400}


def check_groq_project(name: str, key: str) -> None:
    """Descobre o projeto da chave pelo limite diário que o Groq devolve nos cabeçalhos.

    Faz 1 chamada mínima ao gpt-oss-20b (~100 tokens da cota).
    """
    body = json.dumps(
        {
            "model": "openai/gpt-oss-20b",
            "messages": [{"role": "user", "content": "ok"}],
            "max_completion_tokens": 32,
            "reasoning_effort": "low",
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "telegrana-check-setup/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # nosec B310 — URL https fixa
            limit = resp.headers.get("x-ratelimit-limit-requests", "")
    except urllib.error.HTTPError as exc:
        limit = exc.headers.get("x-ratelimit-limit-requests", "") if exc.headers else ""
        if not limit:
            R.warn(f"chave {name}: não consegui ler o projeto (HTTP {exc.code})")
            return
    except urllib.error.URLError, TimeoutError, OSError:
        R.warn(f"chave {name}: não consegui ler o projeto (rede)")
        return
    expected = GROQ_EXPECTED_RPD[name]
    if limit.isdigit() and int(limit) == expected:
        R.ok(f"chave {name} está no projeto telegrana-{name} (limite de {limit} req/dia no 20b)")
    else:
        R.fail(
            f"chave {name} com limite de {limit or '?'} req/dia; esperado {expected}",
            f"a chave foi criada no projeto errado: recrie-a com 'telegrana-{name}' selecionado no topo",
        )


def check_groq(env: dict[str, str]) -> None:
    R.section("S0.4 · Groq")
    keys = {"prod": env.get("GROQ_API_KEY_PROD", ""), "dev": env.get("GROQ_API_KEY_DEV", "")}
    if keys["prod"] and keys["prod"] == keys["dev"]:
        R.fail("as chaves de prod e dev são iguais; crie duas chaves separadas")

    for name, key in keys.items():
        if not key:
            R.missing(f"GROQ_API_KEY_{name.upper()} em branco")
            continue
        if not key.startswith("gsk_"):
            R.warn(f"chave {name} não começa com 'gsk_' (confira se copiou inteira)")
        status, data = http_json(
            "https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {key}"}
        )
        if status == 200 and isinstance(data, dict):
            ids = {m.get("id") for m in data.get("data", [])}
            absent = [m for m in GROQ_REQUIRED_MODELS if m not in ids]
            if absent:
                R.fail(f"chave {name} válida, mas faltam modelos: {', '.join(absent)}")
            else:
                R.ok(f"chave {name} válida; modelos do plano disponíveis")
            check_groq_project(name, key)
        elif status == 401:
            R.fail(f"chave {name} recusada (401): inválida ou apagada")
        else:
            R.fail(f"chave {name}: resposta inesperada ({status or data})")

    R.info(
        "Zero Data Retention não é verificável pela API (ligado pelo agente em 30/09/2026, D025)"
    )


# ---------------------------------------------------------------------------
# S0.5 — Telegram
# ---------------------------------------------------------------------------


def tg(token: str, method: str, params: dict[str, str] | None = None) -> tuple[int | None, object]:
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    return http_json(f"https://api.telegram.org/bot{token}/{method}{query}")


def check_telegram(env: dict[str, str]) -> None:
    R.section("S0.5 · Telegram")
    bots = {
        "prod": (env.get("TELEGRAM_BOT_TOKEN_PROD", ""), env.get("TELEGRAM_BOT_USERNAME_PROD", "")),
        "dev": (env.get("TELEGRAM_BOT_TOKEN_DEV", ""), env.get("TELEGRAM_BOT_USERNAME_DEV", "")),
    }
    ids: dict[str, int] = {}
    for name, (token, username) in bots.items():
        if not token:
            R.missing(f"TELEGRAM_BOT_TOKEN_{name.upper()} em branco")
            continue
        if not re.fullmatch(r"\d{5,15}:[A-Za-z0-9_-]{30,}", token):
            R.fail(f"token {name} fora do formato 123456789:AA... (confira se copiou inteiro)")
            continue
        status, data = tg(token, "getMe")
        if status != 200 or not isinstance(data, dict) or not data.get("ok"):
            R.fail(
                f"token {name} recusado pelo Telegram ({status})",
                "gere outro com /token no @BotFather",
            )
            continue
        me = data["result"]
        ids[name] = me["id"]
        got = me.get("username", "")
        if username and got.lower() != username.lstrip("@").lower():
            R.fail(
                f"token {name} é do bot @{got}, mas TELEGRAM_BOT_USERNAME_{name.upper()} diz @{username}"
            )
        else:
            R.ok(f"token {name} válido: @{got}")
            if not username:
                R.missing(f"TELEGRAM_BOT_USERNAME_{name.upper()} em branco (use: {got})")
        if me.get("can_join_groups"):
            R.fail(
                f"@{got} ainda pode ser adicionado a grupos",
                "@BotFather → /setjoingroups → Disable",
            )
        else:
            R.ok(f"@{got} não entra em grupos")
    if len(ids) == 2 and ids["prod"] == ids["dev"]:
        R.fail("os dois tokens são do mesmo bot; prod e dev precisam ser bots diferentes")

    api_id = env.get("TELEGRAM_API_ID", "")
    api_hash = env.get("TELEGRAM_API_HASH", "")
    if not api_id or not api_hash:
        R.missing("TELEGRAM_API_ID / TELEGRAM_API_HASH em branco")
    elif not api_id.isdigit():
        R.fail("TELEGRAM_API_ID deve ser só números")
    elif not re.fullmatch(r"[0-9a-f]{32}", api_hash):
        R.fail("TELEGRAM_API_HASH deve ter 32 caracteres hexadecimais")
    else:
        R.ok("api_id e api_hash no formato certo (validação completa nos testes E2E da S1)")

    admin = env.get("ADMIN_TELEGRAM_ID", "")
    if not admin:
        R.missing(
            "ADMIN_TELEGRAM_ID em branco", "python scripts/check_setup.py --descobrir-admin-id"
        )
    elif not admin.isdigit():
        R.fail("ADMIN_TELEGRAM_ID deve ser só números")
    elif bots["dev"][0] and "dev" in ids:
        status, data = tg(bots["dev"][0], "getChat", {"chat_id": admin})
        if (
            status == 200
            and isinstance(data, dict)
            and data.get("result", {}).get("type") == "private"
        ):
            R.ok("ADMIN_TELEGRAM_ID confere: é uma conversa privada com o bot de dev")
        else:
            R.warn(
                "o bot de dev não encontrou o ADMIN_TELEGRAM_ID",
                "mande /start ao bot de dev e rode --descobrir-admin-id",
            )
    else:
        R.ok("ADMIN_TELEGRAM_ID preenchido")


def discover_admin_id(env: dict[str, str]) -> int:
    """Lê as últimas mensagens do bot de dev e mostra o id de quem mandou /start."""
    token = env.get("TELEGRAM_BOT_TOKEN_DEV", "")
    R.add_secret(token)
    if not token:
        print("Preencha TELEGRAM_BOT_TOKEN_DEV no .env.local primeiro.")
        return 1
    status, data = tg(token, "getUpdates", {"timeout": "0", "allowed_updates": '["message"]'})
    if status == 409:
        print("O bot de dev tem webhook configurado; esta função só serve antes da S1.")
        return 1
    if status != 200 or not isinstance(data, dict):
        print(R.redact(f"O Telegram recusou a consulta ({status})."))
        return 1
    senders = {}
    for upd in data.get("result", []):
        msg = upd.get("message") or {}
        if msg.get("chat", {}).get("type") == "private" and msg.get("text", "").startswith(
            "/start"
        ):
            sender = msg.get("from", {})
            senders[sender.get("id")] = sender.get("first_name", "")
    if not senders:
        print(
            "Nenhum /start encontrado. Abra o bot de dev no Telegram, toque em Iniciar e rode de novo."
        )
        return 1
    print("Quem mandou /start ao bot de dev:")
    for uid, first_name in senders.items():
        print(f"  {uid}  ({first_name})")
    print("\nCopie o SEU número para ADMIN_TELEGRAM_ID no .env.local.")
    return 0


# ---------------------------------------------------------------------------
# S0.6 — Android
# ---------------------------------------------------------------------------


def check_android(env: dict[str, str]) -> None:
    R.section("S0.6 · Celular Android (adb)")
    listing = run(["adb", "devices", "-l"])
    if listing is None:
        R.fail("adb não encontrado no PATH", "passo 1 do guia S0.6")
        return
    lines = [ln for ln in listing[1].splitlines()[1:] if ln.strip()]
    devices = [ln.split()[0] for ln in lines if len(ln.split()) > 1 and ln.split()[1] == "device"]
    if any(" unauthorized" in ln for ln in lines):
        R.fail("aparelho 'unauthorized'", "desbloqueie o celular e aceite a depuração")
    wanted = env.get("ADB_DEVICE", "")
    if wanted:
        devices = [d for d in devices if d == wanted]
    if not devices:
        R.missing("nenhum aparelho conectado", "adb connect IP:PORTA (guia S0.6, passo 5)")
        return
    # O mesmo celular pode aparecer duas vezes (conexão manual + reconexão via mDNS).
    by_hw: dict[str, str] = {}
    for dev in devices:
        res = run(["adb", "-s", dev, "shell", "getprop", "ro.serialno"])
        by_hw.setdefault(res[1] if res and res[0] == 0 and res[1] else dev, dev)
    if len(by_hw) > 1:
        R.warn("mais de um aparelho conectado; usando o primeiro (defina ADB_DEVICE)")
    serial = next(iter(by_hw.values()))
    if ":" in serial or "_adb-tls-connect" in serial:
        R.ok("aparelho conectado por Wi-Fi")
    else:
        R.warn("aparelho conectado por USB; o plano prevê depuração por Wi-Fi")

    def shell(*args: str) -> str:
        res = run(["adb", "-s", serial, "shell", *args])
        return res[1] if res and res[0] == 0 else ""

    release = shell("getprop", "ro.build.version.release")
    model = shell("getprop", "ro.product.model")
    major = version_tuple(release)[:1]
    if major and major[0] >= 11:
        R.ok(f"{model or 'aparelho'} com Android {release}")
    else:
        R.fail(f"Android {release or '?'}: a depuração por Wi-Fi exige Android 11+")

    packages = shell("pm", "list", "packages", "org.telegram.messenger")
    if "org.telegram.messenger" in packages:
        R.ok("Telegram instalado no aparelho")
    else:
        R.fail("Telegram oficial não encontrado no aparelho")


# ---------------------------------------------------------------------------
# S0.7 — Marca e dados
# ---------------------------------------------------------------------------


def png_size(path: Path) -> tuple[int, int] | None:
    with path.open("rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", head[16:24])
    return width, height


def check_brand_and_data(env: dict[str, str]) -> None:
    del env
    R.section("S0.7 · Marca e dados de avaliação")
    logo = ROOT / "assets" / "brand" / "logo-original.png"
    if not logo.exists():
        R.missing("assets/brand/logo-original.png não encontrado")
    else:
        size = png_size(logo)
        if size is None:
            R.fail("logo-original.png não é um PNG válido")
        elif min(size) < 640:
            R.warn(f"logo com {size[0]}x{size[1]}; o ícone do bot pede pelo menos 640x640")
        else:
            R.ok(f"logo encontrada ({size[0]}x{size[1]})")

    data_dir = ROOT / "tests" / "eval" / "data"
    ignored = run(["git", "check-ignore", "-q", "tests/eval/data/mensagens.txt"])
    if ignored and ignored[0] == 0:
        R.ok("tests/eval/data/ está fora do Git (dados reais não vão para o repositório público)")
    else:
        R.fail("tests/eval/data/ NÃO está ignorado pelo Git: pare e avise o agente")

    msgs = data_dir / "mensagens.txt"
    if msgs.exists():
        count = sum(
            1
            for ln in msgs.read_text(encoding="utf-8-sig").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        )
        if count >= 40:
            R.ok(f"mensagens.txt com {count} mensagens")
        else:
            R.missing(f"mensagens.txt com {count} mensagens (meta: 40 a 60)")
    else:
        R.missing("tests/eval/data/mensagens.txt não encontrado")

    audio_dir = data_dir / "audios"
    audios = (
        {p.name for p in audio_dir.iterdir() if p.suffix.lower() in AUDIO_EXTENSIONS}
        if audio_dir.is_dir()
        else set()
    )
    if len(audios) >= 15:
        R.ok(f"{len(audios)} áudios em tests/eval/data/audios/")
    else:
        R.missing(f"{len(audios)} áudios em tests/eval/data/audios/ (meta: 15 a 20)")

    index = data_dir / "audios.txt"
    if audios and index.exists():
        described = set()
        for ln in index.read_text(encoding="utf-8-sig").splitlines():
            name, sep, said = ln.partition("|")
            if sep and said.strip():
                described.add(name.strip())
        without = len(audios - described)
        orphan = len(described - audios)
        if without == 0 and orphan == 0:
            R.ok("audios.txt descreve todos os áudios")
        else:
            R.fail(f"audios.txt: {without} áudio(s) sem descrição, {orphan} linha(s) sem arquivo")
    elif audios:
        R.missing("tests/eval/data/audios.txt não encontrado")


# ---------------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------------

PHASES: dict[str, Callable[[dict[str, str]], None]] = {
    "1": check_github,
    "2": check_aws,
    "3": check_neon,
    "4": check_groq,
    "5": check_telegram,
    "6": check_android,
    "7": check_brand_and_data,
}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Valida as entregas da S0 do Telegrana.")
    parser.add_argument("fases", nargs="*", help="ex.: s0.3 s0.4 (padrão: todas)")
    parser.add_argument(
        "--descobrir-admin-id",
        action="store_true",
        help="mostra o id de quem mandou /start ao bot de dev",
    )
    args = parser.parse_args()

    if not ENV_FILE.exists():
        print("Arquivo .env.local não encontrado na raiz do projeto.")
        print("Crie a partir do modelo:  Copy-Item .env.local.example .env.local")
        return 1
    env = load_env(ENV_FILE)
    for key in SECRET_KEYS:
        R.add_secret(env.get(key))

    if args.descobrir_admin_id:
        return discover_admin_id(env)

    selected = []
    for raw in args.fases or PHASES:
        key = raw.lower().removeprefix("s0.").removeprefix("s0")
        if key not in PHASES:
            parser.error(f"fase desconhecida: {raw} (use 1 a 7 ou s0.1 a s0.7)")
        selected.append(key)

    print("Telegrana · verificação da S0 (nenhum segredo é exibido)")
    for key in selected:
        try:
            PHASES[key](env)
        except Exception as exc:  # um erro numa fase não pode vazar segredo nem parar as outras
            R.fail(f"erro inesperado: {type(exc).__name__}: {first_line(str(exc))}")

    c = R.counts
    print(
        f"\nResumo: {c['ok']} ok · {c['falha']} falha(s) · {c['aviso']} aviso(s) · {c['falta']} pendente(s)"
    )
    if c["falha"]:
        return 1
    return 2 if c["falta"] else 0


if __name__ == "__main__":
    sys.exit(main())

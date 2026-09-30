# deploy/ — infraestrutura como código

## `app.yaml` — aplicação (S1.3, D031)

Stacks `telegrana-dev` e `telegrana-prod`: Lambdas `telegrana-<env>-bot` (webhook, Function URL) e `telegrana-<env>-rotinas` (agenda às 09:00 e 20:00, horário de Brasília).

**Deploy normal: pelo CI.** Merge na `main` publica o dev. Para publicar a produção:

```powershell
gh workflow run CI --ref main -f prod=true
```

**Deploy manual (emergência), desta máquina:**

```powershell
uv run python scripts/build_lambda.py
uv run python scripts/deploy_tasks.py migrar --env dev
sam deploy --template-file deploy/app.yaml --stack-name telegrana-dev --s3-bucket <ArtifactBucketName> --s3-prefix dev `
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM --parameter-overrides Env=dev LambdaBoundaryArn=<LambdaBoundaryArn> `
  --no-confirm-changeset --profile telegrana-sdk
uv run python scripts/deploy_tasks.py webhook --env dev
uv run python scripts/deploy_tasks.py webhook-info --env dev
```

**Segredos:** `uv run python scripts/ssm_setup.py` (grava/rotaciona no SSM; veja `--help`).

## `bootstrap.yaml` — base da conta (S0.2)

Stack CloudFormation `telegrana-bootstrap`, criada em 30/09/2026 (D023). Contém:

| Recurso | Para quê |
|---|---|
| Orçamento `telegrana-gasto-zero` | e-mail ao primeiro centavo consumido, **inclusive o que sai dos créditos** |
| Orçamento `telegrana-teto-mensal` (US$ 1) | e-mail a 80% (real) e a 100% (previsto); a 100% real, aciona o tópico do kill-switch |
| SNS `telegrana-orcamento-estourado` | recebe o estouro do orçamento → e-mail + Lambda do kill-switch |
| SNS `telegrana-avisos` | relatório do kill-switch por e-mail (tópico separado para não criar laço) |
| Lambda `telegrana-kill-switch` | zera a concorrência de todas as Lambdas `telegrana-*`, menos ela mesma |
| OIDC `token.actions.githubusercontent.com` + papel `telegrana-github-deploy` | deploy pelo GitHub Actions sem chaves (ambientes `dev`/`prod`, só `main`), com permissões mínimas (D031) |
| Política `telegrana-limite-lambdas` | limite de permissões obrigatório de todo papel criado pelo deploy |
| Bucket `telegrana-artefatos-<conta>` | artefatos do deploy, apagados em 7 dias |

O e-mail dos alertas é um parâmetro do deploy e **não fica no repositório**.

### Atualizar a stack

```powershell
aws cloudformation deploy --template-file deploy/bootstrap.yaml --stack-name telegrana-bootstrap `
  --capabilities CAPABILITY_NAMED_IAM --profile telegrana
```

Numa stack que já existe, o `deploy` mantém os valores anteriores dos parâmetros omitidos. Para trocar o e-mail, acrescente `--parameter-overrides AlertEmail=<novo e-mail>`. Quem recebe o e-mail precisa confirmar de novo a inscrição.

### Testar o kill-switch sem efeito

```powershell
Set-Content ks.json '{"dry_run": true}' -NoNewline -Encoding ascii
aws lambda invoke --function-name telegrana-kill-switch --payload fileb://ks.json --cli-binary-format raw-in-base64-out --profile telegrana out.json
Get-Content out.json   # lista as Lambdas que seriam paradas
```

### Religar depois de um acionamento

Descubra a causa do custo primeiro. Depois, para cada função zerada:

```powershell
aws lambda delete-function-concurrency --function-name <nome> --profile telegrana
```

### Limites da conta a lembrar

- A conta nova permite só **5 execuções simultâneas de Lambda no total**. Por isso não dá para reservar concorrência por função; o próprio limite da conta já é o teto. Zerar (`0`) funciona: foi testado em 30/09/2026.
- Os orçamentos contam os custos pagos com créditos (`IncludeCredit: false`). Na S9 (WhatsApp na EC2), o teto mensal precisa subir para o custo planejado, senão o kill-switch dispara.

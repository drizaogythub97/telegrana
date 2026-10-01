# Registro das operações de tratamento (LGPD, art. 37)

Documento interno do controlador. Versão simplificada, adequada a um agente de pequeno porte. Revisar sempre que surgir um dado, operador ou finalidade nova, e no mínimo uma vez por ano.

- **Controlador e encarregado**: Adriano Cardoso, pessoa física (contato: `{{contato_admin}}` no Telegram).
- **Titulares**: familiares e convidados do administrador, maiores de 18 anos (5 a 10 pessoas).
- **Última revisão**: 01/10/2026 (D032).

## Tratamentos

| Tratamento | Dados | Base legal | Retenção | Onde fica |
|---|---|---|---|---|
| Pedido de acesso | id do Telegram, nome e @ exibidos, mensagem (até 200 caracteres) | Art. 7º, V (preliminar a pedido do titular) | Até 7 dias ou criação da conta | `access_requests` (Neon) |
| Cadastro em andamento | id do Telegram, etapa do cadastro | Art. 7º, V | Até 7 dias se não concluído | `users`, `user_channels` |
| Conta | id do Telegram, nome completo, HMAC do telefone, hash Argon2 do código de recuperação, data da declaração de maioridade, aceites (versão e data) | Art. 7º, V | Enquanto a conta existir | `users`, `user_channels`, `terms_acceptances` |
| Lançamentos e transcrições | valores, datas, categorias, descrições, formas de pagamento, cartões, fixos, texto da transcrição | Art. 7º, V; dado sensível incidental: art. 11, I | Enquanto a conta existir | tabelas da conta (RLS forçado) |
| Interpretação por IA | texto ou áudio da mensagem, categorias e formas de pagamento, data | Art. 7º, V | Nenhuma no provedor (retenção zero); o áudio é descartado após a transcrição | Groq (EUA), em trânsito |
| Registros de segurança | tipo e data do evento, ator; sem conteúdo financeiro nem dado pessoal em `details` | Art. 7º, IX | Enquanto a conta existir; na exclusão fica só o evento anônimo | `audit_log` |
| Logs técnicos | metadados de execução, sem dado pessoal | Art. 7º, IX | 7 dias | CloudWatch (AWS, EUA) |
| Deduplicação de mensagens | número do update do Telegram | Art. 7º, V | 7 dias | `processed_updates` |

## Operadores e transferência internacional (art. 33, IX)

| Operador | Papel | País | Termos de dados |
|---|---|---|---|
| Amazon Web Services | Computação, cofre de segredos, logs | EUA (`us-east-1`) | Termos de serviço da AWS (adendo de proteção de dados incluído) |
| Neon | Banco de dados Postgres | EUA (sobre AWS `us-east-1`) | Termos e DPA do Neon |
| Groq | Transcrição e interpretação por IA | EUA | Termos do Groq; retenção zero ativada no painel |

O **Telegram** não é operador: é um serviço independente, usado pelo titular sob a política própria do Telegram.

## Segurança (art. 46)

RLS forçado por conta e suíte de isolamento obrigatória no CI; TLS `verify-full`; segredos só no SSM (SecureString); telefone só como HMAC-SHA256 com pepper; código de recuperação só como Argon2; logs sem dado pessoal; menor privilégio no deploy (OIDC); orçamento com kill-switch.

## Incidentes (art. 48)

Conter (revogar credenciais e tokens, desligar Lambdas pelo kill-switch), preservar evidências, dimensionar (titulares, dados, se havia dado sensível), avisar os titulares pelo bot e comunicar a ANPD no prazo da regulamentação vigente (conferir no site da ANPD na hora). Registrar a causa e a correção em `docs/DECISOES.md`, sem dado pessoal.

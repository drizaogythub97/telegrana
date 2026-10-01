# CLAUDE.md — Telegrana

Regras permanentes do projeto. Leia este arquivo inteiro no início de toda sessão, depois `HANDOFF.md`, depois `docs/PLANO.md`.

## O que é

**Telegrana** é um assistente financeiro **individual** com IA no Telegram: cada pessoa controla as próprias finanças. Começa em acesso antecipado, por convite (família e amigos do Adriano); a divulgação pública só depois dos pré-requisitos da seção 16 do `docs/PLANO.md` (D035). Registra gastos e ganhos por texto e áudio, cadastra fixos (água, luz, internet, assinaturas, salário), controla cartão de crédito com parcelamento e fatura, envia lembretes e gera relatórios em mensagem, XLSX e PDF.

A fonte da verdade do alinhamento é `docs/PLANO.md`. Decisões novas vão para `docs/DECISOES.md` (numeradas, com data, motivo e alternativa descartada).

## Idioma e grafia

- Toda comunicação com o Adriano, documentação, mensagens do bot e commits: **português do Brasil**.
- Código (nomes de variáveis, funções, tabelas): inglês. Comentários: português.
- O nome se escreve **Telegrana** (só o T maiúsculo). Nunca "TeleGrana".

## Stack fechada (não trocar sem registrar em DECISOES.md e pedir aprovação)

| Peça | Escolha |
|---|---|
| Linguagem | Python 3.12+ |
| Canal | Telegram Bot API (webhook) |
| Computação | AWS Lambda com Function URL (sem API Gateway) |
| Agendamento | Amazon EventBridge Scheduler (fuso `America/Sao_Paulo`) |
| Banco | Neon Postgres (plano Free), região `us-east-1` |
| IA | Groq: Whisper large-v3 (áudio) + gpt-oss (texto) |
| IaC | AWS SAM |
| CI/CD | GitHub Actions com OIDC (sem chaves AWS fixas) |
| Região AWS | `us-east-1` |

Conta AWS: a conta antiga do Adriano (Always Free). **O cartão existe só na AWS.** Nenhum outro serviço pode exigir cartão ou gerar cobrança.

## Regras de ouro (inegociáveis)

1. **Segurança é inegociável.** Seção 8 do `docs/PLANO.md` é requisito, não sugestão. Na dúvida entre conveniência e segurança, segurança.
2. **A IA interpreta, o código calcula.** Nenhuma soma, saldo ou total sai do modelo. Todo número de relatório vem de SQL.
3. **A IA nunca escreve SQL e nunca decide acesso.** Ela devolve estruturas validadas por Pydantic; o código monta consultas a partir de listas permitidas.
4. **A conta vem sempre do `from.id` verificado do Telegram**, nunca do texto, de botão ou da IA.
5. **Isolamento por conta com RLS forçado no Postgres** + chaves compostas `(account_id, id)`. Todo recurso novo nasce com teste que tenta vazar dado entre contas e precisa falhar.
6. **Dinheiro em centavos inteiros** (`bigint`). Nunca `float`. Datas no fuso `America/Sao_Paulo`.
7. **Na dúvida, o bot pergunta.** Nunca inventar valor, data ou categoria.
8. **Custo zero fora da AWS; AWS dentro do Always Free** com as proteções da seção 9 do plano.
9. **Dado pessoal só com finalidade.** Nada é coletado antes do aceite dos termos; nenhum campo novo sem finalidade escrita no plano (seção 3.4), atualização da política e novo aceite. Telefone só como HMAC.
10. **Núcleo agnóstico de canal.** Regras de negócio não importam nada de Telegram; o Telegram é um adaptador. (Permite um canal WhatsApp no futuro sem reescrever o núcleo.)

## Forma de trabalhar

- **Automação máxima.** Você desenvolve, testa e faz deploy sozinho. Só pare para pedir ao Adriano o que for impossível sem ele (ações manuais da S0, aprovação de decisões irreversíveis, validação visual no celular).
- **Tudo que precisar do Adriano, peça de uma vez, no começo**, em lista única, com instruções exatas (ver S0 no plano).
- **Pesquise antes de instruir.** Interfaces de AWS, Neon, Groq, Telegram e GitHub mudam. Antes de escrever qualquer passo a passo manual, pesquise o procedimento atual na documentação oficial e registre a data da verificação no documento.
- **Teste de verdade.** Unitários + integração com Postgres real (branch de dev do Neon ou Postgres local em container) + ponta a ponta no ambiente de testes do Telegram. Validação visual no celular do Adriano via `adb` (depuração Wi-Fi) quando a entrega for visual.
- **Nada vai para produção sem os testes verdes e sem a suíte de isolamento entre contas passando.**
- Git: você tem autonomia total sobre o repositório (commits pequenos e descritivos em pt-BR, push, PRs). Nunca reescrever histórico publicado. Nunca commitar segredo.
- Segredos: só em `.env.local` (gitignored) na máquina, SSM Parameter Store (SecureString) na AWS e GitHub Secrets/OIDC no CI. Nunca em código, log, commit, mensagem de erro ou resposta no chat.
- Dependências: versões travadas com hash; nada de pacote obscuro ou sem manutenção. Rodar auditoria de vulnerabilidades no CI.

## Protocolo de encerramento de sprint (obrigatório)

Ao fechar **qualquer** sprint ou micro-fase:

1. Todos os testes verdes; CI verde; deploy feito (quando aplicável).
2. Atualizar `HANDOFF.md` com **absolutamente tudo** que a próxima sessão precisa para continuar sem perguntar nada: estado atual, o que foi feito, o que ficou pendente, decisões tomadas, armadilhas encontradas, comandos úteis, próximos passos exatos, e o que mais você julgar valioso.
3. Registrar decisões novas em `docs/DECISOES.md`.
4. Atualizar `docs/PLANO.md` se algo do alinhamento mudou (marcar com a data).
5. Salvar as memórias relevantes do projeto.
6. Commit e push com mensagem `chore(sprint): encerra Sx — <resumo>`.
7. Mandar ao Adriano um resumo curto: o que entrou, o que ele precisa fazer (se algo), qual é a próxima sprint.

# Telegrana

Bot de Telegram com IA para as finanças pessoais de uma família: registra gastos e ganhos por texto e áudio, cuida de contas fixas, cartão de crédito com parcelamento e fatura, envia lembretes e gera relatórios em mensagem, XLSX e PDF.

Projeto pessoal e familiar, sem fins comerciais. O bot é privado: a entrada é só por convite.

- Plano e alinhamento: [`docs/PLANO.md`](docs/PLANO.md)
- Decisões: [`docs/DECISOES.md`](docs/DECISOES.md)
- Estado atual: [`HANDOFF.md`](HANDOFF.md)

**Stack:** Python · AWS Lambda (Function URL) · EventBridge Scheduler · Neon Postgres (RLS) · Groq (Whisper + gpt-oss) · AWS SAM · GitHub Actions (OIDC).

Encontrou uma falha de segurança? Use o *Private vulnerability reporting* da aba **Security** deste repositório. Não abra issue pública.

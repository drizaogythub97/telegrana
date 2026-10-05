-- 0011 · Pergunta aberta (05/10/2026, roteiro H): no Telegram Web e no Desktop a pergunta
-- do bot não abre a resposta sozinha. A última pergunta feita a uma pessoa fica marcada
-- (rascunho `pergunta`, ISOLADO, 10 min, uma mensagem só): a próxima mensagem solta que
-- tiver a cara da resposta vale como resposta.
alter table telegrana.pending_entries drop constraint pending_entries_pendencia_check;
alter table telegrana.pending_entries add constraint pending_entries_pendencia_check
    check (pendencia in ('valor', 'categoria', 'data', 'confirmar_valor', 'duvida', 'corrigir',
                         'lembrete', 'cartao', 'cartao_dias', 'pergunta'));

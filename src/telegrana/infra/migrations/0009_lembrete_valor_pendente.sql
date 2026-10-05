-- 0009 · "Outro valor" sem responder (05/10/2026, roteiro G5): depois de tocar ✏️ Outro valor
-- num lembrete, a próxima mensagem da pessoa que for só um valor (respondendo ou não) paga
-- AQUELE vencimento, por até 10 minutos. Reaproveita os rascunhos (ISOLADOS, expiram em 1 dia).
alter table telegrana.pending_entries drop constraint pending_entries_pendencia_check;
alter table telegrana.pending_entries add constraint pending_entries_pendencia_check
    check (pendencia in ('valor', 'categoria', 'data', 'confirmar_valor', 'duvida', 'corrigir',
                         'lembrete'));

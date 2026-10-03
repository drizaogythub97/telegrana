-- 0007 · Correção pendente (03/10/2026): depois de tocar ✏️ Corrigir, a próxima mensagem
-- da pessoa (respondendo ou não) corrige AQUELE lançamento, por até 10 minutos.
-- Reaproveita os rascunhos (ISOLADOS, expiram em 1 dia; a idade de 10 min é conferida no código).
alter table telegrana.pending_entries drop constraint pending_entries_pendencia_check;
alter table telegrana.pending_entries add constraint pending_entries_pendencia_check
    check (pendencia in ('valor', 'categoria', 'data', 'confirmar_valor', 'duvida', 'corrigir'));

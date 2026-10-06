-- 0013 · Relatórios em texto (S6, PLANO 6, D047).
-- Resumos automáticos por conta (decisão do Adriano, 06/10/2026): fechamento do mês LIGADO
-- por padrão; resumo semanal DESLIGADO por padrão (liga pelo /resumo).

alter table telegrana.accounts
    add column weekly_summary  boolean not null default false,
    add column monthly_summary boolean not null default true;
grant update (weekly_summary, monthly_summary) on telegrana.accounts to telegrana_app;

-- ---------------------------------------------------------------------------
-- Resumos enviados (ISOLADA): um por conta, tipo e período — rotina repetida não reenvia
-- ---------------------------------------------------------------------------
create table telegrana.summary_sends (
    account_id   uuid not null references telegrana.accounts (id) on delete cascade,
    id           uuid not null default uuidv7(),
    kind         text not null check (kind in ('weekly', 'monthly')),
    period_start date not null,
    sent_at      timestamptz not null default now(),
    primary key (account_id, id),
    unique (account_id, kind, period_start)
);
alter table telegrana.summary_sends enable row level security;
alter table telegrana.summary_sends force row level security;
create policy isolamento on telegrana.summary_sends for all to telegrana_app
    using (account_id = telegrana.current_account_id())
    with check (account_id = telegrana.current_account_id());
create policy migrator on telegrana.summary_sends for all to telegrana_migrator using (true) with check (true);
grant select, insert on telegrana.summary_sends to telegrana_app;

-- ---------------------------------------------------------------------------
-- Contas que querem algum resumo (SECURITY DEFINER: só devolve ids)
-- ---------------------------------------------------------------------------
create function telegrana.accounts_for_summaries(p_kind text)
    returns table (o_account_id uuid)
    language sql stable
    security definer
    set search_path = pg_catalog, telegrana
as $$
    select a.id
      from telegrana.accounts a
     where a.status = 'active'
       and case p_kind when 'weekly' then a.weekly_summary
                       when 'monthly' then a.monthly_summary
                       else false end
$$;
revoke all on function telegrana.accounts_for_summaries(text) from public;
grant execute on function telegrana.accounts_for_summaries(text) to telegrana_app;

-- ---------------------------------------------------------------------------
-- Rascunho da última consulta (para "💳 Incluir compras no cartão")
-- ---------------------------------------------------------------------------
alter table telegrana.pending_entries drop constraint pending_entries_pendencia_check;
alter table telegrana.pending_entries add constraint pending_entries_pendencia_check
    check (pendencia in ('valor', 'categoria', 'data', 'confirmar_valor', 'duvida', 'corrigir',
                         'lembrete', 'cartao', 'cartao_dias', 'pergunta', 'consulta'));

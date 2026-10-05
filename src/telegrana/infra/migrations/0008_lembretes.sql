-- 0008 · Lembretes dos fixos (S4.2, PLANO 4.4, D043, D044).
-- A rotina (09:00 e 20:00, São Paulo) pergunta quais contas têm fixos com lembrete
-- (única função que atravessa contas, e só devolve ids); o resto acontece dentro do
-- account_context de cada conta, com RLS forçado.

-- ---------------------------------------------------------------------------
-- Mês resolvido de um fixo: pago (com o lançamento) ou pulado (ISOLADA)
-- ---------------------------------------------------------------------------
create table telegrana.fixed_occurrences (
    account_id     uuid not null references telegrana.accounts (id) on delete cascade,
    id             uuid not null default uuidv7(),
    fixed_item_id  uuid not null,
    due_date       date not null,
    status         text not null check (status in ('paid', 'skipped')),
    transaction_id uuid,
    created_at     timestamptz not null default now(),
    primary key (account_id, id),
    -- Um vencimento só se resolve uma vez: toque duplo em ✅ Paguei não lança duas vezes.
    unique (account_id, fixed_item_id, due_date),
    foreign key (account_id, fixed_item_id)
        references telegrana.fixed_items (account_id, id) on delete cascade,
    foreign key (account_id, transaction_id)
        references telegrana.transactions (account_id, id) on delete set null (transaction_id)
);

-- ---------------------------------------------------------------------------
-- Lembretes enviados (ISOLADA, 60 dias): nunca mandar o mesmo duas vezes
-- ---------------------------------------------------------------------------
create table telegrana.reminder_sends (
    account_id    uuid not null references telegrana.accounts (id) on delete cascade,
    id            uuid not null default uuidv7(),
    fixed_item_id uuid not null,
    due_date      date not null,
    rule          text not null check (rule in ('before', 'on_day', 'after')),
    sent_on       date not null,
    slot          text not null check (slot in ('morning', 'evening')),
    sent_at       timestamptz not null default now(),
    primary key (account_id, id),
    -- Um lembrete por fixo, por dia e por horário: rotina repetida (nova tentativa do
    -- Scheduler) não manda de novo.
    unique (account_id, fixed_item_id, sent_on, slot),
    foreign key (account_id, fixed_item_id)
        references telegrana.fixed_items (account_id, id) on delete cascade
);

alter table telegrana.fixed_occurrences enable row level security;
alter table telegrana.fixed_occurrences force row level security;
alter table telegrana.reminder_sends    enable row level security;
alter table telegrana.reminder_sends    force row level security;
create policy isolamento on telegrana.fixed_occurrences for all to telegrana_app
    using (account_id = telegrana.current_account_id())
    with check (account_id = telegrana.current_account_id());
create policy isolamento on telegrana.reminder_sends for all to telegrana_app
    using (account_id = telegrana.current_account_id())
    with check (account_id = telegrana.current_account_id());
create policy migrator on telegrana.fixed_occurrences for all to telegrana_migrator using (true) with check (true);
create policy migrator on telegrana.reminder_sends    for all to telegrana_migrator using (true) with check (true);
grant select, insert, delete on telegrana.fixed_occurrences to telegrana_app;
grant update (transaction_id) on telegrana.fixed_occurrences to telegrana_app;
grant select, insert on telegrana.reminder_sends to telegrana_app;

-- ---------------------------------------------------------------------------
-- Contas com lembrete a calcular (SECURITY DEFINER: atravessa contas, mas só devolve
-- ids de contas ativas com fixo ativo e algum lembrete ligado; nada de dado financeiro)
-- ---------------------------------------------------------------------------
create function telegrana.accounts_with_reminders()
    returns table (o_account_id uuid)
    language sql stable
    security definer
    set search_path = pg_catalog, telegrana
as $$
    select distinct f.account_id
      from telegrana.fixed_items f
      join telegrana.accounts a on a.id = f.account_id
     where a.status = 'active'
       and f.active
       and (f.remind_before or f.remind_on_day or f.remind_after)
$$;
revoke all on function telegrana.accounts_with_reminders() from public;
grant execute on function telegrana.accounts_with_reminders() to telegrana_app;

-- ---------------------------------------------------------------------------
-- Limpeza diária: passa a apagar também os lembretes enviados há mais de 60 dias
-- ---------------------------------------------------------------------------
drop function telegrana.purge_account_temporaries();
create function telegrana.purge_account_temporaries()
    returns table (o_drafts integer, o_refs integer, o_sends integer)
    language plpgsql
    security definer
    set search_path = pg_catalog, telegrana
as $$
declare
    v_drafts integer;
    v_refs   integer;
    v_sends  integer;
begin
    delete from telegrana.pending_entries where expires_at < now();
    get diagnostics v_drafts = row_count;
    delete from telegrana.message_refs where created_at < now() - interval '30 days';
    get diagnostics v_refs = row_count;
    delete from telegrana.reminder_sends where sent_at < now() - interval '60 days';
    get diagnostics v_sends = row_count;
    return query select v_drafts, v_refs, v_sends;
end
$$;
revoke all on function telegrana.purge_account_temporaries() from public;
grant execute on function telegrana.purge_account_temporaries() to telegrana_app;

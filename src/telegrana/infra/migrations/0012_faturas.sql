-- 0012 · Faturas de cartão (S5.2, PLANO 4.5, D046).
-- A fatura é (cartão, vencimento): as parcelas previstas com aquele `invoice_on`. Pagar a
-- fatura transforma as parcelas em gasto realizado na data do pagamento (regime de caixa).

-- ---------------------------------------------------------------------------
-- Lembretes do cartão (como nos fixos): véspera, no dia e todo dia depois; horário
-- ---------------------------------------------------------------------------
alter table telegrana.cards
    add column remind_before boolean not null default true,
    add column remind_on_day boolean not null default true,
    add column remind_after  boolean not null default true,
    add column remind_slot   text not null default 'morning'
                             check (remind_slot in ('morning', 'evening', 'both'));
grant update (remind_before, remind_on_day, remind_after, remind_slot) on telegrana.cards
    to telegrana_app;

-- ---------------------------------------------------------------------------
-- Fatura paga (ISOLADA): uma vez por cartão e vencimento — toque duplo não paga duas vezes
-- ---------------------------------------------------------------------------
create table telegrana.card_invoices (
    account_id  uuid not null references telegrana.accounts (id) on delete cascade,
    id          uuid not null default uuidv7(),
    card_id     uuid not null,
    due_date    date not null,
    total_cents bigint not null check (total_cents >= 0),
    paid_cents  bigint not null check (paid_cents > 0 and paid_cents < 100000000000),
    paid_on     date not null,
    created_at  timestamptz not null default now(),
    primary key (account_id, id),
    unique (account_id, card_id, due_date),
    foreign key (account_id, card_id)
        references telegrana.cards (account_id, id) on delete cascade
);

-- ---------------------------------------------------------------------------
-- Avisos de fatura enviados (ISOLADA, 60 dias): fechou / véspera / no dia / atrasada
-- ---------------------------------------------------------------------------
create table telegrana.invoice_notices (
    account_id uuid not null references telegrana.accounts (id) on delete cascade,
    id         uuid not null default uuidv7(),
    card_id    uuid not null,
    due_date   date not null,
    rule       text not null check (rule in ('closed', 'before', 'on_day', 'after')),
    sent_on    date not null,
    slot       text not null check (slot in ('morning', 'evening')),
    sent_at    timestamptz not null default now(),
    primary key (account_id, id),
    unique (account_id, card_id, sent_on, slot),
    foreign key (account_id, card_id)
        references telegrana.cards (account_id, id) on delete cascade
);

alter table telegrana.card_invoices   enable row level security;
alter table telegrana.card_invoices   force row level security;
alter table telegrana.invoice_notices enable row level security;
alter table telegrana.invoice_notices force row level security;
create policy isolamento on telegrana.card_invoices for all to telegrana_app
    using (account_id = telegrana.current_account_id())
    with check (account_id = telegrana.current_account_id());
create policy isolamento on telegrana.invoice_notices for all to telegrana_app
    using (account_id = telegrana.current_account_id())
    with check (account_id = telegrana.current_account_id());
create policy migrator on telegrana.card_invoices   for all to telegrana_migrator using (true) with check (true);
create policy migrator on telegrana.invoice_notices for all to telegrana_migrator using (true) with check (true);
grant select, insert on telegrana.card_invoices to telegrana_app;
grant select, insert on telegrana.invoice_notices to telegrana_app;

-- ---------------------------------------------------------------------------
-- A rotina passa a olhar também as contas com cartão ativo (continua devolvendo só ids)
-- ---------------------------------------------------------------------------
create or replace function telegrana.accounts_with_reminders()
    returns table (o_account_id uuid)
    language sql stable
    security definer
    set search_path = pg_catalog, telegrana
as $$
    select f.account_id
      from telegrana.fixed_items f
      join telegrana.accounts a on a.id = f.account_id
     where a.status = 'active'
       and f.active
       and (f.remind_before or f.remind_on_day or f.remind_after)
    union
    select c.account_id
      from telegrana.cards c
      join telegrana.payment_methods m on m.id = c.payment_method_id
      join telegrana.accounts a on a.id = c.account_id
     where a.status = 'active'
       and m.active
$$;

-- Limpeza: avisos de fatura com mais de 60 dias saem junto com os lembretes dos fixos.
create or replace function telegrana.purge_account_temporaries()
    returns table (o_drafts integer, o_refs integer, o_sends integer)
    language plpgsql
    security definer
    set search_path = pg_catalog, telegrana
as $$
declare
    v_drafts  integer;
    v_refs    integer;
    v_sends   integer;
    v_notices integer;
begin
    delete from telegrana.pending_entries where expires_at < now();
    get diagnostics v_drafts = row_count;
    delete from telegrana.message_refs where created_at < now() - interval '30 days';
    get diagnostics v_refs = row_count;
    delete from telegrana.reminder_sends where sent_at < now() - interval '60 days';
    get diagnostics v_sends = row_count;
    delete from telegrana.invoice_notices where sent_at < now() - interval '60 days';
    get diagnostics v_notices = row_count;
    return query select v_drafts, v_refs, v_sends + v_notices;
end
$$;

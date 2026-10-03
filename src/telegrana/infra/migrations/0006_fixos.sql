-- 0006 · Fixos e recorrentes (S4.1, PLANO 4.3, D043).
-- ISOLADO por conta: RLS forçado + chave composta; chaves estrangeiras compostas garantem
-- que um fixo só aponta para categoria e forma de pagamento da MESMA conta.
-- O fixo gera LEMBRETE, não lançamento: o lançamento nasce quando a pessoa toca em
-- "Paguei/Recebi" (S4.2) e fica ligado ao fixo por transactions.fixed_item_id.

create table telegrana.fixed_items (
    account_id        uuid not null references telegrana.accounts (id) on delete cascade,
    id                uuid not null default uuidv7(),
    user_id           uuid not null,
    kind              text not null check (kind in ('expense', 'income')),
    name              text not null check (char_length(name) between 1 and 40),
    category_id       uuid,
    amount_cents      bigint not null check (amount_cents > 0 and amount_cents < 100000000000),
    -- fixed: o valor é sempre esse (aluguel); estimated: varia (luz, água).
    amount_kind       text not null check (amount_kind in ('fixed', 'estimated')),
    -- Dia do vencimento; 31 em mês curto = último dia do mês (o código calcula).
    day_of_month      smallint not null check (day_of_month between 1 and 31),
    payment_method_id uuid,
    -- Lembretes (PLANO 4.4): véspera, no dia e diário depois do vencimento até Paguei/Pular.
    remind_before     boolean not null default true,
    remind_on_day     boolean not null default true,
    remind_after      boolean not null default true,
    remind_slot       text not null default 'morning'
                      check (remind_slot in ('morning', 'evening', 'both')),
    active            boolean not null default true,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    primary key (account_id, id),
    foreign key (account_id, user_id)
        references telegrana.account_members (account_id, user_id) on delete cascade,
    foreign key (account_id, category_id) references telegrana.categories (account_id, id),
    foreign key (account_id, payment_method_id)
        references telegrana.payment_methods (account_id, id)
);
-- Nome único por conta (sem diferenciar maiúsculas): é por ele que o bot acha o fixo.
create unique index fixed_items_nome_unico on telegrana.fixed_items (account_id, lower(name));

alter table telegrana.fixed_items enable row level security;
alter table telegrana.fixed_items force row level security;
create policy isolamento on telegrana.fixed_items for all to telegrana_app
    using (account_id = telegrana.current_account_id())
    with check (account_id = telegrana.current_account_id());
create policy migrator on telegrana.fixed_items for all to telegrana_migrator
    using (true) with check (true);

grant select, insert, delete on telegrana.fixed_items to telegrana_app;
grant update (name, category_id, amount_cents, amount_kind, day_of_month, payment_method_id,
              remind_before, remind_on_day, remind_after, remind_slot, active, updated_at)
    on telegrana.fixed_items to telegrana_app;

-- Lançamento ↔ fixo (o pagamento de um mês). Apagar o fixo não apaga os lançamentos.
alter table telegrana.transactions add column fixed_item_id uuid;
alter table telegrana.transactions
    add constraint transactions_fixed_item_fk foreign key (account_id, fixed_item_id)
        references telegrana.fixed_items (account_id, id) on delete set null (fixed_item_id);
grant update (fixed_item_id) on telegrana.transactions to telegrana_app;

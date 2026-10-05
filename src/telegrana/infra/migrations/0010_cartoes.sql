-- 0010 · Cartões de crédito e compras parceladas (S5.1, PLANO 4.5, D045).
-- Regime de caixa: a compra no crédito é COMPROMISSO. Cada parcela é um lançamento
-- previsto (status 'planned') na fatura certa; vira gasto realizado quando a fatura é paga
-- (S5.2). O cartão é uma forma de pagamento (payment_methods, kind 'credit') com os dias de
-- fechamento e vencimento aqui.

-- ---------------------------------------------------------------------------
-- Cartões (ISOLADA)
-- ---------------------------------------------------------------------------
create table telegrana.cards (
    account_id        uuid not null references telegrana.accounts (id) on delete cascade,
    id                uuid not null default uuidv7(),
    payment_method_id uuid not null,
    -- Dias do mês; 31 em mês curto = último dia (o código calcula, como nos fixos).
    closing_day       smallint not null check (closing_day between 1 and 31),
    due_day           smallint not null check (due_day between 1 and 31),
    limit_cents       bigint check (limit_cents > 0 and limit_cents < 100000000000),
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    primary key (account_id, id),
    unique (account_id, payment_method_id),
    foreign key (account_id, payment_method_id)
        references telegrana.payment_methods (account_id, id) on delete cascade
);
alter table telegrana.cards enable row level security;
alter table telegrana.cards force row level security;
create policy isolamento on telegrana.cards for all to telegrana_app
    using (account_id = telegrana.current_account_id())
    with check (account_id = telegrana.current_account_id());
create policy migrator on telegrana.cards for all to telegrana_migrator using (true) with check (true);
grant select, insert, delete on telegrana.cards to telegrana_app;
grant update (closing_day, due_day, limit_cents, updated_at) on telegrana.cards to telegrana_app;

-- Apagar um cartão sem compras apaga a forma de pagamento dele (com compras, só desativa).
grant delete on telegrana.payment_methods to telegrana_app;

-- ---------------------------------------------------------------------------
-- Parcelas: cada uma é um lançamento previsto, ligado à compra (a 1ª parcela)
-- ---------------------------------------------------------------------------
alter table telegrana.transactions
    add column purchase_id    uuid,
    add column installment_no smallint check (installment_no between 1 and 72),
    -- Vencimento da fatura em que a parcela cai (não muda quando a fatura é paga).
    add column invoice_on     date,
    add constraint transactions_parcela_check
        check ((purchase_id is null) = (installment_no is null)
               and (installment_no is null or invoice_on is not null)),
    -- A compra é da MESMA conta (chave composta); apagar a 1ª parcela apaga as outras.
    add constraint transactions_compra_fk foreign key (account_id, purchase_id)
        references telegrana.transactions (account_id, id) on delete cascade;
create index transactions_compra on telegrana.transactions (account_id, purchase_id)
    where purchase_id is not null;
create index transactions_fatura on telegrana.transactions (account_id, payment_method_id, invoice_on)
    where invoice_on is not null;
-- Sem DELETE: parcela que sobra (compra que deixa de ser no cartão) é apagada logicamente
-- (deleted_at) e desligada da compra.
grant update (purchase_id, installment_no, invoice_on) on telegrana.transactions to telegrana_app;

-- ---------------------------------------------------------------------------
-- Rascunhos: em qual cartão (botões ou nome) e os dias de um cartão novo
-- ---------------------------------------------------------------------------
alter table telegrana.pending_entries drop constraint pending_entries_pendencia_check;
alter table telegrana.pending_entries add constraint pending_entries_pendencia_check
    check (pendencia in ('valor', 'categoria', 'data', 'confirmar_valor', 'duvida', 'corrigir',
                         'lembrete', 'cartao', 'cartao_dias'));

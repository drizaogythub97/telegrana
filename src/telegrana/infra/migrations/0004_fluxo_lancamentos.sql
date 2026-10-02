-- 0004 · Fluxo dos lançamentos no bot (S2.3, D038, D039): rascunhos com pendência,
-- vínculo recibo ↔ lançamento (correção respondendo ao recibo), parcelas, marca de
-- "é fixo?", formas Crédito e Boleto e o medidor de uso da IA.

-- ---------------------------------------------------------------------------
-- Formas de pagamento: crédito e boleto (cartões detalhados chegam na S5)
-- ---------------------------------------------------------------------------
alter table telegrana.payment_methods drop constraint payment_methods_kind_check;
alter table telegrana.payment_methods add constraint payment_methods_kind_check
    check (kind in ('pix', 'debit', 'cash', 'savings', 'credit', 'boleto', 'other'));

-- ---------------------------------------------------------------------------
-- Lançamentos: parcelas (compra no crédito antes da S5) e resposta a "é fixo?" (S4 usa)
-- ---------------------------------------------------------------------------
alter table telegrana.transactions
    add column installments smallint check (installments between 1 and 72),
    add column recurring boolean;
grant update (installments, recurring) on telegrana.transactions to telegrana_app;

-- ---------------------------------------------------------------------------
-- Rascunhos: lançamento entendido que espera uma resposta (ISOLADA, 1 dia)
-- ---------------------------------------------------------------------------
create table telegrana.pending_entries (
    account_id uuid not null references telegrana.accounts (id) on delete cascade,
    id         uuid not null default uuidv7(),
    user_id    uuid not null,
    data       jsonb not null check (octet_length(data::text) <= 4000),
    pendencia  text not null
               check (pendencia in ('valor', 'categoria', 'data', 'confirmar_valor', 'duvida')),
    created_at timestamptz not null default now(),
    expires_at timestamptz not null default now() + interval '1 day',
    primary key (account_id, id),
    foreign key (account_id, user_id)
        references telegrana.account_members (account_id, user_id) on delete cascade
);

-- ---------------------------------------------------------------------------
-- Recibo ↔ lançamento (ISOLADA, 30 dias): quem responde ao recibo corrige aquele lançamento
-- ---------------------------------------------------------------------------
create table telegrana.message_refs (
    account_id     uuid not null references telegrana.accounts (id) on delete cascade,
    channel        text not null check (channel in ('telegram', 'whatsapp')),
    message_id     text not null check (message_id ~ '^[0-9A-Za-z_.:-]{1,64}$'),
    transaction_id uuid not null,
    created_at     timestamptz not null default now(),
    primary key (account_id, channel, message_id),
    foreign key (account_id, transaction_id)
        references telegrana.transactions (account_id, id) on delete cascade
);

alter table telegrana.pending_entries enable row level security;
alter table telegrana.pending_entries force row level security;
alter table telegrana.message_refs    enable row level security;
alter table telegrana.message_refs    force row level security;
create policy isolamento on telegrana.pending_entries for all to telegrana_app
    using (account_id = telegrana.current_account_id())
    with check (account_id = telegrana.current_account_id());
create policy isolamento on telegrana.message_refs for all to telegrana_app
    using (account_id = telegrana.current_account_id())
    with check (account_id = telegrana.current_account_id());
create policy migrator on telegrana.pending_entries for all to telegrana_migrator using (true) with check (true);
create policy migrator on telegrana.message_refs    for all to telegrana_migrator using (true) with check (true);
grant select, insert, delete on telegrana.pending_entries to telegrana_app;
grant select, insert, delete on telegrana.message_refs to telegrana_app;

-- ---------------------------------------------------------------------------
-- Medidor de uso da IA (GLOBAL, sem dado pessoal): por dia e modelo
-- ---------------------------------------------------------------------------
create table telegrana.ai_usage (
    day        date not null,
    model      text not null check (char_length(model) between 1 and 60),
    requests   integer not null default 0 check (requests >= 0),
    tokens     bigint not null default 0 check (tokens >= 0),
    alerted_at timestamptz,
    primary key (day, model)
);
grant select, insert on telegrana.ai_usage to telegrana_app;
grant update (requests, tokens, alerted_at) on telegrana.ai_usage to telegrana_app;

-- ---------------------------------------------------------------------------
-- Padrões: mesma lista de categorias da 0003 + Crédito e Boleto
-- ---------------------------------------------------------------------------
create or replace function telegrana.seed_account_defaults(p_account_id uuid) returns void
    language sql
    set search_path = pg_catalog, telegrana
as $$
    insert into telegrana.categories (account_id, kind, code, name, emoji, sort)
    select p_account_id, d.kind, d.code, d.name, d.emoji, d.sort
      from (values
        ('expense', 'mercado',      'Mercado',             '🛒', 10),
        ('expense', 'alimentacao',  'Alimentação fora',    '🍽️', 20),
        ('expense', 'moradia',      'Moradia',             '🏠', 30),
        ('expense', 'contas_casa',  'Contas da casa',      '💡', 40),
        ('expense', 'transporte',   'Transporte',          '🚗', 50),
        ('expense', 'combustivel',  'Combustível',         '⛽', 60),
        ('expense', 'saude',        'Saúde',               '💊', 70),
        ('expense', 'educacao',     'Educação',            '📚', 80),
        ('expense', 'lazer',        'Lazer',               '🎮', 90),
        ('expense', 'vestuario',    'Vestuário',           '👕', 100),
        ('expense', 'assinaturas',  'Assinaturas',         '📱', 110),
        ('expense', 'pets',         'Pets',                '🐾', 120),
        ('expense', 'filhos',       'Filhos',              '👶', 130),
        ('expense', 'presentes',    'Presentes',           '🎁', 140),
        ('expense', 'encargos',     'Encargos e juros',    '💸', 150),
        ('expense', 'outros',       'Outros',              '📦', 999),
        ('income',  'salario',      'Salário',             '💼', 10),
        ('income',  'servicos',     'Serviços/Freela',     '🧾', 20),
        ('income',  'rendimentos',  'Rendimentos',         '📈', 30),
        ('income',  'reembolso',    'Reembolso',           '↩️', 40),
        ('income',  'outros_ganhos','Outros ganhos',       '🎉', 999)
      ) as d (kind, code, name, emoji, sort)
    on conflict do nothing;

    insert into telegrana.payment_methods (account_id, kind, name, emoji)
    select p_account_id, d.kind, d.name, d.emoji
      from (values
        ('pix',     'Pix',      '⚡'),
        ('debit',   'Débito',   '💳'),
        ('cash',    'Dinheiro', '💵'),
        ('savings', 'Poupança', '🐷'),
        ('credit',  'Crédito',  '💳'),
        ('boleto',  'Boleto',   '🧾')
      ) as d (kind, name, emoji)
    on conflict do nothing;
$$;

select telegrana.seed_account_defaults(a.id) from telegrana.accounts a;

-- ---------------------------------------------------------------------------
-- Limpeza diária (rotinas): rascunhos vencidos e vínculos de recibo com mais de 30 dias.
-- SECURITY DEFINER porque atravessa contas; só apaga o que já venceu.
-- ---------------------------------------------------------------------------
create function telegrana.purge_account_temporaries()
    returns table (o_drafts integer, o_refs integer)
    language plpgsql
    security definer
    set search_path = pg_catalog, telegrana
as $$
declare
    v_drafts integer;
    v_refs   integer;
begin
    delete from telegrana.pending_entries where expires_at < now();
    get diagnostics v_drafts = row_count;
    delete from telegrana.message_refs where created_at < now() - interval '30 days';
    get diagnostics v_refs = row_count;
    return query select v_drafts, v_refs;
end
$$;
revoke all on function telegrana.purge_account_temporaries() from public;
grant execute on function telegrana.purge_account_temporaries() to telegrana_app;

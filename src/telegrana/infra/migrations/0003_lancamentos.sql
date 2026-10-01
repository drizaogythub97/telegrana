-- 0003 · Categorias, formas de pagamento, lançamentos e regras aprendidas (S2.1, D036).
-- Tudo ISOLADO por conta: RLS forçado + chave composta (account_id, id). As chaves
-- estrangeiras compostas garantem que um lançamento só aponta para categoria e forma de
-- pagamento da MESMA conta (regra de ouro 5).

-- ---------------------------------------------------------------------------
-- Categorias (PLANO 4.2)
-- ---------------------------------------------------------------------------
create table telegrana.categories (
    account_id uuid not null references telegrana.accounts (id) on delete cascade,
    id         uuid not null default uuidv7(),
    kind       text not null check (kind in ('expense', 'income')),
    -- code: só nas categorias padrão (estável para regras e para a IA); null nas criadas.
    code       text check (code ~ '^[a-z_]{2,30}$'),
    name       text not null check (char_length(name) between 1 and 40),
    emoji      text not null check (char_length(emoji) between 1 and 8),
    active     boolean not null default true,
    sort       integer not null default 100,
    created_at timestamptz not null default now(),
    primary key (account_id, id),
    unique (account_id, code)
);
-- Nome único por conta (sem diferenciar maiúsculas): é por ele que o bot acha a categoria.
create unique index categories_nome_unico on telegrana.categories (account_id, lower(name));

-- ---------------------------------------------------------------------------
-- Formas de pagamento (Pix, débito, dinheiro, poupança; cartões chegam na S5)
-- ---------------------------------------------------------------------------
create table telegrana.payment_methods (
    account_id uuid not null references telegrana.accounts (id) on delete cascade,
    id         uuid not null default uuidv7(),
    kind       text not null check (kind in ('pix', 'debit', 'cash', 'savings', 'other')),
    name       text not null check (char_length(name) between 1 and 40),
    emoji      text not null check (char_length(emoji) between 1 and 8),
    active     boolean not null default true,
    created_at timestamptz not null default now(),
    primary key (account_id, id)
);
create unique index payment_methods_nome_unico
    on telegrana.payment_methods (account_id, lower(name));

-- ---------------------------------------------------------------------------
-- Lançamentos (PLANO 4.1)
-- ---------------------------------------------------------------------------
create table telegrana.transactions (
    account_id        uuid not null references telegrana.accounts (id) on delete cascade,
    id                uuid not null default uuidv7(),
    user_id           uuid not null,
    kind              text not null check (kind in ('expense', 'income', 'transfer')),
    amount_cents      bigint not null check (amount_cents > 0 and amount_cents < 100000000000),
    category_id       uuid,
    payment_method_id uuid,
    -- Transferência (ex.: guardar na poupança, D028): sai de payment_method_id, entra aqui.
    to_payment_method_id uuid,
    occurred_on       date not null,  -- competência: quando aconteceu
    cash_on           date not null,  -- caixa: quando o dinheiro saiu/entrou
    description       text check (char_length(description) <= 200),
    source            text not null check (source in ('text', 'audio', 'fixed', 'invoice')),
    original_text     text check (char_length(original_text) <= 1000),
    status            text not null default 'done' check (status in ('done', 'planned')),
    update_id         bigint,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    deleted_at        timestamptz,
    primary key (account_id, id),
    foreign key (account_id, user_id)
        references telegrana.account_members (account_id, user_id) on delete cascade,
    foreign key (account_id, category_id)
        references telegrana.categories (account_id, id),
    foreign key (account_id, payment_method_id)
        references telegrana.payment_methods (account_id, id),
    foreign key (account_id, to_payment_method_id)
        references telegrana.payment_methods (account_id, id),
    -- Gasto e ganho têm categoria; transferência tem destino e não tem categoria.
    check (
        (kind = 'transfer' and to_payment_method_id is not null and category_id is null)
        or (kind <> 'transfer' and to_payment_method_id is null)
    )
);
create index transactions_por_data
    on telegrana.transactions (account_id, cash_on) where deleted_at is null;

-- ---------------------------------------------------------------------------
-- Regras aprendidas ("Drogasil é sempre Saúde", D035)
-- ---------------------------------------------------------------------------
create table telegrana.category_rules (
    account_id  uuid not null references telegrana.accounts (id) on delete cascade,
    id          uuid not null default uuidv7(),
    pattern     text not null check (pattern ~ '^[a-z0-9][a-z0-9 ]{1,59}$'),
    category_id uuid not null,
    created_at  timestamptz not null default now(),
    primary key (account_id, id),
    unique (account_id, pattern),
    foreign key (account_id, category_id)
        references telegrana.categories (account_id, id) on delete cascade
);

-- ---------------------------------------------------------------------------
-- RLS forçado + políticas
-- ---------------------------------------------------------------------------
alter table telegrana.categories      enable row level security;
alter table telegrana.categories      force row level security;
alter table telegrana.payment_methods enable row level security;
alter table telegrana.payment_methods force row level security;
alter table telegrana.transactions    enable row level security;
alter table telegrana.transactions    force row level security;
alter table telegrana.category_rules  enable row level security;
alter table telegrana.category_rules  force row level security;

create policy isolamento on telegrana.categories for all to telegrana_app
    using (account_id = telegrana.current_account_id())
    with check (account_id = telegrana.current_account_id());
create policy isolamento on telegrana.payment_methods for all to telegrana_app
    using (account_id = telegrana.current_account_id())
    with check (account_id = telegrana.current_account_id());
create policy isolamento on telegrana.transactions for all to telegrana_app
    using (account_id = telegrana.current_account_id())
    with check (account_id = telegrana.current_account_id());
create policy isolamento on telegrana.category_rules for all to telegrana_app
    using (account_id = telegrana.current_account_id())
    with check (account_id = telegrana.current_account_id());

create policy migrator on telegrana.categories      for all to telegrana_migrator using (true) with check (true);
create policy migrator on telegrana.payment_methods for all to telegrana_migrator using (true) with check (true);
create policy migrator on telegrana.transactions    for all to telegrana_migrator using (true) with check (true);
create policy migrator on telegrana.category_rules  for all to telegrana_migrator using (true) with check (true);

grant select, insert on telegrana.categories to telegrana_app;
grant update (name, emoji, active, sort) on telegrana.categories to telegrana_app;
grant select, insert on telegrana.payment_methods to telegrana_app;
grant update (name, emoji, active) on telegrana.payment_methods to telegrana_app;
grant select, insert on telegrana.transactions to telegrana_app;
grant update (kind, amount_cents, category_id, payment_method_id, to_payment_method_id,
              occurred_on, cash_on, description, status, updated_at, deleted_at)
    on telegrana.transactions to telegrana_app;
grant select, insert, delete on telegrana.category_rules to telegrana_app;

-- ---------------------------------------------------------------------------
-- Padrões de cada conta (fonte única: chamada ao concluir o cadastro e, abaixo,
-- uma vez para as contas que já existem). SECURITY INVOKER: no app, o RLS só deixa
-- gravar na conta do contexto. Idempotente.
-- ---------------------------------------------------------------------------
create function telegrana.seed_account_defaults(p_account_id uuid) returns void
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
        ('savings', 'Poupança', '🐷')
      ) as d (kind, name, emoji)
    on conflict do nothing;
$$;
revoke all on function telegrana.seed_account_defaults(uuid) from public;
grant execute on function telegrana.seed_account_defaults(uuid) to telegrana_app;

-- Contas que já existem (inclui as em cadastro; quem desistir é apagado em 7 dias).
select telegrana.seed_account_defaults(a.id) from telegrana.accounts a;

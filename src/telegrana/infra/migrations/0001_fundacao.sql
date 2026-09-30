-- 0001 · Fundação: contas, usuários, identidades por canal, termos, convites,
-- pedidos de acesso, deduplicação de updates e auditoria.
--
-- Isolamento (PLANO 8.2, D030):
--   * Tabelas ISOLADAS (dados de uma conta): RLS habilitado e FORÇADO; o papel
--     telegrana_app só enxerga a conta de app.account_id (definido por transação).
--   * O papel telegrana_migrator (dono) tem política própria: é ele que roda as
--     funções SECURITY DEFINER abaixo, os únicos caminhos antes de a conta ser conhecida.
--   * Tabelas GLOBAIS (sem dado financeiro): controladas por GRANT, coluna a coluna
--     quando necessário.
-- Toda tabela nova precisa entrar em ISOLADAS ou GLOBAIS nos testes de isolamento.

-- ---------------------------------------------------------------------------
-- Contexto de conta
-- ---------------------------------------------------------------------------
create function telegrana.current_account_id() returns uuid
    language sql stable
    set search_path = pg_catalog
as $$ select nullif(current_setting('app.account_id', true), '')::uuid $$;

revoke all on function telegrana.current_account_id() from public;
grant usage on schema telegrana to telegrana_app;
grant execute on function telegrana.current_account_id() to telegrana_app;

-- ---------------------------------------------------------------------------
-- Tabelas ISOLADAS
-- ---------------------------------------------------------------------------
-- A conta é o "cofre" de dados; uma pessoa (users) é membro de uma ou mais contas.
create table telegrana.accounts (
    id         uuid primary key default uuidv7(),
    status     text not null default 'onboarding'
               check (status in ('onboarding', 'active', 'blocked')),
    created_at timestamptz not null default now()
);

create table telegrana.users (
    id                uuid primary key default uuidv7(),
    full_name         text check (char_length(full_name) between 2 and 120),
    -- Telefone só como HMAC-SHA256 (32 bytes) com pepper no SSM (PLANO 3.4).
    phone_hmac        bytea unique check (octet_length(phone_hmac) = 32),
    adult_declared_at timestamptz,
    onboarding_step   text not null default 'terms'
                      check (onboarding_step in
                             ('terms', 'name', 'phone', 'adult', 'setup', 'recovery_code', 'done')),
    status            text not null default 'onboarding'
                      check (status in ('onboarding', 'active', 'blocked')),
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);

create table telegrana.account_members (
    account_id uuid not null references telegrana.accounts (id) on delete cascade,
    user_id    uuid not null references telegrana.users (id) on delete cascade,
    role       text not null default 'owner' check (role in ('owner', 'member')),
    created_at timestamptz not null default now(),
    primary key (account_id, user_id)
);
create index account_members_user_idx on telegrana.account_members (user_id);

-- Identidade verificada de cada canal (D022): nada de telegram_id fixo em users.
create table telegrana.user_channels (
    channel     text not null check (channel in ('telegram', 'whatsapp')),
    external_id text not null check (external_id ~ '^[A-Za-z0-9@:._-]{1,64}$'),
    user_id     uuid not null references telegrana.users (id) on delete cascade,
    created_at  timestamptz not null default now(),
    primary key (channel, external_id),
    unique (user_id, channel)  -- V1: uma identidade por canal por pessoa
);

create table telegrana.terms_acceptances (
    account_id     uuid not null,
    id             uuid not null default uuidv7(),
    user_id        uuid not null,
    doc            text not null check (doc in ('termos', 'privacidade')),
    version        integer not null check (version > 0),
    content_sha256 bytea not null check (octet_length(content_sha256) = 32),
    accepted_at    timestamptz not null default now(),
    primary key (account_id, id),
    -- FK composta: o aceite só existe para um membro daquela conta.
    foreign key (account_id, user_id)
        references telegrana.account_members (account_id, user_id) on delete cascade,
    unique (account_id, user_id, doc, version)
);

-- RLS forçado + políticas.
alter table telegrana.accounts          enable row level security;
alter table telegrana.accounts          force row level security;
alter table telegrana.users             enable row level security;
alter table telegrana.users             force row level security;
alter table telegrana.account_members   enable row level security;
alter table telegrana.account_members   force row level security;
alter table telegrana.user_channels     enable row level security;
alter table telegrana.user_channels     force row level security;
alter table telegrana.terms_acceptances enable row level security;
alter table telegrana.terms_acceptances force row level security;

create policy isolamento on telegrana.accounts for all to telegrana_app
    using (id = telegrana.current_account_id())
    with check (id = telegrana.current_account_id());

create policy isolamento on telegrana.account_members for all to telegrana_app
    using (account_id = telegrana.current_account_id())
    with check (account_id = telegrana.current_account_id());

create policy isolamento on telegrana.terms_acceptances for all to telegrana_app
    using (account_id = telegrana.current_account_id())
    with check (account_id = telegrana.current_account_id());

-- Pessoa e identidades: visíveis só se a pessoa for membro da conta do contexto
-- (account_members já passa pelo RLS acima).
create policy isolamento on telegrana.users for all to telegrana_app
    using (exists (select 1 from telegrana.account_members m
                   where m.user_id = users.id
                     and m.account_id = telegrana.current_account_id()))
    with check (exists (select 1 from telegrana.account_members m
                        where m.user_id = users.id
                          and m.account_id = telegrana.current_account_id()));

create policy isolamento on telegrana.user_channels for all to telegrana_app
    using (exists (select 1 from telegrana.account_members m
                   where m.user_id = user_channels.user_id
                     and m.account_id = telegrana.current_account_id()))
    with check (exists (select 1 from telegrana.account_members m
                        where m.user_id = user_channels.user_id
                          and m.account_id = telegrana.current_account_id()));

-- O dono (migrator) acessa tudo: migrações e funções SECURITY DEFINER.
create policy migrator on telegrana.accounts          for all to telegrana_migrator using (true) with check (true);
create policy migrator on telegrana.users             for all to telegrana_migrator using (true) with check (true);
create policy migrator on telegrana.account_members   for all to telegrana_migrator using (true) with check (true);
create policy migrator on telegrana.user_channels     for all to telegrana_migrator using (true) with check (true);
create policy migrator on telegrana.terms_acceptances for all to telegrana_migrator using (true) with check (true);

grant select, delete on telegrana.accounts to telegrana_app;
grant select, delete on telegrana.users to telegrana_app;
grant update (full_name, phone_hmac, adult_declared_at, onboarding_step, status, updated_at)
    on telegrana.users to telegrana_app;
grant select on telegrana.account_members to telegrana_app;
grant select, insert, delete on telegrana.user_channels to telegrana_app;
grant select, insert on telegrana.terms_acceptances to telegrana_app;

-- ---------------------------------------------------------------------------
-- Tabelas GLOBAIS (sem dado financeiro; acesso só por GRANT)
-- ---------------------------------------------------------------------------
-- Link de convite reutilizável: o token existe só como SHA-256 (PLANO 3.2).
create table telegrana.invite_links (
    id           uuid primary key default uuidv7(),
    token_sha256 bytea not null unique check (octet_length(token_sha256) = 32),
    max_uses     integer not null default 20 check (max_uses between 1 and 100),
    uses         integer not null default 0 check (uses between 0 and max_uses),
    expires_at   timestamptz,
    revoked_at   timestamptz,
    created_at   timestamptz not null default now()
);

-- Pedido de acesso de quem achou o bot sozinho; apagado em 7 dias (PLANO 3.2).
create table telegrana.access_requests (
    id           uuid primary key default uuidv7(),
    channel      text not null check (channel in ('telegram', 'whatsapp')),
    external_id  text not null check (external_id ~ '^[A-Za-z0-9@:._-]{1,64}$'),
    display_name text not null check (char_length(display_name) between 1 and 128),
    username     text check (char_length(username) <= 64),
    message      text not null check (char_length(message) between 1 and 200),
    status       text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
    created_at   timestamptz not null default now(),
    decided_at   timestamptz,
    expires_at   timestamptz not null default now() + interval '7 days'
);
-- No máximo um pedido pendente por pessoa.
create unique index access_requests_um_pendente
    on telegrana.access_requests (channel, external_id) where status = 'pending';

-- Idempotência do webhook (PLANO 8.1): update repetido é ignorado.
create table telegrana.processed_updates (
    channel      text not null check (channel in ('telegram', 'whatsapp')),
    update_id    bigint not null,
    processed_at timestamptz not null default now(),
    primary key (channel, update_id)
);

-- Auditoria somente de acréscimo, sem dados pessoais (ids técnicos e evento).
create table telegrana.audit_log (
    id         bigint generated always as identity primary key,
    at         timestamptz not null default now(),
    account_id uuid,  -- sem FK: o registro de exclusão de conta permanece, anônimo
    actor      text not null check (actor in ('system', 'admin', 'user')),
    event      text not null check (event ~ '^[a-z][a-z_.]{2,63}$'),
    details    jsonb not null default '{}'::jsonb
);

grant select, insert on telegrana.invite_links to telegrana_app;
grant update (uses, revoked_at) on telegrana.invite_links to telegrana_app;
grant select, insert, delete on telegrana.access_requests to telegrana_app;
grant update (status, decided_at) on telegrana.access_requests to telegrana_app;
grant select, insert, delete on telegrana.processed_updates to telegrana_app;
grant insert on telegrana.audit_log to telegrana_app;  -- o app não lê nem altera a auditoria

-- ---------------------------------------------------------------------------
-- Funções SECURITY DEFINER: os únicos caminhos antes de a conta ser conhecida
-- ---------------------------------------------------------------------------
-- Quem é esta identidade verificada do canal? (nenhuma linha = pessoa sem conta)
create function telegrana.resolve_identity(p_channel text, p_external_id text)
    returns table (o_user_id uuid, o_account_id uuid, o_user_status text)
    language sql stable
    security definer
    set search_path = pg_catalog, telegrana
as $$
    select c.user_id, m.account_id, u.status
      from telegrana.user_channels c
      join telegrana.users u on u.id = c.user_id
      join telegrana.account_members m on m.user_id = c.user_id and m.role = 'owner'
     where c.channel = p_channel
       and c.external_id = p_external_id
$$;

-- Início do cadastro (depois de o convite ou o pedido de acesso ser validado pelo
-- código): cria conta + pessoa + vínculo + identidade de uma vez. Idempotente.
create function telegrana.start_onboarding(p_channel text, p_external_id text)
    returns table (o_user_id uuid, o_account_id uuid, o_created boolean)
    language plpgsql
    security definer
    set search_path = pg_catalog, telegrana
as $$
declare
    v_user    uuid;
    v_account uuid;
begin
    select r.o_user_id, r.o_account_id into v_user, v_account
      from telegrana.resolve_identity(p_channel, p_external_id) r;
    if found then
        return query select v_user, v_account, false;
        return;
    end if;

    begin
        insert into telegrana.accounts default values returning id into v_account;
        insert into telegrana.users default values returning id into v_user;
        insert into telegrana.account_members (account_id, user_id, role)
             values (v_account, v_user, 'owner');
        insert into telegrana.user_channels (channel, external_id, user_id)
             values (p_channel, p_external_id, v_user);
    exception when unique_violation then
        -- Corrida: outra transação cadastrou a mesma identidade primeiro.
        select r.o_user_id, r.o_account_id into v_user, v_account
          from telegrana.resolve_identity(p_channel, p_external_id) r;
        return query select v_user, v_account, false;
        return;
    end;
    return query select v_user, v_account, true;
end
$$;

revoke all on function telegrana.resolve_identity(text, text) from public;
revoke all on function telegrana.start_onboarding(text, text) from public;
grant execute on function telegrana.resolve_identity(text, text) to telegrana_app;
grant execute on function telegrana.start_onboarding(text, text) to telegrana_app;

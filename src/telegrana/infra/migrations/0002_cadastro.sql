-- 0002 · Cadastro e recuperação (S1.4, D033): código de recuperação, travas de
-- tentativas, pedido de recuperação manual e os caminhos SECURITY DEFINER que
-- precisam enxergar além de uma conta (recuperar, religar, apagar, limpar).

-- ---------------------------------------------------------------------------
-- Ajustes nas tabelas da 0001
-- ---------------------------------------------------------------------------
-- Convite usado para criar a conta (só para o aviso ao admin e o /link status).
alter table telegrana.accounts
    add column invite_link_id uuid references telegrana.invite_links (id) on delete set null;
grant update (status, invite_link_id) on telegrana.accounts to telegrana_app;

-- O mesmo fluxo de pedido serve para "quero entrar" e "perdi o acesso" (PLANO 3.5).
alter table telegrana.access_requests
    add column kind text not null default 'access' check (kind in ('access', 'recovery'));

-- ---------------------------------------------------------------------------
-- Código de recuperação (ISOLADA)
-- ---------------------------------------------------------------------------
-- Código = seletor (8 caracteres, em claro, para achar a linha) + verificador
-- (12 caracteres, só como hash Argon2id). PLANO 3.3 e 3.5.
create table telegrana.recovery_codes (
    account_id    uuid not null,
    user_id       uuid not null,
    selector      text not null unique check (selector ~ '^[0-9A-HJKMNP-TV-Z]{8}$'),
    verifier_hash text not null check (char_length(verifier_hash) between 32 and 256),
    created_at    timestamptz not null default now(),
    primary key (account_id, user_id),
    foreign key (account_id, user_id)
        references telegrana.account_members (account_id, user_id) on delete cascade
);

alter table telegrana.recovery_codes enable row level security;
alter table telegrana.recovery_codes force row level security;
create policy isolamento on telegrana.recovery_codes for all to telegrana_app
    using (account_id = telegrana.current_account_id())
    with check (account_id = telegrana.current_account_id());
create policy migrator on telegrana.recovery_codes for all to telegrana_migrator
    using (true) with check (true);
grant select, insert, delete on telegrana.recovery_codes to telegrana_app;

-- ---------------------------------------------------------------------------
-- Travas de tentativas (GLOBAL; sem dado financeiro; apagadas em 1 dia)
-- ---------------------------------------------------------------------------
create table telegrana.auth_attempts (
    channel      text not null check (channel in ('telegram', 'whatsapp')),
    external_id  text not null check (external_id ~ '^[A-Za-z0-9@:._-]{1,64}$'),
    kind         text not null check (kind in ('code', 'phone')),
    failures     integer not null default 0 check (failures >= 0),
    locked_until timestamptz,
    updated_at   timestamptz not null default now(),
    primary key (channel, external_id, kind)
);
grant select, insert, delete on telegrana.auth_attempts to telegrana_app;
grant update (failures, locked_until, updated_at) on telegrana.auth_attempts to telegrana_app;

-- ---------------------------------------------------------------------------
-- Auxiliar interna (sem EXECUTE para o app): apaga a pessoa, as contas em que ela
-- é a única dona e a auditoria dessas contas.
-- ---------------------------------------------------------------------------
create function telegrana._erase_person(p_user_id uuid) returns void
    language plpgsql
    set search_path = pg_catalog, telegrana
as $$
declare
    v_contas uuid[];
begin
    select coalesce(array_agg(m.account_id), '{}') into v_contas
      from telegrana.account_members m
     where m.user_id = p_user_id
       and m.role = 'owner'
       and not exists (select 1 from telegrana.account_members o
                        where o.account_id = m.account_id and o.user_id <> p_user_id);
    delete from telegrana.audit_log where account_id = any (v_contas);
    delete from telegrana.accounts where id = any (v_contas);
    delete from telegrana.users where id = p_user_id;
end
$$;
revoke all on function telegrana._erase_person(uuid) from public;

-- ---------------------------------------------------------------------------
-- Funções SECURITY DEFINER
-- ---------------------------------------------------------------------------
-- Recuperação por código: acha a linha pelo seletor; o Argon2id é conferido no código.
create function telegrana.recovery_lookup(p_selector text)
    returns table (o_account_id uuid, o_user_id uuid, o_verifier_hash text)
    language sql stable
    security definer
    set search_path = pg_catalog, telegrana
as $$
    select r.account_id, r.user_id, r.verifier_hash
      from telegrana.recovery_codes r
      join telegrana.users u on u.id = r.user_id
     where r.selector = p_selector
       and u.status <> 'onboarding'
$$;

-- Recuperação por telefone: o HMAC chega do código, calculado a partir do contato
-- que o próprio Telegram atesta ser do remetente.
create function telegrana.find_user_by_phone(p_phone_hmac bytea)
    returns table (o_account_id uuid, o_user_id uuid, o_status text)
    language sql stable
    security definer
    set search_path = pg_catalog, telegrana
as $$
    select m.account_id, u.id, u.status
      from telegrana.users u
      join telegrana.account_members m on m.user_id = u.id and m.role = 'owner'
     where u.phone_hmac = p_phone_hmac
$$;

-- Religa uma pessoa a outra identidade do canal (recuperação). Um cadastro
-- inacabado na identidade nova é descartado; uma conta de verdade, nunca.
-- o_result: 'ok' | 'same' | 'in_use' | 'missing'.
create function telegrana.relink_identity(p_channel text, p_external_id text, p_user_id uuid)
    returns table (o_result text, o_account_id uuid, o_old_external_id text)
    language plpgsql
    security definer
    set search_path = pg_catalog, telegrana
as $$
declare
    v_conta  uuid;
    v_atual  uuid;
    v_status text;
    v_antigo text;
begin
    select m.account_id into v_conta
      from telegrana.account_members m
     where m.user_id = p_user_id and m.role = 'owner';
    if not found then
        return query select 'missing'::text, null::uuid, null::text;
        return;
    end if;

    select c.user_id, u.status into v_atual, v_status
      from telegrana.user_channels c
      join telegrana.users u on u.id = c.user_id
     where c.channel = p_channel and c.external_id = p_external_id;
    if found then
        if v_atual = p_user_id then
            return query select 'same'::text, v_conta, null::text;
            return;
        end if;
        if v_status <> 'onboarding' then
            return query select 'in_use'::text, null::uuid, null::text;
            return;
        end if;
        perform telegrana._erase_person(v_atual);
    end if;

    delete from telegrana.user_channels
     where user_id = p_user_id and channel = p_channel
    returning external_id into v_antigo;
    insert into telegrana.user_channels (channel, external_id, user_id)
         values (p_channel, p_external_id, p_user_id);
    return query select 'ok'::text, v_conta, v_antigo;
end
$$;

-- Exclusão definitiva (/apagar_conta e "menor de idade"): só da conta do contexto.
-- Fica apenas o evento anônimo, sem account_id (Política de Privacidade, seção 8).
create function telegrana.erase_account(p_account_id uuid) returns void
    language plpgsql
    security definer
    set search_path = pg_catalog, telegrana
as $$
declare
    v_user uuid;
begin
    if p_account_id is distinct from telegrana.current_account_id() then
        raise exception 'erase_account: conta fora do contexto';
    end if;
    for v_user in
        select m.user_id from telegrana.account_members m where m.account_id = p_account_id
    loop
        perform telegrana._erase_person(v_user);
    end loop;
    insert into telegrana.audit_log (actor, event) values ('user', 'account.deleted');
end
$$;

-- Limpeza diária: cadastros não concluídos há mais de p_idade (PLANO 3.3).
create function telegrana.purge_stale_onboarding(p_idade interval) returns integer
    language plpgsql
    security definer
    set search_path = pg_catalog, telegrana
as $$
declare
    v_user uuid;
    v_total integer := 0;
begin
    for v_user in
        select u.id from telegrana.users u
         where u.status = 'onboarding' and u.created_at < now() - p_idade
    loop
        perform telegrana._erase_person(v_user);
        v_total := v_total + 1;
    end loop;
    return v_total;
end
$$;

-- Lista de pessoas para o admin (recuperação manual, bloqueio). O código só chama
-- quando o remetente é o ADMIN_TELEGRAM_ID.
create function telegrana.admin_list_users()
    returns table (o_account_id uuid, o_user_id uuid, o_full_name text, o_status text,
                   o_created_at timestamptz)
    language sql stable
    security definer
    set search_path = pg_catalog, telegrana
as $$
    select m.account_id, u.id, u.full_name, u.status, u.created_at
      from telegrana.users u
      join telegrana.account_members m on m.user_id = u.id and m.role = 'owner'
     where u.status <> 'onboarding'
     order by u.full_name
$$;

revoke all on function telegrana.recovery_lookup(text) from public;
revoke all on function telegrana.find_user_by_phone(bytea) from public;
revoke all on function telegrana.relink_identity(text, text, uuid) from public;
revoke all on function telegrana.erase_account(uuid) from public;
revoke all on function telegrana.purge_stale_onboarding(interval) from public;
revoke all on function telegrana.admin_list_users() from public;
grant execute on function telegrana.recovery_lookup(text) to telegrana_app;
grant execute on function telegrana.find_user_by_phone(bytea) to telegrana_app;
grant execute on function telegrana.relink_identity(text, text, uuid) to telegrana_app;
grant execute on function telegrana.erase_account(uuid) to telegrana_app;
grant execute on function telegrana.purge_stale_onboarding(interval) to telegrana_app;
grant execute on function telegrana.admin_list_users() to telegrana_app;

-- 0014 · Limites de uso por pessoa (S8, PLANO 8.6, D051).
-- Um contador por conta e dia (fuso de São Paulo): mensagens (com o minuto corrente),
-- chamadas à IA, segundos de áudio e arquivos exportados. Só números: nenhum conteúdo.

-- ---------------------------------------------------------------------------
-- Uso do dia (ISOLADA)
-- ---------------------------------------------------------------------------
create table telegrana.account_usage (
    account_id      uuid not null references telegrana.accounts (id) on delete cascade,
    id              uuid not null default uuidv7(),
    day             date not null,
    messages        integer not null default 0 check (messages >= 0),
    minute          timestamptz,
    minute_messages integer not null default 0 check (minute_messages >= 0),
    ai_calls        integer not null default 0 check (ai_calls >= 0),
    audio_seconds   integer not null default 0 check (audio_seconds >= 0),
    exports         integer not null default 0 check (exports >= 0),
    primary key (account_id, id),
    unique (account_id, day)
);
alter table telegrana.account_usage enable row level security;
alter table telegrana.account_usage force row level security;
create policy isolamento on telegrana.account_usage for all to telegrana_app
    using (account_id = telegrana.current_account_id())
    with check (account_id = telegrana.current_account_id());
create policy migrator on telegrana.account_usage for all to telegrana_migrator using (true) with check (true);
grant select, insert, update on telegrana.account_usage to telegrana_app;

-- ---------------------------------------------------------------------------
-- Limpeza: o uso de mais de 35 dias sai junto com os outros temporários
-- ---------------------------------------------------------------------------
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
    v_usage   integer;
begin
    delete from telegrana.pending_entries where expires_at < now();
    get diagnostics v_drafts = row_count;
    delete from telegrana.message_refs where created_at < now() - interval '30 days';
    get diagnostics v_refs = row_count;
    delete from telegrana.reminder_sends where sent_at < now() - interval '60 days';
    get diagnostics v_sends = row_count;
    delete from telegrana.invoice_notices where sent_at < now() - interval '60 days';
    get diagnostics v_notices = row_count;
    delete from telegrana.account_usage where day < current_date - 35;
    get diagnostics v_usage = row_count;
    return query select v_drafts, v_refs, v_sends + v_notices + v_usage;
end
$$;

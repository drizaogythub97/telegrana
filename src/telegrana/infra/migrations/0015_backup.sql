-- 0015 · Papel de backup (S8, PLANO 12 "Backup", D052).
-- `telegrana_backup` só lê: o papel nasce em infra/bootstrap.py (NOLOGIN) e toda transação
-- dele é READ ONLY. Lê todas as contas por políticas de LEITURA explícitas em cada tabela
-- com RLS (não por BYPASSRLS); o teste de isolamento confere que toda tabela nova tem a sua.

grant usage on schema telegrana to telegrana_backup;
grant select on all tables in schema telegrana to telegrana_backup;
alter default privileges for role telegrana_migrator in schema telegrana
    grant select on tables to telegrana_backup;

do $$
declare
    t record;
begin
    for t in
        select c.relname
          from pg_class c
          join pg_namespace n on n.oid = c.relnamespace
         where n.nspname = 'telegrana' and c.relkind = 'r' and c.relrowsecurity
    loop
        execute format(
            'create policy backup on telegrana.%I for select to telegrana_backup using (true)',
            t.relname
        );
    end loop;
end
$$;

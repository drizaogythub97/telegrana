-- S3.1 (D041): o medidor de uso também conta segundos de áudio (Whisper).
-- Continua GLOBAL e sem dado pessoal: dia, modelo, número de chamadas e quantidades.
alter table telegrana.ai_usage
    add column audio_seconds bigint not null default 0 check (audio_seconds >= 0);
grant update (audio_seconds) on telegrana.ai_usage to telegrana_app;

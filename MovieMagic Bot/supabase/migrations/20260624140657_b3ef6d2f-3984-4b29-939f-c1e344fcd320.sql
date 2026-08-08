
create table if not exists public.scheduled_deletions (
  id bigserial primary key,
  chat_id bigint not null,
  message_id bigint not null,
  delete_at timestamptz not null,
  created_at timestamptz not null default now()
);
grant all on public.scheduled_deletions to service_role;
grant usage, select on sequence public.scheduled_deletions_id_seq to service_role;
alter table public.scheduled_deletions enable row level security;
create index if not exists idx_scheduled_deletions_due on public.scheduled_deletions (delete_at);

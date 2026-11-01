create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  telegram_id bigint not null unique,
  first_name text,
  username text,
  timezone text not null default 'America/Recife',
  currency char(3) not null default 'BRL',
  created_at timestamptz not null default now()
);

create table if not exists categories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  name text not null,
  kind text not null default 'expense' check (kind in ('expense', 'income')),
  keywords text[] not null default '{}',
  created_at timestamptz not null default now(),
  unique (user_id, name)
);

create table if not exists transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  category_id uuid references categories(id) on delete set null,
  kind text not null default 'expense' check (kind in ('expense', 'income')),
  amount_cents integer not null check (amount_cents > 0),
  description text not null check (length(description) between 1 and 500),
  occurred_at date not null default current_date,
  source text not null default 'text' check (source in ('text', 'audio', 'manual', 'import')),
  raw_text text,
  status text not null default 'confirmed' check (status in ('pending', 'confirmed', 'corrected', 'deleted')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists transactions_user_occurred_idx on transactions (user_id, occurred_at desc);
create index if not exists transactions_user_status_idx on transactions (user_id, status);
create index if not exists transactions_category_idx on transactions (category_id);

create table if not exists audit_log (
  id bigserial primary key,
  user_id uuid references users(id) on delete set null,
  transaction_id uuid references transactions(id) on delete set null,
  action text not null,
  before jsonb,
  after jsonb,
  created_at timestamptz not null default now()
);

create index if not exists audit_log_user_created_idx on audit_log (user_id, created_at desc);

create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists transactions_set_updated_at on transactions;

create trigger transactions_set_updated_at
before update on transactions
for each row execute function set_updated_at();

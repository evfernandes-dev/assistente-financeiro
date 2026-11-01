import { neon } from "@neondatabase/serverless";
import type { Env } from "./index";
import type { TelegramMessage } from "./telegram";

export interface User {
  id: string;
  telegram_id: string;
  first_name: string | null;
  username: string | null;
  timezone: string;
  currency: string;
}

export interface Transaction {
  id: string;
  user_id: string;
  category_id: string | null;
  category_name: string | null;
  kind: "expense" | "income";
  amount_cents: number;
  description: string;
  occurred_at: string;
  status: string;
  created_at: string;
}

export interface MonthlySummary {
  expense_cents: number;
  income_cents: number;
  transaction_count: number;
}

export interface CategoryTotal {
  category: string;
  total_cents: number;
}

const DEFAULT_CATEGORIES = [
  { name: "Alimentação", kind: "expense" },
  { name: "Transporte", kind: "expense" },
  { name: "Moradia", kind: "expense" },
  { name: "Saúde", kind: "expense" },
  { name: "Educação", kind: "expense" },
  { name: "Lazer", kind: "expense" },
  { name: "Assinaturas", kind: "expense" },
  { name: "Outros", kind: "expense" },
  { name: "Salário", kind: "income" },
  { name: "Outras receitas", kind: "income" },
];

export const CATEGORY_NAMES = DEFAULT_CATEGORIES.map((category) => category.name);

function db(env: Env) {
  return neon(env.DATABASE_URL);
}

export async function ensureUser(from: TelegramMessage["from"], env: Env): Promise<User> {
  if (!from) {
    throw new Error("Update sem usuário");
  }

  const sql = db(env);

  const rows = (await sql`
    insert into users (telegram_id, first_name, username)
    values (${String(from.id)}, ${from.first_name ?? null}, ${from.username ?? null})
    on conflict (telegram_id) do update
      set first_name = excluded.first_name,
          username = excluded.username
    returning *
  `) as User[];

  const user = rows[0];

  await sql`
    insert into categories (user_id, name, kind)
    select ${user.id}, c.name, c.kind
    from jsonb_to_recordset(${JSON.stringify(DEFAULT_CATEGORIES)}::jsonb) as c(name text, kind text)
    on conflict (user_id, name) do nothing
  `;

  return user;
}

export async function createTransaction(
  input: {
    userId: string;
    kind: "expense" | "income";
    amount: number;
    description: string;
    category?: string;
    occurredAt: string;
    source: "text" | "audio" | "manual" | "import";
    rawText?: string;
  },
  env: Env,
): Promise<Transaction> {
  const sql = db(env);

  const rows = (await sql`
    with inserted as (
      insert into transactions (user_id, category_id, kind, amount_cents, description, occurred_at, source, raw_text)
      values (
        ${input.userId},
        (
          select id from categories
          where user_id = ${input.userId} and name = ${input.category ?? "Outros"}
          limit 1
        ),
        ${input.kind},
        ${Math.round(input.amount * 100)},
        ${input.description},
        ${input.occurredAt}::date,
        ${input.source},
        ${input.rawText ?? null}
      )
      returning id, user_id, category_id, kind, amount_cents, description, occurred_at, status, created_at
    ),
    audit as (
      insert into audit_log (user_id, transaction_id, action, after)
      select i.user_id, i.id, 'create', to_jsonb(i)
      from inserted i
      returning id
    )
    select i.id, i.user_id, i.category_id, c.name as category_name, i.kind, i.amount_cents, i.description,
           to_char(i.occurred_at, 'YYYY-MM-DD') as occurred_at, i.status, i.created_at
    from inserted i
    left join categories c on c.id = i.category_id
  `) as Transaction[];

  return rows[0];
}

export async function listTransactions(
  input: { userId: string; from: string; to: string; limit?: number; category?: string },
  env: Env,
): Promise<Transaction[]> {
  const sql = db(env);
  const limit = Math.min(Math.max(Math.trunc(input.limit ?? 20), 1), 100);
  const category = input.category ?? null;

  return (await sql`
    select t.id, t.user_id, t.category_id, c.name as category_name, t.kind, t.amount_cents, t.description,
           to_char(t.occurred_at, 'YYYY-MM-DD') as occurred_at, t.status, t.created_at
    from transactions t
    left join categories c on c.id = t.category_id
    where t.user_id = ${input.userId}
      and t.status <> 'deleted'
      and t.occurred_at between ${input.from}::date and ${input.to}::date
      and (${category}::text is null or c.name = ${category})
    order by t.occurred_at desc, t.created_at desc
    limit ${limit}
  `) as Transaction[];
}

export async function getMonthlySummary(
  input: { userId: string; from: string; to: string; category?: string },
  env: Env,
): Promise<{ totals: MonthlySummary; byCategory: CategoryTotal[] }> {
  const sql = db(env);
  const category = input.category ?? null;

  const totalsRows = (await sql`
    select
      coalesce(sum(case when t.kind = 'expense' then t.amount_cents end), 0)::int as expense_cents,
      coalesce(sum(case when t.kind = 'income' then t.amount_cents end), 0)::int as income_cents,
      count(*)::int as transaction_count
    from transactions t
    left join categories c on c.id = t.category_id
    where t.user_id = ${input.userId}
      and t.status <> 'deleted'
      and t.occurred_at between ${input.from}::date and ${input.to}::date
      and (${category}::text is null or c.name = ${category})
  `) as MonthlySummary[];

  const byCategory = (await sql`
    select coalesce(c.name, 'Sem categoria') as category, sum(t.amount_cents)::int as total_cents
    from transactions t
    left join categories c on c.id = t.category_id
    where t.user_id = ${input.userId}
      and t.kind = 'expense'
      and t.status <> 'deleted'
      and t.occurred_at between ${input.from}::date and ${input.to}::date
      and (${category}::text is null or c.name = ${category})
    group by 1
    order by 2 desc
  `) as CategoryTotal[];

  return { totals: totalsRows[0], byCategory };
}

export async function getLatestTransaction(userId: string, env: Env): Promise<Transaction | null> {
  const sql = db(env);

  const rows = (await sql`
    select t.id, t.user_id, t.category_id, c.name as category_name, t.kind, t.amount_cents, t.description,
           to_char(t.occurred_at, 'YYYY-MM-DD') as occurred_at, t.status, t.created_at
    from transactions t
    left join categories c on c.id = t.category_id
    where t.user_id = ${userId} and t.status <> 'deleted'
    order by t.created_at desc
    limit 1
  `) as Transaction[];

  return rows[0] ?? null;
}

export async function updateTransaction(
  input: {
    userId: string;
    id: string;
    amount?: number;
    description?: string;
    categoryName?: string;
    occurredAt?: string;
  },
  env: Env,
): Promise<Transaction | null> {
  const sql = db(env);

  const amountCents = input.amount !== undefined ? Math.round(input.amount * 100) : null;
  const description = input.description ?? null;
  const occurredAt = input.occurredAt ?? null;

  const categoryId = input.categoryName
    ? ((
        await sql`
          select id from categories
          where user_id = ${input.userId} and name = ${input.categoryName}
          limit 1
        `
      ) as Array<{ id: string }>)[0]?.id ?? null
    : null;

  const rows = (await sql`
    with target as (
      select * from transactions
      where id = ${input.id}
        and user_id = ${input.userId}
        and status <> 'deleted'
    ),
    updated as (
      update transactions t
      set amount_cents = coalesce(${amountCents}::int, t.amount_cents),
          description = coalesce(${description}::text, t.description),
          category_id = coalesce(${categoryId}::uuid, t.category_id),
          occurred_at = coalesce(${occurredAt}::date, t.occurred_at),
          status = 'corrected'
      from target
      where t.id = target.id
      returning t.id, t.user_id, t.category_id, t.kind, t.amount_cents, t.description, t.occurred_at, t.status, t.created_at
    ),
    audit as (
      insert into audit_log (user_id, transaction_id, action, before, after)
      select target.user_id, target.id, 'correct', to_jsonb(target), to_jsonb(updated)
      from target
      join updated on updated.id = target.id
      returning id
    )
    select u.id, u.user_id, u.category_id, c.name as category_name, u.kind, u.amount_cents, u.description,
           to_char(u.occurred_at, 'YYYY-MM-DD') as occurred_at, u.status, u.created_at
    from updated u
    left join categories c on c.id = u.category_id
  `) as Transaction[];

  return rows[0] ?? null;
}

export async function deleteTransaction(
  input: { userId: string; id: string },
  env: Env,
): Promise<Transaction | null> {
  const sql = db(env);

  const rows = (await sql`
    with target as (
      select * from transactions
      where id = ${input.id}
        and user_id = ${input.userId}
        and status <> 'deleted'
    ),
    deleted as (
      update transactions t
      set status = 'deleted'
      from target
      where t.id = target.id
      returning t.id, t.user_id, t.category_id, t.kind, t.amount_cents, t.description, t.occurred_at, t.status, t.created_at
    ),
    audit as (
      insert into audit_log (user_id, transaction_id, action, before, after)
      select target.user_id, target.id, 'delete', to_jsonb(target), to_jsonb(deleted)
      from target
      join deleted on deleted.id = target.id
      returning id
    )
    select d.id, d.user_id, d.category_id, c.name as category_name, d.kind, d.amount_cents, d.description,
           to_char(d.occurred_at, 'YYYY-MM-DD') as occurred_at, d.status, d.created_at
    from deleted d
    left join categories c on c.id = d.category_id
  `) as Transaction[];

  return rows[0] ?? null;
}

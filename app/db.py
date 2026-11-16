from __future__ import annotations

import datetime as dt
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import asyncpg

from .categories import DEFAULT_CATEGORIES
from .models import CategoryTotal, Kind, MonthlySummary, Transaction, User


class FinanceRepository(Protocol):
    async def ensure_user(
        self,
        telegram_id: int | str,
        first_name: str | None = None,
        username: str | None = None,
    ) -> User: ...

    async def create_transaction(
        self,
        *,
        user_id: str,
        kind: Kind,
        amount: float,
        description: str,
        category: str | None,
        occurred_at: str,
        source: str,
        raw_text: str | None = None,
    ) -> Transaction: ...

    async def list_transactions(
        self,
        *,
        user_id: str,
        from_date: str,
        to_date: str,
        limit: int = 20,
        category: str | None = None,
    ) -> list[Transaction]: ...

    async def get_monthly_summary(
        self,
        *,
        user_id: str,
        from_date: str,
        to_date: str,
        category: str | None = None,
    ) -> tuple[MonthlySummary, list[CategoryTotal]]: ...

    async def get_latest_transaction(self, user_id: str) -> Transaction | None: ...

    async def update_transaction(
        self,
        *,
        user_id: str,
        transaction_id: str,
        amount: float | None = None,
        description: str | None = None,
        category_name: str | None = None,
        occurred_at: str | None = None,
    ) -> Transaction | None: ...

    async def delete_transaction(
        self,
        *,
        user_id: str,
        transaction_id: str,
    ) -> Transaction | None: ...


def _to_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def normalise_database_url(database_url: str) -> str:
    """Remove libpq options that asyncpg would forward as invalid server settings."""
    parts = urlsplit(database_url)
    if not parts.query:
        return database_url

    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() != "channel_binding"
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _transaction_from_record(record: asyncpg.Record) -> Transaction:
    created_at = record["created_at"]
    occurred_at = record["occurred_at"]

    return Transaction(
        id=str(record["id"]),
        user_id=str(record["user_id"]),
        category_id=str(record["category_id"]) if record["category_id"] else None,
        category_name=record["category_name"],
        kind=record["kind"],
        amount_cents=int(record["amount_cents"]),
        description=record["description"],
        occurred_at=(
            occurred_at.isoformat() if isinstance(occurred_at, dt.date) else str(occurred_at)
        ),
        status=record["status"],
        created_at=(
            created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
        ),
    )


def _user_from_record(record: asyncpg.Record) -> User:
    return User(
        id=str(record["id"]),
        telegram_id=str(record["telegram_id"]),
        first_name=record["first_name"],
        username=record["username"],
        timezone=record["timezone"],
        currency=record["currency"],
    )


class PostgresRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            normalise_database_url(self._database_url),
            min_size=1,
            max_size=5,
            statement_cache_size=0,
        )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def _fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        if self._pool is None:
            raise RuntimeError("Banco de dados não conectado")
        async with self._pool.acquire() as connection:
            return await connection.fetch(query, *args)

    async def _execute(self, query: str, *args: Any) -> None:
        if self._pool is None:
            raise RuntimeError("Banco de dados não conectado")
        async with self._pool.acquire() as connection:
            await connection.execute(query, *args)

    async def ensure_user(
        self,
        telegram_id: int | str,
        first_name: str | None = None,
        username: str | None = None,
    ) -> User:
        rows = await self._fetch(
            """
            insert into users (telegram_id, first_name, username)
            values ($1, $2, $3)
            on conflict (telegram_id) do update
              set first_name = excluded.first_name,
                  username = excluded.username
            returning id, telegram_id, first_name, username, timezone, currency
            """,
            int(telegram_id),
            first_name,
            username,
        )
        user = _user_from_record(rows[0])

        await self._execute(
            """
            insert into categories (user_id, name, kind)
            select $1::uuid, c.name, c.kind
            from unnest($2::text[], $3::text[]) as c(name, kind)
            on conflict (user_id, name) do nothing
            """,
            user.id,
            [name for name, _ in DEFAULT_CATEGORIES],
            [kind for _, kind in DEFAULT_CATEGORIES],
        )

        return user

    async def create_transaction(
        self,
        *,
        user_id: str,
        kind: Kind,
        amount: float,
        description: str,
        category: str | None,
        occurred_at: str,
        source: str,
        raw_text: str | None = None,
    ) -> Transaction:
        rows = await self._fetch(
            """
            with inserted as (
              insert into transactions
                (user_id, category_id, kind, amount_cents, description, occurred_at,
                 source, raw_text)
              values (
                $1::uuid,
                (
                  select id from categories
                  where user_id = $1::uuid and name = $2
                  limit 1
                ),
                $3,
                $4,
                $5,
                $6::date,
                $7,
                $8
              )
              returning id, user_id, category_id, kind, amount_cents, description,
                        occurred_at, status, created_at
            ),
            audit as (
              insert into audit_log (user_id, transaction_id, action, after)
              select i.user_id, i.id, 'create', to_jsonb(i)
              from inserted i
              returning id
            )
            select i.id, i.user_id, i.category_id, c.name as category_name, i.kind,
                   i.amount_cents, i.description,
                   to_char(i.occurred_at, 'YYYY-MM-DD') as occurred_at,
                   i.status, i.created_at
            from inserted i
            left join categories c on c.id = i.category_id
            """,
            user_id,
            category or "Outros",
            kind,
            round(amount * 100),
            description,
            _to_date(occurred_at),
            source,
            raw_text,
        )
        return _transaction_from_record(rows[0])

    async def list_transactions(
        self,
        *,
        user_id: str,
        from_date: str,
        to_date: str,
        limit: int = 20,
        category: str | None = None,
    ) -> list[Transaction]:
        safe_limit = min(max(int(limit), 1), 100)
        rows = await self._fetch(
            """
            select t.id, t.user_id, t.category_id, c.name as category_name, t.kind,
                   t.amount_cents, t.description,
                   to_char(t.occurred_at, 'YYYY-MM-DD') as occurred_at,
                   t.status, t.created_at
            from transactions t
            left join categories c on c.id = t.category_id
            where t.user_id = $1::uuid
              and t.status <> 'deleted'
              and t.occurred_at between $2::date and $3::date
              and ($5::text is null or c.name = $5)
            order by t.occurred_at desc, t.created_at desc
            limit $4
            """,
            user_id,
            _to_date(from_date),
            _to_date(to_date),
            safe_limit,
            category,
        )
        return [_transaction_from_record(row) for row in rows]

    async def get_monthly_summary(
        self,
        *,
        user_id: str,
        from_date: str,
        to_date: str,
        category: str | None = None,
    ) -> tuple[MonthlySummary, list[CategoryTotal]]:
        totals_rows = await self._fetch(
            """
            select
              coalesce(sum(case when t.kind = 'expense' then t.amount_cents end), 0)::int
                as expense_cents,
              coalesce(sum(case when t.kind = 'income' then t.amount_cents end), 0)::int
                as income_cents,
              count(*)::int as transaction_count
            from transactions t
            left join categories c on c.id = t.category_id
            where t.user_id = $1::uuid
              and t.status <> 'deleted'
              and t.occurred_at between $2::date and $3::date
              and ($4::text is null or c.name = $4)
            """,
            user_id,
            _to_date(from_date),
            _to_date(to_date),
            category,
        )
        totals_row = totals_rows[0]
        totals = MonthlySummary(
            expense_cents=int(totals_row["expense_cents"]),
            income_cents=int(totals_row["income_cents"]),
            transaction_count=int(totals_row["transaction_count"]),
        )

        category_rows = await self._fetch(
            """
            select coalesce(c.name, 'Sem categoria') as category,
                   sum(t.amount_cents)::int as total_cents
            from transactions t
            left join categories c on c.id = t.category_id
            where t.user_id = $1::uuid
              and t.kind = 'expense'
              and t.status <> 'deleted'
              and t.occurred_at between $2::date and $3::date
              and ($4::text is null or c.name = $4)
            group by 1
            order by 2 desc
            """,
            user_id,
            _to_date(from_date),
            _to_date(to_date),
            category,
        )
        by_category = [
            CategoryTotal(category=row["category"], total_cents=int(row["total_cents"]))
            for row in category_rows
        ]

        return totals, by_category

    async def get_latest_transaction(self, user_id: str) -> Transaction | None:
        rows = await self._fetch(
            """
            select t.id, t.user_id, t.category_id, c.name as category_name, t.kind,
                   t.amount_cents, t.description,
                   to_char(t.occurred_at, 'YYYY-MM-DD') as occurred_at,
                   t.status, t.created_at
            from transactions t
            left join categories c on c.id = t.category_id
            where t.user_id = $1::uuid and t.status <> 'deleted'
            order by t.created_at desc
            limit 1
            """,
            user_id,
        )
        return _transaction_from_record(rows[0]) if rows else None

    async def update_transaction(
        self,
        *,
        user_id: str,
        transaction_id: str,
        amount: float | None = None,
        description: str | None = None,
        category_name: str | None = None,
        occurred_at: str | None = None,
    ) -> Transaction | None:
        category_id: str | None = None
        if category_name:
            category_rows = await self._fetch(
                """
                select id from categories
                where user_id = $1::uuid and name = $2
                limit 1
                """,
                user_id,
                category_name,
            )
            if category_rows:
                category_id = str(category_rows[0]["id"])

        rows = await self._fetch(
            """
            with target as (
              select * from transactions
              where id = $2::uuid
                and user_id = $1::uuid
                and status <> 'deleted'
            ),
            updated as (
              update transactions t
              set amount_cents = coalesce($3::int, t.amount_cents),
                  description = coalesce($4::text, t.description),
                  category_id = coalesce($5::uuid, t.category_id),
                  occurred_at = coalesce($6::date, t.occurred_at),
                  status = 'corrected'
              from target
              where t.id = target.id
              returning t.id, t.user_id, t.category_id, t.kind, t.amount_cents,
                        t.description, t.occurred_at, t.status, t.created_at
            ),
            audit as (
              insert into audit_log (user_id, transaction_id, action, before, after)
              select target.user_id, target.id, 'correct', to_jsonb(target), to_jsonb(updated)
              from target
              join updated on updated.id = target.id
              returning id
            )
            select u.id, u.user_id, u.category_id, c.name as category_name, u.kind,
                   u.amount_cents, u.description,
                   to_char(u.occurred_at, 'YYYY-MM-DD') as occurred_at,
                   u.status, u.created_at
            from updated u
            left join categories c on c.id = u.category_id
            """,
            user_id,
            transaction_id,
            round(amount * 100) if amount is not None else None,
            description,
            category_id,
            _to_date(occurred_at) if occurred_at else None,
        )
        return _transaction_from_record(rows[0]) if rows else None

    async def delete_transaction(
        self,
        *,
        user_id: str,
        transaction_id: str,
    ) -> Transaction | None:
        rows = await self._fetch(
            """
            with target as (
              select * from transactions
              where id = $2::uuid
                and user_id = $1::uuid
                and status <> 'deleted'
            ),
            deleted as (
              update transactions t
              set status = 'deleted'
              from target
              where t.id = target.id
              returning t.id, t.user_id, t.category_id, t.kind, t.amount_cents,
                        t.description, t.occurred_at, t.status, t.created_at
            ),
            audit as (
              insert into audit_log (user_id, transaction_id, action, before, after)
              select target.user_id, target.id, 'delete', to_jsonb(target), to_jsonb(deleted)
              from target
              join deleted on deleted.id = target.id
              returning id
            )
            select d.id, d.user_id, d.category_id, c.name as category_name, d.kind,
                   d.amount_cents, d.description,
                   to_char(d.occurred_at, 'YYYY-MM-DD') as occurred_at,
                   d.status, d.created_at
            from deleted d
            left join categories c on c.id = d.category_id
            """,
            user_id,
            transaction_id,
        )
        return _transaction_from_record(rows[0]) if rows else None

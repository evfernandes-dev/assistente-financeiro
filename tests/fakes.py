from __future__ import annotations

import datetime as dt
import json
from typing import Any

from app.models import (
    AudioInput,
    CategoryTotal,
    Kind,
    MonthlySummary,
    TelegramAudioFile,
    Transaction,
    User,
)


class InMemoryRepository:
    def __init__(self) -> None:
        self.users: list[User] = []
        self.transactions: list[Transaction] = []
        self.audit: list[dict[str, Any]] = []
        self._user_seq = 0
        self._tx_seq = 0

    async def ensure_user(
        self,
        telegram_id: int | str,
        first_name: str | None = None,
        username: str | None = None,
    ) -> User:
        telegram_id_text = str(telegram_id)

        for user in self.users:
            if user.telegram_id == telegram_id_text:
                user.first_name = first_name
                user.username = username
                return user

        self._user_seq += 1
        user = User(
            id=f"user-{self._user_seq}",
            telegram_id=telegram_id_text,
            first_name=first_name,
            username=username,
        )
        self.users.append(user)
        return user

    def _next_created_at(self) -> str:
        base = dt.datetime.now(dt.UTC) + dt.timedelta(microseconds=self._tx_seq)
        return base.isoformat()

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
        self._tx_seq += 1
        category_name = category or "Outros"
        transaction = Transaction(
            id=f"tx-{self._tx_seq}",
            user_id=user_id,
            category_id=f"cat-{category_name}",
            category_name=category_name,
            kind=kind,
            amount_cents=round(amount * 100),
            description=description,
            occurred_at=occurred_at,
            status="confirmed",
            created_at=self._next_created_at(),
        )
        self.transactions.append(transaction)
        self.audit.append(
            {
                "action": "create",
                "transaction_id": transaction.id,
                "after": transaction,
                "raw_text": raw_text,
                "source": source,
            }
        )
        return transaction

    async def list_transactions(
        self,
        *,
        user_id: str,
        from_date: str,
        to_date: str,
        limit: int = 20,
        category: str | None = None,
    ) -> list[Transaction]:
        rows = [
            transaction
            for transaction in self.transactions
            if transaction.user_id == user_id
            and transaction.status != "deleted"
            and from_date <= transaction.occurred_at <= to_date
            and (category is None or transaction.category_name == category)
        ]
        rows.sort(key=lambda item: (item.occurred_at, item.created_at), reverse=True)
        return rows[: min(max(limit, 1), 100)]

    async def get_monthly_summary(
        self,
        *,
        user_id: str,
        from_date: str,
        to_date: str,
        category: str | None = None,
    ) -> tuple[MonthlySummary, list[CategoryTotal]]:
        rows = [
            transaction
            for transaction in self.transactions
            if transaction.user_id == user_id
            and transaction.status != "deleted"
            and from_date <= transaction.occurred_at <= to_date
            and (category is None or transaction.category_name == category)
        ]

        totals = MonthlySummary(
            expense_cents=sum(row.amount_cents for row in rows if row.kind == "expense"),
            income_cents=sum(row.amount_cents for row in rows if row.kind == "income"),
            transaction_count=len(rows),
        )

        grouped: dict[str, int] = {}
        for row in rows:
            if row.kind != "expense":
                continue
            key = row.category_name or "Sem categoria"
            grouped[key] = grouped.get(key, 0) + row.amount_cents

        by_category = [
            CategoryTotal(category=name, total_cents=total)
            for name, total in sorted(grouped.items(), key=lambda item: item[1], reverse=True)
        ]

        return totals, by_category

    async def get_latest_transaction(self, user_id: str) -> Transaction | None:
        rows = [
            transaction
            for transaction in self.transactions
            if transaction.user_id == user_id and transaction.status != "deleted"
        ]
        return max(rows, key=lambda item: item.created_at) if rows else None

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
        for index, transaction in enumerate(self.transactions):
            if (
                transaction.id != transaction_id
                or transaction.user_id != user_id
                or transaction.status == "deleted"
            ):
                continue

            updated = Transaction(
                id=transaction.id,
                user_id=transaction.user_id,
                category_id=f"cat-{category_name}" if category_name else transaction.category_id,
                category_name=category_name or transaction.category_name,
                kind=transaction.kind,
                amount_cents=(
                    round(amount * 100) if amount is not None else transaction.amount_cents
                ),
                description=description or transaction.description,
                occurred_at=occurred_at or transaction.occurred_at,
                status="corrected",
                created_at=transaction.created_at,
            )
            self.transactions[index] = updated
            self.audit.append(
                {
                    "action": "correct",
                    "transaction_id": updated.id,
                    "before": transaction,
                    "after": updated,
                }
            )
            return updated

        return None

    async def delete_transaction(
        self,
        *,
        user_id: str,
        transaction_id: str,
    ) -> Transaction | None:
        for index, transaction in enumerate(self.transactions):
            if (
                transaction.id != transaction_id
                or transaction.user_id != user_id
                or transaction.status == "deleted"
            ):
                continue

            deleted = Transaction(
                id=transaction.id,
                user_id=transaction.user_id,
                category_id=transaction.category_id,
                category_name=transaction.category_name,
                kind=transaction.kind,
                amount_cents=transaction.amount_cents,
                description=transaction.description,
                occurred_at=transaction.occurred_at,
                status="deleted",
                created_at=transaction.created_at,
            )
            self.transactions[index] = deleted
            self.audit.append(
                {
                    "action": "delete",
                    "transaction_id": deleted.id,
                    "before": transaction,
                    "after": deleted,
                }
            )
            return deleted

        return None


class FakeGroq:
    def __init__(self, content: str | dict[str, Any] | Exception = "{}") -> None:
        self.content = content
        self.chat_calls: list[dict[str, Any]] = []
        self.audio_calls: list[AudioInput] = []
        self.transcription_text = "mercado 87,50"
        self.transcription_error: Exception | None = None

    async def chat(self, messages: list[dict[str, str]], *, json_mode: bool = False) -> str:
        self.chat_calls.append({"messages": messages, "json_mode": json_mode})
        if isinstance(self.content, Exception):
            raise self.content
        if isinstance(self.content, str):
            return self.content
        return json.dumps(self.content)

    async def transcribe(self, audio: AudioInput) -> str:
        self.audio_calls.append(audio)
        if self.transcription_error is not None:
            raise self.transcription_error
        return self.transcription_text


class FakeTelegram:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []
        self.downloaded: list[TelegramAudioFile] = []
        self.audio = AudioInput(data=b"\x01\x02\x03", mime_type="audio/ogg", file_name="audio.ogg")

    async def send_message(self, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))

    async def download_audio(self, file: TelegramAudioFile) -> AudioInput:
        self.downloaded.append(file)
        return self.audio

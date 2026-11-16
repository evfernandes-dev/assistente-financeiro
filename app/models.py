from dataclasses import dataclass, field
from typing import Literal

Kind = Literal["expense", "income"]
Source = Literal["text", "audio", "manual", "import"]
Intent = Literal[
    "create_expense",
    "create_income",
    "query",
    "report",
    "correct",
    "delete",
    "unknown",
]
CorrectionField = Literal["amount", "description", "category", "date"]


@dataclass(slots=True)
class User:
    id: str
    telegram_id: str
    first_name: str | None = None
    username: str | None = None
    timezone: str = "America/Recife"
    currency: str = "BRL"


@dataclass(slots=True)
class Transaction:
    id: str
    user_id: str
    category_id: str | None
    category_name: str | None
    kind: Kind
    amount_cents: int
    description: str
    occurred_at: str
    status: str
    created_at: str


@dataclass(slots=True)
class MonthlySummary:
    expense_cents: int = 0
    income_cents: int = 0
    transaction_count: int = 0


@dataclass(slots=True)
class CategoryTotal:
    category: str
    total_cents: int


@dataclass(slots=True)
class ExtractedTransaction:
    kind: Kind = "expense"
    amount: float | None = None
    description: str | None = None
    category: str | None = None
    occurred_at: str | None = None


@dataclass(slots=True)
class ExtractionCorrection:
    reference: str | None = None
    field: CorrectionField | None = None
    new_value: str | None = None


@dataclass(slots=True)
class ExtractionQuery:
    period: str | None = None
    category: str | None = None


@dataclass(slots=True)
class ExtractionResult:
    intent: Intent = "unknown"
    transaction: ExtractedTransaction | None = None
    correction: ExtractionCorrection | None = None
    query: ExtractionQuery | None = None
    confidence: float | None = None
    missing: list[str] = field(default_factory=list)
    reply_if_unclear: str | None = None


@dataclass(slots=True)
class AudioInput:
    data: bytes
    mime_type: str | None = None
    file_name: str | None = None


@dataclass(slots=True)
class TelegramAudioFile:
    file_id: str
    mime_type: str | None = None
    file_size: int | None = None

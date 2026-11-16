from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import math
import re
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from .categories import CATEGORY_NAMES
from .db import FinanceRepository
from .groq import GroqClient
from .models import (
    ExtractedTransaction,
    ExtractionCorrection,
    ExtractionQuery,
    ExtractionResult,
    Intent,
    User,
)
from .reports import brl, format_confirmation, format_monthly_report, format_transaction_list

logger = logging.getLogger(__name__)

VALID_INTENTS: set[str] = {
    "create_expense",
    "create_income",
    "query",
    "report",
    "correct",
    "delete",
    "unknown",
}
VALID_PERIODS: set[str] = {"today", "yesterday", "current_month", "last_month", "this_year"}
VALID_CORRECTION_FIELDS: set[str] = {"amount", "description", "category", "date"}
MAX_TEXT_LENGTH = 4000
MAX_DESCRIPTION_LENGTH = 200
MAX_AMOUNT = 20_000_000

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _as_dict(value: object) -> dict[str, object] | None:
    return value if isinstance(value, dict) else None


def _string_value(value: object, max_length: int) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:max_length]


def parse_amount(value: object) -> float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None

    if not isinstance(value, str):
        return None

    cleaned = re.sub(r"[^\d,.]", "", value)
    cleaned = re.sub(r"\.(?=\d{3}(?:\D|$))", "", cleaned)
    cleaned = cleaned.replace(",", ".")

    if not cleaned:
        return None

    try:
        parsed = float(cleaned)
    except ValueError:
        return None

    return parsed if math.isfinite(parsed) else None


def parse_date(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    trimmed = value.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", trimmed):
        return None

    try:
        dt.date.fromisoformat(trimmed)
    except ValueError:
        return None

    return trimmed


def _normalise_date(value: object, fallback: str) -> str:
    return parse_date(value) or fallback


def normalise_category(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    target = value.strip().casefold()
    for name in CATEGORY_NAMES:
        if name.casefold() == target:
            return name
    return None


def today_in_timezone(timezone: str) -> str:
    try:
        zone = ZoneInfo(timezone)
    except (KeyError, ValueError):
        zone = ZoneInfo("America/Recife")
    return dt.datetime.now(zone).date().isoformat()


def resolve_period(period: str | None, today: str) -> tuple[str, str]:
    current = dt.date.fromisoformat(today)

    if period == "today":
        return today, today

    if period == "yesterday":
        yesterday = (current - dt.timedelta(days=1)).isoformat()
        return yesterday, yesterday

    if period == "last_month":
        last_day = current.replace(day=1) - dt.timedelta(days=1)
        return last_day.replace(day=1).isoformat(), last_day.isoformat()

    if period == "this_year":
        return f"{current.year}-01-01", today

    return f"{current.year}-{current.month:02d}-01", today


def sanitise_extraction(raw: str, today: str) -> ExtractionResult:
    without_fence = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE)
    without_fence = re.sub(r"```$", "", without_fence).strip()
    start = without_fence.find("{")
    end = without_fence.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("Resposta da IA sem JSON")

    parsed = json.loads(without_fence[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Resposta da IA não é um objeto JSON")

    intent_value = parsed.get("intent")
    intent_text = intent_value.strip().lower() if isinstance(intent_value, str) else ""
    intent: Intent = intent_text if intent_text in VALID_INTENTS else "unknown"  # type: ignore[assignment]

    result = ExtractionResult(
        intent=intent,
        reply_if_unclear=_string_value(parsed.get("reply_if_unclear"), 300),
    )

    transaction = _as_dict(parsed.get("transaction"))
    if transaction is not None:
        kind_value = transaction.get("kind")
        result.transaction = ExtractedTransaction(
            kind="income" if kind_value == "income" else "expense",
            amount=parse_amount(transaction.get("amount")),
            description=_string_value(transaction.get("description"), MAX_DESCRIPTION_LENGTH),
            category=normalise_category(transaction.get("category")),
            occurred_at=_normalise_date(transaction.get("occurred_at"), today),
        )

    correction = _as_dict(parsed.get("correction"))
    if correction is not None:
        field_value = correction.get("field")
        field_text = field_value.strip().lower() if isinstance(field_value, str) else ""
        result.correction = ExtractionCorrection(
            reference=_string_value(correction.get("reference"), 60),
            field=field_text if field_text in VALID_CORRECTION_FIELDS else None,  # type: ignore[arg-type]
            new_value=_string_value(correction.get("new_value"), MAX_DESCRIPTION_LENGTH),
        )

    query = _as_dict(parsed.get("query"))
    if query is not None:
        period_value = query.get("period")
        period_text = period_value.strip().lower() if isinstance(period_value, str) else ""
        result.query = ExtractionQuery(
            period=period_text if period_text in VALID_PERIODS else None,
            category=normalise_category(query.get("category")),
        )

    confidence = parsed.get("confidence")
    if (
        isinstance(confidence, (int, float))
        and not isinstance(confidence, bool)
        and math.isfinite(confidence)
    ):
        result.confidence = min(max(float(confidence), 0.0), 1.0)

    missing = parsed.get("missing")
    if isinstance(missing, list):
        result.missing = [item[:120] for item in missing if isinstance(item, str)][:5]

    return result


@lru_cache
def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


async def extract_intent(
    text: str,
    user: User,
    groq: GroqClient,
) -> ExtractionResult:
    today = today_in_timezone(user.timezone)
    content = "\n".join(
        [
            _load_prompt("expense-extraction.md"),
            "",
            f"Data atual: {today}",
            f"Moeda: {user.currency}",
            "",
            f'Mensagem do usuário: """{text}"""',
        ]
    )

    raw = await groq.chat(
        [
            {"role": "system", "content": _load_prompt("financial-agent.md")},
            {"role": "user", "content": content},
        ],
        json_mode=True,
    )

    return sanitise_extraction(raw, today)


async def handle_financial_message(
    *,
    user: User,
    text: str,
    source: str,
    repo: FinanceRepository,
    groq: GroqClient,
) -> str:
    text = text.strip()[:MAX_TEXT_LENGTH]
    today = today_in_timezone(user.timezone)

    try:
        extraction = await extract_intent(text, user, groq)
    except Exception:
        logger.exception("extract_intent falhou")
        return "⚠️ Não consegui interpretar sua mensagem agora. Tente novamente em instantes."

    if extraction.intent in {"create_expense", "create_income"}:
        transaction = extraction.transaction
        amount = parse_amount(transaction.amount if transaction else None)
        description = (
            transaction.description.strip() if transaction and transaction.description else None
        )

        if (
            transaction is None
            or not description
            or amount is None
            or amount <= 0
            or amount > MAX_AMOUNT
        ):
            return (
                extraction.reply_if_unclear
                or "🤔 Não entendi o valor ou a descrição. Pode repetir? Exemplo: mercado 87,50."
            )

        created = await repo.create_transaction(
            user_id=user.id,
            kind="income" if extraction.intent == "create_income" else "expense",
            amount=amount,
            description=description,
            category=transaction.category,
            occurred_at=_normalise_date(transaction.occurred_at, today),
            source=source,
            raw_text=text,
        )
        return format_confirmation(created)

    if extraction.intent == "query":
        period = extraction.query.period if extraction.query else None
        category = extraction.query.category if extraction.query else None
        from_date, to_date = resolve_period(period, today)

        transactions, summary_result = await asyncio.gather(
            repo.list_transactions(
                user_id=user.id,
                from_date=from_date,
                to_date=to_date,
                limit=20,
                category=category,
            ),
            repo.get_monthly_summary(
                user_id=user.id,
                from_date=from_date,
                to_date=to_date,
                category=category,
            ),
        )
        summary, _ = summary_result
        balance = summary.income_cents - summary.expense_cents
        return format_transaction_list(transactions, from_date, to_date, balance)

    if extraction.intent == "report":
        period = (extraction.query.period if extraction.query else None) or "current_month"
        category = extraction.query.category if extraction.query else None
        from_date, to_date = resolve_period(period, today)
        summary, by_category = await repo.get_monthly_summary(
            user_id=user.id,
            from_date=from_date,
            to_date=to_date,
            category=category,
        )
        return format_monthly_report(summary, by_category, from_date, to_date)

    if extraction.intent == "correct":
        latest = await repo.get_latest_transaction(user.id)
        if latest is None:
            return "📭 Não encontrei nenhum lançamento para corrigir."

        field = extraction.correction.field if extraction.correction else None
        new_value = extraction.correction.new_value if extraction.correction else None
        transaction = extraction.transaction
        changes: dict[str, object] = {}

        amount = (
            parse_amount(new_value)
            if field == "amount"
            else parse_amount(transaction.amount if transaction else None)
        )
        if amount is not None and 0 < amount <= MAX_AMOUNT:
            changes["amount"] = amount

        if field == "description" and new_value:
            changes["description"] = new_value
        elif transaction and transaction.description:
            changes["description"] = transaction.description

        if field == "category":
            category = normalise_category(new_value)
            if category:
                changes["category_name"] = category
        elif transaction and transaction.category:
            changes["category_name"] = transaction.category

        if field == "date" and new_value:
            date = parse_date(new_value)
            if date:
                changes["occurred_at"] = date

        if not changes:
            return "🤔 Não entendi o que devo corrigir. Diga o campo e o novo valor."

        updated = await repo.update_transaction(
            user_id=user.id,
            transaction_id=latest.id,
            **changes,  # type: ignore[arg-type]
        )
        if updated is None:
            return "📭 Não encontrei esse lançamento para corrigir."

        return f"✏️ Corrigi o lançamento: {updated.description} — {brl(updated.amount_cents)}."

    if extraction.intent == "delete":
        latest = await repo.get_latest_transaction(user.id)
        if latest is None:
            return "📭 Não encontrei nenhum lançamento para excluir."

        deleted = await repo.delete_transaction(user_id=user.id, transaction_id=latest.id)
        if deleted is None:
            return "📭 Não encontrei esse lançamento para excluir."

        return f"🗑️ Excluí o lançamento: {deleted.description} — {brl(deleted.amount_cents)}."

    return (
        extraction.reply_if_unclear
        or '🤔 Não entendi. Você pode registrar ("mercado 87,50"), consultar '
        '("gastos de hoje") ou pedir um relatório ("relatório do mês").'
    )

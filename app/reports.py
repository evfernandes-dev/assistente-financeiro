from .models import CategoryTotal, MonthlySummary, Transaction


def brl(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    value = abs(cents) / 100
    formatted = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{sign}R$ {formatted}"


def format_confirmation(transaction: Transaction) -> str:
    label = "💸 Gasto registrado" if transaction.kind == "expense" else "💰 Receita registrada"
    category = transaction.category_name or "Sem categoria"

    return "\n".join(
        [
            f"{label}: {transaction.description}",
            f"💵 Valor: {brl(transaction.amount_cents)}",
            f"🏷️ Categoria: {category}",
            f"📅 Data: {transaction.occurred_at}",
        ]
    )


def format_transaction_list(
    transactions: list[Transaction],
    from_date: str,
    to_date: str,
    balance_cents: int,
) -> str:
    if not transactions:
        return f"📭 Nenhum lançamento entre {from_date} e {to_date}."

    lines = [f"📋 Lançamentos de {from_date} a {to_date}"]
    for transaction in transactions:
        emoji = "💸" if transaction.kind == "expense" else "💰"
        sign = "-" if transaction.kind == "expense" else "+"
        lines.append(
            f"{emoji} {transaction.occurred_at} · {transaction.description} · "
            f"{sign}{brl(transaction.amount_cents)}"
        )

    lines.extend(["", f"⚖️ Saldo do período: {brl(balance_cents)}"])
    return "\n".join(lines)


def format_monthly_report(
    summary: MonthlySummary,
    by_category: list[CategoryTotal],
    from_date: str,
    to_date: str,
) -> str:
    lines = [
        f"📊 Relatório de {from_date} a {to_date}",
        f"💰 Receitas: {brl(summary.income_cents)}",
        f"💸 Despesas: {brl(summary.expense_cents)}",
        f"⚖️ Saldo: {brl(summary.income_cents - summary.expense_cents)}",
        f"🧾 Lançamentos: {summary.transaction_count}",
    ]

    if by_category:
        lines.extend(["", "🏷️ Despesas por categoria:"])
        for row in by_category:
            lines.append(f"• {row.category}: {brl(row.total_cents)}")

    return "\n".join(lines)

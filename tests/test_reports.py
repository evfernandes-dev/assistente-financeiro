from app.models import CategoryTotal, MonthlySummary, Transaction
from app.reports import brl, format_confirmation, format_monthly_report, format_transaction_list

TRANSACTION = Transaction(
    id="tx-1",
    user_id="user-1",
    category_id="cat-1",
    category_name="Alimentação",
    kind="expense",
    amount_cents=8750,
    description="Mercado",
    occurred_at="2026-10-31",
    status="confirmed",
    created_at="2026-10-31T12:00:00+00:00",
)


def test_brl_formata_moeda_brasileira() -> None:
    value = brl(123456)
    assert "R$" in value
    assert "1.234,56" in value


def test_format_confirmation_descreve_despesa_e_receita() -> None:
    expense = format_confirmation(TRANSACTION)
    assert "Gasto registrado: Mercado" in expense
    assert "💸" in expense

    income = format_confirmation(
        Transaction(
            id="tx-2",
            user_id="user-1",
            category_id="cat-2",
            category_name="Salário",
            kind="income",
            amount_cents=350000,
            description="Salário",
            occurred_at="2026-10-31",
            status="confirmed",
            created_at="2026-10-31T12:00:00+00:00",
        )
    )
    assert "Receita registrada: Salário" in income
    assert "💰" in income


def test_format_transaction_list_mostra_lancamentos_e_saldo() -> None:
    result = format_transaction_list(
        [
            TRANSACTION,
            Transaction(
                id="tx-2",
                user_id="user-1",
                category_id="cat-2",
                category_name="Salário",
                kind="income",
                amount_cents=350000,
                description="Salário",
                occurred_at="2026-10-31",
                status="confirmed",
                created_at="2026-10-31T12:01:00+00:00",
            ),
        ],
        "2026-10-01",
        "2026-10-31",
        341250,
    )

    assert "Mercado" in result
    assert "Salário" in result
    assert "Saldo do período" in result
    assert "📋" in result
    assert "⚖️" in result
    assert "💸" in result
    assert "💰" in result


def test_format_transaction_list_informa_lista_vazia() -> None:
    result = format_transaction_list([], "2026-10-01", "2026-10-31", 0)
    assert "Nenhum lançamento" in result
    assert "📭" in result


def test_format_monthly_report_monta_totais_e_categorias() -> None:
    totals = MonthlySummary(expense_cents=15000, income_cents=200000, transaction_count=3)
    by_category = [
        CategoryTotal(category="Alimentação", total_cents=10000),
        CategoryTotal(category="Transporte", total_cents=5000),
    ]

    result = format_monthly_report(totals, by_category, "2026-10-01", "2026-10-31")

    assert "Receitas" in result
    assert "Despesas" in result
    assert "Saldo" in result
    assert "Alimentação" in result
    assert "Transporte" in result
    assert "📊" in result
    assert "🏷️" in result
    assert "💰" in result
    assert "💸" in result
    assert "⚖️" in result

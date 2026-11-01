import { describe, expect, it } from "vitest";
import {
  brl,
  formatConfirmation,
  formatMonthlyReport,
  formatTransactionList,
} from "../src/reports";
import type { CategoryTotal, MonthlySummary, Transaction } from "../src/expenses";

const transaction: Transaction = {
  id: "tx-1",
  user_id: "user-1",
  category_id: "cat-1",
  category_name: "Alimentação",
  kind: "expense",
  amount_cents: 8750,
  description: "Mercado",
  occurred_at: "2026-10-31",
  status: "confirmed",
  created_at: "2026-10-31T12:00:00Z",
};

describe("brl", () => {
  it("formata centavos como moeda brasileira", () => {
    const value = brl(123456);
    expect(value).toContain("R$");
    expect(value).toContain("1.234,56");
  });
});

describe("formatConfirmation", () => {
  it("descreve despesa e receita", () => {
    expect(formatConfirmation(transaction)).toContain("Gasto registrado: Mercado");
    expect(formatConfirmation(transaction)).toContain("💸");
    expect(
      formatConfirmation({ ...transaction, kind: "income", description: "Salário" }),
    ).toContain("Receita registrada: Salário");
    expect(
      formatConfirmation({ ...transaction, kind: "income", description: "Salário" }),
    ).toContain("💰");
  });
});

describe("formatTransactionList", () => {
  it("lista lançamentos com o saldo do período", () => {
    const result = formatTransactionList(
      [
        transaction,
        {
          ...transaction,
          id: "tx-2",
          kind: "income",
          description: "Salário",
          amount_cents: 350000,
        },
      ],
      "2026-10-01",
      "2026-10-31",
      341250,
    );

    expect(result).toContain("Mercado");
    expect(result).toContain("Salário");
    expect(result).toContain("Saldo do período");
    expect(result).toContain("📋");
    expect(result).toContain("⚖️");
    expect(result).toContain("💸");
    expect(result).toContain("💰");
  });

  it("informa quando não há lançamentos", () => {
    expect(formatTransactionList([], "2026-10-01", "2026-10-31", 0)).toContain(
      "Nenhum lançamento",
    );
    expect(formatTransactionList([], "2026-10-01", "2026-10-31", 0)).toContain("📭");
  });
});

describe("formatMonthlyReport", () => {
  it("monta totais e despesas por categoria", () => {
    const totals: MonthlySummary = {
      expense_cents: 15000,
      income_cents: 200000,
      transaction_count: 3,
    };
    const byCategory: CategoryTotal[] = [
      { category: "Alimentação", total_cents: 10000 },
      { category: "Transporte", total_cents: 5000 },
    ];

    const result = formatMonthlyReport(totals, byCategory, "2026-10-01", "2026-10-31");

    expect(result).toContain("Receitas");
    expect(result).toContain("Despesas");
    expect(result).toContain("Saldo");
    expect(result).toContain("Alimentação");
    expect(result).toContain("Transporte");
    expect(result).toContain("📊");
    expect(result).toContain("🏷️");
    expect(result).toContain("💰");
    expect(result).toContain("💸");
    expect(result).toContain("⚖️");
  });
});

import type { CategoryTotal, MonthlySummary, Transaction } from "./expenses";

export function brl(cents: number): string {
  return (cents / 100).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

export function formatConfirmation(transaction: Transaction): string {
  const label = transaction.kind === "expense" ? "Gasto registrado" : "Receita registrada";
  const category = transaction.category_name ?? "Sem categoria";

  return [
    `${label}: ${transaction.description}`,
    `Valor: ${brl(transaction.amount_cents)}`,
    `Categoria: ${category}`,
    `Data: ${transaction.occurred_at}`,
  ].join("\n");
}

export function formatTransactionList(
  transactions: Transaction[],
  from: string,
  to: string,
  balanceCents: number,
): string {
  if (transactions.length === 0) {
    return `Nenhum lançamento entre ${from} e ${to}.`;
  }

  const lines = transactions.map((transaction) => {
    const sign = transaction.kind === "expense" ? "-" : "+";
    return `${transaction.occurred_at} · ${transaction.description} · ${sign}${brl(transaction.amount_cents)}`;
  });

  return [...lines, "", `Saldo do período: ${brl(balanceCents)}`].join("\n");
}

export function formatMonthlyReport(
  summary: MonthlySummary,
  byCategory: CategoryTotal[],
  from: string,
  to: string,
): string {
  const lines = [
    `Relatório de ${from} a ${to}`,
    `Receitas: ${brl(summary.income_cents)}`,
    `Despesas: ${brl(summary.expense_cents)}`,
    `Saldo: ${brl(summary.income_cents - summary.expense_cents)}`,
    `Lançamentos: ${summary.transaction_count}`,
  ];

  if (byCategory.length > 0) {
    lines.push("", "Despesas por categoria:");
    for (const row of byCategory) {
      lines.push(`- ${row.category}: ${brl(row.total_cents)}`);
    }
  }

  return lines.join("\n");
}
